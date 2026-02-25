from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableView, QHeaderView, 
                             QPushButton, QAbstractItemView, QMessageBox, QLabel, QMenu, QFileDialog, QDialog, 
                             QDialogButtonBox, QLineEdit, QFormLayout, QDateEdit, QProgressDialog, QRadioButton, QButtonGroup, QApplication)
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QDate, QThread, Signal, QTimer, QSettings
from PySide6.QtGui import QAction, QCursor, QColor
from database.engine import get_db
from database.models import Invoice, InvoiceCategory, CompanyConfig, Contractor, InvoiceType, InvoiceItem
from sqlalchemy.orm import joinedload
from ksef.xml_generator import KsefXmlGenerator
from ksef.client import KsefClient
from lxml import etree
import os
import datetime
import logging

logger = logging.getLogger(__name__)

class KsefSendWorker(QThread):
    finished_signal = Signal(dict)

    def __init__(self, xml_bytes, parent=None):
        super().__init__(parent)
        self.xml_bytes = xml_bytes

    def run(self):
        db = next(get_db())
        try:
            config = db.query(CompanyConfig).first()
            if not config:
                 self.finished_signal.emit({"success": False, "error": "Brak konfiguracji w tle."})
                 return
            
            # Re-init client in this thread
            client = KsefClient(config)
            
            # Auth
            try:
                # Wymuszenie autoryzacji (lub sprawdzenie czy token/sesja jest aktywna)
                client.authenticate(config.nip)
            except Exception as e:
                # Jeśli błąd autoryzacji jest krytyczny, to send_invoice też nie pójdzie
                # Ale w trybie testowym czasem pomijamy
                print(f"Auth error in thread: {e}")

            # Send
            resp = client.send_invoice(self.xml_bytes)
            self.finished_signal.emit(resp)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished_signal.emit({"success": False, "error": str(e)})
        finally:
            db.close()

