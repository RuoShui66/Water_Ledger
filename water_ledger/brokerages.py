from __future__ import annotations

import json
import os
import shlex
import sqlite3
import ssl
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from water_ledger.config import config_section, mapping_account
from water_ledger.paths import DB_PATH, PRIVATE_ROOT, ROOT


TZ = ZoneInfo("Asia/Shanghai")
SNAPSHOT_DIR = PRIVATE_ROOT / "outputs" / "brokerage_snapshots"


@dataclass
class BrokerageSnapshot:
    provider: str
    account_name: str
    snapshot_at: str
    balance_cents: int
    currency: str
    raw: Any


def money_to_cents(value: Any) -> int:
    if isinstance(value, dict):
        for key in ("amount", "value"):
            if value.get(key) not in (None, ""):
                value = value[key]
                break
    if value is None:
        raise ValueError("missing balance value")
    text = str(value).replace(",", "").replace("￥", "").replace("¥", "").strip()
    amount = Decimal(text)
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def now_text() -> str:
    return datetime.now(TZ).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def normalize_provider_config(provider: str) -> dict[str, Any]:
    return config_section("brokerages").get(provider) or {}


def output_raw(provider: str, snapshot_at: str, raw: Any) -> Path:
    SNAPSHOT_DIR.joinpath(provider).mkdir(parents=True, exist_ok=True)
    filename = snapshot_at.replace("-", "").replace(":", "").replace(" ", "_")
    path = SNAPSHOT_DIR / provider / f"{filename}.json"
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def object_to_data(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): object_to_data(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [object_to_data(item) for item in value]
    if hasattr(value, "to_dict"):
        try:
            return object_to_data(value.to_dict())
        except TypeError:
            pass
    if hasattr(value, "__dict__"):
        return object_to_data({k: v for k, v in vars(value).items() if not k.startswith("_")})
    return str(value)


def json_path(data: Any, path: str) -> Any:
    current = data
    for part in path.split("."):
        if not part:
            continue
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            current = getattr(current, part)
    return current


def find_first_value(data: Any, keys: list[str]) -> Any:
    lowered = {key.lower().replace("_", "") for key in keys}

    def walk(value: Any) -> Any:
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower().replace("_", "") in lowered and item not in (None, ""):
                    return item
            for item in value.values():
                found = walk(item)
                if found not in (None, ""):
                    return found
        elif isinstance(value, list):
            for item in value:
                found = walk(item)
                if found not in (None, ""):
                    return found
        return None

    return walk(data)


def extract_balance(data: Any, config: dict[str, Any], default_keys: list[str]) -> Any:
    for path in config.get("balance_paths") or []:
        try:
            value = json_path(data, str(path))
        except (KeyError, IndexError, AttributeError, ValueError):
            continue
        if value not in (None, ""):
            return value
    value = find_first_value(data, default_keys)
    if value in (None, ""):
        raise ValueError(f"Cannot find balance value. Configure brokerages.<provider>.balance_paths.")
    return value


def extract_currency(data: Any, config: dict[str, Any], default: str = "USD") -> str:
    for path in config.get("currency_paths") or []:
        try:
            value = json_path(data, str(path))
        except (KeyError, IndexError, AttributeError, ValueError):
            continue
        if value:
            return str(value).upper()
    return str(config.get("currency") or default).upper()


def provider_account_name(provider: str, config: dict[str, Any]) -> str:
    account = str(config.get("account") or mapping_account("brokerage_account", "")).strip()
    if not account:
        raise SystemExit(
            f"Configure brokerages.{provider}.account in private/config.yaml, "
            "and add the matching brokerage account under accounts first."
        )
    return account


def fetch_longbridge(config: dict[str, Any], snapshot_at: str) -> BrokerageSnapshot:
    exe = str(config.get("executable") or (Path("/Users/water/.local/bin/longbridge") if Path("/Users/water/.local/bin/longbridge").exists() else "longbridge"))
    env = os.environ.copy()
    env.setdefault("LONGBRIDGE_REGION", str(config.get("region") or "cn"))
    currency = str(config.get("currency") or "USD").upper()
    assets = json.loads(subprocess.check_output([exe, "assets", "--currency", currency, "--format", "json"], cwd=ROOT, env=env, text=True))
    portfolio = json.loads(subprocess.check_output([exe, "portfolio", "--format", "json"], cwd=ROOT, env=env, text=True))
    asset_row = assets[0] if isinstance(assets, list) and assets else {}
    value = asset_row.get("net_assets")
    if value in (None, ""):
        value = (portfolio.get("overview") or {}).get("total_asset")
    raw = {
        "snapshot_at": snapshot_at,
        "assets": assets,
        "portfolio": portfolio,
        "selected_net_assets": value,
        "currency": currency,
    }
    return BrokerageSnapshot("longbridge", provider_account_name("longbridge", config), snapshot_at, money_to_cents(value), currency, raw)


def fetch_futu(config: dict[str, Any], snapshot_at: str) -> BrokerageSnapshot:
    try:
        from futu import Currency, OpenSecTradeContext, RET_OK, TrdEnv, TrdMarket
    except ImportError as exc:
        raise SystemExit("Missing optional dependency: futu-api. Install with `pip install futu-api` and run Futu OpenD.") from exc

    host = str(config.get("host") or os.environ.get("FUTU_OPEND_HOST") or "127.0.0.1")
    port = int(config.get("port") or os.environ.get("FUTU_OPEND_PORT") or 11111)
    market_name = str(config.get("market") or "US").upper()
    env_name = str(config.get("trd_env") or "REAL").upper()
    currency_name = str(config.get("currency") or "USD").upper()
    market = getattr(TrdMarket, market_name, TrdMarket.US)
    trd_env = getattr(TrdEnv, env_name, TrdEnv.REAL)
    currency = getattr(Currency, currency_name, Currency.USD)
    ctx = OpenSecTradeContext(filter_trdmarket=market, host=host, port=port)
    try:
        ret, data = ctx.accinfo_query(
            trd_env=trd_env,
            acc_id=int(config.get("acc_id") or 0),
            acc_index=int(config.get("acc_index") or 0),
            refresh_cache=bool(config.get("refresh_cache", False)),
            currency=currency,
        )
        if ret != RET_OK:
            raise RuntimeError(f"Futu accinfo_query failed: {data}")
        raw_data = object_to_data(data)
        rows = raw_data.get("data", raw_data) if isinstance(raw_data, dict) else raw_data
        row = rows[0] if isinstance(rows, list) and rows else raw_data
        value = extract_balance(row, config, ["total_assets", "net_assets", "net_asset", "total_asset"])
        raw = {"snapshot_at": snapshot_at, "account_info": raw_data, "selected_net_assets": value, "currency": currency_name}
        return BrokerageSnapshot("futu", provider_account_name("futu", config), snapshot_at, money_to_cents(value), currency_name, raw)
    finally:
        ctx.close()


def fetch_tiger(config: dict[str, Any], snapshot_at: str) -> BrokerageSnapshot:
    try:
        from tigeropen.tiger_open_config import get_client_config
        from tigeropen.trade.trade_client import TradeClient
    except ImportError as exc:
        raise SystemExit("Missing optional dependency: tigeropen. Install Tiger OpenAPI Python SDK first.") from exc

    def conf_value(key: str, env_key: str | None = None) -> Any:
        if config.get(key):
            return config[key]
        return os.environ.get(env_key or f"TIGER_{key.upper()}")

    client_config = get_client_config(
        private_key_path=conf_value("private_key_path", "TIGER_PRIVATE_KEY_PATH"),
        tiger_id=conf_value("tiger_id", "TIGER_ID"),
        account=conf_value("account_id", "TIGER_ACCOUNT"),
        secret_key=conf_value("secret_key", "TIGER_SECRET_KEY"),
    )
    trade_client = TradeClient(client_config)
    account_id = conf_value("account_id", "TIGER_ACCOUNT")
    mode = str(config.get("account_mode") or "auto").lower()
    if mode == "prime":
        assets = trade_client.get_prime_assets(account=account_id, base_currency=config.get("currency") or "USD")
    else:
        assets = trade_client.get_assets(account=account_id, market_value=bool(config.get("market_value", False)))
    raw_data = object_to_data(assets)
    row = raw_data[0] if isinstance(raw_data, list) and raw_data else raw_data
    value = extract_balance(
        row,
        config,
        ["net_liquidation", "net_liquidation_value", "net_assets", "total_assets", "equity_with_loan", "asset"],
    )
    currency = extract_currency(row, config, str(config.get("currency") or "USD"))
    raw = {"snapshot_at": snapshot_at, "assets": raw_data, "selected_net_assets": value, "currency": currency}
    return BrokerageSnapshot("tiger", provider_account_name("tiger", config), snapshot_at, money_to_cents(value), currency, raw)


def ibkr_get_json(base_url: str, path: str) -> Any:
    url = base_url.rstrip("/") + path
    ctx = ssl._create_unverified_context()
    request = urllib.request.Request(url, headers={"User-Agent": "water-ledger/0.1"})
    try:
        with urllib.request.urlopen(request, context=ctx, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"IBKR Client Portal Gateway request failed: {url}: {exc}") from exc


def fetch_ibkr(config: dict[str, Any], snapshot_at: str) -> BrokerageSnapshot:
    base_url = str(config.get("base_url") or os.environ.get("IBKR_CP_BASE_URL") or "https://localhost:5000/v1/api")
    account_id = config.get("account_id") or os.environ.get("IBKR_ACCOUNT_ID")
    accounts_raw = None
    if not account_id:
        accounts_raw = ibkr_get_json(base_url, "/portfolio/accounts")
        first = accounts_raw[0] if isinstance(accounts_raw, list) and accounts_raw else accounts_raw
        if isinstance(first, dict):
            account_id = first.get("id") or first.get("accountId") or first.get("accountIdKey") or first.get("accountIdValue")
        if not account_id:
            raise RuntimeError("Cannot determine IBKR account id. Configure brokerages.ibkr.account_id.")
    summary = ibkr_get_json(base_url, f"/portfolio/{account_id}/summary")
    value = extract_balance(summary, config, ["netliquidation", "net_liquidation", "netliquidationvalue"])
    currency = extract_currency(summary, config, "USD")
    raw = {
        "snapshot_at": snapshot_at,
        "accounts": accounts_raw,
        "account_id": account_id,
        "summary": summary,
        "selected_net_assets": value,
        "currency": currency,
    }
    return BrokerageSnapshot("ibkr", provider_account_name("ibkr", config), snapshot_at, money_to_cents(value), currency, raw)


def fetch_robinhood(config: dict[str, Any], snapshot_at: str) -> BrokerageSnapshot:
    command = config.get("command")
    if not command:
        raise SystemExit(
            "Robinhood official access is currently exposed through Robinhood Trading MCP. "
            "Configure brokerages.robinhood.command to run a local authenticated MCP bridge that prints JSON."
        )
    if isinstance(command, str):
        cmd = shlex.split(command)
    else:
        cmd = [str(part) for part in command]
    output = subprocess.check_output(cmd, cwd=ROOT, text=True)
    raw_data = json.loads(output)
    value = extract_balance(raw_data, config, ["net_liquidation", "netliquidation", "total_equity", "total_value", "equity"])
    currency = extract_currency(raw_data, config, "USD")
    raw = {"snapshot_at": snapshot_at, "mcp_bridge_response": raw_data, "selected_net_assets": value, "currency": currency}
    return BrokerageSnapshot("robinhood", provider_account_name("robinhood", config), snapshot_at, money_to_cents(value), currency, raw)


FETCHERS = {
    "longbridge": fetch_longbridge,
    "futu": fetch_futu,
    "tiger": fetch_tiger,
    "ibkr": fetch_ibkr,
    "robinhood": fetch_robinhood,
}


def save_snapshot(snapshot: BrokerageSnapshot, write_raw: bool = True) -> dict[str, Any]:
    if not DB_PATH.exists():
        raise SystemExit(f"Database does not exist: {DB_PATH}. Run `python -m water_ledger import` first.")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        account = conn.execute("SELECT id FROM accounts WHERE name = ?", (snapshot.account_name,)).fetchone()
        if not account:
            raise SystemExit(f"Missing account in config/database: {snapshot.account_name}")
        conn.execute(
            """
            INSERT OR REPLACE INTO asset_snapshots
              (account_id, snapshot_at, balance_cents, source, imported_transaction_id)
            VALUES (?, ?, ?, ?, NULL)
            """,
            (account["id"], snapshot.snapshot_at, snapshot.balance_cents, f"{snapshot.provider}_live"),
        )
        conn.commit()
    finally:
        conn.close()
    raw_path = output_raw(snapshot.provider, snapshot.snapshot_at, snapshot.raw) if write_raw else None
    return {
        "provider": snapshot.provider,
        "account": snapshot.account_name,
        "snapshot_at": snapshot.snapshot_at,
        "balance": snapshot.balance_cents / 100,
        "currency": snapshot.currency,
        "raw_path": str(raw_path) if raw_path else None,
    }


def fetch_provider(provider: str, snapshot_at: str | None = None) -> BrokerageSnapshot:
    name = provider.lower().strip()
    if name not in FETCHERS:
        raise SystemExit(f"Unsupported brokerage provider: {provider}. Supported: {', '.join(sorted(FETCHERS))}")
    config = normalize_provider_config(name)
    return FETCHERS[name](config, snapshot_at or now_text())


def enabled_providers() -> list[str]:
    brokerages = config_section("brokerages")
    return [name for name in FETCHERS if (brokerages.get(name) or {}).get("enabled")]


def run_snapshot(provider: str = "enabled", dry_run: bool = False, write_raw: bool = True) -> list[dict[str, Any]]:
    providers = enabled_providers() if provider == "enabled" else (list(FETCHERS) if provider == "all" else [provider])
    if not providers:
        raise SystemExit("No enabled brokerage providers. Enable one under brokerages.* in private/config.yaml.")
    results = []
    snapshot_at = now_text()
    for name in providers:
        snapshot = fetch_provider(name, snapshot_at=snapshot_at)
        results.append({
            "provider": snapshot.provider,
            "account": snapshot.account_name,
            "snapshot_at": snapshot.snapshot_at,
            "balance": snapshot.balance_cents / 100,
            "currency": snapshot.currency,
            "raw_path": None,
        } if dry_run else save_snapshot(snapshot, write_raw=write_raw))
    return results
