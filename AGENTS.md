# Water Ledger Agent Guide

This repository is a local-first personal finance ledger. Treat real bills,
account names, balances, databases, logs, brokerage credentials, and generated
reports as private user data.

## Product Stance

When a new user asks how to use this project for their own bookkeeping, do not
make them operate the whole pipeline by hand. Expose only the decisions and
files that genuinely need the user:

- Which accounts they own and what each account should be called.
- Current balances for wallets, cash, liabilities, or other accounts whose
  statements do not provide balances.
- Exported Alipay, WeChat, bank, brokerage, or manual transaction files.
- Optional brokerage API credentials or snapshots.

The agent should do the rest: initialize the workspace, create private
directories, edit local config from the user's answers, place supplied files in
the correct import folders, run imports, start the local dashboard, and explain
only the next human action.

Open-source defaults must stay minimal. A fresh `private/config.yaml` should
start with only:

- 主银行卡
- 微信余额
- 支付宝余额

If the user mentions additional accounts during the conversation, add them to
`private/config.yaml` for the user, then run `python -m water_ledger import` so
the database and dashboard pick them up. Do not add extra personal assumptions
such as brokerage, loans, in-transit funds, or wealth-management accounts to the
public example config.

## Dialog-First User Input

When the agent environment supports a native user-input dialog or modal, use it
before falling back to prose questions. This applies to Codex, Claude Code, and
similar local coding agents.

Use dialogs for user decisions and private values during:

- First-time initialization.
- Adding a new account.
- Recording or refreshing manual balances.
- Choosing which bill exports the user has available.

Do not ask the user to edit YAML when a dialog plus local file edit can handle
the same job. Ask for the smallest useful batch of information, then update
`private/config.yaml` yourself.

For first-time initialization, collect:

1. Whether to keep the default accounts: 主银行卡, 微信余额, 支付宝余额.
2. Current balances for 微信余额 and 支付宝余额, or "skip for now".
3. Whether the user has Alipay, WeChat, bank, brokerage, or manual bills ready.

For a new account, collect:

1. Account display name and account type.
2. Institution, currency, and whether it counts in net worth.
3. Optional current balance and balance time.

After collecting balance amounts, convert yuan to cents before writing
`manual_balance_cents`, and write `manual_balance_at` when the user provides a
date/time. For liabilities, store balances as negative numbers.

Do not answer first-run questions with a command tutorial by default. Avoid
leading with SQLite, Python modules, directory trees, importer internals, or a
long list of commands. Mention commands only when you are about to run them for
the user, when the user explicitly asks to run things manually, or when a local
blocker requires the user to take over.

## First Answer Contract

When the user asks "这是什么项目", "我该怎么用", "怎么开始记账", or a similar
first-run question, respond like a product onboarding assistant, not like a
technical README. The first answer should:

1. Explain the product in one plain sentence.
2. Say that the user only needs to provide accounts, balances, and bill exports.
3. Offer to initialize/check the workspace immediately.
4. Ask for at most three concrete pieces of information.
5. Avoid command blocks unless the user asks to do it manually.

Use this Chinese shape as the default:

```text
这是一个放在你电脑本地的个人记账本。你不用理解数据库或命令行；
你把账户和账单给我，我来整理、导入，然后给你打开本地看板。

我现在可以先检查/初始化这个账本。你只需要告诉我三件事：
1. 你有哪些账户？比如银行卡、支付宝、微信、现金、券商、借款。
2. 哪些账户需要录当前余额？支付宝、微信、现金、负债通常需要。
3. 你手上有哪些账单文件？支付宝 CSV、微信 Excel、银行 PDF 或手工流水。

真实数据会放在 private/，不会提交到 Git。
```

If a native input dialog is available, show it after this short explanation
instead of continuing with a long back-and-forth in chat.

If running in an environment with shell access, inspect and initialize the
workspace after this answer unless the user asks you to wait.

## First-Run Workflow

Use this workflow for a freshly cloned repository:

