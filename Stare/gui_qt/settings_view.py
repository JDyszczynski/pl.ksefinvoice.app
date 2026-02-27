from PySide6.QtWidgets import (QWidget, QVBoxLayout, QTabWidget, QFormLayout, QLineEdit, QTextEdit,
                             QPushButton, QComboBox, QCheckBox, QHBoxLayout, QMessageBox, QLabel, 
                             QScrollArea, QFrame, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, 
                             QInputDialog, QRadioButton, QButtonGroup, QStackedWidget, QFileDialog, QApplication,
                             QSpinBox, QDoubleSpinBox, QGroupBox, QDateEdit, QCompleter)
from PySide6.QtCore import Qt, QDate
from database.engine import get_db
from database.models import (CompanyConfig, TaxSystem, InvoiceType, InvoiceCategory, 
                             NumberingSetting, PeriodType, VatRate, TaxationForm, LumpSumRate, User)
import hashlib
import shutil
import os
import datetime
from logic.security import SecurityManager
from ksef.client import KsefClient
from logic.tax_offices import TAX_OFFICES
import logging

logger = logging.getLogger(__name__)

from gui_qt.user_dialog import UserDialog

class SettingsView(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.load_config()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        
        # Tabs
        self.tabs = QTabWidget()
        
        # Tab 1: Company (Basic)
        self.tab_company = QWidget()
        self.init_company_tab()
        self.tabs.addTab(self.tab_company, "Dane Firmy")
        
        # Tab: KSeF
        self.tab_settings_ksef = QWidget()
        self.init_ksef_tab()
        self.tabs.addTab(self.tab_settings_ksef, "KSeF")

        # Tab: Others (Inne)
        self.tab_others = QWidget()
        self.init_others_tab()
        self.tabs.addTab(self.tab_others, "Inne")
        
        # Tab 2: Numbering
        self.tab_numbering = QWidget()
        self.init_numbering_tab()
        self.tabs.addTab(self.tab_numbering, "Schematy Numeracji")

        # Tab 3: VAT Rates
        self.tab_vat = QWidget()
        self.init_vat_tab()
        self.tabs.addTab(self.tab_vat, "Stawki VAT")

        # Tab 4: Taxation Rates
        self.tab_taxation = QWidget()
        self.init_taxation_tab()
        self.tabs.addTab(self.tab_taxation, "Stawki opodatkowania")

        # Tab: Program
        self.tab_program = QWidget()
        self.init_program_tab()
        self.tabs.addTab(self.tab_program, "Program")

        # Tab: Baza Danych
        self.tab_database = QWidget()
        self.init_database_tab()
        self.tabs.addTab(self.tab_database, "Baza Danych")
        
        main_layout.addWidget(self.tabs)
        
        # Save Button
        save_btn = QPushButton("Zapisz wszystkie ustawienia")
        save_btn.setStyleSheet("padding: 10px; font-weight: bold;")
        save_btn.clicked.connect(self.save_all)
        main_layout.addWidget(save_btn)

    def init_company_tab(self):
        wrapper = QVBoxLayout(self.tab_company)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        form = QFormLayout(content)
        
        # Identity
        self.is_natural_person_cb = QCheckBox("Osoba Fizyczna (JDG)")
        self.is_natural_person_cb.toggled.connect(self.toggle_person_fields)
        form.addRow("", self.is_natural_person_cb)

        self.person_group = QWidget()
        pg_layout = QFormLayout(self.person_group)
        pg_layout.setContentsMargins(0, 0, 0, 0)
        
        self.first_name = QLineEdit()
        self.last_name = QLineEdit()
        self.birth_date = QDateEdit()
        self.birth_date.setCalendarPopup(True)
        self.birth_date.setDisplayFormat("yyyy-MM-dd")
        
        pg_layout.addRow("Imię:", self.first_name)
        pg_layout.addRow("Nazwisko:", self.last_name)
        pg_layout.addRow("Data Urodzenia:", self.birth_date)
        
        form.addRow(self.person_group)

        self.company_name = QLineEdit()
        self.nip = QLineEdit()
        self.regon = QLineEdit()
        
        form.addRow("Nazwa Firmy (Pełna):", self.company_name)
        form.addRow("NIP:", self.nip)
        form.addRow("REGON:", self.regon)

        # Contact / JPK Info
        self.email = QLineEdit()
        self.phone_number = QLineEdit()
        
        # Tax Office Combo (Searchable)
        self.tax_office_combo = QComboBox()
        self.tax_office_combo.setEditable(True)
        self.tax_office_combo.setInsertPolicy(QComboBox.NoInsert)
        self.tax_office_combo.setPlaceholderText("Wpisz kod lub miasto...")
        
        # Fill Dict
        # Make a list like "2206 - Drugi Urząd Skarbowy w Gdańsku"
        # Sorted by code probably
        sorted_offices = sorted(TAX_OFFICES.items(), key=lambda x: x[0])
        self.tax_office_combo.addItem("", "") # Empty
        for code, name in sorted_offices:
            label = f"{code} - {name}"
            self.tax_office_combo.addItem(label, code)
            
        # Completer for searching
        completer = QCompleter(self.tax_office_combo.model(), self.tax_office_combo)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.tax_office_combo.setCompleter(completer)
        
        form.addRow("E-mail (do JPK):", self.email)
        form.addRow("Telefon (do JPK):", self.phone_number)
        form.addRow("Urząd Skarbowy:", self.tax_office_combo)

        self.address = QLineEdit()
        self.city = QLineEdit()
        self.postal = QLineEdit()
        self.country = QLineEdit("Polska")
        self.country_code = QLineEdit("PL")
        self.bank_account = QLineEdit()
        self.bank_account.setPlaceholderText("XX XXXX XXXX XXXX XXXX XXXX XXXX")
        self.bank_account.setMaxLength(32 + 6) # 26 digits + 2 PL + spaces approx
        self.bank_account.textEdited.connect(self.format_bank_account)
        self.bank_name = QLineEdit()
        self.swift_code = QLineEdit() 
        self.bdo_number = QLineEdit() 
        self.krs = QLineEdit()
        self.share_capital = QLineEdit()
        self.court_info = QTextEdit()
        self.court_info.setMaximumHeight(80)
        
        # Tax System
        self.tax_dd = QComboBox()
        self.tax_dd.addItem("Skala podatkowa", TaxationForm.SCALE.name)
        self.tax_dd.addItem("Podatek liniowy", TaxationForm.LINEAR.name)
        self.tax_dd.addItem("Ryczałt ewidencjonowany", TaxationForm.RYCZALT.name)
        self.tax_dd.currentIndexChanged.connect(self.update_tax_stack)
        
        # VAT Payer
        self.is_vat_cb = QCheckBox("Czynny płatnik VAT")
        self.is_vat_cb.setChecked(True)
        
        # VAT Settlement Method Combo
        self.vat_method_combo = QComboBox()
        self.vat_method_combo.addItem("Miesięczna", "MONTHLY")
        self.vat_method_combo.addItem("Kwartalna", "QUARTERLY")
        self.vat_method_combo.setFixedWidth(200)
        self.vat_method_combo.setEnabled(True)
        
        form.addRow("BDO:", self.bdo_number)
        form.addRow("Adres:", self.address)
        form.addRow("Miasto:", self.city)
        form.addRow("Kod Pocztowy:", self.postal)
        form.addRow("Kraj:", self.country)
        form.addRow("Kod Kraju:", self.country_code)
        form.addRow("Nr Konta:", self.bank_account)
        form.addRow("Nazwa Banku:", self.bank_name)
        form.addRow("SWIFT/BIC:", self.swift_code)
        
        form.addRow("KRS:", self.krs)
        form.addRow("Kapitał zakładowy:", self.share_capital)
        form.addRow("Sąd / Rejestr:", self.court_info)
        
        form.addRow("Forma opodatkowania:", self.tax_dd)
        
        # Row for VAT settings
        vat_row = QHBoxLayout()
        vat_row.addWidget(self.is_vat_cb)
        
        self.vat_settlement_group = QWidget()
        vsg_layout = QHBoxLayout(self.vat_settlement_group)
        vsg_layout.setContentsMargins(10, 0, 0, 0)
        vsg_layout.addWidget(QLabel("Metoda rozliczania:"))
        vsg_layout.addWidget(self.vat_method_combo)
        
        vat_row.addWidget(self.vat_settlement_group)
        vat_row.addStretch()
        
        form.addRow("", vat_row)
        
        # New: Exemption Details (Visible if not VAT payer)
        self.vat_exemption_group = QWidget()
        ve_layout = QFormLayout(self.vat_exemption_group)
        ve_layout.setContentsMargins(0, 0, 0, 0)
        
        self.ve_type = QComboBox()
        self.ve_type.addItem("", "")
        self.ve_type.addItem("Przepis ustawy albo aktu wydanego na podstawie ustawy, na podstawie którego podatnik stosuje zwolnienie od podatku", "USTAWA")
        self.ve_type.addItem("Przepis dyrektywy 2006/112/WE, który zwalnia od podatku taką dostawę towarów lub takie świadczenie usług", "DYREKTYWA")
        self.ve_type.addItem("Inna podstawa prawna wskazująca na to, że dostawa towarów lub świadczenie usług korzysta ze zwolnienia", "INNE")
        
        self.ve_type.setMinimumWidth(300)

        self.ve_desc = QLineEdit()
        self.ve_desc.setPlaceholderText("Np. Art. 43 ust. 1 pkt 19")
        
        ve_layout.addRow(QLabel("<b>Szczegóły Zwolnienia z VAT (P_19):</b>"))
        ve_layout.addRow("Podstawa (Typ):", self.ve_type)
        ve_layout.addRow("Przepis / Podstawa:", self.ve_desc)
        
        form.addRow(self.vat_exemption_group)
        
        # Visibility Logic
        self.is_vat_cb.stateChanged.connect(self.toggle_exemption_ui)
        self.toggle_exemption_ui()
        self.toggle_person_fields() # Init state
        
        # Init Objects for Others Tab (created here as member variables)
        self.footer_extra = QTextEdit()
        self.footer_extra.setMaximumHeight(80)
        self.footer_extra.setPlaceholderText("Dodatkowe informacje do stopki (jeśli wypełnione)")
        
        scroll.setWidget(content)
        wrapper.addWidget(scroll)

    def toggle_person_fields(self):
        is_person = self.is_natural_person_cb.isChecked()
        self.person_group.setVisible(is_person)
        
    def init_ksef_tab(self):
        wrapper = QVBoxLayout(self.tab_settings_ksef)
        content = QWidget()
        form = QFormLayout(content)
        wrapper.addWidget(content)
        wrapper.addStretch()

        # KSeF Configuration
        form.addRow(QLabel("<b>Konfiguracja KSeF:</b>"))
        
        # Environment
        self.ksef_env = QComboBox()
        self.ksef_env.addItem("Produkcyjne", "prod")
        self.ksef_env.addItem("Testowe", "test")
        self.ksef_env.currentIndexChanged.connect(lambda idx: self.on_env_change(self.ksef_env.itemData(idx)))
        form.addRow("Środowisko:", self.ksef_env)

        # Button to refresh Public Keys
        self.btn_refresh_keys = QPushButton("Pobierz/Odśwież klucz publiczny MF")
        self.btn_refresh_keys.setToolTip("Pobierz aktualny klucz publiczny Ministerstwa Finansów dla wybranego środowiska i zapisz w bazie")
        self.btn_refresh_keys.clicked.connect(self.refresh_public_keys)
        form.addRow("", self.btn_refresh_keys)

        # Auth Method
        self.auth_group = QButtonGroup(self)
        self.rb_token = QRadioButton("Token Autoryzacyjny")
        self.rb_cert = QRadioButton("Certyfikat (Klucze)")
        self.auth_group.addButton(self.rb_token)
        self.auth_group.addButton(self.rb_cert)
        
        # Default to Certificate
        self.rb_cert.setChecked(True)
        
        auth_lay = QHBoxLayout()
        auth_lay.addWidget(self.rb_token)
        auth_lay.addWidget(self.rb_cert)
        form.addRow("Metoda logowania:", auth_lay)
        
        # Stack
        self.stack_auth = QStackedWidget()
        
        # Page 0: Token
        p_token = QWidget()
        l_token = QFormLayout(p_token)
        l_token.setContentsMargins(0,10,0,0)
        self.ksef_token = QLineEdit()
        l_token.addRow("Token:", self.ksef_token)
        
        # Test button for Token (closer)
        self.btn_test_token = QPushButton("Test")
        self.btn_test_token.setFixedWidth(60)
        self.btn_test_token.clicked.connect(self.test_ksef_connection)
        l_token.addRow("", self.btn_test_token)
        
        self.stack_auth.addWidget(p_token)
        
        # Page 1: Cert
        p_cert = QWidget()
        l_cert = QFormLayout(p_cert)
        l_cert.setContentsMargins(0,10,0,0)
        
        # Helper for file selection with DB storage
        def make_file_load_row(label, status_attr, load_callback):
            lbl = QLabel("[Brak]")
            lbl.setStyleSheet("color: red")
            setattr(self, status_attr, lbl)
            
            btn = QPushButton("Wczytaj z pliku...")
            btn.clicked.connect(load_callback)
            
            r = QHBoxLayout()
            r.addWidget(lbl)
            r.addWidget(btn)
            l_cert.addRow(label, r)

        # Temporary storage for loaded content (before saving)
        self.pending_cert_content = None
        self.pending_key_content = None

        make_file_load_row("Certyfikat (Public):", "lbl_cert_status", self.load_cert_file)
        make_file_load_row("Klucz Prywatny:", "lbl_key_status", self.load_key_file)
        
        self.key_pass_edit = QLineEdit()
        self.key_pass_edit.setEchoMode(QLineEdit.Password)
        self.key_pass_edit.setPlaceholderText("Pozostaw puste jeśli brak hasła")
        self.key_pass_edit.setFixedWidth(150)
        
        # Test button for Cert (inline)
        self.btn_test_cert = QPushButton("Test")
        self.btn_test_cert.setFixedWidth(60)
        self.btn_test_cert.clicked.connect(self.test_ksef_connection)
        
        h_pass = QHBoxLayout()
        h_pass.addWidget(self.key_pass_edit)
        h_pass.addWidget(self.btn_test_cert)
        h_pass.addStretch()
        
        l_cert.addRow("Hasło klucza:", h_pass)
        
        self.stack_auth.addWidget(p_cert)
        form.addRow(self.stack_auth)
        
        # Default stack page
        self.stack_auth.setCurrentIndex(1)
        
        self.auth_group.buttonClicked.connect(lambda: self.stack_auth.setCurrentIndex(1 if self.rb_cert.isChecked() else 0))

        # Link info
        lbl_info = QLabel(
             "Tokeny oraz certyfikaty dla tego środowiska możesz wygenerować na stronie:\n"
             "https://ksef-test.mf.gov.pl/web/ (Wymagane logowanie profilem zaufanym lub podpisem)"
        )
        lbl_info.setOpenExternalLinks(True) 
        lbl_info.setStyleSheet("color: blue;")
        form.addRow(lbl_info)

    def init_others_tab(self):
        wrapper = QVBoxLayout(self.tab_others)
        content = QWidget()
        form = QFormLayout(content)
        wrapper.addWidget(content)
        wrapper.addStretch()
        
        form.addRow(QLabel("<b>Dodatkowe informacje na fakturze:</b>"))
        form.addRow("Stopka dodatkowa (2):", self.footer_extra)
        form.addRow(QLabel("<i style='color:gray'>Tekst ten będzie dołączany na końcu stopki faktury,<br>jeśli pole zostanie wypełnione (min. 1 znak).</i>"))

    def toggle_exemption_ui(self, state=None):
        # If VAT Payer -> Exemption UI Hidden
        # If Not VAT Payer -> Exemption UI Visible
        is_payer = self.is_vat_cb.isChecked()
        self.vat_exemption_group.setVisible(not is_payer)
        
        # Hide Settlement Method group if not VAT payer
        if hasattr(self, 'vat_settlement_group'):
            self.vat_settlement_group.setVisible(is_payer)
        
        # Also hide limits in Taxation Tab if they are initialized
        if hasattr(self, 'grp_vat_limits'):
            self.grp_vat_limits.setVisible(not is_payer)
            self.grp_vat_limits.setEnabled(not is_payer)

    def update_tax_stack(self):
        data = self.tax_dd.currentData()
        if data == "RYCZALT":
            self.tax_stack.setCurrentIndex(0)
        elif data == "SCALE":
             self.tax_stack.setCurrentIndex(1)
        elif data == "LINEAR":
             self.tax_stack.setCurrentIndex(2)

    def refresh_public_keys(self):
        """Manually trigger fetching of KSeF public keys."""
        env = self.ksef_env.currentData()
        current_nip = self.nip.text().replace("-", "").strip()
        
        if not current_nip:
            QMessageBox.warning(self, "Błąd", "Wprowadź i zapisz najpierw NIP firmy (w zakładce Dane Firmy).")
            return

        try:
            # Create a mock config with just enough info for fetch_public_key logic
            class MockConfig:
                pass
            cfg = MockConfig()
            cfg.nip = current_nip
            # set defaults to avoid other errors if init checks them
            cfg.ksef_auth_mode = "TOKEN" 
            cfg.ksef_environment = env
            # Add missing token attributes to avoid AttributeError in KsefClient.__init__
            cfg.ksef_token = None
            cfg.ksef_token_test = None
            
            client = KsefClient(config=cfg)
            key_bytes = client.fetch_public_key()
            
            if key_bytes:
                QMessageBox.information(self, "Sukces", f"Pomyślnie pobrano i zapisano klucz publiczny dla środowiska {env}.")
            else:
                QMessageBox.warning(self, "Ostrzeżenie", "Operacja zakończona, ale nie zwrócono klucza.")
            
        except Exception as e:
            logger.error(f"Error fetching public key: {e}")
            QMessageBox.critical(self, "Błąd", f"Nie udało się pobrać klucza: {e}\nSprawdź połączenie z internetem.")

    def test_ksef_connection(self):
        class DummyConfig:
            pass
        
        cfg = DummyConfig()
        env = self.ksef_env.currentData()
        cfg.ksef_environment = env
        cfg.ksef_auth_mode = "CERT" if self.rb_cert.isChecked() else "TOKEN"
        
        # Initialize all potential attributes to None to avoid AttributeError
        cfg.ksef_token = None
        cfg.ksef_cert_content = None
        cfg.ksef_private_key_content = None
        cfg.ksef_private_key_pass = None
        cfg.ksef_token_test = None
        cfg.ksef_cert_content_test = None
        cfg.ksef_private_key_content_test = None
        cfg.ksef_private_key_pass_test = None

        # Data form UI
        token_plain = self.ksef_token.text()
        pass_plain = self.key_pass_edit.text()
        
        # Encrypt because Client expects encrypted data in Config
        token_enc = SecurityManager.encrypt(token_plain) if token_plain else None
        pass_enc = SecurityManager.encrypt(pass_plain) if pass_plain else None

        # Resolve Binary Contents (Priority: Newly Loaded > Saved in DB)
        selected_env = self.ksef_env.currentData()
        # Note: self.pending_*_content assumes it belongs to the currently selected tab/env context
        
        cert_content = self.pending_cert_content
        if not cert_content and hasattr(self, 'current_config') and self.current_config:
             if selected_env == 'prod': cert_content = self.current_config.ksef_cert_content
             else: cert_content = getattr(self.current_config, 'ksef_cert_content_test', None)
             
        key_content = self.pending_key_content
        if not key_content and hasattr(self, 'current_config') and self.current_config:
             if selected_env == 'prod': key_content = self.current_config.ksef_private_key_content
             else: key_content = getattr(self.current_config, 'ksef_private_key_content_test', None)

        # Validation Logic
        if cfg.ksef_auth_mode == "TOKEN":
            if not token_plain:
                QMessageBox.warning(self, "Brak danych", "Wprowadź Token autoryzacyjny przed testem.")
                return
        else:
            if not cert_content:
                QMessageBox.warning(self, "Brak danych", f"Brak wczytania certyfikatu dla środowiska {env}.")
                return
            if not key_content:
                QMessageBox.warning(self, "Brak danych", f"Brak wczytania klucza prywatnego dla środowiska {env}.")
                return

        # Assign UI values to the correct set of attributes based on environment
        if env == "prod":
            cfg.ksef_token = token_enc
            cfg.ksef_cert_content = cert_content
            cfg.ksef_private_key_content = key_content
            cfg.ksef_private_key_pass = pass_enc
        else:
            cfg.ksef_token_test = token_enc
            cfg.ksef_cert_content_test = cert_content
            cfg.ksef_private_key_content_test = key_content
            cfg.ksef_private_key_pass_test = pass_enc
        
        nip = self.nip.text().replace("-", "").strip()
        if not nip:
            QMessageBox.warning(self, "Błąd", "Podaj NIP w danych firmy aby przetestować połączenie.")
            return

        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            
            # Late import to avoid circular dep if any
            from ksef.client import KsefClient
            
            # Initialize client with current (unsaved) config
            client = KsefClient(config=cfg)
            
            # Try to authenticate
            # Note: This performs a real request to KSeF API
            client.authenticate(nip)
            
            QApplication.restoreOverrideCursor()
            QMessageBox.information(self, "Sukces", f"Połączenie udane!\nZalogowano do środowiska {cfg.ksef_environment.upper()}.\nToken sesji aktywny.")
            
        except Exception as e:
            QApplication.restoreOverrideCursor()
            logging.error(f"KSeF Test Error: {e}", exc_info=True)
            
            err_str = str(e)
            title = "Błąd Połączenia"
            msg = f"Wystąpił błąd podczas próby połączenia z KSeF:\n{err_str}"
            
            # Detect specific KSeF errors
            if "21115" in err_str or "Nieprawidłowy certyfikat" in err_str:
                title = "Nieprawidłowy Certyfikat"
                msg = "System KSeF odrzucił certyfikat (Błąd 21115).\n\nMożliwe przyczyny:\n- Certyfikat wygasł,\n- Certyfikat nie jest zaufany w wybranym środowisku (Test/Prod),\n- NIP w certyfikacie nie zgadza się z NIP-em podmiotu.\n- Wybrane niewłaściwe pliki."

            QMessageBox.critical(self, title, msg)

    def select_cert(self):
            box.setIcon(QMessageBox.Critical)
            box.setWindowTitle(title)
            box.setText(msg)
            box.setInformativeText("Kliknij 'Show Details' aby zobaczyć pełną treść błędu.")
            box.setDetailedText(err_str)
            box.setStandardButtons(QMessageBox.Ok)
            box.exec()

    def pick_file(self, line_edit, filters):
        fname, _ = QFileDialog.getOpenFileName(self, "Wybierz plik", "", filters)
        if fname:
            line_edit.setText(fname)

    def init_numbering_tab(self):
        wrapper = QVBoxLayout(self.tab_numbering)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.numbering_content = QWidget()
        self.numbering_layout = QVBoxLayout(self.numbering_content)
        self.numbering_rows = []
        
        scroll.setWidget(self.numbering_content)
        wrapper.addWidget(scroll)

    def init_vat_tab(self):
        layout = QVBoxLayout(self.tab_vat)
        
        self.vat_table = QTableWidget()
        self.vat_table.setColumnCount(2)
        self.vat_table.setHorizontalHeaderLabels(["Nazwa (np. 23%)", "Wartość (np. 0.23)"])
        self.vat_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.vat_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.vat_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.vat_table.setEditTriggers(QAbstractItemView.NoEditTriggers) # Read-only view, edit via dialog/delete
        
        layout.addWidget(self.vat_table)
        
        btns = QHBoxLayout()
        add_btn = QPushButton("Dodaj Stawkę")
        add_btn.clicked.connect(self.add_vat_rate)
        del_btn = QPushButton("Usuń Zaznaczone")
        del_btn.clicked.connect(self.delete_vat_rate)
        
        btns.addWidget(add_btn)
        btns.addWidget(del_btn)
        layout.addLayout(btns)

    def init_taxation_tab(self):
        layout = QVBoxLayout(self.tab_taxation)
        
        # --- Common Settings (VAT Limit) ---
        self.grp_vat_limits = QGroupBox("Limity VAT")
        fl_vat = QFormLayout(self.grp_vat_limits)
        
        self.vat_limit_spin = QDoubleSpinBox()
        self.vat_limit_spin.setRange(0, 10_000_000)
        self.vat_limit_spin.setSuffix(" zł")
        self.vat_limit_spin.setGroupSeparatorShown(True)
        
        self.vat_subject_based_cb = QCheckBox("Zwolnienie przedmiotowe (brak limitu / nie dotyczy)")
        self.vat_subject_based_cb.toggled.connect(lambda chk: self.vat_limit_spin.setDisabled(chk))
        
        self.vat_warning_spin = QDoubleSpinBox()
        self.vat_warning_spin.setRange(0, 50_000_000)
        self.vat_warning_spin.setSuffix(" zł")
        self.vat_warning_spin.setSingleStep(1000)
        self.vat_warning_spin.setGroupSeparatorShown(True)
        self.vat_warning_spin.setToolTip("Powiadomienie po przekroczeniu tej kwoty sprzedaży w roku")

        fl_vat.addRow("Próg zwolnienia podmiotowego z VAT:", self.vat_limit_spin)
        fl_vat.addRow("Próg ostrzegawczy:", self.vat_warning_spin)
        fl_vat.addRow("", self.vat_subject_based_cb)
        
        layout.addWidget(self.grp_vat_limits)

        # --- Stacked Settings ---
        self.tax_stack = QStackedWidget()
        layout.addWidget(self.tax_stack)

        # Page 0: Ryczałt (Lump Sum) - existing table logic
        page_lump = QWidget()
        l_lump = QVBoxLayout(page_lump)
        l_lump.addWidget(QLabel("<b>Definicja stawek ryczałtu ewidencjonowanego:</b>"))
        
        self.lump_table = QTableWidget()
        self.lump_table.setColumnCount(2)
        self.lump_table.setHorizontalHeaderLabels(["Nazwa (np. 12%)", "Wartość (np. 0.12)"])
        self.lump_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.lump_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.lump_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.lump_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        l_lump.addWidget(self.lump_table)

        btns = QHBoxLayout()
        add_btn = QPushButton("Dodaj Stawkę")
        add_btn.clicked.connect(self.add_lump_rate)
        del_btn = QPushButton("Usuń Zaznaczone")
        del_btn.clicked.connect(self.delete_lump_rate)
        btns.addWidget(add_btn)
        btns.addWidget(del_btn)
        l_lump.addLayout(btns)
        
        self.tax_stack.addWidget(page_lump)

        # Page 1: Skala Podatkowa (Scale)
        page_scale = QWidget()
        l_scale = QFormLayout(page_scale)
        l_scale.addRow(QLabel("<b>Progi podatkowe (Skala):</b>"))
        
        # Threshold 1
        self.scale_limit_1 = QDoubleSpinBox()
        self.scale_limit_1.setRange(0, 10_000_000)
        self.scale_limit_1.setSuffix(" zł")
        self.scale_limit_1.setGroupSeparatorShown(True)
        l_scale.addRow("I próg dochodowy:", self.scale_limit_1)
        
        self.scale_rate_1 = QDoubleSpinBox()
        self.scale_rate_1.setRange(0, 100)
        self.scale_rate_1.setSuffix("%")
        l_scale.addRow("Stawka podatku I progu:", self.scale_rate_1)
        
        # Deduction
        self.scale_deduction = QDoubleSpinBox()
        self.scale_deduction.setRange(0, 100_000)
        self.scale_deduction.setSuffix(" zł")
        self.scale_deduction.setGroupSeparatorShown(True)
        l_scale.addRow("Kwota zmniejszająca podatek:", self.scale_deduction)

        # Threshold 2
        self.scale_rate_2 = QDoubleSpinBox()
        self.scale_rate_2.setRange(0, 100)
        self.scale_rate_2.setSuffix("%")
        l_scale.addRow("Stawka podatku II progu (nadwyżka):", self.scale_rate_2)
        
        # Solidarity
        l_scale.addRow(QLabel("<b>Danina Solidarnościowa:</b>"))
        self.solidarity_limit = QDoubleSpinBox()
        self.solidarity_limit.setRange(0, 100_000_000)
        self.solidarity_limit.setSuffix(" zł")
        self.solidarity_limit.setGroupSeparatorShown(True)
        l_scale.addRow("Próg dochodowy:", self.solidarity_limit)
        
        self.solidarity_rate = QDoubleSpinBox()
        self.solidarity_rate.setRange(0, 100)
        self.solidarity_rate.setSuffix("%")
        l_scale.addRow("Stawka daniny:", self.solidarity_rate)

        self.tax_stack.addWidget(page_scale)

        # Page 2: Liniowy (Linear)
        page_linear = QWidget()
        l_linear = QFormLayout(page_linear)
        l_linear.addRow(QLabel("<b>Podatek Liniowy:</b>"))
        
        self.linear_rate = QDoubleSpinBox()
        self.linear_rate.setRange(0, 100)
        self.linear_rate.setSuffix("%")
        l_linear.addRow("Stawka podatku:", self.linear_rate)
        
        self.tax_stack.addWidget(page_linear)

    def format_bank_account(self, text):
        if not text:
            return

        cursor_pos = self.bank_account.cursorPosition()
        
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
        
        # Avoid recursive loop only if changed
        if formatted != text:
             # Calculate new cursor position logic roughly
             # Simple approach: set text and restore cursor if possible, or just move to end
             self.bank_account.blockSignals(True)
             self.bank_account.setText(formatted)
             self.bank_account.blockSignals(False)
             # Move cursor to end for simple UX on strict mask
             self.bank_account.setCursorPosition(len(formatted))

    def load_config(self):
        db = next(get_db())
        try:
            config = db.query(CompanyConfig).first()
            if config:
                # Identity
                self.is_natural_person_cb.setChecked(config.is_natural_person or False)
                self.first_name.setText(config.first_name or "")
                self.last_name.setText(config.last_name or "")
                if config.date_of_birth:
                    if hasattr(config.date_of_birth, 'date'): # if datetime
                         self.birth_date.setDate(config.date_of_birth.date())
                    elif isinstance(config.date_of_birth, str):
                         self.birth_date.setDate(QDate.fromString(config.date_of_birth, "yyyy-MM-dd"))
                    elif isinstance(config.date_of_birth, QDate):
                         self.birth_date.setDate(config.date_of_birth)
                    else:
                         # datetime.date
                         self.birth_date.setDate(config.date_of_birth)
                
                # Tax Office
                code = config.tax_office_code
                if code:
                    # Find index
                    idx = self.tax_office_combo.findData(code)
                    if idx >= 0:
                        self.tax_office_combo.setCurrentIndex(idx)
                    else:
                        # Maybe code exists but not in our list? Add temporary?
                        # Or just set text if editable? No, let's keep it safe.
                        pass
                else:
                     self.tax_office_combo.setCurrentIndex(0)
                     
                self.email.setText(config.email or "")
                self.phone_number.setText(config.phone_number or "")
                
                self.company_name.setText(config.company_name or "")
                self.nip.setText(config.nip or "")
                self.regon.setText(config.regon or "")
                self.address.setText(config.address or "")
                self.city.setText(config.city or "")
                self.postal.setText(config.postal_code or "")
                self.country.setText(config.country or "Polska")
                self.country_code.setText(config.country_code or "PL")
                self.bank_account.setText(config.bank_account or "")
                self.bank_name.setText(config.bank_name or "")
                self.swift_code.setText(config.swift_code or "")
                self.bdo_number.setText(config.bdo or "")
                self.krs.setText(config.krs or "")
                self.share_capital.setText(config.share_capital or "")
                self.court_info.setText(config.court_info or "")
                self.footer_extra.setText(config.footer_extra or "")
                
                # Load TaxationForm
                if config.taxation_form:
                    val = config.taxation_form
                    val_name = val.name if hasattr(val, 'name') else str(val)
                    idx = self.tax_dd.findData(val_name)
                    if idx >= 0: self.tax_dd.setCurrentIndex(idx)
                    
                self.is_vat_cb.setChecked(config.is_vat_payer)
                
                # Load VAT Method
                # Requires DB Update (vat_settlement_method)
                if hasattr(config, 'vat_settlement_method'):
                    method = config.vat_settlement_method or "MONTHLY"
                    idx_m = self.vat_method_combo.findData(method)
                    if idx_m >= 0: self.vat_method_combo.setCurrentIndex(idx_m)
                
                # Exemption
                if config.vat_exemption_basis_type:
                    idx = self.ve_type.findData(config.vat_exemption_basis_type)
                    if idx >= 0: self.ve_type.setCurrentIndex(idx)
                self.ve_desc.setText(config.vat_exemption_basis or "")
                self.toggle_exemption_ui()
                
                # New Taxation Parameters
                is_subject_based = getattr(config, 'vat_exemption_subject_based', False)
                self.vat_subject_based_cb.setChecked(is_subject_based)
                self.vat_limit_spin.setDisabled(is_subject_based)
                self.vat_limit_spin.setValue(getattr(config, 'vat_exemption_limit', 200000) or 200000)
                # Warning threshold for VAT limit
                self.vat_warning_spin.setValue(getattr(config, 'vat_warning_threshold', 180000) or 180000)
                
                # Scale
                self.scale_limit_1.setValue(getattr(config, 'tax_scale_limit_1', 120000) or 120000)
                self.scale_rate_1.setValue((getattr(config, 'tax_scale_rate_1', 0.12) or 0.12) * 100)
                self.scale_deduction.setValue(getattr(config, 'tax_scale_deduction', 3600) or 3600)
                self.scale_rate_2.setValue((getattr(config, 'tax_scale_rate_2', 0.32) or 0.32) * 100)
                
                self.solidarity_limit.setValue(getattr(config, 'solidarity_levy_limit', 1000000) or 1000000)
                self.solidarity_rate.setValue((getattr(config, 'solidarity_levy_rate', 0.04) or 0.04) * 100)
                
                # Linear
                self.linear_rate.setValue((getattr(config, 'tax_linear_rate', 0.19) or 0.19) * 100)
                
                self.update_tax_stack()
                
                # KSeF Config
                current_env = config.ksef_environment or "prod"
                idx = self.ksef_env.findData(current_env)
                if idx >= 0: self.ksef_env.setCurrentIndex(idx)
                
                # Auth Mode
                mode = getattr(config, 'ksef_auth_mode', 'CERT')
                if mode == 'CERT':
                    self.rb_cert.setChecked(True)
                    self.stack_auth.setCurrentIndex(1)
                else:
                    self.rb_token.setChecked(True)
                    self.stack_auth.setCurrentIndex(0)

                # Store reference to config for env switching
                self.current_config = config
                self.last_env = current_env
                
                # Load credentials for current environment
                self._load_ksef_credentials_to_ui(current_env)
            
            # Ensure Tax Stack is consistent with Tax Form Dropdown (even if default or loaded)
            self.update_tax_stack()

            # Load Numbering
            self.load_numbering(db)
            
            # Load VAT
            self.load_vat_rates(db)
            
            # Load Lump Sum
            self.load_lump_rates(db)

        finally:
            db.close()

    def seed_default_vat_rates(self, db):
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
                db.add(VatRate(name=name, rate=rate_val))
            db.commit()
        except Exception as e:
            print(f"Error seeding VAT rates: {e}")
            db.rollback()

    def load_vat_rates(self, db):
        rows = db.query(VatRate).all()
        if not rows:
            self.seed_default_vat_rates(db)
            rows = db.query(VatRate).all()
            
        self.vat_table.setRowCount(0)
        for r in rows:
            row_idx = self.vat_table.rowCount()
            self.vat_table.insertRow(row_idx)
            self.vat_table.setItem(row_idx, 0, QTableWidgetItem(str(r.name)))
            self.vat_table.setItem(row_idx, 1, QTableWidgetItem(str(r.rate)))
            self.vat_table.item(row_idx, 0).setData(Qt.UserRole, r.id) # Store ID

    def add_vat_rate(self):
        name, ok1 = QInputDialog.getText(self, "Nowa Stawka VAT", "Nazwa (np. 23%):")
        if not ok1 or not name: return
        
        val_str, ok2 = QInputDialog.getText(self, "Nowa Stawka VAT", "Wartość dziesiętna (np. 0.23):")
        if not ok2 or not val_str: return
        
        try:
            val = float(val_str.replace(",", "."))
        except ValueError:
            QMessageBox.warning(self, "Błąd", "Nieprawidłowa wartość liczbowa!")
            return
            
        db = next(get_db())
        try:
            rate = VatRate(name=name, rate=val)
            db.add(rate)
            db.commit()
            self.load_vat_rates(db)
        except Exception as e:
            QMessageBox.critical(self, "Błąd", str(e))
        finally:
            db.close()

    def delete_vat_rate(self):
        curr = self.vat_table.currentRow()
        if curr < 0: return
        
        rid = self.vat_table.item(curr, 0).data(Qt.UserRole)
        name = self.vat_table.item(curr, 0).text()
        
        res = QMessageBox.question(self, "Usuń", f"Czy usunąć stawkę {name}?", QMessageBox.Yes | QMessageBox.No)
        if res == QMessageBox.Yes:
            db = next(get_db())
            try:
                db.query(VatRate).filter(VatRate.id == rid).delete()
                db.commit()
                self.load_vat_rates(db)
            finally:
                db.close()
                
    def load_lump_rates(self, db):
        rows = db.query(LumpSumRate).all()
        self.lump_table.setRowCount(0)
        for r in rows:
            row_idx = self.lump_table.rowCount()
            self.lump_table.insertRow(row_idx)
            self.lump_table.setItem(row_idx, 0, QTableWidgetItem(str(r.name)))
            self.lump_table.setItem(row_idx, 1, QTableWidgetItem(str(r.rate)))
            self.lump_table.item(row_idx, 0).setData(Qt.UserRole, r.id)

    def add_lump_rate(self):
        name, ok1 = QInputDialog.getText(self, "Nowa Stawka Ryczałtu", "Nazwa (np. 12%):")
        if not ok1 or not name: return
        
        val_str, ok2 = QInputDialog.getText(self, "Nowa Stawka Ryczałtu", "Wartość dziesiętna (np. 0.12):")
        if not ok2 or not val_str: return
        
        try:
            val = float(val_str.replace(",", "."))
        except ValueError:
            QMessageBox.warning(self, "Błąd", "Nieprawidłowa wartość liczbowa!")
            return
            
        db = next(get_db())
        try:
            rate = LumpSumRate(name=name, rate=val)
            db.add(rate)
            db.commit()
            self.load_lump_rates(db)
        except Exception as e:
            QMessageBox.critical(self, "Błąd", str(e))
        finally:
            db.close()

    def delete_lump_rate(self):
        curr = self.lump_table.currentRow()
        if curr < 0: return
        
        rid = self.lump_table.item(curr, 0).data(Qt.UserRole)
        name = self.lump_table.item(curr, 0).text()
        
        res = QMessageBox.question(self, "Usuń", f"Czy usunąć stawkę {name}?", QMessageBox.Yes | QMessageBox.No)
        if res == QMessageBox.Yes:
            db = next(get_db())
            try:
                db.query(LumpSumRate).filter(LumpSumRate.id == rid).delete()
                db.commit()
                self.load_lump_rates(db)
            finally:
                db.close()

    def load_numbering(self, db):
        # Clear existing
        for i in range(self.numbering_layout.count()):
             w = self.numbering_layout.itemAt(0).widget()
             if w: w.setParent(None)
        self.numbering_rows = []

        # Define schema definitions logic similar to Flet
        defs = [
            (InvoiceCategory.SALES, InvoiceType.VAT, "Faktura Sprzedaży (VAT)"),
            (InvoiceCategory.SALES, InvoiceType.RYCZALT, "Faktura Sprzedaży (Ryczałt)"),
            (InvoiceCategory.SALES, InvoiceType.KOREKTA, "Korekta Sprzedaży"),
            (InvoiceCategory.PURCHASE, InvoiceType.VAT, "Faktura Zakupu"),
        ]
        
        # Add Rows
        for cat, typ, label in defs:
            setting = db.query(NumberingSetting).filter(
                NumberingSetting.invoice_category == cat,
                NumberingSetting.invoice_type == typ
            ).first()
            
            row = NumberingRow(cat, typ, label, setting)
            self.numbering_layout.addWidget(row)
            self.numbering_rows.append(row)
            
        self.numbering_layout.addStretch()

    def _load_ksef_credentials_to_ui(self, env):
        if not hasattr(self, "current_config") or not self.current_config:
            return

        if env == "prod":
            # Decrypt PROD
            token_enc = self.current_config.ksef_token
            pass_enc = self.current_config.ksef_private_key_pass
            
            self.ksef_token.setText(SecurityManager.decrypt(token_enc) if token_enc else "")
            self.key_pass_edit.setText(SecurityManager.decrypt(pass_enc) if pass_enc else "")
            
            # Update labels based on content presence
            if self.current_config.ksef_cert_content:
                self.lbl_cert_status.setText("Zapisany w bazie")
                self.lbl_cert_status.setStyleSheet("color: green")
            else:
                self.lbl_cert_status.setText("[Brak]")
                self.lbl_cert_status.setStyleSheet("color: red")
                
            if self.current_config.ksef_private_key_content:
                self.lbl_key_status.setText("Zapisany w bazie")
                self.lbl_key_status.setStyleSheet("color: green")
            else:
                self.lbl_key_status.setText("[Brak]")
                self.lbl_key_status.setStyleSheet("color: red")
        else:
            # Decrypt TEST
            token_enc = getattr(self.current_config, 'ksef_token_test', '')
            pass_enc = getattr(self.current_config, 'ksef_private_key_pass_test', '')
            
            self.ksef_token.setText(SecurityManager.decrypt(token_enc) if token_enc else "")
            self.key_pass_edit.setText(SecurityManager.decrypt(pass_enc) if pass_enc else "")

            if getattr(self.current_config, 'ksef_cert_content_test', None):
                self.lbl_cert_status.setText("Zapisany w bazie (Test)")
                self.lbl_cert_status.setStyleSheet("color: green")
            else:
                self.lbl_cert_status.setText("[Brak Test]")
                self.lbl_cert_status.setStyleSheet("color: red")
                
            if getattr(self.current_config, 'ksef_private_key_content_test', None):
                self.lbl_key_status.setText("Zapisany w bazie (Test)")
                self.lbl_key_status.setStyleSheet("color: green")
            else:
                self.lbl_key_status.setText("[Brak Test]")
                self.lbl_key_status.setStyleSheet("color: red")

    def _save_ui_credentials_to_mem_config(self, env):
        if not hasattr(self, "current_config") or not self.current_config:
            return

        # If data is pending (loaded from file but not saved to main struct yet), 
        # normally we save on "Zapisz" button, but if user switches env, we should probably 
        # transiently keep it or warn?
        # To simplify: We won't save pending content on Env Switch, only on global Save.
        # But we must preserve text fields.
        
        token_plain = self.ksef_token.text()
        pass_plain = self.key_pass_edit.text()
        
        token_enc = SecurityManager.encrypt(token_plain) if token_plain else None
        pass_enc = SecurityManager.encrypt(pass_plain) if pass_plain else None
        
        if env == "prod":
            self.current_config.ksef_token = token_enc
            self.current_config.ksef_private_key_pass = pass_enc
        else:
            self.current_config.ksef_token_test = token_enc
            self.current_config.ksef_private_key_pass_test = pass_enc

    def on_env_change(self, new_env):
        old_env = getattr(self, "last_env", "prod")
        
        # Avoid saving if we are just initializing
        self._save_ui_credentials_to_mem_config(old_env)
        self._load_ksef_credentials_to_ui(new_env)
        self.last_env = new_env
        
        # Don't show popup on startup (when sender is None means internal call or similar check needed? 
        # Actually sender() might not be reliable here if called manually)
        # But we are calling it via signal. 
        # When initializing in load_config, we manually set index, which triggers this signal?
        # A simple check is to see if window is visible? 
        if self.isVisible() and new_env == "test":
             QMessageBox.information(
                 self, 
                 "KSeF Demo", 
                 "Wybrałeś środowisko testowe.\n\n"
                 "Tokeny oraz certyfikaty dla tego środowiska możesz wygenerować na stronie:\n"
                 "https://ksef-test.mf.gov.pl/web/ (Wymagane logowanie profilem zaufanym lub podpisem)"
             )

    def save_all(self):
        db = next(get_db())
        try:
            # Company
            config = db.query(CompanyConfig).first()
            if not config:
                config = CompanyConfig()
                db.add(config)
            
            if hasattr(self, "current_config") and self.current_config:
                self._save_ui_credentials_to_mem_config(self.ksef_env.currentData())
            
            # Identity
            config.is_natural_person = self.is_natural_person_cb.isChecked()
            config.first_name = self.first_name.text()
            config.last_name = self.last_name.text()
            config.date_of_birth = self.birth_date.date().toPython()
            config.tax_office_code = self.tax_office_combo.currentData()
            config.email = self.email.text()
            config.phone_number = self.phone_number.text()

            config.company_name = self.company_name.text()
            config.nip = self.nip.text()
            config.regon = self.regon.text()
            config.address = self.address.text()
            config.city = self.city.text()
            config.postal_code = self.postal.text()
            config.country = self.country.text()
            config.country_code = self.country_code.text()
            config.bank_account = self.bank_account.text()
            config.bank_name = self.bank_name.text()
            config.swift_code = self.swift_code.text()
            config.bdo = self.bdo_number.text()
            config.krs = self.krs.text()
            config.share_capital = self.share_capital.text()
            config.court_info = self.court_info.toPlainText()
            config.footer_extra = self.footer_extra.toPlainText()
            config.is_vat_payer = self.is_vat_cb.isChecked()
            
            # Exemption
            if not config.is_vat_payer:
                config.vat_exemption_basis_type = self.ve_type.currentData()
                config.vat_exemption_basis = self.ve_desc.text()
            else:
                config.vat_exemption_basis_type = None
                config.vat_exemption_basis = None
            
            # KSeF General
            config.ksef_environment = self.ksef_env.currentData()
            config.ksef_auth_mode = "CERT" if self.rb_cert.isChecked() else "TOKEN"

            # KSeF Credentials - Save ALL from memory config
            # (Because the user might have switched envs, edited, and we need to save everything)
            
            # Helper to update content from pending
            # We apply pending content only to the currently selected environment at the time of loading?
            # Actually pending_cert_content is set when user clicks load. 
            # We assume user loads file for CURRENT visible environment tab/selection.
            
            selected_env_for_upload = self.ksef_env.currentData()
            
            if self.pending_cert_content:
                if selected_env_for_upload == "prod":
                    config.ksef_cert_content = self.pending_cert_content
                else:
                    config.ksef_cert_content_test = self.pending_cert_content
                self.pending_cert_content = None
            
            if self.pending_key_content:
                if selected_env_for_upload == "prod":
                    config.ksef_private_key_content = self.pending_key_content
                else:
                    config.ksef_private_key_content_test = self.pending_key_content
                self.pending_key_content = None

            if hasattr(self, "current_config") and self.current_config:
                # Refresh current Env data from UI to mem config before saving
                current_env_from_ui = self.ksef_env.currentData()
                self._save_ui_credentials_to_mem_config(current_env_from_ui)
                
                # PROD
                config.ksef_token = self.current_config.ksef_token
                config.ksef_private_key_pass = self.current_config.ksef_private_key_pass
                
                # TEST
                config.ksef_token_test = getattr(self.current_config, "ksef_token_test", None)
                config.ksef_private_key_pass_test = getattr(self.current_config, "ksef_private_key_pass_test", None)
            else:
                # Fallback if no memory config exists (unlikely if load_config ran)
                # Just save current UI to current env
                current_env = self.ksef_env.currentData()
                token_val = SecurityManager.encrypt(self.ksef_token.text()) if self.ksef_token.text() else None
                pass_val = SecurityManager.encrypt(self.key_pass_edit.text()) if self.key_pass_edit.text() else None

                if current_env == "prod":
                    config.ksef_token = token_val
                    config.ksef_priv_key_pass = pass_val # Not used?
                    
                    # config.ksef_cert_path and path fields are obsolete
                    config.ksef_private_key_pass = pass_val
                else:
                    config.ksef_token_test = token_val
                    config.ksef_private_key_pass_test = pass_val

            
            # Taxation Limits and Rates
            config.is_vat_payer = self.is_vat_cb.isChecked()
            config.vat_settlement_method = self.vat_method_combo.currentData()
            
            config.vat_exemption_subject_based = self.vat_subject_based_cb.isChecked()
            config.vat_exemption_limit = int(self.vat_limit_spin.value())
            config.vat_warning_threshold = int(self.vat_warning_spin.value())
            
            config.tax_scale_limit_1 = int(self.scale_limit_1.value())
            config.tax_scale_rate_1 = self.scale_rate_1.value() / 100.0
            config.tax_scale_deduction = int(self.scale_deduction.value())
            config.tax_scale_rate_2 = self.scale_rate_2.value() / 100.0
            
            config.solidarity_levy_limit = int(self.solidarity_limit.value())
            config.solidarity_levy_rate = self.solidarity_rate.value() / 100.0
            
            config.tax_linear_rate = self.linear_rate.value() / 100.0
            
            ts_name = self.tax_dd.currentData()
            if ts_name: 
                config.taxation_form = TaxationForm[ts_name]
                # Backward compatibility / Sync with old field if needed
                if config.taxation_form == TaxationForm.RYCZALT:
                    config.default_tax_system = TaxSystem.RYCZALT
                else:
                    config.default_tax_system = TaxSystem.VAT
            
            db.commit()

            # Numbering
            for row in self.numbering_rows:
                s = db.query(NumberingSetting).filter(
                    NumberingSetting.invoice_category == row.cat,
                    NumberingSetting.invoice_type == row.typ
                ).first()
                if not s:
                    s = NumberingSetting(invoice_category=row.cat, invoice_type=row.typ)
                    db.add(s)
                
                vals = row.get_values()
                s.period_type = PeriodType[vals["period"]]
                s.template = vals["template"]
            
            db.commit()
            QMessageBox.information(self, "Sukces", "Zapisano ustawienia.")
            
        except Exception as e:
            db.rollback()
            QMessageBox.critical(self, "Błąd", str(e))
        finally:
            db.close()

    def load_cert_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Wybierz certyfikat (PEM/CRT)", "", "Certyfikaty (*.pem *.crt *.cer);;Wszystkie pliki (*.*)")
        if file_path:
            try:
                with open(file_path, 'rb') as f:
                    self.pending_cert_content = f.read()
                self.lbl_cert_status.setText("Wczytano (Do zapisania)")
                self.lbl_cert_status.setStyleSheet("color: blue")
            except Exception as e:
                QMessageBox.critical(self, "Błąd", f"Błąd odczytu pliku: {e}")

    def load_key_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Wybierz klucz prywatny (PEM/KEY)", "", "Klucze (*.pem *.key);;Wszystkie pliki (*.*)")
        if file_path:
            try:
                with open(file_path, 'rb') as f:
                    self.pending_key_content = f.read()
                self.lbl_key_status.setText("Wczytano (Do zapisania)")
                self.lbl_key_status.setStyleSheet("color: blue")
            except Exception as e:
                QMessageBox.critical(self, "Błąd", f"Błąd odczytu pliku: {e}")

    def init_program_tab(self):
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Zarządzanie Użytkownikami"))
        
        self.users_table = QTableWidget()
        # Cols: ID, Username, KSeF(S), KSeF(R), Rozl, Dekl, Konf
        self.users_table.setColumnCount(7)
        self.users_table.setHorizontalHeaderLabels(["ID", "Użytkownik", "KSeF(W)", "KSeF(O)", "Rozl.", "Dekl.", "Konf."])
        self.users_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.users_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.users_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.users_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.users_table)
        
        btn_layout = QHBoxLayout()
        btn_add = QPushButton("Dodaj")
        btn_add.clicked.connect(self.add_user)
        btn_edit = QPushButton("Edytuj")
        btn_edit.clicked.connect(self.edit_user)
        btn_del = QPushButton("Usuń")
        btn_del.clicked.connect(self.delete_user)
        
        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_edit)
        btn_layout.addWidget(btn_del)
        layout.addLayout(btn_layout)
        
        self.tab_program.setLayout(layout)
        self.refresh_user_list()

    def refresh_user_list(self):
        db = next(get_db())
        try:
            users = db.query(User).all()
            self.users_table.setRowCount(0)
            for user in users:
                row = self.users_table.rowCount()
                self.users_table.insertRow(row)
                self.users_table.setItem(row, 0, QTableWidgetItem(str(user.id)))
                self.users_table.setItem(row, 1, QTableWidgetItem(user.username))
                
                # Helper to set check or cross
                def set_bool_item(col, val):
                    item = QTableWidgetItem("✓" if val else "✗")
                    item.setTextAlignment(Qt.AlignCenter)
                    item.setForeground(Qt.green if val else Qt.red)
                    self.users_table.setItem(row, col, item)

                set_bool_item(2, user.perm_send_ksef)
                set_bool_item(3, user.perm_receive_ksef)
                set_bool_item(4, user.perm_settlements)
                set_bool_item(5, user.perm_declarations)
                set_bool_item(6, user.perm_settings)

        finally:
            db.close()

    def add_user(self):
        dlg = UserDialog(self)
        if dlg.exec():
            data = dlg.get_data()
            name = data['username']
            if not name:
                 QMessageBox.warning(self, "Błąd", "Nazwa jest wymagana")
                 return
                 
            db = next(get_db())
            try:
                # Check exists
                if db.query(User).filter(User.username == name).first():
                    QMessageBox.warning(self, "Błąd", "Użytkownik istnieje")
                    return

                pwd = data['password']
                phash = hashlib.sha1(pwd.encode('utf-8')).hexdigest() if pwd else None
                
                new_user = User(
                    username=name,
                    password_hash=phash,
                    perm_send_ksef=data['perm_send_ksef'],
                    perm_receive_ksef=data['perm_receive_ksef'],
                    perm_settlements=data['perm_settlements'],
                    perm_declarations=data['perm_declarations'],
                    perm_settings=data['perm_settings']
                )
                db.add(new_user)
                db.commit()
                self.refresh_user_list()
            finally:
                db.close()

    def edit_user(self):
        row = self.users_table.currentRow()
        if row < 0: return # No selection
        
        try:
            user_id = int(self.users_table.item(row, 0).text())
        except ValueError:
            return

        db = next(get_db())
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user: return

            dlg = UserDialog(self, user)
            if dlg.exec():
                data = dlg.get_data()
                
                # Check safeguard: cannot remove settings permission from the last admin
                if user.perm_settings and not data['perm_settings']:
                    admin_count = db.query(User).filter(User.perm_settings == True).count()
                    if admin_count <= 1:
                        QMessageBox.critical(self, "Błąd", "Nie można odebrać uprawnień. Przynajmniej jeden użytkownik musi mieć dostęp do konfiguracji.")
                        return

                # Check rename conflict if name changed
                if data['username'] != user.username:
                    if db.query(User).filter(User.username == data['username']).first():
                        QMessageBox.warning(self, "Błąd", "Nazwa zajęta.")
                        return
                    user.username = data['username']
                
                pwd = data['password']
                if pwd: # Only update if provided
                     user.password_hash = hashlib.sha1(pwd.encode('utf-8')).hexdigest()
                
                user.perm_send_ksef = data['perm_send_ksef']
                user.perm_receive_ksef = data['perm_receive_ksef']
                user.perm_settlements = data['perm_settlements']
                user.perm_declarations = data['perm_declarations']
                user.perm_settings = data['perm_settings']
                
                db.commit()
                self.refresh_user_list()
        finally:
            db.close()

    def delete_user(self):
        row = self.users_table.currentRow()
        if row < 0: return
        user_id = int(self.users_table.item(row, 0).text())
        confirm = QMessageBox.question(self, "Potwierdź", "Usunąć użytkownika?", QMessageBox.Yes | QMessageBox.No)
        if confirm == QMessageBox.Yes:
            db = next(get_db())
            try:
                user = db.query(User).filter(User.id == user_id).first()
                if user:
                    # Check safeguard
                    if user.perm_settings:
                        admin_count = db.query(User).filter(User.perm_settings == True).count()
                        if admin_count <= 1:
                            QMessageBox.critical(self, "Błąd", "Nie można usunąć ostatniego użytkownika z dostępem do konfiguracji.")
                            return

                    db.delete(user)
                    db.commit()
                    self.refresh_user_list()
            finally:
                db.close()


    def init_database_tab(self):
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Działania na bazie danych (ksef_invoice.db)"))
        
        btn_backup = QPushButton("Wykonaj Kopię Zapasową (Backup)")
        btn_backup.clicked.connect(self.backup_db)
        
        btn_restore = QPushButton("Przywróć Bazę z Kopii")
        btn_restore.clicked.connect(self.restore_db)
        
        btn_reset = QPushButton("Resetuj Bazę Danych (Usuń dane)")
        btn_reset.setStyleSheet("background-color: #ffcccc; color: red;")
        btn_reset.clicked.connect(self.reset_db)
        
        layout.addWidget(btn_backup)
        layout.addWidget(btn_restore)
        layout.addSpacing(20)
        layout.addWidget(btn_reset)
        layout.addStretch()
        
        self.tab_database.setLayout(layout)

    def backup_db(self):
        src = "ksef_invoice.db"
        if not os.path.exists(src):
            QMessageBox.warning(self, "Błąd", "Plik bazy danych nie istnieje.")
            return

        now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"ksef_invoice_backup_{now}.db"
        
        file_path, _ = QFileDialog.getSaveFileName(self, "Zapisz kopię", default_name, "SQLite DB (*.db);;All Files (*.*)")
        if file_path:
            try:
                shutil.copy2(src, file_path)
                QMessageBox.information(self, "Sukces", "Kopia zapasowa utworzona pomyślnie.")
            except Exception as e:
                QMessageBox.critical(self, "Błąd", f"Nie udało się utworzyć kopii: {e}")

    def restore_db(self):
        confirm = QMessageBox.warning(self, "Ostrzeżenie", "Przywrócenie bazy nadpisze obecne dane! Kontynuować?", QMessageBox.Yes | QMessageBox.No)
        if confirm != QMessageBox.Yes: return
        
        file_path, _ = QFileDialog.getOpenFileName(self, "Wybierz plik kopii", "", "SQLite DB (*.db);;All Files (*.*)")
        if file_path:
            try:
                shutil.copy2(file_path, "ksef_invoice.db")
                QMessageBox.information(self, "Sukces", "Baza przywrócona. Zrestartuj aplikację.")
            except Exception as e:
                QMessageBox.critical(self, "Błąd", f"Nie udało się przywrócić bazy: {e}")

    def reset_db(self):
        confirm = QMessageBox.critical(self, "KRYTYCZNE", "To usunie WSZYSTKIE dane (Klientów, Faktury, Ustawienia). Czy na pewno?", QMessageBox.Yes | QMessageBox.No)
        if confirm == QMessageBox.Yes:
             confirm2 = QMessageBox.critical(self, "OSTATECZNE POTWIERDZENIE", "Czy na pewno chcesz wyczyścić bazę?", QMessageBox.Yes | QMessageBox.No)
             if confirm2 == QMessageBox.Yes:
                 try:
                     from database.models import Base
                     from database.engine import engine
                     Base.metadata.drop_all(bind=engine)
                     Base.metadata.create_all(bind=engine)
                     QMessageBox.information(self, "Info", "Baza została zresetowana.")
                     # Try to reload config to reset UI state if possible
                     self.load_config() 
                 except Exception as e:
                     QMessageBox.critical(self, "Błąd", f"Reset nieudany: {e}")

