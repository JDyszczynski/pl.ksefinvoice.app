from database.engine import get_db
from database.models import NumberingSetting, InvoiceCategory, InvoiceType

db = next(get_db())
settings = db.query(NumberingSetting).all()
print("Numbering Settings:")
for s in settings:
    print(f"Cat: {s.invoice_category}, Type: {s.invoice_type}, Template: '{s.template}'")
db.close()
