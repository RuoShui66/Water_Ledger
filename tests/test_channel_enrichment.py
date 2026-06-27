from __future__ import annotations

import sqlite3
import unittest

from water_ledger.core.dedupe import dedupe
from water_ledger.storage.schema import load_schema


class ChannelEnrichmentTest(unittest.TestCase):
    def test_wechat_bank_card_payment_keeps_wechat_details_as_primary_bill(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(load_schema())
        try:
            conn.execute(
                """
                INSERT INTO accounts
                  (id, name, institution, account_type, currency, include_in_net_worth)
                VALUES (1, '主银行卡', '银行', 'bank_card', 'CNY', 1)
                """
            )
            conn.execute(
                """
                INSERT INTO source_files (id, filename, source, sha1, row_count)
                VALUES
                  (1, 'private/imports/bank/example.pdf', 'boc', 'bank-sha1', 1),
                  (2, 'private/imports/wechat/example.xlsx', 'wechat', 'wechat-sha1', 1)
                """
            )
            conn.execute(
                """
                INSERT INTO imported_transactions
                  (id, source, source_file_id, source_txn_id, occurred_at, direction,
                   amount_cents, signed_cents, currency, account_hint, raw_category,
                   category, counterparty, description, payment_method, status,
                   fingerprint, raw_json)
                VALUES
                  (1, 'boc', 1, 'bank-1', '2026-06-21 20:53:00', '支出',
                   66700, -66700, 'CNY', '主银行卡', '网上快捷支付',
                   '其他支出', '财付通', '网上快捷支付 财付通-微信转账',
                   '主银行卡', '已记账', 'fp-bank', '{}'),
                  (2, 'wechat', 2, 'wechat-1', '2026-06-21 20:52:42', '支出',
                   66700, -66700, 'CNY', '微信', '微信转账',
                   '公益人情', '张三', '微信转账 · 备注: 6月房租',
                   '中国银行储蓄卡(0000)', '支付成功', 'fp-wechat', '{}')
                """
            )
            conn.execute(
                """
                INSERT INTO ledger_transactions
                  (id, imported_transaction_id, account_id, occurred_at, direction,
                   amount_cents, signed_cents, currency, category, counterparty,
                   description, source, payment_method, status, include_in_cashflow)
                VALUES
                  (1, 1, 1, '2026-06-21 20:53:00', '支出',
                   66700, -66700, 'CNY', '其他支出', '财付通',
                   '网上快捷支付 财付通-微信转账', 'boc', '主银行卡', '已记账', 1),
                  (2, 2, 1, '2026-06-21 20:52:42', '支出',
                   66700, -66700, 'CNY', '公益人情', '张三',
                   '微信转账 · 备注: 6月房租', 'wechat', '中国银行储蓄卡(0000)', '支付成功', 1)
                """
            )

            dedupe(conn)

            visible = conn.execute(
                """
                SELECT source, counterparty, description, is_duplicate, include_in_cashflow
                FROM ledger_transactions
                WHERE is_duplicate = 0
                """
            ).fetchall()
            duplicate = conn.execute(
                """
                SELECT source, duplicate_of_ledger_id, duplicate_reason, include_in_cashflow
                FROM ledger_transactions
                WHERE is_duplicate = 1
                """
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0]["source"], "wechat")
        self.assertEqual(visible[0]["counterparty"], "张三")
        self.assertIn("6月房租", visible[0]["description"])
        self.assertEqual(visible[0]["include_in_cashflow"], 1)
        self.assertEqual(duplicate["source"], "boc")
        self.assertEqual(duplicate["duplicate_of_ledger_id"], 2)
        self.assertEqual(duplicate["include_in_cashflow"], 0)
        self.assertIn("渠道账单商户和备注", duplicate["duplicate_reason"])


if __name__ == "__main__":
    unittest.main()
