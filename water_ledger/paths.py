from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = Path(os.environ.get("WATER_LEDGER_PRIVATE_DIR", ROOT / "private"))
DB_PATH = Path(os.environ.get("WATER_LEDGER_DB_PATH", PRIVATE_ROOT / "data" / "water_ledger.sqlite"))
CONFIG_PATH = Path(os.environ.get("WATER_LEDGER_CONFIG", PRIVATE_ROOT / "config.yaml"))
SCHEMA_PATH = ROOT / "water_ledger" / "storage" / "schema.sql"
