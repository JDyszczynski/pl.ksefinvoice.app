import sqlite3
import os

DB_PATH = "ksef_invoice.db"

def add_cash_method_column():
    if not os.path.exists(DB_PATH):
        print("Brak pliku bazy danych.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check company_config table
        print("Sprawdzam tabelę company_config...")
        cursor.execute("PRAGMA table_info(company_config)")
        cols = [c[1] for c in cursor.fetchall()]
        
        if "is_cash_method" not in cols:
            print("Dodaję kolumnę is_cash_method do company_config...")
            # SQLite supports ADD COLUMN with default value constraint
            # Mapping Boolean to INTEGER (0=False, 1=True) - default False (0)
            cursor.execute("ALTER TABLE company_config ADD COLUMN is_cash_method INTEGER DEFAULT 0")
            conn.commit()
            print("Kolumna is_cash_method została dodana (domyślnie False).")
        else:
            print("Kolumna is_cash_method już istnieje.")

    except Exception as e:
        print(f"Błąd podczas aktualizacji bazy danych: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    add_cash_method_column()
