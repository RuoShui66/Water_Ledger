#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from water_ledger.brokerages import run_history


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch brokerage historical net-worth snapshots")
    parser.add_argument("--provider", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run_history(args.provider, args.start, args.end, rebuild=args.rebuild), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
