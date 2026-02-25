from database.engine import get_db
from database.models import Invoice

db = next(get_db())
invoices = db.query(Invoice).all()

print(f"{'ID':<5} {'Number':<20} {'ParentID':<10} {'TotalGross':<15} {'PaidAmount':<15}")
print("-" * 70)
for inv in invoices:
    print(f"{inv.id:<5} {inv.number:<20} {str(inv.parent_id):<10} {inv.total_gross:<15} {inv.paid_amount:<15}")

db.close()
