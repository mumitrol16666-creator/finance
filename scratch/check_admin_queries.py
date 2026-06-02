import sqlite3

def run_test():
    conn = sqlite3.connect("data/bot.db")
    cursor = conn.cursor()
    
    users_query = """
        SELECT 
            u.user_id, 
            u.full_access, 
            u.created_at,
            s.lang, 
            s.timezone,
            (SELECT COUNT(*) FROM accounts a WHERE a.user_id = u.user_id AND a.is_archived = 0) as accounts_count,
            (SELECT COUNT(*) FROM transactions t WHERE t.user_id = u.user_id AND t.deleted_at IS NULL) as tx_count,
            (SELECT COUNT(*) FROM debts d WHERE d.user_id = u.user_id AND d.closed_at IS NULL) as active_debts
        FROM users u
        LEFT JOIN settings s ON u.user_id = s.user_id
        ORDER BY u.created_at DESC
    """
    
    accounts_query = """
        SELECT 
            a.user_id, 
            a.name, 
            a.balance, 
            a.currency, 
            a.is_saving
        FROM accounts a
        WHERE a.is_archived = 0
        ORDER BY a.user_id, a.name
    """
    
    try:
        print("Testing users_query...")
        cursor.execute(users_query)
        users = cursor.fetchall()
        print(f"Success! Users count: {len(users)}")
        
        print("\nTesting accounts_query...")
        cursor.execute(accounts_query)
        accounts = cursor.fetchall()
        print(f"Success! Accounts count: {len(accounts)}")
        
    except Exception as e:
        print(f"Error during query execution: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_test()
