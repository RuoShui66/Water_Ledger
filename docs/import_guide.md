# 导入指南

## 支付宝

从支付宝导出 CSV 后放入：

```text
private/imports/alipay/
```

文件名建议保留 `支付宝交易明细` 前缀，导入器会自动识别。

## 微信支付

从微信支付导出 Excel 后放入：

```text
private/imports/wechat/
```

文件名建议保留 `微信支付账单流水文件` 前缀。

## 银行流水

当前银行 PDF 导入器面向含有交易时间、金额、余额字段的流水文本。PDF 放入：

```text
private/imports/bank/
```

如果 PDF 加密，导入器会尝试从文件名中的 `密码xxxx` 片段读取密码。开源仓库不要保留这种文件名。

## 手工流水

手工流水放在：

```text
private/data/manual_transactions.json
```

可参考 [examples/manual_transactions.example.json](../examples/manual_transactions.example.json)。

## 重建账本

```bash
python -m water_ledger import
```

重建会覆盖 `private/data/water_ledger.sqlite`，但不会删除原始账单。
