import logging
import sqlalchemy
from sqlalchemy import inspect, text
from database.engine import get_db, engine
from database.models import CompanyConfig, Invoice, InvoiceItem, User, VatRate, LumpSumRate

logger = logging.getLogger(__name__)

def check_and_migrate_db():
    """
    Sprawdza strukturę bazy danych i dodaje brakujące kolumny.
    Uruchamiane przy starcie aplikacji.
    """
    logger.info("Sprawdzanie struktury bazy danych...")
    
    inspector = inspect(engine)
    
    # 1. Sprawdzenie tabel
    existing_tables = inspector.get_table_names()
    
    # Lista tabel do migracji (Nazwa tabeli w DB, Klasa Modelu)
    tables_to_check = [
        ("company_config", CompanyConfig),
        ("invoices", Invoice),
        ("invoice_items", InvoiceItem),
        ("users", User),
        ("vat_rates", VatRate),
        ("lump_sum_rates", LumpSumRate)
    ]
    
    with engine.connect() as conn:
        for table_name, model_class in tables_to_check:
            if table_name not in existing_tables:
                # Tabela nie istnieje - init_db() ją utworzy, ale jeśli init_db działa tylko create_all,
                # to nie ma problemu. Tutaj skupiamy się na ALTER
                continue
                
            # Pobierz istniejące kolumny w bazie
            existing_columns = [col['name'] for col in inspector.get_columns(table_name)]
            
            # Pobierz oczekiwane kolumny z modelu SQLAlchemy
            # model_class.__table__.columns jest słownikiem kolumn
            for column in model_class.__table__.columns:
                col_name = column.name
                col_type = column.type
                
                if col_name not in existing_columns:
                    logger.info(f"Wykryto brakującą kolumnę: {table_name}.{col_name}. Dodawanie...")
                    
                    # Mapowanie typów SQLAlchemy na typy SQLite
                    # (To jest uproszczone, dla SQLite zazwyczaj wystarczy TEXT, INTEGER, REAL, BLOB)
                    sqlite_type = "TEXT" # Domyślnie
                    
                    if isinstance(col_type, sqlalchemy.Integer):
                        sqlite_type = "INTEGER"
                    elif isinstance(col_type, sqlalchemy.Float):
                        sqlite_type = "REAL"
                    elif isinstance(col_type, sqlalchemy.Boolean):
                        sqlite_type = "BOOLEAN"
                    elif isinstance(col_type, sqlalchemy.Date) or isinstance(col_type, sqlalchemy.DateTime):
                         sqlite_type = "DATETIME"
                    elif isinstance(col_type, sqlalchemy.LargeBinary):
                        sqlite_type = "BLOB"
                    
                    # Konstrukcja zapytania ALTER TABLE
                    # SQLite: ALTER TABLE table_name ADD COLUMN column_name column_type
                    
                    try:
                        # Uwaga: Enumy w SQLite są często TEXT lub VARCHAR.
                        # Boolean w SQLite to integer 0/1, ale typ w definicji może być BOOLEAN.
                        
                        alter_query = text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {sqlite_type}")
                        conn.execute(alter_query)
                        logger.info(f"Dodano kolumnę {col_name} do {table_name}")
                    except Exception as e:
                        logger.error(f"Nie udało się dodać kolumny {table_name}.{col_name}: {e}")
                        # Kontynuuj dla innych kolumn
        
        # --- NEW: Snapshot Migration Logic (Simplified) ---
        # Run detailed migration via separate script/function to avoid complexity
        pass
        
    conn.commit()
    
    # 2. Run Python-level migrations
    try:
        from migrate_snapshots import migrate_snapshots
        migrate_snapshots()
    except Exception as e:
        logger.error(f"Auto-migration script failed: {e}")

    logger.info("Weryfikacja bazy danych zakończona.")
