# Release Notes

## Open Source Preview

Water Ledger is currently a local-first personal finance ledger. This preview is intended for people who are comfortable running Python tools locally and keeping their own financial data outside the public repository.

### Supported Imports

- Alipay CSV transaction exports.
- WeChat Pay Excel transaction exports.
- Selected bank PDF statements, when their table layout can be parsed by the current importer.
- Manual JSON transactions for adjustments, cash records, and entries that are not available from platform exports.

### Optional Capabilities

- Longbridge brokerage asset snapshots are supported as an optional capability. They are disabled by default and should be configured only in `private/config.yaml`.
- Manual account balance anchors can be entered during `init` and are used to backfill opening balances when statements do not provide balance-after-transaction fields.

### Privacy Boundary

- Real bills, SQLite databases, generated reports, logs, account names, card numbers, and secrets should stay under `private/`.
- Public examples are synthetic and live under `examples/`.
- Run `python -m water_ledger privacy-check` before publishing changes.

### Known Limits

- Bank PDF parsing is layout-dependent and may need importer changes for additional banks or statement versions.
- Wallet balances for Alipay and WeChat may need a manual balance anchor because platform bills often do not include balance-after-transaction fields.
- Brokerage automation is optional and not required for normal bill import or the local dashboard.
