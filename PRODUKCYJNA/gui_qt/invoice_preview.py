from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTextBrowser, 
                             QMessageBox, QFileDialog, QToolBar, QTabWidget, QWidget, QTableWidget, QTableWidgetItem, QHeaderView,
                             QLabel, QGroupBox, QFormLayout, QSpacerItem, QSizePolicy)
from PySide6.QtGui import QAction, QIcon, QFont, QPageSize, QPageLayout, QPainter, QTextDocument, QAbstractTextDocumentLayout, QImage, QColor
from PySide6.QtPrintSupport import QPrinter, QPrintDialog, QPrintPreviewDialog
from PySide6.QtCore import Qt, QSizeF, QMarginsF, QRectF, QRect, QBuffer, QByteArray, QIODevice, QSettings
from database.engine import get_db
from database.models import Invoice, CompanyConfig, InvoiceItem, InvoiceCategory
from ksef.xml_generator import KsefXmlGenerator
from logic.security import SecurityManager
import xml.etree.ElementTree as ET
from lxml import etree
import os
from string import Template
import qrcode
from io import BytesIO
import base64
import hashlib
import datetime
from cryptography import x509
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa, ec
from cryptography.hazmat.backends import default_backend
from gui_qt.utils import safe_restore_geometry, save_geometry

