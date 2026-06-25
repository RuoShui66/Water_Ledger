#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = Path(os.environ.get("WATER_LEDGER_PRIVATE_DIR", ROOT / "private"))
DB_PATH = Path(os.environ.get("WATER_LEDGER_DB_PATH", PRIVATE_ROOT / "data" / "water_ledger.sqlite"))
OUT_DIR = PRIVATE_ROOT / "outputs" / "longbridge_live_snapshots"
LONG_BRIDGE = Path("/Users/water/.local/bin/longbridge")
TZ = ZoneInfo("Asia/Shanghai")


def cents(value: str | Decimal) -> int:
    amount = Decimal(str(value).replace(",", "").strip())
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def run_longbridge(*args: str) -> object:
    exe = str(LONG_BRIDGE) if LONG_BRIDGE.exists() else "longbridge"
    env = os.environ.copy()
    env.setdefault("LONGBRIDGE_REGION", "cn")
    output = subprocess.check_output([exe, *args, "--format", "json"], cwd=ROOT, env=env, text=True)
    return json.loads(output)


def main() -> None:
    now = datetime.now(TZ).replace(microsecond=0)
    snapshot_at = now.strftime("%Y-%m-%d %H:%M:%S")

    assets = run_longbridge("assets", "--currency", "USD")
    portfolio = run_longbridge("portfolio")
    asset_row = assets[0] if isinstance(assets, list) and assets else {}
    net_assets = Decimal(str(asset_row["net_assets"]))
    portfolio_total = Decimal(str(portfolio.get("overview", {}).get("total_asset", net_assets)))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = OUT_DIR / f"{now.strftime('%Y%m%d_%H%M%S')}.json"
    raw_path.write_text(
        json.dumps(
            {
                "snapshot_at": snapshot_at,
                "assets": assets,
                "portfolio": portfolio,
                "selected_net_assets_usd": str(net_assets),
                "portfolio_total_asset_usd": str(portfolio_total),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    account = conn.execute("SELECT id FROM accounts WHERE name = '美股账户'").fetchone()
    if not account:
        raise SystemExit("Missing account: 美股账户")
    conn.execute(
        """
        INSERT OR REPLACE INTO asset_snapshots
          (account_id, snapshot_at, balance_cents, source, imported_transaction_id)
        VALUES (?, ?, ?, 'longbridge_live', NULL)
        """,
        (account["id"], snapshot_at, cents(net_assets)),
    )
    conn.commit()
    print(
        json.dumps(
            {
                "snapshot_at": snapshot_at,
                "net_assets_usd": str(net_assets),
                "portfolio_total_asset_usd": str(portfolio_total),
                "raw_path": str(raw_path),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
