from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RawTxn:
    source: str
    source_file: str
    source_txn_id: str
    occurred_at: str
    direction: str
    amount_cents: int
    signed_cents: int
    currency: str
    account_hint: str
    raw_category: str
    category: str
    counterparty: str
    description: str
    payment_method: str
    status: str
    balance_after_cents: int | None
    raw_json: dict[str, Any]
