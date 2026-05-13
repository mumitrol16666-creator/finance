CREATE TABLE IF NOT EXISTS debt_reminder_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  debt_id INTEGER NOT NULL,
  reminder_kind TEXT NOT NULL,
  local_date TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(user_id, debt_id, reminder_kind, local_date)
);

CREATE INDEX IF NOT EXISTS idx_debt_reminder_log_user_date ON debt_reminder_log(user_id, local_date);
