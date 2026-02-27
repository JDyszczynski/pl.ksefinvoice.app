import flet as ft
from database.engine import get_db, init_db
from database.models import User, InvoiceCategory, CompanyConfig, TaxSystem
from gui.warehouse_view import WarehouseView
from gui.contractor_view import ContractorView
from gui.invoice_view import InvoiceView
from gui.settings_view import SettingsView
from gui.settlements_view import SettlementsView
from gui.login_view import LoginView
from gui.utils import resource_path

def main(page: ft.Page):
    try:
        init_db()
    except Exception as e:
        print(f"Błąd bazy: {e}")

    page.title = "KSeF Invoice App"
    page.window_icon = resource_path("logo.256.ico")
    page.padding = 0
    # FIX: contrast issues by setting light theme explicitly
    page.theme_mode = ft.ThemeMode.LIGHT
    # Ważne dla uniknięcia błędów GTK - ustawiamy tło
    page.bgcolor = ft.Colors.WHITE

    # Root container - nigdy nie używamy page.clean()
    root_container = ft.Container(expand=True)
    page.add(root_container)
    
    # --- GLOBAL FILE PICKERS REMOVED (Using Transient Strategy) ---
    # --------------------------------------------------------------

    def logout(e=None):
        root_container.content = LoginView(on_login_success=login_success)
        page.update()

    def login_success(user):
        root_container.content = MainAppLayout(page, user, logout_callback=logout)
        page.update()

    # Na start pokazujemy logowanie
    # root_container.content = LoginView(on_login_success=login_success)
    # page.update()

    # AUTO LOGOWANIE (DEBUG)
    try:
        from database.engine import get_db
        db = next(get_db())
        # Sprawdź czy jest admin, jak nie to stwórz (aby self.user.id i inne pola działały poprawnie, jeśli będą potrzebne)
        user = db.query(User).filter(User.username == "admin").first()
        if not user:
             import hashlib
             h = hashlib.sha1("admin".encode()).hexdigest()
             user = User(username="admin", password_hash=h, perm_settings=True, perm_send_ksef=True)
             db.add(user)
             db.commit()
             db.refresh(user)
        
        # Jeśli i tak błąd bazy, użyj dummy
    except Exception as e:
        print(f"Błąd autologowania z bazy: {e}")
        # Dummy fallback
        user = User(username="admin", perm_settings=True)

    login_success(user)

class MainAppLayout(ft.Column):
    def __init__(self, page, user, logout_callback):
        super().__init__(expand=True, spacing=0)
        self.app_page = page
        
        # --- GLOBAL PICKERS ALREADY INIT IN main() ---
        # No re-creation here.
        # --------------------------------

        self.user = user
        self.logout_callback = logout_callback
        
        # Determine label based on config
        sales_label = "Faktury Sprzedaży"
        try:
             db = next(get_db())
             config = db.query(CompanyConfig).first()
             if config and config.default_tax_system == TaxSystem.RYCZALT:
                 sales_label = "Rachunki"
             db.close()
        except:
             pass

        # Menu górne
        self.menu_row = ft.Container(
            padding=10,
            bgcolor=ft.Colors.BLUE_GREY_50,
            content=ft.Row(
                [
                    ft.Text("KSeF Invoice", size=20, weight="bold", color=ft.Colors.BLUE_GREY_900),
                    ft.VerticalDivider(),
                    ft.TextButton(sales_label, on_click=lambda e: self.change_view(1), icon="output"),
                    ft.TextButton("Faktury Zakupu", on_click=lambda e: self.change_view(2), icon="input"),
                    ft.TextButton("Kontrahenci", on_click=lambda e: self.change_view(3), icon="people"),
                    ft.TextButton("Towary", on_click=lambda e: self.change_view(4), icon="inventory_2"),
                    ft.TextButton("Rozliczenia", on_click=lambda e: self.change_view(6), icon="attach_money"),
                    ft.TextButton("Konfiguracja", on_click=lambda e: self.change_view(5), icon="settings"),
                    ft.Container(expand=True), # Spacer
                    ft.Text(f"Zalogowany: {user.username}", size=12),
                    ft.IconButton(icon=ft.Text("⏻", size=20), tooltip="Wyloguj", on_click=logout_callback)
                ]
            )
        )
        
        # Obszar treści
        self.content_area = ft.Container(expand=True, padding=20)
        
        self.controls = [
            self.menu_row,
            ft.Divider(height=1, thickness=1),
            self.content_area
        ]
        
        # Startowy widok
        self.change_view(0, should_update=False)

    def change_view(self, index, should_update=True):
        self.content_area.content = None
        
        if index == 0:
            self.content_area.content = self._build_dashboard()
        elif index == 1:
            self.content_area.content = InvoiceView(category=InvoiceCategory.SALES)
        elif index == 2:
            self.content_area.content = InvoiceView(category=InvoiceCategory.PURCHASE)
        elif index == 3:
            self.content_area.content = ContractorView()
        elif index == 4:
            self.content_area.content = WarehouseView()
        elif index == 5:
            # Sprawdzenie uprawnień dla konfiguracji
            if self.user.role == 'admin':
                self.content_area.content = SettingsView()
            else:
                 self.content_area.content = ft.Text("Brak uprawnień do konfiguracji (wymagany administrator)", color="red")
        elif index == 6:
            self.content_area.content = SettlementsView()
        
        if should_update:
            self.update()

    def _build_dashboard(self):
        return ft.Container(
            alignment=ft.Alignment(0, 0),
            content=ft.Column([
                 ft.Text(f"Witaj w systemie KSeF Invoice, {self.user.username}", size=30),
                 ft.Text("Wybierz moduł z menu powyżej", color="grey")
            ], horizontal_alignment="center")
        )
