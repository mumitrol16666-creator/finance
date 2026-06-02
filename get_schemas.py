import sqlite3
conn = sqlite3.connect(r'c:\FinanceBot\data\bot.db')
cur = conn.cursor()
cur.execute("SELECT sql FROM sqlite_master WHERE type='table'")
for row in cur.fetchall():
    try:
        sql = row[0]
        if sql:
            print(sql.encode('ascii', 'ignore').decode('ascii'))
    except:
        pass
