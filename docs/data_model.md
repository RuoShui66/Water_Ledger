# Water Ledger 数据存储设计

目标是把“原始流水”和“用于统计的记账流水”分层保存：原始流水可追溯、可重新去重；记账流水面向总览、账单、资产、报告页面查询。

## 核心表

账户、类别、分类关键词、券商账户和个性化估算规则来自配置文件。公开仓库提供 `config/config.example.yaml`，本地私有配置放在 `private/config.yaml`。

### `source_files`

每次导入的源文件。记录文件名、来源、文件 hash、行数和导入时间，便于以后增量导入与审计。

### `accounts`

账户维表。可通过配置预置：

- 主银行卡
- 微信余额
- 支付宝余额

开源默认只预置这三个账户。券商、理财、负债、在途资金、额外银行卡等都应由用户在 `private/config.yaml` 里按需添加，或由 Agent 根据用户会话代为添加。

微信、支付宝账单通常不包含余额，所以余额需要在 `init` 时手动录入一次，或后续接入资产快照。银行余额可从支持“交易后余额”字段的流水中自动生成。

如果账户配置了 `manual_balance_cents` 和 `manual_balance_at`，导入时会把这个时间点视为已知余额，并按该账户非重复交易倒推历史余额，生成：

- `manual_current`：已知时点余额；
- `manual_backfill`：每笔交易后的倒推余额；
- `manual_opening_balance`：导入区间第一笔交易前一秒的期初余额。

如果账户已经有银行流水余额、券商快照等权威 `asset_snapshots`，不会用手工余额倒推覆盖。

### `imported_transactions`

平台原始流水归一化后的表，一行对应源文件中的一笔交易。字段包括：

- `source`: `wechat` / `alipay` / `boc`
- `source_txn_id`: 平台订单号；中行用交易要素 hash
- `occurred_at`
- `direction`: `收入` / `支出` / `不计收支` / `中性交易`
- `amount_cents` / `signed_cents`
- `raw_category` / `category`
- `counterparty`
- `description`
- `payment_method`
- `balance_after_cents`
- `raw_json`

金额统一用“分”保存，避免浮点误差。

### `ledger_transactions`

面向业务页面的记账流水。它引用 `imported_transactions`，并增加：

- `account_id`
- `is_duplicate`
- `duplicate_of_ledger_id`
- `duplicate_reason`
- `include_in_cashflow`

`source` 表示交易来源/通道，例如支付宝账单、微信账单、银行流水；`account_id` 表示实际资金账户。支付宝或微信账单里如果 `收/付款方式` 是银行卡，`source` 仍保留为支付宝/微信，但 `account_id` 归到对应银行卡，避免被当作支付宝余额或微信余额流水。

统计收入、支出、净现金流时只取：

```sql
WHERE is_duplicate = 0 AND include_in_cashflow = 1
```

### `duplicate_links`

跨平台去重关系。当前规则：

- 支付宝/微信订单作为主记录；
- 匹配到的中行快捷支付流水作为重复镜像；
- 中行流水仍保留，用于银行卡余额曲线；
- 只在金额相同、方向相同、时间接近、且中行描述包含 `支付宝` 或 `财付通` 时匹配。

### `asset_snapshots`

资产快照表，用于资产曲线和净资产。中行自动写入每笔交易后的余额；微信、支付宝、美股、负债后续可以按天或按月手动写入。

### `category_overrides`

用户手动改分类时写这里，不改原始流水。展示时优先取 override，没有 override 再取自动分类。

### `category_rules`

后续可做用户自定义分类规则，例如“描述包含 Apple -> 数码订阅”。

## 页面查询口径

### 总览

- 净资产：`v_net_worth_latest`
- 本月收入/支出/净现金流：`v_monthly_cashflow`
- 资产曲线：`v_asset_curve`

### 账单

查询 `ledger_transactions`，支持按 `source` 过滤中行/微信/支付宝，按 `category` 过滤，按 `counterparty`/`description` 搜索。默认可隐藏 `is_duplicate=1`，需要对账时显示。

### 资产

账户列表取 `accounts`，余额取每个账户最新 `asset_snapshots`，没有快照则取 `manual_balance_cents`。

### 报告

月度总结取 `v_monthly_cashflow` 加分类聚合；异常支出可按同分类金额分位数或同商户历史均值判断；订阅统计可从 `category='数码订阅'` 或固定商户周期性交易识别。
