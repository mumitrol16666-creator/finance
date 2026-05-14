-- Add full_access_until column to track when paid access expires
ALTER TABLE users ADD COLUMN full_access_until TEXT;
