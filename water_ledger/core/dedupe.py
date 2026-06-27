from __future__ import annotations

import sqlite3
from datetime import datetime

from water_ledger.config import account_mapping, keyword_list


def mark_duplicate(conn: sqlite3.Connection, dup_id: int, primary_id: int, confidence: float, reason: str) -> None:
    conn.execute(
        "UPDATE ledger_transactions SET is_duplicate=1, duplicate_of_ledger_id=?, duplicate_reason=?, include_in_cashflow=0 WHERE id=?",
        (primary_id, reason, dup_id),
    )
    conn.execute(
        "INSERT OR IGNORE INTO duplicate_links (duplicate_ledger_id, primary_ledger_id, confidence, reason) VALUES (?,?,?,?)",
        (dup_id, primary_id, confidence, reason),
    )

def dedupe(conn: sqlite3.Connection) -> None:
    bank_payment_keywords = keyword_list(account_mapping().get("bank_payment_keywords"))
    platform_rows = conn.execute(
        """SELECT id, source, occurred_at, signed_cents, amount_cents, counterparty, description, payment_method
           FROM ledger_transactions
           WHERE source IN ('wechat','alipay') AND direction IN ('支出','收入')
           ORDER BY occurred_at"""
    ).fetchall()
    bank_rows = conn.execute(
        """SELECT id, source, occurred_at, signed_cents, amount_cents, counterparty, description
           FROM ledger_transactions
           WHERE source='boc' AND direction IN ('支出','收入')
           ORDER BY occurred_at"""
    ).fetchall()
    used_bank: set[int] = set()
    bank_by_amount: dict[int, list[sqlite3.Row]] = {}
    for bank in bank_rows:
        bank_by_amount.setdefault(bank["signed_cents"], []).append(bank)

    for row in platform_rows:
        if row["source"] == "alipay" and not any(k in (row["payment_method"] or "") for k in bank_payment_keywords):
            continue
        if row["source"] == "wechat" and not any(k in (row["payment_method"] or "") for k in ["银行", "储蓄卡", "信用卡"]):
            continue
        platform_keyword = "支付宝" if row["source"] == "alipay" else "财付通"
        occurred = datetime.fromisoformat(row["occurred_at"])
        candidates = []
        for bank in bank_by_amount.get(row["signed_cents"], []):
            if bank["id"] in used_bank:
                continue
            bank_text = f"{bank['counterparty']} {bank['description']}"
            if platform_keyword not in bank_text:
                continue
            delta = abs((datetime.fromisoformat(bank["occurred_at"]) - occurred).total_seconds())
            if delta <= 3 * 24 * 3600:
                candidates.append((delta, bank))
        if candidates:
            candidates.sort(key=lambda item: item[0])
            bank = candidates[0][1]
            used_bank.add(bank["id"])
            mark_duplicate(
                conn,
                bank["id"],
                row["id"],
                0.98 if candidates[0][0] <= 600 else 0.86,
                f"银行快捷支付与{row['source']}订单同金额且时间接近；展示采用渠道账单商户和备注，银行流水保留用于余额",
            )
