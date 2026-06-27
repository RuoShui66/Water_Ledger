from __future__ import annotations

import csv
import os
import sqlite3
from datetime import datetime, timedelta

from water_ledger.config import config_section, keyword_list, mapping_account, private_rules
from water_ledger.core.utils import cents, norm_text
from water_ledger.paths import PRIVATE_ROOT


def row_value(row: dict[str, str], *keys: str) -> str:
    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value not in (None, ""):
            return norm_text(value)
    return ""


def normalize_snapshot_at(value: str) -> str:
    text = norm_text(value)
    if len(text) == 10:
        datetime.strptime(text, "%Y-%m-%d")
        return f"{text} 23:59:59"
    parsed = datetime.fromisoformat(text)
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def import_brokerage_asset_history(conn: sqlite3.Connection, account_ids: dict[str, int]) -> None:
    """Import user-provided historical net-worth snapshots for any date range."""
    imports_dir = PRIVATE_ROOT / "imports" / "brokerage"
    if not imports_dir.exists():
        return
    account_currencies = {
        row["name"]: (row["currency"] or "CNY").upper()
        for row in conn.execute("SELECT name, currency FROM accounts")
    }
    for path in sorted(imports_dir.glob("*.csv")):
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                account_name = row_value(row, "account", "account_name", "账户", "账户名称")
                snapshot_at = row_value(row, "snapshot_at", "datetime", "date", "日期", "时间")
                balance = row_value(row, "balance", "net_worth", "net_assets", "amount", "净资产", "资产")
                if not account_name or not snapshot_at or not balance:
                    continue
                if account_name not in account_ids:
                    raise SystemExit(f"Brokerage history references unknown account: {account_name}")
                currency = row_value(row, "currency", "币种")
                expected_currency = account_currencies.get(account_name, "CNY")
                if currency and currency.upper() != expected_currency:
                    raise SystemExit(
                        f"Brokerage history currency mismatch for {account_name}: "
                        f"{currency.upper()} != {expected_currency}"
                    )
                source = row_value(row, "source", "provider", "来源") or f"brokerage_history:{path.name}"
                conn.execute(
                    """
                    INSERT OR REPLACE INTO asset_snapshots
                      (account_id, snapshot_at, balance_cents, source, imported_transaction_id)
                    VALUES (?, ?, ?, ?, NULL)
                    """,
                    (account_ids[account_name], normalize_snapshot_at(snapshot_at), cents(balance), source),
                )


def import_longbridge_asset_history(conn: sqlite3.Connection, account_ids: dict[str, int]) -> None:
    path = PRIVATE_ROOT / "outputs" / "longbridge_us_asset_daily_cny.csv"
    account_name = config_section("brokerages").get("longbridge", {}).get(
        "account",
        mapping_account("brokerage_account", ""),
    )
    if not path.exists() or account_name not in account_ids:
        return
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date = norm_text(row.get("date"))
            if not date:
                continue
            snapshot_date = datetime.strptime(date, "%Y-%m-%d").date() + timedelta(days=1)
            api_updated_date = norm_text(row.get("api_updated_date"))
            if api_updated_date:
                snapshot_date = min(snapshot_date, datetime.strptime(api_updated_date, "%Y-%m-%d").date())
            conn.execute(
                """
                INSERT OR REPLACE INTO asset_snapshots
                  (account_id, snapshot_at, balance_cents, source, imported_transaction_id)
                VALUES (?, ?, ?, 'longbridge_csv', NULL)
                """,
                (account_ids[account_name], f"{snapshot_date.isoformat()} 23:59:59", cents(row.get("ending_asset_usd"))),
            )

