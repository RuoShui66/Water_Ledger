from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from water_ledger.config import account_mapping, config_list, keyword_list, mapping_account
from water_ledger.core.models import RawTxn
from water_ledger.core.utils import norm_text, sha1
from water_ledger.importers.bill_importers import read_alipay, read_boc_pdf, read_manual, read_wechat
from water_ledger.paths import PRIVATE_ROOT, ROOT
from water_ledger.storage.schema import load_schema


def init_db(conn: sqlite3.Connection) -> dict[str, int]:
    conn.executescript(load_schema())
    accounts = []
    for account in config_list("accounts"):
        accounts.append(
            (
                norm_text(account.get("name")),
                norm_text(account.get("institution")),
                norm_text(account.get("account_type")),
                norm_text(account.get("currency")) or "CNY",
                norm_text(account.get("account_no_mask")) or None,
                1 if account.get("include_in_net_worth", True) else 0,
                account.get("manual_balance_cents"),
                norm_text(account.get("manual_balance_at")) or None,
                norm_text(account.get("note")) or None,
            )
        )
    conn.executemany(
        """INSERT INTO accounts
           (name,institution,account_type,currency,account_no_mask,include_in_net_worth,manual_balance_cents,manual_balance_at,note)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        accounts,
    )
    cats = [
        (
            norm_text(category.get("name")),
            norm_text(category.get("parent_name")) or None,
            norm_text(category.get("cashflow_type")) or "expense",
        )
        for category in config_list("categories")
    ]
    conn.executemany("INSERT INTO categories (name,parent_name,cashflow_type) VALUES (?,?,?)", cats)
    return {name: id_ for id_, name in conn.execute("SELECT id,name FROM accounts")}

def file_sha1(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def source_for_file(path: Path) -> str:
    if "支付宝" in path.name:
        return "alipay"
    if "微信" in path.name:
        return "wechat"
    if path.suffix.lower() == ".pdf":
        return "boc"
    if path.name == "manual_transactions.json":
        return "manual"
    return "manual"

def load_all() -> list[RawTxn]:
    rows: list[RawTxn] = []
    for path in sorted((PRIVATE_ROOT / "imports" / "alipay").glob("支付宝交易明细*.csv")):
        rows.extend(read_alipay(path))
    for path in sorted((PRIVATE_ROOT / "imports" / "wechat").glob("微信支付账单流水文件*.xlsx")):
        rows.extend(read_wechat(path))
    for path in sorted((PRIVATE_ROOT / "imports" / "bank").glob("*.pdf")):
        rows.extend(read_boc_pdf(path))
    manual = PRIVATE_ROOT / "data" / "manual_transactions.json"
    if manual.exists():
        rows.extend(read_manual(manual))
    return rows

def insert_rows(conn: sqlite3.Connection, rows: list[RawTxn], account_ids: dict[str, int]) -> None:
    by_file: dict[str, list[RawTxn]] = {}
    for row in rows:
        by_file.setdefault(row.source_file, []).append(row)
    file_ids: dict[str, int] = {}
    for filename, file_rows in by_file.items():
        path = Path(filename)
        if not path.is_absolute():
            path = ROOT / filename
        conn.execute(
            "INSERT INTO source_files (filename,source,sha1,row_count,note) VALUES (?,?,?,?,?)",
            (filename, source_for_file(path), file_sha1(path), len(file_rows), None),
        )
        file_ids[filename] = conn.execute("SELECT id FROM source_files WHERE filename=?", (filename,)).fetchone()[0]

    for row in rows:
        fingerprint = sha1(row.source, row.occurred_at, row.signed_cents, row.counterparty, row.description)
        conn.execute(
            """INSERT OR IGNORE INTO imported_transactions
               (source,source_file_id,source_txn_id,occurred_at,direction,amount_cents,signed_cents,currency,account_hint,
                raw_category,category,counterparty,description,payment_method,status,balance_after_cents,fingerprint,raw_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                row.source, file_ids[row.source_file], row.source_txn_id, row.occurred_at, row.direction, row.amount_cents,
                row.signed_cents, row.currency, row.account_hint, row.raw_category, row.category, row.counterparty,
                row.description, row.payment_method, row.status, row.balance_after_cents, fingerprint,
                json.dumps(row.raw_json, ensure_ascii=False),
            ),
        )

    source_accounts = account_mapping().get("source_accounts") or {}
    account_for_source = {
        source: account_ids[name]
        for source, name in source_accounts.items()
        if name in account_ids
    }
    bank_account = mapping_account("bank_account", "主银行卡")
    bank_payment_keywords = keyword_list(account_mapping().get("bank_payment_keywords"))
    for r in conn.execute("SELECT * FROM imported_transactions ORDER BY occurred_at"):
        source = r["source"]
        account_id = account_for_source.get(source)
        payment_method = r["payment_method"] or ""
        if source == "manual" and r["account_hint"] in account_ids:
            account_id = account_ids[r["account_hint"]]
        if source in {"alipay", "wechat"} and bank_account in account_ids and any(k in payment_method for k in bank_payment_keywords):
            account_id = account_ids[bank_account]
        include = 0 if r["direction"] in {"不计收支", "中性交易"} or r["category"] == "内部转账/理财" else 1
        conn.execute(
            """INSERT INTO ledger_transactions
               (imported_transaction_id,account_id,occurred_at,direction,amount_cents,signed_cents,currency,category,
                counterparty,description,source,payment_method,status,include_in_cashflow)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                r["id"], account_id, r["occurred_at"], r["direction"], r["amount_cents"],
                r["signed_cents"], r["currency"], r["category"] or "其他支出", r["counterparty"], r["description"],
                source, r["payment_method"], r["status"], include,
            ),
        )
        if source == "boc" and r["balance_after_cents"] is not None:
            conn.execute(
                "INSERT OR IGNORE INTO asset_snapshots (account_id,snapshot_at,balance_cents,source,imported_transaction_id) VALUES (?,?,?,?,?)",
                (account_ids[bank_account], r["occurred_at"], r["balance_after_cents"], "boc_pdf", r["id"]),
            )
