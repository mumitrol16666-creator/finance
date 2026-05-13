CREATE TABLE IF NOT EXISTS recurring_expenses (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id          INTEGER NOT NULL,
  title            TEXT    NOT NULL,
  amount           INTEGER NOT NULL,
  category_id      INTEGER NOT NULL,
  account_id       INTEGER NOT NULL,
  day_of_month     INTEGER NOT NULL,
  comment          TEXT,
  next_run_date    TEXT    NOT NULL,
  last_paid_at     TEXT,
  is_archived      INTEGER NOT NULL DEFAULT 0,
  created_at       TEXT    NOT NULL,
  updated_at       TEXT    NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
  FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE RESTRICT,
  FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_recurring_expenses_user_arch ON recurring_expenses(user_id, is_archived, next_run_date);
