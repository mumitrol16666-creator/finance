import sqlite3
conn = sqlite3.connect(r'c:\FinanceBot\data\bot.db')
cur = conn.cursor()
cur.execute("SELECT sql FROM sqlite_master WHERE name='transactions'")
print(cur.fetchone()[0])
