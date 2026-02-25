import flet as ft
import traceback
import logging
import re
import asyncio
import threading
import time
from datetime import datetime
from sqlalchemy import extract
from database.engine import get_db
from database.models import CompanyConfig, VatRate, TaxSystem, NumberingSetting, InvoiceType, InvoiceCategory, PeriodType, Invoice
from ksef.client import KsefClient
from logic.security import SecurityManager

logger = logging.getLogger(__name__)

class NumberingRow(ft.Container):
    def __init__(self, cat, typ, label, setting):
        super().__init__(
            bgcolor=ft.Colors.WHITE, 
            padding=10, 
            border_radius=5
        )
        self.cat = cat
        self.typ = typ
        self.label_text = label
        
        # Initial values
        self.period_key = "YEARLY"
        if setting and setting.period_type:
            try:
                self.period_key = setting.period_type.value
            except:
                self.period_key = str(setting.period_type)
        
        if setting and setting.template:
            self.template_val = setting.template
        else:
            if typ == InvoiceType.KOREKTA:
                self.template_val = "KOR/{nr}/{rok}"
            elif cat == InvoiceCategory.PURCHASE:
                self.template_val = "ZAK/{nr}/{rok}"
            else:
                self.template_val = "{nr}/{rok}"
                
        # Controls
        self.lbl = ft.Text(self.label_text, width=250, weight="bold")
        
        self.template_txt = ft.TextField(
            label="Wzorzec", 
            value=self.template_val, 
            width=200, 
            hint_text="{nr}, {rok}, {miesiac}"
        )

        self.period_dd = ft.Dropdown(
            label="Okres",
            width=200,
            value=self.period_key,
            options=[
                ft.dropdown.Option(text="Roczna (Nr/Rok)", key="YEARLY"),
                ft.dropdown.Option(text="Miesięczna (Nr/Msc/Rok)", key="MONTHLY"),
            ]
        )
        # Bind checking both potential events for compatibility with this Flet version
        self.period_dd.on_change = self._on_period_change
        self.period_dd.on_select = self._on_period_change
        
        self.content = ft.Row([
            self.lbl, 
            self.period_dd, 
            self.template_txt
        ], alignment=ft.MainAxisAlignment.START)

    def _on_period_change(self, e):
        try:
            print(f"[NumberingRow Debug] Event triggered: {e.name}")
            new_period = self.period_dd.value
            if not new_period and e.control:
                 new_period = e.control.value
            
            curr_tpl = self.template_txt.value or ""
            print(f"[NumberingRow Debug] Period changed to: {new_period}, Current Tpl: {curr_tpl}")
            
            new_tpl = curr_tpl
            
            if new_period == "MONTHLY":
                if "{miesiac}" not in new_tpl:
                    if "{rok}" in new_tpl:
                        new_tpl = new_tpl.replace("{rok}", "{miesiac}/{rok}")
                    else:
                        new_tpl += "/{miesiac}"
            elif new_period == "YEARLY":
                new_tpl = new_tpl.replace("{miesiac}", "")
            
            # Cleanup
            new_tpl = new_tpl.replace("//", "/")
            new_tpl = new_tpl.replace("--", "-")
            new_tpl = new_tpl.replace("__", "_")
            if new_tpl.startswith("/"): new_tpl = new_tpl[1:]
            if new_tpl.endswith("/"): new_tpl = new_tpl[:-1]
            
            print(f"[NumberingRow Debug] New Tpl: {new_tpl}")
            
            self.template_txt.value = new_tpl
            self.template_txt.update()
            
            if self.page:
                self.page.snack_bar = ft.SnackBar(ft.Text(f"Zaktualizowano wzorzec: {new_tpl}"))
                self.page.snack_bar.open = True
                self.page.update()
                
        except Exception as ex:
            print(f"[NumberingRow Error] {ex}")
            traceback.print_exc()

    def get_values(self):
        return {
            "cat": self.cat,
            "typ": self.typ,
            "period": self.period_dd.value,
            "template": self.template_txt.value
        }

