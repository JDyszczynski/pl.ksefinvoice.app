from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Boolean, Enum, Text, LargeBinary
from sqlalchemy.orm import DeclarativeBase, relationship
from datetime import datetime
import enum

class Base(DeclarativeBase):
    pass

class InvoiceType(enum.Enum):
    VAT = "VAT"
    MARZA = "MARZA"
    RYCZALT = "RYCZALT" # Używane jako "Rachunek"
    KOREKTA = "KOREKTA"
    ZALICZKA = "ZALICZKA"
    PODATEK = "PODATEK" # Nowe
    INNE = "INNE"

class TaxSystem(enum.Enum):
    VAT = "VAT" # Zasady ogólne / Liniowy z VAT
    RYCZALT = "RYCZALT" # Ryczałt ewidencjonowany (bez VAT)
    ZWOLNIONY = "ZWOLNIONY" # Zwolniony z VAT

class TaxationForm(enum.Enum):
    SCALE = "SCALE" # Skala podatkowa (12/32%)
    LINEAR = "LINEAR" # Podatek liniowy (19%)
    RYCZALT = "RYCZALT" # Ryczałt ewidencjonowany

class InvoiceCategory(enum.Enum):
    SALES = "Sprzedaż"
    PURCHASE = "Zakup"

class PeriodType(enum.Enum):
    YEARLY = "YEARLY"
    MONTHLY = "MONTHLY"

class NumberingSetting(Base):
    __tablename__ = "numbering_settings"
    
    id = Column(Integer, primary_key=True)
    invoice_type = Column(Enum(InvoiceType), nullable=True) # Typ faktury (VAT, KOREKTA), null = wszystkie inne
    invoice_category = Column(Enum(InvoiceCategory), nullable=False) # Sprzedaż/Zakup
    
    period_type = Column(Enum(PeriodType), default=PeriodType.YEARLY)
    # Wzorzec: {nr}, {rok}, {miesiac}
    template = Column(String(50), default="{nr}/{rok}") 
    
    # Czy ten ciąg ma być domyślny dla danej pary kategoria/typ?
    is_default = Column(Boolean, default=True)

