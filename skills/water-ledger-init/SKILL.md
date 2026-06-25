---
name: water-ledger-init
description: Initialize a Water Ledger local workspace by creating private directories, copying example configuration, preparing manual transaction placeholders, and explaining next import steps. Use when the user wants to set up Water Ledger for the first time or reset generated local scaffolding.
---

# Water Ledger Init

Use this skill to initialize a local Water Ledger workspace.

## Workflow

1. Run `python -m water_ledger init`.
   - In an interactive terminal, answer the ledger display-name prompt.
   - Optionally enter current balances for accounts that do not have statement/API balances, such as wallets, cash accounts, and liabilities.
2. Confirm `private/config.yaml` exists.
3. Confirm these directories exist:
   - `private/imports/alipay`
   - `private/imports/wechat`
   - `private/imports/bank`
   - `private/data`
   - `private/outputs`
4. Tell the user to edit `private/config.yaml` before importing real bills.
5. If the workspace already exists and the user only wants to add balance anchors, run `python -m water_ledger init --configure-balances`.

Never put real account names, bills, PDFs, SQLite databases, or secrets outside `private/`.
