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

Agent 会负责初始化、修改 `private/config.yaml`、导入账单、启动本地看板和排查报错。如果 Codex/Claude Code 支持输入对话框，Agent 会弹出对话框让你填写微信余额、支付宝余额、账单情况等必要信息。真实数据只放在 `private/`，不要放到公开目录。

开源初始配置只默认创建三个账户：

- 主银行卡
- 微信余额
- 支付宝余额

如果你还有其他账户，可以之后随时加。你可以在会话里直接说“帮我加一张招商银行卡”“我还有一个券商账户”“加一个借款账户”，Agent 会弹出对话框收集账户类型、币种、是否计入净资产和当前余额，然后写进 `private/config.yaml`，重建账本后前端看板会自动出现对应账户。

## 常见场景

### 我只想先记日常收支

你可以先只从银行卡、微信和支付宝开始。告诉 Agent 你有哪些账户、当前微信/支付宝余额大概是多少，以及你手上有哪些账单文件。

Agent 会帮你建立默认账户、整理账单并打开看板。之后你看到的每笔交易会尽量显示更容易理解的信息：比如银行卡通过微信支付时，账单里会优先展示微信里更清楚的商户、商品和备注；余额变化仍会归到实际出钱的账户。

### 我还有更多账户

你可以随时告诉 Agent 新增账户，比如多一张银行卡、一个现金账户、一个券商账户、一个信用卡欠款账户或一笔借款。

Agent 会继续问少量必要信息：账户叫什么、属于哪类、用什么币种、是否算进净资产、有没有当前余额。加好后，看板会自动出现这个账户，不需要你手动改页面。

### 我想回溯券商历史净资产

如果你希望资产曲线从过去某一天开始，而不是只从今天开始，告诉 Agent 你想回溯的时间范围。

Agent 会尝试帮你批量拉取这段时间的每日净资产，导入账本并刷新看板。当前自动接入只实际测试过长桥；如果你用的是其他券商，Agent 会告诉你能否直接接入，或者需要提供哪种历史数据作为替代。

新增券商账户后，Agent 也会主动帮你安排之后每天自动更新净资产，除非你明确说暂时不需要。

### 我只有今天的券商余额

这也可以先用。你可以让 Agent 先记录今天的券商余额，作为资产曲线的起点。

需要注意的是，只录今天余额不能还原过去每天的市场波动。如果以后想看到更完整的历史曲线，可以再让 Agent 回溯历史净资产。

### 我想以后每天自动更新券商净资产

你只需要告诉 Agent 想每天几点更新。Agent 会根据当前环境选择合适的定时方式，到点自动读取券商净资产并写入本地账本。

以后打开看板时，资产曲线会随着每日快照逐步更新。你也可以随时让 Agent 帮你查看定时任务是否还在运行，或者暂停每日更新。

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
private/imports/brokerage/ 券商历史净资产导入文件，由脚本生成或手工兜底
private/data/manual_transactions.json  手工流水
```

券商自动接入目前只实际测试过长桥。其他券商配置保留为扩展入口，使用前请先小范围验证，或用券商历史净资产文件兜底导入。

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
python -m water_ledger brokerage-schedule install --time 04:01
python -m water_ledger brokerage-schedule status
python -m water_ledger brokerage-schedule uninstall
python -m water_ledger privacy-check
python -m water_ledger brokerage-history --provider longbridge --start 2025-01-01 --end 2026-06-27 --rebuild
```

`serve` 是前台运行，适合调试；`start` 会在后台常驻运行本地看板，日志写入 `private/logs/server.log`，PID 写入 `private/logs/server.pid`。

`brokerage-schedule install` 会在 macOS 上安装一个本项目专用的 LaunchAgent，在 Windows 上安装一个任务计划程序任务，每天按指定时间运行 `brokerage-snapshot`。日志写入 `private/logs/brokerage_snapshot.log`；本地调度元数据写入 `private/logs/brokerage_schedule.json`。如果只想生成配置但不立即加载，可加 `--write-only`。

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

Agent 应该只把用户必须决策的事项暴露出来：账户名称、账户类型、缺少账单余额的当前余额、账单导出文件、可选券商凭证。其余步骤由 Agent 在本地完成。新增账户时，Agent 应该修改 `private/config.yaml` 并重新导入；前端从数据库读取账户，不需要用户手动改页面。

用户想要每日自动更新券商净资产时，如果当前环境支持 Agent 原生定时任务，Agent 默认可以创建该环境自己的每日任务：Codex app 用 automation，Claude Code 用 routine/cron。定时任务的执行内容仍应调用项目的 `brokerage-snapshot` 命令。在手动终端或没有 Agent 原生定时能力的环境里，使用项目命令 `python -m water_ledger brokerage-schedule install --time HH:MM` 安装本地定时任务。检查或关闭本地任务时使用同一组 `brokerage-schedule status/uninstall` 命令。

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
