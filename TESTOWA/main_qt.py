import sys
import traceback
import warnings
from cryptography.utils import CryptographyDeprecationWarning
warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QStackedWidget, QMessageBox, QFrame)
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QIcon
from database.engine import init_db, get_db
from database.migrations import check_and_migrate_db
from database.models import User
from gui_qt.login_view import LoginView
from gui_qt.invoice_view import InvoiceView
from gui_qt.resource_path import resource_path
from gui_qt.utils import safe_restore_geometry, save_geometry

class MainWindow(QMainWindow):
    APP_VERSION = "1.0.5 (Beta)"

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"KSeF Invoice (TEST) v{self.APP_VERSION}")
        self.setWindowIcon(QIcon(resource_path("logo.ico")))
        
        # Ustawienia aplikacji (wielkość okna)
        self.settings = QSettings("JaroslawDyszczynski", "KSeFInvoice")
        
        # New safe restore
        safe_restore_geometry(self, "windowGeometry", default_percent_w=0.8, default_percent_h=0.8)
        
        # Logging setup
        import logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # Inicjalizacja sprawdzania aktualizacji
        try:
            from gui_qt.update_checker import UpdateCheckerThread
            self.update_checker = UpdateCheckerThread(self.APP_VERSION)
            self.update_checker.update_available.connect(self.show_update_dialog)
            self.update_checker.start()
        except Exception as e:
            print(f"Błąd inicjalizacji aktualizacji: {e}")

        # Inicjalizacja bazy
        try:
            init_db()
            check_and_migrate_db()
            self._ensure_admin()
        except Exception as e:
            QMessageBox.critical(self, "Błąd Bazy", f"Nie można połączyć z bazą danych: {e}")

        # Główny kontener
        self.central_widget = QStackedWidget()
        self.setCentralWidget(self.central_widget)

        # Widoki
        self.login_view = LoginView(self.on_login_success, version_string=self.APP_VERSION)
        self.app_layout = QWidget() # Placeholder dla głównego interfejsu
        
        self.central_widget.addWidget(self.login_view)
        # self.central_widget.addWidget(self.app_layout) # Dodamy później

        self.current_user = None

    def closeEvent(self, event):
        save_geometry(self, "windowGeometry")
        super().closeEvent(event)

    def show_update_dialog(self, new_version, download_url):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        
        msg = QMessageBox(self)
        msg.setWindowTitle("Dostępna aktualizacja")
        msg.setText(f"Dostępna jest nowa wersja programu: {new_version}")
        msg.setInformativeText("Czy chcesz pobrać aktualizację teraz?")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.Yes)
        
        if msg.exec() == QMessageBox.Yes:
            QDesktopServices.openUrl(QUrl(download_url))

    def _ensure_admin(self):
        # Disable auto-admin creation to allow "First Run" logic in LoginView
        pass

    def on_login_success(self, user):
        self.current_user = user
        self.setup_main_layout()
        self.central_widget.addWidget(self.app_layout)
        self.central_widget.setCurrentWidget(self.app_layout)

    def setup_main_layout(self):
        # Tworzenie głównego interfejsu (Menu + Content)
        self.app_layout = QWidget()
        main_layout = QVBoxLayout(self.app_layout)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Menu Bar
        menu_bar = QFrame()
        menu_bar.setFrameShape(QFrame.StyledPanel)
        menu_layout = QHBoxLayout(menu_bar)
        
        title = QLabel("KSeF Invoice")
        font = title.font()
        font.setBold(True)
        # font.setPointSize(16) # Use system font size or just bold
        title.setFont(font)
        # title.setStyleSheet("font-weight: bold; font-size: 16px; padding: 10px;") # Removed manual style
        menu_layout.addWidget(title)
        
        # Przyciski menu
        self.btn_sales = QPushButton("Faktury Sprzedaży")
        self.btn_purchase = QPushButton("Faktury Zakupu")
        self.btn_contractors = QPushButton("Kontrahenci")
        self.btn_warehouse = QPushButton("Towary")
        self.btn_settlements = QPushButton("Rozrachunki")
        self.btn_declarations = QPushButton("Deklaracje")
        self.btn_config = QPushButton("Konfiguracja")
        self.btn_logout = QPushButton("Wyloguj")

        for btn in [self.btn_sales, self.btn_purchase, self.btn_contractors, self.btn_warehouse, self.btn_settlements, self.btn_declarations, self.btn_config, self.btn_logout]:
            # Removed manual stylesheet to use system theme
            menu_layout.addWidget(btn)
        
        menu_layout.addStretch()
        user_info = QLabel(f"Zalogowany: {self.current_user.username}")
        # user_info.setStyleSheet("padding: 10px;")
        menu_layout.addWidget(user_info)

        # Przycisk "O mnie"
        self.btn_about = QPushButton("O mnie")
        self.btn_about.setIcon(QIcon(resource_path("logo.ico")))
        self.btn_about.clicked.connect(self.show_about_dialog)
        menu_layout.addWidget(self.btn_about)

        # Connect signals
        # Use existing buttons directly instead of lambda index hardcoding if possible, or keep indices
        self.btn_sales.clicked.connect(lambda: self.switch_content(1))
        self.btn_purchase.clicked.connect(lambda: self.switch_content(2))
        self.btn_contractors.clicked.connect(lambda: self.switch_content(3))
        self.btn_warehouse.clicked.connect(lambda: self.switch_content(4))
        self.btn_config.clicked.connect(lambda: self.switch_content(5))
        self.btn_settlements.clicked.connect(lambda: self.switch_content(6))
        self.btn_declarations.clicked.connect(lambda: self.switch_content(7))
        self.btn_logout.clicked.connect(self.logout)

        main_layout.addWidget(menu_bar)

        # Apply Permissions
        if self.current_user:
            # Sales/Purchase (KSeF Limits) 
            # Note: For now, if no KSeF send/recv, we don't block the whole view, 
            # but maybe we should disable specific buttons inside.
            # However, user asked to limit things like "Access to settlements".
            
            if not getattr(self.current_user, 'perm_settlements', False):
                self.btn_settlements.hide()
            
            if not getattr(self.current_user, 'perm_declarations', False):
                self.btn_declarations.hide()
                
            if not getattr(self.current_user, 'perm_settings', False):
                self.btn_config.hide()
            
            # For send/receive limits, we need to pass the user to the views or check there.
            # I will pass current_user to InvoiceViews later or now.
            # Let's simple check permissions when initializing views?
            # Or better, pass user permissions to views.

        # Content Area
        self.content_stack = QStackedWidget()
        main_layout.addWidget(self.content_stack)

        # Inicjalizacja widoków
        from database.models import InvoiceCategory
        from gui_qt.welcome_view import WelcomeView
        
        self.welcome_view = WelcomeView(self.APP_VERSION)
        
        # --- VIEWS ---
        # Pass user permissions to InvoiceView if needed, or enforce via inheritance
        self.sales_view = InvoiceView(InvoiceCategory.SALES)
        self.sales_view.set_permissions(self.current_user)
        
        self.purchase_view = InvoiceView(InvoiceCategory.PURCHASE)
        self.purchase_view.set_permissions(self.current_user)
        
        
        from gui_qt.contractor_view import ContractorView
        self.contractors_view = ContractorView()
        
        from gui_qt.warehouse_view import WarehouseView
        self.warehouse_view = WarehouseView()
        
        from gui_qt.settings_view import SettingsView
        self.settings_view = SettingsView()

        from gui_qt.settlements_view import SettlementsView
        self.settlements_view = SettlementsView()
        
        from gui_qt.declarations_view import DeclarationsView
        self.declarations_view = DeclarationsView()


        # Add to Stack
        # 0: Welcome
        self.content_stack.addWidget(self.welcome_view)
        # 1: Sales
        self.content_stack.addWidget(self.sales_view)
        # 2: Purchase
        self.content_stack.addWidget(self.purchase_view)
        # 3: Contractors
        self.content_stack.addWidget(self.contractors_view)
        # 4: Warehouse
        self.content_stack.addWidget(self.warehouse_view)
        # 5: Settings
        self.content_stack.addWidget(self.settings_view)
        # 6: Settlements
        self.content_stack.addWidget(self.settlements_view)
        # 7: Declarations
        self.content_stack.addWidget(self.declarations_view)

    def switch_content(self, index):
        self.content_stack.setCurrentIndex(index)

    def logout(self):
        self.current_user = None
        self.login_view.reset()
        self.central_widget.setCurrentWidget(self.login_view)

    def show_about_dialog(self):
        """
        Wyświetla okno 'O mnie'.
        """
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTextBrowser, QDialogButtonBox, QLabel, QWidget
        
        about_title = f"O mnie - KSeF Invoice v{self.APP_VERSION}"
        
        qr_path = resource_path("QR_buycoffee.png").replace("\\", "/") # Ensure forward slashes for HTML

        # Header Info (Obok Logo)
        info_html = f"""
        <h3>KSeF Invoice v{self.APP_VERSION}</h3>
        <p>Profesjonalne narzędzie do obsługi faktur KSeF.</p>
        <p><b>Autor:</b> Jarosław Dyszczyński<br>
        <b>Kontakt:</b> <a href="mailto:jarek@dyszczynski.pl">jarek@dyszczynski.pl</a></p>
        """

        # Scrollable Content (Support + License)
        about_text = f"""
        <hr>
        
        <p><b>Wesprzyj rozwój projektu:</b><br>
        Jeśli program Ci pomaga, rozważ postawienie kawy: <br>
        <a href="https://buycoffee.to/jarekd">👉 buycoffee.to/jarekd</a></p>
        <p align="center"><img src="{qr_path}" width="150" height="150"></p>
        
        <hr>
        
        <p><b>LICENCJA I OGRANICZENIE ODPOWIEDZIALNOŚCI:</b></p>
        
        <p><small>
        <b>1. STATUS PROGRAMU</b><br>
        Program KSeF Invoice jest udostępniany bezpłatnie w wersji rozwojowej (BETA). 
        Autor dokłada wszelkich starań, aby aplikacja działała poprawnie i zgodnie 
        z dokumentacją techniczną Ministerstwa Finansów, jednak program może zawierać błędy.
        <br><br>
        
        <b>2. BRAK GWARANCJI</b><br>
        PROGRAM JEST DOSTARCZANY "TAKIM, JAKIM JEST" (AS IS), BEZ JAKIEJKOLWIEK 
        GWARANCJI, WYRAŹNEJ LUB DOROZUMIANEJ. UŻYTKOWNIK KORZYSTA Z PROGRAMU 
        WYŁĄCZNIE NA WŁASNĄ ODPOWIEDZIALNOŚĆ.
        <br><br>
        
        <b>3. OGRANICZENIE ODPOWIEDZIALNOŚCI</b><br>
        Autor w żadnym wypadku nie ponosi odpowiedzialności za jakiekolwiek szkody 
        (w tym, bez ograniczeń, szkody wynikające ze strat w zyskach przedsiębiorstwa, 
        przerw w działalności, utraty informacji gospodarczej lub innych strat 
        pieniężnych) powstałe w wyniku używania lub niemożności używania niniejszego 
        programu, nawet jeśli autor został powiadomiony o możliwości wystąpienia takich szkód.
        <br><br>
        
        <b>4. WERYFIKACJA DANYCH</b><br>
        Użytkownik jest zobowiązany do każdorazowej weryfikacji poprawności wyników 
        działania programu (w szczególności poprawności wygenerowanych plików XML 
        oraz statusów wysyłki do systemu KSeF).
        <br><br>
        
        <b>5. BIBLIOTEKI OSÓB TRZECICH</b><br>
        Program wykorzystuje bibliotekę PySide6 (Qt) na licencji GNU LGPL v3. 
        Pozostałe biblioteki (SQLAlchemy, cryptography, signxml, fpdf2) są używane 
        zgodnie z ich odpowiednimi licencjami (MIT/Apache/LGPL).
        <br><br>
        Copyright © 2024-2026 Jarosław Dyszczyński
        </small></p>
        """

        dialog = QDialog(self)
        dialog.setWindowTitle(about_title)
        dialog.resize(500, 600) 
        
        logo_path = resource_path("logo.ico")
        if logo_path:
             dialog.setWindowIcon(QIcon(logo_path))
        
        layout = QVBoxLayout(dialog)
        
        # --- Top Section: Logo + Info ---
        top_widget = QWidget()
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(0,0,0,0)
        
        # Logo
        if logo_path:
             lbl_logo = QLabel()
             # Slightly larger logo for side-by-side view
             pix = QIcon(logo_path).pixmap(80, 80)
             lbl_logo.setPixmap(pix)
             lbl_logo.setAlignment(Qt.AlignTop | Qt.AlignLeft)
             top_layout.addWidget(lbl_logo)
        
        # Info Text
        lbl_info = QLabel()
        lbl_info.setTextFormat(Qt.RichText)
        lbl_info.setText(info_html)
        lbl_info.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        lbl_info.setOpenExternalLinks(True)
        top_layout.addWidget(lbl_info)
        
        top_layout.addStretch() # Push everything to the left/top
        layout.addWidget(top_widget)

        # --- Middle Section: Scrollable ---
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(about_text)
        layout.addWidget(browser)
        
        # --- Bottom Section: Close Button ---
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok)
        btn_box.accepted.connect(dialog.accept)
        layout.addWidget(btn_box)
        
        dialog.exec()

if __name__ == "__main__":
    # Global Exception Hook
    def excepthook(exc_type, exc_value, exc_tb):
        traceback.print_exception(exc_type, exc_value, exc_tb)
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = excepthook

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