def backfill_manual_balance_history(conn: sqlite3.Connection) -> None:
    accounts = conn.execute(
        """
        SELECT id, name, account_type, manual_balance_cents, manual_balance_at
        FROM accounts
        WHERE manual_balance_cents IS NOT NULL
          AND manual_balance_at IS NOT NULL
          AND account_type != 'wallet'
        """
    ).fetchall()
    for account in accounts:
        authoritative_snapshot = conn.execute(
            """
            SELECT 1
              FROM asset_snapshots
             WHERE account_id = ?
               AND source NOT IN ('manual_current', 'manual_backfill', 'manual_opening_balance')
             LIMIT 1
            """,
            (account["id"],),
        ).fetchone()
        if authoritative_snapshot:
            continue
        conn.execute(
            """
            DELETE FROM asset_snapshots
             WHERE account_id = ?
               AND source IN ('manual_current', 'manual_backfill', 'manual_opening_balance')
            """,
            (account["id"],),
        )
        running = int(account["manual_balance_cents"])
        conn.execute(
            """
            INSERT OR REPLACE INTO asset_snapshots
              (account_id, snapshot_at, balance_cents, source, imported_transaction_id)
            VALUES (?, ?, ?, 'manual_current', NULL)
            """,
            (account["id"], account["manual_balance_at"], running),
        )
        earliest_txn_at = None
        txns = conn.execute(
            """
            SELECT id, occurred_at, signed_cents
            FROM ledger_transactions
            WHERE account_id = ?
              AND is_duplicate = 0
              AND occurred_at <= ?
            ORDER BY occurred_at DESC, id DESC
            """,
            (account["id"], account["manual_balance_at"]),
        ).fetchall()
        for txn in txns:
            earliest_txn_at = txn["occurred_at"]
            conn.execute(
                """
                INSERT OR REPLACE INTO asset_snapshots
                  (account_id, snapshot_at, balance_cents, source, imported_transaction_id)
                VALUES (?, ?, ?, 'manual_backfill', NULL)
                """,
                (account["id"], txn["occurred_at"], running),
            )
            running -= int(txn["signed_cents"] or 0)
        if earliest_txn_at:
            opening_at = (datetime.fromisoformat(earliest_txn_at) - timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """
                INSERT OR REPLACE INTO asset_snapshots
                  (account_id, snapshot_at, balance_cents, source, imported_transaction_id)
                VALUES (?, ?, ?, 'manual_opening_balance', NULL)
                """,
                (account["id"], opening_at, running),
            )

def own_untracked_transfer_event(row: sqlite3.Row) -> tuple[str, int]:
    account_type = row["account_type"] or ""
    text = f"{row['counterparty'] or ''} {row['description'] or ''}"
    signed = int(row["signed_cents"] or 0)
    rules = private_rules()
    liability_inflow_keyword = norm_text(rules.get("liability_inflow_keyword"))
    if account_type == "liability" and liability_inflow_keyword and liability_inflow_keyword in text:
        return "domestic", -signed
    if row["category"] != "内部转账/理财" or row["source"] != "boc":
        return "", 0
    if any(k in text for k in keyword_list(rules.get("ignore_transfer_keywords"))):
        return "", 0
    if any(k in text for k in keyword_list(rules.get("brokerage_transfer_keywords"))) and signed < 0:
        return "brokerage", -signed
    owner_keywords = keyword_list(rules.get("own_domestic_owner_keywords"))
    bank_keywords = keyword_list(rules.get("own_domestic_bank_keywords"))
    if owner_keywords and bank_keywords and any(k in text for k in owner_keywords) and any(k in text for k in bank_keywords):
        return "domestic", -signed
    return "", 0