class NumberingRow(QWidget):
    def __init__(self, cat, typ, label, setting):
        super().__init__()
        self.cat = cat
        self.typ = typ
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        
        self.label = QLabel(label)
        self.label.setFixedWidth(200)
        
        self.period_combo = QComboBox()
        self.period_combo.addItem("Roczna (Nr/Rok)", "YEARLY")
        self.period_combo.addItem("Miesięczna (Nr/Msc/Rok)", "MONTHLY")
        
        # Init values
        curr_period = "YEARLY"
        if setting and setting.period_type:
            curr_period = setting.period_type.name
        
        idx = self.period_combo.findData(curr_period)
        if idx >= 0: self.period_combo.setCurrentIndex(idx)
        
        self.template_edit = QLineEdit()
        if setting and setting.template:
            self.template_edit.setText(setting.template)
        else:
            # Default logic
            if typ == InvoiceType.KOREKTA: txt = "KOR/{nr}/{rok}"
            elif cat == InvoiceCategory.PURCHASE: txt = "ZAK/{nr}/{rok}"
            else: txt = "{nr}/{rok}"
            self.template_edit.setText(txt)

        self.period_combo.currentIndexChanged.connect(self.on_period_change)

        layout.addWidget(self.label)
        layout.addWidget(self.period_combo)
        layout.addWidget(QLabel("Wzorzec:"))
        layout.addWidget(self.template_edit)
        
    def on_period_change(self):
        new_period = self.period_combo.currentData()
        tpl = self.template_edit.text()
        
        if new_period == "MONTHLY":
            if "{miesiac}" not in tpl:
                if "{rok}" in tpl:
                    tpl = tpl.replace("{rok}", "{miesiac}/{rok}")
                else:
                    tpl += "/{miesiac}"
        elif new_period == "YEARLY":
            tpl = tpl.replace("{miesiac}", "")
            
        # Cleanup
        tpl = tpl.replace("//", "/").replace("--", "-").strip("/")
        self.template_edit.setText(tpl)

    def get_values(self):
        return {
            "period": self.period_combo.currentData(),
            "template": self.template_edit.text()
        }
