from database.engine import get_db
from database.models import Invoice, InvoiceType

def clean_tax_settlements():
    print("Rozpoczynam usuwanie rozrachunków podatkowych (PPE)...")
    db = next(get_db())
    try:
        # Usuwamy faktury/rozrachunki o numerze zaczynającym się od "PPE/"
        # Oraz te typu PODATEK (jeśli jakieś powstały)
        
        # 1. Po numerze
        query_ppe = db.query(Invoice).filter(Invoice.number.like("PPE/%"))
        count_ppe = query_ppe.count()
        if count_ppe > 0:
            print(f"Znaleziono {count_ppe} rozrachunków PPE po numerze. Usuwanie...")
            query_ppe.delete(synchronize_session=False)
            
        # 2. Po typie (bezpiecznik)
        # Note: InvoiceType.PODATEK might throw error if DB doesn't know it yet depending on driver, 
        # but SQLAlchemy usually handles enum as string in SQLite.
        try:
            query_type = db.query(Invoice).filter(Invoice.type == InvoiceType.PODATEK)
            count_type = query_type.count()
            if count_type > 0:
                print(f"Znaleziono {count_type} rozrachunków typu PODATEK. Usuwanie...")
                query_type.delete(synchronize_session=False)
        except Exception as e:
            print(f"Pominieto usuwanie po typie (może nie istnieć): {e}")

        db.commit()
        print("Zakończono sukcesem.")
        
    except Exception as e:
        db.rollback()
        print(f"Błąd podczas usuwania: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    clean_tax_settlements()
