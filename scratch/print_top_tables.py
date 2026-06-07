import sqlite3
conn = sqlite3.connect(r'c:\FinanceBot\data\bot.db')
cur = conn.cursor()
tables = ['users', 'accounts', 'categories', 'transactions', 'settings']
for table in tables:
    cur.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}'")
    row = cur.fetchone()
    if row:
        print(f"Table: {table}")
        print(row[0])
        print("-" * 50)
conn.close()
