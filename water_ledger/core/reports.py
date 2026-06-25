from __future__ import annotations

import sqlite3

import pandas as pd

from water_ledger.paths import PRIVATE_ROOT


def sync_categories(conn: sqlite3.Connection) -> None:
    for row in conn.execute("SELECT DISTINCT category, direction, include_in_cashflow FROM ledger_transactions WHERE category IS NOT NULL"):
        cashflow_type = "neutral"
        if row["category"] == "内部转账/理财" or row["include_in_cashflow"] == 0:
            cashflow_type = "transfer" if row["category"] == "内部转账/理财" else "neutral"
        elif row["direction"] == "收入":
            cashflow_type = "income"
        elif row["direction"] == "支出":
            cashflow_type = "expense"
        conn.execute(
            "INSERT OR IGNORE INTO categories (name,parent_name,cashflow_type) VALUES (?,?,?)",
            (row["category"], None, cashflow_type),
        )

def write_summary(conn: sqlite3.Connection) -> None:
    out = PRIVATE_ROOT / "outputs"
    out.mkdir(exist_ok=True)
    queries = {
        "ledger_import_summary.csv": """
            SELECT source, COUNT(*) AS raw_rows,
                   SUM(CASE WHEN is_duplicate=1 THEN 1 ELSE 0 END) AS duplicate_rows,
                   SUM(CASE WHEN is_duplicate=0 THEN 1 ELSE 0 END) AS canonical_rows,
                   SUM(CASE WHEN is_duplicate=0 AND direction='收入' AND include_in_cashflow=1 THEN amount_cents ELSE 0 END)/100.0 AS income,
                   SUM(CASE WHEN is_duplicate=0 AND direction='支出' AND include_in_cashflow=1 THEN amount_cents ELSE 0 END)/100.0 AS expense
              FROM ledger_transactions GROUP BY source ORDER BY source
        """,
        "monthly_cashflow.csv": "SELECT * FROM v_monthly_cashflow ORDER BY month",
        "expense_by_category.csv": """
            SELECT category, COUNT(*) AS txns, SUM(amount_cents)/100.0 AS amount
              FROM ledger_transactions
             WHERE is_duplicate=0 AND include_in_cashflow=1 AND direction='支出'
             GROUP BY category ORDER BY amount DESC
        """,
    }
    for filename, query in queries.items():
        df = pd.read_sql_query(query, conn)
        df.to_csv(out / filename, index=False, encoding="utf-8-sig")
