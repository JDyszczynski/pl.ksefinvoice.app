from sqlalchemy import create_engine, text

def upgrade_contractors_is_person():
    engine = create_engine("sqlite:///ksef_invoice.db")
    with engine.connect() as conn:
        try:
            conn.execute(text("SELECT is_person FROM contractors LIMIT 1"))
            print("Kolumna is_person już istnieje.")
        except Exception:
            print("Dodawanie kolumny is_person do contractors...")
            try:
                conn.execute(text("ALTER TABLE contractors ADD COLUMN is_person BOOLEAN DEFAULT 0"))
                print("Dodano kolumnę.")
            except Exception as e:
                print(f"Błąd migracji: {e}")

if __name__ == "__main__":
    upgrade_contractors_is_person()
