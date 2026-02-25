import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure we can import from database package
sys.path.append(os.getcwd())

from database.engine import init_db, DATABASE_URL
from database.models import CompanyConfig, NumberingSetting, User, Contractor

# Helper to capture data
def get_table_data(session, model):
    data = []
    try:
        for item in session.query(model).all():
            # Copy dict excluding internal sqlalchemy state
            d = {k: v for k, v in item.__dict__.items() if not k.startswith('_sa_')}
            data.append(d)
    except Exception:
        pass # Table might not exist or other error
    return data

saved_configs = []
saved_numbering = []
saved_users = []
saved_contractors = []

if os.path.exists("ksef_invoice.db"):
    print("Wykryto istniejącą bazę. Próba zachowania konfiguracji (CompanyConfig, Numbering, Users, Contractors)...")
    try:
        # Create temporary connection to read
        temp_engine = create_engine(DATABASE_URL)
        TempSession = sessionmaker(bind=temp_engine)
        session = TempSession()
        
        try:
            saved_configs = get_table_data(session, CompanyConfig)
            saved_numbering = get_table_data(session, NumberingSetting)
            saved_users = get_table_data(session, User)
            saved_contractors = get_table_data(session, Contractor) # Often valuable to keep
            
            print(f"Zachowano: {len(saved_configs)} config, {len(saved_numbering)} numbering, {len(saved_users)} users, {len(saved_contractors)} contractors.")
        except Exception as e:
            print(f"Błąd podczas odczytu starej konfiguracji: {e}")
        finally:
            session.close()
            temp_engine.dispose()
            
    except Exception as e:
        print(f"Nie udało się połączyć ze starą bazą: {e}")

    try:
        os.remove("ksef_invoice.db")
        print("Usunięto plik starej bazy danych.")
    except PermissionError:
        print("BŁĄD: Nie można usunąć pliku bazy danych. Zamknij aplikację jeśli jest uruchomiona lub zwolnij blokadę pliku.")
        sys.exit(1)
else:
    print("Brak starej bazy danych.")

init_db()
print("Utworzono nową strukturę schemas (Invoice, InvoiceItem itp. z nowymi kolumnami).")

if saved_configs or saved_numbering or saved_users:
    print("Przywracanie konfiguracji...")
    from database.engine import SessionLocal
    session = SessionLocal()
    try:
        for d in saved_configs:
            session.add(CompanyConfig(**d))
        for d in saved_numbering:
            session.add(NumberingSetting(**d))
        for d in saved_users:
            session.add(User(**d))
        for d in saved_contractors:
            session.add(Contractor(**d))
            
        session.commit()
        print("Przywrócono konfigurację i kontrahentów.")
    except Exception as e:
        print(f"Błąd przywracania: {e}")
        session.rollback()
    finally:
        session.close()
