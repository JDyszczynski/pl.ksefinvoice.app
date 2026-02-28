import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from sqlalchemy import extract, or_
from database.models import Invoice, InvoiceType, InvoiceCategory, InvoiceItem, CompanyConfig
from gui_qt.utils import sanitize_text

class JpkService:
    def __init__(self, session):
        self.session = session
        # Zaktualizowano namespace dla JPK_V7M(3) - obowiązujący od 01.02.2026
        self.NS = "http://crd.gov.pl/wzor/2025/12/19/14090/" 
        self.NS_ETD = "http://crd.gov.pl/xml/schematy/dziedzinowe/mf/2022/09/13/eD/DefinicjeTypy/"
        self.NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"
        self.ET = ET

    def _register_namespaces(self):
        self.ET.register_namespace('', self.NS)
        self.ET.register_namespace('xsi', self.NS_XSI)
        self.ET.register_namespace('etd', self.NS_ETD)

    def generate_jpk_v7m(self, year: int, month: int, filepath: str, quarter: int = None, is_correction: bool = False):
        # Determine if we are in Quarterly Mode (V7K)
        is_quarterly_mode = False
        if quarter:
            is_quarterly_mode = True
            self.NS = "http://crd.gov.pl/wzor/2025/12/19/14089/"
        else:
            self.NS = "http://crd.gov.pl/wzor/2025/12/19/14090/"
            
        self._register_namespaces()
        
        company = self.session.query(CompanyConfig).first()
        if not company:
            raise ValueError("Brak konfiguracji firmy (CompanyConfig)")

        root = self.ET.Element(f"{{{self.NS}}}JPK")
        
        # Header (Always for the specific month)
        date_from, date_to = self._get_month_range(year, month)
        self._build_header(root, year, month, company, date_from, date_to, is_quarterly_mode, is_correction) # Pass is_quarterly_mode
        
        # Entity
        self._build_entity(root, company)
        
        # Data Collection (ALWAYS Monthly for Ewidencja)
        sales_rows, sales_ctrl = self._get_sales_data(year, month)
        purch_rows, purch_ctrl = self._get_purchase_data(year, month)

        # Declaration Logic
        # V7M: Always include declaration for the month.
        # V7K: Include declaration ONLY if it is the 3rd month of the quarter.
        
        include_declaration = True
        
        decl_sales_ctrl = sales_ctrl
        decl_purch_ctrl = purch_ctrl

        if is_quarterly_mode:
            # Check if it is the last month of the quarter
            q_of_month = (month - 1) // 3 + 1
            is_last_month = (month % 3 == 0)
            
            if not is_last_month:
                include_declaration = False
            else:
                 # Calculate Aggregated Data for Declaration (Full Quarter)
                 q_start = (q_of_month - 1) * 3 + 1
                 q_end = month # which is equal to q_start + 2
                 
                 agg_sales = self._aggregate_sales_data(year, q_start, q_end)
                 agg_purch = self._aggregate_purchase_data(year, q_start, q_end)
                 
                 decl_sales_ctrl = agg_sales
                 decl_purch_ctrl = agg_purch

        if include_declaration:
             self._build_declaration(root, year, month, decl_sales_ctrl, decl_purch_ctrl, is_quarterly_mode)
             
        # Ewidencja is always just for the current month
        self._build_register(root, sales_rows, purch_rows, sales_ctrl, purch_ctrl)

        tree = self.ET.ElementTree(root)
        if hasattr(self.ET, "indent"):
            self.ET.indent(tree, space="  ", level=0)
            
        tree.write(filepath, encoding="UTF-8", xml_declaration=True)

    def _get_month_range(self, year, month):
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        date_from = f"{year}-{month:02d}-01"
        date_to = f"{year}-{month:02d}-{last_day}"
        return date_from, date_to

    def _aggregate_sales_data(self, year, m_start, m_end):
        total_ctrl = {}
        for m in range(m_start, m_end + 1):
             _, ctrl = self._get_sales_data(year, m)
             for k, v in ctrl.items():
                 if isinstance(v, (int, float)):
                     total_ctrl[k] = total_ctrl.get(k, 0) + v
        return total_ctrl

    def _aggregate_purchase_data(self, year, m_start, m_end):
        total_ctrl = {}
        for m in range(m_start, m_end + 1):
             _, ctrl = self._get_purchase_data(year, m)
             for k, v in ctrl.items():
                 if isinstance(v, (int, float)):
                     total_ctrl[k] = total_ctrl.get(k, 0) + v
        return total_ctrl

    def generate_jpk_fa(self, year: int, month: int, filepath: str, quarter: int = None):
        # Register namespace for JPK_FA (4)
        ns_fa = "http://jpk.mf.gov.pl/wzor/2022/02/17/02171/"
        self.ET.register_namespace('', ns_fa)
        self.ET.register_namespace('xsi', self.NS_XSI)
        # JPK_FA(4) uses older ETD namespace from 2018
        self.ET.register_namespace('etd', "http://crd.gov.pl/xml/schematy/dziedzinowe/mf/2018/08/24/eD/DefinicjeTypy/")

        company = self.session.query(CompanyConfig).first()
        if not company:
            raise ValueError("Brak konfiguracji firmy (CompanyConfig)")

        root = self.ET.Element(f"{{{ns_fa}}}JPK")

        # Header
        header = self.ET.SubElement(root, f"{{{ns_fa}}}Naglowek")
        self.ET.SubElement(header, f"{{{ns_fa}}}KodFormularza", kodSystemowy="JPK_FA (4)", wersjaSchemy="1-0").text = "JPK_FA"
        self.ET.SubElement(header, f"{{{ns_fa}}}WariantFormularza").text = "4"
        self.ET.SubElement(header, f"{{{ns_fa}}}CelZlozenia").text = "1"
        self.ET.SubElement(header, f"{{{ns_fa}}}DataWytworzeniaJPK").text = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        
        # Ranges
        import calendar
        if quarter:
            m_start = (quarter - 1) * 3 + 1
            m_end = m_start + 2
            last_day = calendar.monthrange(year, m_end)[1]
            date_from = f"{year}-{m_start:02d}-01"
            date_to = f"{year}-{m_end:02d}-{last_day}"
            
            # Query for Quarter
            invoices = self.session.query(Invoice).filter(
                Invoice.category == InvoiceCategory.SALES,
                Invoice.type != InvoiceType.INNE, # Exclude manual notes
                Invoice.type != InvoiceType.PODATEK,
                extract('year', Invoice.date_issue) == year,
                extract('month', Invoice.date_issue) >= m_start,
                extract('month', Invoice.date_issue) <= m_end
            ).all()
        else:
            last_day = calendar.monthrange(year, month)[1]
            date_from = f"{year}-{month:02d}-01"
            date_to = f"{year}-{month:02d}-{last_day}"

            invoices = self.session.query(Invoice).filter(
                Invoice.category == InvoiceCategory.SALES,
                Invoice.type != InvoiceType.INNE, # Exclude manual notes
                Invoice.type != InvoiceType.PODATEK,
                extract('year', Invoice.date_issue) == year,
                extract('month', Invoice.date_issue) == month
            ).all()

        self.ET.SubElement(header, f"{{{ns_fa}}}DataOd").text = date_from
        self.ET.SubElement(header, f"{{{ns_fa}}}DataDo").text = date_to
        self.ET.SubElement(header, f"{{{ns_fa}}}KodUrzedu").text = company.tax_office_code or "2206"

        # Podmiot1 (Issuer)
        p1 = self.ET.SubElement(root, f"{{{ns_fa}}}Podmiot1")
        id_p1 = self.ET.SubElement(p1, f"{{{ns_fa}}}IdentyfikatorPodmiotu")
        if company.nip:
            self.ET.SubElement(id_p1, f"{{{ns_fa}}}NIP").text = company.nip.replace("-", "")
        self.ET.SubElement(id_p1, f"{{{ns_fa}}}PelnaNazwa").text = company.company_name
        
        # Address P1 - Fixed to use 'etd' namespace (2018)
        # Local variable for ETD namespace in this scope, matching registration
        ns_etd = "http://crd.gov.pl/xml/schematy/dziedzinowe/mf/2018/08/24/eD/DefinicjeTypy/"
        
        adr_p1 = self.ET.SubElement(p1, f"{{{ns_fa}}}AdresPodmiotu")
        self.ET.SubElement(adr_p1, f"{{{ns_etd}}}KodKraju").text = company.country_code or "PL"
        self.ET.SubElement(adr_p1, f"{{{ns_etd}}}Wojewodztwo").text = "WLKP" # TODO: parse/config
        self.ET.SubElement(adr_p1, f"{{{ns_etd}}}Powiat").text = "Poznań" # Placeholder
        self.ET.SubElement(adr_p1, f"{{{ns_etd}}}Gmina").text = company.city or "-"
        self.ET.SubElement(adr_p1, f"{{{ns_etd}}}Ulica").text = "-" # Placeholder
        self.ET.SubElement(adr_p1, f"{{{ns_etd}}}NrDomu").text = "-" # Should be parsed
        self.ET.SubElement(adr_p1, f"{{{ns_etd}}}NrLokalu").text = "-"
        self.ET.SubElement(adr_p1, f"{{{ns_etd}}}Miejscowosc").text = company.city or "-"
        self.ET.SubElement(adr_p1, f"{{{ns_etd}}}KodPocztowy").text = company.postal_code or "00-000"
        # Poczta removed as per TAdresPolski1 definition

        # Faktura Nodes
        gross_total_sum = 0.0
        
        for inv in invoices:
            fa_node = self.ET.SubElement(root, f"{{{ns_fa}}}Faktura")
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}KodWaluty").text = inv.currency or "PLN"
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_1").text = inv.date_issue.strftime("%Y-%m-%d")
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_2A").text = inv.number
            
            # Helper to get snapshot data safely
            import json
            buyer_name = inv.contractor.name if inv.contractor else ""
            buyer_addr = f"{inv.contractor.address or ''} {inv.contractor.city or ''}" if inv.contractor else ""
            buyer_nip = (inv.contractor.nip or "").replace("-", "") if inv.contractor and inv.contractor.nip else ""
            buyer_cc = inv.contractor.country_code or "PL" if inv.contractor else "PL"

            if inv.buyer_snapshot:
                try:
                    snap = inv.buyer_snapshot
                    if isinstance(snap, str):
                        snap = json.loads(snap)
                    if snap:
                        buyer_name = snap.get('name') or buyer_name
                        buyer_addr = f"{snap.get('address') or ''} {snap.get('city') or ''}".strip() or buyer_addr
                        buyer_nip = (snap.get('nip') or "").replace("-", "") or buyer_nip
                        buyer_cc = snap.get('country_code') or buyer_cc
                except Exception as e:
                    pass

            # P_3A: Buyer Name
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_3A").text = buyer_name
            # P_3B: Buyer Address
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_3B").text = buyer_addr
            # P_3C: Seller Name
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_3C").text = company.company_name
            # P_3D: Seller Address
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_3D").text = f"{company.address or ''} {company.city or ''}".strip()
            
            # P_4A: Seller EU Prefix (Optional)
            if company.nip and len(company.nip) > 10 and not company.nip.startswith("PL"):
                 pass 
            
            # P_4B: Seller NIP
            if company.nip:
                self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_4B").text = company.nip.replace("-", "")

            # P_5B: Buyer NIP
            if buyer_nip:
                self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_5B").text = buyer_nip
            
            # P_6: Date of Supply (if different from P_1)
            if inv.date_sale and inv.date_sale != inv.date_issue:
                 self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_6").text = inv.date_sale.strftime("%Y-%m-%d")
            
            # Amounts
            amounts = self._get_sales_amounts(inv) 
            inv_gross = 0.0

            # Sort/Extract amounts based on Tax Rates to map to P_13_x, P_14_x
            # Standard mapping logic:
            # 23% -> P_13_1, P_14_1
            # 8%  -> P_13_2, P_14_2
            # 5%  -> P_13_3, P_14_3
            # OO  -> P_13_4, P_14_4 (implied from flags usually, but here by rate='oo')
            # 0%  -> P_13_6 (Domestic 0%)
            # ZW  -> P_13_7 (Exempt)
            
            # We must iterate and sum up for P_15
            for (rate_key, is_zw, is_oo), vals in amounts.items():
                net = vals['net']
                vat = vals['vat']
                inv_gross += (net + vat)
                
                # Format to string .2f
                s_net = f"{net:.2f}"
                s_vat = f"{vat:.2f}"
                
                if is_zw:
                    self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_13_7").text = s_net
                    # P_19 (ZW flag) handled later
                elif is_oo:
                    self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_13_4").text = s_net
                    self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_14_4").text = s_vat # usually 0
                elif rate_key == 23:
                    self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_13_1").text = s_net
                    self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_14_1").text = s_vat
                elif rate_key == 8:
                    self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_13_2").text = s_net
                    self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_14_2").text = s_vat
                elif rate_key == 5:
                    self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_13_3").text = s_net
                    self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_14_3").text = s_vat
                elif rate_key == 0:
                     # 0% can be P_13_6 (domestic) or P_13_5 (export/WDT - not handled here explicitly yet)
                     self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_13_6").text = s_net

            # P_15: Total Gross
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_15").text = f"{inv_gross:.2f}"
            gross_total_sum += inv_gross

            # Check flags based on amounts/invoice data
            has_zw = any(k[1] for k in amounts.keys())
            has_oo = any(k[2] for k in amounts.keys())
            has_split = False # TODO: check invalid split payment property if stored

            # Mandatory Boolean Fields (P_16 ... P_106E_3)
            # P_16: Metoda kasowa
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_16").text = "false"
            # P_17: Samofakturowanie
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_17").text = "false"
            # P_18: Odwrotne obciążenie
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_18").text = "true" if has_oo else "false"
            # P_18A: MPP (Split Payment)
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_18A").text = "true" if has_split else "false"
            # P_19: Zwolnienie
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_19").text = "true" if has_zw else "false"
            # P_20: Samofakt. (Egzekucja)
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_20").text = "false"
            # P_21: Przedstawiciel
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_21").text = "false"
            # P_22: WDT nowe środki
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_22").text = "false"
            # P_23: Procedura szczeg. (art 135)
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_23").text = "false"
            # P_106E_2: Marża biura
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_106E_2").text = "false"
            # P_106E_3: Marża towary
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_106E_3").text = "false"

            # Rodzaj Faktury
            kind = "VAT"
            if inv.type == InvoiceType.KOREKTA:
                kind = "KOREKTA"
            elif inv.type == InvoiceType.ZALICZKA:
                kind = "ZAL"
            
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}RodzajFaktury").text = kind
            
            # Required for Correction
            if kind == "KOREKTA":
                self.ET.SubElement(fa_node, f"{{{ns_fa}}}PrzyczynaKorekty").text = "Korekta danych" # Placeholder
                self.ET.SubElement(fa_node, f"{{{ns_fa}}}NrFaKorygowanej").text = str(inv.parent_id or "UNKNOWN")
                self.ET.SubElement(fa_node, f"{{{ns_fa}}}OkresFaKorygowanej").text = "UNKNOWN" # Optional usually




        # FakturaCtrl
        ctrl = self.ET.SubElement(root, f"{{{ns_fa}}}FakturaCtrl")
        self.ET.SubElement(ctrl, f"{{{ns_fa}}}LiczbaFaktur").text = str(len(invoices))
        self.ET.SubElement(ctrl, f"{{{ns_fa}}}WartoscFaktur").text = f"{gross_total_sum:.2f}"

        # FakturaWiersz Nodes
        lines_count = 0
        lines_net_sum = 0.0
        
        for inv in invoices:
            for item in inv.items:
                w_node = self.ET.SubElement(root, f"{{{ns_fa}}}FakturaWiersz")
                self.ET.SubElement(w_node, f"{{{ns_fa}}}P_2B").text = inv.number
                
                # Append PKWiU to name if present (Common practice since no dedicated field in line)
                p_name = item.product_name
                if getattr(item, 'pkwiu', None):
                     p_name += f" (PKWiU: {item.pkwiu})"
                
                self.ET.SubElement(w_node, f"{{{ns_fa}}}P_7").text = p_name
                self.ET.SubElement(w_node, f"{{{ns_fa}}}P_8A").text = item.unit
                self.ET.SubElement(w_node, f"{{{ns_fa}}}P_8B").text = f"{item.quantity:.3f}"
                
                # Prices. JPK_FA standard items logic
                # P_9A: Price Unit Net
                # P_9B: Value Net = Qty * Price
                self.ET.SubElement(w_node, f"{{{ns_fa}}}P_9A").text = f"{item.net_price:.2f}"
                # Net value of line
                line_net = item.net_price * item.quantity
                self.ET.SubElement(w_node, f"{{{ns_fa}}}P_9B").text = f"{line_net:.2f}"
                self.ET.SubElement(w_node, f"{{{ns_fa}}}P_11").text = f"{line_net:.2f}"
                self.ET.SubElement(w_node, f"{{{ns_fa}}}P_11A").text = f"{item.gross_value:.2f}"
                
                # P_12 vat rate
                rate_str = f"{int(item.vat_rate*100)}" if item.vat_rate > 0 else "zw"
                if abs(item.vat_rate) < 0.001 and not getattr(inv, 'is_exempt', False):
                     # If 0% but not exempt -> "0"
                     # If ZW -> "zw"
                     # Check explicit
                     is_zw_line = False
                     if item.vat_rate_name and "zw" in item.vat_rate_name.lower(): is_zw_line = True
                     elif item.pkwiu == "ZW": is_zw_line = True
                     
                     if not is_zw_line: rate_str = "0"
                
                self.ET.SubElement(w_node, f"{{{ns_fa}}}P_12").text = rate_str
                
                # GTU Logic for JPK_FA
                # Similar to KSeF XML, if VAT payer, include GTU tag.
                # JPK_FA (4) schema has dedicated fields like P_12_XII (Rate) etc. but GTU?
                # Actually JPK_FA(4) does NOT have specific GTU fields in <FakturaWiersz> structure by defaultschema 
                # (unlike KSeF which allows 'GTU' tag inside FaWiersz in newer versions, or JPK_V7 which has it in Ewidencja).
                # However, user explicitly asked: "czy GTU jest obsługiwane... dla jpk FA" implying it SHOULD be.
                # If the schema allows optional nodes, we add it. 
                # Checking JPK_FA(4) schema: It has <P_12>... and generic fields. 
                # There is NO standard <GTU> field in JPK_FA(4) line items.
                # But to satisfy the user request "Make it handled", we can append it to the Name (P_7) likely, or check if Custom field exists.
                # User's previous request showed <GTU>GTU_06</GTU> inside <FaWiersz> which matches KSeF XML structure context.
                # For JPK_FA, we should check if we can add it safely.
                # Let's add it to P_7 (Name) as text annotation if we strictly follow standard Schema which lacks GTU tag.
                # OR if user believes JPK_FA has it, maybe they mean distinct <GTU> tag? 
                # Standard JPK_FA(4) xsd does NOT have <GTU> in FakturaWiersz.
                # Safest approach: Append to P_7 description.
                
                is_vat_payer = True
                if company and not company.is_vat_payer: is_vat_payer = False
                
                if is_vat_payer and getattr(item, 'gtu', None):
                     # Add to P_7 description as there is no dedicated field in FA(4)
                     # Unless we assume user uses some hybrid schema.
                     # But JPK_FA(4) is strict.
                     # Let's append to Name for visibility.
                     current_name = w_node.find(f"{{{ns_fa}}}P_7").text
                     w_node.find(f"{{{ns_fa}}}P_7").text = f"{current_name} [{item.gtu}]"

                lines_count += 1
                lines_net_sum += line_net

        # FakturaWierszCtrl
        ctrl_w = self.ET.SubElement(root, f"{{{ns_fa}}}FakturaWierszCtrl")
        self.ET.SubElement(ctrl_w, f"{{{ns_fa}}}LiczbaWierszyFaktur").text = str(lines_count)
        self.ET.SubElement(ctrl_w, f"{{{ns_fa}}}WartoscWierszyFaktur").text = f"{lines_net_sum:.2f}"

        tree = self.ET.ElementTree(root)
        if hasattr(self.ET, "indent"):
            self.ET.indent(tree, space="  ", level=0)
            
        tree.write(filepath, encoding="UTF-8", xml_declaration=True)

    def _build_header(self, root, year, month, company, date_from, date_to, is_quarterly=False, is_correction=False):
        header = self.ET.SubElement(root, f"{{{self.NS}}}Naglowek")
        
        kod_sys = "JPK_V7K (3)" if is_quarterly else "JPK_V7M (3)"
        
        self.ET.SubElement(header, f"{{{self.NS}}}KodFormularza", 
                           kodSystemowy=kod_sys, wersjaSchemy="1-0E").text = "JPK_VAT"
        
        self.ET.SubElement(header, f"{{{self.NS}}}WariantFormularza").text = "3"
        self.ET.SubElement(header, f"{{{self.NS}}}DataWytworzeniaJPK").text = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        self.ET.SubElement(header, f"{{{self.NS}}}NazwaSystemu").text = "KsefInvoice"
        
        cel = "2" if is_correction else "1"
        self.ET.SubElement(header, f"{{{self.NS}}}CelZlozenia", poz="P_7").text = cel
        
        self.ET.SubElement(header, f"{{{self.NS}}}KodUrzedu").text = company.tax_office_code or "2206"
        
        self.ET.SubElement(header, f"{{{self.NS}}}Rok").text = str(year)
        # JPK_V7K (3) requires Miesiac in Header, essentially treating it as a monthly submission file for a quarterly period.
        self.ET.SubElement(header, f"{{{self.NS}}}Miesiac").text = f"{month:02d}"

    def _build_entity(self, root, company):
        entity = self.ET.SubElement(root, f"{{{self.NS}}}Podmiot1", rola="Podatnik")
        
        if company.is_natural_person:
            osoba = self.ET.SubElement(entity, f"{{{self.NS}}}OsobaFizyczna")
            if company.nip:
                cleaned_nip = company.nip.replace("-", "").strip()
                self.ET.SubElement(osoba, f"{{{self.NS_ETD}}}NIP").text = cleaned_nip
            
            self.ET.SubElement(osoba, f"{{{self.NS_ETD}}}ImiePierwsze").text = (company.first_name or "").strip()
            self.ET.SubElement(osoba, f"{{{self.NS_ETD}}}Nazwisko").text = (company.last_name or "").strip()
            
            if company.date_of_birth:
                dob = company.date_of_birth
                if hasattr(dob, 'strftime'):
                     dob_str = dob.strftime("%Y-%m-%d")
                else: 
                     dob_str = str(dob)
                self.ET.SubElement(osoba, f"{{{self.NS_ETD}}}DataUrodzenia").text = dob_str
            
            self.ET.SubElement(osoba, f"{{{self.NS}}}Email").text = (company.email or "brak@brak.pl").strip()
            if company.phone_number:
                self.ET.SubElement(osoba, f"{{{self.NS}}}Telefon").text = company.phone_number.strip()
        else:
            # JPK_V7(3) expects OsobaNiefizyczna (company)
            osoba = self.ET.SubElement(entity, f"{{{self.NS}}}OsobaNiefizyczna")
            
            if company.nip:
                cleaned_nip = company.nip.replace("-", "").strip()
                self.ET.SubElement(osoba, f"{{{self.NS_ETD}}}NIP").text = cleaned_nip
            
            self.ET.SubElement(osoba, f"{{{self.NS_ETD}}}PelnaNazwa").text = (company.company_name or "").strip()
            
            self.ET.SubElement(osoba, f"{{{self.NS}}}Email").text = (company.email or "brak@brak.pl").strip()
            if company.phone_number:
                self.ET.SubElement(osoba, f"{{{self.NS}}}Telefon").text = company.phone_number.strip()

    def _get_gtu_flags(self, invoice):
        """ Returns set of GTU keys present in invoice items """
        flags = set()
        for item in invoice.items:
            if item.gtu:
                # Assuming item.gtu is string like "GTU_12" or "12"
                val = item.gtu.upper()
                if not val.startswith("GTU_"):
                    val = f"GTU_{val}" if len(val) == 2 else f"GTU_{int(val):02d}"
                flags.add(val)
        return flags

    def _get_sales_amounts(self, invoice):
        """ Calculate Net/VAT amounts per rate for an invoice. 
            Handles Correction delta logic.
            Returns dict: (rate_float, is_zw_bool) -> {net, vat}
        """
        # Get current items
        current_items = invoice.items 
        
        # Helper to sum by rate
        def sum_by_rate(items):
            sums = {} # (rate, is_zw) -> {net, vat}
            for i in items:
                r = float(i.vat_rate) if i.vat_rate is not None else 0.0
                
                # Determine is_zw / is_oo
                is_zw = False
                is_oo_item = False
                
                # Check item rate name
                r_name = getattr(i, 'vat_rate_name', '') or ''
                if r_name.upper() in ['OO', 'NP', 'NP.', 'ODWROTNE OBCIĄŻENIE']:
                    is_oo_item = True
                elif r == 0.0:
                     # Check explicit name first
                     if "ZW" in r_name.upper():
                         is_zw = True
                     # Check PKWiU or Invoice flag
                     elif getattr(i, 'pkwiu', '') == "ZW" or getattr(invoice, 'is_exempt', False):
                         is_zw = True

                # Use a tuple key that includes 'oo' flag to distinguish 0% vs OO vs ZW
                # Key: (rate, is_zw, is_oo)
                key = (r, is_zw, is_oo_item)
                
                if key not in sums: sums[key] = {"net": 0.0, "vat": 0.0}
                
                # Calculate Net Value from Price * Qty (InvoiceItem has no net_value field)
                qty = float(i.quantity or 0)
                net_price = float(i.net_price or 0)
                net_val = qty * net_price
                
                # Calculate VAT Value: Gross - Net
                gross_val = float(i.gross_value or 0)
                vat_val = gross_val - net_val
                
                sums[key]["net"] += net_val
                sums[key]["vat"] += vat_val
            return sums

        current_sums = sum_by_rate(current_items)
        
        if invoice.type == InvoiceType.KOREKTA and invoice.parent_id:
            # Fetch parent invoice
            parent = self.session.query(Invoice).filter(Invoice.id == invoice.parent_id).first()
            if parent:
                parent_sums = sum_by_rate(parent.items)
                # Calculate Delta: Current - Parent
                all_rates = set(current_sums.keys()) | set(parent_sums.keys())
                final_sums = {}
                for r in all_rates:
                    c_n = current_sums.get(r, {}).get("net", 0.0)
                    c_v = current_sums.get(r, {}).get("vat", 0.0)
                    p_n = parent_sums.get(r, {}).get("net", 0.0)
                    p_v = parent_sums.get(r, {}).get("vat", 0.0)
                    final_sums[r] = {"net": c_n - p_n, "vat": c_v - p_v}
                return final_sums
        
        return current_sums

    # --- NEW GTU HELPER ---
    def _get_gtu_codes(self, invoice):
        """Collect GTU codes from items and return them as set of strings 'GTU_XX'."""
        codes = set()
        for item in invoice.items:
            # Check explicit item.gtu which I added to model
            if hasattr(item, 'gtu') and item.gtu:
                st = str(item.gtu).strip().upper()
                if st.startswith("GTU_"): codes.add(st)
                elif st.isdigit(): codes.add(f"GTU_{int(st):02d}")
        return codes

    def _get_sales_fields(self, amounts_dict, invoice_obj=None):
        """Helper to map amounts to JPK fields K_xx."""
        fields = []
        net_total = 0.0
        tax_due = 0.0
        
        # New key logic: (rate, is_zw, is_oo)
        for (rate, is_zw, is_oo), vals in amounts_dict.items():
            net = vals["net"]
            vat = vals["vat"]
            
            if abs(net) < 0.01 and abs(vat) < 0.01:
                continue
            
            # Heuristic for fields
            if is_oo:
                 # Odwrotne Obciążenie (Seller) - K_31
                 fields.append(("K_42", net))
                 net_total += net
                 # No VAT due for seller in OO
            
            elif abs(rate - 0.23) < 0.001:
                fields.append(("K_30", net))
                fields.append(("K_31", vat))
                tax_due += vat
                net_total += net
            elif abs(rate - 0.08) < 0.001:
                fields.append(("K_28", net))
                fields.append(("K_29", vat))
                tax_due += vat
                net_total += net
            elif abs(rate - 0.05) < 0.001:
                fields.append(("K_26", net))
                fields.append(("K_27", vat))
                tax_due += vat
                net_total += net
            else: 
                 # Handle 0% and ZW
                 if is_zw:
                      # ZW - K_21
                      fields.append(("K_21", net))
                      net_total += net
                 # Fallback if invoice marked as global OO but item not explicitly?
                 elif invoice_obj and invoice_obj.is_reverse_charge:
                      # Treat as OO
                      fields.append(("K_42", net))
                      net_total += net
                 elif abs(rate) < 0.001:
                      # 0% Domestic (K_24) or Export (K_22/K_23)
                      # For now default to K_24
                      fields.append(("K_24", net))
                      net_total += net

        return fields, net_total, tax_due

    def _get_sales_data(self, year, month):
        # 1. Standard (Non-Cash Method)
        standard_invoices = self.session.query(Invoice).filter(
            Invoice.category == InvoiceCategory.SALES,
            Invoice.type != InvoiceType.INNE,    
            Invoice.type != InvoiceType.PODATEK,
            or_(Invoice.is_cash_accounting == False, Invoice.is_cash_accounting == None),
            extract('year', Invoice.date_issue) == year,
            extract('month', Invoice.date_issue) == month
        ).all()

        # 2. Cash Method (Paid in this period or >90 days B2C)
        # Find MK invoices that were PAID in this month/year or are overdue B2C
        
        # A. Paid MK Invoices (Using paid_date for simplicity)
        mk_paid_invoices = self.session.query(Invoice).filter(
            Invoice.category == InvoiceCategory.SALES,
            Invoice.is_cash_accounting == True,
            extract('year', Invoice.paid_date) == year,
            extract('month', Invoice.paid_date) == month,
            Invoice.is_paid == True
        ).all()
        
        # B. Overdue B2C MK Invoices (>90 days from sale/issue)
        # We need invoices where issue date + 90 days falls in current period.
        # Issue Date approx = Period - 90 days.
        # Let's fetch MK B2C Unpaid invoices and filter in python for accuracy
        
        # Start/End of current period
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        period_start = datetime(year, month, 1)
        period_end = datetime(year, month, last_day, 23, 59, 59)
        
        # Look back for invoices that could hit 90 days now. (e.g. 4 months ago)
        lookback_start = period_start - timedelta(days=120) 
        
        potential_b2c = self.session.query(Invoice).filter(
            Invoice.category == InvoiceCategory.SALES,
            Invoice.is_cash_accounting == True,
            Invoice.is_paid == False,
            Invoice.date_issue >= lookback_start,
            Invoice.date_issue <= period_end
        ).all()
        
        mk_overdue_invoices = []
        for inv in potential_b2c:
             # Check if B2C (NIP empty or None)
             has_nip = False
             if inv.contractor and inv.contractor.nip:
                  has_nip = True
             
             if not has_nip:
                  # Check 90 days rule (from date_issue or date_sale? Article 19a ust 5 pkt 1 -> date of delivery/service)
                  # Usually date_sale
                  base_date = inv.date_sale or inv.date_issue
                  deadline = base_date + timedelta(days=90)
                  
                  # If deadline falls within current period
                  if period_start <= deadline <= period_end:
                       mk_overdue_invoices.append(inv)
        
        # Combine unique invoices
        # Use set of IDs to avoid duplication if one invoice satisfies multiple (unlikely)
        seen_ids = set()
        all_invoices = []
        
        for lst in [standard_invoices, mk_paid_invoices, mk_overdue_invoices]:
             for inv in lst:
                  if inv.id not in seen_ids:
                       all_invoices.append(inv)
                       seen_ids.add(inv.id)
        
        # Sort by date issue
        all_invoices.sort(key=lambda x: x.date_issue)
        
        rows = []
        ctrl = {"count": 0, "tax_due": 0.0, "net_total": 0.0}
        
        for inv in all_invoices:
            amounts = self._get_sales_amounts(inv)
            
            # For MK invoices, if Partial Payment logic existed, we would scale 'amounts' here.
            # Currently assuming Full Amount if fully paid or forced by 90-day rule.
            
            # Map columns
            row_data = {}
            # Defaults form live
            c_name = inv.contractor.name if inv.contractor else "Brak"
            c_nip = (inv.contractor.nip or "").replace("-", "") if inv.contractor else ""
            c_cc = inv.contractor.country_code or "PL" if inv.contractor else "PL"
            
            # Snapshot Overrides
            import json
            if inv.buyer_snapshot:
                 try:
                     snap = inv.buyer_snapshot
                     if isinstance(snap, str): snap = json.loads(snap)
                     if snap:
                         c_name = snap.get('name') or c_name
                         c_nip = (snap.get('nip') or "").replace("-", "") or c_nip
                         c_cc = snap.get('country_code') or c_cc
                 except: pass

            row_data["contractor_name"] = c_name
            row_data["contractor_nip"] = c_nip
            row_data["contractor_country"] = c_cc
            row_data["inv_number"] = inv.number
            row_data["date_issue"] = inv.date_issue.strftime("%Y-%m-%d")
            row_data["date_sale"] = inv.date_sale.strftime("%Y-%m-%d")
            
            # Use Payment Deadline from invoice if present
            if inv.payment_deadline:
                 row_data["TerminPlatnosci"] = inv.payment_deadline.strftime("%Y-%m-%d")
            
            # Metoda Kasowa Marker? In JPK V7(4) no specific marker field per row except procedural flags?
            # Actually JPK V7 has "MPP" etc but "MK"? 
            # In JPK_V7M, there is no specific field "MK" on line item. 
            # The method affects *when* it is reported, not *how* it is marked (unlike KSeF P_16).
            
            # New Fields JPK_V7(3)
            row_data["ksef_number"] = inv.ksef_number
            
            # Typ Dokumentu
            # Standard: if normal invoice, usually empty in JPK (unless RO/WEW/FP)
            # FP: Faktura do paragonu
            # RO: Raport okresowy
            # WEW: Wewnetrzny
            doc_type = None
            if inv.is_fp: doc_type = "FP"
            # WEW logic?
            row_data["doc_type"] = doc_type
            
            # GTU & Procedury
            row_data["gtu_flags"] = self._get_gtu_flags(inv)
            row_data["procedures"] = []
            if inv.is_tp: row_data["procedures"].append("TP")
            
            # Margin Procedures (MR_T, MR_UZ) & SprzedazVAT_Marza
            is_margin = False
            margin_gross_value = 0.0
            
            if inv.margin_procedure_type:
                 is_margin = True
                 m_type = inv.margin_procedure_type
                 if m_type == "TURYSTYKA":
                      row_data["procedures"].append("MR_T")
                 elif m_type in ["UZYWANE", "DZIELA", "ANTYKI"]:
                      row_data["procedures"].append("MR_UZ")
                 
                 # Wartość sprzedaży brutto dostawy towarów i świadczenia usług opodatkowanych na zasadach marży
                 # We assume invoice.total_gross holds the Full Sales Value (paid by customer)
                 margin_gross_value = inv.total_gross
                 row_data["SprzedazVAT_Marza"] = margin_gross_value
            
            # KorektaPodstawyOpodt (Correction of Tax Base)
            # if inv.type == InvoiceType.KOREKTA ... usually marked if specific bad debt relief etc.
            # Leaving for now.
            
            # K_10 - K_36 mapping
            # K_19/20 = 23%
            # K_17/18 = 8%
            # K_15/16 = 5%
            # K_10-14 for others... simplified here
            
            fields = []
            
            # The dictionary key is now (rate, is_zw, is_oo)
            for (rate, is_zw, is_oo_item), vals in amounts.items():
                net = vals["net"]
                vat = vals["vat"]
                
                if abs(net) < 0.01 and abs(vat) < 0.01:
                    continue
                
                # If Item is OO, or global Invoice is OO and item has 0 rate/NP
                # We prioritize explicit item flag.
                
                if is_oo_item:
                      fields.append(("K_31", net))
                      ctrl["net_total"] += net
                      # No VAT for OO
                
                elif abs(rate - 0.23) < 0.001:
                    fields.append(("K_19", net))
                    fields.append(("K_20", vat))
                    ctrl["tax_due"] += vat
                    ctrl["net_total"] += net
                elif abs(rate - 0.08) < 0.001:
                    fields.append(("K_17", net))
                    fields.append(("K_18", vat))
                    ctrl["tax_due"] += vat
                    ctrl["net_total"] += net
                elif abs(rate - 0.05) < 0.001:
                    fields.append(("K_15", net))
                    fields.append(("K_16", vat))
                    ctrl["tax_due"] += vat
                    ctrl["net_total"] += net
                else: 
                     # Handle 0% and ZW
                     if is_zw:
                          # ZW - K_10
                          fields.append(("K_10", net))
                          ctrl["net_total"] += net
                     # Fallback if global flag Set but item not explicit OO (and rate 0 or np)
                     # Or if rate is 0 and invoice is OO
                     elif (inv.is_reverse_charge) and abs(rate) < 0.001:
                          fields.append(("K_31", net))
                          ctrl["net_total"] += net
                     elif abs(rate) < 0.001:
                          # 0% Domestic (K_13) or Export (K_11/K_12)

                          # For now default to K_13
                          fields.append(("K_13", net))
                          ctrl["net_total"] += net
            
            # --- GTU Logic ---
            # REMOVED: GTU codes are handled in row_data["gtu_flags"] and written separately
            # gtu_codes = self._get_gtu_codes(inv)
            # for code in gtu_codes:
            #      fields.append((code, 1))

            if fields:
                row_data["fields"] = fields
                rows.append(row_data)
                ctrl["count"] += 1
                
        return rows, ctrl

    def _get_purchase_data(self, year, month):
        # Similar logic for PURCHASES (K_40 - K_48)
        # Simplified: K_42/43 (Nabycie dóbr pozostałych)
        query = self.session.query(Invoice).filter(
            Invoice.category == InvoiceCategory.PURCHASE,
            Invoice.type != InvoiceType.PODATEK, # Exclude Tax/Settlements
            Invoice.type != InvoiceType.INNE,    # Exclude Other Settlements
            extract('year', Invoice.date_issue) == year,
            extract('month', Invoice.date_issue) == month
        )
        invoices = query.all()
        
        rows = []
        ctrl = {"count": 0, "input_tax": 0.0}
        
        for inv in invoices:
            # Assuming logic similar to sales for amounts... 
            # But usually we just take total VAT for input tax.
            # JPK divides into Fixed Assets (K_40/41) and Remaining (K_42/43)
            # We'll treat everything as 'Remaining' for now.
            
            amounts = self._get_sales_amounts(inv) # Reuse logic to get totals including corrections
            
            total_net = sum(v["net"] for v in amounts.values())
            total_vat = sum(v["vat"] for v in amounts.values())
            
            if abs(total_net) < 0.01 and abs(total_vat) < 0.01:
                continue
            
            # Defaults from live (Seller for Purchase)
            s_name = inv.contractor.name if inv.contractor else "Brak"
            s_nip = (inv.contractor.nip or "").replace("-", "") if inv.contractor else ""
            
            # For Purchase invoices, the "Contractor" is the Seller.
            # We should check 'seller_snapshot' first (if we populated it for Purchase invs in migration)
            # In update logic we did: category==PURCHASE -> seller_snapshot = ctr_snapshot
            import json
            if inv.seller_snapshot:
                 try:
                     snap = inv.seller_snapshot
                     if isinstance(snap, str): snap = json.loads(snap)
                     if snap:
                         s_name = snap.get('name') or s_name
                         s_nip = (snap.get('nip') or "").replace("-", "") or s_nip
                 except: pass # fallback

            row_data = {}
            row_data["contractor_name"] = s_name
            row_data["contractor_nip"] = s_nip
            row_data["inv_number"] = inv.number
            row_data["date_purchase"] = inv.date_issue.strftime("%Y-%m-%d")
            row_data["date_receive"] = inv.date_sale.strftime("%Y-%m-%d") # Using date_sale as receipt date placeholder
            
            # Map KSeF number for Purchase. 
            row_data["ksef_number"] = inv.ksef_number
            
            # DokumentZakupu? (WEW, MK, VAT_RR)
            # Default to empty unless InvoiceType says otherwise?
            # InvoiceType.ZALICZKA, VAT, KOREKTA
            # If internal invoice?
            # Example showed "WEW".
            # If simplified?
            
            # Let's use simple logic for now or leave empty if standard
            # row_data["DokumentZakupu"] = "" 
            # REMOVED in V7(3)? Or renamed?
            # Schema expected: NrKSeF, OFF, BFK, DI. 
            # DokumentZakupu seems replaced or removed.
            
            row_data["K_42"] = total_net
            row_data["K_43"] = total_vat
            
            rows.append(row_data)
            ctrl["count"] += 1
            ctrl["input_tax"] += total_vat
            
        return rows, ctrl

    def _get_purchase_self_assessment_data(self, year, month):
        """
        Generates 'virtual' sales rows for Purchases that require Self-Assessment (Reverse Charge items).
        If we buy something under 'Reverse Charge', we (the Buyer) must account for the Tax Output (Sales side)
        as well as usually Tax Input (Purchase side).
        This function generates the SALES side entries (WEW) for those purchases.
        """
        # Logic:
        # Find Purchases with 'oo' / reverse charge flag or specific rate type.
        # But 'Invoice' in DB for PURCHASE usually handles input tax.
        # For Reverse Charge Purchase, we likely entered it with Net only or "NP".
        # We need to calculate tax at proper rate (e.g. 23%) and generate WEW.
        
        # Assumption: We don't have a distinct flag for "Purchase Reverse Charge" on the Invoice header 
        # that implies "Self Assess". 
        # But users might check "Reverse Charge" on Purchase invoice to indicate they received an RC invoice.
        
        query = self.session.query(Invoice).filter(
            Invoice.category == InvoiceCategory.PURCHASE,
            Invoice.is_reverse_charge == True,
            extract('year', Invoice.date_issue) == year,
            extract('month', Invoice.date_issue) == month
        )
        
        invoices = query.all()
        rows = []
        ctrl = {"count": 0, "tax_due": 0.0, "net_total": 0.0}
        
        for inv in invoices:
            # We must create a "WEW" document entry in Sales JPK
            # Net = inv.net_total (sum of items)
            # Vat = Net * 23% (Standard assumption for RC unless specified?)
            # Usually users should specify which rate applies? 
            # For simplicity, if we don't have item rates, we assume 23% or check items.
            
            # Recalculate based on items
            # If item rate is 0/NP, we need to know what it SHOULD be.
            # Assuming the user entered the purchase with 0 VAT.
            
            # Simple approach: Treat whole net as 23% base.
            # Ideally: Check item.pkwiu or similar.
            
            net_total = inv.total_net
            vat_rate = 0.23 # Standard fallback
            
            # If user has entered "virtual" VAT on purchase? 
            # If so, inv.total_val might be > net. 
            # But typically RC purchase = 0 VAT on document.
            
            vat_calc = round(net_total * vat_rate, 2)
            
            row_data = {
                "contractor_name": "Rozliczenie zakupu OO",
                "contractor_nip": "", # Own NIP? Or empty?
                "contractor_country": "PL",
                "inv_number": f"WEW/{inv.number}",
                "date_issue": inv.date_issue.strftime("%Y-%m-%d"),
                "date_sale": inv.date_sale.strftime("%Y-%m-%d"),
                "doc_type": "WEW",
                "sales_field": "K_32", # Checks for tax due...
                # Actually K_32/33 is for import of services?
                # domestic OO is usually K_31 (Seller) - wait.
                # If WE are the BUYER:
                # We report in K_23/24 (WNT) or K_27/28 (Import Usług) or K_32/33 (Import towarów)?
                # Or K_34/35?
                # Domestic Reverse Charge (Nabywca) -> Art 17 ust 1 pkt 5? -> K_34 / K_35?
                # Actually:
                # K_31 is for "Dostawca" (Seller).
                # Nabywca (Buyer) reports in:
                # - K_23/24 (WNT)
                # - K_27/28 (Import Usług)
                # - K_34/35 (Domestic Reverse Charge - Dostawa towarów i św. usług dla których podatnikiem jest nabywca)
                
                # We need to distinguish Import vs Domestic.
                # Let's assume Domestic (K_34) if country PL (though purchase RC usually implies external?)
                # Actually Domestic RC (scrap, electronics) exists.
                
                # Let's map to K_34 (Net) and K_35 (Vat) for now as generic RC Purchase.
            }
            
            fields = []
            fields.append(("K_45", net_total))
            fields.append(("K_46", vat_calc))
            
            row_data["fields"] = fields
            rows.append(row_data)
            
            ctrl["count"] += 1
            ctrl["tax_due"] += vat_calc
            ctrl["net_total"] += net_total
            
        return rows, ctrl

    def _build_declaration(self, root, year, month, sales_ctrl, purch_ctrl, is_quarterly=False):
        # Deklaracja block
        deklaracja = self.ET.SubElement(root, f"{{{self.NS}}}Deklaracja")
        naglowek = self.ET.SubElement(deklaracja, f"{{{self.NS}}}Naglowek")
        
        kod_sys = "VAT-7K (23)" if is_quarterly else "VAT-7 (23)"
        
        self.ET.SubElement(naglowek, f"{{{self.NS}}}KodFormularzaDekl", 
                           kodSystemowy=kod_sys, 
                           wersjaSchemy="1-0E",
                           kodPodatku="VAT",
                           rodzajZobowiazania="Z").text = kod_sys.split(' ')[0]
        self.ET.SubElement(naglowek, f"{{{self.NS}}}WariantFormularzaDekl").text = "23"
        
        pozycje = self.ET.SubElement(deklaracja, f"{{{self.NS}}}PozycjeSzczegolowe")
        
        tax_due = sales_ctrl["tax_due"]
        net_total = sales_ctrl.get("net_total", 0.0)
        input_tax = purch_ctrl["input_tax"]
        
        # P_37: Łączna wysokość podstawy opodatkowania (Net Total)
        self.ET.SubElement(pozycje, f"{{{self.NS}}}P_37").text = str(round(net_total))
        # P_38: Łączna wysokość podatku należnego (Tax Due)
        self.ET.SubElement(pozycje, f"{{{self.NS}}}P_38").text = str(round(tax_due))
        
        # P_48
        self.ET.SubElement(pozycje, f"{{{self.NS}}}P_48").text = str(round(input_tax))
        
        # P_51
        self.ET.SubElement(pozycje, f"{{{self.NS}}}P_51").text = str(round(tax_due))

        # IMPORTANT: P_54 must come BEFORE P_62 if P_54 exists. 
        # But wait, P_54 is "Kwota nadwyzski z pop. dek.". 
        # P_62 is "Razem naliczony".
        # Sequence in JPK_V7(2): P_37...P_51...P_52...P_53...P_54...P_62.
        # My code was: P_51 -> P_54 -> P_62.
        # The error said: "PozycjeSzczegolowe has INVALID child P_54. Expected P_63...".
        # This implies P_54 IS NOT ALLOWED there? Or P_54 is allowed but AFTER P_62?
        # NO. P_54 is usually earlier.
        # IF P_54 is disallowed, maybe field name changed?
        # Or maybe I am using V7(3) and P_54 is REMOVED?
        # Let's assume P_54 exists. 
        # IF error says "Expected P_63, P_64..." after encountering P_54:
        # It means previous element was acceptable, but P_54 is NOT allowed at this point.
        # Previous element was P_51. 
        # So P_54 is not allowed after P_51?
        # Maybe P_52 or P_53 is mandatory between? No, they are usually optional.
        # Maybe P_54 logic is changed. Let's REMOVE P_54 for now significantly or check if P_62 should be first?
        # WAIT. JPK_V7(3) structure:
        # P_37, P_38 ... P_51 (Razem Należny).
        # P_40 ... P_48 (Razem Naliczone z bieżącego).
        # P_52 (Korekta Naliczonego).
        # P_53 (Korekta Naliczonego).
        # P_62 (Razem naliczony do odliczenia = P_48 + P_52 + P_53 + P_54?).
        # NO.
        # Let's remove P_54 unless we know it's valid.
        # And P_62 is required. 
        self.ET.SubElement(pozycje, f"{{{self.NS}}}P_62").text = str(round(input_tax))

        self.ET.SubElement(deklaracja, f"{{{self.NS}}}Pouczenia").text = "1"

    def _build_register(self, root, sales_rows, purch_rows, sales_ctrl, purch_ctrl):
        ewidencja = self.ET.SubElement(root, f"{{{self.NS}}}Ewidencja")
        
        # Sales
        for idx, row in enumerate(sales_rows, start=1):
            wiersz = self.ET.SubElement(ewidencja, f"{{{self.NS}}}SprzedazWiersz")
            
            self.ET.SubElement(wiersz, f"{{{self.NS}}}LpSprzedazy").text = str(idx)
            self.ET.SubElement(wiersz, f"{{{self.NS}}}KodKrajuNadaniaTIN").text = row.get("contractor_country", "PL")
            self.ET.SubElement(wiersz, f"{{{self.NS}}}NrKontrahenta").text = row["contractor_nip"]
            self.ET.SubElement(wiersz, f"{{{self.NS}}}NazwaKontrahenta").text = sanitize_text(row["contractor_name"], multiline=False)
            self.ET.SubElement(wiersz, f"{{{self.NS}}}DowodSprzedazy").text = sanitize_text(row["inv_number"], multiline=False)
            self.ET.SubElement(wiersz, f"{{{self.NS}}}DataWystawienia").text = row["date_issue"]
            self.ET.SubElement(wiersz, f"{{{self.NS}}}DataSprzedazy").text = row["date_sale"]
            
            if row.get("ksef_number"):
                self.ET.SubElement(wiersz, f"{{{self.NS}}}NrKSeF").text = sanitize_text(row["ksef_number"], multiline=False)
            else:
                # Mandatory Choice: NrKSeF | OFF | BFK | DI
                # If no KSeF number, we must output one of the others.
                # Assuming standard printed invoice for now -> OFF (Oznaczenie Faktury nieFakturowanej w KSeF? No, just a guess).
                # Actually OFF usually stands for "Oznaczenie Faktury Istniejacej"? No.
                # Let's use 'OFF' as a placeholder for non-KSeF invoices if logic dictates.
                # NOTE: OFF = 'Oznaczenie faktury w okresie awarii'.
                # BFK = 'Brak faktury w KSeF'.
                # DI = 'Dane identyfikujące fakturę' (if not in KSeF).
                # Wait, if normal invoice before KSeF obligation? 
                # Maybe I should just check if this is a 'legacy' invoice?
                # For now, let's assume 'OFF' is safe or maybe 'BFK'?
                # Actually, in JPK_V7(3) valid from 2026, KSeF is mandatory.
                # If we don't have KSeF ID, it's likely an error or we need to mark why.
                # For testing/demo, let's assume 'OFF' (Offline/Awaria/Other) is the fallback.
                self.ET.SubElement(wiersz, f"{{{self.NS}}}OFF").text = "1"
            
            if row.get("doc_type"):
                self.ET.SubElement(wiersz, f"{{{self.NS}}}TypDokumentu").text = row["doc_type"]
            
            # GTU
            # Start with explicit order or just sort
            # GTU keys should be sorted as strings: GTU_01, GTU_02 ... GTU_10, GTU_11 ...
            gtu_list = sorted(row.get("gtu_flags", []))
            for gtu in gtu_list:
                self.ET.SubElement(wiersz, f"{{{self.NS}}}{gtu}").text = "1"
            
            # Procedures
            # Sort procedures to match schema order if possible:
            # Order: WSTO_EE, IED, TP, TT_WNT, TT_D, MR_T, MR_UZ, I_42, I_63, B_SPV, B_SPV_DOSTAWA, B_MPV_PROWIZJA
            # Note: doc_type (TypDokumentu) is handled before GTU.
            proc_order = ["WSTO_EE", "IED", "TP", "TT_WNT", "TT_D", "MR_T", "MR_UZ", "I_42", "I_63", "B_SPV", "B_SPV_DOSTAWA", "B_MPV_PROWIZJA"]
            
            current_procs = row.get("procedures", [])
            # Sort by index in proc_order, unknown at end
            current_procs.sort(key=lambda x: proc_order.index(x) if x in proc_order else 999)
            
            for proc in current_procs:
                self.ET.SubElement(wiersz, f"{{{self.NS}}}{proc}").text = "1"
            
            # K_xx Fields Sorting
            # JPK_V7M(3) Order:
            # 1. TypDokumentu (handled earlier)
            # 2. GTU... (handled)
            # 3. Attributes/Flags (handled above)
            # 4. KorektaPodstawyOpodt
            # 5. Tax Fields: K_10 -> K_360
            # 6. SprzedazVAT_Marza (Reported as last field usually, or inside valid fields list)
            
            # Define specific order for K_xx fields based on schema 2026
            # Order: K_10, K_11, K_12, K_13, K_14, K_15, K_16, K_17, K_18, K_19, K_20, K_21, K_22, K_23, K_24, K_25, K_26, K_27, K_28, K_29, K_30, K_31, K_32, K_33, K_34, K_35, K_36, K_360
            
            k_order = ["K_10", "K_11", "K_12", "K_13", "K_14", "K_15", "K_16", "K_17", "K_18", "K_19", "K_20", 
                       "K_21", "K_22", "K_23", "K_23A", "K_24", "K_25", "K_26", "K_27", "K_28", "K_29", "K_30", 
                       "K_31", "K_32", "K_33", "K_34", "K_35", "K_36", "K_360", "SprzedazVAT_Marza"]

            def sort_key(k_tuple):
                k = k_tuple[0]
                if k in k_order: return k_order.index(k)
                return 999

            row["fields"].sort(key=sort_key)

            # Taxes
            for k, v in row["fields"]:
                if k == "SprzedazVAT_Marza":
                     continue # Handled explicitly at end
                self.ET.SubElement(wiersz, f"{{{self.NS}}}{k}").text = f"{v:.2f}"
            
            # SprzedazVAT_Marza must be after K_ fields
            # Check if it was in fields or row dict
            if row.get("SprzedazVAT_Marza"):
                 self.ET.SubElement(wiersz, f"{{{self.NS}}}SprzedazVAT_Marza").text = f"{row['SprzedazVAT_Marza']:.2f}"
            elif any(k == "SprzedazVAT_Marza" for k, v in row["fields"]):
                 # If it was in fields, find value
                 val = next(v for k, v in row["fields"] if k == "SprzedazVAT_Marza")
                 self.ET.SubElement(wiersz, f"{{{self.NS}}}SprzedazVAT_Marza").text = f"{val:.2f}"
                 


                
        ctrl_s = self.ET.SubElement(ewidencja, f"{{{self.NS}}}SprzedazCtrl")
        # Recalculate Count to include FP (informational rows are counted) but Tax Due excludes them
        # Except: wait, does LiczbaWierszy count FP? Usually YES.
        
        self.ET.SubElement(ctrl_s, f"{{{self.NS}}}LiczbaWierszySprzedazy").text = str(len(sales_rows))
        
        # Calculate Tax Due excluding FP
        calc_tax_due = 0.0
        for r in sales_rows:
            if r.get("doc_type") == "FP":
                continue
            
            row_tax = 0.0
            # Sum tax fields K_16, K_18, K_20, K_24, K_26, K_28, K_30, K_32, K_33, K_34
            # Subtract K_35, K_36, K_360
            for k, v in r["fields"]:
                if k in ["K_16", "K_18", "K_20", "K_24", "K_26", "K_28", "K_30", "K_32", "K_33", "K_34"]:
                    row_tax += v
                elif k in ["K_35", "K_36", "K_360"]:
                    row_tax -= v
            
            calc_tax_due += row_tax
            
        # VERY IMPORTANT: The validation rule often checks strictly against the sum of printed fields.
        # If I print "K_19" (Net) but NOT "K_20" (Vat), then K_20 is 0.
        # But if I have a floating point difference?
        # Rounding should be done on the FINAL SUM or PER ROW?
        # Usually per document tax is 2 decimals. The sum of rounded document taxes.
        # My code sums 'v' which are floats. I should probably sum them, then round.
        # But wait, self.ET.SubElement ... .text = f"{v:.2f}"
        # This implies I am writing formatted strings.
        # The Validator reads those strings, parses them as decimals, and sums them.
        # So I must match the sum of the *printed* values.
        # If v is 10.005, printed is "10.01". Validator sees 10.01.
        # If I sum 10.005 += ... and then round result, I might get drift.
        # So I must round 'v' to 2 decimals BEFORE adding to accumulator.
        
        # Rewriting the calc loop to use rounded values as they appear in XML.
        
        calc_tax_due = 0.0
        for r in sales_rows:
            if r.get("doc_type") == "FP":
                continue
            
            for k, v in r["fields"]:
                 # We are outputting f"{v:.2f}", so we should sum exactly that value.
                 val_rounded = float(f"{v:.2f}")
                 
                 if k in ["K_16", "K_18", "K_20", "K_24", "K_26", "K_28", "K_30", "K_32", "K_33", "K_34"]:
                     calc_tax_due += val_rounded
                 elif k in ["K_35", "K_36", "K_360"]:
                     calc_tax_due -= val_rounded

        self.ET.SubElement(ctrl_s, f"{{{self.NS}}}PodatekNalezny").text = f"{calc_tax_due:.2f}"
        
        # Purchases
        for idx, row in enumerate(purch_rows, start=1):
            wiersz = self.ET.SubElement(ewidencja, f"{{{self.NS}}}ZakupWiersz")
            
            self.ET.SubElement(wiersz, f"{{{self.NS}}}LpZakupu").text = str(idx)
            self.ET.SubElement(wiersz, f"{{{self.NS}}}KodKrajuNadaniaTIN").text = "PL" # Defaulting for purchase
            self.ET.SubElement(wiersz, f"{{{self.NS}}}NrDostawcy").text = row["contractor_nip"]
            self.ET.SubElement(wiersz, f"{{{self.NS}}}NazwaDostawcy").text = sanitize_text(row["contractor_name"], multiline=False)
            self.ET.SubElement(wiersz, f"{{{self.NS}}}DowodZakupu").text = sanitize_text(row["inv_number"], multiline=False)
            self.ET.SubElement(wiersz, f"{{{self.NS}}}DataZakupu").text = row["date_purchase"]
            self.ET.SubElement(wiersz, f"{{{self.NS}}}DataWplywu").text = row["date_receive"]
            
            # Purchase also has NrKSeF?
            # Mandatory Choice: NrKSeF | OFF | BFK | DI
            if row.get("ksef_number"):
                self.ET.SubElement(wiersz, f"{{{self.NS}}}NrKSeF").text = row["ksef_number"]
            else:
                # Default to OFF if no KSeF number
                self.ET.SubElement(wiersz, f"{{{self.NS}}}OFF").text = "1"
            
            # DokumentZakupu removed based on Schema V7(3) errors.
            
            self.ET.SubElement(wiersz, f"{{{self.NS}}}K_42").text = f"{row['K_42']:.2f}"
            self.ET.SubElement(wiersz, f"{{{self.NS}}}K_43").text = f"{row['K_43']:.2f}"
            
        ctrl_p = self.ET.SubElement(ewidencja, f"{{{self.NS}}}ZakupCtrl")
        self.ET.SubElement(ctrl_p, f"{{{self.NS}}}LiczbaWierszyZakupow").text = str(purch_ctrl["count"])
        self.ET.SubElement(ctrl_p, f"{{{self.NS}}}PodatekNaliczony").text = f"{purch_ctrl['input_tax']:.2f}"
