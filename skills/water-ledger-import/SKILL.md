---
name: water-ledger-import
description: Import Alipay CSV, WeChat Excel, bank PDFs, and manual transactions into Water Ledger, rebuild the SQLite database, and summarize imported rows, duplicates, refunds, and date ranges. Use when the user asks to import bills or rebuild their ledger.
---

# Water Ledger Import

Use this skill to import local private bills into Water Ledger.

## Workflow

1. Place files under `private/imports/`:
   - Alipay CSV: `private/imports/alipay`
   - WeChat Excel: `private/imports/wechat`
   - Bank PDFs: `private/imports/bank`
2. Run `python -m water_ledger import`.
3. Summarize the JSON output.
4. If import fails, inspect the relevant importer in `water_ledger/importers/`.

Do not move private bills into public directories.
