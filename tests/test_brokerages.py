from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from water_ledger.brokerages import fetch_ibkr, fetch_robinhood, money_to_cents, run_history


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

    def test_history_command_writes_import_csv_for_date_range(self) -> None:
        script = (
            "import json, sys; "
            "start=sys.argv[1]; end=sys.argv[2]; "
            "rows=[]; "
            "rows.append(dict(date=start, balance='1000.00')); "
            "rows.append(dict(date=end, balance='1234.56')); "
            "print(json.dumps(rows))"
        )
        config = {
            "account": "测试券商账户",
            "currency": "USD",
            "history_command": [sys.executable, "-c", script, "{start}", "{end}"],
        }

        with tempfile.TemporaryDirectory() as tmp:
            import_dir = Path(tmp) / "imports" / "brokerage"
            with (
                mock.patch("water_ledger.brokerages.normalize_provider_config", return_value=config),
                mock.patch("water_ledger.brokerages.BROKERAGE_IMPORT_DIR", import_dir),
            ):
                result = run_history("demo", "2025-01-01", "2026-06-27")

            output = Path(result["import_file"]).read_text(encoding="utf-8")

        self.assertEqual(result["rows"], 2)
        self.assertIn("测试券商账户,2025-01-01,1000.00,USD,demo_history", output)
        self.assertIn("测试券商账户,2026-06-27,1234.56,USD,demo_history", output)


if __name__ == "__main__":
    unittest.main()
