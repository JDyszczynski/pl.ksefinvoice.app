from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import json
from database.models import Base, Invoice, Contractor, CompanyConfig
from database.engine import DATABASE_URL

def migrate_snapshots():
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    print("Checking for missing snapshot columns...")
    
    # Check if columns exist
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(invoices)"))
        columns = [row[1] for row in result.fetchall()]
        
        if "seller_snapshot" not in columns:
            print("Adding seller_snapshot column...")
            # SQLite stores JSON as TEXT
            conn.execute(text("ALTER TABLE invoices ADD COLUMN seller_snapshot TEXT"))
            
        if "buyer_snapshot" not in columns:
            print("Adding buyer_snapshot column...")
            conn.execute(text("ALTER TABLE invoices ADD COLUMN buyer_snapshot TEXT"))
            
        conn.commit()

    print("Migrating existing invoices to snapshots...")
    
    # For existing invoices, populate snapshots from current Contractor/Company definitions
    # This is imperfect (historical changes lost) but better than null and required for the new logic
    
    invoices = session.query(Invoice).filter((Invoice.buyer_snapshot == None) | (Invoice.seller_snapshot == None)).all()
    company = session.query(CompanyConfig).first()
    
    seller_data = {}
    if company:
        seller_data = {
            "nip": company.nip,
            "company_name": company.company_name,
            "address": company.address,
            "city": company.city,
            "postal_code": company.postal_code,
            "country_code": company.country_code,
            "bank_account": company.bank_account,
            "bank_name": company.bank_name
        }

    count = 0
    for inv in invoices:
        # Populate Buyer Snapshot
        if not inv.buyer_snapshot and inv.contractor:
            buyer = inv.contractor
            inv.buyer_snapshot = {
                "nip": buyer.nip,
                "name": buyer.name,
                "address": buyer.address,
                "city": buyer.city,
                "postal_code": buyer.postal_code,
                "country_code": buyer.country_code,
                "is_person": buyer.is_person
            }
        
        # Populate Seller Snapshot
        if not inv.seller_snapshot and seller_data:
            inv.seller_snapshot = seller_data
            
        count += 1
        
    session.commit()
    print(f"Migrated {count} invoices.")
    session.close()

if __name__ == "__main__":
    migrate_snapshots()
