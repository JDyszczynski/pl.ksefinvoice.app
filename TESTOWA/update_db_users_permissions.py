from sqlalchemy import create_engine, text
from database.models import Base

def upgrade_users_permissions():
    engine = create_engine("sqlite:///ksef_invoice.db")
    with engine.connect() as conn:
        try:
            # Check if columns exist
            conn.execute(text("SELECT perm_send_ksef FROM users LIMIT 1"))
            print("Uprawnienia już istnieją.")
        except Exception:
            print("Dodawanie kolumn uprawnień...")
            try:
                # Add columns one by one
                conn.execute(text("ALTER TABLE users ADD COLUMN perm_send_ksef BOOLEAN DEFAULT 0"))
                conn.execute(text("ALTER TABLE users ADD COLUMN perm_receive_ksef BOOLEAN DEFAULT 0"))
                conn.execute(text("ALTER TABLE users ADD COLUMN perm_settlements BOOLEAN DEFAULT 0"))
                conn.execute(text("ALTER TABLE users ADD COLUMN perm_declarations BOOLEAN DEFAULT 0"))
                conn.execute(text("ALTER TABLE users ADD COLUMN perm_settings BOOLEAN DEFAULT 0"))
                
                # Migrate existing roles
                # Admins get all permissions
                conn.execute(text("UPDATE users SET perm_send_ksef=1, perm_receive_ksef=1, perm_settlements=1, perm_declarations=1, perm_settings=1 WHERE role='admin'"))
                # Users get... basic? Maybe none? Let's give them basic KSEF receive and UI access?
                # User didn't specify, but safer to give basics or check against 'role' meaning.
                # Assuming 'user' had access to creating invoices which isn't limited here explicitly (only send/receive ksef).
                # But settlements/declarations/settings are administrative.
                # So 'user' -> perm_send_ksef=0, perm_receive_ksef=0, perm_settlements=0, perm_declarations=0, perm_settings=0 ?
                # Or maybe user could send invoices?
                # Let's leave users with 0 for the restricted actions as per user request to limit them.
                
                # Cleanup role column? No, keep it for now just in case.
                
                print("Zaktualizowano schemat i uprawnienia.")
            except Exception as e:
                print(f"Błąd migracji: {e}")

if __name__ == "__main__":
    upgrade_users_permissions()
