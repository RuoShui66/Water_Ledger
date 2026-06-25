from __future__ import annotations

import json
import sqlite3
from typing import Any

from water_ledger.core.assets import (
    backfill_manual_balance_history,
    import_longbridge_asset_history,
    rebuild_alipay_wealth_estimates,
    rebuild_borrowing_account_estimates,
    rebuild_own_untracked_asset_estimates,
    rebuild_wallet_balance_estimates,
)
from water_ledger.core.dedupe import dedupe
from water_ledger.core.refunds import mark_refund_offsets
from water_ledger.core.reports import sync_categories, write_summary
from water_ledger.paths import DB_PATH
from water_ledger.storage.database import init_db, insert_rows, load_all


def rebuild_database() -> dict[str, Any]:
    DB_PATH.parent.mkdir(exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    account_ids = init_db(conn)
    rows = load_all()
    insert_rows(conn, rows, account_ids)
    import_longbridge_asset_history(conn, account_ids)
    dedupe(conn)
    refund_offset_pairs = mark_refund_offsets(conn)
    backfill_manual_balance_history(conn)
    rebuild_own_untracked_asset_estimates(conn, account_ids)
    rebuild_borrowing_account_estimates(conn, account_ids)
    rebuild_wallet_balance_estimates(conn)
    rebuild_alipay_wealth_estimates(conn)
    sync_categories(conn)
    write_summary(conn)
    conn.commit()
    stats = conn.execute(
        """SELECT COUNT(*) AS ledger_rows,
                  SUM(CASE WHEN is_duplicate=1 THEN 1 ELSE 0 END) AS duplicate_rows,
                  MIN(occurred_at) AS min_time,
                  MAX(occurred_at) AS max_time
             FROM ledger_transactions"""
    ).fetchone()
    latest = conn.execute("SELECT net_worth_known, as_of FROM v_net_worth_latest").fetchone()
    result = {
        "db": str(DB_PATH),
        "ledger_rows": stats["ledger_rows"],
        "duplicate_rows": stats["duplicate_rows"],
        "refund_offset_pairs": refund_offset_pairs,
        "min_time": stats["min_time"],
        "max_time": stats["max_time"],
        "known_net_worth": latest["net_worth_known"],
        "net_worth_as_of": latest["as_of"],
    }
    conn.close()
    return result


def main() -> None:
    print(json.dumps(rebuild_database(), ensure_ascii=False, indent=2))
