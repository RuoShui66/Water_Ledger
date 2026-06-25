# 隐私边界

Water Ledger 的原则是：代码、示例配置和假数据可以开源；真实账单、数据库、输出、日志和密钥只留在 `private/`。

## 不应提交

- `private/`
- `.env` 和所有密钥文件
- 真实 `.csv`、`.xlsx`、`.pdf`
- `.sqlite`、`.db`
- 日志和输出报表
- 带姓名、卡号、手机号、订单号的文件

## 开源前检查

```bash
python -m water_ledger privacy-check
```

这个命令会扫描公开工作区中的高风险文件和常见敏感文本。它不会扫描 `private/`，因为该目录本来就不应进入 Git。

## 配置策略

公开仓库只保留：

```text
config/config.example.yaml
```

本地配置放在：

```text
private/config.yaml
```

如果你需要在配置里写真实账户名、卡尾号、券商账户、借款关键词或定时任务参数，请只写入 `private/config.yaml`。