class KsefSyncWorker(QThread):
    progress = Signal(str)
    finished_count = Signal(int)
    error = Signal(str)

    def __init__(self, config, category, start_date, end_date):
        super().__init__()
        self.config = config
        self.category = category
        self.start_date = start_date
        self.end_date = end_date
        self.is_running = True

    def run(self):
        try:
            self.progress.emit("Inicjalizacja klienta KSeF...")
            client = KsefClient(self.config)
            
            self.progress.emit(f"Logowanie jako: {self.config.nip}...")
            client.authenticate(self.config.nip)
            
            # Determine subject type
            # PURCHASE -> Subject2 (Otrzymane/Zakup)
            # SALES -> Subject1 (Wystawione/Sprzedaż)
            subj = "subject2" if self.category == InvoiceCategory.PURCHASE else "subject1"
            
            self.progress.emit("Pobieranie listy faktur...")
            # Convert QDate/string to datetime
            dt_start = datetime.datetime.strptime(self.start_date, "%Y-%m-%d")
            dt_end = datetime.datetime.strptime(self.end_date, "%Y-%m-%d")
            # Set end of day for end date
            dt_end = dt_end.replace(hour=23, minute=59, second=59)

            list_res = client.get_invoice_list(dt_start, dt_end, subject_type=subj)
            invoices_meta = list_res.get("invoices", [])
            
            total = len(invoices_meta)
            self.progress.emit(f"Znaleziono {total} faktur. Rozpoczynam pobieranie...")
            
            db = next(get_db())
            count_imported = 0
            
            try:
                for i, meta in enumerate(invoices_meta):
                    if not self.is_running: break
                    
                    # Note: API KSeF v2 structure returns "ksefNumber" in invoice list query response, NOT "ksefReferenceNumber"
                    ksef_num = meta.get("ksefNumber") or meta.get("ksefReferenceNumber")
                    self.progress.emit(f"Pobieranie [{i+1}/{total}]: {ksef_num}...")
                    logger.info(f"Processing invoice {ksef_num}...")
                    
                    # Check if exists
                    exists = db.query(Invoice).filter(Invoice.ksef_number == ksef_num).first()
                    if exists:
                        logger.info(f"Invoice {ksef_num} already exists in DB. Skipping.")
                        continue
                    
                    # Download XML
                    logger.info(f"Downloading XML for {ksef_num}...")
                    try:
                        xml_bytes = client.get_invoice_xml(ksef_num)
                        logger.info(f"Downloaded XML for {ksef_num} ({len(xml_bytes)} bytes).")
                    except Exception as e:
                        logger.error(f"Failed to download XML for {ksef_num}: {e}")
                        raise e

                    # Parse and Save
                    self.import_invoice(db, xml_bytes, ksef_num, meta)
                    count_imported += 1
                
                db.commit()
                logger.info(f"Batch processing complete. Committed {count_imported} invoices.")
            except Exception as e:
                logger.error(f"Worker Error (Rolling back): {e}")
                db.rollback()
                raise e
            finally:
                db.close()

            self.finished_count.emit(count_imported)
            
        except Exception as e:
            self.error.emit(str(e))
    
    def stop(self):
        self.is_running = False

    def import_invoice(self, db, xml_bytes, ksef_num, meta):
        # Basic parsing using lxml
        root = etree.fromstring(xml_bytes)
        # Remove namespaces for easier search
        for elem in root.getiterator():
            if not hasattr(elem.tag, 'find'): continue
            i = elem.tag.find('}')
            if i >= 0:
                elem.tag = elem.tag[i+1:]
        
        # Helper to get text
        def txt(tag):
            el = root.find(f".//{tag}")
            return el.text if el is not None else None
            
        def txt_node(node, tag):
             el = node.find(tag)
             return el.text if el is not None else None

        # Data
        inv_number = txt("P_2")
        date_issue_str = txt("P_1")
        place_issue = txt("P_1M")
        
        # Check uniqueness by number as well
        if inv_number:
            exists_num = db.query(Invoice).filter(Invoice.number == inv_number).first()
            if exists_num:
                # Update ksef number just in case
                if not exists_num.ksef_number:
                    exists_num.ksef_number = ksef_num
                    exists_num.is_sent_to_ksef = True
                    # Update cache xml if missing
                    if not exists_num.ksef_xml:
                        try:
                            exists_num.ksef_xml = xml_bytes.decode("utf-8")
                        except:
                            exists_num.ksef_xml = str(xml_bytes)
                return

        inv = Invoice()
        inv.category = self.category
        inv.place_of_issue = place_issue
        inv.ksef_number = ksef_num
        inv.environment = self.config.ksef_environment or "test"
        inv.is_sent_to_ksef = True
        inv.number = inv_number or f"KSEF/{ksef_num}"
        # Save Original XML from KSeF
        # Ensure we decode bytes to string for TEXT column
        try:
             inv.ksef_xml = xml_bytes.decode("utf-8")
        except:
             # Fallback if encoding issues
             inv.ksef_xml = str(xml_bytes)
        
        # Detect Type (KOR)
        inv_type_code = txt("RodzajFaktury")
        if inv_type_code == "KOR":
             inv.type = InvoiceType.KOREKTA
        
        if date_issue_str:
            inv.date_issue = datetime.datetime.strptime(date_issue_str, "%Y-%m-%d").date()
            
        # Link Parent for Corrections
        if inv.type == InvoiceType.KOREKTA:
             node_korygowana = root.find(".//DaneFaKorygowanej")
             if node_korygowana is not None:
                  ref_ksef = None
                  ref_nr = None
                  
                  # Look for fields in DaneFaKorygowanej
                  n_ksef = node_korygowana.find("NrKSeFFaKorygowanej")
                  if n_ksef is not None: ref_ksef = n_ksef.text
                  
                  n_nr = node_korygowana.find("NrFaKorygowanej")
                  if n_nr is not None: ref_nr = n_nr.text
                  
                  # Search Parent
                  parent_inv = None
                  if ref_ksef:
                       parent_inv = db.query(Invoice).filter(Invoice.ksef_number == ref_ksef).first()
                  
                  if not parent_inv and ref_nr:
                       # Try fuzzy match by number + category
                       parent_inv = db.query(Invoice).filter(
                           Invoice.number == ref_nr, 
                           Invoice.category == self.category
                       ).first()
                       
                  if parent_inv:
                       inv.parent_id = parent_inv.id
        
        # Contractor (Sprzedawca if Purchase, Nabywca if Sales)
        # Assuming Purchase for now mainly
        if self.category == InvoiceCategory.PURCHASE:
             # Look for Sprzedawca (Podmiot1)
             # Path: Podmiot1/DaneIdentyfikacyjne/NIP
             # Actually in FA(2):
             # Podmiot1 -> DaneIdentyfikacyjne -> NIP
             pass
        
        # Find Contractor NIP
        # Try finding NIP of the OTHER party
        # If Purchase (Subject2), we want Subject1 (Seller) data
        # Structure: Fa/Podmiot1 (Seller), Fa/Podmiot2 (Buyer)
        
        target_subject = "Podmiot1" if self.category == InvoiceCategory.PURCHASE else "Podmiot2"
        
        nip_node = root.find(f".//{target_subject}/DaneIdentyfikacyjne/NIP")
        nip = nip_node.text if nip_node is not None else None
        
        if nip:
            ctr = db.query(Contractor).filter(Contractor.nip == nip).first()
            if not ctr:
                # Create Contractor
                # FIX: Use 'is None' to avoid FutureWarning for lxml Elements with no children
                name_node = root.find(f".//{target_subject}/DaneIdentyfikacyjne/Nazwa") 
                if name_node is None:
                     name_node = root.find(f".//{target_subject}/DaneIdentyfikacyjne/ImiePierwsze")
                     if name_node is not None:
                         surname = root.find(f".//{target_subject}/DaneIdentyfikacyjne/Nazwisko")
                         name_val = f"{name_node.text} {surname.text if surname is not None else ''}".strip()
                     else:
                         name_val = f"Podmiot {nip}"
                else:
                    name_val = name_node.text

                # Address Extraction
                # Try AdresPol (Structured) first
                addr_node = root.find(f".//{target_subject}/Adres/AdresPol")
                address = ""
                city = ""
                postal = ""
                
                if addr_node is not None:
                     l1 = addr_node.find("Ulica")
                     l2 = addr_node.find("NrDomu")
                     l2a = addr_node.find("NrLokalu")
                     l3 = addr_node.find("Miejscowosc")
                     l4 = addr_node.find("KodPocztowy")
                     
                     street = l1.text if l1 is not None else ""
                     house = l2.text if l2 is not None else ""
                     flat = f"/{l2a.text}" if l2a is not None and l2a.text else ""
                     
                     address = f"{street} {house}{flat}".strip()
                     city = l3.text if l3 is not None else ""
                     postal = l4.text if l4 is not None else ""
                else:
                     # Check flat structure (AdresL1, AdresL2, etc.) common in FA(2)
                     base_addr = root.find(f".//{target_subject}/Adres")
                     if base_addr is not None:
                         l1 = base_addr.find("AdresL1") # Usually Street + House
                         l2 = base_addr.find("AdresL2") # Usually City + Zip
                         
                         if l1 is not None: address = l1.text or ""
                         if l2 is not None: 
                             # Very basic heuristic: last word is city? Unreliable.
                             # Just put everything in city if distinct fields missing
                             city = l2.text or ""

                ctr = Contractor(nip=nip, name=name_val, address=address, city=city, postal_code=postal)
                db.add(ctr)
                db.flush() # get ID
            
            inv.contractor_id = ctr.id

            # SNAPSHOT LOGIC (Preserve data from imported XML/Contractor state)
            ctr_snapshot = {
                "nip": ctr.nip,
                "name": ctr.name,
                "address": ctr.address,
                "city": ctr.city,
                "postal_code": ctr.postal_code,
                "country_code": getattr(ctr, 'country_code', 'PL'),
                "is_vat_payer": getattr(ctr, 'is_vat_payer', True),
                "is_vat_ue": getattr(ctr, 'is_vat_ue', False),
                "is_person": getattr(ctr, 'is_person', False)
            }
            
            # Get Company Config (US)
            comp = db.query(CompanyConfig).first()
            us_snapshot = {}
            if comp:
                us_snapshot = {
                    "nip": comp.nip,
                    "company_name": comp.company_name,
                    "address": comp.address,
                    "city": comp.city,
                    "postal_code": comp.postal_code,
                    "country_code": comp.country_code,
                    "bank_account": comp.bank_account,
                    "bank_name": comp.bank_name
                }
            
            if self.category == InvoiceCategory.PURCHASE:
                # Contractor is Seller
                inv.seller_snapshot = ctr_snapshot
                inv.buyer_snapshot = us_snapshot
            else:
                # Contractor is Buyer
                inv.seller_snapshot = us_snapshot
                inv.buyer_snapshot = ctr_snapshot
            
        # Amounts
        # P_13_1 (Netto), P_14_1 (VAT) ... Summing up or P_15 (Total Gross)
        # P_15 is total amount to pay usually
        p15 = txt("P_15")
        if p15:
            inv.total_gross = float(p15)
            # Aproksymacja netto?
            # Better calculate from sections if possible.
            # Simplified:
            inv.total_net = inv.total_gross / 1.23 # Very rough approximation if not parsing detailed lines
            
            # Try to sum fields P_13_x
            net_sum = 0.0
            for i in range(1, 7): # P_13_1 to P_13_6 ?
                 val = txt(f"P_13_{i}")
                 if val: net_sum += float(val)
            if net_sum > 0:
                 inv.total_net = net_sum

        # --- Flags & Annotations (Adnotacje) ---
        adnotacje = root.find(".//Adnotacje")
        if adnotacje is not None:
             def check_flag(tag):
                 node = adnotacje.find(tag)
                 return True if node is not None and node.text == "1" else False
             
             inv.is_cash_accounting = check_flag("P_16")
             inv.is_self_billing = check_flag("P_17")
             inv.is_reverse_charge = check_flag("P_18")
             inv.is_split_payment = check_flag("P_18A")
             
             # Exemption
             if check_flag("Zwolnienie/P_19N") or check_flag("Zwolnienie/P_19Z"): # P_19N=1 means Not Exempt usually? No wait.
                 pass # Logic is complex. P_19=1 in FA(1). FA(2) uses choice.
                 # Actually for P_19 (Exempt):
                 # FA(2): <Zwolnienie> <P_19N>1</P_19N> </Zwolnienie> means NOT exempt (N=Nie).
                 # If <P_19>1</P_19> was present it would be exempt.
                 # Let's rely on simple checks or field presence
                 
             # Check if is_exempt needs to be set based on P_19=1 (Old) or Zwolnienie structure
             # If P_19 exists and == 1 -> Exempt.
             # In FA(2), if <P_19A>, <P_19B>, <P_19C> exist inside Zwolnienie -> Exempt.
             zw = adnotacje.find("Zwolnienie")
             if zw is not None:
                 if zw.find("P_19A") is not None or zw.find("P_19B") is not None or zw.find("P_19C") is not None:
                      inv.is_exempt = True
                      if zw.find("P_19A") is not None: inv.exemption_basis_type = "USTAWA"
                      if zw.find("P_19B") is not None: inv.exemption_basis_type = "DYREKTYWA"
                      if zw.find("P_19C") is not None: inv.exemption_basis_type = "INNE"

        # --- Registers (Stopka) ---
        stopka = root.find(".//Stopka")
        if stopka is not None:
             # If Purchase, we might want to store this on Contractor OR Invoice (as snapshot)
             # Currently Invoice model has these fields but semantically often for "Own Company".
             # But for Purchase invoice, they represent the Seller.
             regs = stopka.find("Rejestry")
             if regs is not None:
                  krs_node = regs.find("KRS")
                  if krs_node is not None: inv.krs = krs_node.text
                  
                  bdo_node = regs.find("BDO")
                  if bdo_node is not None: inv.bdo = bdo_node.text
                  
                  # Also update Contractor if found?
                  if inv.contractor:
                       if krs_node is not None and not inv.contractor.krs: # Assuming Contractor has KRS column?
                            pass # Contractor model usually doesn't have KRS in simple schema, check models.
                            
        # --- Items (FaWiersz) ---
        items_map = {} # Key: NrWierszaFa, Value: InvoiceItem instance
        processed_ids = set()
        
        idx_ctr = 1
        for row in root.findall('.//FaWiersz'):
            try:
                # Deduplicate based on NrWierszaFa
                row_id = txt_node(row, 'NrWierszaFa')
                if row_id and row_id in processed_ids:
                    continue
                if row_id:
                    processed_ids.add(row_id)
                
                name_txt = txt_node(row, 'P_7') or "Towar/Usługa"
                qty_txt = txt_node(row, 'P_8B') or "1"
                unit_txt = txt_node(row, 'P_8A') or "szt"
                net_price_txt = txt_node(row, 'P_9A') or "0"
                net_val_txt = txt_node(row, 'P_11') or "0" # Net Total for line
                vat_txt = txt_node(row, 'P_12') or "23"
                
                # NrWierszaFa (Unique ID for this invoice)
                row_id = txt_node(row, 'NrWierszaFa')
                
                qty = float(qty_txt.replace(',', '.'))
                net_price = float(net_price_txt.replace(',', '.'))
                net_val = float(net_val_txt.replace(',', '.'))
                
                # Parse VAT
                vat_rate = 0.23
                if vat_txt.isdigit():
                    vat_rate = float(vat_txt) / 100.0
                elif vat_txt == "zw":
                    vat_rate = 0.0
                
                # Calc Gross
                if net_val > 0:
                     gross_val = net_val * (1 + vat_rate)
                else:
                     gross_val = (net_price * qty) * (1 + vat_rate)

                item = InvoiceItem(
                    index=idx_ctr,
                    product_name=name_txt,
                    quantity=qty,
                    unit=unit_txt,
                    net_price=net_price,
                    vat_rate=vat_rate,
                    gross_value=gross_val
                    # pkwiu? gtu?
                )
                
                inv.items.append(item)
                if row_id:
                    items_map[row_id] = item
                    
                idx_ctr += 1
            except Exception as e:
                logger.warning(f"Failed to parse item row: {e}")

        # --- Descriptions (DodatkowyOpis) ---
        # Can link to Items via NrWiersza
        for desc_node in root.findall('.//DodatkowyOpis'):
             try:
                 nr_wiersza = txt_node(desc_node, 'NrWiersza')
                 klucz = txt_node(desc_node, 'Klucz')
                 wartosc = txt_node(desc_node, 'Wartosc')
                 
                 if nr_wiersza and nr_wiersza in items_map:
                      target_item = items_map[nr_wiersza]
                      # We have only one pair of columns (key/value) in model currently
                      # If multiple descriptions per item, we might overwrite or concat.
                      # Let's concat if exists
                      if target_item.description_key:
                           if target_item.description_key != klucz:
                                target_item.description_key += f"; {klucz}"
                                target_item.description_value += f"; {wartosc}"
                           else:
                                target_item.description_value += f"; {wartosc}"
                      else:
                           target_item.description_key = klucz
                           target_item.description_value = wartosc
             except Exception:
                 pass

        db.add(inv)

