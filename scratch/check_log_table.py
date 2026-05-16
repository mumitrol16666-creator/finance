import sqlite3
import os

DB_PATH = r'c:\FinanceBot\data\bot.db'

def check_table():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='debt_reminder_log'")
    res = cur.fetchone()
    print(f"Table exists: {res}")
    conn.close()

if __name__ == "__main__":
    check_table()
