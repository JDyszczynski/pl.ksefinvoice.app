from database.engine import get_db
from sqlalchemy import text

def update_db():
    print("Updating database schema within current transaction...")
    db = next(get_db())
    # conn = db.connection()  <-- Don't get connection directly if using ORM session
    
    try:
        # Check if column exists in products table using a safe check
        # SQLite doesn't support IF NOT EXISTS in ALTER TABLE ADD COLUMN
        # But we can try and catch exception or check pragma
        
        # Check 'products' table for 'pkwiu'
        print("Checking/Adding pkwiu to products...")
        try:
             db.execute(text("ALTER TABLE products ADD COLUMN pkwiu VARCHAR(20)"))
             print("Added pkwiu column to products.")
        except Exception as e:
             if "duplicate column" in str(e).lower() or "no such column" in str(e).lower(): # SQLite variants
                  print(f"Column pkwiu likely exists in products: {e}")
             else:
                  print(f"Info: {e}")

        # Commit changes
        db.commit()
        print("Database update finished.")
        
    except Exception as e:
        print(f"Error during migration: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    update_db()