class CompanyConfig(Base):
    __tablename__ = "company_config"
    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String(255), nullable=False)
    nip = Column(String(10), nullable=False)
    regon = Column(String(14), nullable=True)
    address = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    postal_code = Column(String(10), nullable=True)
    country = Column(String(100), default="Polska") # Kraj
    country_code = Column(String(10), default="PL") # Kod kraju
    
    bank_account = Column(String(100), nullable=True)
    bank_name = Column(String(100), nullable=True) # Nazwa banku
    swift_code = Column(String(20), nullable=True) # SWIFT/BIC

    # Dane rejestrowe (Stopka)
    krs = Column(String(20), nullable=True)
    bdo = Column(String(20), nullable=True)
    share_capital = Column(String(50), nullable=True) # np. "50000 zł"
    court_info = Column(String(255), nullable=True) # Sąd Rejonowy...
    
    # NEW: Additional footer info (Stopka 2)
    footer_extra = Column(String(255), nullable=True)

    # NEW: Certyfikatowe logowanie & Environment
    ksef_environment = Column(String(20), default="prod") # 'prod' or 'test'
    ksef_auth_mode = Column(String(20), default="TOKEN") # 'TOKEN' or 'CERT'
    
    # Prod Credentials
    ksef_token = Column(String(1000), nullable=True) # Token autoryzacyjny KSeF (PROD)
    # Changed: Paths -> Content (Binary) for portability
    # Old paths kept for migration compatibility or removed if fresh
    ksef_cert_content = Column(LargeBinary, nullable=True) 
    ksef_private_key_content = Column(LargeBinary, nullable=True)
    ksef_private_key_pass = Column(String(255), nullable=True)
    
    # Test/Demo Credentials
    ksef_token_test = Column(String(1000), nullable=True) 
    ksef_cert_content_test = Column(LargeBinary, nullable=True)
    ksef_private_key_content_test = Column(LargeBinary, nullable=True)
    ksef_private_key_pass_test = Column(String(255), nullable=True)
    
    # Public Keys (KSeF) Cache
    ksef_public_key_prod = Column(LargeBinary, nullable=True)
    ksef_public_key_test = Column(LargeBinary, nullable=True)

    # Konfiguracja domyślna
    default_tax_system = Column(Enum(TaxSystem), default=TaxSystem.RYCZALT)
    taxation_form = Column(Enum(TaxationForm), default=TaxationForm.RYCZALT) # Forma opodatkowania firmy
    default_lump_sum_rate = Column(Float, default=0.12) # Domyślna stawka ryczałtu (12%)

    # JPK V7 Configuration
    is_natural_person = Column(Boolean, default=False) # Czy osoba fizyczna
    first_name = Column(String(100), nullable=True) # Imie (dla osoby fizycznej)
    last_name = Column(String(100), nullable=True) # Nazwisko (dla osoby fizycznej)
    date_of_birth = Column(DateTime, nullable=True) # Data Urodzenia (dla osoby fizycznej)
    tax_office_code = Column(String(10), nullable=True) # Kod Urzędu Skarbowego (e.g. 2206)
    email = Column(String(100), nullable=True) # E-mail (do JPK)
    phone_number = Column(String(20), nullable=True) # Telefon (do JPK)
    
    vat_settlement_method = Column(String(20), default="MONTHLY") # MONTHLY / QUARTERLY

    default_place_of_issue = Column(String(100), nullable=True)
    
    # Zwolnienie z VAT
    is_vat_payer = Column(Boolean, default=True) # Czy firma jest płatnikiem VAT
    vat_exemption_basis_type = Column(String(20), nullable=True) # Podstawa zwolnienia (typ): USTAWA/DYREKTYWA/INNE
    vat_exemption_basis = Column(String(255), nullable=True) # Podstawa prawna zwolnienia
    vat_exemption_limit = Column(Integer, default=200000) # Próg zwolnienia z VAT (np. 200k, user requested 240k possibility)
    vat_warning_threshold = Column(Integer, default=180000) # Próg ostrzegawczy
    vat_exemption_subject_based = Column(Boolean, default=False) # Czy zwolnienie przedmiotowe (brak limitu)

    # Skala Podatkowa (Scale Tax Parameters)
    tax_scale_limit_1 = Column(Integer, default=120000) # Próg I (120k)
    tax_scale_rate_1 = Column(Float, default=0.12) # Stawka I (12%)
    tax_scale_deduction = Column(Integer, default=3600) # Kwota zmniejszająca (3600)
    tax_scale_rate_2 = Column(Float, default=0.32) # Stawka II (32%)
    
    # Podatek Liniowy
    tax_linear_rate = Column(Float, default=0.19)
    
    # Danina Solidarnościowa
    solidarity_levy_limit = Column(Integer, default=1000000) # 1 mln
    solidarity_levy_rate = Column(Float, default=0.04) # 4%

class VatRate(Base):
    __tablename__ = "vat_rates"
    id = Column(Integer, primary_key=True)
    name = Column(String(50)) # np. "23%", "ZW"
    rate = Column(Float) # 0.23, 0.0

class LumpSumRate(Base):
    __tablename__ = "lump_sum_rates"
    id = Column(Integer, primary_key=True)
    name = Column(String(50)) # np. "12%", "8.5%"
    rate = Column(Float) # 0.12, 0.085

class Contractor(Base):
    __tablename__ = "contractors"

    id = Column(Integer, primary_key=True, index=True)
    nip = Column(String(10), unique=True, index=True) # NIP bez kresek
    regon = Column(String(14), nullable=True)
    name = Column(String(255), nullable=False)
    address = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    postal_code = Column(String(10), nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    country = Column(String(100), default="Polska")
    country_code = Column(String(3), default="PL")
    is_vat_payer = Column(Boolean, default=True) # Czy czynny podatnik VAT
    is_vat_ue = Column(Boolean, default=False) # Czy podatnik VAT UE
    is_person = Column(Boolean, default=False) # True = Osoba fizyczna (imię i nazwisko w name), False = Firma

    invoices = relationship("Invoice", back_populates="contractor")

    @property
    def person_name_parts(self):
        """Splits name into (first_name, last_name) properly handling single words or empty."""
        if not self.name:
            return "", ""
        parts = self.name.strip().split(' ', 1)
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], parts[1]


    def __repr__(self):
        return f"<Contractor(name='{self.name}', nip='{self.nip}')>"

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    sku = Column(String(50), nullable=True) # Kod produktu
    unit = Column(String(20), default="szt.")
    purchase_net_price = Column(Float, default=0.0)
    net_price = Column(Float, nullable=False)
    gross_price = Column(Float, default=0.0) # Cache brutto
    vat_rate = Column(Float, default=0.23)
    is_gross_mode = Column(Boolean, default=False) # Czy cena bazowa to brutto

    def __repr__(self):
        return f"<Product(name='{self.name}', price={self.net_price})>"

