from database.engine import get_db
from database.models import Invoice, InvoiceItem, InvoiceCategory, CompanyConfig
from sqlalchemy import func, extract
from logic.revenue_service import RevenueService

def debug():
    db = next(get_db())
    year = 2026
    month = 2 # February

    # Check Config
    config = db.query(CompanyConfig).first()
    print(f"DEBUG: is_vat_payer={config.is_vat_payer}")
    print(f"DEBUG: taxation_form={config.taxation_form}")

    # Dump Invoices
    invoices = db.query(Invoice).filter(
        Invoice.category == InvoiceCategory.SALES,
        extract('year', Invoice.date_issue) == year,
        extract('month', Invoice.date_issue) == month
    ).all()

    total_net_calc = 0.0
    total_gross_calc = 0.0
    total_rev_net = 0.0
    total_rev_gross = 0.0

    print("\n--- INVOICES DEBUG ---")
    for inv in invoices:
        print(f"Inv {inv.number}: Net={inv.total_net}, Gross={inv.total_gross}")
        for item in inv.items:
            net_line = item.net_price * item.quantity
            print(f"  Item: {item.product_name}, Rate={item.lump_sum_rate}, VAT={item.vat_rate}, NetLine={net_line}, GrossVal={item.gross_value}")
            
            total_rev_net += net_line
            total_rev_gross += item.gross_value

        total_net_calc += inv.total_net
        total_gross_calc += inv.total_gross

    print(f"\nTotal Net (Inv Header): {total_net_calc}")
    print(f"Total Gross (Inv Header): {total_gross_calc}")
    print(f"Total Revenue NET (Items): {total_rev_net}")
    print(f"Total Revenue GROSS (Items): {total_rev_gross}")

    svc = RevenueService(db)
    summary = svc.get_monthly_summary(year, month)
    print("\n--- REVENUE SERVICE SUMMARY ---")
    print(summary)
    
    db.close()

if __name__ == "__main__":
    debug()
