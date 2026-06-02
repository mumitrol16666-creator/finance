import sqlite3

conn = sqlite3.connect(r'c:\FinanceBot\data\bot.db')
cur = conn.cursor()

# Check users
cur.execute("SELECT user_id, mode, progress_level FROM users")
users = cur.fetchall()
print("USERS:", users)

# Check recurring expenses
cur.execute("SELECT * FROM recurring_expenses")
exp = cur.fetchall()
print("RECURRING EXP:", exp)

# Check recurring incomes
cur.execute("SELECT * FROM recurring_incomes")
inc = cur.fetchall()
print("RECURRING INC:", inc)

# Check debts
cur.execute("SELECT * FROM debts")
debts = cur.fetchall()
print("DEBTS:", debts)

# Check planned
cur.execute("SELECT * FROM planned_transactions")
planned = cur.fetchall()
print("PLANNED:", planned)

conn.close()
