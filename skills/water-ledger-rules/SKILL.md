---
name: water-ledger-rules
description: Tune Water Ledger classification, transfer, refund, and cashflow rules by editing configuration and rebuilding the local database. Use when the user asks to recategorize merchants, exclude transfers, or adjust refund handling.
---

# Water Ledger Rules

Use this skill to adjust rules in `private/config.yaml`.

## Workflow

1. Edit `classification` for category keywords.
2. Edit `private_rules` for personal transfer or borrowing estimates.
3. Run `python -m water_ledger import`.
4. Compare `private/outputs/expense_by_category.csv` and `private/outputs/monthly_cashflow.csv`.

Promote only generic rules to `config/config.example.yaml`.
