# FinanceBot 📊

A robust, feature-rich Telegram bot for personal finance tracking, featuring multi-currency accounting, multi-language support (RU, EN, KK), advanced reports, category budgets, debt management, and an AI Financial Consultant powered by GPT-4o-mini.

---

## 🚀 Live Project Statistics

*   **Total Python Files:** 100
*   **Total Lines of Code (LOC):** 32,008
*   **Database Tables:** 26
*   **Registered Users:** 12 (8 Premium)
*   **Logged Transactions:** 392
*   **Total Accounts:** 18

---

## 🛠 Technology Stack & Architecture

*   **Runtime:** Python 3.9+ with `asyncio`
*   **Framework:** `aiogram` (v3) for Telegram Bot API integration
*   **Database:** SQLite in **WAL (Write-Ahead Logging)** mode with `aiosqlite` for asynchronous connections
*   **Scheduler:** `APScheduler` for daily reports, quiet hours, auto-cleanup, and AI coaching evaluations
*   **AI Integration:** OpenAI API (`gpt-4o-mini`) with custom prompt engineering and token budget guards
*   **Export Engine:** `openpyxl` for multi-sheet, beautifully formatted Excel spreadsheets

---

## 🌟 Key Features

1.  **Multi-currency Accounts & Transfers:**
    *   Separate balances for cash, debit cards, savings, and investments.
    *   Transfer funds between accounts with automatic exchange rates.
2.  **Category Budgets & Limits:**
    *   Set monthly spending limits per category.
    *   Automatic warnings if a transaction exceeds category limits.
3.  **Scheduled & Recurring Operations:**
    *   Log upcoming planned transactions or recurring monthly incomes/expenses (e.g. salary, rent, subscriptions).
4.  **Debt & Liability Tracker:**
    *   Record loans (lent or borrowed money) with payment dates, interest, and auto-reminders.
5.  **AI Consultant & Financial Coach:**
    *   Request personal budget audits, anomaly checks, and recommendations.
    *   Token budget guards prevent large history payloads from exhausting API limits.
6.  **Interactive Reports Hub:**
    *   Access daily, weekly, and monthly reports with dynamic category breakdowns and streaks.
    *   relocated XLSX/CSV exporter for easy spreadsheets download.

---

## 🗄 Database Structure (26 Tables)

The database utilizes SQLite configured with `PRAGMA foreign_keys = ON`, `busy_timeout = 10000`, and `synchronous = NORMAL` to avoid concurrency locking.

*   `users` — Core user profiles (streaks, onboarded status, premium access fields).
*   `settings` — Notification frequencies, daily report times, quiet hours, language, and timezone settings.
*   `accounts` — User card/cash accounts with balances, currencies, and archiving.
*   `categories` — Customizable transaction categories with emojis.
*   `transactions` — Ledger of expenses, incomes, and transfers.
*   `budgets` — Spending limits configured per category per month.
*   `debts` — Borrowed/lent records with notification state.
*   `recurring_expenses` & `recurring_incomes` — Schedules for automatic transactions.
*   `planned_transactions` — Single planned future transfers or payments.
*   `ai_profile` & `ai_insights` — AI-generated notes, coaching run logs, and active advice blocks.
*   `sent_keyboards` — Tracks inline keyboards for auto-pruning after 30 minutes.

---

## 📂 Project Structure

```
c:/FinanceBot/
├── app/
│   ├── api/            # API endpoints for web/mobile integration
│   ├── config/         # Environment settings and configuration schemas
│   ├── db/             # Migrations and repository functions (SQL query layers)
│   ├── domain/         # Access rules, money conversions, and AI engines
│   ├── fsm/            # States for onboarding and transaction input
│   ├── handlers/       # Message, command, and callback query routers
│   ├── middlewares/    # FSM escaping, DB sessions, throttling, quiet hours
│   ├── scheduler/      #APScheduler notification ticks and cleanup jobs
│   └── ui/             # Localization files (i18n) and keyboard builders
├── data/               # SQLite database directory (production: /opt/finance-bot/data)
├── main.py             # Entrypoint launching the dispatcher and scheduler
├── requirements.txt    # Application dependencies
└── finance-bot.service # Systemd service unit configuration template
```

---

## 🛠 Setup & Running Locally

1.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
2.  **Environment Configuration:**
    Create a `.env` file in the root directory:
    ```ini
    BOT_TOKEN=your_telegram_bot_token
    DB_PATH=./data/bot.db
    ADMIN_IDS=6856090314
    OPENAI_API_KEY=your_openai_key
    OPENAI_MODEL=gpt-4o-mini
    TIMEZONE=Asia/Aqtobe
    ```
3.  **Run the bot:**
    ```bash
    python main.py
    ```

---

## 🚀 Deployment & CI/CD Workflow

Deployment is fully automated using GitHub Actions (`.github/workflows/deploy.yml`):
1.  On push to `master` branch, the CI pipeline connects to the target server via SSH.
2.  Updates the source code in `/opt/finance-bot`.
3.  Performs safe database and `.env` migrations from older `/root/Finance_bot` folders if detected.
4.  Copies `finance-bot.service` to `/etc/systemd/system/finance-bot.service` and executes `systemctl daemon-reload`.
5.  Restarts the `finance-bot` systemd service unit.
