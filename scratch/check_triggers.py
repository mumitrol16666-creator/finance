import sqlite3

def main():
    conn = sqlite3.connect(r'c:\FinanceBot\data\bot.db')
    cur = conn.cursor()
    cur.execute("SELECT name, tbl_name, sql FROM sqlite_master WHERE type='trigger'")
    rows = cur.fetchall()
    print("Triggers in database:")
    for row in rows:
        print(f"Name: {row[0]} | Table: {row[1]}")
        print("SQL:")
        print(row[2])
        print("-" * 50)

if __name__ == '__main__':
    main()
