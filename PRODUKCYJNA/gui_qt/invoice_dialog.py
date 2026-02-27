from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, 
                             QLineEdit, QDateEdit, QComboBox, QPushButton, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QLabel, QMessageBox, QAbstractItemView, QFrame,
                             QTabWidget, QWidget, QCheckBox, QTextEdit, QGroupBox, QGridLayout, QInputDialog,
                             QMenu, QRadioButton, QButtonGroup, QStackedWidget, QApplication, QDialogButtonBox, QScrollArea, QStyle)
from PySide6.QtCore import Qt, QDate, QPoint, QSettings
from PySide6.QtGui import QAction, QIcon
from database.engine import get_db
from database.models import (Invoice, InvoiceItem, InvoicePaymentBreakdown, Contractor, Product, InvoiceCategory, InvoiceType, 
                           CompanyConfig, TaxSystem, VatRate, LumpSumRate, TaxationForm)
from datetime import datetime
from logic.revenue_service import RevenueService
from gui_qt.product_selector import ProductSelector
from gui_qt.utils import safe_restore_geometry, save_geometry

class LargeItemDescriptionDialog(QDialog):
    def __init__(self, key="", value="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dodatkowy Opis Pozycji (KSeF)")
        
        safe_restore_geometry(self, "largeItemDialogGeometry", min_w=500, min_h=300)
        
        layout = QVBoxLayout(self)
        
        form = QFormLayout()
        self.le_key = QLineEdit(key)
        self.le_key.setPlaceholderText("np. Numer seryjny, Kolor, Uwagi (wymagane)")
        form.addRow("Tytuł (Klucz):", self.le_key)
        
        layout.addLayout(form)
        
        layout.addWidget(QLabel("Opis (Wartość):"))
        self.te_value = QTextEdit()
        self.te_value.setPlainText(value)
        self.te_value.setPlaceholderText("Szczegółowy opis pozycji faktury...")
        layout.addWidget(self.te_value)
        
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def done(self, r):
        save_geometry(self, "largeItemDialogGeometry")
        super().done(r)

    def get_data(self):
        return self.le_key.text().strip(), self.te_value.toPlainText().strip()

class PaymentRowWidget(QWidget):
    def __init__(self, parent=None, remove_callback=None):
        super().__init__(parent)
        self.remove_callback = remove_callback
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.method_combo = QComboBox()
        self.method_combo.addItems(["Przelew", "Gotówka", "Karta", "Kredyt", "Kompensata", "BLIK", "Inne"])
        self.method_combo.setEditable(True)
        
        self.amount_edit = QLineEdit("0.00")
        self.amount_edit.setFixedWidth(100)
        
        self.percent_cb = QCheckBox("%")
        self.percent_cb.setToolTip("Wpisz procent (np. 50), a program przeliczy kwotę")
        self.percent_cb.setTristate(False)  # Ensure only Checked/Unchecked
        self.percent_cb.stateChanged.connect(self.on_percent_toggled)

        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setFixedWidth(110)
        
        self.remove_btn = QPushButton("X")
        self.remove_btn.setFixedWidth(30)
        if self.remove_callback:
            self.remove_btn.clicked.connect(lambda: self.remove_callback(self))
        else:
            self.remove_btn.setVisible(False)
            
        layout.addWidget(QLabel("Metoda:"))
        layout.addWidget(self.method_combo, 1) # Expand
        layout.addWidget(QLabel("Kwota:"))
        layout.addWidget(self.amount_edit)
        layout.addWidget(self.percent_cb)
        layout.addWidget(QLabel("Termin:"))
        layout.addWidget(self.date_edit)
        layout.addWidget(self.remove_btn)
        
        # Internal state
        self._last_percent = 0.0
        self.amount_edit.editingFinished.connect(self.on_amount_changed)

    def on_percent_toggled(self, state):
        if state == 2: # Checked
             pass # Logic handled by parent update usually, or immediate recalc
        else:
             pass

    def on_amount_changed(self):
        # Format
        try:
            val = float(self.amount_edit.text().replace(',', '.') or 0)
            self.amount_edit.setText(f"{val:.2f}")
        except: pass

class NipEntryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dane Kontrahenta")
        self.setModal(True)
        self.setFixedSize(350, 150)
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.country_code = QLineEdit("PL")
        self.country_code.setMaxLength(2)
        self.country_code.setPlaceholderText("Kod (np. PL)")
        self.country_code.setToolTip("Dwuliterowy kod kraju UE (np. PL, DE)")
        
        self.nip_input = QLineEdit()
        self.nip_input.setPlaceholderText("Podaj NIP (bez kresek)")
        
        form.addRow("Kod Kraju:", self.country_code)
        form.addRow("NIP / TIN:", self.nip_input)
        
        layout.addLayout(form)
        
        info = QLabel("Zostaw puste pola by wprowadzić kontrahenta ręcznie.")
        info.setStyleSheet("font-size: 10px; color: gray;")
        layout.addWidget(info)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        
        layout.addWidget(buttons)
        
    def validate_and_accept(self):
        cc = self.country_code.text().strip().upper()
        nip = self.nip_input.text().strip().replace("-", "").replace(" ", "")
        
        # Manual mode check
        if not nip:
            self.result_cc = None
            self.result_nip = None
            self.accept()
            return
            
        if not cc or len(cc) != 2 or not cc.isalpha():
             QMessageBox.warning(self, "Błąd", "Kod kraju musi składać się z 2 liter (np. PL).")
             return

        if not nip.isalnum():
             QMessageBox.warning(self, "Błąd", "NIP może zawierać tylko litery i cyfry.")
             return
             
        if cc == "PL":
             if not nip.isdigit():
                 QMessageBox.warning(self, "Błąd", "Polski NIP musi składać się wyłącznie z cyfr.")
                 return
             if len(nip) != 10:
                 QMessageBox.warning(self, "Błąd", f"Polski NIP musi mieć 10 znaków (wpisano {len(nip)}).")
                 return
        
        self.result_cc = cc
        self.result_nip = nip
        self.accept()

    def get_data(self):
        # Returns tuple (cc, nip) or (None, None)
        if hasattr(self, 'result_cc'):
            return self.result_cc, self.result_nip
        return None, None

