-- AI Chat message limits: track usage per month + extra purchased messages
ALTER TABLE settings ADD COLUMN ai_chat_used INTEGER NOT NULL DEFAULT 0;
ALTER TABLE settings ADD COLUMN ai_chat_month TEXT;
ALTER TABLE settings ADD COLUMN ai_chat_extra INTEGER NOT NULL DEFAULT 0;