1. Inspect whether `private/config.yaml` exists.
2. If it does not exist, run `python -m water_ledger init`.
3. Use a native input dialog when available to ask the user for the minimal checklist:
   - Provide account names and rough account types.
   - Provide current balances for accounts that do not have statement balances.
   - Add or attach bill exports for Alipay, WeChat, bank, brokerage, and manual
     transactions.
4. Edit `private/config.yaml` only after the user provides account information,
   or explain exactly which fields still need user input.
5. Put user-supplied bills under:
   - `private/imports/alipay/`
   - `private/imports/wechat/`
   - `private/imports/bank/`
   - `private/data/manual_transactions.json`
6. Run `python -m water_ledger import`.
7. Run `python -m water_ledger privacy-check` before any commit, branch publish,
   release, or public handoff.
8. Start the dashboard with `python -m water_ledger start --port 8787` and give
   the user the local URL.

For bank-card payments made through WeChat or Alipay, prefer the channel bill as
the visible transaction because it usually has the merchant, payee, product, or
remark. Keep the bank transaction as the duplicate mirror for balance and
reconciliation. If a user imports bank bills first and channel bills later,
rebuild the ledger so the visible bill becomes more readable.

## Adding Accounts In Conversation

When the user says something like "帮我加一张招商银行卡", "我还有一个券商账户",
or "加一个借款账户", treat that as an account-configuration request:

1. Use a native input dialog when available, and ask only for missing essentials: account display name, account type,
   institution, currency, whether it counts in net worth, and an optional
   current balance/time.
2. Edit `private/config.yaml` under `accounts`.
3. Update `account_mapping` only when this account should receive imported
   transactions or optional estimates, such as a bank account, brokerage
   account, in-transit account, borrowing account, or Alipay wallet account.
4. Run `python -m water_ledger import`.
5. Tell the user to refresh the dashboard. The frontend reads configured
   accounts from the database, so the new account should appear after import.

Recommended `account_type` values:

- `bank_card`
- `wallet`
- `investment`
- `brokerage`
- `other_asset`
- `liability`

If the user already has `private/config.yaml`, prefer `python -m water_ledger
init --configure-balances` only when they need to add or refresh manual balance
anchors.

## Privacy Rules

- Keep real personal finance files in `private/` unless the user explicitly asks
  for a different local path.
- Never copy real bills, SQLite databases, credential files, generated reports,
  or logs into public repository paths.
- Never commit files from `private/`, `data/`, `outputs/`, or local secret files.
- Do not paste raw transaction tables, order IDs, card numbers, account numbers,
  access tokens, or full statement text into chat. Summarize findings instead.
- If a file appears to contain real financial data in a public path, stop and
  move it into `private/` or ask the user before continuing.
- Before publishing or packaging the repository, run:

```bash
python -m water_ledger privacy-check
```

## Editing Boundaries

- Prefer project commands over ad hoc scripts:
  - `python -m water_ledger init`
  - `python -m water_ledger import`
  - `python -m water_ledger start`
  - `python -m water_ledger status`
  - `python -m water_ledger stop`
  - `python -m water_ledger brokerage-snapshot --provider enabled`
  - `python -m water_ledger privacy-check`
- Preserve existing user changes. Do not reset, delete, or rewrite private data.
- Do not delete original statement exports. Imports rebuild
  `private/data/water_ledger.sqlite`, but source bills are the user's evidence.
- When editing `private/config.yaml`, keep account names and mappings stable
  unless the user asks to rename or merge accounts.
- If import parsing fails, report the failing file, importer, and likely next
  action. Avoid exposing sensitive rows in the explanation.

## User-Facing Tone

Be concrete and calm. Prefer "把账单文件给我/放到这里，我来导入" over long
documentation tours.

Do not say "最短用法是" followed by setup commands to a nontechnical first-run
user. Say "我来做，你提供这些信息" first. The ideal answer tells the user only:

1. What they need to provide.
2. What the agent is going to do locally.
3. Where they can see the result.
