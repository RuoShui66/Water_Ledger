from __future__ import annotations

import re
import sqlite3
from datetime import datetime

from water_ledger.core.utils import norm_text


def refund_match_key(value: str | None) -> str:
    text = norm_text(value)
    if text in {"", "/", "-", "无", "nan"}:
        return ""
    text = re.sub(r"(转账备注|备注|商品|订单|商户单号|交易单号)[:：]", "", text)
    text = re.sub(r"[\s·・（）()【】\\/\-_:：,，.。]+", "", text)
    return text

def has_refund_signal(row: sqlite3.Row) -> bool:
    text = f"{row['category'] or ''} {row['counterparty'] or ''} {row['description'] or ''} {row['status'] or ''}"
    return any(key in text for key in ["退款", "退回", "返现", "返还", "押金", "冲正", "撤销"])

def refund_rows_match(expense: sqlite3.Row, income: sqlite3.Row) -> bool:
    if expense["source"] != income["source"]:
        return False
    if expense["account_id"] != income["account_id"]:
        return False
    if expense["amount_cents"] != income["amount_cents"]:
        return False
    delta = abs((datetime.fromisoformat(income["occurred_at"]) - datetime.fromisoformat(expense["occurred_at"])).total_seconds())
    if delta > 30 * 24 * 3600:
        return False

    expense_merchant = refund_match_key(expense["counterparty"])
    income_merchant = refund_match_key(income["counterparty"])
    if expense_merchant and income_merchant and expense_merchant == income_merchant:
        return True

    expense_desc = refund_match_key(expense["description"])
    income_desc = refund_match_key(income["description"])
    if expense_desc and income_desc and expense_desc == income_desc and len(expense_desc) >= 2:
        return True

    return has_refund_signal(income) and (
        bool(expense_merchant and expense_merchant in refund_match_key(f"{income['counterparty']} {income['description']}"))
        or bool(expense_desc and expense_desc in refund_match_key(f"{income['counterparty']} {income['description']}"))
    )

def mark_refund_offsets(conn: sqlite3.Connection) -> int:
    candidates = conn.execute(
        """SELECT id, account_id, source, occurred_at, direction, amount_cents,
                  category, counterparty, description, status
             FROM ledger_transactions
            WHERE is_duplicate = 0
              AND include_in_cashflow = 1
              AND direction IN ('支出', '收入')
            ORDER BY occurred_at, id"""
    ).fetchall()
    expenses = [row for row in candidates if row["direction"] == "支出"]
    incomes = [row for row in candidates if row["direction"] == "收入"]
    used_income_ids: set[int] = set()
    pairs: list[tuple[int, int, str]] = []

    for expense in expenses:
        matches = []
        expense_time = datetime.fromisoformat(expense["occurred_at"])
        for income in incomes:
            if income["id"] in used_income_ids:
                continue
            if not refund_rows_match(expense, income):
                continue
            income_time = datetime.fromisoformat(income["occurred_at"])
            seconds = abs((income_time - expense_time).total_seconds())
            is_after = 0 if income_time >= expense_time else 1
            refund_signal = 0 if has_refund_signal(income) else 1
            matches.append((refund_signal, is_after, seconds, income))
        if not matches:
            continue
        matches.sort(key=lambda item: (item[0], item[1], item[2]))
        income = matches[0][3]
        used_income_ids.add(income["id"])
        reason = f"退款抵消：同账户同金额进出，支出#{expense['id']} 与收入#{income['id']}互抵"
        pairs.append((expense["id"], income["id"], reason))

    for expense_id, income_id, reason in pairs:
        conn.execute(
            """UPDATE ledger_transactions
                  SET include_in_cashflow = 0,
                      duplicate_reason = ?
                WHERE id IN (?, ?)""",
            (reason, expense_id, income_id),
        )
    return len(pairs)

