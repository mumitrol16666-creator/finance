import sqlite3
import os

DB_PATH = r'c:\FinanceBot\data\bot.db'

def inspect_db():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: DB file not found at {DB_PATH}")
        return

    print(f"Found database file at {DB_PATH}")
    print(f"File size: {os.path.getsize(DB_PATH)} bytes")
    print("-" * 60)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get list of all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row['name'] for row in cursor.fetchall()]

    print(f"Total tables found: {len(tables)}")
    print(f"Tables: {', '.join(tables)}")
    print("-" * 60)

    for table in tables:
        print(f"Table: {table}")
        
        # Get column info
        cursor.execute(f"PRAGMA table_info({table});")
        columns = cursor.fetchall()
        
        # Get row count
        cursor.execute(f"SELECT COUNT(*) as count FROM {table};")
        row_count = cursor.fetchone()['count']
        
        print(f"  Rows: {row_count}")
        print("  Columns:")
        for col in columns:
            col_id = col['cid']
            name = col['name']
            col_type = col['type']
            not_null = "NOT NULL" if col['notnull'] else "NULL"
            default_val = f"DEFAULT {col['dflt_value']}" if col['dflt_value'] is not None else ""
            pk = "PRIMARY KEY" if col['pk'] else ""
            
            constraints = " ".join(filter(None, [not_null, default_val, pk]))
            print(f"    - {name} ({col_type}) {constraints}")
        print("-" * 60)

    conn.close()

if __name__ == '__main__':
    inspect_db()
