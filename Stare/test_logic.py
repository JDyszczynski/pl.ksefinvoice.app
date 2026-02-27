from database.engine import init_db, get_db
from database.models import Product, Contractor, Invoice, InvoiceItem

def test_backend_logic():
    print("1. Inicjalizacja bazy danych...")
    init_db()
    print("   Baza zainicjalizowana.")

    db = next(get_db())

    print("2. Dodawanie produktu...")
    new_prod = Product(name="Test Product", net_price=100.0, vat_rate=23)
    db.add(new_prod)
    db.commit()
    print(f"   Produkt dodany: ID={new_prod.id}, Nazwa={new_prod.name}")

    print("3. Dodawanie kontrahenta...")
    new_contra = Contractor(name="Test Firma", nip="1234567890", address="Ulica 1")
    db.add(new_contra)
    db.commit()
    print(f"   Kontrahent dodany: ID={new_contra.id}, Nazwa={new_contra.name}")

    print("4. Tworzenie faktury...")
    inv = Invoice(number="FV/TEST/1", contractor_id=new_contra.id, total_net=100.0, total_gross=123.0)
    db.add(inv)
    db.commit()
    
    item = InvoiceItem(
        invoice_id=inv.id, product_name=new_prod.name, 
        quantity=1, net_price=new_prod.net_price, 
        vat_rate=new_prod.vat_rate, gross_value=123.0
    )
    db.add(item)
    db.commit()
    print(f"   Faktura dodana: ID={inv.id}, Numer={inv.number}")

    print("5. Weryfikacja danych...")
    saved_inv = db.query(Invoice).filter(Invoice.number == "FV/TEST/1").first()
    if saved_inv and saved_inv.items[0].product_name == "Test Product":
        print("   SUKCES: Dane zapisane i odczytane poprawnie.")
    else:
        print("   BŁĄD: Niepoprawne dane w bazie.")

    db.close()

if __name__ == "__main__":
    test_backend_logic()