def rebuild_own_untracked_asset_estimates(conn: sqlite3.Connection, account_ids: dict[str, int]) -> None:
    account_id = account_ids.get(mapping_account("in_transit_account", ""))
    if not account_id:
        return
    conn.execute(
        "DELETE FROM asset_snapshots WHERE account_id = ? AND source = 'own_untracked_estimate'",
        (account_id,),
    )
    events = []
    txns = conn.execute(
        """
        SELECT lt.id, lt.occurred_at, lt.source, lt.category, lt.counterparty, lt.description,
               lt.signed_cents, a.account_type
          FROM ledger_transactions lt
          JOIN accounts a ON a.id = lt.account_id
         WHERE lt.is_duplicate = 0
           AND lt.occurred_at >= '2026-01-01 00:00:00'
           AND (
             a.account_type = 'liability'
             OR (lt.source = 'boc' AND lt.category = '内部转账/理财')
           )
         ORDER BY lt.occurred_at, lt.id
        """
    ).fetchall()
    for txn in txns:
        bucket, delta = own_untracked_transfer_event(txn)
        if delta:
            if bucket == "domestic":
                priority = 0 if delta > 0 else 1
            else:
                priority = 2
            events.append((txn["occurred_at"], priority, bucket, delta))

    longbridge = config_section("brokerages").get("longbridge") or {}
    for item in longbridge.get("deposit_settlements") or []:
        events.append((item["occurred_at"], 3, "brokerage_settle", cents(item["amount"])))

    domestic_running = 0
    brokerage_running = 0
    for occurred_at, _priority, event_type, amount in sorted(events, key=lambda e: (e[0], e[1])):
        if event_type == "brokerage_settle":
            if brokerage_running <= 0:
                continue
            brokerage_running -= min(brokerage_running, amount)
        elif event_type == "brokerage":
            domestic_running -= min(domestic_running, amount)
            brokerage_running += amount
        elif event_type == "domestic":
            if amount < 0:
                domestic_running -= min(domestic_running, -amount)
            else:
                domestic_running += amount
        else:
            continue
        running = domestic_running + brokerage_running
        conn.execute(
            """
            INSERT OR REPLACE INTO asset_snapshots
              (account_id, snapshot_at, balance_cents, source, imported_transaction_id)
            VALUES (?, ?, ?, 'own_untracked_estimate', NULL)
            """,
            (account_id, occurred_at, running),
        )
    latest_brokerage_snapshot = conn.execute(
        """
        SELECT MAX(snapshot_at) AS snapshot_at
          FROM asset_snapshots s
          JOIN accounts a ON a.id = s.account_id
         WHERE a.name = ?
           AND s.source = 'longbridge_csv'
        """,
        (mapping_account("brokerage_account", ""),),
    ).fetchone()["snapshot_at"]
    if latest_brokerage_snapshot and domestic_running + brokerage_running > 0:
        conn.execute(
            """
            INSERT OR REPLACE INTO asset_snapshots
              (account_id, snapshot_at, balance_cents, source, imported_transaction_id)
            VALUES (?, ?, 0, 'own_untracked_estimate', NULL)
            """,
            (account_id, latest_brokerage_snapshot),
        )

def rebuild_borrowing_account_estimates(conn: sqlite3.Connection, account_ids: dict[str, int]) -> None:
    account_id = account_ids.get(mapping_account("borrowing_account", ""))
    if not account_id:
        return
    keyword = norm_text(private_rules().get("borrowing_keyword")) or os.environ.get("WATER_LEDGER_BORROWING_KEYWORD", "").strip()
    if not keyword:
        return
    start_at = norm_text(private_rules().get("borrowing_start_at")) or "2025-10-01 00:00:00"
    conn.execute(
        "DELETE FROM asset_snapshots WHERE account_id = ? AND source = 'borrowing_estimate'",
        (account_id,),
    )
    rows = conn.execute(
        """
        SELECT id, occurred_at, signed_cents, counterparty, description
         FROM ledger_transactions
         WHERE source = 'boc'
           AND is_duplicate = 0
           AND occurred_at >= ?
           AND (counterparty LIKE ? OR description LIKE ?)
         ORDER BY occurred_at, id
        """,
        (start_at, f"%{keyword}%", f"%{keyword}%"),
    ).fetchall()
    if not rows:
        return
    conn.execute(
        """
        UPDATE ledger_transactions
           SET category = '内部转账/理财',
               include_in_cashflow = 0
         WHERE source = 'boc'
           AND occurred_at >= ?
           AND (counterparty LIKE ? OR description LIKE ?)
        """,
        (start_at, f"%{keyword}%", f"%{keyword}%"),
    )
    running = 0
    for row in rows:
        signed = int(row["signed_cents"] or 0)
        if signed > 0:
            running -= signed
        elif signed < 0 and running < 0:
            running += min(-running, -signed)
        else:
            continue
        conn.execute(
            """
            INSERT OR REPLACE INTO asset_snapshots
              (account_id, snapshot_at, balance_cents, source, imported_transaction_id)
            VALUES (?, ?, ?, 'borrowing_estimate', NULL)
            """,
            (account_id, row["occurred_at"], running),
        )

def wallet_balance_affects_account(account_name: str, direction: str, payment_method: str | None) -> bool:
    method = (payment_method or "").strip()
    if account_name == "微信余额":
        return method == "零钱" or (direction == "收入" and method == "/")
    if account_name == "支付宝余额":
        if "余额宝" in method:
            return False
        return (
            method in ("账户余额", "余额")
            or "账户余额" in method
            or (direction == "收入" and method == "")
        )
    return False

