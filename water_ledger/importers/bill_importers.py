from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pandas as pd
from pypdf import PdfReader

from water_ledger.config import mapping_account
from water_ledger.core.classification import classify
from water_ledger.core.models import RawTxn
from water_ledger.core.utils import cents, norm_text, parse_dt, sha1, signed_amount
from water_ledger.paths import ROOT


def source_file_label(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def read_alipay(path: Path) -> list[RawTxn]:
    lines: list[str] = []
    header_idx: int | None = None
    for encoding in ("gb18030", "utf-8-sig"):
        with path.open("r", encoding=encoding, errors="replace", newline="") as f:
            lines = f.readlines()
        header_idx = next((i for i, line in enumerate(lines) if line.startswith("交易时间,")), None)
        if header_idx is not None:
            break
    if header_idx is None:
        raise ValueError(f"Cannot find Alipay CSV header in {path}")
    reader = csv.DictReader(lines[header_idx:])
    rows: list[RawTxn] = []
    for row in reader:
        if not row.get("交易时间"):
            continue
        direction = norm_text(row.get("收/支"))
        amount_cents = cents(row.get("金额"))
        raw_category = norm_text(row.get("交易分类"))
        counterparty = norm_text(row.get("交易对方"))
        description = norm_text(row.get("商品说明"))
        source_txn_id = norm_text(row.get("交易订单号")).strip()
        occurred_at = parse_dt(row["交易时间"])
        category = classify("alipay", raw_category, counterparty, description, direction)
        rows.append(
            RawTxn(
                source="alipay",
                source_file=source_file_label(path),
                source_txn_id=source_txn_id or sha1("alipay", occurred_at, amount_cents, counterparty, description),
                occurred_at=occurred_at,
                direction=direction,
                amount_cents=amount_cents,
                signed_cents=signed_amount(direction, amount_cents),
                currency="CNY",
                account_hint="支付宝",
                raw_category=raw_category,
                category=category,
                counterparty=counterparty,
                description=description,
                payment_method=norm_text(row.get("收/付款方式")),
                status=norm_text(row.get("交易状态")),
                balance_after_cents=None,
                raw_json={k: norm_text(v) for k, v in row.items() if k},
            )
        )
    return rows

def read_wechat(path: Path) -> list[RawTxn]:
    df = pd.read_excel(path, sheet_name=0, header=None, dtype=str)
    header_row = df.index[df.iloc[:, 0].astype(str).str.strip().eq("交易时间")][0]
    data = pd.read_excel(path, sheet_name=0, header=header_row, dtype=str)
    data = data[data["交易时间"].notna()]
    rows: list[RawTxn] = []
    for _, row in data.iterrows():
        direction = norm_text(row.get("收/支"))
        amount_cents = cents(row.get("金额(元)"))
        raw_category = norm_text(row.get("交易类型"))
        counterparty = norm_text(row.get("交易对方"))
        description = norm_text(row.get("商品"))
        remarks = [
            norm_text(row.get(key))
            for key in ("备注", "交易备注", "转账说明", "付款备注", "收款方备注")
            if norm_text(row.get(key))
        ]
        for remark in remarks:
            if remark and remark not in description:
                description = f"{description} · {remark}" if description else remark
        source_txn_id = norm_text(row.get("交易单号"))
        occurred_at = parse_dt(row["交易时间"])
        category = classify("wechat", raw_category, counterparty, description, direction)
        rows.append(
            RawTxn(
                source="wechat",
                source_file=source_file_label(path),
                source_txn_id=source_txn_id or sha1("wechat", occurred_at, amount_cents, counterparty, description),
                occurred_at=occurred_at,
                direction=direction,
                amount_cents=amount_cents,
                signed_cents=signed_amount(direction, amount_cents),
                currency="CNY",
                account_hint="微信",
                raw_category=raw_category,
                category=category,
                counterparty=counterparty,
                description=description,
                payment_method=norm_text(row.get("支付方式")),
                status=norm_text(row.get("当前状态")),
                balance_after_cents=None,
                raw_json={str(k): norm_text(v) for k, v in row.items()},
            )
        )
    return rows

BOC_START = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})\s+人民币\s+([+-]?[\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+(.*)$")

def boc_clean_text(*parts: str) -> str:
    text = norm_text(" ".join(parts))
    text = re.sub(r"-{3,}", " ", text)
    text = text.replace("美 团", "美团")
    text = text.replace("CHAG EE", "CHAGEE").replace("CHA GEE", "CHAGEE")
    text = text.replace("京 东", "京东")
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def boc_counterparty_and_description(rest: str, extra_lines: list[str]) -> tuple[str, str]:
    full = boc_clean_text(rest, *extra_lines)
    if "美团支付" in full:
        counterparty = "美团支付(钱袋宝)-美团"
        app_match = re.search(r"App([^\s]+)", full)
        if app_match:
            return counterparty, f"美团App {app_match.group(1)}"
        after = re.split(r"美团支付\(钱袋宝\)-", full, maxsplit=1)[-1].strip()
        if after.startswith("美团 "):
            after = after[3:].strip()
        after = re.split(r"美团支付|支付宝|财付通|\b[A-Z]?\d{6,}", after, maxsplit=1)[0]
        after = boc_clean_text(after).strip(" -")
        if after:
            return counterparty, f"美团App {after}"
        return counterparty, full
    if "财付通" in full:
        apartment = re.search(r"财付通-(悦虹人才公寓-)\s*(吴中路店)", full)
        if apartment:
            name = "".join(apartment.groups())
            return name, f"财付通 {name}"
        merchant = re.search(r"(财付通-[^\s]+(?:\s+[^\s]+)?)", full)
        if merchant:
            counterparty = norm_text(merchant.group(1)).replace(" ", "")
            return counterparty, full
        return "财付通", full
    if "支付宝" in full:
        merchant = re.search(r"(支付宝[^\s]+)", full)
        if merchant:
            return merchant.group(1), full
    for provider in ["网银在线", "银联商务", "拉卡拉", "通联支付"]:
        if provider in full:
            after = re.split(rf"{provider}-", full, maxsplit=1)[-1].strip()
            after = re.split(rf"{provider}|支付宝|财付通|美团支付|\b[A-Z]?\d{{6,}}", after, maxsplit=1)[0]
            after = boc_clean_text(after).replace(" ", "").strip(" -")
            if after:
                return after, f"{provider} {after}"
    return full, full

def read_boc_pdf(path: Path) -> list[RawTxn]:
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        password = re.search(r"密码(\d+)", path.name)
        if not password or not reader.decrypt(password.group(1)):
            return []
    records: list[list[str]] = []
    current: list[str] = []
    for page in reader.pages:
        for raw_line in (page.extract_text() or "").splitlines():
            line = norm_text(raw_line)
            if not line:
                continue
            if BOC_START.match(line):
                if current:
                    records.append(current)
                current = [line]
            elif current:
                if line.startswith(("温馨提示", "第 ", "--------------------END", "中国银行交易流水", "交易区间", "借记卡号", "账号：", "记账日期")):
                    continue
                current.append(line)
    if current:
        records.append(current)

    rows: list[RawTxn] = []
    for record in records:
        first = record[0]
        m = BOC_START.match(first)
        if not m:
            continue
        date, time, amount, balance, rest = m.groups()
        occurred_at = f"{date} {time}"
        amount_cents = cents(amount)
        signed = amount_cents
        direction = "收入" if signed > 0 else "支出"
        counterparty, description = boc_counterparty_and_description(rest, record[1:])
        raw_category = norm_text(rest).split(" ", 1)[0] if rest else ""
        source_txn_id = sha1("boc", occurred_at, signed, cents(balance), description)
        category = classify("boc", raw_category, counterparty, description, direction)
        rows.append(
            RawTxn(
                source="boc",
                source_file=source_file_label(path),
                source_txn_id=source_txn_id,
                occurred_at=occurred_at,
                direction=direction,
                amount_cents=abs(signed),
                signed_cents=signed,
                currency="CNY",
                account_hint=mapping_account("bank_account", "主银行卡"),
                raw_category=raw_category,
                category=category,
                counterparty=counterparty,
                description=description,
                payment_method=mapping_account("bank_account", "银行卡"),
                status="已记账",
                balance_after_cents=cents(balance),
                raw_json={"lines": record},
            )
        )
    return rows

def read_manual(path: Path) -> list[RawTxn]:
    items = json.loads(path.read_text(encoding="utf-8"))
    rows: list[RawTxn] = []
    for item in items:
        direction = norm_text(item.get("direction"))
        amount_cents = cents(item.get("amount"))
        signed = signed_amount(direction, amount_cents)
        source = norm_text(item.get("source")) or "manual"
        raw_category = norm_text(item.get("raw_category"))
        counterparty = norm_text(item.get("counterparty"))
        description = norm_text(item.get("description"))
        occurred_at = parse_dt(item.get("occurred_at"))
        category = norm_text(item.get("category")) or classify(source, raw_category, counterparty, description, direction)
        rows.append(
            RawTxn(
                source=source,
                source_file=source_file_label(path),
                source_txn_id=norm_text(item.get("source_txn_id")) or sha1(source, occurred_at, amount_cents, counterparty, description),
                occurred_at=occurred_at,
                direction=direction,
                amount_cents=amount_cents,
                signed_cents=signed,
                currency=norm_text(item.get("currency")) or "CNY",
                account_hint=norm_text(item.get("account_hint")),
                raw_category=raw_category,
                category=category,
                counterparty=counterparty,
                description=description,
                payment_method=norm_text(item.get("payment_method")),
                status=norm_text(item.get("status")),
                balance_after_cents=None,
                raw_json=item.get("raw_json") or item,
            )
        )
    return rows
