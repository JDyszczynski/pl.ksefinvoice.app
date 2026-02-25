from sqlalchemy import create_engine, text
from database.engine import DATABASE_URL

def upgrade():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        try:
             # Check if column exists (SQLite specific check or just try add)
             # SQLite doesn't support IF NOT EXISTS in ADD COLUMN well in older versions, 
             # but we assume modern or catch error.
             conn.execute(text("ALTER TABLE invoices ADD COLUMN upo_url VARCHAR(500)"))
             print("Added upo_url column.")
        except Exception as e:
             if "duplicate column" in str(e).lower() or "no such table" in str(e).lower():
                  print(f"Column likely exists or table missing: {e}")
             else:
                  print(f"Error adding column: {e}")

if __name__ == "__main__":
    upgrade()
