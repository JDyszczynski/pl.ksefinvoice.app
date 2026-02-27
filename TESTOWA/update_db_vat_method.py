from sqlalchemy import create_engine, text
from database.models import Base

def upgrade_db():
    engine = create_engine("sqlite:///ksef_invoice.db")
    with engine.connect() as conn:
        try:
            # 1. Sprawdzamy czy kolumna vat_settlement_method istnieje
            conn.execute(text("ALTER TABLE company_config ADD COLUMN vat_settlement_method VARCHAR(20) DEFAULT 'MONTHLY'"))
            print("Dodano kolumnę vat_settlement_method")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("Kolumna vat_settlement_method już istnieje.")
            else:
                print(f"Błąd przy dodawaniu vat_settlement_method: {e}")
        
        conn.commit()

if __name__ == "__main__":
    upgrade_db()
