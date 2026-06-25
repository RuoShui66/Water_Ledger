---
name: water-ledger-privacy-check
description: Scan a Water Ledger workspace before publishing or committing to ensure private bills, SQLite databases, PDFs, logs, card numbers, tokens, and password-like filenames are not in public paths. Use before open sourcing, committing, or publishing.
---

# Water Ledger Privacy Check

Use this skill before committing or publishing.

## Workflow

1. Run `python -m water_ledger privacy-check`.
2. Run `find . -path './private' -prune -o -type f -print` if manual inspection is needed.
3. Ensure no real `.csv`, `.xlsx`, `.pdf`, `.sqlite`, `.db`, or `.log` files are outside `private/`.
4. Move any finding into `private/` or remove it from the workspace before publishing.
