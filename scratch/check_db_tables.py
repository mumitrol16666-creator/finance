import sqlite3

conn = sqlite3.connect("data/bot.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get list of all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cursor.fetchall()]
print("Tables in database:", tables)

# Print schema/rows for budgets
if "budgets" in tables:
    cursor.execute("SELECT * FROM budgets LIMIT 2")
    print("\nBudgets sample:", [dict(r) for r in cursor.fetchall()])

# Print schema/rows for debts
if "debts" in tables:
    cursor.execute("SELECT * FROM debts LIMIT 2")
    print("\nDebts sample:", [dict(r) for r in cursor.fetchall()])

# Print schema/rows for recurring_expenses
if "recurring_expenses" in tables:
    cursor.execute("SELECT * FROM recurring_expenses LIMIT 2")
    print("\nRecurring Expenses sample:", [dict(r) for r in cursor.fetchall()])

# Print schema/rows for accounts
if "accounts" in tables:
    cursor.execute("SELECT * FROM accounts LIMIT 2")
    print("\nAccounts sample:", [dict(r) for r in cursor.fetchall()])

conn.close()
