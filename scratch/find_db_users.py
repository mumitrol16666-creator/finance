import glob
import sqlite3
import os

def check_db(db_path):
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if cur.fetchone():
            cur.execute("SELECT * FROM users WHERE user_id = 8092822438")
            row = cur.fetchone()
            if row:
                print(f"Found in {db_path}:")
                for k in row.keys():
                    print(f"  {k}: {row[k]}")
            else:
                print(f"Table 'users' exists in {db_path}, but user 8092822438 not found")
        else:
            print(f"No 'users' table in {db_path}")
        conn.close()
    except Exception as e:
        print(f"Error checking {db_path}: {e}")

for f in glob.glob("**/*.db", recursive=True) + glob.glob("**/*.sqlite", recursive=True) + glob.glob("*.db") + glob.glob("*.sqlite"):
    if os.path.isfile(f) and ".venv" not in f:
        check_db(f)
