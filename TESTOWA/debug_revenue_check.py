from database.engine import get_db
from database.models import Invoice, InvoiceItem, InvoiceCategory, InvoiceType
from sqlalchemy import extract, func
import datetime

db = next(get_db())

year = datetime.datetime.now().year
# Assuming the user is talking about current month or specific month.
# Let's check all months where there is data.
print(f"Checking data for year {year}")

invoices = db.query(Invoice).filter(extract('year', Invoice.date_issue) == year).all()

for inv in invoices:
    print(f"ID: {inv.id}, Num: {inv.number}, Date: {inv.date_issue}, Type: {inv.type}, Cat: {inv.category}, Net: {inv.total_net}")
    for item in inv.items:
        print(f"  - Item: {item.product_name}, Qty: {item.quantity}, Price: {item.net_price}, Gross: {item.gross_value}, LumpRate: {item.lump_sum_rate}, VatRate: {item.vat_rate}")

# Calculate summary manually
from logic.revenue_service import RevenueService
svc = RevenueService(db)

# Find used months
months = set([i.date_issue.month for i in invoices])
for m in months:
    print(f"\n--- Month {m} ---")
    summary = svc.get_monthly_summary(year, m)
    print(summary)
