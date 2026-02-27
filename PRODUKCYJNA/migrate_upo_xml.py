from sqlalchemy import create_engine, text

DATABASE_URL = "sqlite:///ksef_invoice.db"
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE invoices ADD COLUMN upo_xml TEXT"))
        print("Added upo_xml column.")
    except Exception as e:
        print(f"Error adding upo_xml (maybe exists): {e}")
