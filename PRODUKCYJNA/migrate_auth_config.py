from database.engine import get_db
from sqlalchemy import text

def migrate_auth():
    print("Migrating Auth Config...")
    db = next(get_db())
    conn = db.connection()
    
    # Add ksef_auth_mode
    try:
        db.execute(text("ALTER TABLE company_config ADD COLUMN ksef_auth_mode VARCHAR(20) DEFAULT 'TOKEN'"))
        print("Added ksef_auth_mode")
    except Exception as e:
        print(f"ksef_auth_mode exists or error: {e}")

    # Add ksef_cert_path
    try:
        db.execute(text("ALTER TABLE company_config ADD COLUMN ksef_cert_path VARCHAR(255)"))
        print("Added ksef_cert_path")
    except Exception as e:
        print(f"ksef_cert_path exists or error: {e}")

    # Add ksef_private_key_path
    try:
        db.execute(text("ALTER TABLE company_config ADD COLUMN ksef_private_key_path VARCHAR(255)"))
        print("Added ksef_private_key_path")
    except Exception as e:
        print(f"ksef_private_key_path exists or error: {e}")

    # Add ksef_private_key_pass
    try:
        db.execute(text("ALTER TABLE company_config ADD COLUMN ksef_private_key_pass VARCHAR(255)"))
        print("Added ksef_private_key_pass")
    except Exception as e:
        print(f"ksef_private_key_pass exists or error: {e}")
        
    db.commit()
    print("Migration finished.")

if __name__ == "__main__":
    migrate_auth()
