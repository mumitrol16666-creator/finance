import sqlite3

def main():
    conn = sqlite3.connect('data/bot.db')
    cursor = conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
    interesting = {
        "rules",
        "expected_events",
        "full_access_payments",
        "user_free_trial",
        "export_logs",
        "sent_keyboards"
    }
    for name, sql in cursor.fetchall():
        if name in interesting:
            print(f"Table: {name}")
            print(sql)
            print("-" * 50)
    conn.close()

if __name__ == '__main__':
    main()
