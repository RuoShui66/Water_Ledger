from __future__ import annotations

import json
import sys
import unittest
from unittest import mock

from water_ledger.brokerages import fetch_ibkr, fetch_robinhood, money_to_cents


class BrokerageSnapshotTest(unittest.TestCase):
    def test_money_to_cents_handles_commas_and_currency_symbols(self) -> None:
        self.assertEqual(money_to_cents("¥12,345.67"), 1234567)

    def test_robinhood_command_bridge_extracts_balance(self) -> None:
        command = [
            sys.executable,
            "-c",
            "import json; print(json.dumps({'net_liquidation': '123.45', 'currency': 'USD'}))",
        ]

        snapshot = fetch_robinhood(
            {"account": "美股账户", "command": command, "balance_paths": ["net_liquidation"]},
            "2026-06-27 12:00:00",
        )

        self.assertEqual(snapshot.provider, "robinhood")
        self.assertEqual(snapshot.balance_cents, 12345)
        self.assertEqual(snapshot.currency, "USD")

    def test_ibkr_extracts_net_liquidation_from_summary(self) -> None:
        def fake_get_json(_base_url: str, path: str):
            if path == "/portfolio/accounts":
                return [{"id": "U1234567"}]
            self.assertEqual(path, "/portfolio/U1234567/summary")
            return {"netliquidation": {"amount": 9876.54, "currency": "USD"}}

        with mock.patch("water_ledger.brokerages.ibkr_get_json", side_effect=fake_get_json):
            snapshot = fetch_ibkr({"account": "美股账户"}, "2026-06-27 12:00:00")

        self.assertEqual(snapshot.provider, "ibkr")
        self.assertEqual(snapshot.balance_cents, 987654)
        self.assertEqual(snapshot.currency, "USD")


if __name__ == "__main__":
    unittest.main()
