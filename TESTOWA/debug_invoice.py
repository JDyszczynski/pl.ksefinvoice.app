from database.engine import get_db
from database.models import Invoice, InvoiceItem, InvoicePaymentBreakdown
from datetime import date

db = next(get_db())
target_date = date(2026, 2, 27)

invoices = db.query(Invoice).all()
print(f"Found {len(invoices)} invoices total in DB.")

for inv in invoices:
    date_match = False
    
    # Handle dates
    inv_date = inv.invoice_date
    if hasattr(inv_date, 'date'):
        inv_date = inv_date.date()
        
    created_at = getattr(inv, 'created_at', None)
    if hasattr(created_at, 'date'):
        created_at = created_at.date()
        
    if inv_date == target_date:
        date_match = True
    elif created_at == target_date:
        date_match = True
        
    if date_match:
        print(f"\n--- INVOICE ID: {inv.id} ---")
        print(f"Number: {inv.number}")
        print(f"Date: {inv_date}")
        print(f"Total Net: {getattr(inv, 'total_net', 'N/A')}")
        print(f"Total Gross: {getattr(inv, 'total_gross', 'N/A')}")
        print(f"Paid Amount: {getattr(inv, 'paid_amount', 'N/A')}")
        
        print("\nITEMS:")
        items = db.query(InvoiceItem).filter(InvoiceItem.invoice_id == inv.id).all()
        if not items:
            print("  NO ITEMS FOUND!")
        else:
            for item in items:
                print(f"  - {item.product_name}, Net: {item.net_price}, Gross: {getattr(item, 'gross_value', 'N/A')}, Qty: {item.quantity}")

        print("\nPAYMENTS (Breakdowns):")
        payments = db.query(InvoicePaymentBreakdown).filter(InvoicePaymentBreakdown.invoice_id == inv.id).all()
        if not payments:
            print("  NO PAYMENTS FOUND!")
        else:
            for payment in payments:
                 print(f"  - Method: {payment.payment_method}, Amount: {payment.amount}")

db.close()
