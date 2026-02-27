from database.engine import get_db, engine
from sqlalchemy import text

def update_schema():
    connection = engine.connect()
    try:
        # Check company_config
        try:
            connection.execute(text("SELECT footer_extra FROM company_config LIMIT 1"))
            print("Column footer_extra exists in company_config.")
        except Exception:
            print("Adding footer_extra to company_config...")
            connection.execute(text("ALTER TABLE company_config ADD COLUMN footer_extra VARCHAR(255)"))
            
        # Check invoice_items
        try:
            connection.execute(text("SELECT description_key FROM invoice_items LIMIT 1"))
            print("Column description_key exists in invoice_items.")
        except Exception:
            print("Adding description_key to invoice_items...")
            connection.execute(text("ALTER TABLE invoice_items ADD COLUMN description_key VARCHAR(255)"))

        try:
            connection.execute(text("SELECT description_value FROM invoice_items LIMIT 1"))
            print("Column description_value exists in invoice_items.")
        except Exception:
            print("Adding description_value to invoice_items...")
            connection.execute(text("ALTER TABLE invoice_items ADD COLUMN description_value VARCHAR(255)"))
            
        connection.commit()
    except Exception as e:
        print(f"Error updating schema: {e}")
    finally:
        connection.close()

if __name__ == "__main__":
    update_schema()
