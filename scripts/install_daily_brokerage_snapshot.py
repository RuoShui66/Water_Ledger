#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from water_ledger.scheduler import (
    DEFAULT_SNAPSHOT_TIME,
    daily_brokerage_schedule_status,
    install_daily_brokerage_schedule,
    print_json,
    uninstall_daily_brokerage_schedule,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage the daily brokerage net-worth snapshot job")
    sub = parser.add_subparsers(dest="command", required=True)

    install = sub.add_parser("install")
    install.add_argument("--time", default=DEFAULT_SNAPSHOT_TIME, help="daily local time in HH:MM")
    install.add_argument("--provider", default="enabled")
    install.add_argument("--write-only", action="store_true")

    sub.add_parser("status")
    sub.add_parser("uninstall")

    args = parser.parse_args()
    if args.command == "install":
        print_json(install_daily_brokerage_schedule(time_value=args.time, provider=args.provider, load=not args.write_only))
        return 0
    if args.command == "status":
        result = daily_brokerage_schedule_status()
        print_json(result)
        return 0 if result["status"] == "installed" else 1
    if args.command == "uninstall":
        print_json(uninstall_daily_brokerage_schedule())
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
