---
name: water-ledger-init
description: Initialize a Water Ledger local workspace by creating private directories, copying example configuration, preparing manual transaction placeholders, and guiding a nontechnical user through accounts, balances, and bill files. Use when the user wants to understand, start, or set up Water Ledger for the first time.
---

# Water Ledger Init

Use this skill to initialize a local Water Ledger workspace.

## First-Run Answer Style

If the user asks what this project is or how to use it, do not start with a
command list. Say, in plain Chinese, that Water Ledger is a local personal
bookkeeping assistant. Tell the user they only need to provide:

- Accounts they own.
- Current balances for wallets, cash, liabilities, or accounts without statement
  balances.
- Bill files such as Alipay CSV, WeChat Excel, bank PDF, brokerage snapshots, or
  manual transactions.

Then offer to initialize/check the workspace and ask for at most those three
inputs. Keep technical details and command blocks out of the first answer unless
the user explicitly wants to operate manually.

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
4. Edit `private/config.yaml` for the user when they provide account details. If
   account details are missing, ask for the missing account names/types/balances
   instead of telling the user to edit the file.
5. If the workspace already exists and the user only wants to add balance anchors, run `python -m water_ledger init --configure-balances`.

Never put real account names, bills, PDFs, SQLite databases, or secrets outside `private/`.
