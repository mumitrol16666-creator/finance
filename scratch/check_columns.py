import sqlite3

def find_user_id_tables():
    conn = sqlite3.connect("data/bot.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    
    user_id_tables = []
    for table in tables:
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [col[1] for col in cursor.fetchall()]
        if 'user_id' in columns:
            user_id_tables.append(table)
            
    print("Tables with user_id:", user_id_tables)
    conn.close()

if __name__ == "__main__":
    find_user_id_tables()
