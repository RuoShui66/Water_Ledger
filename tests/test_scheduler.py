from __future__ import annotations

import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from water_ledger.scheduler import (
    daily_brokerage_schedule_status,
    install_daily_brokerage_schedule,
    normalized_time,
)


class DailyBrokerageScheduleTest(unittest.TestCase):
    def test_normalized_time_accepts_short_hour(self) -> None:
        self.assertEqual(normalized_time("4:01"), "04:01")

    def test_install_write_only_creates_launch_agent_plist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            private_root = root / "private"
            launch_dir = root / "LaunchAgents"
            label = "com.water-ledger.test"

            with (
                mock.patch("water_ledger.scheduler.PRIVATE_ROOT", private_root),
                mock.patch("water_ledger.scheduler.DB_PATH", private_root / "data" / "water_ledger.sqlite"),
                mock.patch("water_ledger.scheduler.CONFIG_PATH", private_root / "config.yaml"),
                mock.patch("water_ledger.scheduler.launch_agent_loaded", return_value=False),
            ):
                result = install_daily_brokerage_schedule(
                    time_value="08:30",
                    provider="longbridge",
                    load=False,
                    label=label,
                    launch_dir=launch_dir,
                )
                status = daily_brokerage_schedule_status(label=label, launch_dir=launch_dir)

            plist_path = Path(result["plist"])
            with plist_path.open("rb") as f:
                plist = plistlib.load(f)

        self.assertEqual(result["status"], "installed")
        self.assertFalse(result["loaded"])
        self.assertEqual(plist["Label"], label)
        self.assertEqual(plist["StartCalendarInterval"], {"Hour": 8, "Minute": 30})
        self.assertEqual(plist["ProgramArguments"][-2:], ["--provider", "longbridge"])
        self.assertEqual(status["status"], "installed")
        self.assertEqual(status["time"], "08:30")
        self.assertEqual(status["provider"], "longbridge")

    def test_windows_install_uses_task_scheduler_and_private_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            private_root = root / "private"
            task_name = "Water Ledger Test Snapshot"
            calls: list[list[str]] = []

            def fake_schtasks(args: list[str], check: bool = True):
                calls.append(args)
                return mock.Mock(returncode=0, stdout="", stderr="")

            with (
                mock.patch("water_ledger.scheduler.sys.platform", "win32"),
                mock.patch("water_ledger.scheduler.PRIVATE_ROOT", private_root),
                mock.patch("water_ledger.scheduler.DB_PATH", private_root / "data" / "water_ledger.sqlite"),
                mock.patch("water_ledger.scheduler.CONFIG_PATH", private_root / "config.yaml"),
                mock.patch("water_ledger.scheduler.run_schtasks", side_effect=fake_schtasks),
            ):
                result = install_daily_brokerage_schedule(
                    time_value="21:15",
                    provider="enabled",
                    task_name=task_name,
                )
                status = daily_brokerage_schedule_status(task_name=task_name)

            script = Path(result["windows_script"]).read_text(encoding="utf-8")

        self.assertEqual(result["scheduler"], "windows-task-scheduler")
        self.assertTrue(result["loaded"])
        self.assertIn(["/Create", "/F", "/SC", "DAILY", "/ST", "21:15", "/TN", task_name, "/TR", f'cmd.exe /c "{result["windows_script"]}"'], calls)
        self.assertIn("WATER_LEDGER_PRIVATE_DIR", script)
        self.assertIn("brokerage-snapshot", script)
        self.assertEqual(status["status"], "installed")
        self.assertEqual(status["time"], "21:15")
        self.assertEqual(status["provider"], "enabled")


if __name__ == "__main__":
    unittest.main()