def rebuild_wallet_balance_estimates(conn: sqlite3.Connection) -> None:
    accounts = conn.execute(
        """
        SELECT id, name, manual_balance_cents, manual_balance_at
        FROM accounts
        WHERE account_type = 'wallet'
          AND manual_balance_cents IS NOT NULL
          AND manual_balance_at IS NOT NULL
        """
    ).fetchall()
    for account in accounts:
        conn.execute(
            "DELETE FROM asset_snapshots WHERE account_id = ? AND source IN ('manual_backfill', 'wallet_estimate')",
            (account["id"],),
        )
        running = int(account["manual_balance_cents"])
        conn.execute(
            """
            INSERT OR REPLACE INTO asset_snapshots
              (account_id, snapshot_at, balance_cents, source, imported_transaction_id)
            VALUES (?, ?, ?, 'manual_current', NULL)
            """,
            (account["id"], account["manual_balance_at"], running),
        )
        txns = conn.execute(
            """
            SELECT id, occurred_at, direction, payment_method, signed_cents
            FROM ledger_transactions
            WHERE account_id = ?
              AND is_duplicate = 0
              AND occurred_at <= ?
            ORDER BY occurred_at DESC, id DESC
            """,
            (account["id"], account["manual_balance_at"]),
        ).fetchall()
        for txn in txns:
            if not wallet_balance_affects_account(account["name"], txn["direction"], txn["payment_method"]):
                continue
            conn.execute(
                """
                INSERT OR REPLACE INTO asset_snapshots
                  (account_id, snapshot_at, balance_cents, source, imported_transaction_id)
                VALUES (?, ?, ?, 'wallet_estimate', NULL)
                """,
                (account["id"], txn["occurred_at"], running),
            )
            running -= int(txn["signed_cents"] or 0)
            if running < 0:
                running = 0

def alipay_wealth_delta_cents(row: sqlite3.Row) -> int:
    description = row["description"] or ""
    payment_method = row["payment_method"] or ""
    amount = int(row["amount_cents"] or 0)
    if "买入退款" in description:
        return -amount
    if "蚂蚁财富" in description and "买入" in description:
        return amount
    if "蚂蚁财富" in description and "卖出至" in description:
        return -amount
    if description.startswith("余额宝-") and "收益发放" in description:
        return amount
    if "余额宝-单次转入" in description or ("余额宝-" in description and "转入" in description):
        return amount
    if description.startswith("退款-") and "余额宝" in payment_method:
        return amount
    if "余额宝" in payment_method and row["direction"] == "支出":
        return -amount
    return 0

def rebuild_alipay_wealth_estimates(conn: sqlite3.Connection) -> None:
    wealth_account = mapping_account("alipay_wealth_account", "")
    if not wealth_account:
        return
    account = conn.execute("SELECT id FROM accounts WHERE name = ?", (wealth_account,)).fetchone()
    alipay_wallet = mapping_account("alipay_wallet_account", "支付宝余额")
    alipay = conn.execute("SELECT id FROM accounts WHERE name = ?", (alipay_wallet,)).fetchone()
    if not account or not alipay:
        return
    conn.execute(
        "DELETE FROM asset_snapshots WHERE account_id = ? AND source = 'alipay_wealth_estimate'",
        (account["id"],),
    )
    rows = conn.execute(
        """
        SELECT occurred_at, direction, amount_cents, payment_method, counterparty, description
        FROM ledger_transactions
        WHERE account_id = ?
          AND is_duplicate = 0
          AND (
            payment_method LIKE '%余额宝%'
            OR counterparty LIKE '%蚂蚁财富%'
            OR description LIKE '%蚂蚁财富%'
            OR description LIKE '%余额宝%'
            OR counterparty LIKE '%余额宝%'
          )
        ORDER BY occurred_at, id
        """,
        (alipay["id"],),
    ).fetchall()
    running = 0
    for row in rows:
        delta = alipay_wealth_delta_cents(row)
        if delta == 0:
            continue
        running += delta
        if running < 0:
            running = 0
        conn.execute(
            """
            INSERT OR REPLACE INTO asset_snapshots
              (account_id, snapshot_at, balance_cents, source, imported_transaction_id)
            VALUES (?, ?, ?, 'alipay_wealth_estimate', NULL)
            """,
            (account["id"], row["occurred_at"], running),
        )
