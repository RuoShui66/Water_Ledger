# 账户和期初余额

新增账户时，可以运行交互式初始化补录余额：

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

## 账本显示名

右上角标题来自 `private/config.yaml`：

```yaml
profile:
  display_name: 我的
  ledger_title: 我的个人资产账本
```

`python -m water_ledger init` 在交互式终端中会询问显示名。直接回车时使用“我的个人资产账本”。
