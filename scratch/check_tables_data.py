import sqlite3

conn = sqlite3.connect("data/bot.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get users
cursor.execute("SELECT user_id, mode, full_access FROM users WHERE full_access=1 LIMIT 5")
users = [dict(r) for r in cursor.fetchall()]
print("Active full access users:", users)

# Get budgets for one user if any
for u in users:
    uid = u["user_id"]
    cursor.execute("SELECT b.*, c.name as category_name, c.emoji FROM budgets b JOIN categories c ON b.category_id=c.id WHERE b.user_id=?", (uid,))
    b_rows = [dict(r) for r in cursor.fetchall()]
    if b_rows:
        print(f"\nBudgets for user {uid}:", b_rows)
        break

# Get debts for one user if any
for u in users:
    uid = u["user_id"]
    cursor.execute("SELECT * FROM debts WHERE user_id=? AND is_active=1", (uid,))
    d_rows = [dict(r) for r in cursor.fetchall()]
    if d_rows:
        print(f"\nActive Debts for user {uid}:", d_rows)
        break

# Get accounts for one user if any
for u in users:
    uid = u["user_id"]
    cursor.execute("SELECT * FROM accounts WHERE user_id=? AND is_archived=0", (uid,))
    a_rows = [dict(r) for r in cursor.fetchall()]
    if a_rows:
        print(f"\nActive Accounts for user {uid}:", a_rows)
        break

conn.close()
