# Finance Bot (personal)

Telegram bot for personal finance tracking (multiple accounts, expense/income/transfer, reports, history, daily report).

## Setup
1) Create `.env` from `.env.example` and put `BOT_TOKEN`.
2) Install deps:
   - `pip install -r requirements.txt`
3) Run:
   - `python main.py`

## Notes
- SQLite database stored at `data/bot.db`.
- Default timezone: Asia/Aqtobe (override in .env).
