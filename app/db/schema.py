SCHEMA_SQL = r'''
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  telegram_id       BIGINT UNIQUE,
  username          VARCHAR UNIQUE NOT NULL,
  password_hash     VARCHAR NOT NULL,
  display_name      VARCHAR,
  onboarding_state  VARCHAR,
  created_at        TEXT    NOT NULL,
  onboarded         INTEGER NOT NULL DEFAULT 0,
  current_streak    INTEGER NOT NULL DEFAULT 0,
  max_streak        INTEGER NOT NULL DEFAULT 0,
  last_activity_date TEXT,
  mode              TEXT    NOT NULL DEFAULT 'newbie',
  progress_level    INTEGER NOT NULL DEFAULT 0,
  full_access       INTEGER NOT NULL DEFAULT 0,
  full_access_until TEXT,
  free_exports_used INTEGER NOT NULL DEFAULT 0,
  promo_used        INTEGER NOT NULL DEFAULT 0,
  trial_3d_claimed  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS settings (
  user_id               INTEGER PRIMARY KEY,
  currency              TEXT    NOT NULL DEFAULT 'KZT',
  timezone              TEXT    NOT NULL DEFAULT 'Asia/Aqtobe',
  lang                  TEXT    NOT NULL DEFAULT 'ru',
  daily_report_enabled  INTEGER NOT NULL DEFAULT 0,
  daily_report_time     TEXT    NOT NULL DEFAULT '21:00',
  daily_report_last_sent_date     TEXT,
  daily_report_pre_last_sent_date TEXT,
  note_max_len          INTEGER NOT NULL DEFAULT 80,
  nudge_enabled         INTEGER NOT NULL DEFAULT 0,
  nudge_interval_min    INTEGER NOT NULL DEFAULT 180,
  nudge_last_sent_at    TEXT,
  debts_enabled         INTEGER NOT NULL DEFAULT 1,
  debts_days_before     INTEGER NOT NULL DEFAULT 3,
  budget_cycle_start_day INTEGER NOT NULL DEFAULT 1,
  ai_chat_daily_date    TEXT,
  ai_chat_daily_used    INTEGER NOT NULL DEFAULT 0,
  app_tutorial_completed INTEGER NOT NULL DEFAULT 0,
  created_at            TEXT    NOT NULL,
  updated_at            TEXT    NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS accounts (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id          INTEGER NOT NULL,
  name             TEXT    NOT NULL,
  balance          INTEGER NOT NULL DEFAULT 0,
  starting_balance INTEGER NOT NULL DEFAULT 0,
  currency         TEXT    NOT NULL DEFAULT 'KZT',
  is_saving        INTEGER NOT NULL DEFAULT 0,
  is_archived      INTEGER NOT NULL DEFAULT 0,
  created_at       TEXT    NOT NULL,
  updated_at       TEXT    NOT NULL,
  acc_type         TEXT    NOT NULL DEFAULT 'regular',
  interest_rate    REAL    DEFAULT 0.0,
  accrual_period   TEXT    DEFAULT 'month',
  last_interest_accrued_at TEXT,
  is_business      INTEGER NOT NULL DEFAULT 0,
  UNIQUE(user_id, name),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_accounts_user ON accounts(user_id);

CREATE TABLE IF NOT EXISTS categories (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id          INTEGER NOT NULL,
  name             TEXT    NOT NULL,
  emoji            TEXT,
  kind             TEXT    NOT NULL DEFAULT 'expense',
  is_archived      INTEGER NOT NULL DEFAULT 0,
  created_at       TEXT    NOT NULL,
  updated_at       TEXT    NOT NULL,
  is_business      INTEGER NOT NULL DEFAULT 0,
  UNIQUE(user_id, kind, name),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_categories_user_kind ON categories(user_id, kind);

CREATE TABLE IF NOT EXISTS transactions (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id            INTEGER NOT NULL,
  ts                 TEXT    NOT NULL,
  type               TEXT    NOT NULL,
  amount             INTEGER NOT NULL,
  account_id         INTEGER NOT NULL,
  category_id        INTEGER,
  note               TEXT,
  related_tx_id      INTEGER,
  created_at         TEXT    NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE RESTRICT,
  FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL,
  FOREIGN KEY (related_tx_id) REFERENCES transactions(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_tx_user_ts ON transactions(user_id, ts);
CREATE INDEX IF NOT EXISTS idx_tx_user_type_ts ON transactions(user_id, type, ts);
CREATE INDEX IF NOT EXISTS idx_tx_account_ts ON transactions(account_id, ts);

CREATE TABLE IF NOT EXISTS budgets (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id       INTEGER NOT NULL,
  month         TEXT    NOT NULL,
  category_id   INTEGER NOT NULL,
  limit_amount  INTEGER NOT NULL,
  created_at    TEXT    NOT NULL,
  updated_at    TEXT    NOT NULL,
  UNIQUE(user_id, month, category_id),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_budgets_user_month ON budgets(user_id, month);

CREATE TABLE IF NOT EXISTS daily_stats (
  user_id        INTEGER NOT NULL,
  date           TEXT    NOT NULL,
  income_total   INTEGER NOT NULL DEFAULT 0,
  expense_total  INTEGER NOT NULL DEFAULT 0,
  tx_count       INTEGER NOT NULL DEFAULT 0,
  created_at     TEXT    NOT NULL,
  updated_at     TEXT    NOT NULL,
  PRIMARY KEY (user_id, date),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS debts (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id            INTEGER NOT NULL,
  direction          TEXT    NOT NULL,
  dtype              TEXT    NOT NULL,
  title              TEXT    NOT NULL,
  total_amount       INTEGER,
  remaining_amount   INTEGER,
  payment_amount     INTEGER,
  next_payment_date  TEXT,
  note               TEXT,
  status             TEXT    NOT NULL DEFAULT 'active',
  is_active          INTEGER NOT NULL DEFAULT 1,
  created_at         TEXT    NOT NULL,
  updated_at         TEXT    NOT NULL,
  closed_at          TEXT,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_debts_user_active ON debts(user_id, is_active, direction);
CREATE INDEX IF NOT EXISTS idx_debts_user_due ON debts(user_id, next_payment_date);

CREATE TABLE IF NOT EXISTS debt_payments (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  debt_id       INTEGER NOT NULL,
  user_id       INTEGER NOT NULL,
  tx_id         INTEGER,
  account_id    INTEGER,
  amount        INTEGER NOT NULL,
  payment_date  TEXT    NOT NULL,
  comment       TEXT,
  created_at    TEXT    NOT NULL,
  FOREIGN KEY (debt_id) REFERENCES debts(id) ON DELETE CASCADE,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (tx_id) REFERENCES transactions(id) ON DELETE SET NULL,
  FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_debt_payments_debt ON debt_payments(debt_id, payment_date DESC);
CREATE INDEX IF NOT EXISTS idx_debt_payments_user ON debt_payments(user_id, payment_date DESC);

CREATE TABLE IF NOT EXISTS debt_notify_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  debt_id INTEGER NOT NULL,
  remind_kind TEXT NOT NULL,
  remind_date TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(debt_id, remind_kind, remind_date),
  FOREIGN KEY (debt_id) REFERENCES debts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS exchange_rates (
  currency TEXT PRIMARY KEY,
  rate_to_usd REAL NOT NULL,
  updated_at TEXT NOT NULL
);
'''
