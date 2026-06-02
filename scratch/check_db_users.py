import sqlite3

conn = sqlite3.connect("data/bot.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get users table info
cursor.execute("PRAGMA table_info(users)")
columns = [row[1] for row in cursor.fetchall()]
print("Users columns:", columns)

# Get some users data
cursor.execute("SELECT * FROM users LIMIT 5")
rows = cursor.fetchall()
for i, r in enumerate(rows):
    print(f"Row {i}:", dict(r))

conn.close()