class PaymentBreakdownDialog(QDialog):
    def __init__(self, current_breakdowns=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Podział Płatności")
        self.resize(400, 300)
        self.breakdowns = current_breakdowns or [] 
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Metoda", "Kwota"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        layout.addWidget(self.table)
        
        # Tools
        tools = QHBoxLayout()
        add_btn = QPushButton("Dodaj")
        add_btn.clicked.connect(self.add_row)
        del_btn = QPushButton("Usuń")
        del_btn.clicked.connect(self.del_row)
        tools.addWidget(add_btn)
        tools.addWidget(del_btn)
        layout.addLayout(tools)
        
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        
        self.load_data()

    def load_data(self):
        self.table.setRowCount(0)
        for item in self.breakdowns:
            r = self.table.rowCount()
            self.table.insertRow(r)
            
            cb = QComboBox()
            cb.addItems(["Gotówka", "Karta", "Przelew", "Kredyt", "Bon", "Czek", "Inne"])
            cb.setCurrentText(item.get("method", "Gotówka"))
            self.table.setCellWidget(r, 0, cb)
            
            self.table.setItem(r, 1, QTableWidgetItem(f"{item.get('amount', 0.0):.2f}"))

    def add_row(self):
        r = self.table.rowCount()
        self.table.insertRow(r)
        cb = QComboBox()
        cb.addItems(["Gotówka", "Karta", "Przelew", "Kredyt", "Bon", "Czek", "Inne"])
        self.table.setCellWidget(r, 0, cb)
        self.table.setItem(r, 1, QTableWidgetItem("0.00"))

    def del_row(self):
        r = self.table.currentRow()
        if r >= 0: self.table.removeRow(r)

    def get_data(self):
        res = []
        for r in range(self.table.rowCount()):
            cb = self.table.cellWidget(r, 0)
            method = cb.currentText()
            try:
                txt = self.table.item(r, 1).text()
                amt = float(txt.replace(",", "."))
            except: amt = 0.0
            if amt > 0:
                res.append({"method": method, "amount": amt})
        return res

class InvoiceDialog(QDialog):
    def __init__(self, category=InvoiceCategory.SALES, invoice_id=None, duplicated_invoice_id=None, corrected_invoice_id=None, parent=None):
        super().__init__(parent)
        
        safe_restore_geometry(self, "invoiceDialogGeometry", default_percent_w=0.9, default_percent_h=0.9, min_w=1000, min_h=700)

        self.category = category
        self.invoice_id = invoice_id
        self.duplicated_invoice_id = duplicated_invoice_id
        self.corrected_invoice_id = corrected_invoice_id # ID of invoice being corrected
        self.is_correction_mode = bool(corrected_invoice_id)
        
        self.db = next(get_db())
        
        # Load Config & Rates
        self.config = self.db.query(CompanyConfig).first()
        self.vat_rates = self.db.query(VatRate).all()
        if not self.vat_rates:
            defaults = [
                ("23%", 0.23),
                ("8%", 0.08),
                ("5%", 0.05),
                ("0% wdt", 0.0),
                ("0% exp", 0.0),
                ("zw", 0.0),
                ("oo", 0.0),
                ("np.", 0.0),
                ("np. u p.", 0.0)
            ]
            try:
                for name, rate_val in defaults:
                    self.db.add(VatRate(name=name, rate=rate_val))
                self.db.commit()
                self.vat_rates = self.db.query(VatRate).all()
            except Exception as e:
                print(f"Error seeding VAT rates: {e}")
                self.db.rollback()

        self.lump_sum_rates = self.db.query(LumpSumRate).all()
        
        # Determine Mode
        self.is_ryczalt_mode = False
        self.is_exempt_mode = False
        
        if self.config:
            # Ryczałt applies only to our Sales (Tax on Revenue)
            if self.category == InvoiceCategory.SALES and self.config.taxation_form == TaxationForm.RYCZALT:
                self.is_ryczalt_mode = True
            
            # Logic for Exempt Mode
            # For SALES: Depends on My Configuration
            if self.category == InvoiceCategory.SALES and not self.config.is_vat_payer:
                self.is_exempt_mode = True
            # For PURCHASE: Defaults to Standard VAT (False), changes only on Contractor selection
            elif self.category == InvoiceCategory.PURCHASE:
                self.is_exempt_mode = False

        self.current_payment_splits = []
        
        title = "Faktura Sprzedaży" if category == InvoiceCategory.SALES else "Faktura Zakupu"
        if invoice_id:
            title = f"Edycja {title}"
        elif self.is_correction_mode:
            title = f"Korekta Faktury"
        else:
            title = f"Nowa {title}"
        self.setWindowTitle(title)
        self.resize(1200, 800)
        
        self.init_ui()
        self.load_data()
        self.check_limit_status()
        self.check_correction_lock()

        # Connect date change signal AFTER loading data to avoid triggers during load
        self.date_issue.dateChanged.connect(self.on_date_changed)

    def check_correction_lock(self):
        """
        Blocks editing if:
        1. The invoice has subsequent corrections (historical document).
        2. The invoice has been finalized in KSeF (Read-Only).
        """
        if not self.invoice_id: return
        
        from database.models import Invoice
        inv = self.db.query(Invoice).get(self.invoice_id)
        if not inv: return

        is_ksef_locked = bool(inv.ksef_number)
        
        # Check if any invoice points to this one as parent
        child = self.db.query(Invoice).filter(Invoice.parent_id == self.invoice_id).order_by(Invoice.id.desc()).first()
        
        reasons = []
        if is_ksef_locked:
             reasons.append("Dokument został zatwierdzony w KSeF.")
        if child:
             reasons.append(f"Istnieje faktura korygująca nr {child.number}.")
        
        if reasons:
             self.save_btn.setEnabled(False)
             
             block_label = "Zablokowane (KSeF)" if is_ksef_locked else "Zablokowane (Korekta)"
             self.save_btn.setText(block_label)
             
             tips = []
             if is_ksef_locked: tips.append("Dokument wysłany do KSeF nie podlega edycji.")
             if child: tips.append(f"Nie można edytować: Istnieje faktura korygująca nr {child.number}")
             
             self.save_btn.setToolTip("\n".join(tips))
             
             msg = "BLOKADA EDYCJI:\n" + "\n".join(reasons) + "\n\nAby zmienić dane, musisz wystawić fakturę korygującą."
             self.warning_banner.setText(msg)
             self.warning_banner.setStyleSheet("background-color: #e3f2fd; color: #0d47a1; padding: 10px; border: 2px solid #1565c0; font-weight: bold; font-size: 14px;")
             self.warning_banner.setVisible(True)
             
             current_title = self.windowTitle()
             if "[TYLKO DO ODCZYTU]" not in current_title:
                self.setWindowTitle(current_title + " [TYLKO DO ODCZYTU]")

    def check_limit_status(self):
        # Only check for SALES
        if self.category != InvoiceCategory.SALES:
            return
            
        srv = RevenueService(self.db)
        status_data = srv.check_vat_limit_status()
        
        status_code = status_data.get('status', 'OK')
        current_rev = status_data.get('current', 0.0)
        limit_val = status_data.get('limit', 0.0)
        # Warning threshold value is not returned by service in dict, but we can compute or ignoring displaying it if not passed.
        # Actually message contains details.
        
        if status_code == "BLOCKED":
             self.warning_banner.setText(f"ALARM: Przekroczono limit zwolnienia VAT! (Sprzedaż: {current_rev:.2f} zł / Limit: {limit_val:.2f} zł)")
             self.warning_banner.setStyleSheet("background-color: #ffebee; color: #b71c1c; padding: 10px; border: 2px solid #d32f2f; font-weight: bold; font-size: 14px;")
             self.warning_banner.setVisible(True)
             
             if not self.config.is_vat_payer and not self.is_correction_mode and not self.invoice_id:
                  # Only block NEW invoices if not VAT payer
                  self.save_btn.setEnabled(False)
                  self.save_btn.setText("Zablokowane (Limit VAT)")
                  
        elif status_code == "WARNING":
             self.warning_banner.setText(f"UWAGA: Zbliżasz się do limitu VAT. (Sprzedaż: {current_rev:.2f} zł)")
             self.warning_banner.setStyleSheet("background-color: #fff3e0; color: #e65100; padding: 10px; border: 1px solid #ffb74d; font-weight: bold;")
             self.warning_banner.setVisible(True)
        else:
             self.warning_banner.setVisible(False)

    def done(self, r):
        save_geometry(self, "invoiceDialogGeometry")
        super().done(r)

    def init_ui(self):
        container = QVBoxLayout(self)

        # Limit Warning Banner
        self.warning_banner = QLabel()
        self.warning_banner.setStyleSheet("background-color: #ffebee; color: #c62828; padding: 10px; border: 1px solid #ef9a9a; font-weight: bold;")
        self.warning_banner.setVisible(False)
        container.addWidget(self.warning_banner)
        
        # Tabs system
        self.tabs = QTabWidget()
        container.addWidget(self.tabs)
        
        # 1. Main Data Tab
        self.tab_main = QWidget()
        self.tabs.addTab(self.tab_main, "Dane Podstawowe")
        self.init_main_tab()
        
        # 2. Payments Tab
        self.tab_payment = QWidget()
        self.tabs.addTab(self.tab_payment, "Płatności")
        self.init_payment_tab()
        
        # 3. KSeF / Annotations Tab
        self.tab_ksef = QWidget()
        self.tabs.addTab(self.tab_ksef, "KSeF / Opcje")
        self.init_ksef_tab()

        # Buttons
        btn_box = QHBoxLayout()
        self.info_lbl = QLabel("")
        if self.is_ryczalt_mode: self.info_lbl.setText("Tryb: Ryczałt")
        if self.is_exempt_mode: self.info_lbl.setText(self.info_lbl.text() + " | Zwolniony z VAT")
        
        btn_box.addWidget(self.info_lbl)
        
        self.save_btn = QPushButton("Zapisz")
        self.save_btn.clicked.connect(self.save_invoice)
        self.cancel_btn = QPushButton("Anuluj")
        self.cancel_btn.clicked.connect(self.reject)
        
        btn_box.addStretch()
        btn_box.addWidget(self.cancel_btn)
        btn_box.addWidget(self.save_btn)
        container.addLayout(btn_box)
        
        self.selected_contractor = None

    def show_correction_help(self):
        help_text = """
        <h3>Instrukcja Wystawiania Korekt</h3>
        <p>Logika korygowania faktur w systemie KSeF opiera się na wystawieniu dokumentu, który wskazuje stan <b>PO KOREKCIE</b>. System automatycznie wylicza różnicę względem faktury pierwotnej podczas księgowania, ale na fakturze korygującej musisz podać pełne, poprawne dane aktualne.</p>
        
        <h4>Scenariusz 1: Zmiana Ceny (np. Rabat)</h4>
        <ul>
            <li>Zostawiasz <b>Ilość</b> bez zmian (np. 1).</li>
            <li>Wpisujesz nową, poprawną <b>Cenę</b> (np. niższą).</li>
            <li>System wyliczy nową wartość pozycji.</li>
        </ul>

        <h4>Scenariusz 2: Zwrot Towaru (Pełny)</h4>
        <ul>
            <li>Zmieniasz <b>Ilość</b> na <b>0</b>.</li>
            <li>Cena pozostaje bez zmian (informacyjnie).</li>
            <li>Wartość pozycji wyniesie 0.00.</li>
        </ul>

        <h4>Scenariusz 3: Zwrot Towaru (Częściowy)</h4>
        <ul>
            <li>Zmieniasz <b>Ilość</b> na faktycznie zatrzymaną przez klienta (np. było 10, zwrócił 2 -> wpisujesz 8).</li>
            <li>Cena bez zmian.</li>
        </ul>

        <h4>Scenariusz 4: Korekta Danych Formalnych</h4>
        <ul>
            <li>Jeśli cena i ilość są poprawne, a zmieniły się np. dane nabywcy lub opis, pozycje pozostawiasz bez zmian (Ilość i Cena jak na fakturze pierwotnej).</li>
        </ul>
        
        <p><b>Ważne:</b> W przypadku KSeF nie wysyłamy "delty" (różnicy), lecz stan docelowy pozycji. Wyjątkiem są specyficzne przypadki korekt zbiorczych, ale w standardowym procesie podajemy dane "Jak powinno być".</p>
        """
        QMessageBox.information(self, "Pomoc - Korekty", help_text)

    def init_main_tab(self):
        layout = QVBoxLayout(self.tab_main)
        
        # Initialize Items Table early to avoid AttributeError during UI setup
        self.items_table = QTableWidget()
        # Dynamic Columns
        cols = ["Nazwa", "Indeks/GTU", "JM", "Ilość", "Cena", "VAT %"]
        if self.is_ryczalt_mode:
            cols.append("Ryczałt %") # Extra column
        cols.append("Wartość") # Total line value
        self.items_table.setColumnCount(len(cols))
        self.items_table.setHorizontalHeaderLabels(cols)
        self.items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.items_table.itemChanged.connect(self.calculate_row_totals)
        
        # Init totals labels early
        self.total_net_lbl = QLabel("Netto: 0.00")
        self.total_gross_lbl = QLabel("Brutto: 0.00")
        self.total_gross_lbl.setStyleSheet("font-weight: bold; font-size: 16px;")

        # Correction Info Block (Only in Correction Mode)
        if self.is_correction_mode:
             corr_grp = QGroupBox("Dane Korekty")
             corr_grp.setStyleSheet("QGroupBox { border: 2px solid orange; margin-top: 10px; } QGroupBox::title { color: orange; }")
             corr_lay = QGridLayout()
             
             # Help Button
             btn_help = QPushButton("?")
             btn_help.setFixedWidth(30)
             btn_help.setStyleSheet("font-weight: bold; background-color: #2196F3; color: white; border-radius: 15px;")
             btn_help.setToolTip("Kliknij, aby zobaczyć instrukcję wystawiania korekt")
             btn_help.clicked.connect(self.show_correction_help)
             corr_lay.addWidget(btn_help, 0, 2)
             
             corr_lay.addWidget(QLabel("Przyczyna korekty (Wymagane):"), 0, 0)
             self.correction_reason_edit = QLineEdit()
             self.correction_reason_edit.setPlaceholderText("np. Zwrot towaru, Błąd w cenie, Pomyłka w stawce VAT")
             corr_lay.addWidget(self.correction_reason_edit, 0, 1)

             corr_lay.addWidget(QLabel("Typ skutku korekty:"), 1, 0)
             self.correction_type_combo = QComboBox()
             # KSeF uses logical values 1, 2, 3 usually, or just description. 
             # Prompt: "Korekta skutkująca w dacie ujęcia faktury pierwotnej" vs "bieżącej"
             # Let's map: 
             # 1 -> In Minus (usually current date if specific conditions met, or original)
             # Actually user prompted: a) Data ujęcia pierwotnej b) Data wystawienia korygującej
             self.correction_type_combo.addItem("1 - Korekta zmniejszająca (Data faktury korygującej)", 1)
             self.correction_type_combo.addItem("2 - Korekta zwiększająca (Data faktury pierwotnej)", 2)
             # User prompt mentions: 
             # a) Korekta skutkująca w dacie ujęcia faktury pierowtnej
             # b) Korekta skutkująca w dacie wystawienia faktury korygującej
             # Let's verify KSeF mapping later, for now store selection.
             corr_lay.addWidget(self.correction_type_combo, 1, 1)
             
             corr_lay.addWidget(QLabel("Faktura Korygowana:"), 2, 0)
             self.parent_inv_info = QLabel("Ładowanie...")
             self.parent_inv_info.setStyleSheet("font-weight: bold;")
             corr_lay.addWidget(self.parent_inv_info, 2, 1)
             
             corr_grp.setLayout(corr_lay)
             layout.addWidget(corr_grp)

        # Top Group: Document Info & Contractor
        top_group = QHBoxLayout()
        
        # --- Left Column: Document Metadata ---
        left_col = QVBoxLayout()
        
        # Row 1: Number & Type
        row1 = QHBoxLayout()
        self.number_edit = QLineEdit()
        self.number_edit.setText("")
        
        # If Sales -> Auto placeholder
        if self.category == InvoiceCategory.SALES:
            self.number_edit.setPlaceholderText("AUTO")
            self.number_edit.setReadOnly(True) 
        else:
            self.number_edit.setPlaceholderText("Wpisz numer")
            self.number_edit.setReadOnly(False)
        
        row1.addWidget(QLabel("Numer:"))
        row1.addWidget(self.number_edit)
        
        # New: Regenerate Button for Sales (fixes date mismatch issues)
        if self.category == InvoiceCategory.SALES:
             self.btn_regen_number = QPushButton("⟳")
             self.btn_regen_number.setToolTip("Przelicz numer wg nowej daty (Generuj nowy kolejny numer)")
             self.btn_regen_number.setFixedWidth(30)
             self.btn_regen_number.clicked.connect(self.regenerate_number)
             row1.addWidget(self.btn_regen_number)
        
        left_col.addLayout(row1)
        
        # Row 2: Dates Logic (Single Date OR Period)
        dates_grp = QGroupBox("Daty")
        dates_lay = QVBoxLayout()
        
        # Grid for Dates
        grid_dates = QGridLayout()
        
        self.date_issue = QDateEdit(QDate.currentDate())
        self.date_issue.setCalendarPopup(True)
        self.place_issue = QLineEdit()
        
        grid_dates.addWidget(QLabel("Data wystawienia:"), 0, 0)
        grid_dates.addWidget(self.date_issue, 0, 1)
        grid_dates.addWidget(QLabel("Miejsce:"), 0, 2)
        grid_dates.addWidget(self.place_issue, 0, 3)

        dates_lay.addLayout(grid_dates)
        
        # Type Selector for Date Sale
        self.bg_date_type = QButtonGroup(self)
        self.rb_date_std = QRadioButton("Data Sprzedaży")
        self.rb_date_period = QRadioButton("Okres (Od-Do)")
        self.rb_date_std.setChecked(True)
        self.bg_date_type.addButton(self.rb_date_std)
        self.bg_date_type.addButton(self.rb_date_period)
        
        type_lay = QHBoxLayout()
        type_lay.addWidget(self.rb_date_std)
        type_lay.addWidget(self.rb_date_period)
        dates_lay.addLayout(type_lay)
        
        self.stack_dates = QStackedWidget()
        # Page 1: Single Date
        p1 = QWidget()
        p1_lay = QHBoxLayout(p1)
        p1_lay.setContentsMargins(0,0,0,0)
        self.date_sale = QDateEdit(QDate.currentDate())
        self.date_sale.setCalendarPopup(True)
        p1_lay.addWidget(QLabel("Data Sprzedaży / Dostawy / Usługi:"))
        p1_lay.addWidget(self.date_sale)
        self.stack_dates.addWidget(p1)
        
        # Page 2: Period
        p2 = QWidget()
        p2_lay = QHBoxLayout(p2)
        p2_lay.setContentsMargins(0,0,0,0)
        self.date_period_start = QDateEdit(QDate.currentDate())
        self.date_period_end = QDateEdit(QDate.currentDate())
        self.date_period_start.setCalendarPopup(True)
        self.date_period_end.setCalendarPopup(True)
        p2_lay.addWidget(QLabel("Od:"))
        p2_lay.addWidget(self.date_period_start)
        p2_lay.addWidget(QLabel("Do:"))
        p2_lay.addWidget(self.date_period_end)
        self.stack_dates.addWidget(p2)
        
        dates_lay.addWidget(self.stack_dates)
        
        self.bg_date_type.buttonClicked.connect(lambda: self.stack_dates.setCurrentIndex(1 if self.rb_date_period.isChecked() else 0))
        
        dates_grp.setLayout(dates_lay)
        left_col.addWidget(dates_grp)
        
        # Row 3: Currency
        curr_box = QGroupBox("Waluta")
        curr_layout = QGridLayout()
        self.currency = QComboBox()
        self.currency.addItems(["PLN", "EUR", "USD", "GBP"])
        self.currency.currentTextChanged.connect(self.update_currency_ui)
        
        self.lbl_rate = QLabel("Kurs:")
        self.currency_rate = QLineEdit("1.0000")
        self.lbl_date_rate = QLabel("Data kursu:")
        self.currency_date = QDateEdit(QDate.currentDate())
        self.currency_date.setCalendarPopup(True)
        
        curr_layout.addWidget(QLabel("Kod:"), 0,0)
        curr_layout.addWidget(self.currency, 0,1)
        curr_layout.addWidget(self.lbl_rate, 1,0)
        curr_layout.addWidget(self.currency_rate, 1,1)
        curr_layout.addWidget(self.lbl_date_rate, 2,0)
        curr_layout.addWidget(self.currency_date, 2,1)
        curr_box.setLayout(curr_layout)
        left_col.addWidget(curr_box)
        
        top_group.addLayout(left_col, 1)

        # --- Right Column: Contractor ---
        right_col = QVBoxLayout()
        group_ctr = QGroupBox("Kontrahent")
        ctr_layout = QVBoxLayout()
        
        self.contractor_info = QLabel("Brak wybranego kontrahenta")
        self.contractor_info.setFrameShape(QFrame.StyledPanel)
        self.contractor_info.setWordWrap(True)
        
        self.contractor_btn = QPushButton("Wybierz / Zmień")
        self.contractor_btn.clicked.connect(self.select_contractor)
        
        ctr_layout.addWidget(self.contractor_info)
        ctr_layout.addWidget(self.contractor_btn)
        group_ctr.setLayout(ctr_layout)
        right_col.addWidget(group_ctr)
        
        # Price Type Selection (Net/Gross)
        pt_box = QGroupBox("Sposób wyliczenia (Ceny)")
        pt_lay = QHBoxLayout()
        self.price_type_combo = QComboBox()
        self.price_type_combo.addItems(["Netto", "Brutto"])
        self.price_type_combo.currentTextChanged.connect(self.on_price_type_changed)
        # Default logic
        if self.is_exempt_mode:
            self.price_type_combo.setCurrentText("Brutto")
        else:
            self.price_type_combo.setCurrentText("Netto")
            
        pt_lay.addWidget(self.price_type_combo)
        pt_box.setLayout(pt_lay)
        right_col.addWidget(pt_box)
        
        # Remarks (Uwagi) - Moved here
        right_col.addWidget(QLabel("Uwagi:"))
        self.notes_edit = QTextEdit()
        self.notes_edit.setTabChangesFocus(True)
        self.notes_edit.setMaximumHeight(80)
        # Allow it to expand to fill available space in column
        right_col.addWidget(self.notes_edit)
        
        top_group.addLayout(right_col, 1)
        
        layout.addLayout(top_group)

        # 2. Items Table
        layout.addWidget(QLabel("Pozycje (Kliknij Prawy Przycisk Myszy aby wybrać produkt):"))
        # self.items_table initialization moved to top of init_main_tab to avoid AttributeError
        
        # Context Menu
        self.items_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.items_table.customContextMenuRequested.connect(self.open_items_menu)
        
        layout.addWidget(self.items_table)

        # Items Controls
        items_controls = QHBoxLayout()
        self.add_item_btn = QPushButton("Dodaj pusty wiersz")
        self.add_item_btn.clicked.connect(self.add_item_row)
        self.remove_item_btn = QPushButton("Usuń wiersz")
        self.remove_item_btn.clicked.connect(self.remove_item_row)
        items_controls.addWidget(self.add_item_btn)
        items_controls.addWidget(self.remove_item_btn)
        
        # New Feature: Checkbox for auto-saving items
        self.chk_auto_save_products = QCheckBox("Zapisuj nowe produkty w kartotece")
        self.chk_auto_save_products.setToolTip("Jeśli zaznaczone, nowe pozycje z listy zostaną dodane do modułu Towary")
        # Default True because user complained it didn't save. 
        # But user also said "manual items should be manual".
        # Let's default to False to be safe, or True to be helpful?
        # User said "when adding new product then it should be added". 
        # But "manual items .. should not".
        # Compromise: Checkbox visible, unchecked by default? 
        # Usually users want explicit action. I'll leave unchecked.
        self.chk_auto_save_products.setChecked(False) 
        items_controls.addSpacing(20)
        items_controls.addWidget(self.chk_auto_save_products)
        
        items_controls.addStretch()
        layout.addLayout(items_controls)

        # Summary
        footer_layout = QHBoxLayout()
        # Labels self.total_net_lbl and self.total_gross_lbl initialized at top of method
        
        totals_layout = QVBoxLayout()
        totals_layout.addWidget(self.total_net_lbl)
        totals_layout.addWidget(self.total_gross_lbl)
        footer_layout.addStretch()
        footer_layout.addLayout(totals_layout)
        layout.addLayout(footer_layout)
        
        # Init Visibility
        self.update_currency_ui(self.currency.currentText())

    def init_payment_tab(self):
        # Main Layout
        self.payment_main_layout = QVBoxLayout(self.tab_payment)
        
        # 1. Summary Header
        summary_grp = QGroupBox("Podsumowanie Płatności")
        sum_lay = QGridLayout()
        
        # User requested: "Brutto faktury", "Rozpisano: Kwota (procent)", "Pozostało"
        self.lbl_pay_total = QLabel("Do zapłaty: 0.00") # Will become "Brutto faktury: ..." 
        self.lbl_pay_total.setStyleSheet("font-weight: bold; font-size: 14px;")
        
        self.lbl_pay_entered = QLabel("Rozpisano: 0.00 (0%)")
        self.lbl_pay_remaining = QLabel("Pozostało: 0.00")
        self.lbl_pay_remaining.setStyleSheet("color: red; font-weight: bold;")
        
        sum_lay.addWidget(self.lbl_pay_total, 0, 0)
        sum_lay.addWidget(self.lbl_pay_entered, 0, 1)
        sum_lay.addWidget(self.lbl_pay_remaining, 0, 2)
        summary_grp.setLayout(sum_lay)
        self.payment_main_layout.addWidget(summary_grp)
        
        # 2. Payment Rows Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.payment_rows_layout = QVBoxLayout(self.scroll_content)
        self.payment_rows_layout.addStretch() # Push items up
        self.scroll_area.setWidget(self.scroll_content)
        
        self.payment_main_layout.addWidget(self.scroll_area, 1)
        
        # 3. Actions
        actions_lay = QHBoxLayout()
        self.btn_add_payment = QPushButton("+ Dodaj kolejną płatność")
        self.btn_add_payment.clicked.connect(self.add_payment_row)
        actions_lay.addWidget(self.btn_add_payment)
        actions_lay.addStretch()
        self.payment_main_layout.addLayout(actions_lay)
        
        # 4. Bank Details (Common)
        grp_bank = QGroupBox("Dane Bankowe (Dla Przelewów)")
        form_bank = QFormLayout()
        
        self.bank_account = QLineEdit()
        self.bank_account.setPlaceholderText("XX XXXX ...")
        self.bank_account.setMaxLength(40)
        self.bank_account.textEdited.connect(self.format_bank_account)
        
        self.swift_field = QLineEdit()
        self.bank_name_field = QLineEdit()
        
        form_bank.addRow("Numer konta:", self.bank_account)
        form_bank.addRow("Kod SWIFT:", self.swift_field)
        form_bank.addRow("Nazwa Banku:", self.bank_name_field)
        
        grp_bank.setLayout(form_bank)
        self.payment_main_layout.addWidget(grp_bank)
        
        # 5. Status Fields (Paid/Date) - Simplification:
        # We derive "Paid" status from the payment methods implicitly or allow manual override
        manual_grp = QGroupBox("Status Rozliczenia")
        man_lay = QHBoxLayout()
        self.is_paid = QCheckBox("Oznacz fakturę jako w pełni zapłaconą")
        self.is_paid.setTristate(False) # Force 2 states
        self.is_paid.setToolTip("Zaznacz, jeśli faktura jest już opłacona (np. gotówka, przedpłata)")
        # Auto-fill logic when user checks this manually
        self.is_paid.stateChanged.connect(self.on_manual_paid_toggle)
        
        man_lay.addWidget(self.is_paid)
        man_lay.addStretch()
        manual_grp.setLayout(man_lay)
        self.payment_main_layout.addWidget(manual_grp)

        # Initialize Lists
        self.payment_rows = []
        
        # Initial Row
        # If we are loading data, we will clear this. If clean, add one default.
        # FIX: For duplication, we also want to start clear and let load_data fill it, 
        # to avoid adding and then immediately deleting a row which causes artifacts.
        if not self.invoice_id and not self.duplicated_invoice_id:
             self.add_payment_row(method="Przelew", amount=0.0)

    def add_payment_row(self, method="Przelew", amount=None):
        # Remove stretch if exists (to add before it)
        # Actually QVBoxLayout adds to end, stretch is at end.
        # We need to insert before stretch? Layout items handling is tricky.
        # Simplest: remove all widgets, rebuild list? No, performance.
        # Our layout has addStretch() called once. 
        # count() includes stretch. 
        
        row = PaymentRowWidget(self.scroll_content, remove_callback=self.remove_payment_row)
        
        # Set Method
        if method: 
            row.method_combo.setCurrentText(method)
            
        # Set Amount
        # If amount provided, set it.
        # If not, calculate remaining.
        if amount is not None:
             row.amount_edit.setText(f"{amount:.2f}")
        else:
             rem = self.get_remaining_amount()
             row.amount_edit.setText(f"{max(0, rem):.2f}")
        
        # Set Date logic: if Transfer -> +7 days (default), if Cash -> Today
        if method in ["Przelew", "Kredyt"]:
             curr_dl = self.payment_rows[0].date_edit.date() if self.payment_rows else QDate.currentDate().addDays(7)
             row.date_edit.setDate(curr_dl)
        else:
             row.date_edit.setDate(QDate.currentDate())
             
        # Connect signals
        # Używamy lambda, aby przekazać 'row' do handlera edycji
        row.amount_edit.textEdited.connect(lambda txt: self.on_amount_edited(row))
        # editingFinished służy do aktualizacji sum, ale my chcemy reagować na edycję tekstu (znikający checkbox)
        row.amount_edit.editingFinished.connect(self.update_payment_totals_ui)
        
        row.percent_cb.stateChanged.connect(lambda s: self.on_row_percent_changed(row, s))
        row.method_combo.currentTextChanged.connect(lambda txt: self.on_payment_method_changed(row, txt))
        
        # Insert before stretch (idx = count - 1)
        cnt = self.payment_rows_layout.count()
        self.payment_rows_layout.insertWidget(cnt - 1, row)
        
        self.payment_rows.append(row)
        
        # First row cannot be deleted usually? Let's allow deleting any, 
        # but if 0 left, add one default?
        self.update_row_delete_buttons()
        self.update_payment_totals_ui()
        
    def on_payment_method_changed(self, row, method_text):
        # Update date default based on method
        if method_text in ["Przelew", "Kredyt"]:
            row.date_edit.setDate(QDate.currentDate().addDays(7))
        else:
            row.date_edit.setDate(QDate.currentDate())
        self.update_payment_totals_ui()

    def remove_payment_row(self, row_widget):
        if len(self.payment_rows) <= 1:
             return
             
        self.payment_rows.remove(row_widget)
        self.payment_rows_layout.removeWidget(row_widget)
        row_widget.deleteLater()
        
        self.update_row_delete_buttons()
        self.update_payment_totals_ui()

    def update_row_delete_buttons(self):
        can_delete = len(self.payment_rows) > 1
        for r in self.payment_rows:
             r.remove_btn.setVisible(can_delete)

    def get_remaining_amount(self):
         total = getattr(self, '_current_total_gross', 0.0)
         entered = 0.0
         for r in self.payment_rows:
              try:
                   entered += float(r.amount_edit.text().replace(',', '.') or 0)
              except: pass
         return total - entered

    def on_row_percent_changed(self, row, state):
        """
        Logika dwukierunkowa:
        - Zaznaczenie (%): Przelicz bieżącą KWOTĘ na PROCENT sumy brutto.
        - Odznaczenie (Kwota): Przelicz bieżący PROCENT na KWOTĘ.
        """
        try:
             total_gross = getattr(self, '_current_total_gross', 0.0)
             if total_gross == 0:
                  # Bez sumy nie możemy przeliczać relacji
                  return

             txt = row.amount_edit.text().replace(',', '.').replace('%', '').strip()
             if not txt: return
             val = float(txt)

             if state == 2: # Checked -> Przejście na PROCENTY
                  # Użytkownik miał wpisaną kwotę (np. 100), chce zobaczyć ile to % całości (np. przy sumie 1000 -> 10%)
                  
                  # Ale uwaga: jeśli użytkownik wpisał "50" z myślą o procencie i DOPIERO klika checkbox?
                  # To jest dylemat. "Nie pojawia się przeliczenie kwoty jaka była na procent i odwrotnie".
                  # Brzmi jakby chciał widzieć konwersję.
                  # Scenariusz A: Wpisuje kwotę zaliczki 500 zł. Klika %. Zmienia się na "25 %".
                  # Scenariusz B: Chce wpisać 50%. Wpisuje "50". Klika %. Zmienia się na "2.5 %" (bo 50 zł to 2.5% z 2000). To źle.
                  
                  # Rozwiązanie: Jeśli wartość jest mała (< 100?) i wygląda na procent, to może to procent?
                  # Nie, lepiej trzymać się sztywnej logiki konwersji wartości.
                  # Jeśli użytkownik chce wpisać "50%", powinien:
                  # 1. Kliknąć % (puste pole -> 0%).
                  # 2. Wpisać 50.
                  
                  # Jeśli jednak pole nie jest puste:
                  pct_val = (val / total_gross) * 100.0
                  # Formatuj ładnie
                  row.amount_edit.blockSignals(True)
                  row.amount_edit.setText(f"{pct_val:.2f}")
                  row.amount_edit.blockSignals(False)
                  # Dodaj tooltip lub placeholder? QLineEdit nie ma suffixu prosto.
             
             else: # Unchecked (0) -> Przejście na KWOTY
                  # Użytkownik miał wpisany procent (np. 50), chce wrócić do kwoty.
                  # val to teraz procent.
                  amount_val = total_gross * (val / 100.0)
                  
                  row.amount_edit.blockSignals(True)
                  row.amount_edit.setText(f"{amount_val:.2f}")
                  row.amount_edit.blockSignals(False)
                  
                  self.update_payment_totals_ui()

        except Exception as e: 
             print(f"Percent conversion error: {e}")
             # W razie błędu po prostu odznacz (bezpiecznik)
             if state == 2:
                  row.percent_cb.setChecked(False)

    def on_amount_edited(self, row):
        # Aktualizacja sum przy każdej edycji tekstu.
        # Checkbox % (jeśli zaznaczony) jest brany pod uwagę w update_payment_totals_ui.
        self.update_payment_totals_ui()

    def update_payment_totals_ui(self):
        total = getattr(self, '_current_total_gross', 0.0)
        entered = 0.0
        immediate_paid = 0.0
        
        for r in self.payment_rows:
             try:
                  t = r.amount_edit.text().replace(',', '.').replace('%','').strip()
                  v = float(t or 0)
                  
                  # Jeśli wiersz ma zaznaczony %, to traktuj v jako Procent z Sumy
                  # (czyli v to np. 50 (%), a wartość: total * 0.5)
                  if r.percent_cb.isChecked() and total > 0:
                       # Obliczamy wartość w zł z procentu
                       amount_pln = total * (v / 100.0)
                       v = amount_pln
                  
                  entered += v
                  
                  # Check method type
                  m = r.method_combo.currentText().lower()
                  # Methods considered "Paid" immediately
                  if any(x in m for x in ['gotówka', 'karta', 'blik', 'mobilna', 'bon', 'kompensata']):
                       immediate_paid += v
             except: pass
         
        to_pay = max(0.0, total - entered)
        
        # Jeśli różnica minimalna (rounding error), to 0
        if abs(to_pay) < 0.02: to_pay = 0.0
        
        # Auto-update status checkbox only if we have full payment via instant methods
        # (user can override manually)
        is_fully_paid = False
        if abs(immediate_paid - total) < 0.05 and total > 0:
             is_fully_paid = True
             
        # New Labels Logic:
        # 1. Total Gross (renamed to Kwota faktury as requested)
        self.lbl_pay_total.setText(f"Kwota faktury: {total:.2f} {self.currency_label.text() if hasattr(self, 'currency_label') else 'PLN'}")
        
        # 2. Entered Amount + Percentage
        pct = 0.0
        if total > 0:
             pct = (entered / total) * 100.0
        self.lbl_pay_entered.setText(f"Rozpisano: {entered:.2f} ({pct:.1f}%)")
        
        # 3. Remaining
        # If entered > total -> Overpayment? Or handle it.
        # "czy jest pokrycie wartości pozycji płatności" -> if remaining <= 0 (or close to 0) -> Green/OK
        rem = total - entered
        rem_display = max(0.0, rem) # Or show negative if overpaid? Let's show signed maybe?
        # User said "czy jest pokrycie". If rem <= 0.01 it is covered.
        
        if rem > 0.01:
             self.lbl_pay_remaining.setText(f"Pozostało: {rem:.2f}")
             self.lbl_pay_remaining.setStyleSheet("color: red; font-weight: bold;")
        elif rem < -0.01:
             self.lbl_pay_remaining.setText(f"Nadpłata: {abs(rem):.2f}")
             self.lbl_pay_remaining.setStyleSheet("color: blue; font-weight: bold;")
        else:
             self.lbl_pay_remaining.setText("Pokryto całość (0.00)")
             self.lbl_pay_remaining.setStyleSheet("color: green; font-weight: bold;")

        # Don't auto-uncheck manual paid checkbox if already checked
        # But if we detect full instant payment, we can suggest it.
        # Let's be passive: only update if not checked?
        # Or respect manual override.
        if not self.is_paid.isChecked() and is_fully_paid:
             self.is_paid.blockSignals(True)
             self.is_paid.setChecked(True)
             self.is_paid.blockSignals(False)
             
    def get_remaining_amount(self):
         total = getattr(self, '_current_total_gross', 0.0)
         entered = 0.0
         for r in self.payment_rows:
              try:
                   t = r.amount_edit.text().replace(',', '.').replace('%','').strip()
                   v = float(t or 0)
                   
                   if r.percent_cb.isChecked() and total > 0:
                        v = total * (v / 100.0)
                        
                   entered += v
              except: pass
         return total - entered

    def _replace_me_legacy_init_payment(self):
         # Legacy holder if needed
         pass

    def init_ksef_tab(self):
        # Scrollable area might be better here due to many fields, but stick to VBox for now
        layout = QVBoxLayout(self.tab_ksef)
        
        top_lay = QHBoxLayout()
        
        # Col 1: Checks
        grp_checks = QGroupBox("Adnotacje / Oznaczenia")
        lay_checks = QVBoxLayout()
        
        self.chk_mpp = QCheckBox("MPP (Podzielona płatność)")
        self.chk_cash = QCheckBox("Metoda Kasowa")
        # Hidden as requested
        # self.chk_fp = QCheckBox("FP (Faktura do paragonu)")
        # self.chk_tp = QCheckBox("TP (Podmioty powiązane)")
        self.chk_reverse = QCheckBox("Odwrotne obciążenie")
        # self.chk_wdt_new = QCheckBox("WDT Nowych środków transportu")
        # self.chk_excise = QCheckBox("Zwrot akcyzy")
        self.chk_margin = QCheckBox("Procedura Marży")
        self.chk_zw = QCheckBox("Zwolnienie z VAT (P_19)")

        # Logic: If entity is NOT VAT Payer, force check and disable
        if self.config:
             # Metoda Kasowa Default
             if getattr(self.config, 'is_cash_method', False) and self.category == InvoiceCategory.SALES:
                  self.chk_cash.setChecked(True)
             
             # Constraints for Cash Method
             # Available only for Active VAT Payer AND Not Ryczalt
             is_ryczalt = (self.config.taxation_form == TaxationForm.RYCZALT) if hasattr(self.config, 'taxation_form') else False
             if not self.config.is_vat_payer or is_ryczalt:
                  self.chk_cash.setChecked(False)
                  self.chk_cash.setEnabled(False) 

             # Constraints for ZW
             if not self.config.is_vat_payer:
                self.chk_zw.setChecked(True)
                self.chk_zw.setEnabled(False) # Locked
        elif self.is_exempt_mode:
            self.chk_zw.setChecked(True)
        
        # Signals
        self.chk_margin.stateChanged.connect(self.toggle_margin_fields)
        self.chk_zw.stateChanged.connect(self.toggle_exemption_fields)
        self.chk_reverse.stateChanged.connect(self.toggle_reverse_charge_fields)
        self.chk_cash.stateChanged.connect(self.toggle_cash_fields)

        for chk in [self.chk_mpp, self.chk_cash, 
                    self.chk_reverse, self.chk_margin, self.chk_zw]:
            lay_checks.addWidget(chk)
            
        grp_checks.setLayout(lay_checks)
        top_lay.addWidget(grp_checks)
        
        # Col 2: Details for Checks
        grp_details = QGroupBox("Szczegóły Oznaczeń")
        self.lay_details = QFormLayout()
        
        # Exemption Logic
        self.exemption_type = QComboBox()
        self.exemption_type.addItem("", "")
        self.exemption_type.addItem("Przepis ustawy albo aktu wydanego na podstawie ustawy, na podstawie którego podatnik stosuje zwolnienie od podatku", "USTAWA")
        self.exemption_type.addItem("Przepis dyrektywy 2006/112/WE, który zwalnia od podatku taką dostawę towarów lub takie świadczenie usług", "DYREKTYWA")
        self.exemption_type.addItem("Inna podstawa prawna wskazująca na to, że dostawa towarów lub świadczenie usług korzysta ze zwolnienia", "INNE")
        
        self.exemption_desc = QLineEdit()
        self.exemption_desc.setPlaceholderText("Podstawa prawna (Art / Przepis)")
        
        # Pre-fill from Company Config if Sales Invoice
        if self.category == InvoiceCategory.SALES and self.config:
            if self.config.vat_exemption_basis_type:
                idx = self.exemption_type.findData(self.config.vat_exemption_basis_type)
                if idx >= 0: self.exemption_type.setCurrentIndex(idx)
            if self.config.vat_exemption_basis:
                self.exemption_desc.setText(self.config.vat_exemption_basis)
        
        # Margin Procedure
        self.margin_type = QComboBox()
        self.margin_type.addItem("", "")
        self.margin_type.addItem("towary używane", "UZYWANE")
        self.margin_type.addItem("dzieła sztuki", "DZIELA")
        self.margin_type.addItem("przedmioty kolekcjonerskie i antyki", "ANTYKI")
        self.margin_type.addItem("biura podróży", "TURYSTYKA")
        
        self.lbl_zw_header = QLabel("<b>Dla Zwolnienia z VAT:</b>")
        self.lbl_zw_type = QLabel("Podstawa (Typ):")
        self.lbl_zw_desc = QLabel("Przepis:")
        
        self.lay_details.addRow(self.lbl_zw_header)
        self.lay_details.addRow(self.lbl_zw_type, self.exemption_type)
        self.lay_details.addRow(self.lbl_zw_desc, self.exemption_desc)
        
        self.lbl_margin_header = QLabel("<b>Dla Marży:</b>")
        self.lbl_margin_type = QLabel("Typ procedury:")
        
        self.lay_details.addRow(self.lbl_margin_header)
        self.lay_details.addRow(self.lbl_margin_type, self.margin_type)
        
        grp_details.setLayout(self.lay_details)
        top_lay.addWidget(grp_details)
        
        layout.addLayout(top_lay)
        
        # Transaction Terms
        grp_trans = QGroupBox("Warunki Transakcji (Umowa / Zamówienie)")
        lay_trans = QGridLayout()
        
        # Order inputs
        self.chk_has_order = QCheckBox("Zamówienie")
        self.chk_has_order.stateChanged.connect(self.toggle_order_fields)
        self.order_num = QLineEdit()
        self.order_num.setPlaceholderText("Numer zamówienia")
        self.order_date = QDateEdit() 
        self.order_date.setDate(QDate.currentDate())
        self.order_date.setCalendarPopup(True)
        
        lay_trans.addWidget(self.chk_has_order, 0, 0)
        lay_trans.addWidget(QLabel("Nr:"), 0, 1)
        lay_trans.addWidget(self.order_num, 0, 2)
        lay_trans.addWidget(QLabel("Data:"), 0, 3)
        lay_trans.addWidget(self.order_date, 0, 4)

        # Contract inputs
        self.chk_has_contract = QCheckBox("Umowa")
        self.chk_has_contract.stateChanged.connect(self.toggle_contract_fields)
        self.contract_num = QLineEdit()
        self.contract_num.setPlaceholderText("Numer umowy")
        self.contract_date = QDateEdit()
        self.contract_date.setDate(QDate.currentDate())
        self.contract_date.setCalendarPopup(True)
        
        lay_trans.addWidget(self.chk_has_contract, 1, 0)
        lay_trans.addWidget(QLabel("Nr:"), 1, 1)
        lay_trans.addWidget(self.contract_num, 1, 2)
        lay_trans.addWidget(QLabel("Data:"), 1, 3)
        lay_trans.addWidget(self.contract_date, 1, 4)
        
        grp_trans.setLayout(lay_trans)
        layout.addWidget(grp_trans)
        
        # Registers
        grp_reg = QGroupBox("Rejestry (Informacyjnie)")
        lay_reg = QHBoxLayout()
        # TODO: Load from Config
        self.reg_bdo = QLineEdit()
        self.reg_bdo.setPlaceholderText("BDO")
        self.reg_krs = QLineEdit()
        self.reg_krs.setPlaceholderText("KRS")
        lay_reg.addWidget(QLabel("BDO:"))
        lay_reg.addWidget(self.reg_bdo)
        lay_reg.addWidget(QLabel("KRS:"))
        lay_reg.addWidget(self.reg_krs)
        
        grp_reg.setLayout(lay_reg)
        layout.addWidget(grp_reg)
        
        layout.addStretch()
        
        # Initialize Visibility
        self.toggle_margin_fields()
        self.toggle_exemption_fields()
        self.toggle_reverse_charge_fields()
        self.toggle_cash_fields()  # Init Cash fields state
        self.toggle_order_fields()
        self.toggle_contract_fields()

    def toggle_cash_fields(self, state=0):
        is_cash = self.chk_cash.isChecked()
        if is_cash:
             # Disable incompatible options (margin, ZW)
             # User Request: MPP + Cash is allowed. 
             # Margin + Cash is allowed (e.g. Small Taxpayer selling used car).
             
             if self.chk_zw.isChecked(): self.chk_zw.setChecked(False)
             self.chk_zw.setEnabled(False)
        else:
             # Restore options ONLY if not blocked by other flags (like Reverse Charge)
             if not self.chk_reverse.isChecked():
                 # Restore ZW - Respect is_vat_payer config
                 is_vat_payer = True
                 if self.config:
                     if hasattr(self.config, 'is_vat_payer'):
                         is_vat_payer = self.config.is_vat_payer
                     elif hasattr(self.config, 'default_tax_system') and self.config.default_tax_system == TaxSystem.ZWOLNIONY:
                         is_vat_payer = False
                 
                 if not is_vat_payer:
                      self.chk_zw.setChecked(True)
                      self.chk_zw.setEnabled(False)
                 else:
                      self.chk_zw.setEnabled(True)

    def toggle_margin_fields(self, state=0):
        visible = self.chk_margin.isChecked()
        self.lbl_margin_header.setVisible(visible)
        self.lbl_margin_type.setVisible(visible)
        self.margin_type.setVisible(visible)
        if not visible:
             self.margin_type.setCurrentIndex(0)

    def toggle_reverse_charge_fields(self, state=0):
        is_acc = self.chk_reverse.isChecked()
        if is_acc:
             # Disable incompatible options
             if self.chk_margin.isChecked(): self.chk_margin.setChecked(False)
             self.chk_margin.setEnabled(False)
             
             if self.chk_zw.isChecked(): self.chk_zw.setChecked(False)
             self.chk_zw.setEnabled(False)
             
             # Metoda Kasowa is ALLOWED with Reverse Charge
             # Do not disable chk_cash
        else:
             # Check if blocked by Cash Method
             if self.chk_cash.isChecked():
                 return

             # Restore options
             self.chk_margin.setEnabled(True)
             
             # Restore ZW - Respect is_vat_payer config
             is_vat_payer = True
             if self.config:
                 if hasattr(self.config, 'is_vat_payer'):
                     is_vat_payer = self.config.is_vat_payer
                 elif hasattr(self.config, 'default_tax_system') and self.config.default_tax_system == TaxSystem.ZWOLNIONY:
                     is_vat_payer = False
             
             if not is_vat_payer:
                  self.chk_zw.setChecked(True)
                  self.chk_zw.setEnabled(False)
             else:
                  self.chk_zw.setEnabled(True)

    def toggle_exemption_fields(self, state=0):
        visible = self.chk_zw.isChecked()
        self.lbl_zw_header.setVisible(visible)
        self.lbl_zw_type.setVisible(visible)
        self.exemption_type.setVisible(visible)
        self.lbl_zw_desc.setVisible(visible)
        self.exemption_desc.setVisible(visible)
        
        # If Config enforces VAT Exemption, lock edits and load from config
        if self.config and not self.config.is_vat_payer and visible:
            self.exemption_type.setEnabled(False)
            self.exemption_desc.setReadOnly(True)
            # Load config values if empty (or always overwrite?) 
            # "nie można zmienić powiązanych informacji w szczegółach - to jedynie z konfiguracji podmiotu"
            if self.config.vat_exemption_basis_type:
                # Find matching data
                idx = self.exemption_type.findData(self.config.vat_exemption_basis_type)
                if idx >= 0: self.exemption_type.setCurrentIndex(idx)
            self.exemption_desc.setText(self.config.vat_exemption_basis or "")
        else:
             self.exemption_type.setEnabled(True)
             self.exemption_desc.setReadOnly(False)

        if not visible:
            self.exemption_type.setCurrentIndex(0)
            self.exemption_desc.clear()

    def toggle_order_fields(self):
        enabled = self.chk_has_order.isChecked()
        self.order_num.setEnabled(enabled)
        self.order_date.setEnabled(enabled)
        if not enabled:
            self.order_num.clear()

    def toggle_contract_fields(self):
        enabled = self.chk_has_contract.isChecked()
        self.contract_num.setEnabled(enabled)
        self.contract_date.setEnabled(enabled)
        if not enabled:
            self.contract_num.clear()

    # --- Logic Helpers ---
    def _form_row(self, label, widget):
        lay = QHBoxLayout()
        lay.addWidget(QLabel(label))
        lay.addWidget(widget)
        return lay

    def update_currency_ui(self, text):
        is_foreign = (text != "PLN")
        self.lbl_rate.setVisible(is_foreign)
        self.currency_rate.setVisible(is_foreign)
        self.lbl_date_rate.setVisible(is_foreign)
        self.currency_date.setVisible(is_foreign)
        if not is_foreign:
             self.currency_rate.setText("1.0000")

    def toggle_paid_fields(self):
        # Legacy stub
        pass

    def on_manual_paid_toggle(self, state):
        if state == Qt.Checked:
             # Logic: if user checks "Paid", we assume paid amount = total gross
             # However, in current model `paid_amount` is calculated from Payment Breakdowns (gotówka, przelew etc.)
             # If no breakdowns exist, we could prompt or just set the flag.
             # But the requirement says: "przelew nastąpi w momencie wprowadzania... oznaczyć jako opłaconą... rozrachunek... rozliczony"
             # So we force update logic on save.
             pass
        
    def format_bank_account(self, text):
        if not text:
            return

        # Remove non-digits
        raw = "".join(filter(str.isdigit, text))
        
        # Limit to 26 digits
        if len(raw) > 26:
            raw = raw[:26]
            
        formatted = ""
        # XX
        if len(raw) > 0:
            formatted += raw[:2]
        # XXXX groups
        if len(raw) > 2:
            for i in range(2, len(raw), 4):
                formatted += " " + raw[i:i+4]
        
        if formatted != text:
             self.bank_account.blockSignals(True)
             self.bank_account.setText(formatted)
             self.bank_account.blockSignals(False)
             self.bank_account.setCursorPosition(len(formatted))

    def open_items_menu(self, pos):
        menu = QMenu()
        act_add = QAction("Dodaj puste", self)
        act_add.triggered.connect(self.add_item_row)
        act_sel = QAction("Wybierz z katalogu", self)
        act_sel.triggered.connect(self.open_product_selector)
        act_del = QAction("Usuń", self)
        act_del.triggered.connect(self.remove_item_row)
        
        # New: Description Action
        act_desc = QAction("Dodaj/Edytuj Opis", self)
        act_desc.triggered.connect(self.add_item_description)
        
        menu.addAction(act_sel)
        menu.addAction(act_add)
        menu.addAction(act_desc)
        menu.addAction(act_del)
        menu.exec(self.items_table.viewport().mapToGlobal(pos))


    def add_item_description(self):
        row = self.items_table.currentRow()
        if row < 0: return
        
        # Get existing meta if any
        name_item = self.items_table.item(row, 0)
        curr_key = name_item.data(Qt.UserRole + 1) or ""
        curr_val = name_item.data(Qt.UserRole + 2) or ""
        
        # Open Custom Dialog
        dlg = LargeItemDescriptionDialog(curr_key, curr_val, self)
        if dlg.exec():
            k, v = dlg.get_data()
            
            # Save meta
            name_item.setData(Qt.UserRole + 1, k)
            name_item.setData(Qt.UserRole + 2, v)
            
            # Update Visuals (Bubble Icon)
            if k or v:
                 # Helper to get icon - Correct usage of QStyle.StandardPixmap
                 icon = self.style().standardIcon(QStyle.SP_MessageBoxInformation)
                 name_item.setIcon(icon)
                 name_item.setToolTip(f"<b>{k}</b><br>{v}")
            else:
                 name_item.setIcon(QIcon())
                 name_item.setToolTip("")

    def open_product_selector(self):
        dlg = ProductSelector(self)
        if dlg.exec():
            prod = dlg.selected_product
            if prod:
                # Add row with product data
                self.add_item_row(product_data=prod)

    def add_item_row(self, product_data=None):
        row = self.items_table.rowCount()
        self.items_table.insertRow(row)
        
        # Name
        name_item = QTableWidgetItem(product_data.name if product_data else "")
        self.items_table.setItem(row, 0, name_item)
        
        # Index/GTU
        sku_val = product_data.sku if product_data and product_data.sku else ""
        self.items_table.setItem(row, 1, QTableWidgetItem(sku_val))
        
        # Unit
        unit_val = product_data.unit if product_data else "szt."
        self.items_table.setItem(row, 2, QTableWidgetItem(unit_val))
        
        # Quantity
        self.items_table.setItem(row, 3, QTableWidgetItem("1.00"))
        
        # Check current Mode (Net/Gross)
        is_gross_mode = (self.price_type_combo.currentText() == "Brutto")
        
        # VAT Combo (Col 5) - Determine first for calculation
        vat_combo = QComboBox()
        default_idx = 0
        target_rate = 0.23
        if product_data: target_rate = product_data.vat_rate
        
        if self.is_exempt_mode:
            # Find ZW
            for i, r in enumerate(self.vat_rates):
                if r.name.lower() == "zw": default_idx = i; break
        else:
            for i, r in enumerate(self.vat_rates):
                if abs(target_rate - r.rate) < 0.001:
                    default_idx = i; break

        # Filter rates for Combo (User Constraint: No OO if not VAT Payer)
        is_vat_payer = True
        if self.config:
             if hasattr(self.config, 'is_vat_payer'):
                 is_vat_payer = self.config.is_vat_payer
             elif hasattr(self.config, 'default_tax_system') and self.config.default_tax_system == TaxSystem.ZWOLNIONY:
                 is_vat_payer = False
        
        for r in self.vat_rates:
            # Check for OO / Transfer Pricing / NP
            r_name_lower = r.name.lower()
            if r_name_lower in ["oo", "np", "np.", "odwrotne obciążenie"]:
                 if not is_vat_payer:
                      continue # Block OO for non-VAT payers
            
            vat_combo.addItem(r.name, r.rate)
            
        # Select correct index after filtering
        found_idx = -1
        # default_idx relates to original full list, need to map to filtered list
        original_default_name = self.vat_rates[default_idx].name if default_idx < len(self.vat_rates) else "23%"
        
        for i in range(vat_combo.count()):
             if vat_combo.itemText(i) == original_default_name:
                  found_idx = i; break
        
        if found_idx >= 0:
             vat_combo.setCurrentIndex(found_idx)
        else:
             vat_combo.setCurrentIndex(0)
        
        # Price Calculation based on Mode
        price_val = 0.0
        if product_data:
             if is_gross_mode:
                  # Try to get gross price directly or calc
                  if getattr(product_data, 'gross_price', 0) > 0:
                       price_val = product_data.gross_price
                  else:
                       price_val = product_data.net_price * (1.0 + target_rate)
             else:
                  price_val = product_data.net_price

        self.items_table.setItem(row, 4, QTableWidgetItem(f"{price_val:.2f}"))
        
        # If exempt mode, lock VAT combo? User request: "pole zablokowane do edycji"
        if self.is_exempt_mode:
             vat_combo.setEnabled(False)
        
        vat_combo.currentIndexChanged.connect(lambda: self.recalculate_totals())
        self.items_table.setCellWidget(row, 5, vat_combo)
        
        next_col = 6
        if self.is_ryczalt_mode:
            # Ryczałt Combo
            ryc_combo = QComboBox()
            # Default from Config
            def_r_val = self.config.default_lump_sum_rate if self.config else 0.12
            def_idx = 0
            for i, r in enumerate(self.lump_sum_rates):
                ryc_combo.addItem(r.name, r.rate)
                if abs(r.rate - def_r_val) < 0.001: def_idx = i
            ryc_combo.setCurrentIndex(def_idx)
            self.items_table.setCellWidget(row, 6, ryc_combo)
            next_col = 7
            
        # Total Value (Readonly)
        val_item = QTableWidgetItem("0.00")
        val_item.setFlags(val_item.flags() ^ Qt.ItemIsEditable)
        self.items_table.setItem(row, next_col, val_item)
        
        self.recalculate_totals()

    def remove_item_row(self):
        row = self.items_table.currentRow()
        if row >=0: self.items_table.removeRow(row)
        self.recalculate_totals()

    def on_price_type_changed(self, new_mode):
        to_gross = (new_mode == "Brutto")
        
        self.items_table.blockSignals(True)
        try:
            for r in range(self.items_table.rowCount()):
                try:
                    price_item = self.items_table.item(r, 4)
                    current_price = float(price_item.text().replace(',', '.') or 0)
                    
                    vat_widget = self.items_table.cellWidget(r, 5)
                    vat_rate = vat_widget.currentData() if vat_widget else 0.0
                    
                    new_price = 0.0
                    if to_gross:
                        # Netto -> Brutto
                        new_price = current_price * (1.0 + vat_rate)
                    else:
                        # Brutto -> Netto
                        new_price = current_price / (1.0 + vat_rate) if (1.0 + vat_rate) > 0 else current_price
                    
                    price_item.setText(f"{new_price:.2f}")
                except Exception as e:
                    print(f"Błąd konwersji wiersza {r}: {e}")
        finally:
            self.items_table.blockSignals(False)
        
        self.recalculate_totals()

    def calculate_row_totals(self, item):
        self.recalculate_totals()

    def recalculate_totals(self):
        total_net = 0.0
        total_gross = 0.0
        currency = self.currency.currentText()
        is_gross_mode = (self.price_type_combo.currentText() == "Brutto")
        
        val_col_idx = 7 if self.is_ryczalt_mode else 6
        
        has_oo_item = False

        for r in range(self.items_table.rowCount()):
            try:
                def parse(t): return float(t.replace(",", ".") or 0)
                
                qty = parse(self.items_table.item(r, 3).text())
                price = parse(self.items_table.item(r, 4).text())
                
                combo_vat = self.items_table.cellWidget(r, 5)
                vat_rate = combo_vat.currentData() if combo_vat else 0.0
                vat_name = combo_vat.currentText() if combo_vat else ""
                
                if vat_name.lower() in ["oo", "np", "np.", "odwrotne obciążenie"]:
                     has_oo_item = True

                if is_gross_mode:
                    # Input Price is Gross
                    gross_line = qty * price
                    # Calc net backwards
                    net_line = gross_line / (1.0 + vat_rate)
                else:
                    # Input Price is Net
                    net_line = qty * price
                    gross_line = net_line * (1.0 + vat_rate)
                
                # Update Value Column
                # Usually we show Gross value in total
                self.items_table.item(r, val_col_idx).setText(f"{gross_line:.2f}")
                
                total_net += net_line
                total_gross += gross_line
            except: pass
            
        self.total_net_lbl.setText(f"Netto: {total_net:.2f} {currency}")
        self.total_gross_lbl.setText(f"Brutto: {total_gross:.2f} {currency}")
        
        # Auto-update Reverse Charge Flag based on items
        if hasattr(self, 'chk_reverse'):
             if has_oo_item:
                  self.chk_reverse.setChecked(True)
                  self.chk_reverse.setEnabled(False) # Locked as requested
                  
                  # Block incompatible options (Margin & Exempt)
                  if hasattr(self, 'chk_margin'):
                       self.chk_margin.setChecked(False)
                       self.chk_margin.setEnabled(False)
                  
                  if hasattr(self, 'chk_zw'):
                       self.chk_zw.setChecked(False)
                       self.chk_zw.setEnabled(False)

             else:
                  # Restore state if no OO items
                  self.chk_reverse.setEnabled(True)
                  
                  # Check current state (Manual or Remaining)
                  is_reverse_on = self.chk_reverse.isChecked()

                  if is_reverse_on:
                       # Enforce Locks if Manually ON
                       if hasattr(self, 'chk_margin'):
                            self.chk_margin.setChecked(False)
                            self.chk_margin.setEnabled(False)
                       if hasattr(self, 'chk_zw'):
                            self.chk_zw.setChecked(False)
                            self.chk_zw.setEnabled(False)
                  else:
                       # Enable Options logic handled by toggle_reverse_charge_fields usually,
                       # but here we ensure they are unlocked if not forced by item
                       # But toggle_* handles logic on signal.
                       
                       # If I just manually unchecked OO, signal fires and unlocks.
                       # If I am just calculating totals and OO is OFF, I should ensure defaults?
                       # Or just leave it to signal logic?
                       # Let's trust 'toggle_reverse_charge_fields' which is connected to StateChanged.
                       pass
                       
                  # NOTE: If we used to have OO item and just removed it, 'has_oo_item' becomes false.
                  # chk_reverse is still Checked and Disabled.
                  # We enable it.
                  # Logic: "if not self.is_correction_mode and self.chk_reverse.isChecked():"
                  # If we force Uncheck, we lose manual selection.
                  # If we don't force uncheck, user has to uncheck manually.
                  
                  # BUT: The requirement "automatycznie oznacza" implies "automatycznie odznacza" when condition gone?
                  # Not necessarily.
                  # Let's keep it manual-friendly as per last fix attempt design.
                  if not self.is_correction_mode and self.chk_reverse.isChecked() and not has_oo_item:
                        # If previously locked (disabled), we might assume it was auto-checked.
                        # But we can't easily know if it was auto or manual if both result in Checked.
                        # (We enabled it a few lines above).
                        # Let's act safe: If user removes OO item, let him decide to uncheck OO or keep it.
                        pass

        self._current_total_gross = total_gross
        if hasattr(self, 'payment_rows'):
             # If only 1 row (default), auto-update it to full amount
             if len(self.payment_rows) == 1:
                  self.payment_rows[0].amount_edit.setText(f"{total_gross:.2f}")
             self.update_payment_totals_ui()

    def load_data(self):
        if self.config:
            self.place_issue.setText(self.config.city or "")
            
            # For Sales Invoices, always try to load Company Bank Details (SWIFT, Name)
            # because they are not stored in Invoice Data, and they belong to the Seller (Us).
            if self.category == InvoiceCategory.SALES:
                 self.swift_field.setText(self.config.swift_code or "")
                 self.bank_name_field.setText(self.config.bank_name or "")
                 
            if not self.invoice_id and self.category == InvoiceCategory.SALES:
                if self.config.bank_account: 
                    self.bank_account.setText(self.config.bank_account)
                    self.format_bank_account(self.config.bank_account)
                # SWIFT/Name handled above
                
                self.reg_bdo.setText(getattr(self.config, 'bdo', '') or "")
                self.reg_krs.setText(getattr(self.config, 'krs', '') or "")

        if self.invoice_id and self.category == InvoiceCategory.SALES and not self.config.is_vat_payer:
             pass # Exempt mode logic handled in init/ui creation

        # --- LOAD INVOICE DATA (Edit or Duplicate or Correction) ---
        target_id = self.invoice_id or self.duplicated_invoice_id or self.corrected_invoice_id
        
        # If Correction Mode AND New (not editing existing draft correction), try to find if there is a newer correction in the chain.
        # User requested: "przenoś je z ostatniej faktury lub ostatniej korekty".
        if self.is_correction_mode and not self.invoice_id and target_id:
             current_id = target_id
             # Find descendants (invoices that have parent_id = current_id)
             # Basic chain search: A -> B -> C. We want C if we started at A.
             # Note: This simple loop assumes linear chain. 
             # Safety limit to avoid infinite loop if circular dependecy exists (though shouldn't).
             for _ in range(10): 
                 child = self.db.query(Invoice).filter(Invoice.parent_id == current_id).order_by(Invoice.id.desc()).first()
                 if child:
                     current_id = child.id
                 else:
                     break
            
             if current_id != target_id:
                 # We found a newer version. Switch target to load Data from it.
                 # Warn user
                 child_doc = self.db.query(Invoice).get(current_id)
                 QMessageBox.information(self, "Przekierowanie", 
                    f"Wybrany dokument posiada już korekty.\n"
                    f"System automatycznie przełączył się na ostatnią korektę w łańcuchu:\n"
                    f"Nr: {child_doc.number} z dn. {child_doc.date_issue}")
                 
                 target_id = current_id
                 self.corrected_invoice_id = current_id

        if target_id:
            inv = self.db.query(Invoice).filter(Invoice.id == target_id).first()
            if inv:
                # 0. Correction Header Info
                if self.is_correction_mode:
                     info = f"Nr: {inv.number} z dn. {inv.date_issue}"
                     if inv.ksef_number:
                          info += f" | KSeF: {inv.ksef_number}"
                     else:
                          info += " | Brak numeru KSeF (Faktura lokalna)"
                     self.parent_inv_info.setText(info)

                # 1. Number & Dates
                if self.invoice_id:
                    # Editing existing
                    self.number_edit.setText(inv.number)
                    self.date_issue.setDate(inv.date_issue)
                    self._original_date_issue = inv.date_issue # Store for auto-regen logic
                    
                    if inv.date_period_start:
                        self.rb_date_period.setChecked(True)
                        self.stack_dates.setCurrentIndex(1)
                        self.date_period_start.setDate(inv.date_period_start)
                        self.date_period_end.setDate(inv.date_period_end or inv.date_period_start)
                    else:
                        self.rb_date_std.setChecked(True)
                        self.stack_dates.setCurrentIndex(0)
                        self.date_sale.setDate(inv.date_sale)
                        
                    # Correction Fields
                    if self.is_correction_mode:
                         self.correction_reason_edit.setText(inv.correction_reason or "")
                         # Set Combo
                         idx = self.correction_type_combo.findData(inv.correction_type)
                         if idx >= 0: self.correction_type_combo.setCurrentIndex(idx)

                else:
                    # Duplicating OR Correcting (New Invoice)
                    # Keep number empty (auto-generate on save)
                    # Set dates to current
                    self.date_issue.setDate(QDate.currentDate())
                    self.rb_date_std.setChecked(True)
                    self.stack_dates.setCurrentIndex(0)
                    self.date_sale.setDate(QDate.currentDate())
                    
                    if self.is_correction_mode:
                        # For correction, date of sale usually matches correction date OR remains original?
                        # Usually it is the date of the event causing correction. Default to Today.
                        pass

                self.place_issue.setText(inv.place_of_issue or "")
                
                # 2. Contractor (Copy from original)
                if inv.contractor:
                    self.set_contractor(inv.contractor)
                
                # 3. Payment
                self.payment_rows = []
                while self.payment_rows_layout.count() > 1: 
                     item = self.payment_rows_layout.takeAt(0)
                     w = item.widget()
                     if w: w.deleteLater()
                
                # Load Splits logic
                if "mieszana" in (inv.payment_method or "").lower() and inv.payment_breakdowns:
                    for pb in inv.payment_breakdowns:
                        # For Correction: Do we copy payments?
                        # Usually correction has its own payment logic (e.g. refund or surcharge).
                        # Let's copy structure but maybe reset amounts? 
                        # User usually wants to see previous state to adjust. 
                        # Actually standard practice: Copy everything 1:1, user edits.
                        
                        # Correct logic: Corrections shouldn't auto-fill payments from original because usually they are UNPAID or REFUNDED differently.
                        # We skip copying payments for corrections, or add empty one.
                        if not self.is_correction_mode:
                            self.add_payment_row(method=pb.payment_method, amount=pb.amount)
                        
                        if not self.is_correction_mode and self.payment_rows:
                            r_w = self.payment_rows[-1]
                            if self.invoice_id:
                                if pb.payment_method in ["Przelew", "Kredyt"] and inv.payment_deadline:
                                     r_w.date_edit.setDate(inv.payment_deadline)
                                elif inv.date_issue:
                                     r_w.date_edit.setDate(inv.date_issue)
                            else:
                                r_w.date_edit.setDate(QDate.currentDate())
                             
                else:
                    # Single Method
                    if not self.is_correction_mode:
                        self.add_payment_row(method=inv.payment_method, amount=inv.total_gross)
                    
                    if not self.is_correction_mode and len(self.payment_rows) > 0:
                         r_w = self.payment_rows[0]
                         if self.invoice_id and inv.payment_deadline:
                              r_w.date_edit.setDate(inv.payment_deadline)
                         else:
                              r_w.date_edit.setDate(QDate.currentDate()) # Default to today
                
                # If correction mode NEW, add empty payment row
                if self.is_correction_mode and not self.invoice_id:
                     self.add_payment_row(method="Przelew", amount=0.0)

                if inv.bank_account_number: self.bank_account.setText(inv.bank_account_number)

                # 4. Price Type & Notes
                if inv.price_type == "GROSS":
                    self.price_type_combo.setCurrentText("Brutto")
                else:
                    self.price_type_combo.setCurrentText("Netto")
                
                if inv.notes:
                    self.notes_edit.setPlainText(inv.notes)

                # 5. Items (Load from original)


                for item in inv.items:
                    # How to pass data to add_item_row?
                    # We have to fill manually after adding
                    self.add_item_row(None) 
                    r = self.items_table.rowCount() - 1
                    self.items_table.item(r, 0).setText(item.product_name)
                    self.items_table.item(r, 1).setText(item.sku or "")
                    self.items_table.item(r, 2).setText(item.unit)
                    
                    # Correction Logic: Copy quantity 1:1 from source (Latest State)
                    # User requested to avoid zeroing out to match "Status Quo" logic.
                    self.items_table.item(r, 3).setText(f"{item.quantity}")
                    
                    price_val = item.net_price if inv.price_type != "GROSS" else item.gross_value/item.quantity if item.quantity else 0
                    self.items_table.item(r, 4).setText(f"{price_val:.2f}") 
                    
                    # Set VAT
                    v_combo = self.items_table.cellWidget(r, 5)
                    v_found = False
                    # 1. Try Match by Name (Preferred for ZW vs 0%)
                    if getattr(item, 'vat_rate_name', None):
                         idx = v_combo.findText(item.vat_rate_name)
                         if idx >= 0:
                              v_combo.setCurrentIndex(idx)
                              v_found = True
                    
                    # 2. Fallback by Value
                    if not v_found:
                        for i in range(v_combo.count()):
                            if abs(v_combo.itemData(i) - item.vat_rate) < 0.001:
                                v_combo.setCurrentIndex(i); break
                    # Set Ryczałt if mode
                    if self.is_ryczalt_mode and item.lump_sum_rate is not None:
                        r_combo = self.items_table.cellWidget(r, 6)
                        for i in range(r_combo.count()):
                            if abs(r_combo.itemData(i) - item.lump_sum_rate) < 0.001:
                                r_combo.setCurrentIndex(i); break
                    
                    # Notes/Description for Item
                    desc_k = getattr(item, 'description_key', None) or ""
                    desc_v = getattr(item, 'description_value', None) or ""
                    
                    if desc_k or desc_v:
                        name_item = self.items_table.item(r, 0)
                        name_item.setData(Qt.UserRole + 1, desc_k)
                        name_item.setData(Qt.UserRole + 2, desc_v)
                        name_item.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxInformation))
                        name_item.setToolTip(f"<b>{desc_k}</b><br>{desc_v}")

                # Notes (Invoice)
                self.notes_edit.setText(inv.notes or "")

                # KSeF / Annotations
                if inv.exemption_basis_type: self.exemption_type.setCurrentText(inv.exemption_basis_type)
                if inv.exemption_basis: self.exemption_desc.setText(inv.exemption_basis)
                if inv.margin_procedure_type:
                    self.chk_margin.setChecked(True)
                    self.margin_type.setCurrentText(inv.margin_procedure_type)
                
                self.chk_mpp.setChecked(inv.is_split_payment)
                self.chk_cash.setChecked(inv.is_cash_accounting)
                # self.chk_fp.setChecked(inv.is_fp) # Hidden
                # if hasattr(inv, 'is_tp'): self.chk_tp.setChecked(inv.is_tp)
                if hasattr(inv, 'is_reverse_charge'): self.chk_reverse.setChecked(inv.is_reverse_charge)
                if hasattr(inv, 'is_exempt'): self.chk_zw.setChecked(inv.is_exempt)
                # if hasattr(inv, 'is_new_transport_intra'): self.chk_wdt_new.setChecked(inv.is_new_transport_intra)
                # if hasattr(inv, 'excise_duty_refund'): self.chk_excise.setChecked(inv.excise_duty_refund)
                
                # Transaction Terms
                self.order_num.setText(inv.transaction_order_number or "")
                if inv.transaction_order_date: self.order_date.setDate(inv.transaction_order_date)
                self.contract_num.setText(inv.transaction_contract_number or "")
                if inv.transaction_contract_date: self.contract_date.setDate(inv.transaction_contract_date)
                
                self.recalculate_totals()



    def on_date_changed(self, new_date):
        """Auto-regenerate number if date changes significantly."""
        if self.category != InvoiceCategory.SALES:
             return
        
        # Determine if we should trigger regeneration
        should_regen = False
        
        if not self.invoice_id:
             # New Invoice: Always sync number with date
             should_regen = True
        elif hasattr(self, '_original_date_issue'):
             # Existing Invoice
             orig = self._original_date_issue
             curr = new_date.toPython()
             
             # If period changed (Month/Year), definitely regen
             if orig.year != curr.year or orig.month != curr.month:
                  should_regen = True
             # If we returned to the original period, also regen (to restore original number)
             elif orig.year == curr.year and orig.month == curr.month:
                  # Only if the number is currently different? 
                  # Safe to just call it, logic inside handles restoration.
                  should_regen = True
                  
        if should_regen:
             self.regenerate_number(silent=True)

    def regenerate_number(self, silent=False):
         from logic.numbering_service import NumberingService
         from database.models import NumberingSetting, PeriodType, Invoice
         
         svc = NumberingService(self.db)
         
         intended_type = InvoiceType.VAT
         if self.is_correction_mode: intended_type = InvoiceType.KOREKTA
         elif self.is_ryczalt_mode: intended_type = InvoiceType.RYCZALT
         
         lookup_type = intended_type
         if intended_type == InvoiceType.RYCZALT: lookup_type = InvoiceType.VAT # Share config
         
         setting = self.db.query(NumberingSetting).filter(
            NumberingSetting.invoice_category == self.category,
            NumberingSetting.invoice_type == lookup_type
         ).first()
         
         if not setting:
              print("[INFO] Creating default settings for regen")
              setting = svc.get_or_create_config(self.category, lookup_type)
         
         # Logic based on current Date Issue
         tgt_date = self.date_issue.date().toPython()
         
         # Smart Logic: Restore Original Number if we are back in the original period (for existing invoices)
         is_restore = False
         next_num = 1
         fmt = ""
         
         if self.invoice_id and hasattr(self, '_original_date_issue'):
             orig = self._original_date_issue
             # Check if we match the original period
             # (Simplified check: Month & Year match means same period for most standard numberings)
             if orig.year == tgt_date.year and orig.month == tgt_date.month:
                  orig_inv = self.db.query(Invoice).get(self.invoice_id)
                  if orig_inv:
                       next_num = orig_inv.sequence_number
                       fmt = orig_inv.number
                       is_restore = True
         
         if not is_restore:
              next_num = svc.find_potential_number(setting, tgt_date)
              fmt = svc.format_number(setting, next_num, tgt_date)
         
         self.number_edit.setText(fmt)
         
         # Store for Save logic
         self._pending_sequence_data = {
              'number': fmt,
              'sequence_number': next_num,
              'sequence_year': tgt_date.year,
              'sequence_month': tgt_date.month if setting.period_type == PeriodType.MONTHLY else None
         }
         
         # Only show popup if manual (not silent)
         # Note: 'silent' might be a boolean from 'clicked' signal (False), so we treat False as Not Silent.
         if silent is not True:
             msg = f"Przywrócono numer: {fmt}" if is_restore else f"Wygenerowano nowy numer: {fmt}"
             msg += "\nZapisz fakturę aby zatwierdzić."
             QMessageBox.information(self, "Numeracja", msg)

    def save_invoice(self):
        # Validation: Purchase must have a number
        if self.category == InvoiceCategory.PURCHASE:
             if not self.number_edit.text().strip():
                  QMessageBox.warning(self, "Brak Numeru", "Dla faktur zakupu wymagane jest podanie numeru dokumentu (Oryginalny numer faktury).")
                  self.number_edit.setFocus()
                  return

        # Calculate Totals First (needed for Percent Logic in Payment Rows)
        calc_gross_fresh = 0.0
        is_gross_mode = (self.price_type_combo.currentText() == "Brutto")
        for r in range(self.items_table.rowCount()):
             try:
                 def parse(t): return float(t.replace(",", ".") or 0)
                 # Check if item exists
                 if not self.items_table.item(r, 3) or not self.items_table.item(r, 4): continue
                 
                 qty = parse(self.items_table.item(r, 3).text())
                 price = parse(self.items_table.item(r, 4).text())
                 vat_rate_w = self.items_table.cellWidget(r, 5)
                 vat_rate = vat_rate_w.currentData() if vat_rate_w else 0.0
                 if is_gross_mode:
                    lg = qty * price
                 else:
                    lg = (qty * price) * (1.0 + vat_rate)
                 calc_gross_fresh += lg
             except: pass
        
        # Gather payment data
        rows_data = []
        rows_sum = 0.0
        for r in self.payment_rows:
             try:
                  txt = r.amount_edit.text().replace(',', '.').replace('%', '').strip()
                  amt = float(txt or 0)
                  
                  # Conversion if Percent Checkbox
                  if r.percent_cb.isChecked() and calc_gross_fresh > 0:
                       amt = calc_gross_fresh * (amt / 100.0)
                  
                  rows_sum += amt
                  rows_data.append({
                       'method': r.method_combo.currentText(),
                       'amount': amt,
                       'date': r.date_edit.date().toPython()
                  })
             except: pass

        # Validate Totals if multiple rows or mismatch
        if abs(rows_sum - calc_gross_fresh) > 0.05:
                  QMessageBox.warning(self, "Błąd kwoty", 
                                      f"Suma płatności ({rows_sum:.2f}) nie zgadza się z wartością brutto faktury ({calc_gross_fresh:.2f}).\n"
                                      f"Różnica: {rows_sum - calc_gross_fresh:.2f}.\n\n"
                                      "Proszę poprawić kwoty w zakładce Płatności.")
                  return
        
        # VALIDATION: Reverse Charge (OO) Logic
        if self.chk_reverse.isChecked():
             # 1. Require NIP for Buyer (Contractor)
             if not self.selected_contractor or not self.selected_contractor.nip:
                  QMessageBox.warning(self, "Błąd Odwrotnego Obciążenia", 
                                      "Dla faktur z odwrotnym obciążeniem wymagany jest NIP nabywcy (transakcja B2B).\n"
                                      "Wybierz kontrahenta z NIP lub uzupełnij dane.")
                  return
             
             # 2. Check for VAT > 0 on OO items
             # (Actually we should check if ANY item is OO, and if that specific item has VAT > 0)
             # But usually global Flag implies stricter rules.
             # Ideally: Items marked as OO (rate=0/np) are fine. Items 23% are fine if Mixed?
             # User said: "Dopuść: Fakturę mieszaną (część 23% na kasowej, część OO na kasowej)."
             # User said: "Zablokuj: Naliczanie kwoty VAT (wartość > 0) dla pozycji oznaczonych jako OO."
             
             # Let's scan items.
             for r in range(self.items_table.rowCount()):
                  vat_w = self.items_table.cellWidget(r, 5)
                  if vat_w:
                       rate_name = vat_w.currentText().lower()
                       rate_val = vat_w.currentData()
                       
                       is_oo_rate = rate_name in ["oo", "np", "np.", "odwrotne obciążenie"]
                       if is_oo_rate and rate_val > 0.0:
                            QMessageBox.warning(self, "Błąd Stawki VAT", 
                                                f"Pozycja {r+1} jest oznaczona jako '{rate_name}', ale ma stawkę > 0%.\n"
                                                "Dla odwrotnego obciążenia stawka VAT musi wynosić 0.00.")
                            return

        try:
            is_new = False
            inv = None
            if self.invoice_id:
                inv = self.db.query(Invoice).filter(Invoice.id == self.invoice_id).first()
            if not inv:
                inv = Invoice()
                inv.category = self.category
                is_new = True
                
                # Determine intended type for Numbering
                intended_type = InvoiceType.VAT
                if self.is_correction_mode:
                    intended_type = InvoiceType.KOREKTA
                elif self.is_ryczalt_mode:
                    intended_type = InvoiceType.RYCZALT
                
                # Auto Number
                if self.category == InvoiceCategory.SALES and not self.number_edit.text():
                     from logic.numbering_service import NumberingService
                     from database.models import NumberingSetting
                     svc = NumberingService(self.db)
                     
                     # Force shared configuration with VAT for RYCZALT to ensure consistency
                     lookup_type = intended_type
                     if intended_type == InvoiceType.RYCZALT:
                         lookup_type = InvoiceType.VAT

                     setting = self.db.query(NumberingSetting).filter(
                        NumberingSetting.invoice_category == self.category,
                        NumberingSetting.invoice_type == lookup_type
                     ).first()
                     
                     if not setting: 
                         # Fallback or create if missing (using lookup_type)
                         setting = svc.get_or_create_config(self.category, lookup_type)
                     
                     # Check if we are correcting and config for KOREKTA is default (same logic)
                     # If intended_type is KOREKTA, get_or_create creates template "KOR/{nr}/{rok}" usually.
                     
                     next_num = svc.find_potential_number(setting, self.date_issue.date().toPython())
                     inv.number = svc.format_number(setting, next_num, self.date_issue.date().toPython())
                     
                     # Fill sequence numbers to ensure gaps are detected correctly later
                     inv.sequence_number = next_num
                     inv.sequence_year = self.date_issue.date().year()
                     # Optional: Logic for monthly
                     from database.models import PeriodType
                     if setting.period_type == PeriodType.MONTHLY:
                         inv.sequence_month = self.date_issue.date().month()
                         
                else:
                     inv.number = self.number_edit.text()
                     # If manual, we try to set at least Year/Month for filtering consistency
                     # sequence_number is tricky if we don't parse the string. 
                     # Leaving sequence_number None usually means "External Sequence" or "Manual Gap".
                     inv.sequence_year = self.date_issue.date().year()
                     inv.sequence_month = self.date_issue.date().month()
            
            # --- CORRECTION HANDLING ---
            if self.is_correction_mode:
                 if not self.correction_reason_edit.text():
                      QMessageBox.warning(self, "Błąd", "Dla faktury korygującej wymagane jest podanie przyczyny korekty.")
                      return
                      
                 inv.type = InvoiceType.KOREKTA
                 inv.parent_id = self.corrected_invoice_id
                 inv.correction_reason = self.correction_reason_edit.text()
                 inv.correction_type = self.correction_type_combo.currentData()
                 
                 # Set relation fields
                 parent_inv = self.db.query(Invoice).filter(Invoice.id == self.corrected_invoice_id).first()
                 if parent_inv:
                      inv.related_invoice_number = parent_inv.number
                      inv.related_ksef_number = parent_inv.ksef_number
            else:
                 inv.type = InvoiceType.VAT if not self.is_ryczalt_mode else InvoiceType.RYCZALT

            # Force update number from UI if allowed (Purchase / Edit mode)
            # This ensures edits to number are saved, and manual new invoices are definitely captured.
            if self.category != InvoiceCategory.SALES:
                 inv.number = self.number_edit.text()
            else:
                 # Logic for SALES (usually ReadOnly, but might be regenerated via button)
                 if hasattr(self, '_pending_sequence_data') and self._pending_sequence_data:
                      inv.number = self._pending_sequence_data['number']
                      inv.sequence_number = self._pending_sequence_data['sequence_number']
                      inv.sequence_year = self._pending_sequence_data['sequence_year']
                      inv.sequence_month = self._pending_sequence_data['sequence_month']

            # Dates
            inv.date_issue = self.date_issue.date().toPython()
            inv.place_of_issue = self.place_issue.text()
            
            if self.rb_date_period.isChecked():
                inv.date_period_start = self.date_period_start.date().toPython()
                inv.date_period_end = self.date_period_end.date().toPython()
                inv.date_sale = inv.date_period_end # Map logic
            else:
                inv.date_sale = self.date_sale.date().toPython()
                inv.date_period_start = None
                inv.date_period_end = None
            
            if self.selected_contractor:
                inv.contractor_id = self.selected_contractor.id
                # SNAPSHOT: Save current contractor state to preserve invoice integrity
                inv.buyer_snapshot = {
                    "nip": self.selected_contractor.nip,
                    "regon": self.selected_contractor.regon,
                    "name": self.selected_contractor.name,
                    "address": self.selected_contractor.address,
                    "city": self.selected_contractor.city,
                    "postal_code": self.selected_contractor.postal_code,
                    "country": self.selected_contractor.country,
                    "country_code": self.selected_contractor.country_code,
                    "is_vat_payer": self.selected_contractor.is_vat_payer,
                    "is_vat_ue": self.selected_contractor.is_vat_ue,
                    "is_person": self.selected_contractor.is_person
                }
            
            # SNAPSHOT: Seller Details
            company_config = self.db.query(CompanyConfig).first()
            if company_config:
                 inv.seller_snapshot = {
                    "nip": company_config.nip,
                    "company_name": company_config.company_name,
                    "address": company_config.address,
                    "city": company_config.city,
                    "postal_code": company_config.postal_code,
                    "country_code": company_config.country_code,
                    "bank_account": company_config.bank_account,
                    "bank_name": company_config.bank_name,
                    "krs": company_config.krs,
                    "bdo": company_config.bdo,
                    "court_info": company_config.court_info
                 }
            
            # Price Type
            price_choice = self.price_type_combo.currentText()
            inv.price_type = "GROSS" if price_choice == "Brutto" else "NET"
            
            # Payment & Bank
            # Determine Main Method
            if len(rows_data) == 1:
                 inv.payment_method = rows_data[0]['method']
            else:
                 inv.payment_method = "Mieszana (Wiele metod)"
            
            # Deadline logic: find first "Transfer" or "Credit" date
            target_deadline = None
            for r in rows_data:
                 if r['method'] in ["Przelew", "Kredyt"]:
                      target_deadline = r['date']
                      break
            if not target_deadline and rows_data: target_deadline = rows_data[0]['date']
            inv.payment_deadline = target_deadline
            
            inv.bank_account_number = self.bank_account.text()
            
            # --- Payment & Settlements Logic ---
            # Calculate paid amount from "immediate" methods
            paid_acc = 0.0
            for s in rows_data:
                  m_key = (s['method'] or "").lower()
                  # Include Prepayment (Przedpłata) if considered immediate? Usually Transfer is pending.
                  if any(k in m_key for k in ['gotówka', 'gotowka', 'karta', 'bon', 'kompensata', 'mobilna', 'blik']):
                       paid_acc += s['amount']
                 
            inv.paid_amount = paid_acc
             
            # Check if fully paid
            # If "is_paid" checkbox manually checked, trust it.
            if self.is_paid.isChecked():
                 # User explicitly set "PAID"
                 inv.is_paid = True
                 # If automatic calculation (from immediate payments) is less than total,
                 # we assume the difference was settled just now (e.g. transfer made instantly)
                 if inv.paid_amount < calc_gross_fresh: 
                     inv.paid_amount = calc_gross_fresh
                     # Set current date as payment date if not set
                     if not inv.paid_date:
                        inv.paid_date = datetime.now()
            else:
                 # User unchecked "PAID" (or didn't check it)
                 # Recalculate strictly based on immediate payment methods (Cash/Card)
                 # If it was previously marked as paid override, we revert to actual evidence
                 inv.paid_amount = paid_acc
                 inv.is_paid = (abs(paid_acc - calc_gross_fresh) < 0.05 and calc_gross_fresh > 0)
                 
                 # If not paid fully, clear paid_date if it was set to issue date
                 if not inv.is_paid and paid_acc == 0:
                      inv.paid_date = None
             
            if paid_acc > 0:
                  # Use date of first immediate payment
                  first_imm_date = None
                  for s in rows_data:
                       m_key = (s['method'] or "").lower()
                       if any(k in m_key for k in ['gotówka', 'gotowka', 'karta', 'bon', 'kompensata', 'mobilna', 'blik']):
                           first_imm_date = s['date']
                           break
                  inv.paid_date = first_imm_date or self.date_issue.date().toPython()
            else:
                  inv.paid_date = None
            
            if is_new:
                self.db.add(inv)
                # Flush to get ID if needed for breakdowns (though SQLAlchemy handles object link, better safe)
                self.db.flush() 
            else:
                # Invalidate cached KSeF XML on edit to force regeneration (and new hash)
                # Only if NOT sent (if sent, we shouldn't be here or we are corrupting history, 
                # but clearing xml allows re-send attempt if needed)
                if not inv.ksef_number:
                     inv.ksef_xml = None 

            # Save Payment Splits ALWAYS (map to payment_breakdowns table)
            # Logic: If 1 row -> also save it? KSeF logic might use it. 
            # Or only if > 1? The previous logic was only if 'Mieszana'.
            # To be consistent with "Mieszana" mode being triggered by >1 row:
            if not is_new:
                 self.db.query(InvoicePaymentBreakdown).filter(InvoicePaymentBreakdown.invoice_id == inv.id).delete()
            
            if len(rows_data) > 0: # Save even if 1 row, for consistency? 
                # Old logic used inv.payment_method only if no breakdowns.
                # Let's save logic: if inv.payment_method == "Mieszana" -> save all rows.
                if inv.payment_method == "Mieszana (Wiele metod)":
                    for split in rows_data:
                        pb = InvoicePaymentBreakdown(invoice_id=inv.id, payment_method=split['method'], amount=split['amount'])
                        self.db.add(pb)
                else:
                    # If single method, we usually don't need breakdown table, fields on Invoice are enough.
                    # BUT for "Split Payment" amount integrity, we might want it? No, keep it simple.
                    pass

            # Optionally save Bank Name / SWIFT if model supports it (currently model only has bank_account_number)
            # If we want to persist SWIFT/BankName per invoice, we need migrations. For now assuming global or just text.
            
            # KSeF Flags
            inv.is_split_payment = self.chk_mpp.isChecked()
            inv.is_cash_accounting = self.chk_cash.isChecked()
            # inv.is_fp = self.chk_fp.isChecked() # Hidden
            # if hasattr(inv, 'is_tp'): inv.is_tp = self.chk_tp.isChecked()
            if hasattr(inv, 'is_reverse_charge'): inv.is_reverse_charge = self.chk_reverse.isChecked()
            if hasattr(inv, 'is_exempt'): inv.is_exempt = self.chk_zw.isChecked()
            # if hasattr(inv, 'is_new_transport_intra'): inv.is_new_transport_intra = self.chk_wdt_new.isChecked()
            # if hasattr(inv, 'excise_duty_refund'): inv.excise_duty_refund = self.chk_excise.isChecked()
            
            # Exempt details
            inv.exemption_basis_type = self.exemption_type.currentText() if self.chk_zw.isChecked() else None
            inv.exemption_basis = self.exemption_desc.text() if self.chk_zw.isChecked() else None
            
            # Margin
            inv.margin_procedure_type = self.margin_type.currentText() if self.chk_margin.isChecked() else None
            
            # Transaction Terms
            inv.transaction_order_number = self.order_num.text()
            if self.order_date.text() != "brak": inv.transaction_order_date = self.order_date.date().toPython()
            inv.transaction_contract_number = self.contract_num.text()
            if self.contract_date.text() != "brak": inv.transaction_contract_date = self.contract_date.date().toPython()
            
            # Notes
            inv.notes = self.notes_edit.toPlainText()

            if is_new: self.db.add(inv)
            self.db.commit()
            
            # Items Save
            if not is_new:
                self.db.query(InvoiceItem).filter(InvoiceItem.invoice_id == inv.id).delete()
            
            # --- SANITIZATION ---
            from gui_qt.utils import sanitize_text
            inv.number = sanitize_text(inv.number or "")
            inv.place_of_issue = sanitize_text(inv.place_of_issue or "")
            inv.correction_reason = sanitize_text(inv.correction_reason or "")
            inv.notes = sanitize_text(inv.notes or "", multiline=True)
            inv.transaction_order_number = sanitize_text(inv.transaction_order_number or "")
            inv.transaction_contract_number = sanitize_text(inv.transaction_contract_number or "")
            inv.bank_account_number = sanitize_text(inv.bank_account_number or "")
            
            # Snapshots cleaning (in-place modification of dict if possible or simple clean of key fields)
            if inv.buyer_snapshot and isinstance(inv.buyer_snapshot, dict):
                 for k in ['name', 'address', 'city', 'country_code', 'postal_code', 'nip']:
                      if k in inv.buyer_snapshot:
                          inv.buyer_snapshot[k] = sanitize_text(inv.buyer_snapshot[k])
            
            if inv.seller_snapshot and isinstance(inv.seller_snapshot, dict):
                 for k in ['company_name', 'address', 'city', 'country_code', 'postal_code', 'nip', 'bank_name', 'bank_account']:
                      if k in inv.seller_snapshot:
                          inv.seller_snapshot[k] = sanitize_text(inv.seller_snapshot[k])

            is_gross_mode = (inv.price_type == "GROSS")
            
            # Aggregate Totals
            agg_total_net = 0.0
            agg_total_gross = 0.0
            
            for r in range(self.items_table.rowCount()):
                try:
                    def parse(t): return float(t.replace(",", ".") or 0)
                    
                    raw_name = self.items_table.item(r, 0).text()
                    name = sanitize_text(raw_name)
                    if not name: continue # Skip empty rows

                    sku = sanitize_text(self.items_table.item(r, 1).text())
                    unit = sanitize_text(self.items_table.item(r, 2).text())
                    qty = parse(self.items_table.item(r, 3).text())
                    price = parse(self.items_table.item(r, 4).text())
                    
                    vat_widget = self.items_table.cellWidget(r, 5)
                    vat_rate = vat_widget.currentData()
                    vat_rate_name = vat_widget.currentText()
                    
                    lump_rate = None
                    if self.is_ryczalt_mode:
                        lump_rate = self.items_table.cellWidget(r, 6).currentData()
                        
                    # Descriptions
                    name_item = self.items_table.item(r, 0)
                    desc_k = sanitize_text(name_item.data(Qt.UserRole + 1) or "")
                    desc_v = sanitize_text(name_item.data(Qt.UserRole + 2) or "")
                        
                    if is_gross_mode:
                        # Price is Gross Unit Price
                        gross_line = qty * price
                        net_line = gross_line / (1.0 + vat_rate)
                        net_price = net_line / qty if qty else 0
                        
                        # Data for Product Model
                        prod_net = price / (1.0 + vat_rate)
                        prod_gross = price
                    else:
                        # Price is Net Unit Price
                        net_line = qty * price
                        gross_line = net_line * (1.0 + vat_rate)
                        net_price = price
                        
                        # Data for Product Model
                        prod_net = price
                        prod_gross = price * (1.0 + vat_rate)
                    
                    agg_total_net += net_line
                    agg_total_gross += gross_line

                    # --- Auto-Save Product Logic ---
                    if self.chk_auto_save_products.isChecked():
                        try:
                            # Trim name for safety
                            s_name = name.strip()
                            if s_name:
                                existing_prod = self.db.query(Product).filter(Product.name == s_name).first()
                                if not existing_prod:
                                     # Create new
                                     new_prod = Product(
                                          name=s_name,
                                          sku=sku,
                                          unit=unit,
                                          net_price=prod_net,
                                          gross_price=prod_gross,
                                          vat_rate=vat_rate,
                                          is_gross_mode=is_gross_mode
                                     )
                                     self.db.add(new_prod)
                                     # Flush to get ID if needed, though commit is at end
                                     self.db.flush() 
                        except Exception as e_prod:
                            print(f"Error auto-saving product: {e_prod}")

                    
                    item = InvoiceItem(invoice_id=inv.id)
                    item.product_name = name
                    item.sku = sku
                    item.quantity = qty
                    item.unit = unit
                    item.net_price = net_price
                    item.gross_value = gross_line
                    item.vat_rate = vat_rate
                    item.vat_rate_name = vat_rate_name
                    item.lump_sum_rate = lump_rate
                    item.description_key = desc_k
                    item.description_value = desc_v
                    self.db.add(item)
                except: pass
            
            # Update Invoice Totals
            inv.total_net = agg_total_net
            inv.total_gross = agg_total_gross
                
            self.db.commit()
            self.accept()
            
        except Exception as e:
            self.db.rollback()
            QMessageBox.critical(self, "Błąd", str(e))
            print(e)
            
    def select_contractor(self):
        ctrs = self.db.query(Contractor).all()
        ctrs.sort(key=lambda x: x.name)
        
        ADD_KEY = "   [ + DODAJ NOWEGO KONTRAHENTA + ]"
        items = [ADD_KEY] + [f"{c.nip} - {c.name}" for c in ctrs]
        
        item, ok = QInputDialog.getItem(self, "Wybierz Kontrahenta", "Kontrahent:", items, 0, False)
        if ok and item:
            if item == ADD_KEY:
                self.add_new_contractor_flow()
            else:
                nip = item.split(" - ")[0]
                ctr = self.db.query(Contractor).filter(Contractor.nip == nip).first()
                self.set_contractor(ctr)

    def add_new_contractor_flow(self):
        # Use custom dialog for separate Country Code and strict NIP input
        ndialog = NipEntryDialog(self)
        if not ndialog.exec():
            return
            
        cc_in, nip_in = ndialog.get_data()
        
        from gui_qt.contractor_view import ContractorDialog
        from vies.client import ViesClient
        from mf_whitelist.client import MfWhitelistClient
        import re
        
        # If user left empty in manual mode, nip_in is None
        data = {}
        if nip_in:
            data["nip"] = nip_in
            data["country_code"] = cc_in if cc_in else "PL"
            
            # Since validation passed in NipEntryDialog, we can proceed to lookup
            validation_error = None
            # Double check (redundant but safe)
            if cc_in == "PL" and len(nip_in) != 10:
                pass # Already checked

            if not validation_error:
                # 2. Online Lookup
                try:
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    found_any_info = False
                    
                    country_code = cc_in
                    nip_digits = nip_in

                    # A. Try VIES (Europe + PL address)
                    vies = ViesClient()
                    vies_res = vies.check_vat(country_code, nip_digits)
                    print(f"[DEBUG] VIES response: {vies_res}")

                    if vies_res and vies_res.get('valid'):
                        found_any_info = True
                        if vies_res.get('name'): data["name"] = vies_res['name']
                        if vies_res.get('address'): 
                            # Parsing logic mainly for PL addresses typical in VIES
                            addr_raw = vies_res['address']
                            parts = [p.strip() for p in addr_raw.split('\n') if p.strip()]
                            
                            parsed = False
                            if country_code == 'PL' and len(parts) >= 2:
                                zip_city = parts[-1]
                                match = re.match(r'^(\d{2}-\d{3})\s+(.+)$', zip_city)
                                if match:
                                    data["postal_code"] = match.group(1)
                                    data["city"] = match.group(2)
                                    data["address"] = ", ".join(parts[:-1])
                                    parsed = True
                            
                            if not parsed:
                                data["address"] = addr_raw.replace("\n", ", ")
                                
                        data["is_vat_ue"] = True
                        data["country_code"] = country_code
                    
                    # B. Try MF Whitelist (PL Only, usually better Name/Status)
                    if country_code == "PL":
                        mf = MfWhitelistClient()
                        mf_res = mf.check_nip(nip_digits)
                        print(f"[DEBUG] MF response: {mf_res}")
                        if mf_res and mf_res.get('success'):
                            # Check actual data presence
                            if mf_res.get('name'):
                                data["name"] = mf_res['name']
                                found_any_info = True
                            if mf_res.get('active') is not None:
                                data["is_vat_payer"] = mf_res.get('active', False)
                            
                            # Additional MF Data
                            if mf_res.get('status'):
                                data["mf_status"] = mf_res['status']  # e.g. "Czynny", "Zwolniony"
                            
                            if mf_res.get('regon'):
                                data["regon"] = mf_res['regon']
                            
                            # Use address from MF if VIES failed or returned nothing useful
                            if not data.get("address") and mf_res.get("residence_address"):
                                mf_addr = mf_res["residence_address"]
                                # Very basic parsing for MF address if needed, usually string like "UL. ABC 1, 00-000 MIASTO"
                                data["address"] = mf_addr
                                # Try to extract zip/city if we have comma
                                if "," in mf_addr:
                                    parts = mf_addr.rsplit(",", 1)
                                    if len(parts) == 2:
                                        data["address"] = parts[0].strip()
                                        zip_city = parts[1].strip()
                                        match = re.match(r'^(\d{2}-\d{3})\s+(.+)$', zip_city)
                                        if match:
                                            data["postal_code"] = match.group(1)
                                            data["city"] = match.group(2)
                            
                            if mf_res.get('account_numbers'):
                                print(f"[DEBUG] Znalezione konta bankowe (MF): {mf_res['account_numbers']}")
                    
                    elif country_code != "PL":
                         data["country"] = "Zagranica" 

                    QApplication.restoreOverrideCursor()
                    
                    if not found_any_info:
                         QMessageBox.information(self, "Brak Danych", "Nie znaleziono danych podmiotu lub bazy są niedostępne. Wprowadź dane ręcznie.")

                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    print(f"Błąd pobierania danych: {e}")
                    QMessageBox.warning(self, "Ostrzeżenie", f"Błąd pobierania danych z baz zewnętrznych ({str(e)}). Kontynuuj ręcznie.")
        
        # Open Dialog with pre-filled data
        dlg = ContractorDialog(self, contractor_data=data)
        if dlg.exec():
            new_data = dlg.get_data()
            try:
                # Check duplication
                existing = self.db.query(Contractor).filter(Contractor.nip == new_data["nip"]).first()
                if existing:
                     QMessageBox.warning(self, "Info", f"Kontrahent o NIP {new_data['nip']} już istnieje. Zostanie wybrany.")
                     self.set_contractor(existing)
                     return
                
                # Check duplication if NIP is empty (e.g. foreign manual) - maybe check name?
                if not new_data["nip"]:
                    # Allow multiple no-nip contractors? Usually yes for individuals.
                    pass

                new_ctr = Contractor(**new_data)
                self.db.add(new_ctr)
                self.db.commit()
                self.db.refresh(new_ctr)
                
                self.set_contractor(new_ctr)
                QMessageBox.information(self, "Sukces", "Dodano i wybrano nowego kontrahenta.")
            except Exception as e:
                self.db.rollback()
                QMessageBox.critical(self, "Błąd", f"Błąd zapisu: {str(e)}")

    def set_contractor(self, ctr):
        self.selected_contractor = ctr
        self.contractor_info.setText(f"<b>{ctr.name}</b><br>NIP: {ctr.nip}<br>{ctr.address}, {ctr.city}")
        
        # Check Purchase logic: If purchase, detect if Contractor is VAT Payer
        if self.category == InvoiceCategory.PURCHASE:
            # If contractor is NOT vat payer, default price type to GROSS and VAT to ZW
            if not ctr.is_vat_payer:
                 self.is_exempt_mode = True 
                 self.price_type_combo.setCurrentText("Brutto")
                 self.chk_zw.setChecked(True)
                 self.info_lbl.setText("Tryb: Wykryto Zwolnienie z VAT (Zakup od nie-vatowca)")
                 self.update_rows_vat("ZW")
            else:
                 # Revert to standard defaults if we switch to a VAT payer
                 self.is_exempt_mode = False
                 self.price_type_combo.setCurrentText("Netto")
                 self.chk_zw.setChecked(False)
                 self.info_lbl.setText("")
                 # Optionally reset rows to 23% if they were ZW? 
                 # We will set them to 23% (Standard) to be helpful
                 self.update_rows_vat("23%")

    def update_rows_vat(self, name_fragment):
        """Helper to batch update VAT rates in existing rows"""
        target_idx = -1
        # Find index matching name
        for i, r in enumerate(self.vat_rates):
            if name_fragment in r.name:
                target_idx = i
                break
        
        if target_idx != -1:
            for r in range(self.items_table.rowCount()):
                combo = self.items_table.cellWidget(r, 5)
                if combo:
                    combo.setCurrentIndex(target_idx)
                    # If updating based on Exempt mode switch, update enabled state
                    if self.is_exempt_mode:
                        combo.setEnabled(False)
                    else:
                        combo.setEnabled(True)
        else:
            # If target not found but we are switching non-exempt -> enable
            if not self.is_exempt_mode:
                for r in range(self.items_table.rowCount()):
                    combo = self.items_table.cellWidget(r, 5)
                    if combo: combo.setEnabled(True)
        
        self.recalculate_totals()

