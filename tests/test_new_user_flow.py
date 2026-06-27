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


if __name__ == "__main__":
    unittest.main()
