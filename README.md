# Water Ledger

Water Ledger 是一个放在你电脑本地的个人记账本。你把支付宝、微信、银行卡、券商和手工流水给它，它会整理成一个本地看板，帮你看资产、收支、分类、去重和退款抵消。

真实账单、数据库、输出和密钥默认放在 `private/`，该目录已被 `.gitignore` 忽略。公开仓库只保留示例配置和示例数据。

## 我想开始记账

如果你是普通用户，不需要先理解数据库、目录结构或命令。直接让 Codex/Claude 这类本地 Agent 接管：

```text
我想用 Water Ledger 给自己记账。
请按 AGENTS.md 帮我初始化，问我需要提供哪些账户、余额和账单；
你来改配置、导入账单、启动看板。
```

你只需要准备三类东西：

- 账户：银行卡、支付宝、微信、现金、券商、借款等。
- 余额：支付宝、微信、现金、负债等没有账单余额的账户，录一次当前余额。
- 账单：支付宝 CSV、微信 Excel、银行 PDF、手工流水或券商快照。

Agent 会负责初始化、修改 `private/config.yaml`、导入账单、启动本地看板和排查报错。真实数据只放在 `private/`，不要放到公开目录。

## 手动运行

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m water_ledger init
```

初始化后，把账单放到对应目录：

```text
private/imports/alipay/   支付宝 CSV
private/imports/wechat/   微信支付 Excel
private/imports/bank/     银行 PDF
private/data/manual_transactions.json  手工流水
```

然后运行：

```bash
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
python -m water_ledger brokerage-snapshot --provider enabled
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

## 给 AI Agent 的约束

这个项目适合让 Codex、Claude Code 这类本地 Agent 辅助使用。仓库级约束放在：

- [AGENTS.md](AGENTS.md)：通用 Agent 行为契约。
- [CLAUDE.md](CLAUDE.md)：Claude 入口，指向同一套规则。

建议对 Agent 说：

```text
我想用这个项目给自己记账。请按 AGENTS.md 初始化工作区；
你来修改 private/config.yaml、导入账单并启动看板。
需要我提供账户、余额或账单文件时再问我。
```

Agent 应该只把用户必须决策的事项暴露出来：账户名称、账户类型、缺少账单余额的当前余额、账单导出文件、可选券商凭证。其余步骤由 Agent 在本地完成。

当用户问项目是什么、该怎么开始、下一步做什么这类上手问题时，Agent 不应该先抛命令清单或实现细节；应该先用一句话说明项目能帮用户完成什么，再区分“需要用户提供/决定的信息”和“Agent 可以代劳的操作”，最后主动推进当前环境里的下一步。

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
- [券商净资产快照](docs/brokerage_snapshots.md)
- [隐私边界](docs/privacy.md)
- [常驻运行](docs/run_service.md)
- [发行说明](RELEASE_NOTES.md)

开源前请运行：

```bash
python -m water_ledger privacy-check
```

## 新用户可用性测试

如果想按“第一次 clone 项目”的方式验证完整链路，可以运行：

```bash
bash scripts/smoke_test.sh
```

这个脚本会使用临时私有目录完成初始化、复制 `examples/` 中的支付宝和微信示例账单、重建 SQLite、运行隐私检查、启动本地网页并访问首页，最后停止服务。

也可以手工执行同样的流程：

```bash
python -m water_ledger init --no-balance-prompts
cp examples/支付宝交易明细_sample.csv private/imports/alipay/
cp examples/微信支付账单流水文件_sample.xlsx private/imports/wechat/
python -m water_ledger import
python -m water_ledger start --port 8787
open http://127.0.0.1:8787
python -m water_ledger stop
```

开发者回归测试：

```bash
python -m unittest discover -s tests
```
