from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base

# Domyślna konfiguracja to SQLite dla łatwego startu. 
# Aby użyć MariaDB: 'mysql+pymysql://user:password@localhost/dbname'
DATABASE_URL = "sqlite:///ksef_invoice.db"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Tworzy tabelę w bazie danych jeśli nie istnieją"""
    Base.metadata.create_all(bind=engine)

def get_db():
    """Generator sesji bazy danych"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
