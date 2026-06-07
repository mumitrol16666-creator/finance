import sqlite3

def main():
    conn = sqlite3.connect(r'c:\FinanceBot\data\bot.db')
    cur = conn.cursor()
    cur.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
    rows = cur.fetchall()
    print("Tables in database:")
    for row in rows:
        print(f"Table name: {row[0]}")
        print("SQL:")
        print(row[1])
        print("=" * 60)

if __name__ == '__main__':
    main()
