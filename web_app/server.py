#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import time
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from water_ledger.config import ledger_title


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = APP_ROOT / "static"
PRIVATE_ROOT = Path(os.environ.get("WATER_LEDGER_PRIVATE_DIR", ROOT / "private"))
DB_PATH = Path(os.environ.get("WATER_LEDGER_DB_PATH", PRIVATE_ROOT / "data" / "water_ledger.sqlite"))
USD_TO_CNY_FALLBACK_RATE = 6.764984440535787
FX_CACHE_SECONDS = 300
_FX_CACHE: dict[str, float] = {"rate": USD_TO_CNY_FALLBACK_RATE, "ts": 0}
LOCAL_TZ = ZoneInfo("Asia/Shanghai")

ACCOUNT_GROUPS = {
    "bank_card": {"group": "银行卡", "icon": "●"},
    "wallet": {"group": "互联网钱包", "icon": "◆"},
    "brokerage": {"group": "券商账户", "icon": "▲", "usd": True},
    "investment": {"group": "投资理财", "icon": "◆"},
    "other_asset": {"group": "其他资产", "icon": "●"},
    "liability": {"group": "负债", "icon": "▽", "debt": True},
}


def account_group_meta(account: dict, balance: float | None = None) -> dict:
    account_type = str(account.get("account_type") or "").strip()
    meta = dict(ACCOUNT_GROUPS.get(account_type) or ACCOUNT_GROUPS["other_asset"])
    if balance is not None and balance < 0:
        meta = dict(ACCOUNT_GROUPS["liability"])
    currency = str(account.get("currency") or "CNY").upper()
    if currency == "USD":
        meta["usd"] = True
    return meta


def money_expr(column: str) -> str:
    return f"round({column} / 100.0, 2)"


def current_local_day() -> str:
    return datetime.now(LOCAL_TZ).date().isoformat()


