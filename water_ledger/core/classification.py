from __future__ import annotations

from water_ledger.config import classification_config, keyword_list
from water_ledger.core.utils import norm_text


def classify(source: str, raw_category: str, counterparty: str, description: str, direction: str) -> str:
    text = f"{raw_category} {counterparty} {description}"
    cfg = classification_config()
    if any(k in text for k in keyword_list(cfg.get("transfer_keywords"))):
        return "内部转账/理财"
    if direction not in {"支出", "收入"}:
        if any(k in text for k in keyword_list(cfg.get("neutral_transfer_keywords"))):
            return "内部转账/理财"
        return "不计收支"
    if direction == "收入":
        if any(k in text for k in keyword_list(cfg.get("refund_keywords"))):
            return "退款返现"
        if any(k in text for k in keyword_list(cfg.get("salary_keywords"))):
            return "工资收入"
        return "其他收入"
    housing_keys = keyword_list(cfg.get("housing_keywords"))
    housing_counterparties = set(keyword_list(cfg.get("housing_counterparties")))
    if any(k in text for k in housing_keys) or counterparty in housing_counterparties:
        return "居住缴费"
    if "押金" in text:
        return "其他支出"
    for rule in cfg.get("expense_rules") or []:
        category = norm_text(rule.get("category"))
        keys = keyword_list(rule.get("keywords"))
        if any(key.lower() in text.lower() for key in keys):
            return category
    return raw_category if raw_category and raw_category not in {"其他", "/"} else "其他支出"
