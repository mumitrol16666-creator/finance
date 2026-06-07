import sqlite3

def main():
    conn = sqlite3.connect(r'c:\FinanceBot\Copy of data\bot.db')
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(users)")
    cols = cur.fetchall()
    print("Columns in old users table:")
    for col in cols:
        print(f" - {col[1]} ({col[2]})")

if __name__ == '__main__':
    main()
