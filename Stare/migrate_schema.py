from database.engine import get_db, engine, Base
from database.models import LumpSumRate, VatRate
from sqlalchemy import text

def migrate():
    db = next(get_db())
    conn = db.connection()
    
    # 1. Create new Tax System tables if not exist
    try:
        # Check if table exists
        db.execute(text("SELECT count(*) FROM lump_sum_rates"))
    except:
        print("Creating lump_sum_rates table...")
        LumpSumRate.__table__.create(db.get_bind())
        
        # Seed Ryczałt Rates
        rates = [
            ("17%", 0.17), ("15%", 0.15), ("14%", 0.14), 
            ("12.5%", 0.125), ("12%", 0.12), ("10%", 0.10), 
            ("8.5%", 0.085), ("5.5%", 0.055), ("3%", 0.03), ("2%", 0.02)
        ]
        for name, rate in rates:
            db.add(LumpSumRate(name=name, rate=rate))
        db.commit()
        print("Seeded Lump Sum Rates.")

    # 2. Add columns to Invoices
    try:
        db.execute(text("ALTER TABLE invoices ADD COLUMN price_type VARCHAR(10) DEFAULT 'NET'"))
        print("Added price_type to invoices")
    except Exception as e: pass # Already exists

    try:
        db.execute(text("ALTER TABLE invoices ADD COLUMN is_new_transport_intra BOOLEAN DEFAULT 0"))
        print("Added is_new_transport_intra to invoices")
    except: pass

    try:
        db.execute(text("ALTER TABLE invoices ADD COLUMN excise_duty_refund BOOLEAN DEFAULT 0"))
        print("Added excise_duty_refund to invoices")
    except: pass
    
    try:
        db.execute(text("ALTER TABLE invoices ADD COLUMN transaction_contract_date DATETIME"))
        print("Added transaction_contract_date to invoices")
    except: pass

    # 3. Add columns to Items
    try:
        db.execute(text("ALTER TABLE invoice_items ADD COLUMN lump_sum_rate FLOAT DEFAULT NULL"))
        print("Added lump_sum_rate to items")
    except: pass

    try:
        db.execute(text("ALTER TABLE invoice_items ADD COLUMN sku VARCHAR(50) DEFAULT NULL"))
        print("Added sku to items")
    except: pass
    
    try:
        db.execute(text("ALTER TABLE invoice_items ADD COLUMN gtu VARCHAR(10) DEFAULT NULL"))
        print("Added gtu to items")
    except: pass

    # 4. Config
    try:
        db.execute(text("ALTER TABLE company_config ADD COLUMN taxation_form VARCHAR(20) DEFAULT 'RYCZALT'"))
        print("Added taxation_form to config")
    except: pass

    db.close()

if __name__ == "__main__":
    migrate()
