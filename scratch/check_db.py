import sqlite3
import os

db_files = ["finance.db", "finance_bot.db", "database.sqlite", "data/bot.db"]
for db_file in db_files:
    if os.path.exists(db_file):
        print(f"--- DB: {db_file} ---")
        conn = sqlite3.connect(db_file)
        try:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(users)")
            columns = [row[1] for row in cursor.fetchall()]
            print("Columns in 'users':", columns)
            
            # Check for current_streak, max_streak, last_activity_date
            missing = []
            if "current_streak" not in columns:
                missing.append("current_streak")
            if "max_streak" not in columns:
                missing.append("max_streak")
            if "last_activity_date" not in columns:
                missing.append("last_activity_date")
                
            if missing:
                print(f"Missing columns in {db_file}: {missing}")
                for col in missing:
                    if col in ("current_streak", "max_streak"):
                        cursor.execute(f"ALTER TABLE users ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
                    else:
                        cursor.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
                conn.commit()
                print(f"Added missing columns {missing} to {db_file} successfully!")
            else:
                print(f"All streak columns are already present in {db_file}!")
        except Exception as e:
            print(f"Error for {db_file}: {e}")
        finally:
            conn.close()
