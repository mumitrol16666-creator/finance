-- AI Reports limits: track extra purchased reports
ALTER TABLE settings ADD COLUMN ai_reports_extra INTEGER NOT NULL DEFAULT 0;