class InvoicePreviewDialog(QDialog):
    def __init__(self, invoice_id, parent=None, initial_tab=0):
        super().__init__(parent)
        self.invoice_id = invoice_id
        self.setWindowTitle("Podgląd Faktury")
        
        safe_restore_geometry(self, "invoicePreviewGeometry", default_percent_w=0.7, default_percent_h=0.8, min_w=900, min_h=800)

        self.initial_tab_index = initial_tab
        
        self.db = next(get_db())
        self.invoice = self.db.query(Invoice).filter(Invoice.id == self.invoice_id).first()
        self.config = self.db.query(CompanyConfig).first()
        
        self.init_ui()
        self.load_preview()

    def done(self, r):
        save_geometry(self, "invoicePreviewGeometry")
        super().done(r)

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Toolbar
        toolbar = QToolBar()
        layout.addWidget(toolbar)
        
        act_print = QAction("Drukuj", self)
        act_print.triggered.connect(self.print_invoice)
        toolbar.addAction(act_print)
        
        act_pdf = QAction("Eksportuj PDF", self)
        act_pdf.triggered.connect(self.export_pdf)
        toolbar.addAction(act_pdf)
        
        act_xml = QAction("Zapisz XML", self)
        act_xml.triggered.connect(self.export_xml)
        toolbar.addAction(act_xml)
        
        toolbar.addSeparator()
        
        act_close = QAction("Zamknij", self)
        act_close.triggered.connect(self.accept)
        toolbar.addAction(act_close)

        # Tabs
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # Tab 1: Wizualizacja
        self.tab_preview = QWidget()
        lay_prev = QVBoxLayout(self.tab_preview)
        lay_prev.setContentsMargins(0,0,0,0)
        self.preview = QTextBrowser()
        lay_prev.addWidget(self.preview)
        self.tabs.addTab(self.tab_preview, "Wizualizacja Faktury")
        
        # Tab 2: KSeF Details
        self.tab_ksef = QWidget()
        self.init_ksef_tab()
        self.tabs.addTab(self.tab_ksef, "Szczegóły KSeF / UPO")

        # Tab 3: Podgląd XML
        self.tab_xml = QWidget()
        lay_xml = QVBoxLayout(self.tab_xml)
        lay_xml.setContentsMargins(0,0,0,0)
        self.xml_preview = QTextBrowser()
        # Monospace font
        font = self.xml_preview.font() 
        font.setFamily("Monospace")
        self.xml_preview.setFont(font)
        lay_xml.addWidget(self.xml_preview)
        self.tabs.addTab(self.tab_xml, "Podgląd XML (Faktura)")

        # Set initial tab
        self.tabs.setCurrentIndex(self.initial_tab_index)

    def init_ksef_tab(self):
        layout = QVBoxLayout(self.tab_ksef)
        
        # 1. Header Status
        self.lbl_ksef_status = QLabel("Status KSeF: Nieznany")
        font_status = QFont()
        font_status.setPointSize(16)
        font_status.setBold(True)
        self.lbl_ksef_status.setFont(font_status)
        self.lbl_ksef_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_ksef_status)
        
        # 2. Key Info Group
        gb_info = QGroupBox("Najważniejsze Informacje (z UPO)")
        form_layout = QFormLayout(gb_info)
        
        self.lbl_nip_seller = QLabel("-")
        form_layout.addRow("NIP Sprzedawcy:", self.lbl_nip_seller)
        
        self.lbl_ksef_num_doc = QLabel("-")
        self.lbl_ksef_num_doc.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form_layout.addRow("Numer KSeF Dokumentu:", self.lbl_ksef_num_doc)
        
        self.lbl_inv_num_upo = QLabel("-")
        form_layout.addRow("Numer Faktury (UPO):", self.lbl_inv_num_upo)
        
        self.lbl_date_issue_upo = QLabel("-")
        form_layout.addRow("Data Wystawienia (UPO):", self.lbl_date_issue_upo)
        
        self.lbl_date_sent = QLabel("-")
        form_layout.addRow("Data Przesłania:", self.lbl_date_sent)
        
        self.lbl_date_assigned = QLabel("-")
        form_layout.addRow("Data Nadania Nr KSeF:", self.lbl_date_assigned)
        
        self.lbl_doc_hash = QLabel("-")
        self.lbl_doc_hash.setWordWrap(True)
        form_layout.addRow("Skrót dokumentu:", self.lbl_doc_hash)
        
        self.lbl_mode = QLabel("-")
        form_layout.addRow("Tryb wysyłki:", self.lbl_mode)
        
        self.lbl_entity_receiving = QLabel("-")
        self.lbl_entity_receiving.setWordWrap(True)
        form_layout.addRow("Podmiot Przyjmujący:", self.lbl_entity_receiving)
        
        self.lbl_ref_num = QLabel("-") # Actually Session ID in KSeF terms usually
        self.lbl_ref_num.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form_layout.addRow("Numer Referencyjny Sesji:", self.lbl_ref_num)

        layout.addWidget(gb_info)
        
        # Actions
        btn_layout = QHBoxLayout()
        self.btn_save_upo = QPushButton("Zapisz plik UPO (XML)")
        self.btn_save_upo.setIcon(QIcon.fromTheme("document-save"))
        self.btn_save_upo.clicked.connect(self.save_upo_xml)
        btn_layout.addWidget(self.btn_save_upo)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 3. Raw XML (Expandable)
        layout.addWidget(QLabel("Pełna treść techniczna UPO (XML):"))
        self.upo_preview = QTextBrowser()
        font = self.upo_preview.font() 
        font.setFamily("Monospace")
        self.upo_preview.setFont(font)
        self.upo_preview.setPlaceholderText("Brak treści UPO.")
        self.upo_preview.setLineWrapMode(QTextBrowser.NoWrap) # Better for XML
        # Remove fixed height constraint
        layout.addWidget(self.upo_preview, 1) # Add stretch factor 1 to take remaining space
        
        # Load content
        self.update_ksef_tab_data()

    def update_ksef_tab_data(self):
        inv = self.invoice
        # if inv and inv.date_issue:
        #      self.lbl_date_issue.setText(str(inv.date_issue))
             
        if not inv: return 
        
        is_sent = bool(inv.ksef_number)
        has_upo = hasattr(inv, "upo_xml") and inv.upo_xml
        
        if not is_sent:
            self.lbl_ksef_status.setText("Faktura niewysłana do KSeF")
            self.lbl_ksef_status.setStyleSheet("color: gray;")
            self.btn_save_upo.setEnabled(False)
            return
        
        # Check Date mismatch for Purchase invoices?
        # Actually, for Purchase invoices, we don't have UPO XML usually, but we have KSeF Number.
        if inv.category == InvoiceCategory.PURCHASE:
             self.lbl_ksef_status.setText("POBRANA Z KSEF")
             self.lbl_ksef_status.setStyleSheet("color: #0288D1;") # Blue
             self.btn_save_upo.setEnabled(False) # No UPO for purchase
             self.upo_preview.setPlainText("Brak UPO dla faktur zakupowych (pobranych).")
             # Fill other fields if possible?
             self.lbl_ksef_num_doc.setText(inv.ksef_number)
             self.lbl_inv_num_upo.setText(inv.number)
             if inv.date_issue:
                 self.lbl_date_issue_upo.setText(str(inv.date_issue))
             return

        if has_upo:
            self.lbl_ksef_status.setText("WYSŁANA I POTWIERDZONA (UPO)")
            self.lbl_ksef_status.setStyleSheet("color: green;")
            self.btn_save_upo.setEnabled(True)
            
            # Formatting XML
            try:
                import xml.dom.minidom
                dom = xml.dom.minidom.parseString(inv.upo_xml)
                pretty_xml = dom.toprettyxml(indent="    ")
                self.upo_preview.setPlainText(pretty_xml)
            except Exception:
                self.upo_preview.setPlainText(inv.upo_xml)
            
            # Remove Namespaces for easier parsing
            try:
                # Basic parsing logic
                content = inv.upo_xml
                
                root = ET.fromstring(content)
                ns = {}
                # Extract namespace if present
                if root.tag.startswith('{'):
                     ns_url = root.tag[1:].split('}')[0]
                     ns = {'ns': ns_url}
                     
                def find_text(elem, tag_name):
                    # Try with namespace
                    if ns:
                         # Try simple
                         found = elem.find(f".//ns:{tag_name}", ns)
                         if found is not None: return found.text
                    # Try without namespace for safety (if iter)
                    for e in elem.iter():
                        if e.tag.endswith(tag_name) or e.tag.endswith("}" + tag_name):
                            return e.text
                    return "-"

                # New Fields Requested
                self.lbl_nip_seller.setText(find_text(root, "NipSprzedawcy"))
                self.lbl_ksef_num_doc.setText(find_text(root, "NumerKSeFDokumentu"))
                self.lbl_inv_num_upo.setText(find_text(root, "NumerFaktury"))
                self.lbl_date_issue_upo.setText(find_text(root, "DataWystawieniaFaktury"))
                self.lbl_date_sent.setText(find_text(root, "DataPrzeslaniaDokumentu"))
                self.lbl_date_assigned.setText(find_text(root, "DataNadaniaNumeruKSeF"))
                self.lbl_doc_hash.setText(find_text(root, "SkrotDokumentu"))
                self.lbl_mode.setText(find_text(root, "TrybWysylki"))
                self.lbl_entity_receiving.setText(find_text(root, "NazwaPodmiotuPrzyjmujacego"))
                
                # Session Ref
                ref = find_text(root, "NumerReferencyjnySesji")
                if ref == "-": ref = find_text(root, "NumerReferencyjny") # Fallback
                self.lbl_ref_num.setText(ref)

            except Exception as e:
                print(f"UPO Parse Error: {e}")
                self.lbl_nip_seller.setText("Błąd parsowania")

        else:
            self.lbl_ksef_status.setText("WYSŁANA - OCZEKIWANIE NA UPO")
            self.lbl_ksef_status.setStyleSheet("color: orange;")
            self.btn_save_upo.setEnabled(False)
            self.upo_preview.setPlainText("Brak UPO w bazie. Pobierz UPO z menu faktury aby zobaczyć szczegóły.")
            
    def save_upo_xml(self):
        if not self.invoice.upo_xml:
            QMessageBox.warning(self, "Brak UPO", "Brak treści UPO do zapisania.")
            return
            
        default_name = f"UPO_{self.invoice.number.replace('/', '_')}.xml"
        file_path, _ = QFileDialog.getSaveFileName(self, "Zapisz UPO XML", 
                                                 default_name,
                                                 "XML Files (*.xml)")
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(self.invoice.upo_xml)
                QMessageBox.information(self, "Zapisano", "Plik UPO został zapisany.")
            except Exception as e:
                QMessageBox.critical(self, "Błąd", f"Nie udało się zapisać pliku: {e}")


    def load_preview(self):
        if not self.invoice or not self.config:
            self.preview.setHtml("<h1>Błąd: Brak danych faktury lub konfiguracji firmy.</h1>")
            return
            
        html = self.generate_html()
        self.preview.setHtml(html)
        
        # XML Preview
        try:
             # Prefer stored original XML if available (especially for Purchase or already Sent invoices)
             if self.invoice.ksef_xml:
                 xml_content = self.invoice.ksef_xml
             else:
                 gen = KsefXmlGenerator()
                 xml_content = gen.generate_invoice_xml(self.invoice, self.config)
                 # Cache it for consistency
                 self.invoice.ksef_xml = xml_content
                 self.db.commit()
             
             self.xml_preview.setPlainText(xml_content)
        except Exception as e:
             self.xml_preview.setPlainText(f"Błąd generowania XML: {e}")

    def generate_html(self):
        inv = self.invoice
        cfg = self.config
        ctr = inv.contractor
        
        # Helper for None values
        def s(val): return str(val) if val is not None else ""
        def d(val):
             if val is None: return ""
             if hasattr(val, 'strftime'): return val.strftime("%Y-%m-%d")
             return str(val).split(' ')[0]
             
        def currency(val): return f"{val:.2f} {inv.currency}"

        # --- 1. KSeF Data Extraction ---
        ksef_block = ""
        has_ksef = bool(inv.ksef_number)
        
        if has_ksef:
            ksef_ksef_num = inv.ksef_number
            ksef_ref_num = "-"
            ksef_sent_date = "-"
            ksef_upo_date = "-"
            ksef_entity_receiving = "-"
            ksef_doc_hash = "-"
            
            if hasattr(inv, 'upo_xml') and inv.upo_xml:
                 import re
                 c = inv.upo_xml
                 def get_tag(tag):
                     m = re.search(f"<{tag}>(.*?)</{tag}>", c)
                     if not m: m = re.search(f":{tag}>(.*?)</.*:{tag}>", c)
                     return m.group(1) if m else "-"
                 
                 found_ksef = get_tag("NumerKSeFDokumentu")
                 if found_ksef != "-": ksef_ksef_num = found_ksef
                 
                 found_ref = get_tag("NumerReferencyjnySesji")
                 if found_ref == "-": found_ref = get_tag("NumerReferencyjny")
                 ksef_ref_num = found_ref
                 
                 ksef_sent_date = get_tag("DataPrzeslaniaDokumentu")
                 ksef_upo_date = get_tag("DataNadaniaNumeruKSeF")
                 
                 found_entity = get_tag("NazwaPodmiotuPrzyjmujacego")
                 if found_entity != "-": ksef_entity_receiving = found_entity
                 
                 found_hash = get_tag("SkrotDokumentu")
                 if found_hash != "-": ksef_doc_hash = found_hash
                 
            elif hasattr(inv, 'upo_datum') and inv.upo_datum:
                 ksef_upo_date = str(inv.upo_datum)

            # Layout adjustments for Qt Text Engine compatibility (Tables are required for side-by-side)
            ksef_block = f"""
            <div class='ksef-box'>
                <table width="100%" cellspacing="0" cellpadding="0">
                    <tr>
                        <td colspan="2" class='ksef-title'>POTWIERDZENIE Z REJESTRU KSeF (UPO)</td>
                    </tr>
                    <tr>
                        <td class='ksef-label'>Numer KSeF:</td>
                        <td class='ksef-value'>{ksef_ksef_num}</td>
                    </tr>
                    <tr>
                        <td class='ksef-label'>Identyfikator Sesji:</td>
                        <td class='ksef-value'>{ksef_ref_num}</td>
                    </tr>
                    <tr>
                        <td class='ksef-label'>Data Przesłania:</td>
                        <td class='ksef-value'>{ksef_sent_date}</td>
                    </tr>
                    <tr>
                        <td class='ksef-label'>Data Nadania (UPO):</td>
                        <td class='ksef-value'>{ksef_upo_date}</td>
                    </tr>
                    <tr>
                        <td class='ksef-label'>Podmiot Przyjmujący:</td>
                        <td class='ksef-value'>{ksef_entity_receiving}</td>
                    </tr>
                    <tr>
                        <td class='ksef-label' style='border-bottom:none'>Skrót dokumentu:</td>
                        <td class='ksef-value' style='border-bottom:none'>{ksef_doc_hash}</td> 
                    </tr>
                </table>
            </div>
            """

        # --- 2. Headers (Invoice Info) ---
        # Determining Invoice Type Label
        inv_type_label = "FAKTURA VAT"
        
        # Safe Enum access
        itype = getattr(inv, 'type', None)
        itype_name = itype.name if hasattr(itype, 'name') else str(itype)
        
        correction_info_rows = ""

        if itype_name == "KOREKTA": 
             inv_type_label = "FAKTURA KORYGUJĄCA"
             
             reason = getattr(inv, 'correction_reason', '-')
             correction_info_rows += f"<tr><td class='invoice-info-label' style='color:#B00;'>Przyczyna:</td><td style='color:#B00;'>{s(reason)}</td></tr>"
             
             # Show what is corrected
             res_ksef = getattr(inv, 'related_ksef_number', None)
             res_inv = getattr(inv, 'related_invoice_number', None)
             
             if res_ksef:
                  correction_info_rows += f"<tr><td class='invoice-info-label'>Do faktury KSeF:</td><td style='font-size:8pt;'>{res_ksef}</td></tr>"
             elif res_inv:
                  correction_info_rows += f"<tr><td class='invoice-info-label'>Do faktury:</td><td>{res_inv}</td></tr>"


        # Helper for extracting simple tags from stored XML (for fields not in DB)
        def get_xml_tag(tag, content):
            if not content: return None
            import re
            m = re.search(f"{tag}>(.*?)</.*{tag}>", content)
            if not m: m = re.search(f"{tag}>(.*?)</{tag}>", content)
            return m.group(1) if m else None

        # Try to find SystemInfo or Place if missing in DB but present in XML
        xml_src = getattr(inv, 'ksef_xml', None)
        sys_info = get_xml_tag("SystemInfo", xml_src)
        
        # Fallback for Place of Issue if DB is empty (e.g. old import)
        if not inv.place_of_issue and xml_src:
             place_xml = get_xml_tag("P_1M", xml_src)
             if place_xml: inv.place_of_issue = place_xml

        if itype_name == "ZALICZKA": inv_type_label = "FAKTURA ZALICZKOWA"
        if getattr(inv, 'is_proforma', False): inv_type_label = "PROFORMA"

        invoice_dates_table = f"""
        <tr><td class='invoice-info-label'>Data wystawienia:</td><td>{d(inv.date_issue)}</td></tr>
        <tr><td class='invoice-info-label'>Data sprzedaży:</td><td>{d(inv.date_sale)}</td></tr>
        <tr><td class='invoice-info-label'>Miejsce wystawienia:</td><td>{s(inv.place_of_issue)}</td></tr>
        {f"<tr><td class='invoice-info-label'>System:</td><td style='font-size:8pt; color:gray;'>{sys_info}</td></tr>" if sys_info else ""}
        {correction_info_rows}
        """
        
        # --- 3. Parties (Seller / Buyer) ---
        # Prepare registers line
        reg_list = []
        if getattr(cfg, 'bdo', None): reg_list.append(f"BDO: {cfg.bdo}")
        if getattr(cfg, 'krs', None): reg_list.append(f"KRS: {cfg.krs}")
        if getattr(cfg, 'regon', None): reg_list.append(f"REGON: {cfg.regon}")
        
        regs_line = " | ".join(reg_list)
        if regs_line: regs_line = "<br>" + regs_line

        seller_content = f"""
        <b>{cfg.company_name}</b><br>
        {cfg.address}<br>
        {cfg.postal_code} {cfg.city}<br>
        <br>
        NIP: <b>{cfg.nip}</b>{regs_line}
        """
        
        # Logic to use Snapshot if available
        buyer_name = "Brak danych"
        buyer_address = ""
        buyer_postal = ""
        buyer_city = ""
        buyer_nip = "Brak"

        # Try snapshot first
        used_snapshot = False
        if inv.buyer_snapshot:
            try:
                import json
                snap = inv.buyer_snapshot
                if isinstance(snap, str): snap = json.loads(snap)
                if snap:
                    buyer_name = snap.get('name') or "Brak danych"
                    buyer_address = snap.get('address') or ""
                    buyer_postal = snap.get('postal') or ""
                    buyer_city = snap.get('city') or ""
                    buyer_nip = snap.get('nip') or "Brak"
                    used_snapshot = True
            except Exception as e:
                print(f"Error reading buyer snapshot: {e}")

        # Fallback to current relation if no snapshot used
        if not used_snapshot:
             if ctr:
                 buyer_name = ctr.name or "Brak danych"
                 buyer_address = ctr.address or ""
                 buyer_postal = ctr.postal_code or ""
                 buyer_city = ctr.city or ""
                 buyer_nip = ctr.nip or "Brak"
             else:
                 buyer_name = "Brak danych"
                 buyer_address = ""
                 buyer_postal = ""
                 buyer_city = ""
                 buyer_nip = "Brak"

        buyer_content = f"""
        <b>{buyer_name}</b><br>
        {buyer_address}<br>
        {buyer_postal} {buyer_city}<br>
        <br>
        NIP: <b>{buyer_nip}</b>
        """

        # --- 4. Items ---
        items_html_rows = ""
        
        for i, item in enumerate(inv.items, 1):
            net_val = item.quantity * item.net_price
            gross_val = item.gross_value
            vat_val = gross_val - net_val
            
            vat_display = f"{int(item.vat_rate*100)}%"
            if inv.is_exempt or (hasattr(item, 'pkwiu') and item.pkwiu in ["ZW", "zw"]):
                vat_display = "ZW"
            
            # Check for extra description
            desc_key = getattr(item, 'description_key', '')
            desc_val = getattr(item, 'description_value', '')
            has_desc = bool(desc_key or desc_val or (item.pkwiu and item.pkwiu != "ZW"))
            
            row_class = "main-row" if has_desc else ""
            border_style = "border-bottom: none;" if has_desc else ""
            
            items_html_rows += f"""
            <tr class='{row_class}'>
                <td class='center-col' style='{border_style}'>{i}</td>
                <td style='{border_style}'><b>{item.product_name}</b></td>
                <td class='center-col' style='{border_style}'>{item.quantity}</td>
                <td class='center-col' style='{border_style}'>{item.unit}</td>
                <td class='num-col' style='{border_style}'>{item.net_price:.2f}</td>
                <td class='num-col' style='{border_style}'>{net_val:.2f}</td>
                <td class='center-col' style='{border_style}'>{vat_display}</td>
                <td class='num-col' style='{border_style}'>{vat_val:.2f}</td>
                <td class='num-col' style='{border_style}'>{gross_val:.2f}</td>
            </tr>
            """
            
            if has_desc:
                desc_parts = []
                if item.pkwiu and item.pkwiu != "ZW": desc_parts.append(f"PKWiU/CN: {item.pkwiu}")
                if desc_key or desc_val: desc_parts.append(f"{desc_key}: {desc_val}")
                full_desc = " | ".join(desc_parts)
                
                items_html_rows += f"""
                <tr class='desc-row'>
                    <td></td>
                    <td colspan='8'>{full_desc}</td>
                </tr>
                """

        # items_table removed - logic moved to template
        items_rows = items_html_rows

        # --- 5. VAT Summary ---
        vat_summary = {}
        total_net = 0
        total_vat = 0
        total_gross = 0
        
        for item in inv.items:
            # Recalculate to be sure
            n = item.quantity * item.net_price
            g = item.gross_value
            v = g - n
            
            total_net += n
            total_vat += v
            total_gross += g
            
            rate_label = f"{int(item.vat_rate*100)}%"
            if inv.is_exempt or (hasattr(item, 'pkwiu') and item.pkwiu in ["ZW", "zw"]):
                 rate_label = "ZW"
            
            if rate_label not in vat_summary:
                vat_summary[rate_label] = [0.0, 0.0, 0.0] # Net, Vat, Gross
            
            vat_summary[rate_label][0] += n
            vat_summary[rate_label][1] += v
            vat_summary[rate_label][2] += g

        vat_rows = ""
        for rate, vals in vat_summary.items():
            vat_rows += f"""
            <tr>
                <td class='label'>{rate}</td>
                <td>{currency(vals[0])}</td>
                <td>{currency(vals[1])}</td>
                <td>{currency(vals[2])}</td>
            </tr>
            """
            
        vat_rows += f"""
        <tr style='font-weight: bold; border-top: 2px solid #000;'>
            <td class='label'>RAZEM</td>
            <td>{currency(total_net)}</td>
            <td>{currency(total_vat)}</td>
            <td>{currency(total_gross)}</td>
        </tr>
        """
        
        total_gross_display = currency(total_gross)

        # --- 6. Payment & Notes ---
        
        # Payment Breakdowns Logic
        payment_method_str = inv.payment_method or "Przelew"
        payment_details_html = ""
        
        is_mixed = "miesza" in payment_method_str.lower() or "wiele" in payment_method_str.lower() or (hasattr(inv, "payment_breakdowns") and len(inv.payment_breakdowns) > 1)
        
        if is_mixed and hasattr(inv, "payment_breakdowns") and inv.payment_breakdowns:
            payment_details_html += "<div style='margin-top:5px; font-size:9pt;'><b>Szczegóły płatności:</b><ul style='margin-top:2px; padding-left:20px; margin-bottom: 0;'>"
            for pb in inv.payment_breakdowns:
                m_lower = pb.payment_method.lower()
                # Simple heuristic for status
                is_paid_method = any(x in m_lower for x in ['gotówka', 'karta', 'cash', 'blik'])
                
                status_str = "Zapłacono" if is_paid_method else "Do zapłaty"
                # If paid, use sale/paid date. If not, use deadline.
                relevant_date = inv.paid_date or inv.date_issue if is_paid_method else inv.payment_deadline
                date_str = d(relevant_date)
                
                payment_details_html += f"<li>{currency(pb.amount)} - {pb.payment_method} ({status_str}: {date_str})</li>"
            payment_details_html += "</ul></div>"

        # --- QR Code Logic (KSeF Verification) ---
        qr_html = ""
        try:
             # Check for PODATEK exception
             itype_n = getattr(inv, 'type', None)
             itype_name_str = itype_n.name if hasattr(itype_n, 'name') else str(itype_n)
             is_tax_doc = (itype_name_str == "PODATEK") or (inv.number and inv.number.startswith("Podatek")) or (itype_name_str == "INNE")
             
             if not is_tax_doc:
                 ksef_number = getattr(inv, 'ksef_number', None)
                 is_offline = False
                 ksef_link = None
                 hash_b64 = None

                 # Get XML content first
                 xml_content = getattr(inv, 'ksef_xml', None)
                 if not xml_content:
                     try:
                         gen = KsefXmlGenerator()
                         xml_content = gen.generate_invoice_xml(inv, cfg)
                         # FIX: Persist the generated XML so subsequent usage (Send) uses the same Content/Hash
                         # This ensures the QR code (based on this XML) matches what is eventually sent to KSeF
                         inv.ksef_xml = xml_content
                         self.db.commit()
                     except Exception as ex:
                         print(f"XML Gen Error: {ex}")

                 # Prepare raw bytes
                 xml_bytes_raw = None
                 if xml_content:
                     if isinstance(xml_content, str):
                        xml_bytes_raw = xml_content.encode('utf-8')
                     else:
                        xml_bytes_raw = xml_content

                 # 1. ONLINE MODE (KSeF Number exists -> Use RAW Hash of sent file)
                 if ksef_number and xml_bytes_raw:
                     try:
                         # No C14N for Online - hash must match what KSeF stored (the raw upload)
                         hasher = hashlib.sha256(xml_bytes_raw)
                         digest = hasher.digest()
                         hash_b64 = base64.urlsafe_b64encode(digest).decode().rstrip('=')
                         
                         nip = (cfg.nip or "").replace("-", "")
                         env = getattr(inv, 'environment', 'test')
                         
                         d_issue = inv.date_issue
                         if not d_issue: d_issue = datetime.datetime.now()
                         if isinstance(d_issue, str):
                             try: d_issue = datetime.datetime.strptime(d_issue, "%Y-%m-%d")
                             except: d_issue = datetime.datetime.now()
                         date_str = d_issue.strftime("%d-%m-%Y")
                         
                         if env == 'prod':
                             base_url = "https://qr.ksef.mf.gov.pl/invoice"
                         else: 
                             base_url = "https://qr-demo.ksef.mf.gov.pl/invoice"
                             
                         ksef_link = f"{base_url}/{nip}/{date_str}/{hash_b64}"
                     except Exception as ex:
                         print(f"Online QR Error: {ex}")

                 # 2. OFFLINE MODE (No KSeF Number -> Use C14N Hash as per FA(3))
                 elif not ksef_link and xml_bytes_raw:
                     try:
                        # Canonicalize for Offline
                        parser = etree.XMLParser(remove_blank_text=True)
                        root = etree.fromstring(xml_bytes_raw, parser)
                        xml_c14n = etree.tostring(root, method="c14n", exclusive=False, with_comments=False)
                        
                        hasher = hashlib.sha256(xml_c14n)
                        digest = hasher.digest()
                        hash_b64 = base64.urlsafe_b64encode(digest).decode().rstrip('=')
                        
                        is_offline = True
                        nip = (cfg.nip or "").replace("-", "")
                        env = getattr(inv, 'environment', 'test')
                        
                        d_issue = inv.date_issue
                        if not d_issue: d_issue = datetime.datetime.now()
                        if isinstance(d_issue, str):
                            try: d_issue = datetime.datetime.strptime(d_issue, "%Y-%m-%d")
                            except: d_issue = datetime.datetime.now()
                        date_str = d_issue.strftime("%d-%m-%Y")

                        if env == 'prod':
                             domain = "qr.ksef.mf.gov.pl"
                        else:
                             domain = "qr-demo.ksef.mf.gov.pl"
                        
                        base_url = f"https://{domain}/invoice"
                        
                        ksef_link = f"{base_url}/{nip}/{date_str}/{hash_b64}"
                     except Exception as ex:
                        print(f"Offline QR gen failed: {ex}")
                 
                 # 3. Legacy / Fallback to stored link
                 if not ksef_link:
                     ksef_link = getattr(inv, 'verification_link', None)
                     if not ksef_link:
                         candidate_url = getattr(inv, 'upo_url', "")
                         if candidate_url and "/web/verify/" in candidate_url:
                             ksef_link = candidate_url

                 qr_html = ""
                 if ksef_link:
                     def make_qr_img(link, label):
                         # Generate QR Image
                         qr = qrcode.QRCode(box_size=4, border=1) # Smaller box for potential dual display
                         qr.add_data(link)
                         qr.make(fit=True)
                         pil_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
                         
                         buf = BytesIO()
                         pil_img.save(buf, format="PNG")
                         qimg = QImage.fromData(buf.getvalue())
                         
                         # Overlay Text
                         painter = QPainter(qimg)
                         painter.setRenderHint(QPainter.Antialiasing)
                         
                         font = QFont("Arial", 10, QFont.Bold) # Adjusted for size
                         painter.setFont(font)
                         
                         text = "KSeF"
                         fm = painter.fontMetrics()
                         text_w = fm.horizontalAdvance(text)
                         text_h = fm.height()
                         
                         rect = qimg.rect()
                         center_x = rect.width() / 2
                         center_y = rect.height() / 2
                         
                         bg_rect = QRect(int(center_x - text_w/2 - 2), int(center_y - text_h/2 - 2), 
                                         int(text_w + 4), int(text_h + 4))
                         painter.fillRect(bg_rect, QColor("white"))
                         painter.setPen(QColor("black")) 
                         painter.drawRect(bg_rect)
                         
                         painter.setPen(QColor("#D32F2F")) 
                         painter.drawText(rect, Qt.AlignCenter, text)
                         painter.end()
                         
                         # Save modified
                         ba = QByteArray()
                         buff = QBuffer(ba)
                         buff.open(QIODevice.WriteOnly)
                         qimg.save(buff, "PNG")
                         return base64.b64encode(ba.data()).decode("utf-8")

                     # PRIMARY QR (Code I)
                     info_text_1 = "OFFLINE" if is_offline else (ksef_number if ksef_number else "KSeF")
                     img_str_1 = make_qr_img(ksef_link, "KSeF")
                     
                     qr_html = f"""
                     <table cellspacing='0' cellpadding='0'><tr>
                         <td style='vertical-align: top; padding-right: 50px;'>
                             <div style='text-align: center;'>
                                 <img src='data:image/png;base64,{img_str_1}' width='150' height='150' />
                                 <div style='font-size: 7pt; font-weight: bold; width: 150px; word-wrap: break-word;'>{info_text_1}</div>
                             </div>
                         </td>
                     """
                     
                     # SECONDARY QR (Code II - Certificate) - Only Offline and if keys present
                     # Select Credentials based on Environment (Prefer Signing Cert if available)
                     env = getattr(inv, 'environment', 'test')
                     
                     cert_content = None
                     key_content = None
                     pass_enc = None
                     
                     if env == 'prod':
                         if getattr(cfg, 'ksef_signing_cert_content', None) and getattr(cfg, 'ksef_signing_private_key_content', None):
                             cert_content = cfg.ksef_signing_cert_content
                             key_content = cfg.ksef_signing_private_key_content
                             pass_enc = getattr(cfg, 'ksef_signing_private_key_pass', None)
                         else:
                             cert_content = cfg.ksef_cert_content
                             key_content = cfg.ksef_private_key_content
                             pass_enc = cfg.ksef_private_key_pass
                     else:
                         if getattr(cfg, 'ksef_signing_cert_content_test', None) and getattr(cfg, 'ksef_signing_private_key_content_test', None):
                             cert_content = getattr(cfg, 'ksef_signing_cert_content_test', None)
                             key_content = getattr(cfg, 'ksef_signing_private_key_content_test', None)
                             pass_enc = getattr(cfg, 'ksef_signing_private_key_pass_test', None)
                         else:
                             cert_content = getattr(cfg, 'ksef_cert_content_test', None)
                             key_content = getattr(cfg, 'ksef_private_key_content_test', None)
                             pass_enc = getattr(cfg, 'ksef_private_key_pass_test', None)

                     if is_offline and hash_b64 and cert_content and key_content:
                         try:
                             # Load Cert
                             cert = x509.load_pem_x509_certificate(cert_content, default_backend())
                             serial_dec = cert.serial_number
                             serial_hex = f"{serial_dec:X}"
                             # Ensure even length hex (KSeF requirement for byte-aligned serials)
                             if len(serial_hex) % 2 != 0:
                                 serial_hex = "0" + serial_hex
                             
                             # Load Private Key (Decrypt password first)
                             pass_bytes = None
                             if pass_enc:
                                 try:
                                     pass_plain = SecurityManager.decrypt(pass_enc)
                                     if pass_plain:
                                         pass_bytes = pass_plain.encode('utf-8')
                                 except Exception as e_dec:
                                     print(f"Password Decryption Fail: {e_dec}")
                                     # Attempt raw use if decrypt fails (backward compat?)
                                     pass_bytes = pass_enc.encode('utf-8')

                             priv_key = serialization.load_pem_private_key(
                                 key_content,
                                 password=pass_bytes,
                                 backend=default_backend()
                             )
                             
                             env = getattr(inv, 'environment', 'test')
                             domain = "qr.ksef.mf.gov.pl" if env == 'prod' else "qr-demo.ksef.mf.gov.pl"
                             
                             # Context (Assume Nip/Self)
                             nip_ctx = (cfg.nip or "").replace("-", "")
                             
                             # URL Construction
                             # {domain}/certificate/Nip/{ctx}/{nip_seller}/{serial}/{hash}
                             url_path_to_sign = f"{domain}/certificate/Nip/{nip_ctx}/{nip_ctx}/{serial_hex}/{hash_b64}"
                             
                             # Sign (RSA-PSS or ECDSA)
                             # Assuming RSA based on typical KSeF usage. 
                             # If key is EC, use EC.
                             if isinstance(priv_key, rsa.RSAPrivateKey):
                                 signature = priv_key.sign(
                                     url_path_to_sign.encode('utf-8'),
                                     padding.PSS(
                                         mgf=padding.MGF1(hashes.SHA256()),
                                         salt_length=32
                                     ),
                                     hashes.SHA256()
                                 )
                             elif isinstance(priv_key, ec.EllipticCurvePrivateKey):
                                 signature = priv_key.sign(
                                     url_path_to_sign.encode('utf-8'),
                                     ec.ECDSA(hashes.SHA256())
                                 )
                             else:
                                 raise Exception("Unsupported Key Type")

                             sig_b64 = base64.urlsafe_b64encode(signature).decode().rstrip('=')
                             full_cert_link = f"https://{url_path_to_sign}/{sig_b64}"
                             
                             img_str_2 = make_qr_img(full_cert_link, "CERTYFIKAT")
                             
                             qr_html += f"""
                             <td style='vertical-align: top;'>
                                 <div style='text-align: center;'>
                                     <img src='data:image/png;base64,{img_str_2}' width='150' height='150' />
                                     <div style='font-size: 7pt; font-weight: bold; width: 150px;'>CERTYFIKAT</div>
                                 </div>
                             </td>
                             """
                         except Exception as ex_cert:
                             print(f"Cert QR Skip: {ex_cert}")
                             # qr_html += f"<div>Error: {ex_cert}</div>"

                 # Close Table
                 qr_html += "</tr></table>"
                 
                 # Wrap in margin container
                 qr_html = f"<div style='margin-top: 5px;'>{qr_html}</div>"

        except Exception as e:
             print(f"QR Gen Error: {e}")
             qr_html = f"<!-- QR Error: {e} -->"


        # --- Method Label (under invoice number) ---
        labels = []
        if getattr(inv, 'is_cash_accounting', False):
            labels.append("METODA KASOWA")
        
        # User request: MPP label
        if getattr(inv, 'is_split_payment', False):
            labels.append("mechanizm podzielonej płatności")
            
        method_label = "<br>".join(labels)

        payment_block = f"""
        <div class='payment-section'>
            <table style='width: 100%'>
                <tr>
                    <td style='width: 50%; vertical-align: top;'>
                        <b>Sposób płatności:</b> {payment_method_str}<br>
                        <b>Termin płatności:</b> {d(inv.payment_deadline)}<br>
                        <b>Konto bankowe:</b> {inv.bank_account_number or cfg.bank_account or "-"}<br>
                        {f"<b>Bank:</b> {cfg.bank_name}" if cfg.bank_name else ""}
                        {f"<br>SWIFT: {cfg.swift_code}" if cfg.swift_code else ""}
                        {payment_details_html}
                        {qr_html}
                    </td>
                    <td style='width: 50%; vertical-align: top; text-align: right;'>
                        {f"<b>Uwagi:</b><br>{inv.notes}" if inv.notes else ""}
                        <br>
                        { "<div style='color:#000; border: 2px solid #000; display:inline-block; padding:2px 5px; margin-top:5px; font-weight:bold;'>ZAPŁACONO</div>" if inv.is_paid else ""}
                    </td>
                </tr>
            </table>
        </div>
        """
        
        # --- 7. Footer ---
        footer_parts = []
        
        court = getattr(cfg, 'court_info', '')
        krs = getattr(cfg, 'krs', '')
        if court or krs:
            # Handle "Podmiot zarejestrowany w..." logic
            # User sample: "Podmiot zarejestrowany w pod numerem 0002038465" suggests they might miss court name
            # If court is present: "Podmiot zarejestrowany w Sądzie X pod numerem 123"
            # If only KRS: "Podmiot zarejestrowany w KRS pod numerem 123"
            c_text = court if court else "KRS"
            # If krs is empty, we probably shouldn't show "pod numerem -"
            k_text = krs if krs else "-"
            footer_parts.append(f"Podmiot zarejestrowany w {c_text} pod numerem {k_text}.")

        # Line 2: NIP | REGON | Kapitał
        line2_parts = []
        if cfg.nip: line2_parts.append(f"NIP: {cfg.nip}")
        if getattr(cfg, 'regon', None): line2_parts.append(f"REGON: {cfg.regon}")
        if getattr(cfg, 'share_capital', None): line2_parts.append(f"Kapitał zakładowy: {cfg.share_capital}")
        
        if line2_parts:
             footer_parts.append(" | ".join(line2_parts))
        
        footer_content = " ".join(footer_parts)
        
        footer_block = f"""
        <div class='footer'>
            {footer_content}
            <br>
            Dokument wygenerowany elektronicznie w systemie KsefInvoice.
        </div>
        """
        
        # load template first to ensure context is ready or define this block before
        
        # --- 8. Annotations Page ---
        def yn(val): return "1. Tak" if val else "2. Nie"
        
        # Check logic for negations
        is_exempt = getattr(inv, 'is_exempt', False)
        # "Brak dostawy zwolnionej" => True means NO exempt delivery => NOT is_exempt
        # Logic: If item is exempt => rule is False ("2. Nie" - there IS exempt delivery). 
        # If item is NOT exempt => rule is True ("1. Tak" - there is NO exempt delivery).
        rule_no_exempt = not is_exempt 
        
        is_new_transport_intra = getattr(inv, 'is_new_transport_intra', False)
        rule_no_wdt = not is_new_transport_intra
        
        # WE simplified - not in model, user requested '2. Nie'
        rule_we_simplified = False 
        
        # Margin Procedures
        inv_type_name = inv.type.name if hasattr(inv.type, 'name') else str(inv.type)
        is_margin = (inv_type_name == "MARZA")
        rule_no_margin = not is_margin
        
        annotations_page = f"""
        <div class="page-break">
            <h2>Adnotacje</h2>
            
            <table class="annotations-table">
                <tr>
                    <th>Metoda kasowa</th>
                    <th>Samofakturowanie</th>
                    <th>Odwrotne obciążenie</th>
                    <th>Mechanizm podzielonej płatności</th>
                </tr>
                <tr>
                    <td>{yn(getattr(inv, 'is_cash_accounting', False))}</td>
                    <td>{yn(getattr(inv, 'is_self_billing', False))}</td>
                    <td>{yn(getattr(inv, 'is_reverse_charge', False))}</td>
                    <td>{yn(getattr(inv, 'is_split_payment', False))}</td>
                </tr>
            </table>
            
            <div class="annotations-list">
                <ul>
                    <li>Znacznik braku dostawy towarów lub świadczenia usług zwolnionych od podatku na podstawie art. 43 ust. 1, art. 113 ust. 1 i 9 ustawy albo przepisów wydanych na podstawie art. 82 ust. 3 ustawy lub na podstawie innych przepisów - <b>{yn(rule_no_exempt)}</b></li>
                    <li style="margin-top: 5px;">Brak wewnątrzwspólnotowej dostawy nowych środków transportu - <b>{yn(rule_no_wdt)}</b></li>
                    <li style="margin-top: 5px;">VAT: Faktura WE uproszczona na mocy art. 135-138 ustawy o ptu. Podatek z tytułu dokonanej dostawy zostanie rozliczony przez ostatniego w kolejności podatnika podatku od wartości dodanej: <b>{yn(rule_we_simplified)}</b></li>
                    <li style="margin-top: 5px;">Brak wystąpienia procedur marży, o których mowa w art. 119 lub art. 120 ustawy: <b>{yn(rule_no_margin)}</b></li>
                </ul>
            </div>
            
        </div>
        """

        # Load Template
        # Use robustness for path - resolve relative to this file
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        template_path = os.path.join(base_dir, 'templates', 'invoice_template.html')
        
        if not os.path.exists(template_path):
            return f"<h1>Błąd: Nie znaleziono pliku szablonu {template_path}</h1>"
            
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                template_str = f.read()
            
            template = Template(template_str)
            html_content = template.safe_substitute(
                inv_type_label=inv_type_label,
                inv_number=inv.number,
                method_label=method_label,  # Method Label
                invoice_dates_table=invoice_dates_table,
                ksef_block=ksef_block,
                seller_content=seller_content,
                buyer_content=buyer_content,
                items_rows=items_rows,
                vat_rows=vat_rows,
                total_gross_display=total_gross_display,
                payment_block=payment_block,
                footer_block=footer_block,
                annotations_page=annotations_page
            )
            return html_content
            
        except Exception as e:
            return f"<h1>Błąd renderowania szablonu: {e}</h1>"

    def print_content(self, printer):
        """
        Custom print handler to support page numbering 'Strona X z N'.
        """
        doc = QTextDocument()
        doc.setHtml(self.generate_html())
        
        # Align doc layout to printer's paint rect
        layout_rect = printer.pageRect(QPrinter.DevicePixel)
        doc.setPageSize(QSizeF(layout_rect.size()))
        
        painter = QPainter(printer)
        page_count = doc.pageCount()
        
        # If document is empty or 0 pages, handle gracefully
        if page_count == 0:
            painter.end()
            return

        for i in range(page_count):
            if i > 0:
                printer.newPage()
            
            painter.save()
            # Draw content - Translate layout to current page view
            painter.translate(0, -i * layout_rect.height())
            # Clip to ensure clean edges (though usually not strictly required if layout matches)
            painter.setClipRect(QRectF(0, i * layout_rect.height(), layout_rect.width(), layout_rect.height()))
            
            doc.drawContents(painter)
            painter.restore()
            
            # Draw Page Number (If > 1 page)
            if page_count > 1:
                painter.save()
                f = painter.font()
                f.setPointSize(8)
                painter.setFont(f)
                
                # Draw at bottom right of the printable area
                page_info = f"Strona {i+1} z {page_count}"
                # Rect at bottom: x=0, y=height-30, w=width, h=30
                footer_rect = QRectF(0, layout_rect.height() - 30, layout_rect.width(), 30)
                painter.drawText(footer_rect, Qt.AlignRight | Qt.AlignTop, page_info)
                painter.restore()

        painter.end()

    def print_invoice(self):
        printer = QPrinter(QPrinter.ScreenResolution) # Use ScreenResolution to match preview scaling
        dialog = QPrintDialog(printer, self)
        if dialog.exec() == QDialog.Accepted:
            self.print_content(printer)

    def export_pdf(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Zapisz PDF", 
                                                 f"Faktura_{self.invoice.number.replace('/', '_')}.pdf", 
                                                 "PDF Files (*.pdf)")
        if file_path:
            # Use ScreenResolution to match HTML px match
            printer = QPrinter(QPrinter.ScreenResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(file_path)
            # A4 Page Size
            printer.setPageSize(QPageSize(QPageSize.A4))
            # Minimal margins
            printer.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Millimeter)
            
            self.print_content(printer)
            QMessageBox.information(self, "PDF", "Zapisano pomyślnie.")

    def export_xml(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Zapisz XML", 
                                                 f"Faktura_{self.invoice.number.replace('/', '_')}.xml", 
                                                 "XML Files (*.xml)")
        if file_path:
            try:
                if self.invoice.ksef_xml:
                    xml_content = self.invoice.ksef_xml
                else:
                    gen = KsefXmlGenerator()
                    xml_content = gen.generate_invoice_xml(self.invoice, self.config)
                    
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(xml_content)
                QMessageBox.information(self, "XML", "Zapisano pomyślnie.")
            except Exception as e:
                QMessageBox.critical(self, "Błąd", str(e))
    
    def closeEvent(self, event):
        self.db.close()
        super().closeEvent(event)
