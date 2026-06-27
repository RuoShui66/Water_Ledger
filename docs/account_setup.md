# 账户和期初余额

开源初始配置只包含最常见的三个账户：

- 主银行卡
- 微信余额
- 支付宝余额

其他账户都是可配置的。你可以在会话里告诉 Agent：

```text
帮我加一张招商银行卡，计入净资产，人民币账户。
```

或者：

```text
我还有一个券商账户，美元，计入净资产。
```

如果 Codex/Claude Code 支持输入对话框，Agent 应该弹出对话框收集账户类型、币种、是否计入净资产和当前余额。Agent 会把账户添加到 `private/config.yaml`，然后运行 `python -m water_ledger import`。前端看板从数据库读取账户，重新导入并刷新后会自动出现新增账户。

需要补录余额时，Agent 应优先用输入对话框询问微信余额、支付宝余额或新增账户余额。手动操作时也可以运行交互式初始化：

```bash
python -m water_ledger init --configure-balances
```

也可以直接在 `private/config.yaml` 的 `accounts` 中添加一项：

```yaml
- name: 招商银行卡
  institution: 招商银行
  account_type: bank_card
  currency: CNY
  include_in_net_worth: true
  manual_balance_cents: 123456
  manual_balance_at: "2026-06-30 23:59:59"
  note: 用户手动录入当前余额
```

`manual_balance_cents` 用“分”保存。上面的 `123456` 表示 `1234.56` 元。

导入账单后，Water Ledger 会按下面的顺序确定账户余额：

1. 银行流水、券商接口或资产快照里带的余额优先，这类数据会写成权威 `asset_snapshots`。
2. 如果没有权威快照，但账户配置了 `manual_balance_cents` 和 `manual_balance_at`，系统会把它当成已知余额。
3. 系统从这个已知余额出发，按账户交易倒推历史余额，并写入 `asset_snapshots`：

- `manual_current`
- `manual_backfill`
- `manual_opening_balance`

这适合“我有一年的账单，也知道今天余额，想估算一年前期初余额”的场景。

注意：

- 微信、支付宝钱包有专门估算逻辑，因为不是每笔平台账单都影响钱包余额。
- 负债账户的余额应为负数；初始化交互中输入正数欠款时会自动保存为负数。
- 如果银行 PDF 或券商 API 已经提供了余额快照，系统会优先使用这些权威快照。
- 交易必须能映射到该账户，倒推才有意义；必要时更新 `account_mapping`。
- 如果要启用支付宝理财估算，可以新增一个 `investment` 账户，并在 `account_mapping.alipay_wealth_account` 指向它。

常用 `account_type`：

- `bank_card`：银行卡。
- `wallet`：微信、支付宝、现金等钱包。
- `investment`：理财、基金等投资资产。
- `brokerage`：券商账户。
- `other_asset`：其他资产或在途资金。
- `liability`：借款、消费贷、信用卡欠款等负债。

新增券商账户后，如果想回溯历史净资产，让 Agent 运行 `python -m water_ledger brokerage-history --provider <provider> --start <date> --end <date> --rebuild` 批量拉取任意时间段。只录当前余额只能得到当前快照，不能还原过去每天的市场波动。CSV 只是脚本产物或兜底导入格式。

## 账本显示名

右上角标题来自 `private/config.yaml`：

```yaml
profile:
  display_name: 我的
  ledger_title: 我的个人资产账本
```

`python -m water_ledger init` 在交互式终端中会询问显示名。直接回车时使用“我的个人资产账本”。
