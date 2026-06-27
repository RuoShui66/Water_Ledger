---
name: water-ledger-assets
description: Configure Water Ledger asset snapshots, brokerage account mappings, brokerage snapshots, manual balances, and net-worth curves. Use when the user wants to update assets, liabilities, brokerages, or scheduled snapshots.
---

# Water Ledger Assets

Use this skill to manage asset snapshots and brokerage settings.

## Workflow

1. Check `private/config.yaml` account names.
2. Update `brokerages.<provider>` only in `private/config.yaml`. Supported providers: `longbridge`, `futu`, `tiger`, `ibkr`, `robinhood`.
3. Run `python -m water_ledger brokerage-snapshot --provider enabled` for enabled brokerage snapshots.
4. Run `python -m water_ledger import` to rebuild derived curves.

`python scripts/snapshot_longbridge_assets.py` remains available as a Longbridge compatibility wrapper.

Secrets and brokerage credentials must stay in environment variables or private tool config.
