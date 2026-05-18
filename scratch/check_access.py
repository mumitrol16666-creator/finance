import sqlite3
import os
from datetime import datetime

def check_access(db_path):
    if not os.path.exists(db_path):
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        now = datetime.now().isoformat()
        
        cur.execute("SELECT user_id, full_access, full_access_until FROM users")
        rows = cur.fetchall()
        for row in rows:
            uid, is_full, until = row
            access_type = "Full" if is_full else "Free"
            
            if until:
                status = "ACTIVE" if until > now else "EXPIRED"
                print(f"UserID: {uid} | Mode: {access_type} | Until: {until} | Status: {status}")
            else:
                if is_full:
                    print(f"UserID: {uid} | Mode: Full | Until: FOREVER")
                else:
                    print(f"UserID: {uid} | Mode: Free | Until: -")
        
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_access('C:/FinanceBot/data/bot.db')
