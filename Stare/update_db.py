import sqlite3
import os

DB_PATH = "ksef_invoice.db"

def add_column():
    if not os.path.exists(DB_PATH):
        print("Brak pliku bazy danych.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("PRAGMA table_info(invoices)")
        cols = [c[1] for c in cursor.fetchall()]
        
        if "upo_datum" not in cols:
            print("Dodaję kolumnę upo_datum...")
            cursor.execute("ALTER TABLE invoices ADD COLUMN upo_datum DATETIME")
            conn.commit()
            print("Gotowe.")
        else:
            print("Kolumna upo_datum już istnieje.")
            
    except Exception as e:
        print(f"Błąd: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    add_column()