class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    number = Column(String(50), unique=True, nullable=False)
    category = Column(Enum(InvoiceCategory), default=InvoiceCategory.SALES) # Sprzedaż/Zakup
    type = Column(Enum(InvoiceType), default=InvoiceType.VAT) # VAT/Marża/itp
    tax_system = Column(Enum(TaxSystem), default=TaxSystem.RYCZALT) # System podatkowy faktury
    
    contractor_id = Column(Integer, ForeignKey("contractors.id"))
    
    date_issue = Column(DateTime, default=datetime.now) # Data wystawienia
    date_sale = Column(DateTime, default=datetime.now) # Data sprzedaży/wykonania usługi
    place_of_issue = Column(String(100), nullable=True) # Miejsce wystawienia
    
    payment_method = Column(String(50), default="Przelew")
    price_type = Column(String(10), default="NET") # "NET" lub "GROSS"
    
    # Pola do kontroli numeracji
    sequence_year = Column(Integer, nullable=True)
    sequence_month = Column(Integer, nullable=True) # Tylko dla numeracji miesięcznej
    sequence_number = Column(Integer, nullable=True) # ID porządkowe w obrębie roku/miesiąca
    payment_deadline = Column(DateTime, nullable=True) # Termin płatności
    bank_account_number = Column(String(100), nullable=True) # Numer konta na fakturze
    
    currency = Column(String(3), default="PLN")
    currency_rate = Column(Float, default=1.0)
    currency_date = Column(DateTime, nullable=True)
    
    total_net = Column(Float, default=0.0)
    total_gross = Column(Float, default=0.0)
    
    # Rozliczenia
    is_paid = Column(Boolean, default=False) # Czy zapłacono całość
    paid_amount = Column(Float, default=0.0)
    paid_date = Column(DateTime, nullable=True) # Data zapłaty częściowej lub całościowej
    
    # Dla faktur korygujących i powiązanych
    parent_id = Column(Integer, ForeignKey('invoices.id'), nullable=True)
    parent = relationship("Invoice", remote_side="Invoice.id") # Relacja do rodzica (nie używamy remote_side=[id] w nowszym SQLAlchemy 2.0 style jeśli class defined, ale tutaj Invoice referencuje sam siebie)
    
    correction_reason = Column(String(500), nullable=True) # Przyczyna korekty (P_CorrectiveDesc)
    correction_type = Column(Integer, nullable=True) # 1=Zmniejszająca (Skutek data pierwotna), 2=Zwiększająca? KSeF 1/2/3
    related_invoice_number = Column(String(100), nullable=True) # Numer faktury korygowanej (P_2RE)
    related_ksef_number = Column(String(100), nullable=True) # Nr KSeF korygowanej (NrKSeF)
    
    notes = Column(String(1000), nullable=True) # Uwagi
    
    ksef_number = Column(String(100), nullable=True) # Numer KSeF po wysłaniu
    ksef_xml = Column(Text, nullable=True) # Pełny XML faktury (cache)
    
    # Environment tracking
    environment = Column(String(10), default="test") # 'prod' or 'test'
    
    is_sent_to_ksef = Column(Boolean, default=False)
    upo_datum = Column(DateTime, nullable=True) # Data UPO
    upo_url = Column(String(500), nullable=True) # Link do UPO
    upo_xml = Column(Text, nullable=True) # Pełny XML UPO (cache)
    
    # KSeF Flags / Attributes
    # P_16: Metoda kasowa
    is_cash_accounting = Column(Boolean, default=False)
    # P_17: Samofakturowanie
    is_self_billing = Column(Boolean, default=False)
    # P_18: Odwrotne obciążenie
    is_reverse_charge = Column(Boolean, default=False)
    # P_18A: Mechanizm podzielonej płatności (MPP)
    is_split_payment = Column(Boolean, default=False)
    
    # Dodatkowe flagi KSeF
    is_new_transport_intra = Column(Boolean, default=False) # WDT nowych środków transportu
    excise_duty_refund = Column(Boolean, default=False) # Zwrot akcyzy
    
    # Faktura uproszczona (P_23) / FP (Fisklana P_109)
    is_simplified = Column(Boolean, default=False) 
    is_fp = Column(Boolean, default=False) # Faktura do paragonu
    is_tp = Column(Boolean, default=False) # Podmiot powiązany
    
    # Zwolnienie i Marża szczegóły
    # P_19: Zwolnienie (True jeśli występuje P_19=1)
    is_exempt = Column(Boolean, default=False)
    # Typ zwolnienia: 'USTAWA' (P_19A), 'DYREKTYWA' (P_19B), 'INNE' (P_19C)
    exemption_basis_type = Column(String(20), nullable=True) 
    # Treść przepisu
    exemption_basis = Column(String(255), nullable=True)
    
    # Marża procedura (jeśli invoice.type == MARZA)
    # wartości: 'UZYWANE' (towary używane), 'DZIELA' (sztuki), 'ANTYKI' (kolekcjonerskie/antyki), 'TURYSTYKA' (procedura marży dla biur podróży)
    margin_procedure_type = Column(String(20), nullable=True)
    
    # Daty okresowe / Dostawy
    # Jeśli date_period_start jest ustawione, to date_sale to P_6 (Data wykonania/zakończenia) lub element okresu
    date_period_start = Column(DateTime, nullable=True) 
    date_period_end = Column(DateTime, nullable=True)
    
    # Warunki transakcji (Zamówienia/Umowy)
    transaction_order_number = Column(String(100), nullable=True) # Zamówienie numer
    transaction_order_date = Column(DateTime, nullable=True) # Zamówienie data
    transaction_contract_number = Column(String(100), nullable=True) # Umowa numer
    transaction_contract_date = Column(DateTime, nullable=True) # Umowa data
    
    # Dodatkowe pola
    bank_accounts = Column(Text, nullable=True) # JSON or semicolon separated list
    has_attachment = Column(Boolean, default=False) # Czy jest sekcja Zalacznik (wizualizacja)
    
    contractor = relationship("Contractor", back_populates="invoices")
    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")
    payment_breakdowns = relationship("InvoicePaymentBreakdown", back_populates="invoice", cascade="all, delete-orphan")

