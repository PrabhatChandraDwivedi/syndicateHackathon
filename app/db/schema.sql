-- Canonical SQLite schema for ReconcileOS contract (section 3 data model)
-- Tables mirror the entities listed in ARCHITECTURE.md §3

CREATE TABLE FinancialTransaction (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL, -- bank|corporate_card|payment_processor
  account_id TEXT,
  date TEXT,
  amount REAL,
  currency TEXT,
  counterparty_raw TEXT,
  reference_raw TEXT,
  raw_payload TEXT,
  source_file_id TEXT,
  ingested_at TEXT,
  external_id TEXT
);

CREATE TABLE Invoice (
  id TEXT PRIMARY KEY,
  invoice_number TEXT,
  entity_id TEXT,
  counterparty_id TEXT,
  invoice_type TEXT CHECK(invoice_type IN ('sales','purchase')),
  invoice_date TEXT,
  due_date TEXT,
  taxable_amount REAL,
  tax_amount REAL,
  open_amount REAL,
  status TEXT,
  raw_payload TEXT,
  source_file_id TEXT
);

CREATE TABLE Merchant (
  merchant_id TEXT PRIMARY KEY,
  canonical_name TEXT,
  aliases TEXT,
  default_gl_code TEXT
);

CREATE TABLE GSTRecord (
  supplier_gstin TEXT,
  recipient_gstin TEXT,
  invoice_number TEXT,
  invoice_date TEXT,
  taxable_value REAL,
  igst REAL,
  cgst REAL,
  sgst REAL,
  source TEXT,
  raw_payload TEXT
);

CREATE TABLE OpsRecord (
  ops_id TEXT PRIMARY KEY,
  order_ref TEXT,
  date TEXT,
  gross_amount REAL,
  fees REAL,
  net_amount REAL,
  channel TEXT,
  raw_payload TEXT
);

CREATE TABLE ReconciliationCase (
  case_id TEXT PRIMARY KEY,
  workflow TEXT,
  source_ids TEXT,
  candidate_target_ids TEXT,
  status TEXT,
  confidence REAL,
  method TEXT,
  financial_impact REAL,
  evidence TEXT,
  alternatives TEXT,
  exception_type TEXT,
  policy_version TEXT,
  rule_ids_used TEXT,
  neatlogs_trace_id TEXT,
  token_cost_usd REAL,
  latency_ms REAL
);

CREATE TABLE HumanDecision (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id TEXT,
  actor_id TEXT,
  action TEXT,
  final_allocations TEXT,
  comment TEXT,
  created_rule_ids TEXT
);

CREATE TABLE LearnedRule (
  rule_id TEXT PRIMARY KEY,
  rule_type TEXT,
  pattern TEXT,
  target TEXT,
  scope TEXT,
  source_case_id TEXT,
  confidence REAL,
  created_at TEXT,
  last_used_at TEXT,
  use_count INTEGER,
  status TEXT,
  never_auto BOOLEAN
);

CREATE TABLE AuditEvent (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT,
  actor_type TEXT,
  actor_id TEXT,
  case_id TEXT,
  event_type TEXT,
  before_state TEXT,
  after_state TEXT,
  inputs_hash TEXT,
  policy_version TEXT,
  model_version TEXT,
  neatlogs_trace_id TEXT,
  prev_hash TEXT,
  this_hash TEXT
);

CREATE TABLE ActionState (
  idempotency_key TEXT PRIMARY KEY,
  case_id TEXT,
  action_type TEXT,
  status TEXT,
  result TEXT,
  attempts INTEGER
);

CREATE TABLE RunRecord (
  run_id TEXT PRIMARY KEY,
  started_at TEXT,
  policy_version TEXT,
  rule_snapshot_id TEXT,
  source_file_ids TEXT,
  neatlogs_trace_id TEXT,
  metrics_json TEXT
);

/** idempotence and append-only helpers may be added in migrations */
