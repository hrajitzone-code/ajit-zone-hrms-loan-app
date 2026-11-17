import sqlite3
import os

db_path = os.path.abspath('c:/Users/Sakshi/OneDrive/Documents/My Projects/ajit_zone_loan_app/instance/loan_system.db')

def direct_sqlite_migrate():
    print(f"Connecting to SQLite database: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    columns_to_add = [
        ("users", "employee_id", "INTEGER REFERENCES employees(id)"),
        ("employees", "joining_date", "DATE"),
        ("employees", "updated_at", "DATETIME"),
        ("loans", "interest_rate", "FLOAT DEFAULT 0.0"),
        ("loans", "processing_fee", "FLOAT DEFAULT 0.0"),
        ("loans", "declaration_accepted", "BOOLEAN DEFAULT 1"),
        ("loans", "disbursement_date", "DATETIME"),
        ("loans", "workflow_status", "VARCHAR(32) DEFAULT 'Submitted'"),
        ("emi_deductions", "deduction_status", "VARCHAR(32) DEFAULT 'Processed'")
    ]

    for table, col_name, col_type in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type};")
            print(f"[MIGRATED] Added '{col_name}' to '{table}'.")
        except sqlite3.OperationalError as e:
            print(f"[SKIP] '{col_name}' in '{table}': {e}")

    conn.commit()
    conn.close()
    print("[SUCCESS] Direct SQLite schema migration completed!")

if __name__ == '__main__':
    direct_sqlite_migrate()
