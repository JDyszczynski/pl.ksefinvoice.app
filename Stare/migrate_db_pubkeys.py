import sqlite3
import os

DB_FILE = "ksef_invoice.db"

def migrate():
    if not os.path.exists(DB_FILE):
        print("Baza danych nie istnieje. Zmiany zostaną zaaplikowane przy pierwszym uruchomieniu.")
        return

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        # Check if columns exist
        cursor.execute("PRAGMA table_info(company_config)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "ksef_public_key_prod" not in columns:
            print("Adding ksef_public_key_prod...")
            cursor.execute("ALTER TABLE company_config ADD COLUMN ksef_public_key_prod BLOB")
            
        if "ksef_public_key_test" not in columns:
            print("Adding ksef_public_key_test...")
            cursor.execute("ALTER TABLE company_config ADD COLUMN ksef_public_key_test BLOB")
            
        conn.commit()
        print("Migracja zakończona sukcesem.")
    except Exception as e:
        print(f"Błąd migracji: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
