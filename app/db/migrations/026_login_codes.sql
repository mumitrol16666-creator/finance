-- Create login_codes table to store 6-digit authentication codes for the mobile app
CREATE TABLE IF NOT EXISTS login_codes (
  code TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  expires_at TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_login_codes_user ON login_codes(user_id);
