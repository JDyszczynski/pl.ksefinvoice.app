from sqlalchemy import create_engine, text
from database.engine import DATABASE_URL

def migrate():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        try:
            # Check if column exists
            result = conn.execute(text("PRAGMA table_info(invoices)"))
            columns = [row[1] for row in result.fetchall()]
            
            if "environment" not in columns:
                print("Adding 'environment' column to invoices table...")
                conn.execute(text("ALTER TABLE invoices ADD COLUMN environment VARCHAR(10) DEFAULT 'test'"))
                print("Column added.")
            else:
                print("Column 'environment' already exists.")
                
        except Exception as e:
            print(f"Migration failed: {e}")

if __name__ == "__main__":
    migrate()