class InvoicePaymentBreakdown(Base):
    __tablename__ = "invoice_payment_breakdowns"
    
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"))
    payment_method = Column(String(50)) # Gotówka, Karta, Przelew, Kredyt
    amount = Column(Float, default=0.0)
    
    invoice = relationship("Invoice", back_populates="payment_breakdowns")

class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"))
    
    # Pozycja na fakturze
    index = Column(Integer, default=1) # NrWierszaFa
    
    product_name = Column(String(255))
    sku = Column(String(50), nullable=True) # Indeks / SKU
    pkwiu = Column(String(20), nullable=True) # PKWiU
    gtu = Column(String(10), nullable=True) # GTU (01-13)
    
    quantity = Column(Float, default=1.0)
    unit = Column(String(20), default="szt.")
    
    net_price = Column(Float, nullable=False)
    vat_rate = Column(Float, default=0.23) # Używane przy VAT
    vat_rate_name = Column(String(20), nullable=True) # Nazwa stawki (np. "23%", "ZW", "0% WDT")
    lump_sum_rate = Column(Float, nullable=True) # Stawka ryczałtu dla tej pozycji (0.12, 0.085 etc)
    
    gross_value = Column(Float, nullable=False)
    
    # NEW: Additional Item Description (DodatkowyOpis)
    description_key = Column(String(255), nullable=True)
    description_value = Column(String(255), nullable=True)

    invoice = relationship("Invoice", back_populates="items")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(100), nullable=True) # SHA1 hash. Null = no password.
    # Permissions
    perm_send_ksef = Column(Boolean, default=False)
    perm_receive_ksef = Column(Boolean, default=False)
    perm_settlements = Column(Boolean, default=False)
    perm_declarations = Column(Boolean, default=False)
    perm_settings = Column(Boolean, default=False)
    
    def __repr__(self):
        return f"<User(username='{self.username}')>"
        return f"<User {self.username}>"
