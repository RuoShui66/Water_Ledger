from __future__ import annotations

import json
import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HAS_IMPORT_DEPS = all(importlib.util.find_spec(name) for name in ("pandas", "openpyxl", "pypdf", "yaml"))


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class NewUserFlowTest(unittest.TestCase):
    def run_ledger(self, private_dir: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["WATER_LEDGER_PRIVATE_DIR"] = str(private_dir)
        return subprocess.run(
            [sys.executable, "-m", "water_ledger", *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=check,
        )

    @unittest.skipUnless(HAS_IMPORT_DEPS, "runtime import dependencies are not installed")
    def test_imports_example_bills(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            private_dir = Path(tmp) / "private"
            self.run_ledger(private_dir, "init", "--no-balance-prompts")
            shutil.copyfile(
                ROOT / "examples" / "支付宝交易明细_sample.csv",
                private_dir / "imports" / "alipay" / "支付宝交易明细_sample.csv",
            )
            shutil.copyfile(
                ROOT / "examples" / "微信支付账单流水文件_sample.xlsx",
                private_dir / "imports" / "wechat" / "微信支付账单流水文件_sample.xlsx",
            )

            result = self.run_ledger(private_dir, "import")
            stats = json.loads(result.stdout)

        self.assertEqual(stats["ledger_rows"], 6)
        self.assertEqual(stats["duplicate_rows"], 0)
        self.assertEqual(stats["refund_offset_pairs"], 1)
        self.assertEqual(
            {warning["account"] for warning in stats["warnings"]},
            {"微信余额", "支付宝余额"},
        )

    def test_status_reports_custom_port(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            private_dir = Path(tmp) / "private"
            port = free_port()
            self.run_ledger(private_dir, "init", "--no-balance-prompts")
            try:
                started = self.run_ledger(private_dir, "start", "--port", str(port))
                self.assertEqual(json.loads(started.stdout)["url"], f"http://127.0.0.1:{port}")

                status = self.run_ledger(private_dir, "status")
                self.assertEqual(json.loads(status.stdout)["url"], f"http://127.0.0.1:{port}")
            finally:
                self.run_ledger(private_dir, "stop", check=False)

    @unittest.skipUnless(importlib.util.find_spec("yaml"), "PyYAML is not installed")
    def test_init_starts_with_minimal_default_accounts(self) -> None:
        import yaml

        with tempfile.TemporaryDirectory() as tmp:
            private_dir = Path(tmp) / "private"
            self.run_ledger(private_dir, "init", "--no-balance-prompts")

            config = yaml.safe_load((private_dir / "config.yaml").read_text(encoding="utf-8"))

        self.assertEqual(
            [account["name"] for account in config["accounts"]],
            ["主银行卡", "微信余额", "支付宝余额"],
        )

    @unittest.skipUnless(HAS_IMPORT_DEPS, "runtime import dependencies are not installed")
    def test_imports_brokerage_history_for_any_date_range(self) -> None:
        import sqlite3
        import yaml

        with tempfile.TemporaryDirectory() as tmp:
            private_dir = Path(tmp) / "private"
            self.run_ledger(private_dir, "init", "--no-balance-prompts")
            config_path = private_dir / "config.yaml"
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            config["accounts"].append(
                {
                    "name": "测试券商账户",
                    "institution": "示例券商",
                    "account_type": "brokerage",
                    "currency": "USD",
                    "include_in_net_worth": True,
                    "manual_balance_cents": None,
                    "manual_balance_at": None,
                    "note": "测试历史净资产",
                }
            )
            config_path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
            history_dir = private_dir / "imports" / "brokerage"
            history_dir.mkdir(parents=True, exist_ok=True)
            history_dir.joinpath("brokerage_history.csv").write_text(
                "\n".join(
                    [
                        "account,date,balance,currency,source",
                        "测试券商账户,2025-01-01,1000.00,USD,manual_history",
                        "测试券商账户,2025-09-15,1200.50,USD,manual_history",
                        "测试券商账户,2026-06-27,1500.25,USD,manual_history",
                    ]
                ),
                encoding="utf-8",
            )

            self.run_ledger(private_dir, "import")
            with sqlite3.connect(private_dir / "data" / "water_ledger.sqlite") as conn:
                rows = conn.execute(
                    """
                    SELECT s.snapshot_at, s.balance_cents, s.source
                    FROM asset_snapshots s
                    JOIN accounts a ON a.id = s.account_id
                    WHERE a.name = '测试券商账户'
                    ORDER BY s.snapshot_at
                    """
                ).fetchall()

        self.assertEqual(
            rows,
            [
                ("2025-01-01 23:59:59", 100000, "manual_history"),
                ("2025-09-15 23:59:59", 120050, "manual_history"),
                ("2026-06-27 23:59:59", 150025, "manual_history"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
