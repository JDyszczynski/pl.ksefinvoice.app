import xml.etree.ElementTree as ET
import re
from datetime import datetime
from database.models import Invoice, InvoiceItem, Contractor, InvoiceType, TaxSystem, InvoiceCategory

class KsefLogic:
    """
    Central logic for KSeF compliance.
    Handles mapping between Database Models and KSeF XML Structure (FA(2)/FA(3)).
    """

    NAMESPACES = {
        'ksef': 'http://ksef.mf.gov.pl/schema/gtw/svc/types/2021/10/01/0001', # Base namespace, might vary by version
        # We usually strip namespaces for easier parsing in simple logic
    }

    @staticmethod
    def strip_namespaces(xml_string):
        """Removes namespaces to simplify ElementTree parsing."""
        return re.sub(r' xmlns="[^"]+"', '', xml_string, count=1)

    @staticmethod
    def parse_xml_to_invoice(xml_str: str, category: InvoiceCategory = InvoiceCategory.PURCHASE) -> Invoice:
        """
        Parses KSeF XML and returns an ephemeral Invoice object (not attached to session).
        NOTE: This does NOT commit to DB.
        """
        clean_xml = KsefLogic.strip_namespaces(xml_str)
        root = ET.fromstring(clean_xml)

        # 1. Header (Naglowek)
        header = root.find(".//Naglowek")
        fa_node = root.find(".//Fa")
        
        inv_number = "UNKNOWN"
        if fa_node is not None:
             inv_number = fa_node.findtext("P_2", "UNKNOWN")
        
        # Dates
        date_issue_str = "2024-01-01"
        date_sale_str = "2024-01-01"
        
        if fa_node is not None:
             date_issue_str = fa_node.findtext("P_1", date_issue_str)
             # P_6 is Date of Sale/Finish
             date_sale_str = fa_node.findtext("P_6", date_issue_str)

        try:
            date_issue = datetime.strptime(date_issue_str, "%Y-%m-%d").date()
        except: date_issue = datetime.now().date()
        
        try:
             date_sale = datetime.strptime(date_sale_str, "%Y-%m-%d").date()
        except: date_sale = date_issue

        # 2. Contractor (Podmiot1 = Seller for Purchase, Buyer for Sales usually? 
        # In KSeF XML:
        # Podmiot1 is the Seller (Sprzedawca).
        # Podmiot2 is the Buyer (Nabywca).
        # If Category is PURCHASE, our Contractor is Podmiot1.
        # If Category is SALES, our Contractor is Podmiot2.
        
        contractor = Contractor()
        # Find relevant party node
        party_node = None
        if category == InvoiceCategory.PURCHASE:
             party_node = root.find(".//Podmiot1")
        else:
             party_node = root.find(".//Podmiot2")
        
        if party_node:
             dane = party_node.find(".//DaneIdentyfikacyjne")
             nip = dane.findtext("NIP")
             name = dane.findtext("NazwaPelna") # Or in Adres
             
             adres = party_node.find(".//Adres")
             road = adres.findtext(".//Ulica") or ""
             house = adres.findtext(".//NrDomu") or ""
             flat = adres.findtext(".//NrLokalu") or ""
             city = adres.findtext(".//Miejscowosc") or ""
             zip_code = adres.findtext(".//KodPocztowy") or ""
             country = adres.findtext(".//KodKraju") or "PL"
             
             full_address = f"{road} {house}"
             if flat: full_address += f"/{flat}"
             
             contractor.nip = nip
             contractor.name = name if name else "Nieznany"
             contractor.address = full_address
             contractor.city = city
             contractor.postal_code = zip_code
             contractor.country_code = country

        # 3. Totals
        net_total = 0.0
        gross_total = 0.0
        currency = "PLN"
        
        if fa_node is not None:
             currency = fa_node.findtext("KodWaluty", "PLN")
             # P_15 is Total Gross
             gross_total = float(fa_node.findtext("P_15", "0.0").replace(',', '.'))
             # Sum of Nets (P_13_x) or P_14_x (Vat)
             # Simplified: We sum generic nets if available, or rely on Items sum later
        
        # 4. Details / Flags
        payment_method = "Przelew" # Default
        bank_accounts_list = []
        
        # Platnosc
        platnosc = fa_node.find(".//Platnosc") if fa_node else None
        if platnosc:
             if platnosc.findtext("Zaplacono") == "1":
                 payment_method = "Gotówka/Inne" # Logic
        
        # Bank Account (often in Podmiot1 for Seller)
        # In KSeF, RachunekBankowy is under Podmiot1
        party_seller = root.find(".//Podmiot1")
        if party_seller:
             for acc in party_seller.findall(".//NrRachunku"):
                 if acc.text:
                     bank_accounts_list.append(acc.text)

        # Payment Deadline (TerminPlatnosci)
        deadline_date = None
        if platnosc:
            termin = platnosc.find(".//TerminPlatnosci") 
            # In FA(2), TerminPlatnosci field usually:
            # <TerminPlatnosci>
            #    <Termin>2023-11-25</Termin>
            # </TerminPlatnosci>
            if termin:
                 d_text = termin.findtext(".//Termin")
                 if d_text:
                     try:
                        deadline_date = datetime.strptime(d_text, "%Y-%m-%d").date()
                     except: pass
        
        # Footer Logic (Stopka) - Map first line to notes
        footer_notes = None
        footer_nodes = root.findall(".//Stopka/Informacje/StopkaFaktury")
        if footer_nodes:
            # Take the first one as requested
            if footer_nodes[0].text:
                footer_notes = footer_nodes[0].text

        # Construct Invoice
        # Note: Purchase invoices mostly imply standard VAT flow unless specific flags found.
        # We enforce TaxSystem.VAT strongly for downloaded KSeF invoices to avoid 'Ryczałt' columns in UI.
        target_tax_system = TaxSystem.VAT 
        
        invoice = Invoice(
            number=inv_number,
            ksef_xml=xml_str,
            category=category,
            type=InvoiceType.VAT, # Logic needed for KOREKTA
            tax_system=target_tax_system,
            date_issue=date_issue,
            date_sale=date_sale,
            currency=currency, # Ensure model supports it!
            payment_method=payment_method,
            payment_deadline=deadline_date,
            bank_accounts="; ".join(bank_accounts_list) if bank_accounts_list else None,
            total_gross=gross_total,
            items=[],
            notes=footer_notes
        )
        invoice.contractor = contractor # Transient
        
        # 5. Items (FaWiersz)
        items = []
        item_map = {} # Map for grouping descriptions by line number logic if needed
        idx = 1
        for row in root.findall(".//FaWiersz"):
             try:
                 nr_wiersza_fa = row.findtext("NrWierszaFa")
                 
                 name = row.findtext("P_7")
                 qty = float(row.findtext("P_8B", "0").replace(',', '.'))
                 unit = row.findtext("P_8A", "szt")
                 net_price = float(row.findtext("P_9A", "0").replace(',', '.'))
                 # P_11 is Net Value
                 net_val_row = float(row.findtext("P_11", "0").replace(',', '.'))
                 
                 # P_12 is VAT Rate (integer or string like 'zw')
                 vat_s = row.findtext("P_12", "23")
                 vat_rate = 0.23
                 is_exempt_zw = False
                 
                 if vat_s.isdigit():
                     vat_rate = float(vat_s) / 100.0
                 elif vat_s.lower() == 'zw':
                     vat_rate = 0.0
                     is_exempt_zw = True
                 
                 gross_val_row = net_val_row * (1 + vat_rate)
                 
                 item = InvoiceItem(
                     index=idx,
                     product_name=name,
                     quantity=qty,
                     unit=unit,
                     net_price=net_price,
                     vat_rate=vat_rate,
                     gross_value=gross_val_row,
                     # We reuse 'pkwiu' column or another field to flag ZW transiently if not in model?
                     # Ideally we should modify model. But for transient logic, we can attach attribute.
                     # Or hijack pkwiu (not recommended but fast). 
                     pkwiu = "ZW" if is_exempt_zw else None 
                     # Note: pkwiu is nullable. 
                 )
                 # Attach transient flag for UI logic (won't serve via DB query unless we map it)
                 item.is_exempt_zw = is_exempt_zw 
                 items.append(item)
                 
                 # Store map for DodatkowyOpis
                 # Using nr_wiersza_fa if available, else idx (as string)
                 key_idx = str(nr_wiersza_fa) if nr_wiersza_fa else str(idx)
                 item_map[key_idx] = item

                 idx += 1
             except Exception as ex:
                 print(f"Item parse error: {ex}")

        # 6. Additional Item Descriptions (DodatkowyOpis)
        # Structure: <DodatkowyOpis><NrWiersza>1</NrWiersza><Klucz>...</Klucz><Wartosc>...</Wartosc></DodatkowyOpis>
        for desc in root.findall(".//DodatkowyOpis"):
            try:
                nr = desc.findtext("NrWiersza")
                key = desc.findtext("Klucz")
                val = desc.findtext("Wartosc")
                if nr in item_map:
                    item_map[nr].description_key = key
                    item_map[nr].description_value = val
            except: pass

        invoice.items = items
        return invoice

    @staticmethod
    def update_invoice_from_xml(invoice_db: Invoice, xml_str: str):
        """
        Updates an existing DB Invoice object with data parsed from its XML.
        Use this for 'Repair' or 'Sync'.
        """
        temp_inv = KsefLogic.parse_xml_to_invoice(xml_str, invoice_db.category)
        
        # Sync simple fields
        if not invoice_db.payment_deadline:
            invoice_db.payment_deadline = temp_inv.payment_deadline
        
        if not invoice_db.bank_account:
            invoice_db.bank_account = temp_inv.bank_account
            
        # Sync Items if empty
        if not invoice_db.items:
            for it in temp_inv.items:
                # Must re-instantiate to avoid session conflicts if temp_inv not bound
                new_it = InvoiceItem(
                     invoice_id=invoice_db.id,
                     index=it.index,
                     product_name=it.product_name,
                     quantity=it.quantity,
                     unit=it.unit,
                     net_price=it.net_price,
                     vat_rate=it.vat_rate,
                     gross_value=it.gross_value
                )
                # invoice_db.items.append(new_it) # SQLAlchemy relationship
                # Or return items to be added manually
                pass
        return temp_inv

    @staticmethod
    def save_invoice_from_xml(session, invoice_id: int):
        """
        Repairs/Updates a specific invoice ID in the database by re-parsing its KSeF XML.
        Commits changes to the session.
        """
        inv = session.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not inv or not inv.ksef_xml:
            return None
        
        # 1. Parse into transient object
        parsed = KsefLogic.parse_xml_to_invoice(inv.ksef_xml, inv.category)
        
        # 2. Update Header Fields if missing
        if not inv.payment_deadline: inv.payment_deadline = parsed.payment_deadline
        if not inv.tax_system or inv.tax_system == TaxSystem.RYCZALT:
             # FIX: Force VAT system for synced KSeF invoices if they were wrongly defaulted to Ryczalt
             inv.tax_system = TaxSystem.VAT
             
        if not inv.payment_method or inv.payment_method == "Przelew": 
             # Only override if we found something specific? Or just trust parsed?
             if parsed.payment_method != "Przelew": inv.payment_method = parsed.payment_method
        if not inv.bank_accounts: inv.bank_accounts = parsed.bank_accounts
        
        # Note: dates in parsed are Dates, DB are DateTimes. 
        # SQLAlchemy usually handles date->datetime roughly, but explicit cast is safer.
        # But for now assuming compatibility or parsed.date_issue is datetime.date.
        
        # 3. Update/Re-create Items if empty
        # Check count
        if not inv.items:
            for item in parsed.items:
                new_item = InvoiceItem(
                    invoice_id=inv.id,
                    index=item.index,
                    product_name=item.product_name,
                    quantity=item.quantity,
                    unit=item.unit,
                    net_price=item.net_price,
                    vat_rate=item.vat_rate,
                    gross_value=item.gross_value,
                    pkwiu=item.pkwiu
                )
                session.add(new_item)
        
        session.commit()
        return inv
