from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, 
                             QPushButton, QHeaderView, QLabel, QDialog, QFormLayout, QLineEdit, 
                             QDialogButtonBox, QCheckBox, QMessageBox, QAbstractItemView, QStyle,
                             QDateEdit, QComboBox, QGroupBox, QDoubleSpinBox, QMenu)
from PySide6.QtCore import Qt, QDate, QSettings, QRect
from PySide6.QtGui import QColor, QBrush, QAction, QPixmap, QImage, QPainter, QFont
from database.engine import get_db
from database.models import Invoice, InvoiceCategory, InvoiceType, Contractor
import datetime
import random
import string
import qrcode
import hashlib
import base64
from lxml import etree
from ksef.xml_generator import KsefXmlGenerator
from io import BytesIO

class BankAccountEdit(QLineEdit):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setPlaceholderText("Numer konta (26 cyfr)")
        self.setInputMask("99 9999 9999 9999 9999 9999 9999; ")

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        # Jeśli pole jest puste (same spacje z maski), ustaw kursor na początek
        # filter(str.isdigit, ...) sprawdza czy wpisano jakiekolwiek cyfry
        clean_text = "".join(filter(str.isdigit, self.text()))
        if not clean_text:
            self.setCursorPosition(0)

class NumericItem(QTableWidgetItem):
    def __lt__(self, other):
        try:
            return float(self.text().replace(" ", "")) < float(other.text().replace(" ", ""))
        except ValueError:
            return super().__lt__(other)

class ManualSettlementDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dodaj Rozrachunek Ręcznie")
        self.resize(400, 300)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.cb_type = QComboBox()
        self.cb_type.addItems(["Sprzedaż", "Zakup", "Podatek", "Inne"])
        form.addRow("Typ:", self.cb_type)
        
        self.le_contractor = QLineEdit()
        self.le_contractor.setPlaceholderText("Nazwa kontrahenta / Zobowiązania")
        form.addRow("Podmiot:", self.le_contractor)
        
        self.le_desc = QLineEdit()
        self.le_desc.setPlaceholderText("Opis / Numer dokumentu")
        form.addRow("Opis:", self.le_desc)
        
        self.le_account = BankAccountEdit()
        form.addRow("Numer konta:", self.le_account)
        
        self.de_date = QDateEdit(QDate.currentDate())
        self.de_date.setCalendarPopup(True)
        form.addRow("Termin Płatności:", self.de_date)
        
        self.sb_amount = QDoubleSpinBox()
        self.sb_amount.setRange(0.01, 1000000.0)
        self.sb_amount.setSuffix(" zł")
        form.addRow("Kwota:", self.sb_amount)

        layout.addLayout(form)
        
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_data(self):
        # Strip everything except digits for DB
        raw_Account = self.le_account.text()
        clean_acc = "".join(filter(str.isdigit, raw_Account))
        
        return {
            "type": self.cb_type.currentText(),
            "contractor": self.le_contractor.text(),
            "desc": self.le_desc.text(),
            "account": clean_acc,
            "date": self.de_date.date().toPython(),
            "amount": self.sb_amount.value()
        }

class PaymentDialog(QDialog):
    def __init__(self, invoice_id, parent=None):
        super().__init__(parent)
        self.invoice_id = invoice_id
        self.setWindowTitle("Rejestracja Płatności")
        self.resize(400, 300)
        self.db = next(get_db())
        self.invoice = self.db.query(Invoice).filter(Invoice.id == self.invoice_id).first()
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        form = QFormLayout()
        
        # Info
        remaining = self.invoice.total_gross - self.invoice.paid_amount
        
        # Color logic for refunds
        color = "red" if remaining > 0 else "blue"
        lbl_style = f"font-weight: bold; color: {color};"
        
        self.lbl_total = QLabel(f"{self.invoice.total_gross:.2f} {self.invoice.currency}")
        self.lbl_paid = QLabel(f"{self.invoice.paid_amount:.2f} {self.invoice.currency}")
        self.lbl_remaining = QLabel(f"{remaining:.2f} {self.invoice.currency}")
        self.lbl_remaining.setStyleSheet(lbl_style)
        
        form.addRow("Łącznie do zapłaty (Brutto):", self.lbl_total)
        form.addRow("Już wpłacono/zwrócono:", self.lbl_paid)
        
        rem_label = "Pozostało do zapłaty:" if remaining >= 0 else "Do zwrotu:"
        form.addRow(rem_label, self.lbl_remaining)
        
        # Input
        initial_date = QDate.currentDate()
        if self.invoice.paid_date:
            try:
                # paid_date is datetime in model
                pd = self.invoice.paid_date
                initial_date = QDate(pd.year, pd.month, pd.day)
            except:
                pass
        
        self.date_edit = QDateEdit(initial_date)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setCalendarPopup(True)
        form.addRow("Data rozliczenia:", self.date_edit)

        self.amount_edit = QLineEdit(f"{remaining:.2f}")
        form.addRow("Kwota wpłaty / zwrotu:", self.amount_edit)
        
        # Checkbox
        self.chk_full = QCheckBox("Oznacz jako w pełni rozliczona")
        self.chk_full.setChecked(True)
        form.addRow("", self.chk_full)
        
        layout.addLayout(form)
        
        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        
    def save(self):
        try:
            val = float(self.amount_edit.text().replace(",", "."))
            
            # Allow negatives for refunds if total is negative
            # Logic: paid_amount tracks flow. 
            # If correction (-100), user pays -100 (refund). paid_amount += -100 -> -100.
            # Remaining: -100 - (-100) = 0.
            
            self.invoice.paid_amount += val
            self.invoice.paid_date = self.date_edit.date().toPython()
            
            # Check paid stat logic
            # Epsilon check for float
            remaining = self.invoice.total_gross - self.invoice.paid_amount
            
            if self.chk_full.isChecked() or abs(remaining) < 0.01:
                self.invoice.is_paid = True
            else:
                self.invoice.is_paid = False
                
            self.db.commit()
            self.accept()
        except ValueError:
            QMessageBox.warning(self, "Błąd", "Nieprawidłowa kwota")
        except Exception as e:
            QMessageBox.critical(self, "Błąd", str(e))

    def closeEvent(self, event):
        self.db.close()
        super().closeEvent(event)

