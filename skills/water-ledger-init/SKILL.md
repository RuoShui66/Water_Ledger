---
name: water-ledger-init
description: Initialize a Water Ledger local workspace by creating private directories, copying example configuration, preparing manual transaction placeholders, and guiding a nontechnical user through accounts, balances, and bill files. Use when the user wants to understand, start, or set up Water Ledger for the first time.
---

# Water Ledger Init

Use this skill to initialize a local Water Ledger workspace.

Open-source initialization starts with only three accounts: 主银行卡, 微信余额,
支付宝余额. Other accounts should be added later in conversation when the user
mentions them.

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

If the environment supports a native input dialog, use it immediately after the
short first-run explanation. Prefer a dialog over prose questions for:

- Whether to keep the default accounts.
- WeChat and Alipay current balances, or skipping them for now.
- Which bill exports the user has ready.

After the dialog returns, edit `private/config.yaml` yourself. Do not tell the
user to edit YAML for these first-run values.

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
   through a native input dialog when available, instead of telling the user to
   edit the file.
5. If the user adds an account in conversation, edit `private/config.yaml`, run
   `python -m water_ledger import`, and tell them to refresh the dashboard.
6. If the workspace already exists and the user only wants to add balance anchors, run `python -m water_ledger init --configure-balances`.

Never put real account names, bills, PDFs, SQLite databases, or secrets outside `private/`.
