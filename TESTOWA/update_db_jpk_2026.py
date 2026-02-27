import sqlite3
import os

DB_FILE = "ksef_invoice.db"

def migrate():
    if not os.path.exists(DB_FILE):
        print(f"Baza danych {DB_FILE} nie istnieje. Tworzenie nowej struktury przy uruchomieniu aplikacji.")
        return

    print(f"Rozpoczynam aktualizację bazy danych {DB_FILE} dla JPK 2026...")
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Lista kolumn do dodania w formacie (nazwa_kolumny, typ_danych)
    new_columns = [
        ("is_natural_person", "BOOLEAN DEFAULT 0"),
        ("first_name", "VARCHAR(100)"),
        ("last_name", "VARCHAR(100)"),
        ("date_of_birth", "DATETIME"),
        ("tax_office_code", "VARCHAR(10)"),
        ("email", "VARCHAR(100)"),
        ("phone_number", "VARCHAR(20)")
    ]
    
    table_name = "company_config"
    
    # Sprawdź istniejące kolumny
    cursor.execute(f"PRAGMA table_info({table_name})")
    existing_columns = [info[1] for info in cursor.fetchall()]
    
    for col_name, col_type in new_columns:
        if col_name not in existing_columns:
            try:
                print(f"Dodawanie kolumny {col_name}...")
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError as e:
                print(f"Błąd przy dodawaniu kolumny {col_name}: {e}")
        else:
            print(f"Kolumna {col_name} już istnieje.")

    conn.commit()
    conn.close()
    print("Aktualizacja zakończona pomyślnie.")

if __name__ == "__main__":
    migrate()
