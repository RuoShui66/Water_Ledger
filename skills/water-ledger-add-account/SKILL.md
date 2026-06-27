---
name: water-ledger-add-account
description: Add or update bank card, wallet, brokerage, liability, and manual accounts in Water Ledger configuration. Use when the user wants to add an account, change account mapping, or set a manual balance.
---

# Water Ledger Add Account

Use this skill to edit `private/config.yaml`.

## Workflow

1. Use a native input dialog when available. Ask only for missing essentials:
   display name, account type, institution, currency, whether it counts in net
   worth, and optional current balance/time.
2. Add the account under `accounts` in `private/config.yaml`.
3. Update `account_mapping` only if the account should receive imported
   transactions or optional estimates.
4. Use `manual_balance_cents` and `manual_balance_at` only for user-provided balances.
5. Run `python -m water_ledger import` to rebuild.
6. Tell the user to refresh the dashboard; accounts are read from the database,
   so the frontend will show the new account after import.

Open-source defaults should remain minimal: 主银行卡, 微信余额, 支付宝余额.
Do not add brokerage, liability, in-transit, or wealth-management accounts to
public example config unless they are examples in documentation.

Keep real account names and card masks in `private/config.yaml`, not `config/config.example.yaml`.
