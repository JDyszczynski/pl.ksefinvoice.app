import os
import sys
# Ensure we can import from parent/current directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from database.engine import get_db

def migrate_signing_certs():
    print("Migracja bazy danych: Dodawanie kolumn dla Certyfikatu Podpisu Weryfikacyjnego...")
    
    db = next(get_db())
    conn = db.bind.connect()
    
    # List of new columns to add
    # (Column Name, SQL Type)
    new_columns = [
        ("ksef_signing_cert_content", "BLOB"),
        ("ksef_signing_private_key_content", "BLOB"),
        ("ksef_signing_private_key_pass", "VARCHAR(255)"),
        ("ksef_signing_cert_content_test", "BLOB"),
        ("ksef_signing_private_key_content_test", "BLOB"),
        ("ksef_signing_private_key_pass_test", "VARCHAR(255)")
    ]
    
    # Check existing columns using PRAGMA (SQLite specific)
    # Generic SQL check is harder without reflection, but let's assume SQLite for this project context
    # or handle "duplicate column" error gracefully.
    
    try:
        # Commit implied by DDL in many engines, but let's be safe with transaction
        trans = conn.begin()
        
        for col_name, col_type in new_columns:
            try:
                sql = text(f"ALTER TABLE company_config ADD COLUMN {col_name} {col_type}")
                conn.execute(sql)
                print(f"  + Dodano kolumnę: {col_name}")
            except Exception as e:
                # If column exists, it throws error (e.g. "duplicate column name")
                if "duplicate column" in str(e).lower():
                    print(f"  - Kolumna {col_name} już istnieje.")
                else:
                    print(f"  ! Błąd dodawania {col_name}: {e}")
        
        trans.commit()
        print("Migracja zakończona pomyślnie.")
        
    except Exception as e:
        print(f"Błąd ogólny migracji: {e}")
    finally:
        conn.close()
        db.close()

if __name__ == "__main__":
    migrate_signing_certs()
