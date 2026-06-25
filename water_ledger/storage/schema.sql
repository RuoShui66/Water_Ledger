PRAGMA foreign_keys = ON;

DROP VIEW IF EXISTS v_monthly_cashflow;
DROP VIEW IF EXISTS v_asset_curve;
DROP VIEW IF EXISTS v_net_worth_latest;
DROP TABLE IF EXISTS duplicate_links;
DROP TABLE IF EXISTS ledger_transactions;
DROP TABLE IF EXISTS imported_transactions;
DROP TABLE IF EXISTS asset_snapshots;
DROP TABLE IF EXISTS category_overrides;
DROP TABLE IF EXISTS category_rules;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS accounts;
DROP TABLE IF EXISTS source_files;

CREATE TABLE source_files (
  id INTEGER PRIMARY KEY,
  filename TEXT NOT NULL UNIQUE,
  source TEXT NOT NULL,
  imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  sha1 TEXT NOT NULL,
  row_count INTEGER NOT NULL DEFAULT 0,
  note TEXT
);

CREATE TABLE accounts (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  institution TEXT NOT NULL,
  account_type TEXT NOT NULL,
  currency TEXT NOT NULL DEFAULT 'CNY',
  account_no_mask TEXT,
  include_in_net_worth INTEGER NOT NULL DEFAULT 1,
  manual_balance_cents INTEGER,
  manual_balance_at TEXT,
  note TEXT
);

CREATE TABLE categories (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  parent_name TEXT,
  cashflow_type TEXT NOT NULL CHECK (cashflow_type IN ('income','expense','transfer','neutral'))
);

CREATE TABLE imported_transactions (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL CHECK (source IN ('wechat','alipay','boc','manual')),
  source_file_id INTEGER NOT NULL REFERENCES source_files(id),
  source_txn_id TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  direction TEXT NOT NULL,
  amount_cents INTEGER NOT NULL,
  signed_cents INTEGER NOT NULL,
  currency TEXT NOT NULL DEFAULT 'CNY',
  account_hint TEXT,
  raw_category TEXT,
  category TEXT,
  counterparty TEXT,
  description TEXT,
  payment_method TEXT,
  status TEXT,
  balance_after_cents INTEGER,
  fingerprint TEXT NOT NULL,
  raw_json TEXT NOT NULL,
  UNIQUE (source, source_txn_id)
);

CREATE TABLE ledger_transactions (
  id INTEGER PRIMARY KEY,
  imported_transaction_id INTEGER NOT NULL UNIQUE REFERENCES imported_transactions(id),
  account_id INTEGER REFERENCES accounts(id),
  occurred_at TEXT NOT NULL,
  direction TEXT NOT NULL,
  amount_cents INTEGER NOT NULL,
  signed_cents INTEGER NOT NULL,
  currency TEXT NOT NULL DEFAULT 'CNY',
  category TEXT NOT NULL,
  counterparty TEXT,
  description TEXT,
  source TEXT NOT NULL,
  payment_method TEXT,
  status TEXT,
  is_duplicate INTEGER NOT NULL DEFAULT 0,
  duplicate_of_ledger_id INTEGER REFERENCES ledger_transactions(id),
  duplicate_reason TEXT,
  include_in_cashflow INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE duplicate_links (
  id INTEGER PRIMARY KEY,
  duplicate_ledger_id INTEGER NOT NULL UNIQUE REFERENCES ledger_transactions(id),
  primary_ledger_id INTEGER NOT NULL REFERENCES ledger_transactions(id),
  confidence REAL NOT NULL,
  reason TEXT NOT NULL
);

CREATE TABLE asset_snapshots (
  id INTEGER PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES accounts(id),
  snapshot_at TEXT NOT NULL,
  balance_cents INTEGER NOT NULL,
  source TEXT NOT NULL,
  imported_transaction_id INTEGER REFERENCES imported_transactions(id),
  UNIQUE (account_id, snapshot_at, source)
);

CREATE TABLE category_overrides (
  id INTEGER PRIMARY KEY,
  ledger_transaction_id INTEGER NOT NULL UNIQUE REFERENCES ledger_transactions(id),
  category TEXT NOT NULL,
  note TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE category_rules (
  id INTEGER PRIMARY KEY,
  pattern TEXT NOT NULL,
  field TEXT NOT NULL DEFAULT 'description',
  category TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 100,
  enabled INTEGER NOT NULL DEFAULT 1
);

CREATE VIEW v_monthly_cashflow AS
SELECT
  substr(occurred_at, 1, 7) AS month,
  SUM(CASE WHEN direction='收入' AND include_in_cashflow=1 THEN amount_cents ELSE 0 END) / 100.0 AS income,
  SUM(CASE WHEN direction='支出' AND include_in_cashflow=1 THEN amount_cents ELSE 0 END) / 100.0 AS expense,
  SUM(CASE WHEN include_in_cashflow=1 THEN signed_cents ELSE 0 END) / 100.0 AS net_cashflow
FROM ledger_transactions
WHERE is_duplicate = 0
GROUP BY substr(occurred_at, 1, 7);

CREATE VIEW v_asset_curve AS
SELECT
  a.name AS account_name,
  date(s.snapshot_at) AS snapshot_date,
  MAX(s.snapshot_at) AS snapshot_at,
  (SELECT s2.balance_cents / 100.0
     FROM asset_snapshots s2
    WHERE s2.account_id=s.account_id AND date(s2.snapshot_at)=date(s.snapshot_at)
    ORDER BY s2.snapshot_at DESC LIMIT 1) AS balance
FROM asset_snapshots s
JOIN accounts a ON a.id=s.account_id
GROUP BY a.name, date(s.snapshot_at);

CREATE VIEW v_net_worth_latest AS
WITH latest AS (
  SELECT account_id, MAX(snapshot_at) AS snapshot_at
  FROM asset_snapshots
  GROUP BY account_id
)
SELECT
  SUM(CASE WHEN a.include_in_net_worth=1 THEN COALESCE(s.balance_cents, a.manual_balance_cents, 0) ELSE 0 END) / 100.0 AS net_worth_known,
  MAX(COALESCE(s.snapshot_at, a.manual_balance_at)) AS as_of
FROM accounts a
LEFT JOIN latest l ON l.account_id=a.id
LEFT JOIN asset_snapshots s ON s.account_id=l.account_id AND s.snapshot_at=l.snapshot_at;
