# Water Ledger

本地优先的个人资产账本。它把支付宝、微信、银行卡、券商和手工流水统一进 SQLite，在本地完成分类、去重、退款抵消、资产快照和看板展示。

真实账单、数据库、输出和密钥默认放在 `private/`，该目录已被 `.gitignore` 忽略。公开仓库只保留示例配置和示例数据。

## 快速开始

```bash
pip install -r requirements.txt
python -m water_ledger init
python -m water_ledger import
python -m water_ledger start --port 8787
```

浏览器访问：

```text
http://127.0.0.1:8787
```

## 常用命令

```bash
python -m water_ledger init
python -m water_ledger import
python -m water_ledger start
python -m water_ledger status
python -m water_ledger stop
python -m water_ledger serve
python -m water_ledger privacy-check
```

`serve` 是前台运行，适合调试；`start` 会在后台常驻运行本地看板，日志写入 `private/logs/server.log`，PID 写入 `private/logs/server.pid`。

`init` 会创建：

```text
private/
  config.yaml
  imports/
    alipay/
    wechat/
    bank/
  data/
  outputs/
```

公开示例配置在 [config/config.example.yaml](config/config.example.yaml)，本地运行时优先读取 `private/config.yaml`。
初始化时可输入账本显示名；直接回车时默认显示“我的个人资产账本”。`init` 也会让你选填各账户当前余额，银行/券商账单或接口会提供余额的账户可以跳过；微信、支付宝、现金、负债等缺少“交易后余额”的账户建议填一次，导入后会用它倒推期初余额。

已有配置想补录余额时运行：

```bash
python -m water_ledger init --configure-balances
```

## 代码结构

```text
water_ledger/
  core/          # 金额、文本、分类、去重、退款、资产和报告逻辑
  importers/     # 支付宝、微信、银行 PDF、手工流水导入器
  storage/       # SQLite schema 和数据库装载
  cli.py         # 命令行入口
web_app/         # 本地看板服务
scripts/         # 兼容入口
examples/        # 可公开的假数据
```

## 文档

- [数据模型](docs/data_model.md)
- [账户和期初余额](docs/account_setup.md)
- [导入指南](docs/import_guide.md)
- [隐私边界](docs/privacy.md)
- [常驻运行](docs/run_service.md)
- [发行说明](RELEASE_NOTES.md)

开源前请运行：

```bash
python -m water_ledger privacy-check
```
