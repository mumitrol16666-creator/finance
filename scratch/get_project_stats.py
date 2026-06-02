import sqlite3
import os

def get_db_stats():
    db_path = "data/bot.db"
    if not os.path.exists(db_path):
        print(f"DB not found at {db_path}")
        return {}
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]
    
    stats = {"tables_count": len(tables), "tables": tables}
    
    def count_rows(table_name):
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            return cursor.fetchone()[0]
        except Exception:
            return 0

    # Users
    stats["total_users"] = count_rows("users")
    
    # Premium users (full_access = 1)
    try:
        cursor.execute("SELECT COUNT(*) FROM users WHERE full_access = 1")
        stats["premium_users"] = cursor.fetchone()[0]
    except Exception:
        stats["premium_users"] = 0
        
    # Transactions
    stats["total_tx"] = count_rows("transactions")
    # Active transactions
    try:
        cursor.execute("SELECT COUNT(*) FROM transactions WHERE deleted_at IS NULL")
        stats["active_tx"] = cursor.fetchone()[0]
    except Exception:
        stats["active_tx"] = 0
        
    # Accounts
    stats["total_accounts"] = count_rows("accounts")
    # Categories
    stats["total_categories"] = count_rows("categories")
    # Budgets
    stats["total_budgets"] = count_rows("budgets")
    # Liabilities
    stats["total_liabilities"] = count_rows("liabilities")
    # Recurring
    stats["total_recurring_expenses"] = count_rows("recurring_expenses")
    stats["total_recurring_incomes"] = count_rows("recurring_incomes")
    stats["total_planned"] = count_rows("planned_transactions")
    
    conn.close()
    return stats

def get_codebase_stats():
    py_files = 0
    total_loc = 0
    
    for root, dirs, files in os.walk("app"):
        if "__pycache__" in root:
            continue
        for f in files:
            if f.endswith(".py"):
                py_files += 1
                path = os.path.join(root, f)
                try:
                    with open(path, "r", encoding="utf-8") as file:
                        total_loc += len(file.readlines())
                except Exception:
                    pass
                    
    return {"py_files": py_files, "total_loc": total_loc}

if __name__ == "__main__":
    db = get_db_stats()
    code = get_codebase_stats()
    
    print("--- PROJECT STATS ---")
    print(f"Total Python Files: {code['py_files']}")
    print(f"Total Lines of Code (LOC): {code['total_loc']}")
    print(f"Database Tables ({db.get('tables_count', 0)}): {db.get('tables')}")
    print(f"Total Registered Users: {db.get('total_users')}")
    print(f"Premium Users: {db.get('premium_users')}")
    print(f"Total Transactions: {db.get('total_tx')} (Active: {db.get('active_tx')})")
    print(f"Total Accounts: {db.get('total_accounts')}")
    print(f"Total Categories: {db.get('total_categories')}")
    print(f"Total Budget Limits: {db.get('total_budgets')}")
    print(f"Total Liabilities/Debts: {db.get('total_liabilities')}")
    print(f"Total Recurring Expenses: {db.get('total_recurring_expenses')}")
    print(f"Total Recurring Incomes: {db.get('total_recurring_incomes')}")
    print(f"Total Planned Transactions: {db.get('total_planned')}")
