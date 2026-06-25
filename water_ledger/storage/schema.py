from __future__ import annotations

from water_ledger.paths import SCHEMA_PATH


def load_schema() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")
