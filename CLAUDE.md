# Claude Instructions

Follow [AGENTS.md](AGENTS.md) as the source of truth for this repository.

Key reminders:

- Keep real finance data inside `private/`.
- Ask the user only for account choices, current balances, bill exports, and
  optional brokerage credentials.
- Use a native input dialog when available for initialization, adding accounts,
  and recording WeChat/Alipay/manual balances.
- Daily brokerage snapshots can default to the current agent's recurring-task
  feature: Codex app automation in Codex, Claude routine/cron in Claude Code.
  Use the project `brokerage-schedule` command only when agent-native scheduling
  is unavailable or the user asks for a system-local schedule.
- When adding a brokerage account, proactively set up daily net-worth snapshots
  after provider configuration, unless the user explicitly declines.
- Do initialization, config edits, imports, privacy checks, and dashboard startup
  for the user whenever possible.
- Never commit or paste raw private financial data.
