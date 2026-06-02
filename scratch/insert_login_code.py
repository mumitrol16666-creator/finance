import sqlite3
from datetime import datetime, timedelta, timezone

def main():
    conn = sqlite3.connect("C:/FinanceBot/data/bot.db")
    expires_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO login_codes (code, user_id, expires_at) VALUES (?, ?, ?)",
        ("111111", 938030819, expires_at)
    )
    conn.commit()
    conn.close()
    print("Test login code 111111 successfully created for user_id 938030819")

if __name__ == '__main__':
    main()
