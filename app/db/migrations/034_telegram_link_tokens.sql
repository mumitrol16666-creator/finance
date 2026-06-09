CREATE TABLE IF NOT EXISTS telegram_link_tokens (
  token TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  purpose TEXT NOT NULL DEFAULT 'premium',
  expires_at TEXT NOT NULL,
  used_at TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_telegram_link_tokens_user
ON telegram_link_tokens(user_id, expires_at);

CREATE TABLE IF NOT EXISTS user_id_aliases (
  old_user_id INTEGER PRIMARY KEY,
  current_user_id INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
