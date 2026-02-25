from database.engine import get_db
from database.models import Invoice, InvoiceCategory
from datetime import datetime

db = next(get_db())

try:
    # Fix ID 1 (The stuck Sales invoice)
    inv1 = db.query(Invoice).filter(Invoice.id == 1).first()
    if inv1 and inv1.number == '1/02/2026':
        print(f"Fixing Invoice {inv1.id}: {inv1.number}")
        inv1.sequence_year = 2026
        inv1.sequence_month = 2
        inv1.sequence_number = 1
    
    # Check other invoices
    invoices = db.query(Invoice).all()
    for inv in invoices:
        if inv.sequence_year is None and inv.date_issue:
            print(f"Updating generic invoice {inv.id} ({inv.number}) with year {inv.date_issue.year}")
            inv.sequence_year = inv.date_issue.year
            inv.sequence_month = inv.date_issue.month
            # We don't guess sequence_number for unknown formats to avoid collisions, 
            # but for our specific '1/02/2026' case we handled it above.
            
    db.commit()
    print("Database updated.")
except Exception as e:
    print(f"Error: {e}")
    db.rollback()
finally:
    db.close()