class SettingsView(ft.Column):
    def __init__(self):
        super().__init__(expand=True)
        
        # --- TAB 1: Dane Firmy ---
        self.company_name = ft.TextField(label="Nazwa Firmy", width=800)
        self.nip = ft.TextField(label="NIP", width=160)
        self.regon = ft.TextField(label="REGON", width=160)
        self.krs = ft.TextField(label="Numer KRS", width=160)
        self.bdo = ft.TextField(label="Numer BDO", width=160)
        self.address = ft.TextField(label="Adres")
        self.city = ft.TextField(label="Miasto")
        
        def format_postal_code(e):
            val = "".join(filter(str.isdigit, e.control.value))
            if len(val) > 5: val = val[:5]
            if len(val) > 2:
                e.control.value = f"{val[:2]}-{val[2:]}"
            else:
                e.control.value = val
            e.control.update()
            
        self.postal_code = ft.TextField(label="Kod pocztowy", on_change=format_postal_code, width=120)
        
        self.country = ft.TextField(label="Kraj", value="Polska", expand=True)
        self.country_code = ft.TextField(label="Kod (PL)", value="PL", width=80)
        
        def format_bank_account(e):
            if not e.control.value:
                return

            # Remove all non-digits
            raw = "".join(filter(str.isdigit, e.control.value))
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
            
            e.control.value = formatted.strip()
            e.control.update()

        self.bank_account = ft.TextField(
            label="Nr Konta Bankowego", 
            on_change=format_bank_account,
            hint_text="XX 1111 2222 3333 4444 5555 6666",
            width=310,
            text_align=ft.TextAlign.CENTER,
            keyboard_type=ft.KeyboardType.NUMBER
        )
        self.bank_name = ft.TextField(label="Nazwa Banku", width=400)
        self.swift = ft.TextField(label="SWIFT", width=120)

        # Nowe ustawienie: Forma opodatkowania
        self.tax_system_dd = ft.Dropdown(
            label="Domyślna forma opodatkowania",
            options=[
                ft.dropdown.Option(text="Ryczałt ewidencjonowany (Rachunek)", key=TaxSystem.RYCZALT.value),
                ft.dropdown.Option(text="VAT / Liniowy (Faktura VAT)", key=TaxSystem.VAT.value)
            ],
            value=TaxSystem.RYCZALT.value,
            width=400
        )
        self.tax_system_dd.on_change = lambda e: self.load_numbering_settings()
        
        # VAT Exemption details
        self.is_vat_payer = ft.Switch(label="Czynny płatnik VAT", value=True)
        self.vat_exemption_type = ft.Dropdown(
            label="Typ zwolnienia z VAT",
            options=[
                ft.dropdown.Option("USTAWA"),
                ft.dropdown.Option("DYREKTYWA"),
                ft.dropdown.Option("INNE"),
            ],
            width=200,
            disabled=True
        )
        self.vat_exemption_basis = ft.TextField(label="Podstawa prawna zwolnienia", disabled=True, expand=1)
        
        def on_vat_payer_change(e):
            is_vat = self.is_vat_payer.value
            self.vat_exemption_type.disabled = is_vat
            self.vat_exemption_basis.disabled = is_vat
            self.vat_exemption_type.update()
            self.vat_exemption_basis.update()
            
        self.is_vat_payer.on_change = on_vat_payer_change
        
        tab_company_content = ft.Container(
            padding=20,
            content=ft.Column([
                 ft.Text("Dane rejestrowe", size=20, weight="bold"),
                 self.company_name,
                 ft.Row([self.nip, self.regon, self.krs, self.bdo]),
                 self.address,
                 ft.Row([self.postal_code, self.city, self.country_code, self.country]),
                 ft.Row([self.bank_name, self.swift, self.bank_account]),
                 ft.Divider(),
                 ft.Text("Ustawienia księgowe", size=16, weight="bold"),
                 self.tax_system_dd,
                 ft.Container(
                     content=ft.Column([
                         self.is_vat_payer,
                         ft.Row([
                             ft.Text("Szczegóły zwolnienia (jeśli nie VAT):"),
                         ]),
                         ft.Row([
                             self.vat_exemption_type,
                             self.vat_exemption_basis
                         ])
                     ]),
                     bgcolor=ft.Colors.GREY_50,
                     padding=10,
                     border_radius=5
                 ),
                 ft.Divider(),
                 ft.ElevatedButton("Zapisz dane firmy", icon="save", on_click=self.save_config)
            ], scroll=ft.ScrollMode.AUTO)
        )

        # --- TAB 2: KSeF i Integracje ---
        self.ksef_cert_content_blob = None
        self.ksef_key_content_blob = None
        
        self.file_picker_cert = ft.FilePicker(on_result=self.on_cert_picked)
        self.file_picker_key = ft.FilePicker(on_result=self.on_key_picked)
        
        self.ksef_auth_mode = ft.Dropdown(
            label="Tryb autoryzacji",
            options=[
                ft.dropdown.Option("TOKEN", "Token (Standard)"),
                ft.dropdown.Option("CERT", "Certyfikat (Klucz)"),
            ],
            value="TOKEN",
            width=300
        )

        self.ksef_token = ft.TextField(label="Token KSeF", password=True, can_reveal_password=True, width=500)
        
        self.ksef_cert_status = ft.Text("Brak wczytania", color="grey")
        self.ksef_key_status = ft.Text("Brak wczytania", color="grey")
        self.ksef_key_pass = ft.TextField(label="Hasło do klucza prywatnego", password=True, can_reveal_password=True, width=300)
        
        self.token_container = ft.Column([
             ft.Container(
                    padding=10,
                    bgcolor=ft.Colors.BLUE_50,
                    border_radius=5,
                    content=ft.Column([
                        ft.Text("Instrukcja: Jak pobrać token?", weight="bold", color=ft.Colors.BLUE),
                        ft.Text("1. Zaloguj się na ksef.mf.gov.pl (Produkcja)."),
                        ft.Text("2. W sekcji Tokeny wygeneruj nowy token."),
                        ft.Text("3. Wymagane uprawnienia: Dostęp do faktur, Wystawianie faktur."),
                    ], spacing=2)
             ),
             ft.Text("Token autoryzacyjny:", size=14, weight="bold"),
             self.ksef_token
        ])
        
        self.cert_container = ft.Column([
            ft.Text("Konfiguracja Certyfikatu (Produkcja)", size=14, weight="bold"),
            ft.Text("Wymaga wczytania plików PEM/CRT oraz klucza prywatnego.", size=12, color="grey"),
            ft.Row([
                ft.ElevatedButton("Wybierz Certyfikat", icon="upload_file", on_click=self.launch_cert_picker),
                self.ksef_cert_status
            ]),
            ft.Row([
                ft.ElevatedButton("Wybierz Klucz Prywatny", icon="vpn_key", on_click=self.launch_key_picker),
                self.ksef_key_status
            ]),
            self.ksef_key_pass,
            ft.Text("Hasło do klucza zostanie zaszyfrowane w bazie danych.", size=11, italic=True, color=ft.Colors.GREY_600)
        ], visible=False)

        def on_mode_change(e):
             is_token = (self.ksef_auth_mode.value == "TOKEN")
             self.token_container.visible = is_token
             self.cert_container.visible = not is_token
             self.token_container.update()
             self.cert_container.update()
             
        self.ksef_auth_mode.on_change = on_mode_change
        
        tab_ksef_content = ft.Container(
            padding=20,
            content=ft.Column([
                ft.Text("Integracja z KSeF", size=20, weight="bold"),
                self.ksef_auth_mode,
                ft.Divider(),
                self.token_container,
                self.cert_container,
                ft.Divider(),
                ft.ElevatedButton("Test połączenia", icon="wifi_tethering", on_click=self.test_ksef_connection),
                ft.Divider(),
                ft.Text("Ustawienia NBP", size=20, weight="bold"),
                ft.Switch(label="Automatycznie pobieraj kursy walut", value=True),
                ft.ElevatedButton("Zapisz ustawienia integracji", icon="save", on_click=self.save_config)
            ], scroll=ft.ScrollMode.AUTO)
        )
        
        # --- TAB 3: Definicje (VAT, Jednostki) ---
        tab_defs_content = ft.Container(
            padding=20, 
            content=ft.Column([
                 ft.Text("Definicje stawek VAT", size=20, weight="bold"),
                 ft.ElevatedButton("Zarządzaj stawkami VAT", on_click=self.manage_vat_rates),
                 ft.Text("Definicje Jednostek miary", size=20, weight="bold"),
                 # Placeholder for unit definitions
            ])
        )
        
        # --- TAB 4: Użytkownicy ---
        tab_users_content = ft.Container(
             padding=20,
             content=ft.Column([
                 ft.Text("Zarządzanie użytkownikami", size=20, weight="bold"),
                 ft.ElevatedButton("Dodaj użytkownika", icon="person_add"),
                 # Placeholder list user
                 ft.Text("(Lista użytkowników w budowie)")
             ])
        )

        # --- TAB 5: Numeracja ---
        self.numbering_column = ft.Column()
        
        self.btn_save_numbering = ft.ElevatedButton("Zapisz ustawienia numeracji", icon="save", on_click=self.save_numbering_settings)

        tab_numbering_content = ft.Container(
            padding=20, 
            content=ft.Column([
                ft.Text("Konfiguracja Numeracji", size=20, weight="bold"),
                ft.Text("Definiuj format numeru (użyj {nr}, {rok}, {miesiac}) oraz okres numeracji.", size=12, color="grey"),
                ft.Divider(),
                self.numbering_column,
                ft.Divider(),
                self.btn_save_numbering
            ], scroll=ft.ScrollMode.AUTO)
        )

        # --- MANUALLY IMPLEMENTED TABS ---
        self.tabs_content = [tab_company_content, tab_ksef_content, tab_defs_content, tab_users_content, tab_numbering_content]
        self.current_tab_index = 0
        
        self.tab_buttons = ft.Row([
            ft.TextButton("Firma", icon="business", data=0, on_click=self.change_tab, style=ft.ButtonStyle(color=ft.Colors.BLUE)),
            ft.TextButton("KSeF / Integracje", icon="cloud_sync", data=1, on_click=self.change_tab),
            ft.TextButton("Słowniki", icon="list_alt", data=2, on_click=self.change_tab),
            ft.TextButton("Użytkownicy", icon="group", data=3, on_click=self.change_tab),
            ft.TextButton("Numeracja", icon="format_list_numbered", data=4, on_click=self.change_tab),
        ], scroll=ft.ScrollMode.AUTO)

        self.content_area = ft.Container(content=self.tabs_content[0], expand=True)
        
        # Load numbering settings immediately
        self.load_numbering_settings()
        
        # Load company config immediately
        self.load_config()

        self.controls = [
            ft.Container(self.tab_buttons, bgcolor=ft.Colors.GREY_100, padding=5),
            ft.Divider(height=1, thickness=1),
            self.content_area
        ]

    def change_tab(self, e):
        # Reset styles
        for btn in self.tab_buttons.controls:
            btn.style = None
        
        # Highlight active
        e.control.style = ft.ButtonStyle(color=ft.Colors.BLUE)
        
        # Change content
        idx = e.control.data
        self.content_area.content = self.tabs_content[idx]
        self.update()

    def on_cert_picked(self, e: ft.FilePickerResultEvent):
        if e.files and len(e.files) > 0:
            f = e.files[0]
            try:
                # Flet web vs desktop. On desktop path is available.
                if f.path:
                    with open(f.path, "rb") as file:
                        self.ksef_cert_content_blob = file.read()
                    self.ksef_cert_status.value = f"Wczytano: {f.name}"
                    self.ksef_cert_status.color = "green"
                    self.ksef_cert_status.update()
            except Exception as ex:
                self.ksef_cert_status.value = f"Błąd: {str(ex)}"
                self.ksef_cert_status.color = "red"
                self.ksef_cert_status.update()

    def on_key_picked(self, e: ft.FilePickerResultEvent):
        if e.files and len(e.files) > 0:
            f = e.files[0]
            try:
                if f.path:
                    with open(f.path, "rb") as file:
                        self.ksef_key_content_blob = file.read()
                    self.ksef_key_status.value = f"Wczytano: {f.name}"
                    self.ksef_key_status.color = "green"
                    self.ksef_key_status.update()
            except Exception as ex:
                self.ksef_key_status.value = f"Błąd: {str(ex)}"
                self.ksef_key_status.color = "red"
                self.ksef_key_status.update()

    def launch_cert_picker(self, e):
        if self.file_picker_cert not in e.page.overlay:
            e.page.overlay.append(self.file_picker_cert)
            e.page.update()
        self.file_picker_cert.pick_files(allow_multiple=False, allowed_extensions=["pem", "crt", "cer"])

    def launch_key_picker(self, e):
        if self.file_picker_key not in e.page.overlay:
            e.page.overlay.append(self.file_picker_key)
            e.page.update()
        self.file_picker_key.pick_files(allow_multiple=False, allowed_extensions=["pem", "key"])

    def test_ksef_connection(self, e):
        nip = self.nip.value
        token = self.ksef_token.value
        
        if not nip or not token:
             self.page.show_snack_bar(ft.SnackBar(ft.Text("Wprowadź NIP i Token przed testem!")))
             return

        try:
             # Uruchomienie progress ring (np. zmiana ikony przycisku)
             e.control.icon = "hourglass_empty"
             e.control.text = "Łączenie..."
             self.update()
             
             client = KsefClient(token=token)
             # Klient pobiera klucz publiczny automatycznie przy imporcie? Nie, w metodach.
             
             # Próba autentykacji
             # KsefClient logic: authenticate(nip)
             # Jeśli zwróci True, to jest OK.
             result = client.authenticate(nip)
             
             if result:
                  dialog = ft.AlertDialog(
                      title=ft.Text("Sukces", color=ft.Colors.GREEN),
                      content=ft.Text(f"Pomyślnie połączono z KSeF!\nNIP: {nip}\nToken Sesyjny pobrany.")
                  )
                  self.page.dialog = dialog
                  dialog.open = True
                  self.page.update()
             
        except Exception as ex:
             dialog = ft.AlertDialog(
                 title=ft.Text("Błąd połączenia", color=ft.Colors.RED),
                 content=ft.Text(f"Nieudana autoryzacja:\n{str(ex)}")
             )
             self.page.dialog = dialog
             dialog.open = True
             self.page.update()
             logger.error(traceback.format_exc())
        
        finally:
             e.control.icon = "wifi_tethering"
             e.control.text = "Test połączenia"
             self.update()

    def load_config(self):
        db = next(get_db())
        config = db.query(CompanyConfig).first()
        if config:
            # Używamy setattr bezpiecznie, bo init pól jest w __init__
            if hasattr(self, 'company_name'): self.company_name.value = config.company_name
            if hasattr(self, 'nip'): self.nip.value = config.nip
            if hasattr(self, 'regon'): self.regon.value = config.regon
            if hasattr(self, 'address'): self.address.value = config.address
            if hasattr(self, 'city'): self.city.value = config.city
            if hasattr(self, 'postal_code'): self.postal_code.value = config.postal_code
            
            # Bank & Country
            if hasattr(self, 'bank_account'): self.bank_account.value = config.bank_account
            if hasattr(self, 'bank_name'): self.bank_name.value = config.bank_name or ""
            if hasattr(self, 'swift'): self.swift.value = config.swift_code or ""
            
            if hasattr(self, 'country'): self.country.value = config.country or "Polska"
            if hasattr(self, 'country_code'): self.country_code.value = config.country_code or "PL"

            if hasattr(self, 'ksef_token'): 
                try:
                    self.ksef_token.value = SecurityManager.decrypt(config.ksef_token) if config.ksef_token else ""
                except Exception as e:
                    logger.error(f"Failed to decrypt KSeF Token: {e}")
                    self.ksef_token.value = ""
            
            if hasattr(self, 'ksef_auth_mode'):
                mode = config.ksef_auth_mode or "TOKEN"
                self.ksef_auth_mode.value = mode
                is_token = (mode == "TOKEN")
                if hasattr(self, 'token_container'): self.token_container.visible = is_token
                if hasattr(self, 'cert_container'): self.cert_container.visible = not is_token
            
            if config.ksef_cert_content:
                if hasattr(self, 'ksef_cert_status'):
                     self.ksef_cert_status.value = "Certyfikat zapisany w bazie."
                     self.ksef_cert_status.color = "green"
            
            if config.ksef_private_key_content:
                if hasattr(self, 'ksef_key_status'): 
                     self.ksef_key_status.value = "Klucz zapisany w bazie."
                     self.ksef_key_status.color = "green"

            if config.ksef_private_key_pass:
                if hasattr(self, 'ksef_key_pass'):
                    try:
                        self.ksef_key_pass.value = SecurityManager.decrypt(config.ksef_private_key_pass)
                    except Exception as e:
                        logger.error(f"Failed to decrypt password: {e}")
                        self.ksef_key_pass.value = ""

            if hasattr(self, 'tax_system_dd'): self.tax_system_dd.value = config.default_tax_system.value if config.default_tax_system else TaxSystem.RYCZALT.value
            
            # New fields
            if hasattr(self, 'bdo'): self.bdo.value = config.bdo or ""
            if hasattr(self, 'krs'): self.krs.value = config.krs or ""
            
            if hasattr(self, 'is_vat_payer'): 
                self.is_vat_payer.value = config.is_vat_payer
                # Trigger disable logic
                self.vat_exemption_type.disabled = config.is_vat_payer
                self.vat_exemption_basis.disabled = config.is_vat_payer

            if hasattr(self, 'vat_exemption_type'): self.vat_exemption_type.value = config.vat_exemption_basis_type
            if hasattr(self, 'vat_exemption_basis'): self.vat_exemption_basis.value = config.vat_exemption_basis

        db.close()
        
        # Refresh numbering settings to match the loaded tax system
        self.load_numbering_settings()
        
        try:
            self.update()
        except: pass
        
    async def save_config(self, e):
        db = next(get_db())
        config = db.query(CompanyConfig).first()
        if not config:
            config = CompanyConfig()
            db.add(config)
        
        config.company_name = self.company_name.value
        config.nip = self.nip.value
        config.regon = self.regon.value
        config.address = self.address.value
        config.city = self.city.value
        config.postal_code = self.postal_code.value
        
        config.bank_account = self.bank_account.value
        config.bank_name = self.bank_name.value
        config.swift_code = self.swift.value
        
        config.country = self.country.value
        config.country_code = self.country_code.value
        
        if self.ksef_token.value:
            config.ksef_token = SecurityManager.encrypt(self.ksef_token.value)
        else:
            config.ksef_token = None
            
        if hasattr(self, 'ksef_auth_mode'):
            config.ksef_auth_mode = self.ksef_auth_mode.value
            
        if self.ksef_cert_content_blob:
            config.ksef_cert_content = self.ksef_cert_content_blob
            
        if self.ksef_key_content_blob:
            config.ksef_private_key_content = self.ksef_key_content_blob
            
        if hasattr(self, 'ksef_key_pass'):
            val = self.ksef_key_pass.value
            if val:
                # Always re-encrypt on save to ensure consistent state
                try:
                    config.ksef_private_key_pass = SecurityManager.encrypt(val)
                except Exception as e:
                    logger.error(f"Encryption failed: {e}")
            else:
                # If cleared, remove from DB? Or keep old?
                # If user cleared the field, we should probably clear the secret.
                # But to avoid accidental deletion if field wasn't loaded correctly...
                # Assuming if loaded correctly it has value.
                config.ksef_private_key_pass = None

        # Save new fields
        config.bdo = self.bdo.value
        config.krs = self.krs.value
        config.is_vat_payer = self.is_vat_payer.value
        config.vat_exemption_basis_type = self.vat_exemption_type.value
        config.vat_exemption_basis = self.vat_exemption_basis.value
        
        try:
             config.default_tax_system = TaxSystem(self.tax_system_dd.value)
        except: pass
        
        db.commit()
        db.close()
        
        # Visual Feedback logic
        btn = e.control
        # Safe read for text property which might be missing on getter in some versions
        original_text = getattr(btn, "text", None)
        if not original_text and hasattr(btn, "content"):
             if isinstance(btn.content, str):
                 original_text = btn.content
             elif hasattr(btn.content, "value"):
                 original_text = btn.content.value
                 
        if not original_text: original_text = "Zapisz" # Fallback
        
        original_icon = btn.icon
        
        btn.text = "Zapisano"
        btn.icon = "check"
        btn.style = ft.ButtonStyle(bgcolor={"": "green"}, color={"": "white"}) 
        btn.update()
        
        if self.page:
            self.page.snack_bar = ft.SnackBar(ft.Text("Konfiguracja zapisana!"))
            self.page.snack_bar.open = True
            self.page.update()
            
        await asyncio.sleep(1)
        
        try:
            btn.text = original_text
            btn.icon = original_icon
            btn.style = None
            btn.update()
            if btn.page:
                btn.page.update()
        except: pass

    def manage_vat_rates(self, e):
        # Prosty menedżer stawek VAT
        db = next(get_db())
        rates = db.query(VatRate).all()
        
        name_field = ft.TextField(label="Opis (np. Stawka 23%)", width=250)
        value_field = ft.TextField(label="Wartość % / Kod (np. 23, ZW)", width=200)
        
        rates_list = ft.Column()

        def refresh_list():
            rates_list.controls.clear()
            current_rates = db.query(VatRate).all()
            for r in current_rates:
                val_display = f"{int(r.rate * 100)}%"
                # Jeśli nazwa sugeruje kod literowy, a stawka jest 0, to wyświetl kod
                # Ale tutaj prościej wyświetlić po prostu stawkę matematyczną
                
                rates_list.controls.append(ft.Container(
                    bgcolor=ft.Colors.WHITE,
                    padding=10,
                    border_radius=5,
                    content=ft.Row([
                        ft.Text(f"{r.name} = {val_display}", size=16, weight="bold"),
                        ft.Container(expand=True),
                        ft.ElevatedButton(
                            content=ft.Text("USUŃ", size=14, weight="bold"),
                            bgcolor=ft.Colors.RED_100,
                            color=ft.Colors.RED,
                            on_click=lambda e, r=r: delete_rate(r)
                        )
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
                ))
            if dlg and dlg.open: self.page.update()

        def add_rate(e):
            val_str = value_field.value.strip().upper().replace(",", ".")
            SPECIAL_CODES = ["ZW", "NP", "OO"]
            
            try:
                if val_str in SPECIAL_CODES:
                    val = 0.0
                    # Jeśli użytkownik nie podał nazwy, użyj kodu jako nazwy
                    if not name_field.value:
                         name_field.value = val_str
                else:
                    # Konwersja z formatu naturalnego 23 -> 0.23
                    val_clean = val_str.replace("%", "")
                    val = float(val_clean) / 100.0

                new_r = VatRate(name=name_field.value, rate=val)
                db.add(new_r)
                db.commit()
                name_field.value = ""
                value_field.value = ""
                refresh_list()
            except ValueError:
                if self.page:
                    self.page.snack_bar = ft.SnackBar(ft.Text(f"Błędna wartość stawki: {val_str}"))
                    self.page.snack_bar.open = True
                    self.page.update()
                pass

        def delete_rate(rate):
            db.delete(rate)
            db.commit()
            refresh_list()

        dlg = None

        refresh_list()
        
        add_btn = ft.ElevatedButton(
            content=ft.Text("DODAJ", size=14, weight="bold"),
            bgcolor=ft.Colors.GREEN_100,
            color=ft.Colors.GREEN,
            height=50,
            on_click=add_rate
        )

        dlg = ft.AlertDialog(
            title=ft.Text("Definicje stawek VAT"),
            content=ft.Container(height=400, width=600, content=ft.Column([
                ft.Row([name_field, value_field, add_btn]),
                ft.Divider(),
                ft.Container(content=rates_list, expand=True, bgcolor=ft.Colors.GREY_50)
            ])),
            actions=[ft.TextButton("Zamknij", on_click=lambda e: setattr(dlg, 'open', False) or self.page.update())]
        )
        refresh_list()
        self.page.overlay.append(dlg)
        dlg.open = True
        self.page.update()

    def load_numbering_settings(self):
        self.numbering_column.controls.clear()
        self.numbering_inputs = [] # Stores NumberingRow instances

        db = next(get_db())
        
        # Define combinations
        combinations = [
            (InvoiceCategory.SALES, InvoiceType.VAT, "Faktura VAT (Sprzedaż)"),
            (InvoiceCategory.SALES, InvoiceType.RYCZALT, "Rachunek (Sprzedaż)"),
            (InvoiceCategory.SALES, InvoiceType.KOREKTA, "Faktura Korygująca (Sprzedaż)"),
            (InvoiceCategory.SALES, InvoiceType.ZALICZKA, "Faktura Zaliczkowa (Sprzedaż)"),
            (InvoiceCategory.PURCHASE, InvoiceType.VAT, "Faktura Zakupu"),
            (InvoiceCategory.PURCHASE, InvoiceType.KOREKTA, "Korekta Zakupu"),
        ]
        
        for cat, typ, label in combinations:
            setting = db.query(NumberingSetting).filter_by(invoice_category=cat, invoice_type=typ).first()
            
            # Create dedicated row component
            row = NumberingRow(cat, typ, label, setting)
            self.numbering_inputs.append(row)
            self.numbering_column.controls.append(row)

        db.close()
        try:
             self.numbering_column.update()
        except: pass

    async def save_numbering_settings(self, e):
        db = next(get_db())
        try:
            for row in self.numbering_inputs:
                data = row.get_values()
                cat = data["cat"]
                typ = data["typ"]
                p_type_str = data["period"]
                tpl = data["template"]
                
                p_type = PeriodType(p_type_str)
                
                setting = db.query(NumberingSetting).filter_by(invoice_category=cat, invoice_type=typ).first()
                
                # Check for changes in period type and validate
                if setting and setting.period_type != p_type:
                    current_date = datetime.now()
                    
                    # Base query for invoices of this type
                    inv_query = db.query(Invoice).filter(
                        Invoice.category == cat,
                        Invoice.type == typ
                    )
                    
                    if setting.period_type == PeriodType.YEARLY and p_type == PeriodType.MONTHLY:
                        # Trying to switch from Yearly to Monthly
                        # Allowed if NO invoices in CURRENT MONTH
                        count_month = inv_query.filter(
                            extract('year', Invoice.date_issue) == current_date.year,
                            extract('month', Invoice.date_issue) == current_date.month
                        ).count()
                        
                        if count_month > 0:
                            raise Exception(f"Nie można zmienić na numerację miesięczną dla {typ.value}: "
                                            f"W tym miesiącu ({current_date.month}/{current_date.year}) wystawiono już dokumenty.")

                    elif setting.period_type == PeriodType.MONTHLY and p_type == PeriodType.YEARLY:
                         # Trying to switch from Monthly to Yearly
                         # Allowed if NO invoices in CURRENT YEAR
                        count_year = inv_query.filter(
                            extract('year', Invoice.date_issue) == current_date.year
                        ).count()

                        if count_year > 0:
                             raise Exception(f"Nie można zmienić na numerację roczną dla {typ.value}: "
                                             f"W tym roku ({current_date.year}) wystawiono już dokumenty.")

                if not setting:
                    setting = NumberingSetting(invoice_category=cat, invoice_type=typ)
                    db.add(setting)
                
                setting.period_type = p_type
                setting.template = tpl
            
            db.commit()
            print("[Settings] Numbering saved successfully.")
            
            # Button handling using e.control and style logic for robustness
            btn = e.control
            btn.text = "Zapisano"
            btn.icon = "check"
            # Using style is often more reliable than direct bgcolor property after init in some versions
            btn.style = ft.ButtonStyle(bgcolor={"": "green"}, color={"": "white"}) 
            btn.update()
            
            if self.page:
                self.page.snack_bar = ft.SnackBar(ft.Text("Ustawienia numeracji zapisane!"))
                self.page.snack_bar.open = True
                self.page.update()
            
            # Use asyncio sleep inside the async handler - keeps UI responsive for repaints
            await asyncio.sleep(1)
            
            try:
                btn.text = "Zapisz ustawienia numeracji"
                btn.icon = "save"
                btn.style = None # Reset style to default
                btn.update()
                if btn.page:
                    btn.page.update()
            except Exception as ex:
                print(f"[Settings] Reset error: {ex}")
                
        except Exception as ex:
            print(f"[Settings] Save error: {ex}")
            if self.page:
                self.page.snack_bar = ft.SnackBar(ft.Text(f"Błąd zapisu: {str(ex)}"), bgcolor=ft.Colors.RED)
                self.page.snack_bar.open = True
                self.page.update()
            logger.error(traceback.format_exc())
            
        finally:
            db.close()

