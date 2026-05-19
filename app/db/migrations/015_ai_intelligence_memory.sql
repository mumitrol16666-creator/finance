-- Таблица общего профиля пользователя и его стадии финансовой грамотности
CREATE TABLE IF NOT EXISTS ai_profile (
    user_id INTEGER PRIMARY KEY,
    user_stage TEXT NOT NULL DEFAULT 'chaotic', -- chaotic, stabilizing, budgeting, investing
    behavioral_summary TEXT, -- Описание пользователя (например: "Склонен к вечерней доставке еды")
    discipline_score INTEGER DEFAULT 100, -- Индекс дисциплины от 0 до 100
    preferred_budgeting_type TEXT DEFAULT 'weekly', -- weekly, monthly, 50/30/20
    updated_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Таблица инсайтов/паттернов, обнаруженных аналитическим движком
CREATE TABLE IF NOT EXISTS ai_insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    insight_key TEXT NOT NULL, -- e.g. 'night_orders', 'food_limit_streak'
    insight_text TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0, -- Уверенность 0.0 - 1.0
    detected_at TEXT NOT NULL,
    expires_at TEXT, -- Срок годности инсайта
    status TEXT NOT NULL DEFAULT 'active', -- active, archived, ignored
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Лог выданных рекомендаций для оценки их эффективности
CREATE TABLE IF NOT EXISTS ai_recommendations_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    recommendation_type TEXT NOT NULL, -- e.g. 'cut_delivery'
    message_text TEXT NOT NULL,
    target_metric_name TEXT, -- e.g. 'delivery_spend_weekly'
    target_metric_start_value REAL,
    target_metric_goal_value REAL,
    status TEXT NOT NULL DEFAULT 'sent', -- sent, accepted, ignored, succeeded, failed
    created_at TEXT NOT NULL,
    evaluated_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
