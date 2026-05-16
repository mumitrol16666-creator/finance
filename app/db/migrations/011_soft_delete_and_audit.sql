-- Soft-delete for transactions + audit trail.
-- Backwards-compatible: existing rows keep deleted_at = NULL.

ALTER TABLE transactions ADD COLUMN deleted_at TEXT NULL;

CREATE INDEX IF NOT EXISTS idx_tx_user_ts_live
  ON transactions(user_id, ts)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_tx_user_id_live
  ON transactions(user_id, id)
  WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS tx_audit (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     INTEGER NOT NULL,
  tx_id       INTEGER NOT NULL,
  action      TEXT    NOT NULL,
  at          TEXT    NOT NULL,
  related_id  INTEGER NULL,
  payload     TEXT    NULL
);

CREATE INDEX IF NOT EXISTS idx_tx_audit_user_at
  ON tx_audit(user_id, at DESC);

CREATE INDEX IF NOT EXISTS idx_tx_audit_tx
  ON tx_audit(tx_id);
