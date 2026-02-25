from datetime import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom
from gui_qt.utils import sanitize_text

class KsefXmlGenerator:
    def generate_invoice_xml(self, invoice, company_config):
        """
        Generuje treść XML dla faktury zgodnie ze schemą KSeF FA(3).
        invoice: obiekt modelu Invoice
        company_config: obiekt modelu CompanyConfig (Sprzedawca)
        """
        
        # Helper functions for text sanitization
        clean = lambda s: sanitize_text(str(s) if s is not None else "", multiline=False)
        clean_ml = lambda s: sanitize_text(str(s) if s is not None else "", multiline=True)
        
        # Namespaces
        NS_KSEF = "http://crd.gov.pl/wzor/2025/06/25/13775/"
        NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"
        
        ET.register_namespace('', NS_KSEF)
        ET.register_namespace('xsi', NS_XSI)
        
        root = ET.Element(f"{{{NS_KSEF}}}Faktura")
        # root.set(f"{{{NS_XSI}}}schemaLocation", "http://crd.gov.pl/wzor/2025/06/25/13775/ schemat.xsd")
        
        # --- Naglowek ---
        naglowek = ET.SubElement(root, f"{{{NS_KSEF}}}Naglowek")
        kod = ET.SubElement(naglowek, f"{{{NS_KSEF}}}KodFormularza")
        kod.text = "FA"
        kod.set("kodSystemowy", "FA (3)")
        kod.set("wersjaSchemy", "1-0E")
        
        wariant = ET.SubElement(naglowek, f"{{{NS_KSEF}}}WariantFormularza")
        wariant.text = "3"
        
        data_wyt = ET.SubElement(naglowek, f"{{{NS_KSEF}}}DataWytworzeniaFa")
        data_wyt.text = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

        ET.SubElement(naglowek, f"{{{NS_KSEF}}}SystemInfo").text = "KSeF Invoice Linux"

        # --- Helper: Resolve Entity Data (Snapshot or Live) ---
        def get_entity_data(snapshot, live_obj, is_company_config=False):
            data = {}
            if snapshot:
                data['nip'] = snapshot.get('nip')
                data['name'] = snapshot.get('company_name') if is_company_config else snapshot.get('name')
                data['country_code'] = snapshot.get('country_code', 'PL')
                data['address'] = snapshot.get('address')
                data['postal'] = snapshot.get('postal_code')
                data['city'] = snapshot.get('city')
                data['bank_account'] = snapshot.get('bank_account') # Only mostly for seller
            else:
                if is_company_config:
                    data['nip'] = live_obj.nip
                    data['name'] = live_obj.company_name
                    data['country_code'] = live_obj.country_code
                    data['address'] = live_obj.address
                    data['postal'] = live_obj.postal_code
                    data['city'] = live_obj.city
                    data['bank_account'] = live_obj.bank_account
                elif live_obj: # Contractor
                    data['nip'] = live_obj.nip
                    data['name'] = live_obj.name
                    data['country_code'] = live_obj.country_code
                    data['address'] = live_obj.address
                    data['postal'] = live_obj.postal_code
                    data['city'] = live_obj.city
                    data['bank_account'] = None
            return data

        seller_data = get_entity_data(invoice.seller_snapshot, company_config, is_company_config=True)
        buyer_data = get_entity_data(invoice.buyer_snapshot, invoice.contractor, is_company_config=False)

        # --- Podmiot1 (Sprzedawca) ---
        p1 = ET.SubElement(root, f"{{{NS_KSEF}}}Podmiot1")
        dane_p1 = ET.SubElement(p1, f"{{{NS_KSEF}}}DaneIdentyfikacyjne")
        ET.SubElement(dane_p1, f"{{{NS_KSEF}}}NIP").text = clean((seller_data['nip'] or "").replace("-", ""))
        ET.SubElement(dane_p1, f"{{{NS_KSEF}}}Nazwa").text = clean(seller_data['name'])
        
        adres_p1 = ET.SubElement(p1, f"{{{NS_KSEF}}}Adres")
        ET.SubElement(adres_p1, f"{{{NS_KSEF}}}KodKraju").text = clean(seller_data['country_code'] or "PL")
        # Note: AdresL1 used for simplified address output
        ET.SubElement(adres_p1, f"{{{NS_KSEF}}}AdresL1").text = clean(f"{seller_data['address'] or ''} {seller_data['postal'] or ''} {seller_data['city'] or ''}")
        
        # Prepare Bank Account variable for later use
        acc_val = invoice.bank_account_number or seller_data.get('bank_account')

        # --- Podmiot2 (Nabywca) ---
        p2 = ET.SubElement(root, f"{{{NS_KSEF}}}Podmiot2")
        dane_p2 = ET.SubElement(p2, f"{{{NS_KSEF}}}DaneIdentyfikacyjne")
        
        if buyer_data.get('nip'):
             ET.SubElement(dane_p2, f"{{{NS_KSEF}}}NIP").text = clean((buyer_data['nip']).replace("-", ""))
             
        ET.SubElement(dane_p2, f"{{{NS_KSEF}}}Nazwa").text = clean(buyer_data['name'])
             
        adres_p2 = ET.SubElement(p2, f"{{{NS_KSEF}}}Adres")
        ET.SubElement(adres_p2, f"{{{NS_KSEF}}}KodKraju").text = clean(buyer_data['country_code'] or "PL")
        ET.SubElement(adres_p2, f"{{{NS_KSEF}}}AdresL1").text = clean(f"{buyer_data['address'] or ''} {buyer_data['postal'] or ''} {buyer_data['city'] or ''}")
             
        # Additional Podmiot2 details
        # Hardcoded based on user example success
        ET.SubElement(p2, f"{{{NS_KSEF}}}JST").text = "2" # Example
        ET.SubElement(p2, f"{{{NS_KSEF}}}GV").text = "2"

        # --- Fa (Dane Faktury) ---
        fa = ET.SubElement(root, f"{{{NS_KSEF}}}Fa")
        ET.SubElement(fa, f"{{{NS_KSEF}}}KodWaluty").text = clean(invoice.currency or "PLN")
        ET.SubElement(fa, f"{{{NS_KSEF}}}P_1").text = invoice.date_issue.strftime("%Y-%m-%d") # Data wystawienia
        if invoice.place_of_issue:
             ET.SubElement(fa, f"{{{NS_KSEF}}}P_1M").text = clean(invoice.place_of_issue)
        ET.SubElement(fa, f"{{{NS_KSEF}}}P_2").text = clean(invoice.number) # Numer
        ET.SubElement(fa, f"{{{NS_KSEF}}}P_6").text = invoice.date_sale.strftime("%Y-%m-%d") # Data sprzedazy
        
        # Aggregation Logic
        agg_net = {'23': 0.0, '8': 0.0, '5': 0.0, 'zw': 0.0, 'other': 0.0}
        agg_vat = {'23': 0.0, '8': 0.0, '5': 0.0, 'zw': 0.0, 'other': 0.0}

        for item in invoice.items:
             # Determine rate key
             r_key = '23' # Default
             rate_val = item.vat_rate
             
             if rate_val == 0.0:
                 is_zw = False
                 # Check explicit name first (Preferred)
                 if getattr(item, 'vat_rate_name', None) and "ZW" in item.vat_rate_name.upper():
                      is_zw = True
                 # Fallback
                 elif getattr(item, 'pkwiu', '') == "ZW" or getattr(invoice, 'is_exempt', False):
                      is_zw = True

                 if is_zw:
                     r_key = 'zw'
                 else:
                     r_key = 'other' # 0% not ZW
             elif abs(rate_val - 0.08) < 0.01:
                 r_key = '8'
             elif abs(rate_val - 0.05) < 0.01:
                 r_key = '5'
             elif abs(rate_val - 0.23) < 0.01:
                 r_key = '23'
             
             net_val = item.quantity * item.net_price
             # Calculate VAT based on item rate (if 0, it's 0)
             vat_val = net_val * rate_val
             
             agg_net[r_key] += net_val
             agg_vat[r_key] += vat_val

        # Populate Aggregates
        if agg_net['23'] > 0 or agg_vat['23'] > 0:
             ET.SubElement(fa, f"{{{NS_KSEF}}}P_13_1").text = f"{agg_net['23']:.2f}"
             ET.SubElement(fa, f"{{{NS_KSEF}}}P_14_1").text = f"{agg_vat['23']:.2f}"
        
        if agg_net['8'] > 0 or agg_vat['8'] > 0:
             ET.SubElement(fa, f"{{{NS_KSEF}}}P_13_2").text = f"{agg_net['8']:.2f}"
             ET.SubElement(fa, f"{{{NS_KSEF}}}P_14_2").text = f"{agg_vat['8']:.2f}"
             
        if agg_net['5'] > 0 or agg_vat['5'] > 0:
             ET.SubElement(fa, f"{{{NS_KSEF}}}P_13_3").text = f"{agg_net['5']:.2f}"
             ET.SubElement(fa, f"{{{NS_KSEF}}}P_14_3").text = f"{agg_vat['5']:.2f}"

        if agg_net['zw'] > 0:
             ET.SubElement(fa, f"{{{NS_KSEF}}}P_13_6_1").text = f"{agg_net['zw']:.2f}"
        
        # Total Gross (P_15) - Must use dot separator
        ET.SubElement(fa, f"{{{NS_KSEF}}}P_15").text = f"{invoice.total_gross:.2f}"

        # Adnotacje 
        adnotacje = ET.SubElement(fa, f"{{{NS_KSEF}}}Adnotacje")
        ET.SubElement(adnotacje, f"{{{NS_KSEF}}}P_16").text = "1" if invoice.is_cash_accounting else "2"
        ET.SubElement(adnotacje, f"{{{NS_KSEF}}}P_17").text = "1" if invoice.is_self_billing else "2"
        ET.SubElement(adnotacje, f"{{{NS_KSEF}}}P_18").text = "1" if invoice.is_reverse_charge else "2"
        ET.SubElement(adnotacje, f"{{{NS_KSEF}}}P_18A").text = "1" if invoice.is_split_payment else "2"
        
        # Zwolnienie
        if invoice.is_exempt:
             zw = ET.SubElement(adnotacje, f"{{{NS_KSEF}}}Zwolnienie")
             ET.SubElement(zw, f"{{{NS_KSEF}}}P_19").text = "1"
             # Basis
             basis = getattr(company_config, 'vat_exemption_basis', '') or "Art. 43 ust. 1" 
             # Or from invoice if stored
             ET.SubElement(zw, f"{{{NS_KSEF}}}P_19A").text = basis
        else:
             zw = ET.SubElement(adnotacje, f"{{{NS_KSEF}}}Zwolnienie")
             ET.SubElement(zw, f"{{{NS_KSEF}}}P_19N").text = "1"
             
        # New Means of Transport - Default Negative
        nst = ET.SubElement(adnotacje, f"{{{NS_KSEF}}}NoweSrodkiTransportu")
        ET.SubElement(nst, f"{{{NS_KSEF}}}P_22N").text = "1" 
        
        ET.SubElement(adnotacje, f"{{{NS_KSEF}}}P_23").text = "2"
        
        # Margin - Default Negative
        pm = ET.SubElement(adnotacje, f"{{{NS_KSEF}}}PMarzy")
        ET.SubElement(pm, f"{{{NS_KSEF}}}P_PMarzyN").text = "1"

        # RodzajFaktury (VAT, KOR, ZAL, ROZ...)
        inv_type_enum = invoice.type
        is_kor = False
        k_val = "VAT"
        
        # Determine Kind
        from database.models import InvoiceType
        if inv_type_enum == InvoiceType.KOREKTA: 
             k_val = "KOR"
             is_kor = True
        elif inv_type_enum == InvoiceType.ZALICZKA:
             k_val = "ZAL"
        elif inv_type_enum == InvoiceType.RYCZALT:
             k_val = "VAT" # Ryczałt usually reported as VAT type in FA(2) but specific fields filled? or just VAT.
             # Actually RYCZAŁT often implies simplified or spec. logic, but "VAT" is standard unless specific "UPR"?
             pass
             
        ET.SubElement(fa, f"{{{NS_KSEF}}}RodzajFaktury").text = k_val
        
        # --- KOR Details ---
        if is_kor:
             # Przyczyna (Optional but nice)
             if invoice.correction_reason:
                  ET.SubElement(fa, f"{{{NS_KSEF}}}PrzyczynaKorekty").text = clean_ml(invoice.correction_reason)
             
             # TypKorekty (1, 2, 3)
             # User prompt implies: 1, 2. KSeF defines: 1=Scenariusz A (pierwotna), 2=Scenariusz B (bieżąca)
             # Default to 1 if not set? Or skip if optional?
             # User prompt: "<TypKorekty>1</TypKorekty>"
             if invoice.correction_type:
                  ET.SubElement(fa, f"{{{NS_KSEF}}}TypKorekty").text = str(invoice.correction_type)
             
             # DaneFaKorygowanej
             dfk = ET.SubElement(fa, f"{{{NS_KSEF}}}DaneFaKorygowanej")
             
             # 1. DataWystFaKorygowanej (Obowiązkowe)
             # Get parent date for correction reference
             p_date = invoice.parent.date_issue if invoice.parent else invoice.date_issue
             date_val = p_date.strftime("%Y-%m-%d")
             ET.SubElement(dfk, f"{{{NS_KSEF}}}DataWystFaKorygowanej").text = date_val

             # 2. NrFaKorygowanej (Obowiązkowe - numer własny faktury korygowanej)
             # Replaces older P_2RE field
             p_nr = clean(invoice.related_invoice_number or "BRAK")
             ET.SubElement(dfk, f"{{{NS_KSEF}}}NrFaKorygowanej").text = p_nr
             
             # 3. Choice: KSeF Number vs No KSeF Number
             if invoice.related_ksef_number:
                  # Case A: Invoice exists in KSeF
                  # Flag "1"
                  ET.SubElement(dfk, f"{{{NS_KSEF}}}NrKSeF").text = "1"
                  # Actual Number
                  ET.SubElement(dfk, f"{{{NS_KSEF}}}NrKSeFFaKorygowanej").text = clean(invoice.related_ksef_number)
             else:
                  # Case B: Invoice outside KSeF (e.g. historical or foreign)
                  ET.SubElement(dfk, f"{{{NS_KSEF}}}NrKSeFN").text = "1"

        # DodatkowyOpis dla Wierszy
        # Wymaga w modelu items atrybutów: description_key, description_value lub podobnych (np. w JSON/polu)
        # Tutaj zakładamy, że jeśli w itemie są te pola, to je dodajemy.
        sorted_items = sorted(invoice.items, key=lambda x: x.index if x.index else 0)
        for i, item in enumerate(sorted_items, start=1):
            # Check for generic description or specific additional info
            desc_key = getattr(item, 'description_key', None)
            desc_val = getattr(item, 'description_value', None)
                
            if desc_key and desc_val:
                dod_opis = ET.SubElement(fa, f"{{{NS_KSEF}}}DodatkowyOpis")
                ET.SubElement(dod_opis, f"{{{NS_KSEF}}}NrWiersza").text = str(i)
                ET.SubElement(dod_opis, f"{{{NS_KSEF}}}Klucz").text = clean(desc_key)
                ET.SubElement(dod_opis, f"{{{NS_KSEF}}}Wartosc").text = clean(desc_val)

        # --- Items (FaWiersz) ---
        # Generate FaWiersz INSIDE Fa (before Platnosc)
        for i, item in enumerate(sorted_items, start=1):
            wiersz = ET.SubElement(fa, f"{{{NS_KSEF}}}FaWiersz")
            ET.SubElement(wiersz, f"{{{NS_KSEF}}}NrWierszaFa").text = str(i)
            # P_7: Nazwa (Name)
            p7_val = (item.product_name or "Towar/Usługa")
            ET.SubElement(wiersz, f"{{{NS_KSEF}}}P_7").text = clean(p7_val)
            # P_8A: Miara (Unit)
            p8a_val = (item.unit or "szt.")
            ET.SubElement(wiersz, f"{{{NS_KSEF}}}P_8A").text = clean(p8a_val)
            # P_8B: Ilosc (Qty)
            ET.SubElement(wiersz, f"{{{NS_KSEF}}}P_8B").text = f"{item.quantity:.2f}"
            # P_9A: Cena jedn netto (Net Price)
            ET.SubElement(wiersz, f"{{{NS_KSEF}}}P_9A").text = f"{item.net_price:.2f}" 
            # P_11: Wartosc netto (Net Value)
            net_val_line = item.quantity * item.net_price
            ET.SubElement(wiersz, f"{{{NS_KSEF}}}P_11").text = f"{net_val_line:.2f}"
            
            # Rate Code for Line Item
            rate_xml = "23"
            if item.vat_rate == 0.0:
                 pkwiu = (getattr(item, 'pkwiu', '') or "").upper()
                 if pkwiu == "ZW" or invoice.is_exempt:
                     rate_xml = "zw"
                 else:
                     rate_xml = "0"
            elif abs(item.vat_rate - 0.08) < 0.01:
                 rate_xml = "8"
            elif abs(item.vat_rate - 0.05) < 0.01:
                rate_xml = "5"
             
            ET.SubElement(wiersz, f"{{{NS_KSEF}}}P_12").text = rate_xml

        # Platnosc Logic Calculations (Moved up for Rozliczenia access)
        def get_pm_info(name):
             # Returns (code, is_immediate)
             n = (name or "").lower()
             if "gotówka" in n or "gotowka" in n: return "1", True
             if "karta" in n: return "2", True
             if "bon" in n: return "3", True
             if "czek" in n: return "4", False
             if "kredyt" in n: return "5", False
             if "przelew" in n: return "6", False
             if "mobilna" in n or "blik" in n: return "7", True
             return "6", False # Default Przelew

        # Collect breakdowns
        breakdowns = []
        if invoice.payment_method and "mieszana" in invoice.payment_method.lower() and invoice.payment_breakdowns:
            for pb in invoice.payment_breakdowns:
                code, is_imm = get_pm_info(pb.payment_method)
                breakdowns.append({'code': code, 'is_imm': is_imm, 'amount': pb.amount, 'method_name': pb.payment_method})
        else:
            # Single method
            code, is_imm = get_pm_info(invoice.payment_method)
            if invoice.is_paid and not is_imm:
                 is_imm = True
            breakdowns.append({'code': code, 'is_imm': is_imm, 'amount': invoice.total_gross, 'method_name': invoice.payment_method})

        # Calculate totals
        total_paid_imm = sum(b['amount'] for b in breakdowns if b['is_imm'])
        total_deferred = sum(b['amount'] for b in breakdowns if not b['is_imm'])
        
        # Determine scenario
        is_fully_paid = (total_deferred <= 0.01)
        is_partially_paid = (total_deferred > 0.01 and total_paid_imm > 0.01)
        
        payment_date = getattr(invoice, 'payment_date', None) or invoice.date_issue

        # Rozliczenie (Check if needed - adding boilerplate for validation if required)
        # Assuming simple structure for now as per user reference "DoRozliczenia=0"
        rozliczenie_el = ET.SubElement(fa, f"{{{NS_KSEF}}}Rozliczenie")
        # Logic: If fully paid, simple 0. If not, diff.
        to_pay = max(0.0, total_deferred)
        ET.SubElement(rozliczenie_el, f"{{{NS_KSEF}}}DoRozliczenia").text = f"{to_pay:.2f}" if to_pay > 0 else "0"

        # Platnosc XML Generation
        platnosc = ET.SubElement(fa, f"{{{NS_KSEF}}}Platnosc")

        if is_fully_paid:
            # Check for multiple methods
            imm_methods = [b for b in breakdowns if b['is_imm']]
            if len(imm_methods) > 1:
                # Scenario: Paid in Full via parts/mixed
                ET.SubElement(platnosc, f"{{{NS_KSEF}}}ZnacznikZaplatyCzesciowej").text = "2"
                for b in imm_methods:
                    zp = ET.SubElement(platnosc, f"{{{NS_KSEF}}}ZaplataCzesciowa")
                    ET.SubElement(zp, f"{{{NS_KSEF}}}KwotaZaplatyCzesciowej").text = f"{b['amount']:.2f}"
                    ET.SubElement(zp, f"{{{NS_KSEF}}}DataZaplatyCzesciowej").text = payment_date.strftime("%Y-%m-%d")
                    ET.SubElement(zp, f"{{{NS_KSEF}}}FormaPlatnosci").text = b['code']
            else:
                # Scenario: Simple Paid (Single method, or inferred single)
                ET.SubElement(platnosc, f"{{{NS_KSEF}}}Zaplacono").text = "1"
                ET.SubElement(platnosc, f"{{{NS_KSEF}}}DataZaplaty").text = payment_date.strftime("%Y-%m-%d")
        
        elif is_partially_paid:
            # Scenario: Mixed (Partial Pay + Deferred)
            ET.SubElement(platnosc, f"{{{NS_KSEF}}}ZnacznikZaplatyCzesciowej").text = "1"
            imm_methods = [b for b in breakdowns if b['is_imm']]
            for b in imm_methods:
                zp = ET.SubElement(platnosc, f"{{{NS_KSEF}}}ZaplataCzesciowa")
                ET.SubElement(zp, f"{{{NS_KSEF}}}KwotaZaplatyCzesciowej").text = f"{b['amount']:.2f}"
                ET.SubElement(zp, f"{{{NS_KSEF}}}DataZaplatyCzesciowej").text = payment_date.strftime("%Y-%m-%d")
                ET.SubElement(zp, f"{{{NS_KSEF}}}FormaPlatnosci").text = b['code']
        
        # Termin (Deadline) - only if pending amount exists
        # Also generate if strictly deferred (is_fully_paid=False and not is_partially_paid)
        # Essentially if total_deferred > 0.01
        
        if total_deferred > 0.01:
             if invoice.payment_deadline:
                 terminy = ET.SubElement(platnosc, f"{{{NS_KSEF}}}TerminPlatnosci")
                 ET.SubElement(terminy, f"{{{NS_KSEF}}}Termin").text = invoice.payment_deadline.strftime("%Y-%m-%d")

        # Global FormaPlatnosci
        deferred_methods = [b for b in breakdowns if not b['is_imm']]
        
        global_code = None
        if deferred_methods:
            global_code = deferred_methods[0]['code']
        elif is_fully_paid and len(breakdowns) == 1:
            global_code = breakdowns[0]['code']
            
        if global_code:
             ET.SubElement(platnosc, f"{{{NS_KSEF}}}FormaPlatnosci").text = global_code

        # RachunekBankowy (Included even if paid, as per user request/example)
        if acc_val:
              # Keep only digits - strictly numeric for KSeF NrRB
              raw_acc = acc_val.split(';')[0]
              acc_clean = "".join(filter(str.isdigit, raw_acc))
              
              # Truncate to KSeF MAX LENGTH (usually 28 characters for IBAN) 
              # Standard PL NRB is 26, PL+26=28. Some might be 32 (rare).
              # The provided 30 digit one is invalid but we should at least not exceed max length allowed if any.
              # However, truncating blindly is bad. We just pass the cleaned digits.
              # The user must fix their data.
              
              if acc_clean:
                  rb = ET.SubElement(platnosc, f"{{{NS_KSEF}}}RachunekBankowy")
                  ET.SubElement(rb, f"{{{NS_KSEF}}}NrRB").text = acc_clean
                  if hasattr(company_config, 'swift_code') and company_config.swift_code:
                       ET.SubElement(rb, f"{{{NS_KSEF}}}SWIFT").text = company_config.swift_code
                  if getattr(company_config, 'bank_name', None):
                       ET.SubElement(rb, f"{{{NS_KSEF}}}NazwaBanku").text = company_config.bank_name

        # --- Stopka ---
        stopka = ET.SubElement(root, f"{{{NS_KSEF}}}Stopka")
        
        # Informacje (Bank info etc.)
        info_list = []
        
        # NOTE: Bank info removed from here as per KSeF requirements (it is in RachunekBankowy)
        
        if getattr(company_config, 'share_capital', None):
             info_list.append(f"Kapitał zakładowy: {company_config.share_capital}")
             
        if getattr(company_config, 'court_info', None):
             info_list.append(f"Sąd: {company_config.court_info}")
             
        # New: Footer Extra (Stopka 2)
        if getattr(company_config, 'footer_extra', None):
             info_list.append(company_config.footer_extra)
             
        # Add Invoice Notes as separate info
        if invoice.notes:
             info_list.append(invoice.notes)

        # Generate XML elements for each info
        for info_txt in info_list:
             if info_txt:
                 inf_node = ET.SubElement(stopka, f"{{{NS_KSEF}}}Informacje")
                 ET.SubElement(inf_node, f"{{{NS_KSEF}}}StopkaFaktury").text = info_txt

        # Rejestry
        has_regs = False
        rejestry = ET.SubElement(stopka, f"{{{NS_KSEF}}}Rejestry")
        
        if getattr(company_config, 'krs', None):
             ET.SubElement(rejestry, f"{{{NS_KSEF}}}KRS").text = company_config.krs
             has_regs = True
             
        if company_config.regon:
             ET.SubElement(rejestry, f"{{{NS_KSEF}}}REGON").text = company_config.regon
             has_regs = True
             
        if getattr(company_config, 'bdo', None):
             ET.SubElement(rejestry, f"{{{NS_KSEF}}}BDO").text = company_config.bdo
             has_regs = True
             
        if not has_regs:
             stopka.remove(rejestry)
             
        if not has_regs and not info_list:
             root.remove(stopka)

        # Pretty Print
        xml_str = ET.tostring(root, encoding='utf-8')
        try:
             parsed = minidom.parseString(xml_str)
             # Force UTF-8 encoding declaration
             return parsed.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")
        except:
             return xml_str.decode('utf-8') if isinstance(xml_str, bytes) else xml_str
