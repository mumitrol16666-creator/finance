import sqlite3

def main():
    conn = sqlite3.connect(r'c:\FinanceBot\Copy of data\bot.db')
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, applied_at FROM migrations ORDER BY applied_at")
        rows = cur.fetchall()
        print("Migrations in old database:")
        for r in rows:
            print(f" - {r[0]} ({r[1]})")
    except sqlite3.OperationalError as e:
        print("Error:", e)

if __name__ == '__main__':
    main()
