-- Add budget_cycle_start_day to settings table
ALTER TABLE settings ADD COLUMN budget_cycle_start_day INTEGER NOT NULL DEFAULT 1;
