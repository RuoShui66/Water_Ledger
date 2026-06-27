#!/usr/bin/env python3
from __future__ import annotations

import json

from water_ledger.brokerages import run_snapshot


def main() -> None:
    print(json.dumps(run_snapshot(provider="longbridge"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
