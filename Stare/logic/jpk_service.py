import xml.etree.ElementTree as ET
from datetime import datetime
from sqlalchemy import extract
from database.models import Invoice, InvoiceType, InvoiceCategory, InvoiceItem, CompanyConfig

class JpkService:
    def __init__(self, session):
        self.session = session
        self.NS = "http://crd.gov.pl/wzor/2025/12/19/14090/" # JPK_V7M(3) namespace
        self.NS_ETD = "http://crd.gov.pl/xml/schematy/dziedzinowe/mf/2022/09/13/eD/DefinicjeTypy/"
        self.NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"
        self.ET = ET

    def _register_namespaces(self):
        self.ET.register_namespace('', self.NS)
        self.ET.register_namespace('xsi', self.NS_XSI)
        self.ET.register_namespace('etd', self.NS_ETD)

    def generate_jpk_v7m(self, year: int, month: int, filepath: str, quarter: int = None, is_correction: bool = False):
        self._register_namespaces()
        
        company = self.session.query(CompanyConfig).first()
        if not company:
            raise ValueError("Brak konfiguracji firmy (CompanyConfig)")

        root = self.ET.Element(f"{{{self.NS}}}JPK")
        
        # Determine date range and type
        is_quarterly = False
        if quarter:
            is_quarterly = True
            # Quarter 1: Jan-Mar
            m_start = (quarter - 1) * 3 + 1
            m_end = m_start + 2
            
            import calendar
            date_from = f"{year}-{m_start:02d}-01"
            last_day = calendar.monthrange(year, m_end)[1]
            date_to = f"{year}-{m_end:02d}-{last_day}"
            
            # Fetch data for the whole quarter
            sales_rows = []
            sales_ctrl = {"count": 0, "tax_due": 0.0, "net_total": 0.0}
            purch_rows = []
            purch_ctrl = {"count": 0, "input_tax": 0.0}
            
            for m in range(m_start, m_end + 1):
                s_rows, s_ctrl = self._get_sales_data(year, m)
                p_rows, p_ctrl = self._get_purchase_data(year, m)
                
                # Self-Assessment for Quarter
                sa_rows, sa_ctrl = self._get_purchase_self_assessment_data(year, m)
                s_rows.extend(sa_rows)
                s_ctrl["count"] += sa_ctrl["count"]
                s_ctrl["tax_due"] += sa_ctrl["tax_due"]
                s_ctrl.setdefault("net_total", 0.0) # Ensure key exists
                s_ctrl["net_total"] += sa_ctrl["net_total"]

                sales_rows.extend(s_rows)
                sales_ctrl["count"] += s_ctrl["count"]
                sales_ctrl["tax_due"] += s_ctrl["tax_due"]
                sales_ctrl["net_total"] += s_ctrl.get("net_total", 0.0)
                
                purch_rows.extend(p_rows)
                purch_ctrl["count"] += p_ctrl["count"]
                purch_ctrl["input_tax"] += p_ctrl["input_tax"]

        else:
            is_quarterly = False
            import calendar
            last_day = calendar.monthrange(year, month)[1]
            date_from = f"{year}-{month:02d}-01"
            date_to = f"{year}-{month:02d}-{last_day}"
            
            sales_rows, sales_ctrl = self._get_sales_data(year, month)
            purch_rows, purch_ctrl = self._get_purchase_data(year, month)
            
            # Incorporate Self-Assessment Rows (Reverse Charge Purchases shown in Sales)
            sa_rows, sa_ctrl = self._get_purchase_self_assessment_data(year, month)
            sales_rows.extend(sa_rows)
            sales_ctrl["count"] += sa_ctrl["count"]
            sales_ctrl["tax_due"] += sa_ctrl["tax_due"]
            sales_ctrl["net_total"] += sa_ctrl["net_total"]

        self._build_header(root, year, month, company, date_from, date_to, is_quarterly, is_correction)
        self._build_entity(root, company)
        
        if is_quarterly:
             # V7K: Only 3rd month has declaration. 
             # But here we assume we are generating the "Full Quarterly JPK" which includes declaration.
             self._build_declaration(root, year, month, sales_ctrl, purch_ctrl, is_quarterly)
        else:
             self._build_declaration(root, year, month, sales_ctrl, purch_ctrl, is_quarterly)
             
        self._build_register(root, sales_rows, purch_rows, sales_ctrl, purch_ctrl)

        tree = self.ET.ElementTree(root)
        if hasattr(self.ET, "indent"):
            self.ET.indent(tree, space="  ", level=0)
            
        tree.write(filepath, encoding="UTF-8", xml_declaration=True)

    def generate_jpk_fa(self, year: int, month: int, filepath: str, quarter: int = None):
        # Register namespace for JPK_FA (4)
        ns_fa = "http://crd.gov.pl/wzor/2022/03/18/11411/"
        self.ET.register_namespace('', ns_fa)
        self.ET.register_namespace('xsi', self.NS_XSI)
        self.ET.register_namespace('etd', "http://crd.gov.pl/xml/schematy/dziedzinowe/mf/2022/09/13/eD/DefinicjeTypy/")

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
                extract('year', Invoice.date_issue) == year,
                extract('month', Invoice.date_issue) == month
            ).all()

        self.ET.SubElement(header, f"{{{ns_fa}}}DataOd").text = date_from
        self.ET.SubElement(header, f"{{{ns_fa}}}DataDo").text = date_to
        self.ET.SubElement(header, f"{{{ns_fa}}}KodUrzedu").text = company.tax_office_code or "2206"
        self.ET.SubElement(header, f"{{{ns_fa}}}KodUrzedu").text = company.tax_office_code or "2206"

        # Podmiot1 (Issuer)
        p1 = self.ET.SubElement(root, f"{{{ns_fa}}}Podmiot1")
        id_p1 = self.ET.SubElement(p1, f"{{{ns_fa}}}IdentyfikatorPodmiotu")
        if company.nip:
            self.ET.SubElement(id_p1, f"{{{ns_fa}}}NIP").text = company.nip.replace("-", "")
        self.ET.SubElement(id_p1, f"{{{ns_fa}}}PelnaNazwa").text = company.company_name
        
        # Address P1
        adr_p1 = self.ET.SubElement(p1, f"{{{ns_fa}}}AdresPodmiotu")
        self.ET.SubElement(adr_p1, f"{{{ns_fa}}}KodKraju").text = company.country_code or "PL"
        self.ET.SubElement(adr_p1, f"{{{ns_fa}}}Wojewodztwo").text = "WLKP" # TODO: parse/config
        self.ET.SubElement(adr_p1, f"{{{ns_fa}}}Powiat").text = "-"
        self.ET.SubElement(adr_p1, f"{{{ns_fa}}}Gmina").text = company.city or "-"
        self.ET.SubElement(adr_p1, f"{{{ns_fa}}}Miejscowosc").text = company.city or "-"
        self.ET.SubElement(adr_p1, f"{{{ns_fa}}}NrDomu").text = "-" # Should be parsed from address
        self.ET.SubElement(adr_p1, f"{{{ns_fa}}}KodPocztowy").text = company.postal_code or "00-000"

        # Faktura Nodes
        gross_total_sum = 0.0
        
        for inv in invoices:
            fa_node = self.ET.SubElement(root, f"{{{ns_fa}}}Faktura")
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}KodWaluty").text = inv.currency or "PLN"
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_1").text = inv.date_issue.strftime("%Y-%m-%d")
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_2A").text = inv.number
            
            # Buyer
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_3A").text = inv.contractor.name if inv.contractor else ""
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_3B").text = f"{inv.contractor.address or ''} {inv.contractor.city or ''}" if inv.contractor else ""
            if inv.contractor and inv.contractor.nip:
                self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_3C").text = inv.contractor.nip.replace("-", "")
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_3D").text = inv.contractor.country_code or "PL" if inv.contractor else "PL"
            
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_4A").text = inv.date_sale.strftime("%Y-%m-%d")
            # P_4B usually same as P_4A for services
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_5").text = inv.currency or "PLN" # P_5 code currency
            
            # Amounts
            amounts = self._get_sales_amounts(inv) # This logic returns Deltas for Corrections.
            # JPK_FA typically expects FULL amounts for the document (Faktura), not deltas, unless it is a standard.
            # However, JPK_FA includes Kind "KOREKTA".
            # For "KOREKTA", fields P_13_x, P_14_x represent the DIFFERENCE or the NEW STATE?
            # Standard JPK_FA(4) Brochure says P_13/14 for Korekta should assume values resulting from the correction (amounts of the correction).
            # Usually users enter the difference (Delta) in correction documents (e.g. -1 item).
            # So `_get_sales_amounts` returning deltas is correct if we assume our Invoice model stores the "New State" 
            # and `_get_sales_amounts` calculates the difference. 
            # WAIT! `_get_sales_amounts` logic I wrote returns (Current - Parent). YES, that is the Delta.
            # JPK_FA for correction expects the DELTA (values that change the tax base).
            # So using `amounts` is correct.

            inv_gross = 0.0
            
            for rtype, vals in amounts.items():
                net = vals["net"]
                vat = vals["vat"]
                inv_gross += (net + vat)
                
                # Check rate mapping (JPK_FA(4))
                # P_13_1 / P_14_1 : basic rate (23)
                # P_13_2 / P_14_2 : reduced (8)
                # P_13_3 / P_14_3 : reduced (5)
                # P_13_6_1 : Zwolnione (FA(2/3?)) in FA(4) P_13_7 is Zwolnione usually? Wait
                # JPK_FA (4) Schema:
                # P_13_1 (23), P_13_2 (8), P_13_3 (5), P_13_4 (Reverse Charge? No, Export?)
                # P_13_5 (0% WDT), P_13_6 (0% Export), P_13_7 (ZW)
                # P_13_10 (OO for purchaser - art 17.1.7/8)? 
                
                if rtype == '23':
                    self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_13_1").text = f"{net:.2f}"
                    self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_14_1").text = f"{vat:.2f}"
                elif rtype == '8':
                    self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_13_2").text = f"{net:.2f}"
                    self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_14_2").text = f"{vat:.2f}"
                elif rtype == '5':
                    self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_13_3").text = f"{net:.2f}"
                    self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_14_3").text = f"{vat:.2f}"
                elif rtype == 'zw':
                    self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_13_7").text = f"{net:.2f}"
                elif rtype == '0':
                    # 0% Domestic?
                    self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_13_6").text = f"{net:.2f}"
                elif rtype == 'oo_domestic':
                    # Odwrotne Obciążenie (Seller)
                    # For JPK_FA, where does it go?
                    # P_13_10? "Dostawa towarów oraz świadczenie usług, dla których podatnikiem jest nabywca (art. 17 ust. 1 pkt 7 i 8)"
                    self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_13_10").text = f"{net:.2f}"
                elif rtype == 'export_svc':
                    # Export Usług (Art 28b) - P_13_4? No, P_13_4 is "Dostawa ... stawka 0% (art 129)"? 
                    # Actually typically Export Svc is outside of scope, but JPK_FA might capture it in P_13_5 - P_13_11 range.
                    # P_13_11 "Świadczenie usług poza terytorium kraju..." (Art 100 ust 1 pkt 4) -> This is likely K_11 equiv.
                    self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_13_11").text = f"{net:.2f}"
                
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_15").text = f"{inv_gross:.2f}"
                
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_15").text = f"{inv_gross:.2f}"
            gross_total_sum += inv_gross
            
            # Flags P_16 to P_18...
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_16").text = "true" if inv.is_cash_accounting else "false"
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_17").text = "true" if inv.is_self_billing else "false"
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_18").text = "true" if inv.is_reverse_charge else "false"
            # ... and so on. P_18A (MPP) boolean > "true"/"false"
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}P_18A").text = "true" if inv.is_split_payment else "false"

            # Invoice Type
            kind = "VAT"
            if inv.type == InvoiceType.KOREKTA:
                kind = "KOREKTA"
            elif inv.type == InvoiceType.ZALICZKA:
                kind = "ZAL"
            
            self.ET.SubElement(fa_node, f"{{{ns_fa}}}RodzajFaktury").text = kind
            
            if kind == "KOREKTA" and inv.parent_id:
                # Add correction details
                parent = self.session.query(Invoice).get(inv.parent_id)
                self.ET.SubElement(fa_node, f"{{{ns_fa}}}PrzyczynaKorekty").text = "Korekta danych" # Placeholder
                if parent:
                    self.ET.SubElement(fa_node, f"{{{ns_fa}}}NrFaKorygowanej").text = parent.number
                    self.ET.SubElement(fa_node, f"{{{ns_fa}}}OkresFaKorygowanej").text = parent.date_issue.strftime("%Y-%m-%d")

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
                self.ET.SubElement(w_node, f"{{{ns_fa}}}P_7").text = item.product_name
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
                rate_str = f"{int(item.vat_rate*100)}" if item.vat_rate else "zw"
                self.ET.SubElement(w_node, f"{{{ns_fa}}}P_12").text = rate_str
                
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
        
        wariant = self.ET.SubElement(header, f"{{{self.NS}}}WariantFormularza")
        wariant.text = "3"
        
        cel = "2" if is_correction else "1"
        self.ET.SubElement(header, f"{{{self.NS}}}CelZlozenia", poz="P_7").text = cel
        self.ET.SubElement(header, f"{{{self.NS}}}DataWytworzeniaJPK").text = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        
        self.ET.SubElement(header, f"{{{self.NS}}}DataOd").text = date_from
        self.ET.SubElement(header, f"{{{self.NS}}}DataDo").text = date_to
        
        self.ET.SubElement(header, f"{{{self.NS}}}KodUrzedu").text = company.tax_office_code or "2206"

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

    def _classify_rate_type(self, item, invoice):
        """ Classify item into JPK buckets based on rate and metadata """
        r_val = float(item.vat_rate) if item.vat_rate is not None else 0.0
        r_name = (getattr(item, 'vat_rate_name', '') or '').upper()
        
        # 1. Reverse Charge (OO)
        # Check explicit names or invoice flag
        is_oo = False
        if r_name in ['OO', 'NP', 'NP.', 'ODWROTNE OBCIĄŻENIE']:
            is_oo = True
        elif invoice.is_reverse_charge and abs(r_val) < 0.001:
            is_oo = True
            
        if is_oo:
            # Distinguish types if possible
            if "UE" in r_name or "EXPORT" in r_name or "WNT" in r_name:
                 # Refine foreign OO
                 if "USŁUG" in r_name or "SVC" in r_name:
                      return 'export_svc' # Usługi art. 28b
                 return 'oo_foreign' # Generic foreign (maybe WNT or Export Goods)
            return 'oo_domestic' # Default to K_31

        # 2. Standard Rates
        if abs(r_val - 0.23) < 0.001: return '23'
        if abs(r_val - 0.08) < 0.001: return '8'
        if abs(r_val - 0.05) < 0.001: return '5'
        
        # 3. ZW / 0%
        is_zw = False
        if "ZW" in r_name or getattr(item, 'pkwiu', '') == "ZW" or getattr(invoice, 'is_exempt', False):
             return 'zw'
             
        if abs(r_val) < 0.001:
             return '0'
             
        return 'other'

    def _get_sales_amounts(self, invoice):
        """ Calculate Net/VAT amounts per rate-type for an invoice. 
            Returns dict: type_code -> {net, vat}
        """
        # Get current items
        current_items = invoice.items 
        
        # Helper to sum by classified type
        def sum_by_type(items):
            sums = {} 
            for i in items:
                rtype = self._classify_rate_type(i, invoice)
                
                if rtype not in sums: sums[rtype] = {"net": 0.0, "vat": 0.0}
                
                qty = float(i.quantity or 0)
                net_price = float(i.net_price or 0)
                net_val = qty * net_price
                
                gross_val = float(i.gross_value or 0)
                vat_val = gross_val - net_val
                
                sums[rtype]["net"] += net_val
                sums[rtype]["vat"] += vat_val
            return sums

        current_sums = sum_by_type(current_items)
        
        if invoice.type == InvoiceType.KOREKTA and invoice.parent_id:
            parent = self.session.query(Invoice).filter(Invoice.id == invoice.parent_id).first()
            if parent:
                parent_sums = sum_by_type(parent.items)
                all_types = set(current_sums.keys()) | set(parent_sums.keys())
                final_sums = {}
                for t in all_types:
                    c_n = current_sums.get(t, {}).get("net", 0.0)
                    c_v = current_sums.get(t, {}).get("vat", 0.0)
                    p_n = parent_sums.get(t, {}).get("net", 0.0)
                    p_v = parent_sums.get(t, {}).get("vat", 0.0)
                    final_sums[t] = {"net": c_n - p_n, "vat": c_v - p_v}
                return final_sums
        
        return current_sums

    def _get_sales_data(self, year, month):
        query = self.session.query(Invoice).filter(
            Invoice.category == InvoiceCategory.SALES,
            extract('year', Invoice.date_issue) == year,
            extract('month', Invoice.date_issue) == month
        ) # Order by date?
        invoices = query.all()
        
        rows = []
        ctrl = {"count": 0, "tax_due": 0.0, "net_total": 0.0}
        
        for inv in invoices:
            amounts = self._get_sales_amounts(inv)
            
            # Map columns
            row_data = {}
            row_data["contractor_name"] = inv.contractor.name if inv.contractor else "Brak"
            row_data["contractor_nip"] = (inv.contractor.nip or "").replace("-", "") if inv.contractor else ""
            row_data["contractor_country"] = inv.contractor.country_code or "PL" if inv.contractor else "PL"
            row_data["inv_number"] = inv.number
            row_data["date_issue"] = inv.date_issue.strftime("%Y-%m-%d")
            row_data["date_sale"] = inv.date_sale.strftime("%Y-%m-%d")
            
            # Use Payment Deadline from invoice if present
            if inv.payment_deadline:
                 row_data["TerminPlatnosci"] = inv.payment_deadline.strftime("%Y-%m-%d")
            
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
            fields = []
            
            for rtype, vals in amounts.items():
                net = vals["net"]
                vat = vals["vat"]
                
                if abs(net) < 0.01 and abs(vat) < 0.01:
                    continue
                
                # Mapping based on classified type
                if rtype == '23':
                    fields.append(("K_19", net))
                    fields.append(("K_20", vat))
                    ctrl["tax_due"] += vat
                    ctrl["net_total"] += net
                elif rtype == '8':
                    fields.append(("K_17", net))
                    fields.append(("K_18", vat))
                    ctrl["tax_due"] += vat
                    ctrl["net_total"] += net
                elif rtype == '5':
                    fields.append(("K_15", net))
                    fields.append(("K_16", vat))
                    ctrl["tax_due"] += vat
                    ctrl["net_total"] += net
                elif rtype == 'zw':
                    fields.append(("K_10", net))
                    ctrl["net_total"] += net
                elif rtype == '0':
                    # 0% Domestic
                    fields.append(("K_13", net))
                    ctrl["net_total"] += net
                elif rtype == 'oo_domestic':
                    # K_31 (Seller OO)
                    fields.append(("K_31", net))
                    ctrl["net_total"] += net
                elif rtype == 'export_svc':
                     # K_11 (Export Usług Art 28B)
                    fields.append(("K_11", net))
                    ctrl["net_total"] += net
                # else: ignore or fallback
            
            if fields:
                row_data["fields"] = fields
                rows.append(row_data)
                ctrl["count"] += 1
                
        return rows, ctrl

    def _get_purchase_self_assessment_data(self, year, month):
        """ Generate Sales Register entries for Purchases with OO (Self Assessment) """
        query = self.session.query(Invoice).filter(
            Invoice.category == InvoiceCategory.PURCHASE,
            extract('year', Invoice.date_issue) == year,
            extract('month', Invoice.date_issue) == month
        )
        invoices = query.all()
        rows = []
        ctrl_add = {"count": 0, "tax_due": 0.0, "net_total": 0.0}
        
        for inv in invoices:
            amounts = self._get_sales_amounts(inv) # Returns classified amounts
            
            has_oo = False
            oo_net = 0.0
            
            # Check for OO items
            for rtype, vals in amounts.items():
                 if rtype in ['oo_domestic', 'oo_foreign', 'export_svc'] or (rtype=='0' and inv.is_reverse_charge):
                      has_oo = True
                      oo_net += vals["net"]
            
            if has_oo and abs(oo_net) > 0.01:
                 # Create Artificial Sales Row
                 row_data = {}
                 row_data["contractor_name"] = inv.contractor.name if inv.contractor else "Brak"
                 row_data["contractor_nip"] = (inv.contractor.nip or "").replace("-", "") if inv.contractor else ""
                 row_data["contractor_country"] = inv.contractor.country_code or "PL" if inv.contractor else "PL"
                 row_data["inv_number"] = f"WEW/{inv.number}" # Mark as internal/self reference
                 row_data["date_issue"] = inv.date_issue.strftime("%Y-%m-%d")
                 row_data["date_sale"] = inv.date_issue.strftime("%Y-%m-%d") # Use issue date?
                 row_data["doc_type"] = "WEW"
                 
                 # Calculate Virtual VAT (assuming 23% standard for self-assessment unless specialized)
                 # Prompt: "sam wyliczyłeś, np. 23%"
                 virt_vat = oo_net * 0.23
                 
                 # Map to K_32/33 (Purchase OO -> Sales Register)
                 # Wait, K_31 is for SELLER OO.
                 # K_32/33 is for BUYER OO.
                 fields = []
                 fields.append(("K_32", oo_net))
                 fields.append(("K_33", virt_vat))
                 
                 row_data["fields"] = fields
                 rows.append(row_data)
                 ctrl_add["count"] += 1
                 ctrl_add["tax_due"] += virt_vat
                 ctrl_add["net_total"] += oo_net
                 
        return rows, ctrl_add

    def _get_purchase_data(self, year, month):
        # Similar logic for PURCHASES (K_40 - K_48)
        # Simplified: K_42/43 (Nabycie dóbr pozostałych)
        query = self.session.query(Invoice).filter(
            Invoice.category == InvoiceCategory.PURCHASE,
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
                
            row_data = {}
            row_data["contractor_name"] = inv.contractor.name if inv.contractor else "Brak"
            row_data["contractor_nip"] = (inv.contractor.nip or "").replace("-", "") if inv.contractor else ""
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
            row_data["DokumentZakupu"] = "" 
            
            row_data["K_42"] = total_net
            row_data["K_43"] = total_vat
            
            rows.append(row_data)
            ctrl["count"] += 1
            ctrl["input_tax"] += total_vat
            
        return rows, ctrl

    def _build_declaration(self, root, year, month, sales_ctrl, purch_ctrl, is_quarterly=False):
        # Deklaracja block
        deklaracja = self.ET.SubElement(root, f"{{{self.NS}}}Deklaracja")
        naglowek = self.ET.SubElement(deklaracja, f"{{{self.NS}}}Naglowek")
        
        kod_sys = "VAT-7K (23)" if is_quarterly else "VAT-7 (23)"
        
        self.ET.SubElement(naglowek, f"{{{self.NS}}}KodFormularzaDekl", kodSystemowy=kod_sys, wersjaSchemy="1-0E").text = "VAT-7"
        self.ET.SubElement(naglowek, f"{{{self.NS}}}WariantFormularzaDekl").text = "23"
        
        pozycje = self.ET.SubElement(deklaracja, f"{{{self.NS}}}PozycjeSzczegolowe")
        
        tax_due = sales_ctrl["tax_due"]
        net_total = sales_ctrl.get("net_total", 0.0)
        input_tax = purch_ctrl["input_tax"]
        
        # P_37: Łączna wysokość podstawy opodatkowania (Net Total)
        self.ET.SubElement(pozycje, f"{{{self.NS}}}P_37").text = str(round(net_total))
        # P_38: Łączna wysokość podatku należnego (Tax Due)
        self.ET.SubElement(pozycje, f"{{{self.NS}}}P_38").text = str(round(tax_due))
        
        # P_48: Łączna wysokość podatku naliczonego do odliczenia (Input Tax)
        self.ET.SubElement(pozycje, f"{{{self.NS}}}P_48").text = str(round(input_tax))
        
        # P_51: Kwota podatku należnego ogółem (Usually sum of P_38 + others)
        self.ET.SubElement(pozycje, f"{{{self.NS}}}P_51").text = str(round(tax_due))
        
        # P_62: Kwota podatku naliczonego do odliczenia (Usually sum of P_48 + others)
        self.ET.SubElement(pozycje, f"{{{self.NS}}}P_62").text = str(round(input_tax))
        
        # P_54: Kwota do przeniesienia (0 for simple case)
        self.ET.SubElement(pozycje, f"{{{self.NS}}}P_54").text = "0" 
        
        self.ET.SubElement(root, f"{{{self.NS}}}Pouczenia").text = "1"

    def _build_register(self, root, sales_rows, purch_rows, sales_ctrl, purch_ctrl):
        ewidencja = self.ET.SubElement(root, f"{{{self.NS}}}Ewidencja")
        
        # Sales
        for idx, row in enumerate(sales_rows, start=1):
            wiersz = self.ET.SubElement(ewidencja, f"{{{self.NS}}}SprzedazWiersz")
            
            self.ET.SubElement(wiersz, f"{{{self.NS}}}LpSprzedazy").text = str(idx)
            self.ET.SubElement(wiersz, f"{{{self.NS}}}KodKrajuNadaniaTIN").text = row.get("contractor_country", "PL")
            self.ET.SubElement(wiersz, f"{{{self.NS}}}NrKontrahenta").text = row["contractor_nip"]
            self.ET.SubElement(wiersz, f"{{{self.NS}}}NazwaKontrahenta").text = row["contractor_name"]
            self.ET.SubElement(wiersz, f"{{{self.NS}}}DowodSprzedazy").text = row["inv_number"]
            self.ET.SubElement(wiersz, f"{{{self.NS}}}DataWystawienia").text = row["date_issue"]
            self.ET.SubElement(wiersz, f"{{{self.NS}}}DataSprzedazy").text = row["date_sale"]
            
            if row.get("ksef_number"):
                self.ET.SubElement(wiersz, f"{{{self.NS}}}NrKSeF").text = row["ksef_number"]
            
            if row.get("doc_type"):
                self.ET.SubElement(wiersz, f"{{{self.NS}}}TypDokumentu").text = row["doc_type"]
            
            # GTU
            # Start with explicit order or just sort
            for gtu in sorted(row.get("gtu_flags", [])):
                self.ET.SubElement(wiersz, f"{{{self.NS}}}{gtu}").text = "1"
            
            # Procedures
            for proc in sorted(row.get("procedures", [])):
                self.ET.SubElement(wiersz, f"{{{self.NS}}}{proc}").text = "1"
            
            # KorektaPodstawyOpodt (placeholder logic, usually connected to correction or bad debt)
            # self.ET.SubElement(wiersz, f"{{{self.NS}}}KorektaPodstawyOpodt").text = "1"
            
            if row.get("TerminPlatnosci"):
                self.ET.SubElement(wiersz, f"{{{self.NS}}}TerminPlatnosci").text = row["TerminPlatnosci"]
                
             # SprzedazVAT_Marza (Gross Value for Margin Procedure)
            if row.get("SprzedazVAT_Marza"):
                 self.ET.SubElement(wiersz, f"{{{self.NS}}}SprzedazVAT_Marza").text = f"{row['SprzedazVAT_Marza']:.2f}"

            # Taxes
            for k, v in row["fields"]:
                self.ET.SubElement(wiersz, f"{{{self.NS}}}{k}").text = f"{v:.2f}"
            
            # Other fields mentioned in example? SprzedazVAT_Marza usually 0 or omitted

                
        ctrl_s = self.ET.SubElement(ewidencja, f"{{{self.NS}}}SprzedazCtrl")
        self.ET.SubElement(ctrl_s, f"{{{self.NS}}}LiczbaWierszySprzedazy").text = str(sales_ctrl["count"])
        self.ET.SubElement(ctrl_s, f"{{{self.NS}}}PodatekNalezny").text = f"{sales_ctrl['tax_due']:.2f}"
        
        # Purchases
        for idx, row in enumerate(purch_rows, start=1):
            wiersz = self.ET.SubElement(ewidencja, f"{{{self.NS}}}ZakupWiersz")
            
            self.ET.SubElement(wiersz, f"{{{self.NS}}}LpZakupu").text = str(idx)
            self.ET.SubElement(wiersz, f"{{{self.NS}}}KodKrajuNadaniaTIN").text = "PL" # Defaulting for purchase
            self.ET.SubElement(wiersz, f"{{{self.NS}}}NrDostawcy").text = row["contractor_nip"]
            self.ET.SubElement(wiersz, f"{{{self.NS}}}NazwaDostawcy").text = row["contractor_name"]
            self.ET.SubElement(wiersz, f"{{{self.NS}}}DowodZakupu").text = row["inv_number"]
            self.ET.SubElement(wiersz, f"{{{self.NS}}}DataZakupu").text = row["date_purchase"]
            self.ET.SubElement(wiersz, f"{{{self.NS}}}DataWplywu").text = row["date_receive"]
            
            # Purchase also has NrKSeF?
            # Assuming we might store it in inv.related_ksef_number or simply ksef_number if it's a purchase invoice we registered?
            # Usually only Sales have our KSeF number. Purchase invoices have supplier's KSeF number. 
            # Our Invoice model for PURCHASE category.
            # Let's see if we have ksef_number in row data.
            # We need to map it in _get_purchase_data
            if row.get("ksef_number"):
                self.ET.SubElement(wiersz, f"{{{self.NS}}}NrKSeF").text = row["ksef_number"]
            
            if row.get("DokumentZakupu"):
                self.ET.SubElement(wiersz, f"{{{self.NS}}}DokumentZakupu").text = row["DokumentZakupu"]
            
            self.ET.SubElement(wiersz, f"{{{self.NS}}}K_42").text = f"{row['K_42']:.2f}"
            self.ET.SubElement(wiersz, f"{{{self.NS}}}K_43").text = f"{row['K_43']:.2f}"
            
        ctrl_p = self.ET.SubElement(ewidencja, f"{{{self.NS}}}ZakupCtrl")
        self.ET.SubElement(ctrl_p, f"{{{self.NS}}}LiczbaWierszyZakupow").text = str(purch_ctrl["count"])
        self.ET.SubElement(ctrl_p, f"{{{self.NS}}}PodatekNaliczony").text = f"{purch_ctrl['input_tax']:.2f}"