class InvoiceTableModel(QAbstractTableModel):
    def __init__(self, invoices=None):
        super().__init__()
        self.invoices = invoices or []
        self.headers = ["Numer", "Data", "Kontrahent", "Netto", "Brutto", "Status KSeF"]

    def rowCount(self, parent=QModelIndex()):
        return len(self.invoices)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.invoices)):
            return None
        
        invoice = self.invoices[index.row()]
        col = index.column()

        # Highlight Corrections based on Invoice metadata
        if role == Qt.ForegroundRole:
             if invoice.type == InvoiceType.KOREKTA:
                  return QColor("#E65100") # Dark Orange / Rust

        if role == Qt.DisplayRole:
            if col == 0:
                prefix = "[KOR] " if invoice.type == InvoiceType.KOREKTA else ""
                return f"{prefix}{invoice.number}"
            elif col == 1: 
                return invoice.date_issue.strftime("%Y-%m-%d") if invoice.date_issue else ""
            elif col == 2: 
                # Use snapshot data if available to reflect historical state
                import json
                name = "Brak"
                
                # Check snapshot based on category
                if invoice.category == InvoiceCategory.SALES:
                     # For Sales, we care about the Buyer (our customer)
                     if invoice.buyer_snapshot:
                          try:
                              snap = invoice.buyer_snapshot
                              if isinstance(snap, str): snap = json.loads(snap)
                              if snap and snap.get('name'):
                                  return snap.get('name')
                          except: pass
                
                elif invoice.category == InvoiceCategory.PURCHASE:
                     # For Purchase, we care about the Seller (our supplier)
                     if invoice.seller_snapshot:
                          try:
                              snap = invoice.seller_snapshot
                              if isinstance(snap, str): snap = json.loads(snap)
                              if snap and snap.get('name'):
                                  return snap.get('name')
                          except: pass

                # Fallback to current relation
                if invoice.contractor:
                    name = invoice.contractor.name 
                return name
            elif col == 3: 
                return f"{invoice.total_net:.2f}"
            elif col == 4: 
                return f"{invoice.total_gross:.2f}"
            elif col == 5: 
                if invoice.category == InvoiceCategory.PURCHASE:
                     if invoice.ksef_number: return "Pobrana z KSeF"
                     return "Ręczna"
                else:
                     if invoice.upo_datum: return "Wysłana i Potwierdzona"
                     if invoice.ksef_number: return "Wysłano (Czekam na UPO)"
                     return "Nie wysłano" if not invoice.is_sent_to_ksef else "W kolejce"
        
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.headers[section]
        return None
    
    def update_data(self, new_invoices):
        self.beginResetModel()
        self.invoices = new_invoices
        self.endResetModel()
    
    def get_invoice(self, row):
        if 0 <= row < len(self.invoices):
            return self.invoices[row]
        return None

