import sqlite3
con = sqlite3.connect("C:/FinanceBot/data/bot.db")
cur = con.cursor()
cur.execute("PRAGMA table_info(settings)")
print("LOCAL DB SETTINGS COLUMNS:")
for row in cur.fetchall():
    print(row[1])
con.close()
