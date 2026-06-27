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

## First-Run Workflow

Use this workflow for a freshly cloned repository:

1. Inspect whether `private/config.yaml` exists.
2. If it does not exist, run `python -m water_ledger init`.
3. Tell the user the minimal checklist:
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
documentation tours. The ideal answer tells the user only:

1. What they need to provide.
2. What the agent is going to do locally.
3. Where they can see the result.

