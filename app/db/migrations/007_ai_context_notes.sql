CREATE TABLE IF NOT EXISTS ai_context_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    note_type TEXT NOT NULL,
    period_kind TEXT NOT NULL DEFAULT 'month',
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ai_context_notes_user_type_period
ON ai_context_notes(user_id, note_type, period_kind, id DESC);
