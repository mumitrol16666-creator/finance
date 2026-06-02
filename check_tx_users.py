import sqlite3
conn = sqlite3.connect(r'c:\FinanceBot\data\bot.db')
cur = conn.cursor()
cur.execute("SELECT user_id, COUNT(*) FROM transactions GROUP BY user_id")
print("Transactions by user:")
print(cur.fetchall())

cur.execute("SELECT user_id, COUNT(*) FROM login_codes GROUP BY user_id")
print("\nLogin codes by user:")
print(cur.fetchall())
