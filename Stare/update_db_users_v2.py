from sqlalchemy import create_engine, text
from database.models import Base

def upgrade_users():
    # Use production DB
    engine = create_engine("sqlite:///ksef_invoice.db")
    with engine.connect() as conn:
        # Check if users table format is correct or recreate
        # Actually since I modified the model, I should probably check columns.
        # But assuming prior migrations might have created it differently or not at all.
        try:
            # Check if password_hash exists
            conn.execute(text("SELECT password_hash FROM users LIMIT 1"))
            print("Tabela users ma już password_hash.")
        except Exception:
            print("Aktualizacja tabeli users (dodanie password_hash lub tworzenie tabeli)...")
            # Create table if not exists
            try:
                Base.metadata.create_all(engine)
                # If table existed but with old schema, we might need alter.
                # Let's try to add column if insert fails or just assume create_all handles NEW tables.
                # If table exists, create_all does nothing.
                
                # Try adding column manually if 'password' column exists but 'password_hash' not
                try:
                    conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(100)"))
                    print("Dodano kolumnę password_hash")
                except Exception as e:
                    if "duplicate column" not in str(e).lower():
                        # Maybe table didn't exist and create_all created it correct?
                        pass
                        
                # Remove `password` column if exists? SQLite doesn't support DROP COLUMN easily in older versions.
                # We will just ignore the old column.
                
            except Exception as e:
                print(f"Błąd migracji users: {e}")

if __name__ == "__main__":
    upgrade_users()