class InvoiceView(QWidget):
    def __init__(self, category):
        super().__init__()
        self.category = category
        self.xml_gen = KsefXmlGenerator()
        self.current_user = None # Set via set_permissions
        self.init_ui()
        self.load_invoices()
        
    def set_permissions(self, user):
        self.current_user = user
        # Apply logic
        if self.category == InvoiceCategory.PURCHASE:
             # Limit Receiving
             if self.sync_ksef_btn:
                 can_receive = getattr(user, 'perm_receive_ksef', False)
                 self.sync_ksef_btn.setVisible(can_receive)
                 if "Pobierz z KSeF" in self.sync_ksef_btn.text():
                     # self.sync_ksef_btn.setEnabled(can_receive) # Already hidden
                     pass
        
        # Limit Sending (Logic inside on_table_context_menu or button?)
        # Sales invoices have context menu "Wyślij do KSeF"
        # I need to store this permission to check later in context menu

    def showEvent(self, event):
        self.load_invoices()
        super().showEvent(event)

    def init_ui(self):
        layout = QVBoxLayout(self)
        self.settings = QSettings("KsefInvoice", "Filters")

        # Header
        header_lay = QHBoxLayout()
        header_lay.setContentsMargins(0, 0, 0, 10)
        
        title_str = "Faktury Sprzedaży" if self.category == InvoiceCategory.SALES else "Faktury Zakupu"
        title = QLabel(title_str)
        title.setStyleSheet("font-size: 24px; font-weight: bold; margin-right: 20px;")
        header_lay.addWidget(title)
        
        # Spacer
        header_lay.addStretch()

        # KSeF Environment Indicator (Dynamic)
        self.test_label = QLabel("KSEF TEST")
        self.test_label.setStyleSheet("color: red; font-weight: bold; font-size: 14px; margin-right: 15px;")
        self.test_label.setVisible(False) # Default hidden, updated in load_invoices
        header_lay.addWidget(self.test_label)
        
        # Filters (Dates)
        # Restore saved dates or default
        cat_suffix = "Purchase" if self.category == InvoiceCategory.PURCHASE else "Sales"
        
        d_from_str = self.settings.value(f"dateFrom{cat_suffix}")
        # d_to_str ignored - User request: Always set "To" date to Current Date on startup
        
        d_from_val = QDate.currentDate().addMonths(-1)
        d_to_val = QDate.currentDate()
        
        if d_from_str: d_from_val = QDate.fromString(d_from_str, Qt.ISODate)
        # if d_to_str: ... -> Disabled to ensure fresh date on restart

        header_lay.addWidget(QLabel("Od:"))
        self.date_from = QDateEdit(d_from_val)
        self.date_from.setCalendarPopup(True)
        self.date_from.setFixedWidth(110)
        self.date_from.dateChanged.connect(self.save_filters_and_reload)
        header_lay.addWidget(self.date_from)
        
        header_lay.addWidget(QLabel("Do:"))
        self.date_to = QDateEdit(d_to_val)
        self.date_to.setCalendarPopup(True)
        self.date_to.setFixedWidth(110)
        self.date_to.dateChanged.connect(self.save_filters_and_reload)
        header_lay.addWidget(self.date_to)
        
        # Buttons
        if self.category == InvoiceCategory.SALES:
            self.add_btn = QPushButton("Dodaj Fakturę")
            self.add_btn.clicked.connect(self.add_invoice)
            header_lay.addWidget(self.add_btn)
        elif self.category == InvoiceCategory.PURCHASE:
             self.add_btn = QPushButton("Dodaj Zakup")
             self.add_btn.clicked.connect(self.add_invoice)
             header_lay.addWidget(self.add_btn)
             
             self.sync_ksef_btn = QPushButton("Pobierz z KSeF")
             self.sync_ksef_btn.clicked.connect(self.sync_from_ksef)
             header_lay.addWidget(self.sync_ksef_btn)

        self.refresh_btn = QPushButton("Odśwież")
        self.refresh_btn.clicked.connect(self.load_invoices)
        header_lay.addWidget(self.refresh_btn)

        layout.addLayout(header_lay)


        # Table
        self.table = QTableView()
        self.model = InvoiceTableModel()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # Double Click Action -> Preview/KSeF Info
        self.table.doubleClicked.connect(self.on_table_double_click)
        
        # Context Menu
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.open_context_menu)

        layout.addWidget(self.table)

    def save_filters_and_reload(self):
        cat_suffix = "Purchase" if self.category == InvoiceCategory.PURCHASE else "Sales"
        if self.settings:
             self.settings.setValue(f"dateFrom{cat_suffix}", self.date_from.date().toString(Qt.ISODate))
             self.settings.setValue(f"dateTo{cat_suffix}", self.date_to.date().toString(Qt.ISODate))
        self.load_invoices()

    def load_invoices(self):
        db = next(get_db())
        try:
            # Update Environment Label state
            config = db.query(CompanyConfig).first()
            if config and config.ksef_environment == "test":
                self.test_label.setVisible(True)
            else:
                self.test_label.setVisible(False)

            d_from = self.date_from.date().toPython()
            d_to = self.date_to.date().toPython()
            
            # Ensure d_to covers the whole day (up to 23:59:59)
            d_to_full = datetime.datetime.combine(d_to, datetime.time.max)
            d_from_full = datetime.datetime.combine(d_from, datetime.time.min)
            
            query = db.query(Invoice).filter(
                Invoice.category == self.category,
                Invoice.date_issue >= d_from_full,
                Invoice.date_issue <= d_to_full
            )
            
            # Exclude Settlements (Podatek, Inne) from Invoice List
            # These are handled in SettlementsView/Rozrachunki
            if self.category == InvoiceCategory.PURCHASE:
                 query = query.filter(
                      Invoice.type != InvoiceType.PODATEK,
                      Invoice.type != InvoiceType.INNE
                 )
            
            invoices = query.options(joinedload(Invoice.contractor), joinedload(Invoice.payment_breakdowns))\
            .order_by(Invoice.id.desc()).all()
            self.model.update_data(invoices)
        except Exception as e:
             print(f"Błąd ładowania faktur: {e}")
        finally:
            db.close()

    def open_context_menu(self, position):
        index = self.table.indexAt(position)
        if not index.isValid():
            return
        
        row = index.row()
        invoice = self.model.get_invoice(row)
        
        menu = QMenu()
        
        # Edit
        # For SALES, allowing Edit is standard. For Purchase, maybe only Note editing?
        edit_action = QAction("Edytuj", self)
        edit_action.triggered.connect(lambda: self.edit_invoice(invoice))
        menu.addAction(edit_action)
        
        # KSeF Info / Preview (Prioritized)
        ksef_info = QAction("Podgląd Faktury / KSeF", self)
        ksef_info.triggered.connect(lambda: self.show_ksef_info(invoice))
        menu.addAction(ksef_info)

        # Delete
        delete_action = QAction("Usuń", self)
        delete_action.triggered.connect(lambda: self.delete_invoice(invoice))
        menu.addAction(delete_action)
        
        menu.addSeparator()

        # Sales/XML
        if self.category == InvoiceCategory.SALES:
            # Correction Action
            correction_action = QAction("Koryguj", self)
            correction_action.triggered.connect(lambda: self.correct_invoice(invoice))
            menu.addAction(correction_action)

            # Duplicate Action
            duplicate_action = QAction("Duplikuj (jako nowy)", self)
            duplicate_action.triggered.connect(lambda: self.duplicate_invoice(invoice))
            menu.addAction(duplicate_action)
            menu.addSeparator()

            export_xml_action = QAction("Eksport XML", self)
            export_xml_action.triggered.connect(lambda: self.export_xml(invoice))
            menu.addAction(export_xml_action)
            
            send_ksef = QAction("Wyślij do KSeF", self)
            if invoice.is_sent_to_ksef:
                 send_ksef.setText("Wyślij ponownie do KSeF")
            
            # Check permissions
            can_send = True
            if self.current_user and not getattr(self.current_user, 'perm_send_ksef', False):
                can_send = False
                send_ksef.setText("Wyślij do KSeF (Brak uprawnień)")
                send_ksef.setEnabled(False)
            
            send_ksef.triggered.connect(lambda: self.send_to_ksef(invoice))
            menu.addAction(send_ksef)
            
            get_upo_action = QAction("Pobierz UPO", self)
            if invoice.upo_datum:
                 get_upo_action.setText("Pokaż UPO")
            
            if not invoice.ksef_number:
                get_upo_action.setEnabled(False)
                
            get_upo_action.triggered.connect(lambda: self.get_upo(invoice))
            menu.addAction(get_upo_action)
        
        menu.exec(self.table.viewport().mapToGlobal(position))
        
    def on_table_double_click(self, index):
        if not index.isValid(): return
        invoice = self.model.get_invoice(index.row())
        if invoice:
            self.show_ksef_info(invoice)

    def add_invoice(self):
        from gui_qt.invoice_dialog import InvoiceDialog
        dlg = InvoiceDialog(self.category, parent=self)
        if dlg.exec():
            self.load_invoices()

    def duplicate_invoice(self, invoice):
        from gui_qt.invoice_dialog import InvoiceDialog
        # Pass duplicated_invoice_id, but NO invoice_id (so it treats as new)
        dlg = InvoiceDialog(self.category, duplicated_invoice_id=invoice.id, parent=self)
        if dlg.exec():
            # Dialog handles saving new invoice (because invoice_id was None)
            self.load_invoices()

    def correct_invoice(self, invoice):
        from gui_qt.invoice_dialog import InvoiceDialog
        # Pass corrected_invoice_id to init correction mode
        dlg = InvoiceDialog(self.category, corrected_invoice_id=invoice.id, parent=self)
        if dlg.exec():
            self.load_invoices()
            
    def edit_invoice(self, invoice):
        from gui_qt.invoice_dialog import InvoiceDialog
        dlg = InvoiceDialog(self.category, invoice_id=invoice.id, parent=self)
        if dlg.exec():
            self.load_invoices()

    def delete_invoice(self, invoice):
        res = QMessageBox.question(self, "Usuń", f"Czy usunąć fakturę {invoice.number}?", QMessageBox.Yes | QMessageBox.No)
        if res == QMessageBox.Yes:
            db = next(get_db())
            try:
                # Check for contractor cleanup later
                contractor_id = invoice.contractor_id

                # Manual cleanup of items to ensure no orphans
                db.query(InvoiceItem).filter(InvoiceItem.invoice_id == invoice.id).delete()
                
                # Use merge to attach instance to this session for deletion
                to_delete = db.merge(invoice)
                db.delete(to_delete)
                db.flush()
                
                # Check if contractor is orphan
                if contractor_id:
                     count = db.query(Invoice).filter(Invoice.contractor_id == contractor_id).count()
                     if count == 0:
                          # Check if it really is orphan or user wants to keep it?
                          # User asked: "usuwając fakturę nie usuwa się kontrahent" -> implying they want it removed.
                          # Let's double check if we can remove it (e.g. no other dependencies)
                          # Assuming Contractor only linked to Invoices here.
                          orphan_ctr = db.query(Contractor).filter(Contractor.id == contractor_id).first()
                          if orphan_ctr:
                               res_ctr = QMessageBox.question(self, "Usuń Kontrahenta", 
                                                    f"Kontrahent '{orphan_ctr.name}' nie ma już żadnych przypisanych faktur. Czy usunąć go z bazy?", 
                                                    QMessageBox.Yes | QMessageBox.No)
                               if res_ctr == QMessageBox.Yes:
                                   db.delete(orphan_ctr)

                db.commit()
                self.load_invoices()
            finally:
                db.close()

    def send_to_ksef(self, invoice_input):
        # 1. Setup session and reload objects
        db = next(get_db())
        try:
            config = db.query(CompanyConfig).first()
            if not config:
                QMessageBox.warning(self, "Błąd", "Brak konfiguracji firmy. Uzupełnij NIP/Token/Certyfikat.")
                return

            # Reload invoice
            invoice = db.query(Invoice).filter(Invoice.id == invoice_input.id).first()
            if not invoice:
                QMessageBox.warning(self, "Błąd", "Nie znaleziono faktury w bazie.")
                return

            # 2. Confirm
            res = QMessageBox.question(self, "Wysyłka KSeF", f"Czy wysłać fakturę {invoice.number} do KSeF?\n(Środowisko: {config.ksef_environment})", 
                                       QMessageBox.Yes | QMessageBox.No)
            if res != QMessageBox.Yes: return
            
            # Preparation: Generate XML in Main Thread (safe for Lazy Load)
            try:
                # Use existing XML if available to ensure Hash consistency
                if invoice.ksef_xml:
                    xml_str = invoice.ksef_xml
                else:
                    xml_str = self.xml_gen.generate_invoice_xml(invoice, config)
                    # Save generated XML to DB to ensure consistency between QR and KSeF
                    invoice.ksef_xml = xml_str
                    db.commit()

                xml_bytes = xml_str.encode('utf-8')
            except Exception as e:
                QMessageBox.critical(self, "Błąd Generowania XML", f"Nie udało się wygenerować XML: {e}")
                return

            # 3. Process in Thread
            # Progress Dialog with "Busy" indicator (0-0 range) -> Animowany pasek
            self.progress_dlg = QProgressDialog("Trwa łączenie z bramką KSeF i wysyłka...", "Anuluj", 0, 0, self)
            self.progress_dlg.setWindowModality(Qt.WindowModal)
            self.progress_dlg.setMinimumDuration(0) # Show immediately
            self.progress_dlg.show()
            
            # Create Thread
            self.ksef_worker = KsefSendWorker(xml_bytes)
            
            # Handle Signals
            self.ksef_worker.finished_signal.connect(lambda resp: self.on_ksef_send_finished(resp, invoice_input.id))
            self.ksef_worker.finished.connect(self.ksef_worker.deleteLater)
            
            self.progress_dlg.canceled.connect(self.ksef_worker.terminate) # Optional: brute force cancel

            # Start
            self.ksef_worker.start()

        finally:
            db.close()

    def on_ksef_send_finished(self, resp, invoice_id):
        # Cleanup Dialog
        if hasattr(self, 'progress_dlg'):
            self.progress_dlg.close()
            
        if resp.get("success"):
            ksef_idx = resp.get("ksef_number")
            ts = resp.get("timestamp")
            upo_url = resp.get("upo_url")
            
            # Update DB (New Session)
            db = next(get_db())
            try:
                inv_db = db.query(Invoice).filter(Invoice.id == invoice_id).first()
                if inv_db:
                    inv_db.ksef_number = ksef_idx
                    inv_db.is_sent_to_ksef = True
                    if upo_url:
                        inv_db.upo_url = upo_url
                    if ts:
                        try:
                            ts_clean = ts.replace("Z", "+00:00")
                            dt_upo = datetime.datetime.fromisoformat(ts_clean)
                            inv_db.upo_datum = dt_upo
                        except Exception as e:
                            print(f"Date parsing error: {e}")
                    db.commit()
            except Exception as e:
                print(f"DB Update error: {e}")
            finally:
                db.close()
            
            self.load_invoices() # Refresh view
            
            is_duplicate = resp.get("is_duplicate", False)
            msg_title = "KSeF - Duplikat" if is_duplicate else "Sukces"
            msg_body = f"Faktura przyjęta jako DUPLIKAT (była już wysłana).\nNr KSeF: {ksef_idx}" if is_duplicate else f"Faktura wysłana pomyślnie!\nNr KSeF: {ksef_idx}"

            # Zapytaj czy otworzyć UPO od razu
            if upo_url:
                res = QMessageBox.question(self, msg_title, f"{msg_body}\n\nCzy chcesz POBRAĆ UPO teraz?", QMessageBox.Yes | QMessageBox.No)
                if res == QMessageBox.Yes:
                     # Trigger get_upo to fetch and save, then show
                     # Reload object first
                     db = next(get_db())
                     inv_new = db.query(Invoice).filter(Invoice.id == invoice_id).first()
                     db.close()
                     self.get_upo(inv_new)
            else:
                if is_duplicate:
                    QMessageBox.warning(self, msg_title, msg_body)
                else:
                    QMessageBox.information(self, msg_title, msg_body)
        else:
            err = resp.get("error", "Nieznany błąd")
            QMessageBox.warning(self, "Błąd wysyłki", f"Odpowiedź KSeF: {err}")


    def get_upo(self, invoice):
        if not invoice.ksef_number:
            QMessageBox.warning(self, "Błąd", "Faktura nie posiada numeru KSeF. Najpierw wyślij fakturę.")
            return

        # If UPO Content exists, just show it
        if hasattr(invoice, 'upo_xml') and invoice.upo_xml:
             self.show_ksef_info(invoice, initial_tab=1)
             return
            
        progress = QProgressDialog("Pobieranie UPO...", "Anuluj", 0, 0, self)
        progress.show()
        QApplication.processEvents()
        
        try:
            db = next(get_db())
            config = db.query(CompanyConfig).first()
            db.close()
            
            client = KsefClient(config)
             # Auth if needed
            try:
                client.authenticate(config.nip)
            except: pass
            
            # Use cached UPO URL if available
            resp = client.get_upo(invoice.ksef_number, upo_url=getattr(invoice, 'upo_url', None))
            # Logic to fetch content if URL provided
            upo_xml_content = None
            if resp.get('upoUrl'):
                try:
                    import requests
                    r = requests.get(resp['upoUrl'])
                    if r.status_code == 200:
                        upo_xml_content = r.text
                except Exception as ex:
                    print(f"Failed to download UPO content: {ex}")

            progress.close()
            
            desc = resp.get("processingDescription", "Brak opisu statusu")
            code = resp.get("processingCode")
            timestamp = resp.get("timestamp")

            if code == 200 and timestamp:
                try:
                    # Parse timestamp (e.g. 2023-10-10T10:00:00.123Z)
                    ts_clean = timestamp.replace("Z", "+00:00")
                    dt_upo = datetime.datetime.fromisoformat(ts_clean)
                    
                    # Update DB
                    db = next(get_db())
                    inv_upd = db.query(Invoice).filter(Invoice.id == invoice.id).first()
                    if inv_upd:
                        inv_upd.upo_datum = dt_upo
                        # Save XML content if fetched
                        if upo_xml_content:
                            inv_upd.upo_xml = upo_xml_content
                            
                        db.commit()
                    db.close()
                    
                    self.load_invoices() # Refresh list
                    
                    # Show KSeF Info directly instead of message box
                    # Reload object to be sure
                    self.show_ksef_info(invoice, initial_tab=1)
                    return
                except Exception as e:
                    print(f"Błąd zapisu daty/UPO: {e}")

            # Update DB if UPO date/number changes?
            # For now just show info
            QMessageBox.information(self, f"Status KSeF ({code})", f"Status: {desc}\nNr Ref: {resp.get('referenceNumber')}")
            
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Błąd", f"Nie udało się pobrać UPO: {e}")

    def sync_from_ksef(self):
        # 1. Check Config & Determine Last Date
        db = next(get_db())
        config = db.query(CompanyConfig).first()
        
        last_inv = db.query(Invoice).filter(
            Invoice.category == self.category,
            Invoice.is_sent_to_ksef == True
        ).order_by(Invoice.date_issue.desc()).first()
        
        db.close()
        
        if not config:
            QMessageBox.warning(self, "Błąd", "Brak konfiguracji firmy!")
            return

        last_date_str = "Brak"
        suggested_start = None
        if last_inv and last_inv.date_issue:
             suggested_start = last_inv.date_issue
             if isinstance(suggested_start, datetime.datetime):
                 last_date_str = suggested_start.strftime("%Y-%m-%d")
             else:
                 last_date_str = str(suggested_start)

        # 2. Ask User for Mode
        dlg = QDialog(self)
        dlg.setWindowTitle("Pobieranie z KSeF")
        dlg.setMinimumWidth(350)
        layout = QVBoxLayout(dlg)
        
        layout.addWidget(QLabel("<b>Wybierz zakres pobierania:</b>"))
        
        rb_filter = QRadioButton(f"Wg filtra dat: {self.date_from.text()} - {self.date_to.text()}")
        rb_filter.setChecked(True)
        layout.addWidget(rb_filter)
        
        rb_latest = QRadioButton(f"Kontynuuj od ostatniej faktury ({last_date_str})")
        if not suggested_start:
             rb_latest.setEnabled(False)
             rb_latest.setText("Kontynuuj od ostatniej faktury (Brak danych)")
        layout.addWidget(rb_latest)
        
        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        
        if dlg.exec() != QDialog.Accepted:
             return
             
        # Determine actual dates
        if rb_latest.isChecked() and suggested_start:
             start = last_date_str
             # End date usually 'now', or maybe filter's end date? User usually wants 'up to date'
             # Let's use current date to ensure we get everything recent.
             end = datetime.datetime.now().strftime("%Y-%m-%d")
        else:
             start = self.date_from.date().toString("yyyy-MM-dd")
             end = self.date_to.date().toString("yyyy-MM-dd")
            
        # 3. Setup Progress Dialog
        self.progress_dlg = QProgressDialog(f"Pobieranie faktur z KSeF ({start} - {end})...", "Anuluj", 0, 0, self)
        self.progress_dlg.setWindowModality(Qt.WindowModal)
        self.progress_dlg.show()
        
        # 4. Start Worker
        self.worker = KsefSyncWorker(config, self.category, start, end)
        self.worker.progress.connect(lambda msg: self.progress_dlg.setLabelText(msg))
        self.worker.finished_count.connect(self.on_sync_finished)
        self.worker.error.connect(self.on_sync_error)
        
        self.progress_dlg.canceled.connect(self.worker.stop)
        
        self.worker.start()

    def on_sync_finished(self, count):
        self.progress_dlg.close()
        QMessageBox.information(self, "Sukces", f"Zakończono synchronizację.\nPobrano nowych faktur: {count}")
        self.load_invoices()

    def on_sync_error(self, msg):
        self.progress_dlg.close()
        QMessageBox.critical(self, "Błąd KSeF", f"Wystąpił błąd podczas pobierania:\n{msg}")

    def show_ksef_info(self, invoice, initial_tab=0):
        from gui_qt.invoice_preview import InvoicePreviewDialog
        try:
            dlg = InvoicePreviewDialog(invoice.id, parent=self, initial_tab=initial_tab)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "Błąd Podglądu", str(e))
            print(f"Preview error: {e}")

    def export_xml(self, invoice):
        # Native File Dialog - Robust!
        default_name = f"Faktura_{invoice.number.replace('/', '_')}.xml"
        file_path, _ = QFileDialog.getSaveFileName(self, "Zapisz XML", 
                                                 os.path.join(os.path.expanduser("~"), "Downloads", default_name),
                                                 "XML Files (*.xml)")
        
        if not file_path:
            return

        db = next(get_db())
        try:
            # Re-fetch with fresh session
            full_inv = db.query(Invoice).filter(Invoice.id == invoice.id).first()
            if not full_inv: return

            config = db.query(CompanyConfig).first()
            if not config:
                QMessageBox.warning(self, "Błąd", "Brak konfiguracji firmy!")
                return

            xml_content = self.xml_gen.generate_invoice_xml(full_inv, config)
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(xml_content)
            
            QMessageBox.information(self, "Sukces", f"Zapisano plik XML w:\n{file_path}")

        except Exception as e:
            QMessageBox.critical(self, "Błąd Eksportu", str(e))
        finally:
            db.close()
