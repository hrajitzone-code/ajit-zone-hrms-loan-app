import sqlite3
import os

db_path = os.path.abspath('c:/Users/Sakshi/OneDrive/Documents/My Projects/ajit_zone_loan_app/instance/loan_system.db')

def migrate_users_permissions():
    print(f"Connecting to SQLite database: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Add permissions column if missing
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN permissions TEXT;")
        print("[MIGRATED] Added 'permissions' column to 'users' table.")
    except sqlite3.OperationalError as e:
        print(f"[SKIP] 'permissions' column in 'users': {e}")

    # 2. Add is_primary_superadmin column if missing
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN is_primary_superadmin BOOLEAN DEFAULT 0;")
        print("[MIGRATED] Added 'is_primary_superadmin' column to 'users' table.")
    except sqlite3.OperationalError as e:
        print(f"[SKIP] 'is_primary_superadmin' column in 'users': {e}")

    conn.commit()
    conn.close()
    print("[SUCCESS] Users schema migration completed.")

if __name__ == '__main__':
    migrate_users_permissions()
