import sqlite3

conn = sqlite3.connect("data/bot.db")
cursor = conn.cursor()

for table in ["accounts", "budgets", "debts", "recurring_expenses", "recurring_incomes", "planned_transactions"]:
    cursor.execute(f"PRAGMA table_info({table})")
    print(f"\n{table} columns:")
    for row in cursor.fetchall():
        print(f"  {row[1]} ({row[2]})")

conn.close()