def current_usd_to_cny_rate() -> float:
    now = time.time()
    if now - _FX_CACHE["ts"] < FX_CACHE_SECONDS:
        return _FX_CACHE["rate"]
    try:
        proc = subprocess.run(
            ["longbridge", "exchange-rate", "--format", "json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=6,
        )
        data = json.loads(proc.stdout)
        exchanges = data.get("exchanges") or []
        cnh = next(
            (
                item
                for item in exchanges
                if item.get("base_currency") == "USD" and item.get("other_currency") == "CNH"
            ),
            None,
        )
        cny = next(
            (
                item
                for item in exchanges
                if item.get("base_currency") == "USD" and item.get("other_currency") == "CNY"
            ),
            None,
        )
        rate_row = cnh or cny
        average_rate = float(rate_row["average_rate"])
        rate = 1 / average_rate
    except Exception:
        rate = _FX_CACHE["rate"] or USD_TO_CNY_FALLBACK_RATE
    _FX_CACHE.update({"rate": rate, "ts": now})
    return rate


def to_cny(amount: float, currency: str, usd_to_cny_rate: float) -> float:
    if currency == "USD":
        return amount * usd_to_cny_rate
    return amount


def asset_curve_points(usd_to_cny_rate: float, limit: int | None = None) -> list[dict]:
    account_curves = asset_account_curve_points(usd_to_cny_rate)
    totals_by_date: dict[str, float] = {}
    for account in account_curves:
        for point in account["series"]:
            totals_by_date[point["date"]] = totals_by_date.get(point["date"], 0) + point["v"]
    points = [
        {"date": date, "balance": round(balance, 2)}
        for date, balance in sorted(totals_by_date.items())
    ]
    return points[-limit:] if limit else points


def asset_account_curve_points(usd_to_cny_rate: float) -> list[dict]:
    account_rows = rows(
        """
        select id, name, institution, account_type, currency,
               manual_balance_cents / 100.0 as manual_balance
        from accounts
        order by id
        """
    )
    snapshots = rows(
        """
        select account_id, date(snapshot_at) as date, snapshot_at,
               balance_cents / 100.0 as balance,
               source
        from asset_snapshots
        order by date(snapshot_at), snapshot_at
        """
    )
    dates = sorted({snap["date"] for snap in snapshots})
    snapshot_by_account: dict[int, list[dict]] = {}
    for snap in snapshots:
        snapshot_by_account.setdefault(snap["account_id"], []).append(snap)

    latest_by_account: dict[int, float] = {}
    for account in account_rows:
        account_id = account["id"]
        latest_by_account[account_id] = 0
    index_by_account = {account["id"]: 0 for account in account_rows}
    series_by_account: dict[int, list[dict]] = {account["id"]: [] for account in account_rows}
    for date in dates:
        for account in account_rows:
            account_id = account["id"]
            account_snaps = snapshot_by_account.get(account_id, [])
            index = index_by_account[account_id]
            while index < len(account_snaps) and account_snaps[index]["date"] <= date:
                latest_by_account[account_id] = account_snaps[index]["balance"] or 0
                index += 1
            index_by_account[account_id] = index
            if not account_snaps:
                latest_by_account[account_id] = account.get("manual_balance") or 0
            series_by_account[account_id].append(
                {
                    "date": date,
                    "m": date[2:7].replace("-", "/"),
                    "v": round(
                        to_cny(latest_by_account[account_id], account.get("currency") or "CNY", usd_to_cny_rate)
                    ),
                }
            )

    return [
        {
            "id": account["id"],
            "name": account["name"],
            "institution": account.get("institution") or "",
            "accountType": account.get("account_type") or "",
            "currency": account.get("currency") or "CNY",
            "series": series_by_account[account["id"]],
        }
        for account in account_rows
    ]


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def rows(sql: str, params: tuple = ()) -> list[dict]:
    with connect() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def one(sql: str, params: tuple = ()) -> dict:
    with connect() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else {}


def current_month() -> str:
    result = one(
        """
        select substr(max(occurred_at), 1, 7) as month
        from ledger_transactions
        where is_duplicate = 0
        """
    )
    return result.get("month") or ""


def api_summary() -> dict:
    month = current_month()
    summary = one(
        """
        select
          count(*) as transaction_count,
          min(occurred_at) as first_transaction_at,
          max(occurred_at) as last_transaction_at
        from ledger_transactions
        where is_duplicate = 0
        """
    )
    month_cashflow = one(
        """
        select month, income, expense, net_cashflow
        from v_monthly_cashflow
        where month = ?
        """,
        (month,),
    )
    asset_accounts = api_assets()["accounts"]
    net_worth = {
        "net_worth_known": round(
            sum(
                account.get("balance") or 0
                for account in asset_accounts
                if account.get("include_in_net_worth")
            ),
            2,
        ),
        "as_of": max((account.get("snapshot_at") or "" for account in asset_accounts), default=""),
    }
    source_counts = rows(
        """
        select source, count(*) as count
        from ledger_transactions
        group by source
        order by source
        """
    )
    recent = rows(
        """
        select id, occurred_at, direction, category, counterparty, description,
               source, payment_method, status, is_duplicate,
               """ + money_expr("amount_cents") + """ as amount,
               """ + money_expr("signed_cents") + """ as signed_amount
        from ledger_transactions
        where is_duplicate = 0
        order by occurred_at desc, id desc
        limit 12
        """
    )
    categories = rows(
        """
        select category,
               count(*) as count,
               """ + money_expr("sum(amount_cents)") + """ as amount
        from ledger_transactions
        where direction = '支出'
          and is_duplicate = 0
          and include_in_cashflow = 1
          and substr(occurred_at, 1, 7) = ?
        group by category
        order by sum(amount_cents) desc
        limit 8
        """,
        (month,),
    )
    monthly = rows(
        """
        select month, income, expense, net_cashflow
        from v_monthly_cashflow
        order by month desc
        limit 12
        """
    )
    return {
        "summary": summary,
        "current_month": month,
        "month_cashflow": month_cashflow,
        "net_worth": net_worth,
        "source_counts": source_counts,
        "recent": recent,
        "categories": categories,
        "monthly": list(reversed(monthly)),
    }


def api_transactions(query: dict[str, list[str]]) -> dict:
    limit = min(int(query.get("limit", ["80"])[0]), 300)
    source = query.get("source", ["all"])[0]
    category = query.get("category", ["all"])[0]
    direction = query.get("direction", ["all"])[0]
    month = query.get("month", [""])[0]
    search = query.get("search", [""])[0].strip()
    show_duplicates = query.get("duplicates", ["0"])[0] == "1"

    clauses = []
    params: list[str] = []
    if not show_duplicates:
        clauses.append("is_duplicate = 0")
    if source != "all":
        clauses.append("source = ?")
        params.append(source)
    if category != "all":
        clauses.append("category = ?")
        params.append(category)
    if direction != "all":
        clauses.append("direction = ?")
        params.append(direction)
    if month:
        clauses.append("substr(occurred_at, 1, 7) = ?")
        params.append(month)
    if search:
        clauses.append("(counterparty like ? or description like ? or payment_method like ?)")
        like = f"%{search}%"
        params.extend([like, like, like])
    where = " where " + " and ".join(clauses) if clauses else ""

    items = rows(
        """
        select id, occurred_at, direction, category, counterparty, description,
               source, payment_method, status, is_duplicate, duplicate_reason,
               include_in_cashflow,
               """ + money_expr("amount_cents") + """ as amount,
               """ + money_expr("signed_cents") + """ as signed_amount
        from ledger_transactions
        """
        + where
        + """
        order by lt.occurred_at desc, lt.id desc
        limit ?
        """,
        tuple(params + [limit]),
    )
    total = one("select count(*) as total from ledger_transactions" + where, tuple(params))
    return {"items": items, "total": total.get("total", 0)}


def api_filters() -> dict:
    return {
        "months": [
            item["month"]
            for item in rows(
                """
                select substr(occurred_at, 1, 7) as month
                from ledger_transactions
                group by substr(occurred_at, 1, 7)
                order by month desc
                """
            )
        ],
        "categories": [
            item["category"]
            for item in rows(
                """
                select category
                from ledger_transactions
                group by category
                order by category
                """
            )
        ],
        "sources": ["alipay", "boc", "wechat"],
    }


def api_assets() -> dict:
    usd_to_cny_rate = current_usd_to_cny_rate()
    accounts = rows(
        """
        with latest as (
          select account_id, max(snapshot_at) as snapshot_at
          from asset_snapshots
          group by account_id
        )
        select a.id, a.name, a.institution, a.account_type, a.currency,
               a.account_no_mask, a.include_in_net_worth,
               coalesce(s.balance_cents, a.manual_balance_cents, 0) / 100.0 as balance,
               coalesce(s.snapshot_at, a.manual_balance_at) as snapshot_at,
               coalesce(s.source, case when a.manual_balance_cents is not null then 'manual' end) as source
        from accounts a
        left join latest l on l.account_id = a.id
        left join asset_snapshots s on s.account_id = l.account_id and s.snapshot_at = l.snapshot_at
        order by balance desc, a.id
        """
    )
    for account in accounts:
        native_balance = account.get("balance") or 0
        native_currency = account.get("currency") or "CNY"
        account["native_balance"] = round(native_balance, 2)
        account["native_currency"] = native_currency
        account["fx_rate"] = usd_to_cny_rate if native_currency == "USD" else 1
        account["balance"] = round(to_cny(native_balance, native_currency, usd_to_cny_rate), 2)

    return {"accounts": accounts, "curve": asset_curve_points(usd_to_cny_rate, limit=90)}


def api_report() -> dict:
    month = current_month()
    totals = one("select * from v_monthly_cashflow where month = ?", (month,))
    top_expenses = rows(
        """
        select category,
               count(*) as count,
               round(sum(amount_cents) / 100.0, 2) as amount,
               round(avg(amount_cents) / 100.0, 2) as avg_amount
        from ledger_transactions
        where direction = '支出'
          and is_duplicate = 0
          and include_in_cashflow = 1
          and substr(occurred_at, 1, 7) = ?
        group by category
        order by sum(amount_cents) desc
        limit 12
        """,
        (month,),
    )
    merchants = rows(
        """
        select coalesce(nullif(counterparty, ''), nullif(description, ''), '未命名') as name,
               count(*) as count,
               round(sum(amount_cents) / 100.0, 2) as amount
        from ledger_transactions
        where direction = '支出'
          and is_duplicate = 0
          and include_in_cashflow = 1
          and substr(occurred_at, 1, 7) = ?
        group by coalesce(nullif(counterparty, ''), nullif(description, ''), '未命名')
        having count(*) >= 2
        order by sum(amount_cents) desc
        limit 10
        """,
        (month,),
    )
    subscriptions = rows(
        """
        select occurred_at, category, counterparty, description, source,
               round(amount_cents / 100.0, 2) as amount
        from ledger_transactions
        where direction = '支出'
          and is_duplicate = 0
          and include_in_cashflow = 1
          and (category = '数码订阅' or description like '%订阅%' or counterparty like '%Apple%' or description like '%OpenAI%')
        order by occurred_at desc
        limit 20
        """
    )
    monthly = rows(
        """
        select month, income, expense, net_cashflow
        from v_monthly_cashflow
        order by month desc
        limit 18
        """
    )
    return {
        "month": month,
        "totals": totals,
        "top_expenses": top_expenses,
        "merchants": merchants,
        "subscriptions": subscriptions,
        "monthly": list(reversed(monthly)),
    }


def compact_category(category: str, direction: str = "") -> str:
    if direction == "收入":
        return "收入"
    mapping = {
        "餐饮": "餐饮",
        "交通出行": "交通",
        "购物日用": "购物",
        "服饰装扮": "购物",
        "生活服务": "购物",
        "商户消费": "购物",
        "POS消费": "购物",
        "扫二维码付款": "购物",
        "网上快捷支付": "购物",
        "居住缴费": "居住",
        "通信话费": "通信",
        "数码订阅": "应用软件",
        "数码电器": "数码",
        "娱乐休闲": "娱乐",
        "文化休闲": "娱乐",
        "运动户外": "娱乐",
        "医疗健康": "医疗",
        "公益人情": "人情",
        "群收款": "人情",
        "学习办公": "学习",
        "内部转账/理财": "转账",
        "不计收支": "转账",
        "自助取款": "转账",
        "退款返现": "转账",
    }
    return mapping.get(category, "其他")


def clean_bill_text(value: str | None) -> str:
    text = (value or "").strip()
    text = re.sub(r"-{3,}", " ", text)
    text = text.replace("CHAG EE", "CHAGEE").replace("CHA GEE", "CHAGEE")
    text = text.replace("京 东", "京东")
    text = re.sub(r"-?\d{14,}$", "", text)
    text = re.sub(r"\b[A-Z]?\d{6,}[A-Z]?\b", " ", text)
    text = text.replace("银企对接", " ").replace("美 团", "美团")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def bill_detail(counterparty: str | None, description: str | None, source: str | None = None) -> str:
    merchant = clean_bill_text(counterparty)
    desc = clean_bill_text(description)
    if not desc or desc == merchant:
        return ""
    if merchant and desc.startswith(merchant):
        desc = desc[len(merchant):].strip(" -·")
    if desc.startswith("财付通 "):
        desc = desc.removeprefix("财付通 ").strip()
    if desc and desc != merchant:
        return desc[:80]
    return ""


def bill_display(counterparty: str | None, description: str | None, source: str | None = None) -> tuple[str, str]:
    merchant = clean_bill_text(counterparty) or clean_bill_text(description) or "未命名流水"
    detail = bill_detail(counterparty, description, source)
    if detail and any(k in merchant for k in ["美团支付", "支付宝", "财付通"]):
        title = detail.removeprefix("美团App ").strip() or detail
        return title, merchant
    return merchant, detail


def account_source_key(account_id: int | None, account_name: str | None = "") -> str:
    name = account_name or ""
    if "微信" in name:
        return "wx"
    if "支付宝" in name:
        return "ali"
    return "boc"


def design_transactions(limit: int | None = None, month: str | None = None) -> list[dict]:
    where = ["is_duplicate = 0"]
    params: list[str | int] = []
    if month:
        where.append("substr(occurred_at, 1, 7) = ?")
        params.append(month)
    sql = (
        """
        select lt.id, lt.account_id, a.name as account_name, lt.occurred_at, lt.direction,
               lt.category, lt.counterparty, lt.description, lt.source, lt.payment_method,
               lt.signed_cents, lt.include_in_cashflow, lt.duplicate_reason
        from ledger_transactions
        lt left join accounts a on a.id = lt.account_id
        where """
        + " and ".join(where)
        + """
        order by lt.occurred_at desc, lt.id desc
        """
    )
    if limit:
        sql += " limit ?"
        params.append(limit)
    source_map = {"alipay": "ali", "wechat": "wx", "boc": "boc"}
    out = []
    for row in rows(sql, tuple(params)):
        merchant, detail = bill_display(row.get("counterparty"), row.get("description"), row.get("source"))
        amount = round((row["signed_cents"] or 0) / 100.0, 2)
        channel = source_map.get(row["source"], "boc")
        out.append(
            {
                "id": row["id"],
                "date": row["occurred_at"],
                "day": row["occurred_at"][:10],
                "time": row["occurred_at"][11:16],
                "accountId": row["account_id"],
                "src": account_source_key(row["account_id"], row.get("account_name")),
                "channel": channel,
                "accountName": row.get("account_name") or "",
                "paymentMethod": row.get("payment_method") or "",
                "merchant": merchant,
                "detail": detail,
                "searchText": " ".join(part for part in [merchant, detail, row.get("description"), row["category"], row.get("payment_method")] if part),
                "cat": compact_category(row["category"], row["direction"]),
                "amount": amount,
                "countable": bool(row["include_in_cashflow"]),
                "refundReason": row.get("duplicate_reason") if not row["include_in_cashflow"] else None,
            }
        )
    return out


def asset_design_payload(accounts: list[dict]) -> dict:
    usd_to_cny_rate = current_usd_to_cny_rate()
    account_rows = rows(
        """
        select id, name, institution, account_type, currency, include_in_net_worth,
               manual_balance_cents / 100.0 as manual_balance,
               manual_balance_at
        from accounts
        order by id
        """
    )
    snapshots = rows(
        """
        select account_id, date(snapshot_at) as date, snapshot_at,
               balance_cents / 100.0 as balance
        from asset_snapshots
        order by date(snapshot_at), snapshot_at
        """
    )
    dates = [
        row["date"]
        for row in rows(
            """
            select day as date from (
              select date(occurred_at) as day from ledger_transactions
              union
              select snapshot_date as day from v_asset_curve
            )
            order by day desc
            """
        )
    ]
    txns = rows(
        """
        select lt.id, lt.account_id, lt.occurred_at, lt.source, lt.direction, lt.category,
               lt.counterparty, lt.description, lt.payment_method, lt.signed_cents,
               coalesce(it.balance_after_cents, dit.balance_after_cents, snap.balance_cents) / 100.0 as balance_after
        from ledger_transactions lt
        left join imported_transactions it on it.id = lt.imported_transaction_id
        left join duplicate_links dl on dl.primary_ledger_id = lt.id
        left join ledger_transactions dlt on dlt.id = dl.duplicate_ledger_id
        left join imported_transactions dit on dit.id = dlt.imported_transaction_id
        left join asset_snapshots snap on snap.account_id = lt.account_id and snap.snapshot_at = lt.occurred_at
        where lt.is_duplicate = 0
        order by lt.occurred_at desc, lt.id desc
        """
    )

    snapshot_by_account: dict[int, list[dict]] = {}
    for snap in snapshots:
        snapshot_by_account.setdefault(snap["account_id"], []).append(snap)

    latest_account = {account["id"]: account for account in accounts}
    account_meta = []
    account_name_by_id = {account["id"]: account["name"] for account in account_rows}
    for account in account_rows:
        meta = account_group_meta(account)
        latest = latest_account.get(account["id"], {})
        account_meta.append(
            {
                "id": account["id"],
                "itemId": f"acct-{account['id']}",
                "name": account["name"],
                "sub": account.get("institution") or account.get("account_type") or "",
                "group": meta["group"],
                "icon": meta["icon"],
                "debt": bool(meta.get("debt")),
                "usd": bool(meta.get("usd")),
                "currency": account["currency"],
                "latest": round(latest.get("balance") or account.get("manual_balance") or 0, 2),
                "manualBalance": round(account.get("manual_balance") or 0, 2),
            }
        )

    history: dict[str, dict[str, float]] = {}
    for date in dates:
        day_balances: dict[str, float] = {}
        for account in account_rows:
            snaps = snapshot_by_account.get(account["id"], [])
            balance = None
            for snap in snaps:
                if snap["date"] <= date:
                    balance = snap["balance"]
                else:
                    break
            if balance is None:
                balance = (account.get("manual_balance") or 0) if not snaps else 0
            day_balances[str(account["id"])] = round(
                to_cny(balance or 0, account.get("currency") or "CNY", usd_to_cny_rate), 2
            )
        history[date] = day_balances

    txns_by_day_account: dict[str, list[dict]] = {}
    txns_by_account: dict[str, list[dict]] = {}
    source_map = {"alipay": "ali", "wechat": "wx", "boc": "boc"}

    def add_asset_txn(item: dict) -> None:
        key = f"{item['day']}|{item['accountId']}"
        txns_by_day_account.setdefault(key, []).append(item)
        txns_by_account.setdefault(str(item["accountId"]), []).append(item)

    for txn in txns:
        merchant, detail = bill_display(txn.get("counterparty"), txn.get("description"), txn.get("source"))
        channel = source_map.get(txn["source"], "boc")
        item = {
            "id": txn["id"],
            "accountId": txn["account_id"],
            "date": txn["occurred_at"],
            "day": txn["occurred_at"][:10],
            "time": txn["occurred_at"][11:16],
            "src": account_source_key(txn["account_id"], account_name_by_id.get(txn["account_id"], "")),
            "channel": channel,
            "merchant": merchant,
            "detail": detail,
            "paymentMethod": txn.get("payment_method") or "",
            "cat": compact_category(txn["category"], txn["direction"]),
            "amount": round((txn["signed_cents"] or 0) / 100.0, 2),
            "balanceAfter": round(txn["balance_after"], 2) if txn["balance_after"] is not None else None,
        }
        add_asset_txn(item)

    synthetic_sources = {"borrowing_estimate", "own_untracked_estimate"}
    for account_id, snaps in snapshot_by_account.items():
        account_name = account_name_by_id.get(account_id, "")
        if str(account_id) in txns_by_account:
            continue
        synthetic_snaps = [
            snap for snap in snaps
            if snap.get("source") in synthetic_sources
        ]
        previous = 0.0
        for snap in synthetic_snaps:
            balance = float(snap.get("balance") or 0)
            delta = round(balance - previous, 2)
            previous = balance
            if abs(delta) < 0.005:
                continue
            item = {
                "id": f"snap-{account_id}-{snap['snapshot_at']}",
                "accountId": account_id,
                "date": snap["snapshot_at"],
                "day": snap["date"],
                "time": snap["snapshot_at"][11:16],
                "src": account_source_key(account_id, account_name),
                "channel": "manual",
                "merchant": account_name,
                "detail": "估算余额变动",
                "paymentMethod": "",
                "cat": "内部转账",
                "amount": delta,
                "balanceAfter": round(balance, 2),
            }
            add_asset_txn(item)

    for txn_list in txns_by_account.values():
        txn_list.sort(key=lambda item: (item["date"], str(item["id"])), reverse=True)
    for txn_list in txns_by_day_account.values():
        txn_list.sort(key=lambda item: (item["date"], str(item["id"])), reverse=True)

    return {
        "dates": dates,
        "accounts": account_meta,
        "history": history,
        "txnsByDayAccount": txns_by_day_account,
        "txnsByAccount": txns_by_account,
    }


def api_design_data() -> dict:
    month = current_month()
    month_row = one("select * from v_monthly_cashflow where month = ?", (month,))
    assets_payload = api_assets()
    accounts = assets_payload["accounts"]
    usd_to_cny_rate = current_usd_to_cny_rate()
    asset_group_map: dict[str, dict] = {}
    for account in accounts:
        balance = round(account.get("balance") or 0, 2)
        meta = account_group_meta(account, balance)
        group_name = meta["group"]
        group = asset_group_map.setdefault(
            group_name,
            {
                "group": group_name,
                "icon": meta["icon"],
                "usd": bool(meta.get("usd")),
                "debt": bool(meta.get("debt")),
                "items": [],
            },
        )
        item = {
            "id": f"acct-{account['id']}",
            "name": account["name"],
            "sub": account.get("institution") or account.get("account_type") or "",
            "cny": balance,
        }
        if meta.get("usd"):
            item["usd"] = round(account.get("native_balance") or item["cny"] / usd_to_cny_rate, 2)
        group["items"].append(item)

    group_order = ["银行卡", "互联网钱包", "投资理财", "券商账户", "其他资产", "负债"]
    asset_groups = sorted(
        asset_group_map.values(),
        key=lambda group: (group_order.index(group["group"]) if group["group"] in group_order else len(group_order), group["group"]),
    )

    latest_net = sum(
        account.get("balance") or 0
        for account in accounts
        if account.get("include_in_net_worth")
    )
    account_series = asset_account_curve_points(usd_to_cny_rate)
    daily_net_points = asset_curve_points(usd_to_cny_rate)
    nw_series = [
        {
            "date": item["date"],
            "m": item["date"][2:7].replace("-", "/"),
            "v": round(item["balance"] or 0),
        }
        for item in daily_net_points
    ]
    if not nw_series:
        today = current_local_day()
        nw_series = [{"date": today, "m": today[2:7].replace("-", "/"), "v": round(latest_net)}]
    stock_curve_rows = rows(
        """
        select v.snapshot_date as date,
               v.snapshot_at,
               v.balance,
               a.currency
        from v_asset_curve v
        join accounts a on a.name = v.account_name
        where a.account_type = 'brokerage'
           or a.name like '%美股%'
           or a.name like '%股票%'
        order by v.snapshot_date, v.snapshot_at
        """
    )
    stock_latest_by_date: dict[str, float] = {}
    for item in stock_curve_rows:
        converted = to_cny(item.get("balance") or 0, item.get("currency") or "CNY", usd_to_cny_rate)
        stock_latest_by_date[item["date"]] = converted
    stock_series = []
    latest_stock = 0.0
    for item in nw_series:
        latest_stock = stock_latest_by_date.get(item["date"], latest_stock)
        stock_series.append({"date": item["date"], "m": item["m"], "v": round(latest_stock)})

    top_expenses = rows(
        """
        select occurred_at, category, counterparty, description, signed_cents, amount_cents
        from ledger_transactions
        where direction = '支出'
          and is_duplicate = 0
          and include_in_cashflow = 1
          and substr(occurred_at, 1, 7) = ?
        order by amount_cents desc
        limit 3
        """,
        (month,),
    )
    anomalies = [
        {
            "merchant": row.get("counterparty") or row.get("description") or "大额支出",
            "cat": compact_category(row["category"]),
            "amount": round((row["signed_cents"] or 0) / 100.0, 2),
            "note": "本月金额较高，建议复核分类和必要性",
            "date": row["occurred_at"][5:10],
        }
        for row in top_expenses
    ]
    subscription_rows = rows(
        """
        select occurred_at, counterparty, description, source,
               round(amount_cents / 100.0, 2) as amount
        from ledger_transactions
        where direction = '支出'
          and is_duplicate = 0
          and include_in_cashflow = 1
          and substr(occurred_at, 1, 7) = ?
          and (category = '数码订阅' or description like '%订阅%' or counterparty like '%Apple%' or description like '%OpenAI%')
        order by occurred_at desc
        limit 8
        """,
        (month,),
    )
    subscriptions = [
        {
            "name": item.get("counterparty") or item.get("description") or "订阅服务",
            "cycle": "月",
            "cny": round(item["amount"]),
            "next": item["occurred_at"][5:10],
            "flag": item["source"],
        }
        for item in subscription_rows
    ]
    suggestions = [
        {"tag": "现金流", "text": f"{month} 净现金流为 ¥{round(month_row.get('net_cashflow') or 0):,}，可以结合资产页确认是否需要转入理财或预留现金。"},
        {"tag": "分类", "text": "大额的网上快捷支付、商户消费建议继续细分，报告会更接近真实生活场景。"},
        {"tag": "应用软件", "text": "应用软件列表来自云服务、App 扣费和平台服务商户，适合每月快速检查是否还在使用。"},
    ]
    label = f"{month[:4]} 年 {int(month[5:7])} 月" if month else ""
    return {
        "today": current_local_day(),
        "profile": {
            "ledgerTitle": ledger_title(),
        },
        "fx": {"usdToCny": usd_to_cny_rate},
        "assets": asset_groups,
        "assetTimeline": asset_design_payload(accounts),
        "nwSeries": nw_series,
        "stockSeries": stock_series,
        "accountSeries": account_series,
        "month": {
            "label": label,
            "income": round(month_row.get("income") or 0),
            "expense": round(month_row.get("expense") or 0),
        },
        "categories": ["餐饮", "交通", "购物", "居住", "通信", "应用软件", "数码", "娱乐", "医疗", "人情", "学习", "收入", "转账", "其他"],
        "txns": design_transactions(limit=120, month=month),
        "allTxns": design_transactions(limit=7000),
        "anomalies": anomalies,
        "subscriptions": subscriptions,
        "suggestions": suggestions,
    }


API_ROUTES = {
    "/api/summary": api_summary,
    "/api/filters": api_filters,
    "/api/assets": api_assets,
    "/api/report": api_report,
    "/api/design-data": api_design_data,
}


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        if parsed.path in {"/", "/index.html"}:
            return str(STATIC_ROOT / "design" / "index.html")
        return str(STATIC_ROOT / parsed.path.lstrip("/"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/transactions":
                payload = api_transactions(parse_qs(parsed.query))
                self.send_json(payload)
                return
            if parsed.path in API_ROUTES:
                self.send_json(API_ROUTES[parsed.path]())
                return
            super().do_GET()
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=500)

    def send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def run_server(host: str = "127.0.0.1", port: int = 8787) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Water Ledger running at http://{host}:{port}")
    print(f"Using database: {DB_PATH}")
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Water Ledger local browser")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8787, type=int)
    args = parser.parse_args()
    run_server(args.host, args.port)


if __name__ == "__main__":
    main()
