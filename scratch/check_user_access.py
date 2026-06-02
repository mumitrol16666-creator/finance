import sqlite3

def check_user():
    conn = sqlite3.connect("data/bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = 6856090314")
    row = cursor.fetchone()
    if row:
        print("User row:", row)
    else:
        print("User not found in database!")
    conn.close()

if __name__ == "__main__":
    check_user()
