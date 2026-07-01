from __future__ import annotations

import sqlite3
import unittest

from water_ledger.core.assets import rebuild_wallet_balance_estimates


class WalletBalanceEstimateTest(unittest.TestCase):
    def make_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE accounts (
              id INTEGER PRIMARY KEY,
              name TEXT NOT NULL,
              account_type TEXT NOT NULL,
              manual_balance_cents INTEGER,
              manual_balance_at TEXT
            );
            CREATE TABLE ledger_transactions (
              id INTEGER PRIMARY KEY,
              account_id INTEGER,
              occurred_at TEXT NOT NULL,
              direction TEXT NOT NULL,
              signed_cents INTEGER NOT NULL,
              payment_method TEXT,
              is_duplicate INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE asset_snapshots (
              id INTEGER PRIMARY KEY,
              account_id INTEGER NOT NULL,
              snapshot_at TEXT NOT NULL,
              balance_cents INTEGER NOT NULL,
              source TEXT NOT NULL,
              imported_transaction_id INTEGER,
              UNIQUE (account_id, snapshot_at, source)
            );
            """
        )
        return conn

    def test_wallet_estimates_move_forward_and_ignore_non_wallet_methods(self) -> None:
        conn = self.make_conn()
        conn.execute(
            """
            INSERT INTO accounts
              (id, name, account_type, manual_balance_cents, manual_balance_at)
            VALUES (1, '微信余额', 'wallet', 10000, '2026-06-02 12:00:00')
            """
        )
        conn.executemany(
            """
            INSERT INTO ledger_transactions
              (account_id, occurred_at, direction, signed_cents, payment_method)
            VALUES (1, ?, ?, ?, ?)
            """,
            [
                ("2026-06-01 12:00:00", "支出", -1000, "零钱"),
                ("2026-06-03 12:00:00", "支出", -2000, "零钱"),
                ("2026-06-04 12:00:00", "支出", -3000, "中国银行储蓄卡(0000)"),
                ("2026-06-05 12:00:00", "收入", 500, "/"),
            ],
        )

        rebuild_wallet_balance_estimates(conn)

        rows = conn.execute(
            """
            SELECT snapshot_at, balance_cents, source
            FROM asset_snapshots
            WHERE account_id = 1
            ORDER BY snapshot_at
            """
        ).fetchall()
        self.assertEqual(
            [(row["snapshot_at"], row["balance_cents"], row["source"]) for row in rows],
            [
                ("2026-06-01 12:00:00", 10000, "wallet_estimate"),
                ("2026-06-02 12:00:00", 10000, "manual_current"),
                ("2026-06-03 12:00:00", 8000, "wallet_estimate"),
                ("2026-06-05 12:00:00", 8500, "wallet_estimate"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
