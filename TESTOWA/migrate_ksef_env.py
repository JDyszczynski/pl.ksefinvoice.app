from sqlalchemy import create_engine, text
from database.engine import DATABASE_URL

def migrate():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE company_config ADD COLUMN ksef_environment VARCHAR(20) DEFAULT 'test'"))
            conn.commit()
            print("Migration successful: Added ksef_environment column.")
        except Exception as e:
            print(f"Migration failed (maybe column exists?): {e}")

if __name__ == "__main__":
    migrate()
