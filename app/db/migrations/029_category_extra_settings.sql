-- Migration: Add extra settings to categories table
ALTER TABLE categories ADD COLUMN default_account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL;
ALTER TABLE categories ADD COLUMN exclude_from_analytics INTEGER NOT NULL DEFAULT 0;
ALTER TABLE categories ADD COLUMN warn_threshold REAL NOT NULL DEFAULT 0.70;
