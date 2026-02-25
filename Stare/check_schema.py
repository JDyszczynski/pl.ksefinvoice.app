import sqlite3

DB_PATH = "ksef_invoice.db"

def check_schema():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(company_config)")
    columns = cursor.fetchall()
    print("Columns in company_config:")
    for col in columns:
        print(f"- {col[1]} ({col[2]})")
        
    print("\nSelect Test:")
    try:
        cursor.execute("SELECT bdo_number FROM company_config")
        print("Select bdo_number success.")
    except Exception as e:
        print(f"Select bdo_number failed: {e}")
        
    conn.close()

if __name__ == "__main__":
    check_schema()