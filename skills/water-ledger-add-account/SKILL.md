---
name: water-ledger-add-account
description: Add or update bank card, wallet, brokerage, liability, and manual accounts in Water Ledger configuration. Use when the user wants to add an account, change account mapping, or set a manual balance.
---

# Water Ledger Add Account

Use this skill to edit `private/config.yaml`.

## Workflow

1. Add the account under `accounts`.
2. Update `account_mapping` if the account should receive imported transactions.
3. Use `manual_balance_cents` and `manual_balance_at` only for user-provided balances.
4. Run `python -m water_ledger import` to rebuild.

Keep real account names and card masks in `private/config.yaml`, not `config/config.example.yaml`.
