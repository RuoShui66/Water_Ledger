---
name: water-ledger-assets
description: Configure Water Ledger asset snapshots, brokerage account mappings, Longbridge snapshots, manual balances, and net-worth curves. Use when the user wants to update assets, liabilities, brokerages, or scheduled snapshots.
---

# Water Ledger Assets

Use this skill to manage asset snapshots and brokerage settings.

## Workflow

1. Check `private/config.yaml` account names.
2. Update `brokerages.longbridge` only if Longbridge is used.
3. Run `python scripts/snapshot_longbridge_assets.py` for live Longbridge snapshots.
4. Run `python -m water_ledger import` to rebuild derived curves.

Secrets and brokerage credentials must stay in environment variables or private tool config.
