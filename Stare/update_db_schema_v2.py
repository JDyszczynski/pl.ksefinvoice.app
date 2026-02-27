import sqlite3
import os

DB_PATH = "ksef_invoice.db"

def update_db():
    if not os.path.exists(DB_PATH):
        print("Baza danych nie istnieje.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if columns exist
    cursor.execute("PRAGMA table_info(company_config)")
    columns = [info[1] for info in cursor.fetchall()]
    
    new_columns = {
        "krs": "TEXT",
        "bdo": "TEXT",
        "share_capital": "TEXT",
        "court_info": "TEXT"
    }

    for col, dtype in new_columns.items():
        if col not in columns:
            print(f"Dodawanie kolumny {col} do company_config...")
            try:
                cursor.execute(f"ALTER TABLE company_config ADD COLUMN {col} {dtype}")
                print(f"Dodano {col}.")
            except Exception as e:
                print(f"Błąd przy dodawaniu {col}: {e}")
        else:
            print(f"Kolumna {col} już istnieje.")

    conn.commit()
    conn.close()
    print("Aktualizacja schematu bazy zakończona.")

if __name__ == "__main__":
    update_db()
