from database.engine import get_db
from database.models import Base
from sqlalchemy import text

def update_db():
    db = next(get_db())
    try:
        # Sprawdź czy kolumna istnieje
        try:
            db.execute(text("SELECT vat_warning_threshold FROM company_config LIMIT 1"))
            print("Kolumna vat_warning_threshold już istnieje.")
        except Exception:
            print("Dodawanie kolumny vat_warning_threshold...")
            db.execute(text("ALTER TABLE company_config ADD COLUMN vat_warning_threshold INTEGER DEFAULT 180000"))
            db.commit()
            print("Dodano kolumnę.")

    except Exception as e:
        print(f"Błąd migracji: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    update_db()
