# Open Source Plan

## Done

- Move private data into `private/`
- Add `.gitignore`
- Add example config and local private config
- Split core package from import script
- Add CLI commands
- Add privacy scan
- Add sample data and docs

## Before First Public Push

- Run `python -m water_ledger privacy-check`
- Inspect `git status --short`
- Confirm no real bills, databases, logs, PDFs, or snapshots are staged
- Run a clean sample import in a temporary private directory

## Future Skills

- `water-ledger-init`
- `water-ledger-import`
- `water-ledger-add-account`
- `water-ledger-rules`
- `water-ledger-assets`
- `water-ledger-privacy-check`