class TransferDataDialog(QDialog):
    def __init__(self, invoice_id, parent=None):
        super().__init__(parent)
        self.invoice_id = invoice_id
        self.setWindowTitle("Dane do Przelewu")
        # Removed fixed size
        self.db = next(get_db())
        
        # Load Root and Family
        self.root_inv = self.db.query(Invoice).filter(Invoice.id == self.invoice_id).first()
        self.family = [self.root_inv]
        self._load_descendants(self.root_inv)
        
        from database.models import CompanyConfig
        self.config = self.db.query(CompanyConfig).first()
        
        self.init_ui()
        
    def _load_descendants(self, parent_inv):
         children = self.db.query(Invoice).filter(Invoice.parent_id == parent_inv.id).all()
         for child in children:
             self.family.append(child)
             self._load_descendants(child)
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QVBoxLayout.SetFixedSize)  # Automatically fit content
        
        info = QLabel("Poniżej znajdują się dane potrzebne do wykonania przelewu:")
        layout.addWidget(info)
        
        form_layout = QFormLayout()
        
        # 1. Calc logic (Group)
        self.family.sort(key=lambda x: x.id)
        self.latest_doc = self.family[-1]
        
        total_gross = self.latest_doc.total_gross
        total_paid = sum(i.paid_amount for i in self.family)
        remaining_val = total_gross - total_paid
        
        # Determine Recipient
        recipient_name = ""
        recipient_addr = ""
        account = ""
        
        if self.root_inv.category == InvoiceCategory.SALES:
             recipient_name = self.config.company_name or ""
             recipient_addr = f"{self.config.address or ''}, {self.config.postal_code or ''} {self.config.city or ''}"
             # Use latest doc account or config default
             account = self.latest_doc.bank_account_number or self.config.bank_account or ""
        else:
             if self.root_inv.contractor:
                 recipient_name = self.root_inv.contractor.name or ""
                 recipient_addr = f"{self.root_inv.contractor.address or ''} {self.root_inv.contractor.postal_code or ''} {self.root_inv.contractor.city or ''}"
             account = self.root_inv.bank_account_number or ""
             
        # Title Construction
        title_parts = []
        is_tax = (self.root_inv.type == InvoiceType.PODATEK) or (self.root_inv.number and self.root_inv.number.startswith("Podatek"))
        
        if is_tax:
            title_parts.append(self.root_inv.number)
        else:
            title_parts.append(f"Faktura {self.root_inv.number}")
            
        corrections = [inv for inv in self.family if inv.id != self.root_inv.id]
        if corrections:
            corr_nums = ", ".join([c.number for c in corrections])
            title_parts.append(f"Korekty: {corr_nums}")
            
        title_txt = " / ".join(title_parts)
        
        # Fields
        self.f_name = QLineEdit(recipient_name); self.f_name.setReadOnly(True)
        self.f_addr = QLineEdit(recipient_addr); self.f_addr.setReadOnly(True)
        self.f_acc = BankAccountEdit(account)
        if not account:
            self.f_acc.setPlaceholderText("Wpisz numer konta aby wygenerować kod QR")
        # Allow editing account especially for taxes
        # self.f_acc.setReadOnly(True) 
        
        self.f_title = QLineEdit(title_txt); self.f_title.setReadOnly(True)
        self.f_amt = QLineEdit(f"{remaining_val:.2f}"); self.f_amt.setReadOnly(True)

        form_layout.addRow("Odbiorca:", self.f_name)
        form_layout.addRow("Adres:", self.f_addr)
        form_layout.addRow("Nr Konta:", self.f_acc)
        form_layout.addRow("Tytuł przelewu:", self.f_title)
        form_layout.addRow("Kwota do zapłaty:", self.f_amt)

        # MPP Section (New)
        if getattr(self.root_inv, 'is_split_payment', False):
            # Calculate aggregate remaining
            fam_net_total = sum(i.total_net for i in self.family)
            fam_gross_total = sum(i.total_gross for i in self.family)
            # remaining_val is already calculated based on (gross - paid)
            
            pay_net = 0.0
            pay_vat = 0.0

            if fam_gross_total > 0.01:
                # Calculate VAT part of the remaining amount proportionally
                vat_amount_total = fam_gross_total - fam_net_total
                vat_ratio = vat_amount_total / fam_gross_total
                
                pay_vat = remaining_val * vat_ratio
                pay_net = remaining_val - pay_vat

            mpp_layout = QVBoxLayout()
            # Construct clear message
            mpp_msg = f"MPP / Split Payment\n\nKwota Netto: {pay_net:.2f}\nKwota VAT: {pay_vat:.2f}"
            mpp_lbl = QLabel(mpp_msg)
            mpp_lbl.setStyleSheet("font-weight: bold; color: white; background-color: #D32F2F; border-radius: 5px; padding: 10px; font-size: 11pt;")
            mpp_lbl.setAlignment(Qt.AlignCenter)
            
            mpp_layout.addWidget(mpp_lbl)
            layout.addLayout(mpp_layout)
        
        # Connect text change to update QR (if user types)
        # Using lambda to capture closure vars, but recipient_name/title_txt are constant in dialog lifetime (for now)
        self.f_acc.textChanged.connect(self.trigger_update_qr)
        
        # QR Code Source Toggle
        self.qr_source_group = QGroupBox("Rodzaj kodu QR")
        self.qr_source_layout = QHBoxLayout()
        self.qr_source_group.setLayout(self.qr_source_layout)
        
        from PySide6.QtWidgets import QRadioButton, QButtonGroup
        self.rb_ksef = QRadioButton("KSeF (Weryfikacja/Link)")
        self.rb_bank = QRadioButton("Bank (Płatność)")
        
        self.qr_mode_group = QButtonGroup(self)
        self.qr_mode_group.addButton(self.rb_ksef, 1)
        self.qr_mode_group.addButton(self.rb_bank, 2)
        
        self.qr_source_layout.addWidget(self.rb_ksef)
        self.qr_source_layout.addWidget(self.rb_bank)
        
        layout.addWidget(self.qr_source_group)
        
        # Sekcja kodu QR
        self.qr_container = QGroupBox("Kod QR")
        self.qr_layout = QVBoxLayout()
        self.qr_container.setLayout(self.qr_layout)
        layout.addWidget(self.qr_container)

        layout.addLayout(form_layout)
        
        # Load preference
        settings = QSettings("KsefInvoice", "Settings")
        last_qr_mode = settings.value("last_qr_mode", "ksef")
        if last_qr_mode == "bank":
            self.rb_bank.setChecked(True)
        else:
            self.rb_ksef.setChecked(True)
            
        self.rb_ksef.toggled.connect(self.trigger_update_qr)
        self.rb_bank.toggled.connect(self.trigger_update_qr)
        
        # Store variables for update_qr
        self.curr_recipient_name = recipient_name
        self.curr_title_txt = title_txt
        self.curr_remaining = remaining_val
        self.curr_pay_vat = pay_vat if getattr(self.root_inv, 'is_split_payment', False) else 0.0

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Close)
        btns.accepted.connect(self.save_account) # Save changes to DB
        btns.rejected.connect(self.accept)
        layout.addWidget(btns)
        
        # Initial Render
        self.trigger_update_qr()

    def trigger_update_qr(self):
        # Save preference
        settings = QSettings("KsefInvoice", "Settings")
        mode = "ksef" if self.rb_ksef.isChecked() else "bank"
        settings.setValue("last_qr_mode", mode)
        
        self.update_qr(
            self.f_acc.text(),
            self.curr_remaining,
            self.curr_recipient_name,
            self.curr_title_txt,
            mode=mode,
            pay_vat=self.curr_pay_vat
        )

    def save_account(self):
        new_acc = self.f_acc.text()
        clean_acc = "".join(filter(str.isdigit, new_acc))
        
        # Update Root Invoice
        try:
            # Re-query to be safe attached to session? 
            # self.root_inv is already from self.db session.
            self.root_inv.bank_account_number = clean_acc
            self.db.commit()
            QMessageBox.information(self, "Zapisano", "Zaktualizowano numer konta.")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie udało się zapisać numeru konta: {e}")

    def update_qr(self, account, remaining_val, recipient_name, title_txt, mode="ksef", pay_vat=0.0):
        # Clear previous layout content
        while self.qr_layout.count():
            child = self.qr_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Prioritize Mode
        if mode == "ksef":
            self.render_ksef_qr()
        else:
            self.render_bank_qr(account, remaining_val, recipient_name, title_txt, pay_vat)

    def render_ksef_qr(self):
        self.qr_container.setTitle("Kod QR do weryfikacji KSeF" if self.rb_ksef.isChecked() else "Kod QR do płatności")
        
        # Determine target invoice (Latest Correction or Root)
        target_inv = self.latest_doc
        
        # Skip for internal types
        if target_inv.type in (InvoiceType.PODATEK, InvoiceType.INNE) or \
           (hasattr(target_inv.type, 'value') and target_inv.type.value in ("PODATEK", "INNE")):
            self.qr_layout.addWidget(QLabel("Dla tego typu dokumentu kod KSeF nie jest generowany."))
            return

        ksef_number = getattr(target_inv, 'ksef_number', None)
        ksef_link = None
        hash_b64 = None
        is_offline = False
        
        # Get XML Content
        try:
            xml_content = getattr(target_inv, 'ksef_xml', None)
            if not xml_content:
                gen = KsefXmlGenerator()
                xml_content = gen.generate_invoice_xml(target_inv, self.config)
                # FIX: Ensure QR matches potential future send
                target_inv.ksef_xml = xml_content
                self.db.commit()
            
            xml_bytes_raw = None
            if xml_content:
                if isinstance(xml_content, str):
                    xml_bytes_raw = xml_content.encode('utf-8')
                else:
                    xml_bytes_raw = xml_content

            # 1. ONLINE MODE (Use Raw Hash)
            if ksef_number and xml_bytes_raw:
                 # Standard Online Hash (Raw)
                 hasher = hashlib.sha256(xml_bytes_raw)
                 digest = hasher.digest()
                 hash_b64 = base64.urlsafe_b64encode(digest).decode().rstrip('=')
                 
                 nip = (self.config.nip or "").replace("-", "")
                 env = getattr(target_inv, 'environment', 'test')
                 
                 d_issue = target_inv.date_issue
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

            # 2. OFFLINE MODE (Use C14N Hash as per FA(3))
            elif not ksef_link and xml_bytes_raw:
                 # C14N for Offline
                 try:
                    parser = etree.XMLParser(remove_blank_text=True)
                    root = etree.fromstring(xml_bytes_raw, parser)
                    xml_c14n = etree.tostring(root, method="c14n", exclusive=False, with_comments=False)
                    
                    hasher = hashlib.sha256(xml_c14n)
                    digest = hasher.digest()
                    hash_b64 = base64.urlsafe_b64encode(digest).decode().rstrip('=')
                 except Exception as c14n_ex:
                    print(f"C14N Warning: {c14n_ex}")
                    # Fallback to raw if C14N fails (unlikely)
                    hasher = hashlib.sha256(xml_bytes_raw)
                    digest = hasher.digest()
                    hash_b64 = base64.urlsafe_b64encode(digest).decode().rstrip('=')

                 is_offline = True
                 # Check legacy/stored
                 ksef_link = getattr(target_inv, 'verification_link', None)
                 
                 if not ksef_link:
                     candidate_url = getattr(target_inv, 'upo_url', "")
                     if candidate_url and "/web/verify/" in candidate_url:
                         ksef_link = candidate_url
                 
                 # Generate if still None
                 if not ksef_link:
                     try:
                         nip = (self.config.nip or "").replace("-", "")
                         d_issue = target_inv.date_issue
                         if not d_issue: d_issue = datetime.datetime.now()
                         if isinstance(d_issue, str):
                             try: d_issue = datetime.datetime.strptime(d_issue, "%Y-%m-%d")
                             except: d_issue = datetime.datetime.now()
                         date_str = d_issue.strftime("%d-%m-%Y")
                         
                         env = getattr(target_inv, 'environment', 'test')
                         if env == 'prod':
                              domain = "qr.ksef.mf.gov.pl"
                         else:
                              domain = "qr-demo.ksef.mf.gov.pl"
                         
                         base_url = f"https://{domain}/invoice"
                         
                         ksef_link = f"{base_url}/{nip}/{date_str}/{hash_b64}"
                     except Exception as e:
                         self.qr_layout.addWidget(QLabel(f"Błąd generowania Offline QR: {e}"))
                         return
        except Exception as e:
            print(f"Hash/Gen calc error: {e}")

        try:
            # Generate KSeF QR
            qr = qrcode.QRCode(box_size=8, border=2)
            qr.add_data(ksef_link)
            qr.make(fit=True)
            pil_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
            
            buf = BytesIO()
            pil_img.save(buf, format="PNG")
            qimg = QImage.fromData(buf.getvalue())
            
            # Overlay "KSeF" Text
            painter = QPainter(qimg)
            painter.setRenderHint(QPainter.Antialiasing)
            
            font = QFont("Arial", 14, QFont.Bold)
            painter.setFont(font)
            
            text = "KSeF"
            fm = painter.fontMetrics()
            text_w = fm.horizontalAdvance(text)
            text_h = fm.height()
            
            rect = qimg.rect()
            center_x = rect.width() / 2
            center_y = rect.height() / 2
            
            bg_rect = QRect(int(center_x - text_w/2 - 5), int(center_y - text_h/2 - 5), 
                            int(text_w + 10), int(text_h + 10))
            painter.fillRect(bg_rect, QColor("white"))
            painter.setPen(QColor("black")) 
            painter.drawRect(bg_rect)
            
            painter.setPen(QColor("#D32F2F")) 
            painter.drawText(rect, Qt.AlignCenter, text)
            painter.end()
            
            lbl_img = QLabel()
            pix = QPixmap.fromImage(qimg)
            lbl_img.setPixmap(pix.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            lbl_img.setAlignment(Qt.AlignCenter)
            self.qr_layout.addWidget(lbl_img)
            
            # Info Label
            if is_offline:
                info_txt = "OFFLINE"
            elif ksef_number:
                info_txt = f"{ksef_number}"
            else:
                info_txt = "Zeskanuj, aby zweryfikować"
                
            info = QLabel(info_txt)
            info.setAlignment(Qt.AlignCenter)
            info.setStyleSheet("font-weight: bold;" if is_offline else "")
            self.qr_layout.addWidget(info)
        except Exception as e:
            self.qr_layout.addWidget(QLabel(f"Błąd QR KSeF: {e}"))

    def render_bank_qr(self, account, remaining_val, recipient_name, title_txt, pay_vat):
        self.qr_container.setTitle("Kod QR do płatności (Aplikacja Bankowa)")
        if remaining_val <= 0:
            lbl = QLabel("Należność zapłacona.")
            lbl.setAlignment(Qt.AlignCenter)
            self.qr_layout.addWidget(lbl)
            return

        if not account:
            lbl = QLabel("Wprowadź numer konta, aby wygenerować kod QR.")
            lbl.setAlignment(Qt.AlignCenter)
            self.qr_layout.addWidget(lbl)
            return

        try:
            clean_account = "".join(filter(str.isdigit, account))
            
            if len(clean_account) == 26:
                amount_gr = int(remaining_val * 100)
                safe_name = (recipient_name or "")[:20].replace("|", "") 
                
                # Check for Split Payment
                is_mpp = getattr(self.root_inv, 'is_split_payment', False)
                
                if is_mpp:
                    # MPP Standard ZBP Logic
                    # Title format: /VAT/kwota_vat/IDC/nip_dostawcy/INV/nr_faktury/TXT/tekst
                    
                    # Logic to determine NIP for IDC:
                    # If this is PURCHASE invoice, we pay the SELLER (contractor)
                    # If this is SALES invoice (correction?), we pay the BUYER? No, Sales usually implies we receive.
                    # But TransferDataDialog shows data for TRANSFER.
                    # If SALES, recipient_name is US (CompanyConfig). So IDC maps to OUR NIP?
                    # But MPP is about paying TO someone.
                    
                    target_nip = ""
                    if self.root_inv.category == InvoiceCategory.PURCHASE:
                         # Use contractor NIP
                         if self.root_inv.contractor:
                             target_nip = self.root_inv.contractor.nip or ""
                    else:
                         # Sales - paying to US?
                         if self.config and self.config.nip:
                             target_nip = self.config.nip
                    
                    target_nip = "".join(filter(str.isdigit, target_nip))
                    inv_num = self.root_inv.number or "BRAK"
                    
                    # Ensure VAT format is comma separated X,XX
                    vat_gr = int(pay_vat * 100)
                    vat_str = f"{vat_gr/100:.2f}".replace(".", ",")
                    
                    title_mpp = f"/VAT/{vat_str}/IDC/{target_nip}/INV/{inv_num}/TXT/{title_txt}"
                    safe_title = title_mpp # ZBP title field
                else:
                    safe_title = (title_txt or "")[:32].replace("|", "") 

                # Construct ZBP string
                qr_data = f"|PL|{clean_account}|{amount_gr}|{safe_name}|{safe_title}||||"
                
                qr = qrcode.QRCode(box_size=4, border=2)
                qr.add_data(qr_data)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                
                buf = BytesIO()
                img.save(buf, format="PNG")
                qimg = QImage.fromData(buf.getvalue())
                
                lbl_img = QLabel()
                pix = QPixmap.fromImage(qimg)
                lbl_img.setPixmap(pix.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                lbl_img.setAlignment(Qt.AlignCenter)
                self.qr_layout.addWidget(lbl_img)
                
                desc_txt = "Kod MPP (ZBP)" if is_mpp else "Przelew standardowy"
                info = QLabel(desc_txt)
                info.setAlignment(Qt.AlignCenter)
                self.qr_layout.addWidget(info)
            else:
                lbl = QLabel("Nieprawidłowy numer konta (wymagane 26 cyfr).")
                self.qr_layout.addWidget(lbl)

        except Exception as e:
            self.qr_layout.addWidget(QLabel(f"Błąd generowania QR: {e}"))
            print(f"QR Error: {e}")

    # Compatibility shim if called old way (shouldn't happen with new connect)
    # def update_qr(self, account, remaining_val, recipient_name, title_txt): ...
            # Format: |PL|NRB|KWOTA|NAZWA|TYTUL|RESERVED|RESERVED|RESERVED|
            
            clean_account = "".join(filter(str.isdigit, account))
            
            if len(clean_account) == 26:
                amount_gr = int(remaining_val * 100)
                
                # Sanitize fields
                safe_name = (recipient_name or "")[:20].replace("|", "") 
                safe_title = (title_txt or "")[:32].replace("|", "") 
                
                # Construct ZBP string
                qr_data = f"|PL|{clean_account}|{amount_gr}|{safe_name}|{safe_title}||||"
                
                # Generate QR
                qr_img = qrcode.make(qr_data)
                
                buffer = BytesIO()
                qr_img.save(buffer, format="PNG")
                qimage = QImage.fromData(buffer.getvalue())
                pixmap = QPixmap.fromImage(qimage)
                
                qr_label = QLabel()
                qr_label.setPixmap(pixmap.scaled(200, 200, Qt.KeepAspectRatio))
                qr_label.setAlignment(Qt.AlignCenter)
                self.qr_layout.addWidget(qr_label)
                
            else:
                 pass
                 # Don't show error while typing, or show faint status?
                 if len(clean_account) > 0:
                     lbl = QLabel(f"Nieprawidłowa długość: {len(clean_account)}/26")
                     lbl.setStyleSheet("color: gray;")
                     self.qr_layout.addWidget(lbl)

        except Exception as e:
            print(f"QR Error: {e}")


    def closeEvent(self, event):
        self.db.close()
        super().closeEvent(event)


class SettlementsView(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("KsefInvoice", "Settlements")
        self.init_ui()
        self.restore_filters()
        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Header Row (Title + Filters + Actions)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 10) # Some bottom space
        
        # 1. Title
        title = QLabel("Rozrachunki")
        title.setStyleSheet("font-size: 24px; font-weight: bold; margin-right: 20px;")
        header.addWidget(title)
        
        # Spacer separates Title from Filters (Filters aligned right)
        header.addStretch()
        
        # 2. Filters (Compact, no GroupBox)
        
        # Date From
        header.addWidget(QLabel("Od:"))
        self.date_from = QDateEdit(QDate.currentDate().addMonths(-1))
        self.date_from.setCalendarPopup(True)
        self.date_from.setFixedWidth(110)
        self.date_from.dateChanged.connect(self.save_filters_and_load)
        header.addWidget(self.date_from)
        
        # Date To (Removed per user request)
        # header.addWidget(QLabel("Do:"))
        # self.date_to = QDateEdit(QDate.currentDate())
        # ...
        
        # Type
        self.combo_type = QComboBox()
        self.combo_type.addItems(["Wszystkie", "Sprzedaż", "Zakup", "Podatek", "Inne"])
        self.combo_type.currentTextChanged.connect(self.save_filters_and_load)
        header.addWidget(self.combo_type)
        
        # Status
        self.combo_status = QComboBox()
        self.combo_status.addItems(["Wszystkie", "Opłacone", "Nieopłacone", "Częściowo"])
        self.combo_status.currentTextChanged.connect(self.save_filters_and_load)
        header.addWidget(self.combo_status)
        
        # 3. Buttons
        self.btn_reset = QPushButton("Reset")
        self.btn_reset.setFixedWidth(60)
        self.btn_reset.clicked.connect(self.reset_filters)
        header.addWidget(self.btn_reset)
        
        refresh_btn = QPushButton("Odśwież")
        refresh_btn.setFixedWidth(80)
        refresh_btn.clicked.connect(self.load_data)
        header.addWidget(refresh_btn)

        # Manual Add
        btn_add = QPushButton("Dodaj Ręcznie")
        btn_add.clicked.connect(self.add_manual_settlement)
        header.addWidget(btn_add)
        
        layout.addLayout(header)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(10) # +1 for Actions, +1 for Date
        self.table.setHorizontalHeaderLabels([
            "Typ", "Numer", "Kontrahent", "Termin", "Waluta", "Kwota Brutto", 
            "Zapłacono", "Pozostało", "Status", "Akcje"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # Resize Actions column manually if needed
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.open_context_menu)
        self.table.doubleClicked.connect(self.open_payment)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().sortIndicatorChanged.connect(self.save_sort_state)
        
        layout.addWidget(self.table)
        
        help_lbl = QLabel("Kliknij dwukrotnie na wiersz, aby zarejestrować płatność. Użyj przycisku 'Dane do przelewu' dla szczegółów.")
        help_lbl.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(help_lbl)

    def load_data(self):
        # Refresh on Show
        pass

    def add_manual_settlement(self):
        dlg = ManualSettlementDialog(self)
        if dlg.exec():
            data = dlg.get_data()
            self._save_manual_settlement(data)

    def _save_manual_settlement(self, data):
        db = next(get_db())
        try:
            # Map type to Enum
            cat = InvoiceCategory.PURCHASE
            inv_type = InvoiceType.VAT
            
            t = data['type']
            if t == "Sprzedaż":
                cat = InvoiceCategory.SALES
                inv_type = InvoiceType.INNE # Manual entry treated as Note
            elif t == "Zakup":
                cat = InvoiceCategory.PURCHASE
                inv_type = InvoiceType.INNE # Manual entry treated as Note
            elif t == "Podatek":
                cat = InvoiceCategory.PURCHASE
                inv_type = InvoiceType.PODATEK
            elif t == "Inne":
                cat = InvoiceCategory.PURCHASE
                inv_type = InvoiceType.INNE
            else:
                # Fallback
                cat = InvoiceCategory.PURCHASE
                inv_type = InvoiceType.VAT
            
            # Contractor
            c_name = data['contractor'] or "Inny"
            contractor = db.query(Contractor).filter(Contractor.name == c_name).first()
            if not contractor:
                # Create dummy
                # Musimy zapewnić unikalny NIP dla każdego "fake" kontrahenta, 
                # jeśli tabela Contractors wymaga unikalności (UNIQUE constraint).
                dummy_nip = "0000000000"
                while db.query(Contractor).filter(Contractor.nip == dummy_nip).first():
                     # Generuj losowy nip 10-cyfrowy, aby ominąć constraint
                     dummy_nip = ''.join(random.choices(string.digits, k=10))

                contractor = Contractor(name=c_name, nip=dummy_nip)
                db.add(contractor)
                db.commit()
                db.refresh(contractor)
                
            # Create Invoice
            # Generate random number to avoid collision
            rnd = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            num = data['desc'] or f"MANUAL/{rnd}"
            
            # Check unique
            if db.query(Invoice).filter(Invoice.number == num).first():
                num = f"{num}-{rnd}"
            
            # Konwersja daty płatności na datetime
            deadline_py = data['date'] # To jest date, musimy zrobić datetime
            deadline_dt = datetime.datetime.combine(deadline_py, datetime.time.min)
                
            inv = Invoice(
                contractor_id=contractor.id,
                category=cat,
                type=inv_type,
                number=num,
                date_issue=datetime.datetime.now(),
                date_sale=datetime.datetime.now(),
                payment_deadline=deadline_dt, # Was date, model expects datetime
                total_net=data['amount'],
                total_gross=data['amount'],
                is_paid=False,
                payment_method="Inne",
                currency="PLN",
                # Ensure fields are valid
                notes="Wpis ręczny",
                bank_account_number=data.get('account', "")
            )
            db.add(inv)
            db.commit()
            QMessageBox.information(self, "Sukces", "Dodano rozrachunek.")
            self.load_data()
            
        except Exception as e:
            db.rollback()
            # print error to see details
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Błąd", f"Nie udało się dodać: {e}")
        finally:
            db.close()

    def showEvent(self, event):
        self.load_data()
        super().showEvent(event)

    def reset_filters(self):
        self.date_from.setDate(QDate.currentDate().addMonths(-1))
        self.combo_type.setCurrentIndex(0)
        self.combo_status.setCurrentIndex(0)
        self.save_filters_and_load()

    def restore_filters(self):
        # Restore Date From
        d_val = self.settings.value("date_from")
        if d_val:
            self.date_from.setDate(QDate.fromString(str(d_val), Qt.ISODate))
            
        # Restore Type
        t_val = self.settings.value("type")
        if t_val:
            idx = self.combo_type.findText(str(t_val))
            if idx >= 0:
                self.combo_type.setCurrentIndex(idx)
                
        # Restore Status
        s_val = self.settings.value("status")
        if s_val:
            idx = self.combo_status.findText(str(s_val))
            if idx >= 0:
                self.combo_status.setCurrentIndex(idx)
        
        # Restore Sorting
        sort_col = self.settings.value("sort_column", defaultValue=None)
        sort_ord = self.settings.value("sort_order", defaultValue=None)
        
        if sort_col is not None and sort_ord is not None:
            self.table.horizontalHeader().setSortIndicator(int(sort_col), Qt.SortOrder(int(sort_ord)))

    def save_sort_state(self, logicalIndex, order):
        self.settings.setValue("sort_column", logicalIndex)
        # Handle PySide6 Enum type
        val = order.value if hasattr(order, 'value') else int(order)
        self.settings.setValue("sort_order", val)

    def save_filters_and_load(self):
        # Save state
        self.settings.setValue("date_from", self.date_from.date().toString(Qt.ISODate))
        self.settings.setValue("type", self.combo_type.currentText())
        self.settings.setValue("status", self.combo_status.currentText())
        
        self.load_data()

    def load_data(self):
        db = next(get_db())
        try:
            # Base query
            query = db.query(Invoice)
            
            # 1. Date Filter (Only From, No To)
            d_from = self.date_from.date().toPython()
            d_from_dt = datetime.datetime.combine(d_from, datetime.time.min)
            
            query = query.filter(Invoice.date_issue >= d_from_dt)
            
            # 2. Type Filter
            type_txt = self.combo_type.currentText()
            if type_txt == "Sprzedaż":
                query = query.filter(Invoice.category == InvoiceCategory.SALES)
            elif type_txt == "Zakup":
                query = query.filter(
                    (Invoice.category == InvoiceCategory.PURCHASE) & 
                    (Invoice.type != InvoiceType.PODATEK) &
                    (Invoice.type != InvoiceType.INNE)
                )
            elif type_txt == "Podatek":
                 query = query.filter(Invoice.category == InvoiceCategory.PURCHASE, Invoice.type == InvoiceType.PODATEK)
            elif type_txt == "Inne":
                 query = query.filter(Invoice.type == InvoiceType.INNE)
                
            # 3. Status Filter
            status_txt = self.combo_status.currentText()
            if status_txt == "Opłacone":
                query = query.filter(Invoice.is_paid == True)
            elif status_txt == "Nieopłacone":
                query = query.filter(Invoice.is_paid == False, Invoice.paid_amount == 0)
            elif status_txt == "Częściowo opłacone":
                query = query.filter(Invoice.is_paid == False, Invoice.paid_amount > 0)
            
            # Results
            invoices = query.order_by(Invoice.date_issue.desc()).all()
            
            self.table.setRowCount(0)
            
            # Results
            invoices = query.order_by(Invoice.date_issue.desc()).all()
            
            # --- Logika grupowania ("wątki": faktura + korekty) ---
            filtered_invoices = invoices
            
            # Zbiór wszystkich ID rootów, które wyświetlimy
            # Strategia view: Iterujemy po filtered. Znajdujemy Roota. Jeśli Root jeszcze nie wyświetlony, wyświetlamy go.
            # Ważne: Żeby bilans był poprawny, musimy dociągnąć całą rodzinę (nawet jeśli filtr daty wyciął brata).
            # W SQL to dodatkowe zapytania (lazy loading .parent/.children).
            
            processed_root_ids = set()
            self.table.setRowCount(0)
            
            # Disable sorting during load
            self.table.setSortingEnabled(False)
            
            for inv in filtered_invoices:
                # 1. Znajdź Roota (Fakturę pierwotną)
                curr = inv
                depth = 0
                while curr.parent and depth < 10:
                    curr = curr.parent
                    depth += 1
                root = curr
                
                if root.id in processed_root_ids:
                    continue
                processed_root_ids.add(root.id)

                # 2. Pobierz całą rodzinę, żeby policzyć saldo wątku
                # Rekurencyjnie zbieramy dzieci roota
                family = [root]
                
                def collect_descendants(parent_inv):
                    # Wymagane jest, aby relacje były załadowane.
                    # Jeśli używamy tej samej sesji co query, parent_id/relationship zadziała.
                    # Ale relationship 'children' nie jest zdefiniowane w models.py (brak backref explicit).
                    # Musimy query zrobić.
                    children = db.query(Invoice).filter(Invoice.parent_id == parent_inv.id).all()
                    for child in children:
                        family.append(child)
                        collect_descendants(child)
                
                collect_descendants(root)

                # 3. Policz saldo grupy
                # Sortujemy rodzinę po ID (lub dacie), aby znaleźć najnowszą wersję dokumentu
                # Zakładamy, że najnowszy dokument (korekta) zawiera "aktualną" wartość brutto całej transakcji.
                family.sort(key=lambda x: x.id)
                latest_doc = family[-1]
                
                # W tym modelu (zbadane w DB) korekta przechowuje NOWĄ PEŁNĄ WARTOŚĆ, a nie różnicę.
                # Zatem należność grupy to wartość z OSTATNIEGO dokumentu.
                total_gross_group = latest_doc.total_gross
                
                # Wpłaty sumujemy ze wszystkich dokumentów (płatność mogła być do roota lub do korekty)
                total_paid_group = sum(i.paid_amount for i in family)
                remaining_group = total_gross_group - total_paid_group

                # Status Logic
                status_color = QColor("red")
                status_text = "Nierozliczona"
                
                # Tolerancja groszowa
                if abs(remaining_group) < 0.02:
                    status_color = QColor("green")
                    status_text = "Rozliczona"
                    remaining_group = 0.00
                elif total_paid_group > 0.01:
                    status_color = QColor("orange")
                    status_text = "Częściowo"
                
                # Jeśli ujemne (zwrot)
                if remaining_group < -0.01:
                    status_color = QColor("blue")
                    status_text = "Do zwrotu"

                # 4. Wyświetlanie
                row = self.table.rowCount()
                self.table.insertRow(row)
                
                # Typ
                if root.type == InvoiceType.PODATEK:
                    cat_text = "Podatek"
                    color_brush = QBrush(QColor("magenta"))
                elif root.type == InvoiceType.INNE:
                    cat_text = "Inne"
                    color_brush = QBrush(QColor("darkCyan"))
                elif root.category == InvoiceCategory.SALES:
                    cat_text = "Sprzedaż"
                    color_brush = QBrush(QColor("blue"))
                else:
                    cat_text = "Zakup"
                    color_brush = QBrush(QColor("orange"))
                
                item_cat = QTableWidgetItem(cat_text)
                item_cat.setForeground(color_brush)
                self.table.setItem(row, 0, item_cat)
                
                # Numer (+ info o korektach)
                corrections_count = len(family) - 1
                disp_num = root.number
                if corrections_count > 0:
                    disp_num += f" (+{corrections_count} kor.)"
                
                item_num = QTableWidgetItem(disp_num)
                # Store data for actions
                item_num.setData(Qt.UserRole, root.id)
                item_num.setData(Qt.UserRole + 1, remaining_group)
                self.table.setItem(row, 1, item_num)
                
                # Kontrahent
                ctr_name = root.contractor.name if root.contractor else "Brak"
                self.table.setItem(row, 2, QTableWidgetItem(ctr_name))
                
                # Termin Płatności (New)
                date_deadline = ""
                if root.payment_deadline:
                    # Check if datetime or date
                    if isinstance(root.payment_deadline, datetime.datetime):
                        date_deadline = root.payment_deadline.strftime("%Y-%m-%d")
                    else:
                        date_deadline = str(root.payment_deadline)
                self.table.setItem(row, 3, QTableWidgetItem(date_deadline))
                
                # Waluta
                self.table.setItem(row, 4, QTableWidgetItem(root.currency))
                
                # Brutto (Suma Grupy) - Sortable
                item_gross = NumericItem(f"{total_gross_group:.2f}")
                self.table.setItem(row, 5, item_gross)
                
                # Zapłacono (Suma Grupy) - Sortable
                item_paid = NumericItem(f"{total_paid_group:.2f}")
                self.table.setItem(row, 6, item_paid)
                
                # Pozostało (Suma Grupy) - Sortable
                item_rem = NumericItem(f"{remaining_group:.2f}")
                item_rem.setFont(self.get_bold_font())
                item_rem.setForeground(QBrush(status_color))
                self.table.setItem(row, 7, item_rem)
                
                # Status
                item_stat = QTableWidgetItem(status_text)
                item_stat.setBackground(QBrush(status_color))
                item_stat.setForeground(QBrush(QColor("white") if status_color != QColor("orange") else QColor("black")))
                item_stat.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, 8, item_stat)
                
                # Actions Container
                container = QWidget()
                layout_actions = QHBoxLayout(container)
                layout_actions.setContentsMargins(0, 2, 0, 2)
                layout_actions.setSpacing(4)
                layout_actions.setAlignment(Qt.AlignCenter)

                # Settle Button
                btn_settle = QPushButton()
                btn_settle.setIcon(self.style().standardIcon(QStyle.SP_DialogApplyButton)) 
                btn_settle.setToolTip("Rozlicz wątek (zarejestruj wpłatę/zwrot)")
                btn_settle.setFixedWidth(30)
                # Pass Root ID and Remaining
                btn_settle.clicked.connect(lambda ch, r=root.id, rem=remaining_group: self.show_group_payment_dialog(r, rem))
                
                # Transfer Data Button
                btn_transfer = QPushButton()
                btn_transfer.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxInformation))
                btn_transfer.setToolTip("Dane do przelewu")
                btn_transfer.setFixedWidth(30)
                btn_transfer.clicked.connect(lambda ch, i=root.id: self.show_transfer_data(i))
                
                layout_actions.addWidget(btn_settle)
                layout_actions.addWidget(btn_transfer)
                self.table.setCellWidget(row, 9, container)
                
            # Enable sorting after load
            self.table.setSortingEnabled(True)
        
        except Exception as e:
            print(f"Error loading settlements: {e}")
            import traceback
            traceback.print_exc()
        finally:
            db.close()

    def get_bold_font(self):
        f = self.font()
        f.setBold(True)
        return f
            
    def show_group_payment_dialog(self, root_id, remaining_val):
        dlg = GroupPaymentDialog(root_id, remaining_val, self)
        if dlg.exec():
            self.load_data()


            
    def show_transfer_data(self, invoice_id):
        dlg = TransferDataDialog(invoice_id, self)
        dlg.exec()
        
    def show_payment_dialog(self, invoice_id):
        dlg = PaymentDialog(invoice_id, self)
        if dlg.exec():
            self.load_data()

    def open_payment(self, index):
        if not index.isValid(): return
        row = index.row()
        # Data is stored in column 1 (Number)
        item = self.table.item(row, 1)
        inv_id = item.data(Qt.UserRole)
        remaining = item.data(Qt.UserRole + 1)
        
        # Use Group Payment Dialog to match row logic
        if inv_id is not None:
             self.show_group_payment_dialog(inv_id, remaining)

    def open_context_menu(self, position):
        menu = QMenu()
        
        # Check if row is selected
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
            
        row = rows[0].row()
        item = self.table.item(row, 1)
        if not item:
            return
            
        inv_id = item.data(Qt.UserRole)
        
        # Add actions
        transfer_action = QAction("Dane do przelewu", self)
        transfer_action.triggered.connect(lambda: self.show_transfer_data(inv_id))
        menu.addAction(transfer_action)
        
        menu.addSeparator()
        
        delete_action = QAction("Usuń wpis", self)
        delete_action.triggered.connect(lambda: self.delete_settlement(inv_id))
        menu.addAction(delete_action)
        
        menu.exec(self.table.viewport().mapToGlobal(position))

    def delete_settlement(self, inv_id):
        db = next(get_db())
        try:
            inv = db.query(Invoice).filter(Invoice.id == inv_id).first()
            if not inv:
                QMessageBox.warning(self, "Błąd", "Nie znaleziono wpisu.")
                return

            # --- Zabezpieczenia (Safeguards) ---
            
            # 1. KSeF
            if inv.ksef_number or inv.is_sent_to_ksef:
                QMessageBox.critical(self, "Operacja zablokowana", 
                    "Nie można usunąć dokumentu zarejestrowanego w KSeF.\nJest to trwały zapis księgowy.")
                return

            # 2. Korekty (Dzieci)
            child_count = db.query(Invoice).filter(Invoice.parent_id == inv.id).count()
            if child_count > 0:
                QMessageBox.warning(self, "Operacja zablokowana", 
                    f"Ten dokument posiada powiązane korekty ({child_count}).\nAby go usunąć, należy najpierw usunąć wszystkie korekty.")
                return

            # 3. Pozycje faktury (Realny dokument vs Wpis ręczny)
            # Sprawdzamy, czy faktura ma pozycje towarowe. Jeśli tak, to jest to dokument źródłowy.
            if inv.items and len(inv.items) > 0:
                 QMessageBox.warning(self, "Operacja zablokowana", 
                     "Ten wpis jest powiązany z pełnym dokumentem faktury (posiada pozycje).\n"
                     "Nie można go usunąć z poziomu modułu Rozrachunków, aby nie utracić danych faktury.\n\n"
                     "Jeżeli chcesz usunąć fakturę (szkic), zrób to w module Faktury.")
                 return
            
            # --- Potwierdzenie ---
            reply = QMessageBox.question(
                self, 
                "Potwierdzenie", 
                "Czy na pewno chcesz usunąć ten ręczny wpis rozrachunkowy?\nTej operacji nie można cofnąć.",
                QMessageBox.Yes | QMessageBox.No, 
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                db.delete(inv)
                db.commit()
                self.load_data()
                QMessageBox.information(self, "Sukces", "Wpis został usunięty.")
                
        except Exception as e:
            db.rollback()
            QMessageBox.critical(self, "Błąd", f"Nie udało się usunąć: {e}")
        finally:
            db.close()

class GroupPaymentDialog(QDialog):
    def __init__(self, root_id, remaining_val, parent=None):
        super().__init__(parent)
        self.root_id = root_id
        self.group_remaining = remaining_val
        self.setWindowTitle("Rozliczenie grupowe")
        self.db = next(get_db())
        self.root_inv = self.db.query(Invoice).filter(Invoice.id == self.root_id).first()
        
        # Pobierz całą rodzinę (korekty)
        self.family = [self.root_inv]
        self._load_descendants(self.root_inv)
        
        self.init_ui()
        
    def _load_descendants(self, parent_inv):
         children = self.db.query(Invoice).filter(Invoice.parent_id == parent_inv.id).all()
         for child in children:
             self.family.append(child)
             self._load_descendants(child)
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QVBoxLayout.SetFixedSize)
        form = QFormLayout()
        
        corrections = [inv for inv in self.family if inv.id != self.root_inv.id]
        
        if corrections:
             label_text = f"Rozliczasz fakturę {self.root_inv.number} wraz z korektami:"
        else:
             label_text = f"Rozliczasz fakturę {self.root_inv.number}"

        info_label = QLabel(label_text)
        info_label.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
        layout.addWidget(info_label)
        
        if corrections:
            corr_layout = QVBoxLayout()
            corr_layout.setSpacing(2)
            corr_layout.setContentsMargins(10, 0, 0, 10)
            for corr in corrections:
                date_str = corr.date_issue.strftime('%Y-%m-%d') if corr.date_issue else "?"
                lbl = QLabel(f"• {corr.number} (z dn. {date_str})")
                lbl.setStyleSheet("color: #555;")
                corr_layout.addWidget(lbl)
            
            # Reduce stretch here
            layout.addLayout(corr_layout)
        
        # Color logic
        color = "red" if self.group_remaining > 0 else "blue"
        lbl_style = f"font-weight: bold; color: {color}; font-size: 14px;"
        
        self.lbl_rem = QLabel(f"{self.group_remaining:.2f} {self.root_inv.currency}")
        self.lbl_rem.setStyleSheet(lbl_style)
        
        label_txt = "Do zapłaty:" if self.group_remaining >= 0 else "Do zwrotu:"
        form.addRow(label_txt, self.lbl_rem)
        
        # Date Input
        initial_date = QDate.currentDate()
        if self.root_inv.paid_date:
            try:
                pd = self.root_inv.paid_date
                initial_date = QDate(pd.year, pd.month, pd.day)
            except:
                pass

        self.date_edit = QDateEdit(initial_date)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setCalendarPopup(True)
        form.addRow("Data rozliczenia:", self.date_edit)

        # Default value matches remaining (absolute for input simplicity?)
        # Let's keep signs to be explicit. If -200, user sees -200.
        self.amount_edit = QLineEdit(f"{self.group_remaining:.2f}")
        form.addRow("Kwota operacji:", self.amount_edit)
        
        layout.addLayout(form)
        
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def save(self):
        try:
            val = float(self.amount_edit.text().replace(",", "."))
            
            # --- Validacja Nadpłaty ---
            if val > 0:
                # Próba dokonania wpłaty
                if self.group_remaining <= 0.01:
                    QMessageBox.warning(self, "Błąd", "Dokument jest już w pełni opłacony (lub nadpłacony).\nNie można dodać kolejnej wpłaty.")
                    return
                
                if val > self.group_remaining + 0.01:
                     QMessageBox.warning(self, "Błąd", f"Kwota wpłaty ({val:.2f}) przewyższa pozostałą należność ({self.group_remaining:.2f})")
                     return
            
            elif val < 0:
                # Próba zwrotu (wartość ujemna)
                # Dopuszczalne tylko, jeśli mamy nadpłatę (remaining < 0) lub korektę wpłaty.
                # Jeśli remaining < 0 (np. -100), to val nie może być mniejsze niż remaining (np. -200).
                if self.group_remaining < -0.01:
                    if val < self.group_remaining - 0.01:
                        QMessageBox.warning(self, "Błąd", f"Kwota zwrotu ({abs(val):.2f}) przewyższa wartość nadpłaty ({abs(self.group_remaining):.2f})")
                        return
            # --------------------------

            # Zapisujemy do Roota
            self.root_inv.paid_amount += val
            self.root_inv.paid_date = self.date_edit.date().toPython()
            
            # Update root flag (indicative)
            # W grupie status liczymy dynamicznie, ale flaga na pojedynczej fv też się przydaje
            if self.root_inv.paid_amount >= self.root_inv.total_gross:
                 self.root_inv.is_paid = True
            else:
                 self.root_inv.is_paid = False
            
            self.db.commit()
            self.accept()
        except ValueError:
            QMessageBox.warning(self, "Błąd", "Nieprawidłowa kwota")
            
    def closeEvent(self, event):
        self.db.close()
        super().closeEvent(event)
