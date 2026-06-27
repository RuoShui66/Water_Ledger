# 券商净资产快照

Water Ledger 可以把券商账户的净资产写入 `asset_snapshots`，用于资产负债页和净值曲线。

有两种方式：

- 批量拉取历史净资产：适合回溯任意时间段，例如过去 3 个月、半年、3 年或完整开户以来。
- 调用券商实时接口：适合记录今天或定期记录之后的净资产。

## 批量拉取历史净资产

主路径是让项目运行一个本地脚本去批量拉取，不需要用户自己上传 CSV。先在 `private/config.yaml` 给券商配置 `history_command`：

```yaml
brokerages:
  longbridge:
    enabled: true
    account: 我的券商账户
    currency: USD
    history_command:
      - python
      - private/tools/export_brokerage_history.py
      - --account
      - "{account}"
      - --currency
      - "{currency}"
      - --start
      - "{start}"
      - --end
      - "{end}"
```

`history_command` 可以输出 JSON 或 CSV。JSON 示例：

```json
[
  {"date": "2025-01-01", "balance": "10000.00", "currency": "USD"},
  {"date": "2026-06-27", "balance": "15666.66", "currency": "USD"}
]
```

然后运行：

```bash
python -m water_ledger brokerage-history --provider longbridge --start 2025-01-01 --end 2026-06-27 --rebuild
```

等价脚本入口：

```bash
python scripts/fetch_brokerage_history.py --provider longbridge --start 2025-01-01 --end 2026-06-27 --rebuild
```

命令会把脚本结果写入 `private/imports/brokerage/`，并在 `--rebuild` 时立即重建 SQLite。日期范围不受限制；脚本返回哪几天，资产页就能使用哪几天的快照。如果想看每日曲线，请让脚本返回每日净资产。

## 历史净资产 CSV 兜底

把 CSV 放到：

```text
private/imports/brokerage/
```

然后运行：

```bash
python -m water_ledger import
```

CSV 支持这些列名：

- `account` / `account_name` / `账户` / `账户名称`
- `date` / `snapshot_at` / `datetime` / `日期` / `时间`
- `balance` / `net_worth` / `net_assets` / `amount` / `净资产` / `资产`
- `currency`
- `source` / `provider` / `来源`

最小示例：

```csv
account,date,balance,currency,source
我的券商账户,2025-01-01,10000.00,USD,manual_history
我的券商账户,2026-06-27,15666.66,USD,manual_history
```

CSV 是脚本产物或兜底导入格式。日期范围不受限制。CSV 里有哪几天，资产页就能使用哪几天的快照；如果想看每日曲线，请导出每日净资产。

统一命令：

```bash
python -m water_ledger brokerage-snapshot --provider enabled
```

只测试接口、不写入 SQLite：

```bash
python -m water_ledger brokerage-snapshot --provider ibkr --dry-run
```

原始响应会写入：

```text
private/outputs/brokerage_snapshots/
```

所有券商默认关闭。请只在 `private/config.yaml` 中启用和填写账号、路径、命令；不要把密钥、私钥、token 或真实响应放进公开仓库。

## Longbridge

依赖本机已配置 `longbridge` CLI：

```yaml
brokerages:
  longbridge:
    enabled: true
    account: 美股账户
    currency: USD
    region: cn
```

兼容旧入口：

```bash
python scripts/snapshot_longbridge_assets.py
```

## 富途 / Futu / moomoo

富途官方 OpenAPI 需要先启动本地 OpenD，再通过 Python SDK 查询资金数据。官方接口 `accinfo_query` 用于查询净资产、证券市值、现金和购买力等账户资金数据。

安装可选依赖：

```bash
pip install futu-api
```

示例配置：

```yaml
brokerages:
  futu:
    enabled: true
    account: 美股账户
    currency: USD
    host: 127.0.0.1
    port: 11111
    market: US
    trd_env: REAL
    acc_id:
    acc_index: 0
```

如果 SDK 返回字段和默认提取不一致，可加：

```yaml
balance_paths:
  - data.0.total_assets
```

## 老虎 / Tiger Brokers

老虎 OpenAPI 的 Python SDK 提供 `TradeClient.get_assets` 和 `TradeClient.get_prime_assets`。环球账户通常用 `get_assets`，综合/模拟账户可设置 `account_mode: prime`。

安装老虎官方 Python SDK 后，在私有配置或环境变量里放账号信息：

```yaml
brokerages:
  tiger:
    enabled: true
    account: 美股账户
    currency: USD
    account_mode: auto
    account_id:
    private_key_path:
    tiger_id:
    secret_key:
```

对应环境变量：

```bash
export TIGER_PRIVATE_KEY_PATH=/path/to/private_key.pem
export TIGER_ID=your_tiger_id
export TIGER_ACCOUNT=your_account_id
export TIGER_SECRET_KEY=optional_secret_key
```

## 盈透 / IBKR

IBKR 使用官方 Client Portal Gateway。先启动 Gateway 并在浏览器完成登录，默认地址是：

```text
https://localhost:5000
```

Water Ledger 会查询：

```text
/v1/api/portfolio/accounts
/v1/api/portfolio/{accountId}/summary
```

示例配置：

```yaml
brokerages:
  ibkr:
    enabled: true
    account: 美股账户
    currency: USD
    base_url: https://localhost:5000/v1/api
    account_id:
```

如果账户较多，建议显式填写 `account_id`。

## Robinhood

Robinhood 目前公开的官方自动化入口是 Trading MCP，而不是常规 REST 密钥接口。Water Ledger 不内置非官方私有 API 登录。

推荐方式是配置一个本地、已认证的 MCP 桥接命令，让它输出 JSON，例如：

```json
{
  "net_liquidation": "12345.67",
  "currency": "USD"
}
```

私有配置：

```yaml
brokerages:
  robinhood:
    enabled: true
    account: 美股账户
    currency: USD
    command:
      - python
      - private/tools/robinhood_snapshot.py
    balance_paths: [net_liquidation, total_equity, total_value]
    currency_paths: [currency]
```

这样可以用 Robinhood 官方 MCP 完成授权，同时避免在 Water Ledger 中保存 Robinhood 密码或依赖非官方抓包接口。
