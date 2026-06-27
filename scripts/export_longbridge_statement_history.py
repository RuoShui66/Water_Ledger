from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]


def run_longbridge(args: list[str]) -> object:
    exe = os.environ.get("LONGBRIDGE_CLI") or "longbridge"
    env = os.environ.copy()
    env.setdefault("LONGBRIDGE_REGION", "cn")
    output = subprocess.check_output([exe, *args], cwd=ROOT, env=env, text=True)
    return json.loads(output)


def parse_statement_date(value: str) -> date:
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").date()
    return datetime.strptime(text, "%Y-%m-%d").date()


def iso_day(value: date) -> str:
    return value.strftime("%Y-%m-%d")


def format_money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def convert_total(data: dict, balance: str, balance_currency: str, target_currency: str) -> str:
    balance_currency = balance_currency.upper()
    target_currency = target_currency.upper()
    if balance_currency == target_currency:
        return format_money(Decimal(balance))
    if balance_currency == "HKD" and target_currency == "USD":
        for row in data.get("account_balances") or []:
            if str(row.get("currency") or "").upper() == "USD" and row.get("rate"):
                return format_money(Decimal(balance) / Decimal(str(row["rate"])))
    raise RuntimeError(f"Cannot convert statement asset total from {balance_currency} to {target_currency}")


def first_asset_total(file_key: str, target_currency: str) -> str:
    data = run_longbridge(
        [
            "statement",
            "export",
            "--file-key",
            file_key,
            "--section",
            "asset",
            "--format",
            "json",
        ]
    )
    if not isinstance(data, dict):
        raise RuntimeError(f"Statement export did not return an object for {file_key}")
    asset_rows = data.get("asset") if isinstance(data, dict) else None
    if not asset_rows:
        raise RuntimeError(f"Statement asset section is empty for {file_key}")
    for row in asset_rows:
        if str(row.get("currency") or "").upper() == target_currency.upper():
            return convert_total(data, str(row["total"]), str(row.get("currency") or ""), target_currency)
    row = asset_rows[0]
    return convert_total(data, str(row["total"]), str(row.get("currency") or ""), target_currency)


def current_net_assets(currency: str) -> str:
    data = run_longbridge(["assets", "--currency", currency, "--format", "json"])
    if not isinstance(data, list) or not data:
        raise RuntimeError("Longbridge assets returned no rows")
    value = data[0].get("net_assets")
    if value in (None, ""):
        raise RuntimeError("Longbridge assets did not include net_assets")
    return str(value)


def build_rows(account: str, currency: str, start: date, end: date) -> list[dict[str, str]]:
    limit = max((end - start).days + 10, 30)
    statements = run_longbridge(
        [
            "statement",
            "--type",
            "daily",
            "--start-date",
            iso_day(start),
            "--limit",
            str(limit),
            "--format",
            "json",
        ]
    )
    if not isinstance(statements, list):
        raise RuntimeError("Longbridge statement list did not return a list")

    rows: list[dict[str, str]] = []
    seen_days: set[str] = set()
    for item in statements:
        if not isinstance(item, dict):
            continue
        statement_date = parse_statement_date(str(item.get("date") or ""))
        if statement_date < start or statement_date > end:
            continue
        file_key = str(item.get("file_key") or "")
        if not file_key:
            continue
        day = iso_day(statement_date)
        rows.append(
            {
                "account": account,
                "date": day,
                "balance": first_asset_total(file_key, currency),
                "currency": currency,
                "source": "longbridge_statement_history",
            }
        )
        seen_days.add(day)

    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    if start <= today <= end and iso_day(today) not in seen_days:
        rows.append(
            {
                "account": account,
                "date": iso_day(today),
                "balance": current_net_assets(currency),
                "currency": currency,
                "source": "longbridge_live_current",
            }
        )

    rows.sort(key=lambda row: row["date"])
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Longbridge daily net-asset history for Water Ledger.")
    parser.add_argument("--account", required=True)
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()
    if end < start:
        raise SystemExit("--end must be on or after --start")

    rows = build_rows(args.account, args.currency.upper(), start, end)
    print(json.dumps(rows, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
