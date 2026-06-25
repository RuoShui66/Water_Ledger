from __future__ import annotations

import hashlib
import re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import pandas as pd


def cents(value: Any) -> int:
    if value is None or value == "":
        return 0
    text = str(value).replace(",", "").replace("￥", "").replace("元", "").strip()
    return int((Decimal(text) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def money_from_cents(value: int | None) -> float | None:
    if value is None:
        return None
    return float(Decimal(value) / Decimal(100))


def norm_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\u3000", " ").replace("\t", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return "" if text.lower() == "nan" else text


def sha1(*parts: Any) -> str:
    h = hashlib.sha1()
    for part in parts:
        h.update(norm_text(part).encode("utf-8", errors="ignore"))
        h.update(b"\x1f")
    return h.hexdigest()


def parse_dt(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return pd.to_datetime(str(value)).strftime("%Y-%m-%d %H:%M:%S")


def signed_amount(direction: str, amount_cents: int) -> int:
    if direction in {"支出", "不计收支"}:
        return -amount_cents
    return amount_cents
