-- Add free_exports_used column to track free Excel exports before downgrade shock triggers
ALTER TABLE users ADD COLUMN free_exports_used INTEGER NOT NULL DEFAULT 0;
