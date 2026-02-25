import flet as ft
import re
import os
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import traceback
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from fpdf import FPDF
from database.engine import get_db
from database.models import Invoice, Contractor, Product, InvoiceItem, InvoiceCategory, InvoiceType, CompanyConfig, TaxSystem, VatRate
from logic.numbering_service import NumberingService, NumberingException
from logic.ksef_logic import KsefLogic
from ksef.xml_generator import KsefXmlGenerator
from ksef.client import KsefClient
from nbp.client import NbpClient
from gus.client import GusClient
from vies.client import ViesClient
from mf_whitelist.client import MfWhitelistClient

class InvoiceView(ft.Column):
    def __init__(self, category=InvoiceCategory.SALES):
        super().__init__(scroll=ft.ScrollMode.AUTO, expand=True)

        self.xml_gen = KsefXmlGenerator()
        self.nbp_client = NbpClient()
        self.category = category
        self.current_filter_contractor = None
        self.current_filter_date_from = None
        self.current_filter_date_to = None
        self.gus_client = GusClient()
        self.vies_client = ViesClient()
        self.mf_client = MfWhitelistClient()
        self.row_clipboard = None
        
        # Replacement of DataTable with ListView to fix rendering issues
        # and support PopupMenuButton correctly (like in Items List)
        self.headers_container = ft.Container(
            padding=ft.padding.symmetric(horizontal=10, vertical=10),
            bgcolor=ft.Colors.BLUE_GREY_50,
            border=ft.border.all(1, ft.Colors.BLUE_GREY_200),
        )
        # Using Column instead of ListView/DataTable to avoid PopupMenuButton rendering bugs (gray overlay)
        self.invoices_list = ft.Column(expand=True, spacing=2, scroll=ft.ScrollMode.AUTO)
        
        # Określenie tytułu na podstawie konfiguracji
        title = "Dokumenty Sprzedaży"
        if category == InvoiceCategory.SALES:
            title = "Faktury Sprzedaży"
            try:
                db = next(get_db())
                config = db.query(CompanyConfig).first()
                if config and config.default_tax_system == TaxSystem.RYCZALT:
                    title = "Rachunki"
                db.close()
            except: pass
        else:
            title = "Faktury Zakupu"
        
        # Filtry i Toolbar
        self.filter_number = ft.TextField(label="Szukaj numeru", width=200, on_change=self.apply_filters)
        self.date_from = ft.TextField(label="Data od", width=120, icon="calendar_today", value=datetime.now().strftime("%Y-%m-01"))
        self.date_to = ft.TextField(label="Data do", width=120, icon="calendar_today", value=datetime.now().strftime("%Y-%m-%d"))
        
        self.payment_method_dd = None # Will be referenced later
        self.bank_accounts_field = None
        
        self.selected_invoice_id = None

        self.edit_button = ft.ElevatedButton("Edytuj", icon="edit", disabled=True, tooltip="Edycja zaznaczonej faktury", on_click=self.edit_selected_invoice)

        toolbar_buttons = [
                ft.ElevatedButton("Dodaj", icon="add", on_click=self.open_add_invoice_dialog),
                self.edit_button,
                # Usuwanie globalne (dla zaznaczonych - opcja przyszłościowa)
                ft.ElevatedButton("Usuń", icon="delete", color="red", visible=False),
        ]
        
        if self.category == InvoiceCategory.PURCHASE:
             # Dla zakupów dodajemy przycisk pobierania z KSeF
             toolbar_buttons.append(
                 ft.ElevatedButton("Pobierz z KSeF", icon="cloud_download", 
                                   on_click=self.download_ksef_invoices,
                                   bgcolor=ft.Colors.BLUE_100, color=ft.Colors.BLUE)
             )

        toolbar_buttons.append(ft.VerticalDivider())
        toolbar_buttons.extend([self.date_from, self.date_to, self.filter_number])
        
        self.toolbar = ft.Row(toolbar_buttons + [
                ft.IconButton(icon=ft.Text("↻", size=20), tooltip="Odśwież", on_click=lambda e: self.load_invoices())
        ])
        
        self.pagination = ft.Row(
            [
                ft.IconButton(icon=ft.Text("<", size=20)),
                ft.Text("Strona 1 z 1"),
                ft.IconButton(icon=ft.Text(">", size=20)),
            ],
            alignment=ft.MainAxisAlignment.CENTER
        )

        self.controls = [
            ft.Row([
                ft.Text(title, size=30, weight="bold"),
                self.toolbar
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Column([
                self.headers_container,
                ft.Container(expand=True, content=self.invoices_list)
            ], expand=True),
            self.pagination
        ]
        self.load_invoices()

    def did_mount(self):
        # Global pickers already mounted in AppLayout
        pass

    def will_unmount(self):
        # No cleanup for global pickers
        pass

    def edit_selected_invoice(self, e):
        if self.selected_invoice_id:
            self.open_add_invoice_dialog(e, edit_invoice_id=self.selected_invoice_id)

    def on_row_select(self, e, invoice_id):
        # Handle selection logic
        # Toggle off if clicking selected? No, usually keep selected.
        
        self.selected_invoice_id = invoice_id
        
        # Enable edit button only if something is selected
        self.edit_button.disabled = (self.selected_invoice_id is None)
        self.edit_button.update()
        
        # Refresh visuals
        self.load_invoices(page_num=getattr(self, 'current_page', 1))

    def copy_row_to_clipboard(self, invoice):
        """Copies invoice data to clipboard in Excel-friendly format (Tab separated)."""
        # Format: Number \t Date \t Contractor \t Net \t Gross \t Status
        line = f"{invoice.number}\t{invoice.date_issue}\t{invoice.contractor_name}\t{invoice.total_net}\t{invoice.total_gross}\t{'KSeF' if invoice.is_sent_to_ksef else 'Draft'}"
        if self.page:
            self.page.set_clipboard(line)
            self.page.snack_bar = ft.SnackBar(ft.Text("Skopiowano wiersz do schowka"))
            self.page.snack_bar.open = True
            self.page.update()

    def load_invoices(self, page_num=1):
        
        try:
            db = next(get_db())
            query = db.query(Invoice).filter(Invoice.category == self.category)
            
            # Filtrowanie po numerze
            if self.filter_number.value:
                query = query.filter(Invoice.number.ilike(f"%{self.filter_number.value}%"))
                
            invoices = query.options(joinedload(Invoice.contractor)).order_by(Invoice.date_issue.desc()).limit(50).all()
            
            # Pobranie konfiguracji do sprawdzenia trybu
            config = db.query(CompanyConfig).first()
            is_ryczalt_mode = False
            if config and config.default_tax_system == TaxSystem.RYCZALT:
                is_ryczalt_mode = True
                
            # Aktualizacja nagłówków tabeli w zależności od trybu i kategorii
            
            # Purchase specific columns
            if self.category == InvoiceCategory.PURCHASE:
                self.headers_container.content = ft.Row([
                    ft.Container(ft.Text("KSeF Ref / Numer", weight="bold", size=14), width=150),
                    ft.Container(ft.Text("Wystawiono", weight="bold", size=14), width=100),
                    ft.Container(ft.Text("Wystawca", weight="bold", size=14), expand=True),
                    ft.Container(ft.Text("Brutto", weight="bold", size=14), width=100),
                    ft.Container(ft.Text("UPO", weight="bold", size=14), width=80),
                    ft.Container(ft.Text("Akcje", weight="bold", size=14), width=50),
                ], alignment=ft.MainAxisAlignment.START)
            elif is_ryczalt_mode:
                self.headers_container.content = ft.Row([
                    ft.Container(ft.Text("Numer", weight="bold", size=14), width=150),
                    ft.Container(ft.Text("Data", weight="bold", size=14), width=100),
                    ft.Container(ft.Text("Kontrahent", weight="bold", size=14), expand=True),
                    ft.Container(ft.Text("Wartość (Suma)", weight="bold", size=14), width=100),
                    ft.Container(ft.Text("Status", weight="bold", size=14), width=50),
                    ft.Container(ft.Text("Akcje", weight="bold", size=14), width=50),
                ], alignment=ft.MainAxisAlignment.START)
            else:
                 self.headers_container.content = ft.Row([
                    ft.Container(ft.Text("Numer", weight="bold", size=14), width=150),
                    ft.Container(ft.Text("Typ", weight="bold", size=14), width=80),
                    ft.Container(ft.Text("Data", weight="bold", size=14), width=100),
                    ft.Container(ft.Text("Kontrahent", weight="bold", size=14), expand=True),
                    ft.Container(ft.Text("Netto", weight="bold", size=14), width=100, text_align=ft.TextAlign.RIGHT),
                    ft.Container(ft.Text("Brutto", weight="bold", size=14), width=100, text_align=ft.TextAlign.RIGHT),
                    ft.Container(ft.Text("Status", weight="bold", size=14), width=50),
                    ft.Container(ft.Text("Akcje", weight="bold", size=14), width=50),
                ], alignment=ft.MainAxisAlignment.START)
            
            self.invoices_list.controls.clear()
            
            for inv in invoices:
                status_icon = ft.Icon("check_circle", color="green") if inv.is_sent_to_ksef else ft.Icon("circle_outlined", color="grey")
                contractor_name = inv.contractor.name if inv.contractor else "Brak"
                current_inv = inv 
                
                # --- Generowanie Menu Kontekstowego ---
                # Używamy PopupMenuButton w Row (ListView), co naprawia błędy z DataTable
                
                is_ksef_locked = False
                if self.category == InvoiceCategory.PURCHASE:
                    is_ksef_locked = bool(current_inv.ksef_number)
                else:
                    is_ksef_locked = current_inv.is_sent_to_ksef

                menu_items = [
                    ft.PopupMenuItem(icon="visibility", content=ft.Text("Podgląd"), 
                                     on_click=lambda e, i=current_inv.id: self.open_add_invoice_dialog(e, edit_invoice_id=i, readonly=True)),
                    ft.PopupMenuItem(icon="code", content=ft.Text("Podgląd KSeF"), 
                                     on_click=lambda e, i=current_inv: self.show_xml_preview(i)),
                    ft.PopupMenuItem(icon="download", content=ft.Text("Eksport XML"), 
                                     on_click=lambda e, i=current_inv: self.export_xml(i)),
                    ft.PopupMenuItem(icon="copy", content=ft.Text("Kopiuj wiersz"), 
                                     on_click=lambda e, i=current_inv: self.copy_row_to_clipboard(i)),
                ]
                
                if not is_ksef_locked:
                     menu_items.append(
                        ft.PopupMenuItem(icon="edit", content=ft.Text("Edytuj"), 
                                         on_click=lambda e, i=current_inv.id: self.open_add_invoice_dialog(e, edit_invoice_id=i))
                    )
                else:
                     menu_items.append(ft.PopupMenuItem(icon="lock", content=ft.Text("Edycja zablokowana (KSeF)"), disabled=True))

                if not is_ksef_locked or self.category == InvoiceCategory.PURCHASE:
                     menu_items.append(ft.PopupMenuItem(icon="delete", content=ft.Text("Usuń"), 
                                                        on_click=lambda e, i=current_inv: self.confirm_delete_invoice(i)))

                actions_btn = ft.PopupMenuButton(
                    icon="more_vert",
                    items=menu_items,
                    tooltip="Opcje"
                )

                # Row Selection Handler
                def on_row_click(e, i=current_inv.id):
                    self.on_row_select(e, i)

                row_bg = ft.Colors.BLUE_50 if (current_inv.id == self.selected_invoice_id) else ft.Colors.WHITE

                if self.category == InvoiceCategory.PURCHASE:
                    # Purchase specific logic
                    upo_text = "Dostępne" if inv.ksef_number else "-" 
                    display_num = inv.number if len(inv.number) < 30 else inv.number[:20] + "..."
                    if inv.ksef_number: display_num += f"\n({inv.ksef_number[:15]}...)"
                    
                    row_content = ft.Row([
                        ft.Container(ft.Text(display_num, size=14), width=150),
                        ft.Container(ft.Text(inv.date_issue.strftime("%Y-%m-%d"), size=14), width=100),
                        ft.Container(ft.Text(contractor_name, size=14, overflow=ft.TextOverflow.ELLIPSIS), expand=True),
                        ft.Container(ft.Text(f"{inv.total_gross:.2f}", size=14), width=100),
                        ft.Container(ft.Text(upo_text, size=14), width=80),
                        ft.Container(actions_btn, width=50),
                    ])
                elif is_ryczalt_mode:
                    row_content = ft.Row([
                        ft.Container(ft.Text(inv.number, size=14), width=150),
                        ft.Container(ft.Text(inv.date_issue.strftime("%Y-%m-%d"), size=14), width=100),
                        ft.Container(ft.Text(contractor_name, size=14), expand=True),
                        ft.Container(ft.Text(f"{inv.total_gross:.2f} {inv.currency}", size=14), width=100),
                        ft.Container(status_icon, width=50),
                        ft.Container(actions_btn, width=50),
                    ])
                else:
                    row_content = ft.Row([
                        ft.Container(ft.Text(inv.number, size=14), width=150),
                        ft.Container(ft.Text(inv.type.value, size=14), width=80),
                        ft.Container(ft.Text(inv.date_issue.strftime("%Y-%m-%d"), size=14), width=100),
                        ft.Container(ft.Text(contractor_name, size=14), expand=True),
                        ft.Container(ft.Text(f"{inv.total_net:.2f}", size=14), width=100, text_align=ft.TextAlign.RIGHT),
                        ft.Container(ft.Text(f"{inv.total_gross:.2f}", size=14), width=100, text_align=ft.TextAlign.RIGHT),
                        ft.Container(status_icon, width=50),
                        ft.Container(actions_btn, width=50),
                    ])

                self.invoices_list.controls.append(
                    ft.Container(
                        content=row_content,
                        bgcolor=row_bg,
                        padding=ft.padding.symmetric(vertical=5, horizontal=0),
                        on_click=on_row_click,
                        ink=True,
                        border=ft.border.only(bottom=ft.border.BorderSide(1, ft.Colors.GREY_300))
                    )
                )
        except Exception as e:
            print(f"Błąd ładowania faktur: {e}")
        finally:
            if 'db' in locals(): db.close()
            
        try:
            if self.page:
                self.update()
        except Exception:
            pass

    def delete_invoice(self, invoice_id):
        """Usuwa fakturę i powiązane elementy, jeśli to możliwe."""
        db = next(get_db())
        try:
            inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
            if not inv:
                return

            # Sprawdzenie kontrahenta
            contractor = inv.contractor
            contractor_id = contractor.id if contractor else None
            
            # Usuń fakturę (kaskadowo usunie pozycje invoice_items dzięki cascade="all, delete-orphan")
            # Rozliczenia są polami w Invoice, więc znikają razem z nim.
            db.delete(inv)
            db.commit()
            
            # Próba usunięcia kontrahenta, jeśli nie ma innych faktur
            contractor_deleted = False
            if contractor_id:
                other_invs = db.query(Invoice).filter(Invoice.contractor_id == contractor_id).count()
                if other_invs == 0:
                    try:
                        db.delete(contractor)
                        db.commit()
                        contractor_deleted = True
                    except Exception as e:
                        print(f"Nie można usunąć kontrahenta: {e}")

            msg = "Usunięto fakturę."
            if contractor_deleted:
                 msg += " Usunięto również nieużywanego kontrahenta."

            if self.page:
                 self.page.snack_bar = ft.SnackBar(ft.Text(msg))
                 self.page.snack_bar.open = True
                 self.page.update()
            
            self.load_invoices()
            
        except Exception as e:
            db.rollback()
            print(f"Błąd usuwania: {e}")
            if self.page:
                self.page.snack_bar = ft.SnackBar(ft.Text(f"Błąd usuwania: {e}"))
                self.page.snack_bar.open = True
                self.page.update()
        finally:
            db.close()

    def confirm_delete_invoice(self, invoice):
        # KSeF Safety Check
        if invoice.is_sent_to_ksef and self.category == InvoiceCategory.SALES:
             if self.page:
                  self.page.snack_bar = ft.SnackBar(ft.Text("Nie można usunąć faktury wysłanej do KSeF!"))
                  self.page.snack_bar.open = True
                  self.page.update()
             return
        # Allow deletion for Purchase invoices even if KSeF (local wipe)
        # if invoice.ksef_number and self.category == InvoiceCategory.PURCHASE:
             # return 

        dlg = ft.AlertDialog(
            title=ft.Text("Potwierdzenie"),
            content=ft.Text(f"Czy na pewno chcesz usunąć fakturę {invoice.number}? \nJeśli to jedyny dokument tego kontrahenta, zostanie on również usunięty."),
            actions=[
                ft.TextButton("Nie", on_click=lambda e: setattr(dlg, 'open', False) or self.page.update()),
                ft.TextButton("Tak, usuń", style=ft.ButtonStyle(color="red"), 
                              on_click=lambda e: setattr(dlg, 'open', False) or self.delete_invoice(invoice.id))
            ]
        )
        self.page.overlay.append(dlg)
        dlg.open = True
        self.page.update()

    def did_mount(self):
        # No local file pickers to mount
        pass

    def will_unmount(self):
        # No local file pickers to unmount
        pass

    def save_xml_click(self, number):
        print(f"[DEBUG] save_xml_click OverlayModal called for {number}")
        
        # Determine default path
        home = os.path.expanduser("~")
        downloads = os.path.join(home, "Downloads")
        if not os.path.exists(downloads):
            downloads = home

        fname = f"Faktura_{str(number).replace('/', '_')}.xml"
        
        # Inputs
        filename_input = ft.TextField(label="Nazwa pliku", value=fname, width=400)
        path_input = ft.TextField(label="Folder zapisu", value=downloads, width=400)
        
        # Modal wrapper
        modal_bg = ft.Container(
            expand=True,
            bgcolor="#80000000", # Transparent black
            alignment=ft.Alignment(0, 0),
            clickable=True, # Block clicks to underlying
        )

        def close_modal(e):
            if modal_bg in self.page.overlay:
                self.page.overlay.remove(modal_bg)
                self.page.update()

        def save_action(e):
            folder = path_input.value
            filename = filename_input.value
            full_path = os.path.join(folder, filename)
            
            content = getattr(self, 'current_preview_xml_content', None)
            if content:
                try:
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    print(f"[DEBUG] Zapisano plik XML pomyślnie: {full_path}")
                    if self.page:
                        self.page.snack_bar = ft.SnackBar(ft.Text(f"Zapisano XML: {full_path}"), bgcolor=ft.Colors.GREEN)
                        self.page.snack_bar.open = True
                        close_modal(None)
                except Exception as ex:
                    print(f"[ERROR] Błąd zapisu pliku XML do {full_path}: {ex}")
                    if self.page:
                         self.page.snack_bar = ft.SnackBar(ft.Text(f"Błąd zapisu: {ex}"), bgcolor=ft.Colors.RED)
                         self.page.snack_bar.open = True
                         self.page.update()
            else:
                 print("[ERROR] Brak zawartości XML do zapisu (current_preview_xml_content is None)")
                 close_modal(None)

        # Dialog Box
        dialog_box = ft.Container(
            bgcolor=ft.Colors.WHITE,
            padding=20,
            border_radius=8,
            width=500,
            height=300,
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=15, color=ft.Colors.BLACK54),
            content=ft.Column([
                ft.Text("Zapisz XML", size=20, weight="bold"),
                ft.Text("Wybierz lokalizację zapisu (ścieżka bezwzględna):"),
                path_input,
                filename_input,
                ft.Row([
                    ft.TextButton("Anuluj", on_click=close_modal),
                    ft.ElevatedButton("Zapisz", on_click=save_action)
                ], alignment=ft.MainAxisAlignment.END, spacing=10)
            ])
        )
        
        modal_bg.content = dialog_box
        
        self.page.overlay.append(modal_bg)
        self.page.update()

    def save_pdf_click(self, number):
        print(f"[DEBUG] save_pdf_click OverlayModal called for {number}")
        
        # Determine default path
        home = os.path.expanduser("~")
        downloads = os.path.join(home, "Downloads")
        if not os.path.exists(downloads):
            downloads = home 
            
        fname = f"Faktura_{str(number).replace('/', '_')}.pdf"

        # Inputs
        filename_input = ft.TextField(label="Nazwa pliku", value=fname, width=400)
        path_input = ft.TextField(label="Folder zapisu", value=downloads, width=400)
        
        # Modal wrapper
        modal_bg = ft.Container(
            expand=True,
            bgcolor="#80000000",
            alignment=ft.Alignment(0, 0),
            clickable=True, 
        )

        def close_modal(e):
            if modal_bg in self.page.overlay:
                self.page.overlay.remove(modal_bg)
                self.page.update()

        def save_action(e):
            folder = path_input.value
            filename = filename_input.value
            full_path = os.path.join(folder, filename)
            
            if hasattr(self, 'current_preview_data') and self.current_preview_data:
                data = self.current_preview_data
                success = self._generate_pdf(data, full_path)
                
                if success:
                     print(f"[DEBUG] Zapisano PDF pomyślnie: {full_path}")
                else:
                     print(f"[ERROR] Błąd generowania PDF do: {full_path}")
                
                msg = f"Zapisano PDF: {full_path}" if success else "Błąd generowania PDF"
                color = ft.Colors.GREEN if success else ft.Colors.RED
                
                if self.page:
                    self.page.snack_bar = ft.SnackBar(ft.Text(msg), bgcolor=color)
                    self.page.snack_bar.open = True
                    close_modal(None)
            else:
                print("[ERROR] Brak danych do generowania PDF (current_preview_data is None)")
                if self.page:
                    self.page.snack_bar = ft.SnackBar(ft.Text("Brak danych do PDF"), bgcolor=ft.Colors.RED)
                    self.page.snack_bar.open = True
                    close_modal(None)

        # Dialog Box
        dialog_box = ft.Container(
            bgcolor=ft.Colors.WHITE,
            padding=20,
            border_radius=8,
            width=500,
            height=300,
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=15, color=ft.Colors.BLACK54),
            content=ft.Column([
                ft.Text("Zapisz PDF", size=20, weight="bold"),
                ft.Text("Wybierz lokalizację zapisu (ścieżka bezwzględna):"),
                path_input,
                filename_input,
                ft.Row([
                    ft.TextButton("Anuluj", on_click=close_modal),
                    ft.ElevatedButton("Zapisz", on_click=save_action)
                ], alignment=ft.MainAxisAlignment.END, spacing=10)
            ])
        )
        
        modal_bg.content = dialog_box
        
        self.page.overlay.append(modal_bg)
        self.page.update()

    # --- OLD HANDLERS (kept but unused now) ---
    def save_xml_result(self, e):
        pass

    def save_pdf_result(self, e):
        pass

    def _clean_invoice_xml(self, xml_str):
        """Pomocnicza metoda do czyszczenia XML z namespace'ów i prefiksów"""
        if not xml_str: 
             return ""
        
        # 1. Agresywne usunięcie xsi:schemaLocation
        xml_str = re.sub(r'xsi:schemaLocation\s*=\s*"[^"]*"', '', xml_str, flags=re.DOTALL)
        
        # 2. Usunięcie deklaracji przestrzeni nazw xmlns="..." i xmlns:prefix="..."
        xml_str = re.sub(r'xmlns(:[a-zA-Z0-9_]+)?\s*=\s*"[^"]*"', '', xml_str, flags=re.DOTALL)
        
        # 3. Usunięcie wszelkich pozostałych atrybutów z prefiksami (np. xsi:type="...")
        xml_str = re.sub(r'\s[a-zA-Z0-9_]+:[a-zA-Z0-9_]+\s*=\s*"[^"]*"', '', xml_str, flags=re.DOTALL)
        
        # 4. Usunięcie prefiksów z tagów (otwierających i zamykających)
        xml_str = re.sub(r'(<|/)[a-zA-Z0-9_]+:', r'\1', xml_str)
        
        return xml_str

    def _parse_xml_data(self, xml_str):
        try:
            xml_str = self._clean_invoice_xml(xml_str)

            root = ET.fromstring(xml_str)
            
            data = {}
            # Basic
            # Spróbuj znaleźć sekcję Fa (Faktura) lub szukaj bezpośrednio
            # Dla OVH struktura to Root -> Fa -> P_...
            # Ale po usunięciu namespace Root to Faktura.
            
            data['number'] = root.findtext('.//Fa/P_2') or root.findtext('.//P_2') or "N/A"
            data['date'] = root.findtext('.//Fa/P_1') or root.findtext('.//P_1') or "N/A"
            data['place'] = root.findtext('.//Fa/P_1M') or root.findtext('.//P_1M') or "N/A"
            
            # Seller
            # Podmiot1 to zwykle Sprzedawca w FA(3)
            s = root.find('.//Podmiot1')
            if s is None:
                # Fallback szukanie gdziekolwiek
                s = root.find('.//Sprzedawca') 

            if s:
                 s_addr = s.find('.//Adres')
                 nip_node = s.find('.//DaneIdentyfikacyjne/NIP') or s.find('.//NIP')
                 name_node = s.find('.//DaneIdentyfikacyjne/Nazwa') or s.find('.//Nazwa')
                 
                 data['seller'] = {
                     'nip': nip_node.text if nip_node is not None else "",
                     'name': name_node.text if name_node is not None else "Brak nazwy",
                     'address': f"{s_addr.findtext('AdresL1') or ''} {s_addr.findtext('AdresL2') or ''}".strip() if s_addr is not None else ""
                 }
                 
                 # Bank Accounts
                 accounts = []
                 for acc in s.findall('.//NrRachunku'):
                     if acc.text: accounts.append(acc.text)
                 data['bank_accounts'] = accounts
            else:
                 data['seller'] = {'nip': '', 'name': '', 'address': ''}
                 data['bank_accounts'] = []

            # Buyer
            b = root.find('.//Podmiot2')
            if b:
                 b_addr = b.find('.//Adres')
                 data['buyer'] = {
                     'nip': b.find('.//DaneIdentyfikacyjne/NIP').text if b.find('.//DaneIdentyfikacyjne/NIP') is not None else "",
                     'name': b.find('.//DaneIdentyfikacyjne/Nazwa').text if b.find('.//DaneIdentyfikacyjne/Nazwa') is not None else "",
                     'address': f"{b_addr.findtext('AdresL1') or ''} {b_addr.findtext('AdresL2') or ''}".strip() if b_addr is not None else ""
                 }
            else:
                 data['buyer'] = {}

            # Items
            items = []
            for row in root.findall('.//FaWiersz'):
                items.append({
                    'index': row.findtext('NrWierszaFa') or "",
                    'name': row.findtext('P_7') or "",
                    'qty': row.findtext('P_8B') or "0",
                    'unit': row.findtext('P_8A') or "szt",
                    'net_price': row.findtext('P_9A') or "0",
                    'net_val': row.findtext('P_11') or "0",
                    'vat': row.findtext('P_12') or "np"
                })
            data['items'] = items
            
            # Flags & Extra
            fa = root.find('.//Fa')
            data['currency'] = fa.findtext('KodWaluty') if fa is not None and fa.findtext('KodWaluty') else "PLN"
            data['total_net'] = fa.findtext('P_13_1') or "0.00" if fa is not None else "0.00"
            data['total_vat'] = fa.findtext('P_14_1') or "0.00" if fa is not None else "0.00"
            data['total_gross'] = fa.findtext('P_15') or "0.00" if fa is not None else "0.00"
            
            data['is_cash_method'] = bool(fa.findtext('P_16') == '1' or fa.findtext('MetodaKasowa') == '1') if fa else False
            data['is_reverse_charge'] = bool(fa.findtext('P_19') == '1' or fa.findtext('OdwrotneObciazenie') == '1') if fa else False
            
            # Attachments check (KSeF Node) - usually outside Fa, in Root
            data['has_attachment'] = (root.find('.//Zalacznik') is not None)

            # Pay
            pay = root.find('.//Platnosc')
            data['deadline'] = pay.find('.//Termin').text if pay is not None and pay.find('.//Termin') is not None else ""
            
            # Footer
            footer_text = ""
            stopka = root.find('.//Stopka')
            if stopka is not None:
                info_node = stopka.find('.//Informacje/StopkaFaktury')
                if info_node is not None and info_node.text:
                    footer_text += info_node.text + "\n"
                
                krs = stopka.findtext('.//Rejestry/KRS')
                regon = stopka.findtext('.//Rejestry/REGON')
                if krs: footer_text += f"KRS: {krs} "
                if regon: footer_text += f"REGON: {regon} "
            
            data['footer'] = footer_text.strip()
            
            return data
        except Exception as e:
            print(f"Błąd parsowania do podglądu: {e}")
            return None

    def _generate_pdf(self, data, path):
        try:
             pdf = FPDF()
             pdf.add_page()
             
             # Font - try DejaVu for PL support
             font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
             if os.path.exists(font_path):
                 # Remove unique=True which causes error in some fpdf2 versions
                 pdf.add_font("DejaVu", "", font_path)
                 pdf.set_font("DejaVu", size=10)
                 font_fam = "DejaVu"
             else:
                 pdf.set_font("Helvetica", size=10)
                 font_fam = "Helvetica"

             # Header
             pdf.set_font(font_fam, size=16)
             pdf.cell(0, 10, f"Faktura VAT: {data.get('number', '')}", ln=True, align='C')
             pdf.set_font(font_fam, size=10)
             pdf.cell(0, 10, f"Data wystawienia: {data.get('date', '')}, Miejsce: {data.get('place', '')}", ln=True, align='C')
             pdf.ln(10)
             
             # Seller/Buyer
             pdf.set_font(font_fam, size=12)
             pdf.cell(95, 10, "Sprzedawca:", border=0)
             pdf.cell(95, 10, "Nabywca:", border=0, ln=True)
             
             pdf.set_font(font_fam, size=10)
             
             s = data.get('seller', {})
             b = data.get('buyer', {})
             
             start_y = pdf.get_y()
             
             s_text = f"{s.get('name','')}\nNIP: {s.get('nip','')}\n{s.get('address','')}"
             if data.get('bank_accounts'):
                 s_text += "\n\nKonta bankowe:\n" + "\n".join(data.get('bank_accounts'))
             
             pdf.multi_cell(95, 5, s_text)
             end_y_s = pdf.get_y()
             
             pdf.set_xy(105, start_y)
             pdf.multi_cell(95, 5, f"{b.get('name','')}\nNIP: {b.get('nip','')}\n{b.get('address','')}")
             end_y_b = pdf.get_y()
             
             pdf.set_y(max(end_y_s, end_y_b) + 10)
             
             # Flags
             flags = []
             if data.get('is_cash_method'): flags.append("METODA KASOWA")
             if data.get('is_self_billing'): flags.append("SAMOFAKTUROWANIE")
             if data.get('is_reverse_charge'): flags.append("ODWROTNE OBCIĄŻENIE")
             if data.get('is_split_payment'): flags.append("MECHANIZM PODZIELONEJ PŁATNOŚCI")
             if data.get('is_exempt'): flags.append("ZWOLNIENIE Z PODATKU")
             
             if flags:
                 pdf.set_font(font_fam, size=10)
                 pdf.multi_cell(0, 5, "ADNOTACJE: " + " / ".join(flags), align='L')
                 pdf.ln(5)

             # Items Header
             pdf.set_fill_color(200, 220, 255)
             pdf.cell(10, 8, "Lp", 1, 0, 'C', True)
             pdf.cell(70, 8, "Nazwa", 1, 0, 'C', True)
             pdf.cell(15, 8, "Ilość", 1, 0, 'C', True)
             pdf.cell(15, 8, "J.m.", 1, 0, 'C', True)
             pdf.cell(25, 8, "Cena Netto", 1, 0, 'C', True)
             pdf.cell(15, 8, "VAT", 1, 0, 'C', True)
             pdf.cell(40, 8, "Wartość Netto", 1, 1, 'C', True)
             
             # Items
             pdf.set_font(font_fam, size=9)
             i = 1
             for item in data.get('items', []):
                 idx = item.get('index') or str(i)
                 
                 # Inteligentne skracanie nazwy, aby nie nachodziła na inne komórki
                 name = item.get('name', '')
                 # Max width ~68mm (dla komórki 70mm, margines 1mm z obu stron)
                 while pdf.get_string_width(name) > 68 and len(name) > 0:
                     name = name[:-1] # Proste ucięcie, można dodać '...'
                 
                 pdf.cell(10, 6, str(idx), 1)
                 pdf.cell(70, 6, name, 1)
                 pdf.cell(15, 6, str(item.get('qty','')), 1, 0, 'R')
                 pdf.cell(15, 6, str(item.get('unit','')), 1, 0, 'C')
                 pdf.cell(25, 6, str(item.get('net_price','')), 1, 0, 'R')
                 pdf.cell(15, 6, f"{item.get('vat','')}%", 1, 0, 'R')
                 pdf.cell(40, 6, str(item.get('net_val','')), 1, 1, 'R')
                 i+=1
             
             pdf.set_font(font_fam, size=10)
             pdf.ln(5)
             
             # Totals
             pdf.cell(130, 8, "", 0)
             pdf.cell(30, 8, "Razem Netto:", 0, 0, 'R')
             pdf.cell(30, 8, f"{data.get('total_net','')} {data.get('currency','')}", 0, 1, 'R')

             pdf.cell(130, 8, "", 0)
             pdf.cell(30, 8, "Razem VAT:", 0, 0, 'R')
             pdf.cell(30, 8, f"{data.get('total_vat','')} {data.get('currency','')}", 0, 1, 'R')
             
             pdf.set_font(font_fam, size=12) # Bold via size or style if supported
             pdf.cell(130, 10, "", 0)
             pdf.cell(30, 10, "Razem Brutto:", 0, 0, 'R')
             pdf.cell(30, 10, f"{data.get('total_gross','')} {data.get('currency','')}", 0, 1, 'R')
             
             pdf.ln(10)
             if data.get('deadline'):
                  pdf.cell(0, 10, f"Termin płatności: {data.get('deadline')}", ln=True)

             # Footer / Stopka
             if data.get('footer'):
                 pdf.ln(10)
                 pdf.set_font(font_fam, size=8)
                 pdf.multi_cell(0, 5, data['footer'])
                 
             # Attachment Page
             if data.get('has_attachment'):
                 pdf.add_page()
                 pdf.set_font(font_fam, size=16)
                 pdf.cell(0, 20, "ZAŁĄCZNIK W FORMACIE USTRUKTURYZOWANYM", ln=True, align='C')
                 pdf.set_font(font_fam, size=10)
                 pdf.multi_cell(0, 5, "Dokument zawiera załącznik w formacie ustrukturyzowanym (XML).\nAby zapoznać się z jego treścią, pobierz plik XML z systemu KSeF.")

             pdf.output(path)
             return True
        except Exception as e:
             print(f"PDF Gen Error: {e}")
             return False

    def export_xml(self, invoice):
        """Export invoice to XML (KSeF format)"""
        db = next(get_db())
        try:
            full_inv = db.merge(invoice)
            
            # For PURCHASE invoices, prefer original KSeF XML if available
            if full_inv.category == InvoiceCategory.PURCHASE and full_inv.ksef_xml:
                 xml_content = full_inv.ksef_xml
            else:
                 # Regenerate or generate fresh
                 config = db.query(CompanyConfig).first()
                 if not config:
                     if self.page:
                         self.page.snack_bar = ft.SnackBar(ft.Text("Brak konfiguracji firmy!"))
                         self.page.snack_bar.open = True
                         self.page.update()
                     return
                 
                 xml_content = self.xml_gen.generate_invoice_xml(full_inv, config)
            
            self.current_preview_xml_content = xml_content
            
            # Trigger file picker via central handler logic
            self.save_xml_click(full_inv.number)
                
        except Exception as e:
            print(f"Export Error: {e}")
            if self.page:
                 self.page.snack_bar = ft.SnackBar(ft.Text(f"Błąd eksportu: {e}"))
                 self.page.snack_bar.open = True
                 self.page.update()
        finally:
            db.close()

    def show_xml_preview(self, invoice):
        """
        Pokazuje podgląd faktury (graficzny + XML).
        Dla faktur pobranych z KSeF pobiera oryginalny XML z KSeF.
        Dla faktur własnych generuje XML.
        """
        db = next(get_db())
        try:
            full_inv = db.merge(invoice)
            xml_content = ""
            
            if full_inv.category == InvoiceCategory.PURCHASE and full_inv.ksef_number:
                 # Check DB cache first
                 if full_inv.ksef_xml:
                     xml_content = full_inv.ksef_xml
                 
                 if not xml_content:
                     try:
                          config = db.query(CompanyConfig).first()
                          
                          client = KsefClient(config.ksef_token)
                          client.authenticate(config.nip) 
                          
                          raw_xml = client.get_invoice_xml(full_inv.ksef_number)
                          if isinstance(raw_xml, bytes):
                               xml_content = raw_xml.decode("utf-8", errors="ignore")
                          else:
                               xml_content = str(raw_xml)
                          
                          # Save to DB cache
                          if xml_content and "<Faktura" in xml_content:
                               full_inv.ksef_xml = xml_content
                               db.commit()
                               # db.refresh(full_inv)
                                   
                     except Exception as e:
                          xml_content = f"Błąd pobierania XML z KSeF: {str(e)}"
            else:
                config = db.query(CompanyConfig).first()
                if not config:
                    if self.page:
                        self.page.snack_bar = ft.SnackBar(ft.Text("Brak konfiguracji firmy! Uzupełnij w Ustawieniach."))
                        self.page.snack_bar.open = True
                        self.page.update()
                    return

                try:
                    xml_content = self.xml_gen.generate_invoice_xml(full_inv, config)
                except Exception as e:
                    if self.page:
                        self.page.snack_bar = ft.SnackBar(ft.Text(f"Błąd generowania XML: {str(e)}"))
                        self.page.snack_bar.open = True
                        self.page.update()
                    return
            
            # PARSE DATA
            data = self._parse_xml_data(xml_content)
            
            content_control = None
            if data:
                 def add_product(item_data):
                     try:
                         db = next(get_db())
                         try:
                             # Check if exists
                             exists = db.query(Product).filter(Product.name == item_data['name']).first()
                             if exists:
                                 if self.page:
                                     self.page.snack_bar = ft.SnackBar(ft.Text(f"Produkt '{item_data['name']}' już istnieje."))
                                     self.page.snack_bar.open = True
                                     self.page.update()
                                 return

                             # Parse price check
                             try:
                                 price = float(item_data['net_price'].replace(',','.'))
                             except:
                                 price = 0.0

                             # Vat mapping
                             try:
                                 vat_val = float(item_data['vat']) / 100.0
                             except:
                                 vat_val = 0.23
                             
                             new_prod = Product(
                                 name=item_data['name'],
                                 unit=item_data['unit'],
                                 net_price=price, # Use purchase price as base selling price initially
                                 purchase_net_price=price,
                                 vat_rate=vat_val
                             )
                             db.add(new_prod)
                             db.commit()
                             
                             if self.page:
                                 self.page.snack_bar = ft.SnackBar(ft.Text(f"Dodano produkt: {item_data['name']}"))
                                 self.page.snack_bar.open = True
                                 self.page.update()
                         finally:
                             db.close()
                     except Exception as e:
                         print(f"Error adding product: {e}")

                 items_ctrls = []
                 for item in data['items']:
                     # Capture item value in closure default arg
                     items_ctrls.append(
                         ft.Row([
                             ft.Row([
                                 ft.IconButton(
                                     # Używając 'icon' zamiast 'content' dla compatibility z tą wersją Flet
                                     icon=ft.Text("+", size=16, weight="bold"), 
                                     tooltip="Dodaj produkt do bazy", 
                                     on_click=lambda e, i=item: add_product(i)
                                 ),
                                 ft.Text(item['name'], expand=1)
                             ], expand=3, spacing=5),
                             ft.Text(item['qty'], expand=1, text_align="right"),
                             ft.Text(item['unit'], expand=1, text_align="center"),
                             ft.Text(item['net_price'], expand=1, text_align="right"),
                             ft.Text(f"{item['vat']}%", expand=1, text_align="right"),
                             ft.Text(item['net_val'], expand=1, text_align="right"),
                         ])
                     )
                     
                 content_control = ft.Column([
                     ft.Text(f"Faktura {data['number']}", size=20, weight="bold", text_align="center"),
                     ft.Text(f"Data: {data['date']}, Miejsce: {data['place']}", text_align="center"),
                     ft.Divider(),
                     ft.Row([
                         ft.Column([
                             ft.Text("Sprzedawca", weight="bold"),
                             ft.Text(data['seller']['name']),
                             ft.Text(f"NIP: {data['seller']['nip']}"),
                             ft.Text(data['seller']['address']),
                         ], expand=1),
                         ft.Column([
                             ft.Text("Nabywca", weight="bold"),
                             ft.Text(data['buyer']['name']),
                             ft.Text(f"NIP: {data['buyer']['nip']}"),
                             ft.Text(data['buyer']['address']),
                         ], expand=1)
                     ]),
                     ft.Divider(),
                     ft.Text("Pozycje:", weight="bold"),
                     ft.Row([
                         ft.Text("Nazwa", weight="bold", expand=3),
                         ft.Text("Ilość", weight="bold", expand=1, text_align="right"),
                         ft.Text("J.m.", weight="bold", expand=1, text_align="center"),
                         ft.Text("Cena Netto", weight="bold", expand=1, text_align="right"),
                         ft.Text("VAT", weight="bold", expand=1, text_align="right"),
                         ft.Text("Wartość Netto", weight="bold", expand=1, text_align="right"),
                     ]),
                     ft.Column(items_ctrls),
                     ft.Divider(),
                     ft.Row([
                         ft.Text("Razem Netto:", weight="bold"),
                         ft.Text(f"{data['total_net']} {data['currency']}")
                     ], alignment="end"),
                     ft.Row([
                         ft.Text("Razem VAT:", weight="bold"),
                         ft.Text(f"{data['total_vat']} {data['currency']}")
                     ], alignment="end"),
                     ft.Row([
                         ft.Text("Razem Brutto:", size=16, weight="bold"),
                         ft.Text(f"{data['total_gross']} {data['currency']}", size=16, weight="bold")
                     ], alignment="end"),
                     ft.Text(f"Termin płatności: {data['deadline']}", weight="bold") if data['deadline'] else ft.Container(),
                     ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
                     ft.Text(data['footer'], size=10, color=ft.Colors.GREY_700, selectable=True) if data.get('footer') else ft.Container()
                 ], scroll=ft.ScrollMode.AUTO)
            else:
                 content_control = ft.Column([
                      ft.Text("Nie udało się sparsować XML do podglądu graficznego.", color="red"),
                      ft.Text(xml_content, font_family="monospace", selectable=True, size=12)
                 ], scroll=ft.ScrollMode.AUTO)

            def print_pdf(e):
                 if not data: return
                 import tempfile
                 tmp_path = os.path.join(tempfile.gettempdir(), f"print_{invoice.number}.pdf")
                 if self._generate_pdf(data, tmp_path):
                      # Linux specific print/open
                      os.system(f"xdg-open {tmp_path}")
                 else:
                      if self.page:
                           self.page.snack_bar = ft.SnackBar(ft.Text("Wydruk nie powiódł się"))
                           self.page.snack_bar.open = True
                           self.page.update()

            # Store current state for FilePickers
            self.current_preview_xml_content = xml_content
            self.current_preview_data = data
            
            # FilePickers are now initialized in __init__ and added to controls
            # No need to check or add to overlay here.
            
            dlg = ft.AlertDialog(
                title=ft.Text(f"Podgląd faktury: {invoice.number}"),
                content=ft.Container(
                    content=content_control,
                    width=800, height=600, bgcolor=ft.Colors.GREY_100, padding=10,
                    border_radius=10,
                ),
                actions=[
                    ft.TextButton("Zapisz XML", on_click=lambda _: self.save_xml_click(invoice.number)),
                    ft.TextButton("Zapisz PDF", on_click=lambda _: self.save_pdf_click(invoice.number)),
                    ft.TextButton("Drukuj", on_click=print_pdf),
                    ft.TextButton("Zamknij", on_click=lambda e: setattr(dlg, 'open', False) or self.page.update()),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            self.page.overlay.append(dlg)
            dlg.open = True
            self.page.update()
        except Exception as e:
             print(f"Błąd podglądu XML: {e}")
             if self.page:
                 self.page.snack_bar = ft.SnackBar(ft.Text(f"Błąd: {e}"))
                 self.page.snack_bar.open = True
                 self.page.update()
        finally:
            db.close()

    def download_ksef_invoices(self, e):
        def start_download(mode):
            dl_dlg.open = False
            self.page.update()
            self._execute_ksef_download(mode)

        dl_dlg = ft.AlertDialog(
            title=ft.Text("Pobieranie faktur"),
            content=ft.Text("Wybierz zakres pobierania (zakup)."),
            actions=[
                ft.TextButton("Anuluj", on_click=lambda e: setattr(dl_dlg, 'open', False) or self.page.update()),
                ft.ElevatedButton("od ostatniego pobrania", 
                    on_click=lambda e: start_download("LATEST")),
                ft.ElevatedButton("Wszystkie (wg dat w filtrze)", 
                    on_click=lambda e: start_download("ALL")),
            ],
            actions_alignment=ft.MainAxisAlignment.END
        )
        self.page.overlay.append(dl_dlg)
        dl_dlg.open = True
        self.page.update()

    def _execute_ksef_download(self, mode="ALL"):
        # 1. Konfiguracja i Walidacja
        db = next(get_db())
        config = db.query(CompanyConfig).first()
        if not config or not config.ksef_token or not config.nip:
             if self.page:
                 self.page.snack_bar = ft.SnackBar(ft.Text("Skonfiguruj NIP i Token KSeF w ustawieniach!"))
                 self.page.snack_bar.open = True
                 self.page.update()
             db.close()
             return

        # 2. Wyświetlenie postępu
        status_txt = ft.Text("Łączenie z KSeF...", key="status_text")
        progress_dlg = ft.AlertDialog(
            title=ft.Text("Pobieranie faktur z KSeF"),
            content=ft.Column([
                ft.ProgressRing(),
                status_txt
            ], height=100, alignment=ft.MainAxisAlignment.CENTER),
            modal=True
        )
        self.page.dialog = progress_dlg
        progress_dlg.open = True
        self.page.update()

        try:
             # 3. Połączenie
             client = KsefClient(config.ksef_token)
             auth_ok = client.authenticate(config.nip)
             
             status_txt.value = "Pobieranie listy..."
             self.page.update()
             
             # 4. Pobranie listy
             d_from = None
             d_to = datetime.now()
             
             if mode == "LATEST":
                 last_dt = db.query(func.max(Invoice.date_issue)).filter(Invoice.category == InvoiceCategory.PURCHASE).scalar()
                 if last_dt:
                     d_from = last_dt.replace(hour=0, minute=0, second=0, microsecond=0)

             if not d_from:
                 try:
                     d_from = datetime.strptime(self.date_from.value, "%Y-%m-%d")
                 except:
                     d_from = datetime.now().replace(day=1)
             
             if mode == "ALL":
                 try:
                     d_to = datetime.strptime(self.date_to.value, "%Y-%m-%d")
                     d_to = d_to.replace(hour=23, minute=59, second=59)
                 except:
                     pass
             
             resp_list = client.get_invoice_list(d_from, d_to, subject_type="subject2") # Zakup
             
             # Obsługa formatu response z KSeF v2 (invoices) oraz starego (invoiceHeaderList)
             headers = resp_list.get("invoices", [])
             if not headers and "invoiceHeaderList" in resp_list:
                  headers = resp_list["invoiceHeaderList"]

             count_new = 0
             
             status_txt.value = f"Przetwarzanie {len(headers)} faktur..."
             self.page.update()
             
             for hdr in headers:
                 # Mapowanie pól: nowe API (ksefNumber) vs stare (ksefReferenceNumber)
                 ksef_no = hdr.get("ksefNumber") or hdr.get("ksefReferenceNumber")
                 inv_ref = hdr.get("invoiceNumber") or hdr.get("invoiceReferenceNumber")
                 
                 # Sprawdź czy istnieje
                 exists = db.query(Invoice).filter(Invoice.ksef_number == ksef_no).first()
                 if exists: continue
                 
                 # Tworzenie nowej faktury z nagłówka
                 inv_date_str = hdr.get("invoicingDate", datetime.now().strftime("%Y-%m-%d"))
                 try:
                     # Obsługa formatów ISO, np. 2023-05-15T12:00:00...
                     inv_date = datetime.fromisoformat(inv_date_str)
                     if inv_date.tzinfo:
                         inv_date = inv_date.replace(tzinfo=None)
                 except ValueError:
                     try:
                        inv_date = datetime.strptime(inv_date_str[:10], "%Y-%m-%d")
                     except:
                        inv_date = datetime.now()
                 
                 amount_net = float(hdr.get("netAmount") or hdr.get("net") or 0)
                 amount_gross = float(hdr.get("grossAmount") or hdr.get("gross") or 0)
                 
                 # Próba wyciągnięcia danych wystawcy
                 issuer_nip = "Nieznany"
                 issuer_name = "Nieznany"
                 
                 try:
                      if "seller" in hdr:
                           issuer_nip = hdr["seller"].get("nip")
                           # Spróbuj pobrać nazwę z metadanych KSeF, jeśli dostępna
                           issuer_name = hdr["seller"].get("name", f"Kontrahent KSeF {issuer_nip}")
                      else:
                           subject = hdr.get("subjectBy", {})
                           issuer_nip = subject.get("issuedByIdentifier", {}).get("identifier")
                           issuer_name = subject.get("issuedByName", f"Kontrahent KSeF {issuer_nip}")
                 except: pass

                 # Kontrahent
                 contractor = db.query(Contractor).filter(Contractor.nip == issuer_nip).first()
                 if not contractor and issuer_nip:
                      # Jeśli nazwa jest generyczna, spróbujmy ją pobrać z GUS (opcjonalnie)
                      # Na razie używamy tego co przyszło z KSeF lub placeholder
                      
                      contractor = Contractor(
                          name=issuer_name, 
                          nip=issuer_nip,
                          is_vat_payer=True
                      )
                      db.add(contractor)
                      db.flush()
                 
                 # Pobranie szczegółów płatności oraz PEŁNYCH danych kontrahenta z XML
                 is_paid_status = False
                 paid_val = 0.0
                 payment_method_str = "Pozostałe"
                 final_inv_number = inv_ref or ksef_no # Fallback numeru - use full KSeF number to avoid unique constraint violation
                 payment_deadline = None
                 place_issue = None
                 xml_str = None
                 
                 try:
                     raw_xml = client.get_invoice_xml(ksef_no)
                     if raw_xml:
                         # Sprawdź typ danych
                         if isinstance(raw_xml, str):
                              xml_str = raw_xml
                         else:
                              xml_str = raw_xml.decode("utf-8", errors="ignore")
                         
                         # Parse root to get namespaces map
                         # Standard namespace handling in ElementTree is tedious with default ns.
                         # We will strip namespaces for simplicity as before.
                         
                         xml_str_clean = self._clean_invoice_xml(xml_str)
                         
                         root = ET.fromstring(xml_str_clean)
                         
                         # 0. Dane podstawowe (P_1) - Data wystawienia
                         p1_node = root.find(".//Fa/P_1")
                         if p1_node is not None and p1_node.text:
                             try:
                                 inv_date = datetime.strptime(p1_node.text, "%Y-%m-%d").date()
                             except:
                                 pass # Fallback to metadata date

                         # P_1M - Miejsce wystawienia
                         place_issue = None
                         p1m_node = root.find(".//Fa/P_1M")
                         if p1m_node is not None and p1m_node.text:
                              place_issue = p1m_node.text

                         # 1. Numer faktury (P_2)
                         # Szukamy P_2 wszedzie (Fa/P_2)
                         p2_node = root.find(".//Fa/P_2")
                         if p2_node is not None and p2_node.text:
                              final_inv_number = p2_node.text
                         elif root.find(".//P_2") is not None and root.find(".//P_2").text:
                               final_inv_number = root.find(".//P_2").text

                         # 2. Termin płatności (Fa/Platnosc/TerminPlatnosci/Termin)
                         # Struktura z przykładu: <Fa><Platnosc><TerminPlatnosci><Termin>2026-02-04</Termin>...
                         platnosci = root.find(".//Fa/Platnosc")
                         if platnosci is None: platnosci = root.find(".//Platnosci")
                         
                         if platnosci:
                              termin_node = platnosci.find(".//Termin")
                              if termin_node is not None and termin_node.text:
                                   try:
                                       payment_deadline = datetime.strptime(termin_node.text, "%Y-%m-%d")
                                   except: pass
                              
                              # Sprawdzenie Zaplacono (dla innych struktur)
                              zaplacono = platnosci.find("Zaplacono")
                              if zaplacono is not None and zaplacono.text == "1":
                                   is_paid_status = True
                         
                         # 3. Aktualizacja danych kontrahenta z XML (adres, pełna nazwa)
                         # Szukamy sekcji Podmiot1 (Sprzedawca)
                         podmiot1 = root.find(".//Podmiot1")
                         if podmiot1 and contractor:
                             dane_ident = podmiot1.find("DaneIdentyfikacyjne")
                             dane_adres = podmiot1.find("Adres")
                             
                             if dane_ident and contractor.name.startswith("Kontrahent KSeF"):
                                  full_name = dane_ident.find("Nazwa")
                                  if full_name is not None and full_name.text:
                                       contractor.name = full_name.text
                             
                             if dane_adres:
                                  # Obsługa formatu standardowego (AdresPol/Zag) oraz prostego (AdresL1)
                                  adres_l1 = dane_adres.find("AdresPol")
                                  if adres_l1 is None: adres_l1 = dane_adres.find("AdresZag")
                                  
                                  # Format uproszczony (np. OVH) - pola bezpośrednio w Adres
                                  simple_l1 = dane_adres.find("AdresL1")
                                  
                                  if simple_l1 is not None:
                                       # Struktura płaska <Adres><AdresL1>...</AdresL1><AdresL2>...</AdresL2><KodKraju>
                                       ulica_txt = simple_l1.text if simple_l1.text else ""
                                       l2 = dane_adres.find("AdresL2")
                                       l2_txt = l2.text if l2 is not None and l2.text else ""
                                       kraj_node = dane_adres.find("KodKraju")
                                       kraj_txt = kraj_node.text if kraj_node is not None else "PL"

                                       contractor.address = ulica_txt.strip()
                                       
                                       # Próba wyciagnięcia kodu i miasta z AdresL2 (np. "53-332 WROCLAW")
                                       contractor.city = l2_txt # Domyślnie calosc
                                       parsed_l2 = False
                                       if l2_txt:
                                           # Regex na kod pocztowy XX-XXX na początku
                                           match_code = re.match(r'^(\d{2}-\d{3})\s+(.*)$', l2_txt.strip())
                                           if match_code:
                                                contractor.postal_code = match_code.group(1)
                                                contractor.city = match_code.group(2)
                                                parsed_l2 = True
                                       
                                       if not parsed_l2 and not contractor.postal_code:
                                            contractor.postal_code = ""

                                       contractor.country_code = kraj_txt
                                       db.add(contractor)
                                       db.flush()

                                  elif adres_l1:
                                       # Struktura standardowa
                                       ulica = adres_l1.find("Ulica")
                                       nr_domu = adres_l1.find("NrDomu")
                                       nr_lok = adres_l1.find("NrLokalu")
                                       miasto = adres_l1.find("Miejscowosc")
                                       kod = adres_l1.find("KodPocztowy") # KodPocztowy (PL) lub Kod (Zag)
                                       if kod is None: kod = adres_l1.find("Kod")
                                       kraj = adres_l1.find("KodKraju")
                                       
                                       addr_parts = []
                                       if ulica and ulica.text: addr_parts.append(ulica.text)
                                       if nr_domu and nr_domu.text: addr_parts.append(nr_domu.text)
                                       if nr_lok and nr_lok.text: addr_parts.append(f"lok. {nr_lok.text}")
                                       
                                       contractor.address = " ".join(addr_parts)
                                       contractor.city = miasto.text if miasto else ""
                                       contractor.postal_code = kod.text if kod else ""
                                       contractor.country_code = kraj.text if kraj else "PL"
                                       db.add(contractor) 
                                       db.flush()

                 except Exception as ex:
                     print(f"Błąd parsowania XML faktury {ksef_no}: {ex}")

                 if is_paid_status:
                     paid_val = amount_gross

                 # Dodatkowe flagi KSeF (P_16, P_19, Bank)
                 is_cash = False
                 is_self_billing = False
                 is_reverse = False
                 is_split = False
                 is_exempt = False
                 has_attach = False
                 bank_accs = []
                 
                 if xml_str:
                     try:
                         # Use existing clean util or ad-hoc
                         # Reuse existing root from earlier if possible, but safe to reparse clean
                         # Actually earlier we did: root = ET.fromstring(xml_str_clean)
                         
                         fa = root.find(".//Fa")
                         if fa is not None:
                             is_cash = (fa.findtext("P_16") == "1" or fa.findtext("MetodaKasowa") == "1")
                             is_self_billing = (fa.findtext("P_17") == "1")
                             # P_18 is usually Reverse Charge in P_18 or P_18A in some. In FA(2) P_18 is reverse charge.
                             is_reverse = (fa.findtext("P_18") == "1" or fa.findtext("OdwrotneObciazenie") == "1")
                             is_split = (fa.findtext("P_18A") == "1")
                             
                             # Zwolnienie P_19 (Sequence inside Zwolnienie choice)
                             # Since elementtree find searches recursively with .// if specified, or direct child.
                             # P_19 is deep.
                             p_19_node = fa.find(".//P_19")
                             if p_19_node is not None and p_19_node.text == "1":
                                 is_exempt = True
                         
                         if root.find(".//Zalacznik") is not None:
                             has_attach = True
                             
                         # Bank Accounts (usually in Podmiot1)
                         p1 = root.find(".//Podmiot1")
                         if p1:
                             for acc in p1.findall(".//NrRachunku"):
                                 if acc.text: bank_accs.append(acc.text)
                     except: pass

                 # --- Items Parsing & Preparation ---
                 items_objs = []
                 if xml_str:
                    try:
                        idx_ctr = 1
                        for row in root.findall('.//FaWiersz'):
                            try:
                                name_txt = row.findtext('P_7') or "Towar/Usługa"
                                qty_txt = row.findtext('P_8B', "1").replace(',', '.')
                                unit_txt = row.findtext('P_8A') or "szt"
                                net_price_txt = row.findtext('P_9A', "0").replace(',', '.')
                                net_val_txt = row.findtext('P_11', "0").replace(',', '.')
                                vat_txt = row.findtext('P_12', "23") 
                                
                                qty = float(qty_txt)
                                net_price = float(net_price_txt)
                                net_val = float(net_val_txt)
                                
                                # Parse VAT
                                vat_rate = 0.23
                                if vat_txt.isdigit():
                                    vat_rate = float(vat_txt) / 100.0
                                elif vat_txt == "zw":
                                    vat_rate = 0.0

                                # Approx gross
                                gross_val = net_val * (1 + vat_rate)
                                
                                items_objs.append(InvoiceItem(
                                    index=idx_ctr,
                                    product_name=name_txt,
                                    quantity=qty,
                                    unit=unit_txt,
                                    net_price=net_price,
                                    net_value=net_val, # Note: Model might compute this, but we set it
                                    vat_rate=vat_rate,
                                    gross_value=gross_val,
                                    pkwiu=None
                                ))
                                idx_ctr += 1
                            except Exception as e:
                                print(f"Row parse error for {ksef_no}: {e}")
                    except: pass
                 # -----------------------------------

                 new_inv = Invoice(
                     number=final_inv_number,
                     ksef_number=ksef_no,
                     ksef_xml=xml_str,
                     category=InvoiceCategory.PURCHASE,
                     type=InvoiceType.VAT,
                     date_issue=inv_date,
                     date_sale=inv_date, # Assumed
                     place_of_issue=place_issue,
                     payment_deadline=payment_deadline,
                     contractor_id=contractor.id if contractor else None,
                     total_net=amount_net,
                     total_gross=amount_gross,
                     is_sent_to_ksef=True,
                     is_cash_accounting=is_cash,
                     is_self_billing=is_self_billing,
                     is_reverse_charge=is_reverse,
                     is_split_payment=is_split,
                     is_exempt=is_exempt,
                     has_attachment=has_attach,
                     bank_accounts="; ".join(bank_accs) if bank_accs else None,
                     notes="Pobrano z KSeF",
                     is_paid=is_paid_status,
                     paid_amount=paid_val,
                     payment_method=payment_method_str
                 )
                 
                 db.add(new_inv)
                 db.flush() # Get ID
                 
                 for it in items_objs:
                     it.invoice_id = new_inv.id
                     db.add(it)

                 count_new += 1
                 
             db.commit()
             
             progress_dlg.open = False
             self.page.update()
             
             if self.page:
                 self.page.snack_bar = ft.SnackBar(ft.Text(f"Pobrano {count_new} nowych faktur."))
                 self.page.snack_bar.open = True
                 self.load_invoices()
             
        except Exception as ex:
             progress_dlg.open = False
             self.page.update()
             if self.page:
                 self.page.snack_bar = ft.SnackBar(ft.Text(f"Błąd: {str(ex)}"))
                 self.page.snack_bar.open = True
             print(f"Błąd download_ksef: {ex}")
             traceback.print_exc()
             
        finally:
             db.close()

    def apply_filters(self, e):
        self.load_invoices()

    def open_advanced_filters(self, e):
        pass

    def open_add_invoice_dialog(self, e=None, edit_invoice_id=None, readonly=False):
        db = next(get_db())
        contractors = db.query(Contractor).all()
        products = db.query(Product).all()
        active_prod_dd = None
        active_on_prod_change = None
        config = db.query(CompanyConfig).first()
        
        edit_mode = (edit_invoice_id is not None)
        existing_invoice = None
        if edit_mode:
            # Eagerly load items to avoid DetachedInstanceError after session close
            existing_invoice = db.query(Invoice).options(
                joinedload(Invoice.items),
                joinedload(Invoice.contractor)
            ).filter(Invoice.id == edit_invoice_id).first()
            if not existing_invoice:
                 db.close()
                 return # Should not happen

        # Safety Check for KseF
        is_locked_ksef = False
        if edit_mode and existing_invoice:
            if existing_invoice.is_sent_to_ksef and existing_invoice.category == InvoiceCategory.SALES:
                is_locked_ksef = True
            if existing_invoice.ksef_number and existing_invoice.category == InvoiceCategory.PURCHASE:
                is_locked_ksef = True
            
        db.close()
        
        # Force readonly if locked (though user might want to view it via this method)
        # But user requested distinct "Preview" logic.
        
        dialog_title = "Nowy dokument"

        # REPAIR / SYNC LOGIC with KsefLogic Module
        # Ensures that if we have XML but missing DB data (Items, Payment Info), we repair it now.
        if edit_mode and existing_invoice and existing_invoice.ksef_xml:
             # Basic check if repair needed: no items? default payment method?
             needs_repair = False
             if not existing_invoice.items: needs_repair = True
             if not existing_invoice.payment_method or existing_invoice.payment_method == "Przelew":
                 # Could be actual Przelew, but if XML has something else, we want it.
                 # Let the logic decide. 
                 pass # Logic handles this
             
             # Always run sync for safety on 'Preview' of KSeF invoice
             try:
                 print(f"Syncing invoice {existing_invoice.id} with KSeF XML...")
                 db = next(get_db())
                 refreshed_inv = KsefLogic.save_invoice_from_xml(db, existing_invoice.id)
                 
                 if refreshed_inv:
                     # Update the local object used for UI initialization
                     existing_invoice.tax_system = refreshed_inv.tax_system # Sync Tax System!
                     existing_invoice.payment_method = refreshed_inv.payment_method
                     existing_invoice.payment_deadline = refreshed_inv.payment_deadline
                     existing_invoice.bank_accounts = refreshed_inv.bank_accounts
                     
                     # Crucially: Update items. Since existing_invoice is detached and loaded previously,
                     # its .items list is stale (empty).
                     # We attach the fresh items list (as plain objects / or keep them detached)
                     # The loop below iterates over existing_invoice.items.
                     # We temporarily patch it.
                     existing_invoice.items = [i for i in refreshed_inv.items]
                     # Restore transient ZW flags from logic parsing if possible
                     for db_item, mem_item in zip(existing_invoice.items, refreshed_inv.items):
                         if getattr(mem_item, 'is_exempt_zw', False) or (mem_item.pkwiu == "ZW" and mem_item.vat_rate == 0.0):
                             db_item.is_exempt_zw = True 
                         else:
                             db_item.is_exempt_zw = False 
                     
                 db.close()
             except Exception as ex:
                 print(f"Sync Error: {ex}")

        if edit_mode:
             dialog_title = f"Edycja: {existing_invoice.number}"
        if readonly:
             dialog_title = f"Podgląd: {existing_invoice.number}" if existing_invoice else "Podgląd"

        # --- Helper for ReadOnly Controls ---
        def ro(ctrl, override_readonly=None):
            is_ro = readonly if override_readonly is None else override_readonly
            if is_ro:
                if isinstance(ctrl, (ft.TextField, ft.Dropdown)):
                    ctrl.read_only = True
                    ctrl.border = ft.InputBorder.NONE # Visual cleaner lookup
                elif isinstance(ctrl, (ft.IconButton, ft.ElevatedButton, ft.Checkbox)):
                    ctrl.disabled = True
            return ctrl

        if edit_mode:
             dialog_title = f"Edycja dokumentu {existing_invoice.number}"
             # Ensure lock for purchase KSeF invoices if requested
             # Logic: Lock if Purchase (KSeF) OR Sales (Sent to KSeF)
             if self.category == InvoiceCategory.PURCHASE:
                  # For purchase, assume mostly readonly if it's external.
                  # If we created it manually as a draft, maybe editable?
                  # But usually Purchase = Downloaded.
                  if existing_invoice.ksef_number or existing_invoice.ksef_xml or existing_invoice.is_sent_to_ksef:
                      is_locked_ksef = True
             elif self.category == InvoiceCategory.SALES:
                  if existing_invoice.is_sent_to_ksef:
                       is_locked_ksef = True
             
             if is_locked_ksef:
                 dialog_title += " (Tylko odczyt - KSeF)"
             if readonly:
                 dialog_title = f"Podgląd dokumentu {existing_invoice.number}"
        elif self.category == InvoiceCategory.PURCHASE:
             dialog_title = "Rejestracja Faktury Zakupu"
        elif self.category == InvoiceCategory.SALES:
             dialog_title = "Wystaw fakturę sprzedaży"
             
        # Helper for bank account but also enforce locking on all inputs
        if is_locked_ksef:
            # We must enforce readonly on ALL created controls later, 
            # OR wrap them. But simpler to use the 'ro' helper extensively or set disabled at end.
            pass

        # Domyślny system podatkowy
        if edit_mode and existing_invoice:
            default_system = existing_invoice.tax_system
        elif self.category == InvoiceCategory.PURCHASE:
             # Purchase invoices always treated as input VAT for now
             default_system = TaxSystem.VAT
        else:
            default_system = config.default_tax_system if config and config.default_tax_system else TaxSystem.RYCZALT
            
        # If Purchase and synced as VAT, default_system is VAT.
        # This controls 'visible' of columns. is_ryczalt = ...
        
        # Ukryty, używany tylko do przekazania wartości logicznej
        tax_system_dd = ft.TextField(value=default_system.value, visible=False)

        contractor_dd = ft.Dropdown(
            label="Wybierz kontrahenta", 
            options=[ft.dropdown.Option(text=c.name, key=str(c.id)) for c in contractors],
            value=str(existing_invoice.contractor_id) if edit_mode and existing_invoice.contractor_id else None,
            expand=True,
            disabled=is_locked_ksef
        )
        
        invoice_type_options = [
            ft.dropdown.Option(text="Faktura VAT", key=InvoiceType.VAT.value),
            ft.dropdown.Option(text="Faktura (bez VAT)", key=InvoiceType.RYCZALT.value),
            ft.dropdown.Option(text="Faktura Marża", key=InvoiceType.MARZA.value),
            ft.dropdown.Option(text="Korekta", key=InvoiceType.KOREKTA.value),
            ft.dropdown.Option(text="Zaliczka", key=InvoiceType.ZALICZKA.value),
        ]
        
        invoice_type = ft.Dropdown(
            label="Typ dokumentu",
            value=(existing_invoice.type.value if edit_mode else (InvoiceType.VAT.value if default_system == TaxSystem.VAT else InvoiceType.RYCZALT.value)),
            options=invoice_type_options,
            width=200,
            disabled=is_locked_ksef
        )

        # Place of issue
        place_init = existing_invoice.place_of_issue if edit_mode else (config.city if config else "")
        place_of_issue_field = ft.TextField(label="Miejsce wystawienia", value=place_init, width=200, disabled=is_locked_ksef)

        # Dates

        def refresh_contractors(selected_id=None):
            db = next(get_db())
            c_list = db.query(Contractor).all()
            db.close()
            contractor_dd.options = [ft.dropdown.Option(text=c.name, key=str(c.id)) for c in c_list]
            if selected_id:
                contractor_dd.value = str(selected_id)
            if self.page: self.page.update()

        def quick_add_contractor(e):
             if is_locked_ksef: return
             dlg_quick.open = True
             self.page.update() 

        contractor_row = ft.Row([
            ro(contractor_dd), 
            ro(ft.TextButton(content=ft.Text("+", size=24, weight="bold"), tooltip="Dodaj nowego", on_click=quick_add_contractor, disabled=is_locked_ksef))
        ])
        
        date_issue_init = existing_invoice.date_issue.strftime("%Y-%m-%d") if edit_mode else datetime.now().strftime("%Y-%m-%d")
        date_sale_init = existing_invoice.date_sale.strftime("%Y-%m-%d") if edit_mode else datetime.now().strftime("%Y-%m-%d")
        
        date_issue_field = ft.TextField(label="Data wystawienia", value=date_issue_init, width=150, disabled=is_locked_ksef)
        date_sale_field = ft.TextField(label="Data sprzedaży/dostawy", value=date_sale_init, width=150, disabled=is_locked_ksef)
        
        # Calculate days diff for payment term if edit
        term_init = "14"
        if edit_mode and existing_invoice.date_issue and existing_invoice.payment_deadline:
             try:
                 delta = existing_invoice.payment_deadline - existing_invoice.date_issue
                 term_init = str(delta.days)
             except: pass
             
        payment_deadline_field = ft.TextField(label="Termin Płatności (dni)", value=term_init, width=100, disabled=is_locked_ksef)
        
        # New Contractor Dialog components
        name_field = ft.TextField(label="Nazwa / Imię i Nazwisko", width=400)
        nip_field = ft.TextField(label="NIP", width=200)
        address_field = ft.TextField(label="Adres (ulica i nr)", width=400)
        city_field = ft.TextField(label="Miasto", width=200)
        postal_field = ft.TextField(label="Kod pocztowy", width=100)
        phone_field = ft.TextField(label="Telefon", width=200)
        email_field = ft.TextField(label="Email", width=200)

        country_field = ft.TextField(label="Kraj", value="Polska", width=200)
        country_code_field = ft.TextField(label="Kod kraju (ISO)", value="PL", width=100)

        is_vat_field = ft.Checkbox(label="Czynny podatnik VAT", value=True)
        is_vat_ue_field = ft.Checkbox(label="Podatnik VAT UE", value=False)

        def verify_vat(e):
                 if not nip_field.value:
                      return
                 
                 if self.page:
                      self.page.snack_bar = ft.SnackBar(ft.Text("Weryfikacja w systemie MF..."), duration=1000)
                      self.page.snack_bar.open = True
                      self.page.update()

                 result = self.mf_client.check_nip(nip_field.value)
                 
                 msg = "Błąd weryfikacji"
                 is_error = True
                 
                 if result.get("success"):
                     status = result.get("status")
                     active = result.get("active")
                     request_id = result.get("request_id", "-")
                     msg = f"Weryfikacja MF zakończona.\nStatus: {status}\nID zapytania: {request_id}"
                     is_error = False
                     if active:
                         is_vat_field.value = True
                         if self.page: is_vat_field.update()
                 else:
                     msg = f"Błąd weryfikacji MF: {result.get('error')}"

                 if self.page:
                     dlg_result = ft.AlertDialog(
                        title=ft.Text("Wynik weryfikacji MF"),
                        content=ft.Text(msg, size=16, color=ft.Colors.RED if is_error else ft.Colors.GREEN_900),
                        actions=[ft.TextButton("OK", on_click=lambda e: setattr(dlg_result, 'open', False) or self.page.update())]
                     )
                     self.page.overlay.append(dlg_result)
                     dlg_result.open = True
                     self.page.update()

        def verify_vat_ue(e):
            country = country_code_field.value
            nip = nip_field.value
            
            if not country or not nip:
                if self.page:
                    self.page.snack_bar = ft.SnackBar(ft.Text("Wprowadź kod kraju i NIP"))
                    self.page.snack_bar.open = True
                    self.page.update()
                return

            if self.page:
                self.page.snack_bar = ft.SnackBar(ft.Text("Weryfikacja w systemie VIES..."), duration=1000)
                self.page.snack_bar.open = True
                self.page.update()

            result = self.vies_client.check_vat(country, nip)
            
            msg = "Błąd weryfikacji VIES"
            is_error = True
            
            if result.get("success"):
                valid = result.get("valid")
                status_str = "AKTYWNY" if valid else "NIEAKTYWNY/NIEWAŻNY"
                msg = f"Weryfikacja VIES zakończona.\nStatus: {status_str}"
                if result.get("name") and result.get("name") != "---":
                    msg += f"\nNazwa: {result.get('name')}"
                
                is_error = not valid
                if valid:
                    is_vat_ue_field.value = True
                    if self.page: is_vat_ue_field.update()
                    
                    if result.get("name") and not name_field.value:
                        name_field.value = result.get("name")
                        if self.page: name_field.update()
            else:
                msg = f"Błąd VIES: {result.get('error')}"

            if self.page:
                dlg_result = ft.AlertDialog(
                title=ft.Text("Wynik weryfikacji VIES"),
                content=ft.Text(msg, size=16, color=ft.Colors.RED if is_error else ft.Colors.GREEN_900),
                actions=[ft.TextButton("OK", on_click=lambda e: setattr(dlg_result, 'open', False) or self.page.update())]
                )
                self.page.overlay.append(dlg_result)
                dlg_result.open = True
                self.page.update()

        def search_gus_dialog(e):
            id_type = ft.RadioGroup(content=ft.Row([
                ft.Radio(value="NIP", label="NIP"),
                ft.Radio(value="REGON", label="REGON")
            ]), value="NIP")
            id_val_field = ft.TextField(label="Numer", width=200)

            def confirm_gus(e):
                if not id_val_field.value: return
                # Zakładamy NIP
                data = self.gus_client.get_contractor_by_nip(id_val_field.value)
                
                if data:
                    name_field.value = data.get("name", "")
                    nip_field.value = data.get("nip", "")
                    address_field.value = data.get("address", "")
                    city_field.value = data.get("city", "")
                    postal_field.value = data.get("postal_code", "")
                    if "email" in data: email_field.value = data["email"]
                    if "phone" in data: phone_field.value = data["phone"]
                    
                    dlg_gus.open = False
                    self.page.update()
                    dlg_quick.update()

                dlg_gus = ft.AlertDialog(
                    title=ft.Text("Pobierz z GUS"),
                    content=ft.Column([
                        id_type,
                        id_val_field
                    ], height=150),
                    actions=[
                        ft.TextButton("Anuluj", on_click=lambda e: setattr(dlg_gus, 'open', False) or self.page.update()),
                        ft.ElevatedButton("Szukaj", on_click=confirm_gus)
                    ]
                )
                self.page.overlay.append(dlg_gus)
                dlg_gus.open = True
                self.page.update()

        def save_quick_contractor(e):
            if not name_field.value: return
            db = next(get_db())
            
            # Check exist
            if nip_field.value and db.query(Contractor).filter(Contractor.nip == nip_field.value).first():
                if self.page:
                     self.page.snack_bar = ft.SnackBar(ft.Text("Taki NIP już istnieje!"))
                     self.page.snack_bar.open = True
                     self.page.update()
                db.close()
                return

            new_c = Contractor(
                name=name_field.value,
                nip=nip_field.value,
                address=address_field.value,
                city=city_field.value,
                postal_code=postal_field.value,
                phone=phone_field.value,
                email=email_field.value,
                country=country_field.value,
                country_code=country_code_field.value,
                is_vat_payer=is_vat_field.value,
                is_vat_ue=is_vat_ue_field.value
            )
            db.add(new_c)
            db.commit()
            new_id = new_c.id
            db.close()
            
            dlg_quick.open = False
            self.page.update()
            refresh_contractors(new_id)

        dlg_quick = ft.AlertDialog(
            title=ft.Text("Nowy kontrahent"),
            content=ft.Container(
                width=600, height=500,
                content=ft.Column([
                    ft.ElevatedButton("Pobierz z GUS", icon="search", on_click=search_gus_dialog),
                    name_field,
                    nip_field,
                    ft.Row([is_vat_field, ft.ElevatedButton("MF", on_click=verify_vat)]),
                    ft.Row([is_vat_ue_field, ft.ElevatedButton("VIES", on_click=verify_vat_ue)]),
                    address_field,
                    ft.Row([postal_field, city_field]),
                    ft.Row([country_field, country_code_field]),
                    ft.Divider(),
                    ft.Row([phone_field, email_field])
                ], scroll=ft.ScrollMode.AUTO)
            ),
            actions=[
                ft.TextButton("Anuluj", on_click=lambda e: setattr(dlg_quick, 'open', False) or self.page.update()),
                ft.ElevatedButton("Zapisz", on_click=save_quick_contractor)
            ]
        )
        self.page.overlay.append(dlg_quick)
        # dlg_quick.open = True -- DO NOT AUTO OPEN
        # self.page.update()

        # REMOVED DUPLICATE DEFINITIONS THAT BROKE INIT LOGIC
        # contractor_row = ...
        # date_issue_field = ...
        # date_sale_field = ...
        # Remove duplicate payment_deadline_field here (it was defined at line ~1414)
        
        # Payment Methods
        payment_methods_opts = [
            ft.dropdown.Option("Przelew"),
            ft.dropdown.Option("Gotówka"),
            ft.dropdown.Option("Karta"),
            ft.dropdown.Option("Kredyt kupiecki"),
            ft.dropdown.Option("Inne")
        ]
        
        default_pay_method = "Przelew"
        if self.category == InvoiceCategory.PURCHASE and not edit_invoice_id:
             default_pay_method = "Gotówka"
        if edit_mode and existing_invoice and existing_invoice.payment_method:
             # Ensure method is in list or add "Inne" logic
             if any(o.key == existing_invoice.payment_method for o in payment_methods_opts):
                  default_pay_method = existing_invoice.payment_method
             elif any(o.text == existing_invoice.payment_method for o in payment_methods_opts):
                  default_pay_method = existing_invoice.payment_method
             else:
                  # Maybe append or just set value (dropdown accepts custom value if valid? Flet Dropdown is strict)
                  # If custom value, maybe it falls into "Inne" or we add it?
                  # For safety let's assume it matches mapped options, otherwise set "Inne"
                  default_pay_method = existing_invoice.payment_method # Try direct assignment
                  
        payment_method_dd = ft.Dropdown(label="Metoda płatności", value=default_pay_method, options=payment_methods_opts, width=200)

        # Extra Flags
        flag_cash_method = ft.Checkbox(label="Metoda kasowa", value=(existing_invoice.is_cash_accounting if edit_mode else False))
        flag_reverse_charge = ft.Checkbox(label="Odwrotne obciążenie", value=(existing_invoice.is_reverse_charge if edit_mode else False))
        
        # Accounts
        initial_bank_account = ""
        initial_swift = ""
        initial_bank_name = ""

        # Load defaults based on category
        if self.category == InvoiceCategory.SALES:
             # For SALES, default to My Company Config
             initial_bank_account = config.bank_account if config and config.bank_account else ""
             initial_swift = config.swift_code if config and config.swift_code else ""
             initial_bank_name = config.bank_name if config and config.bank_name else ""
        
        # Override if Editing Existing Invoice
        if edit_mode and existing_invoice:
             # Always prefer what is in the invoice if set
             if existing_invoice.bank_accounts:
                 initial_bank_account = existing_invoice.bank_accounts
                 initial_swift = "" 
                 initial_bank_name = ""
             elif existing_invoice.bank_account_number: # Check legacy/alt column
                 initial_bank_account = existing_invoice.bank_account_number

             # If it's SALES and invoice has no account (unlikely), we might fall back to config? 
             # Better to show empty or what was saved. If saved is empty, show empty.
             if not initial_bank_account and self.category == InvoiceCategory.SALES:
                 initial_bank_account = config.bank_account if config else ""

        def format_bank_account(e):
            if not e.control.value:
                return

            raw = "".join(filter(str.isdigit, e.control.value))
            if len(raw) > 26: raw = raw[:26]
            formatted = ""
            # Polish format: 2 digit checksum + 6 groups of 4
            # XX XXXX XXXX XXXX XXXX XXXX XXXX
            if len(raw) > 0:
                formatted = raw[:2]
            if len(raw) > 2:
                for i in range(2, len(raw), 4):
                    formatted += " " + raw[i:i+4]
            e.control.value = formatted.strip()
            e.control.update()

        self.bank_accounts_field = ft.TextField(
             label="Numer konta bankowego", 
             value=initial_bank_account, 
             width=350,
             hint_text="XX XXXX XXXX XXXX XXXX XXXX XXXX",
             on_change=format_bank_account,
             keyboard_type=ft.KeyboardType.NUMBER
        )
        self.swift_field = ft.TextField(label="Kod SWIFT", value=initial_swift, width=120)
        self.bank_name_field = ft.TextField(label="Nazwa Banku", value=initial_bank_name, width=250)

        # Logic for visibility
        is_init_visible = default_pay_method in ["Przelew", "Kredyt kupiecki"]
        
        # Date calc helpers
        def calc_date_from_days(days_val):
            try:
                days = int(days_val)
                d_iss = datetime.strptime(date_issue_field.value, "%Y-%m-%d")
                return (d_iss + timedelta(days=days)).strftime("%Y-%m-%d")
            except:
                return datetime.now().strftime("%Y-%m-%d")

        term_days_init = "14"
        term_date_init = calc_date_from_days(term_days_init) # Default
        
        if edit_mode and existing_invoice:
             if existing_invoice.payment_deadline and existing_invoice.date_issue:
                 try:
                     # Calculate diff
                     delta = existing_invoice.payment_deadline - existing_invoice.date_issue
                     term_days_init = str(delta.days)
                     # Set explicit date from DB
                     term_date_init = existing_invoice.payment_deadline.strftime("%Y-%m-%d")
                 except: pass
             elif existing_invoice.payment_deadline:
                  term_date_init = existing_invoice.payment_deadline.strftime("%Y-%m-%d")
        
        payment_deadline_field = ft.TextField(label="Termin (dni)", value=term_days_init, width=80, visible=is_init_visible, disabled=is_locked_ksef)
        
        payment_deadline_date_field = ft.TextField(label="Data płatności", value=term_date_init, width=120, icon="calendar_today", visible=is_init_visible, disabled=is_locked_ksef)
        
        # Sync Logic
        def on_term_days_change(e):
             new_date = calc_date_from_days(payment_deadline_field.value)
             payment_deadline_date_field.value = new_date
             try:
                 if payment_deadline_date_field.page: payment_deadline_date_field.update()
             except: pass
        
        def on_term_date_change(e):
             try:
                 d_pay = datetime.strptime(payment_deadline_date_field.value, "%Y-%m-%d")
                 d_iss = datetime.strptime(date_issue_field.value, "%Y-%m-%d")
                 if d_pay < d_iss:
                      d_pay = d_iss
                      payment_deadline_date_field.value = d_pay.strftime("%Y-%m-%d")
                      try:
                          if payment_deadline_date_field.page: payment_deadline_date_field.update()
                      except: pass
                 
                 delta = d_pay - d_iss
                 payment_deadline_field.value = str(delta.days)
                 try:
                     if payment_deadline_field.page: payment_deadline_field.update()
                 except: pass
             except: pass

        payment_deadline_field.on_change = on_term_days_change
        payment_deadline_date_field.on_change = on_term_date_change

        # --- Payment Visibility Logic (Moved Up) ---
        # Define early to ensure binding works
        def update_payment_visibility(e=None):
             method = payment_method_dd.value
             print(f"[DEBUG] update_payment_visibility: value='{method}', event={e}")
             is_visible = method not in ["Gotówka", "Karta"]

             # Update Fields Visibility directly
             if payment_deadline_field: payment_deadline_field.visible = is_visible
             if payment_deadline_date_field: payment_deadline_date_field.visible = is_visible
             
             # Attempt to update row if it exists (might be defined later or captured via closure?)
             # Issue: 'payment_params_row' is not defined yet here.
             # Solution: access it via e.control.parent if possible? Or define empty holder?
             # Better: We only need to update the individual fields if they are on page?
             # Or we need to update the PARENT row to reflow?
             # We will defer row update to a lambda or use a mutable container reference.
             pass 

        # We will split logic:
        # 1. on_change handler that recalculates visibility flags on controls
        # 2. visual refresh that requires the layout to be ready
        
        # --- NEW KSEF FIELDS ---
        flag_split_payment = ft.Checkbox(label="MPP (Mechanizm Podzielonej Płatności)", value=existing_invoice.is_split_payment if edit_mode else False, disabled=is_locked_ksef)
        
        # Visibility of VAT options
        is_vat_payer_status = config.is_vat_payer if config else True
        flag_cash_method.visible = is_vat_payer_status
        flag_split_payment.visible = is_vat_payer_status
        
        vat_options_row = ft.Row([ro(flag_cash_method), ro(flag_split_payment)], visible=is_vat_payer_status)

        margin_chk = ft.Checkbox(label="Procedura Marży", value=False)
        margin_proc = ft.Dropdown(
             label="Procedura marży (dla faktur MARŻA)",
             options=[
                 ft.dropdown.Option("UZYWANE", "Towary używane"),
                 ft.dropdown.Option("DZIELA", "Dzieła sztuki"),
                 ft.dropdown.Option("ANTYKI", "Antyki"),
                 ft.dropdown.Option("TURYSTYKA", "Biura podróży")
             ],
             value=None,
             width=250,
             visible=False
        )
        
        def toggle_margin(e):
             margin_proc.visible = margin_chk.value
             if not margin_chk.value:
                  margin_proc.value = None
             if self.page: self.page.update()
        margin_chk.on_change = toggle_margin
        
        # Transaction Terms
        order_chk = ft.Checkbox(label="Zamówienie", value=False)
        order_num = ft.TextField(label="Numer zamówienia", width=200, visible=False)
        order_date = ft.TextField(label="Data (YYYY-MM-DD)", width=150, visible=False)
        
        contract_chk = ft.Checkbox(label="Umowa", value=False)
        contract_num = ft.TextField(label="Numer umowy", width=200, visible=False)
        contract_date = ft.TextField(label="Data (YYYY-MM-DD)", width=150, visible=False)

        def toggle_linked_docs(e):
             order_num.visible = order_chk.value
             order_date.visible = order_chk.value
             contract_num.visible = contract_chk.value
             contract_date.visible = contract_chk.value
             
             if not order_chk.value: order_num.value = ""; order_date.value = ""
             if not contract_chk.value: contract_num.value = ""; contract_date.value = ""
             
             if self.page: self.page.update()
             
        order_chk.on_change = toggle_linked_docs
        contract_chk.on_change = toggle_linked_docs

        # Payment Status
        is_paid_switch = ft.Switch(label="Opłacona", value=False)
        paid_amt_field = ft.TextField(label="Zapłacona kwota", value="0.00", disabled=True, width=150)
        paid_date_field = ft.TextField(label="Data wpłaty", value="", disabled=True, width=150)
        
        def toggle_paid(e):
             paid_amt_field.disabled = not is_paid_switch.value
             paid_date_field.disabled = not is_paid_switch.value
             if is_paid_switch.value:
                  paid_date_field.value = datetime.now().strftime("%Y-%m-%d")
                  # Calculate and fill total amount automatically
                  try:
                       total_gross = 0.0
                       is_ryco = False
                       # Check if tax_system_dd matches Ryczalt (via closure)
                       try:
                            if tax_system_dd.value == TaxSystem.RYCZALT.value:
                                 is_ryco = True
                       except: pass
                       
                       # items_list is via closure
                       for item in items_list:
                            qty = float(str(item.get('quantity', 0)).replace(',', '.') or 0)
                            net_p = float(str(item.get('net_price', 0)).replace(',', '.') or 0)
                            vat = float(str(item.get('vat_rate', 0)).replace(',', '.') or 0)
                            if is_ryco:
                                 # For Lump Sum, vat field holds rate
                                 val_lump = item.get('lump_sum_rate', 0)
                                 vat = float(str(val_lump).replace(',', '.') or 0)

                            gross_val = (qty * net_p) * (1 + vat)
                            total_gross += gross_val
                       
                       paid_amt_field.value = f"{total_gross:.2f}"
                  except Exception as ex:
                       print(f"Auto-fill paid amount error: {ex}")
                       pass

             paid_amt_field.update()
             paid_date_field.update()
        is_paid_switch.on_change = toggle_paid
        # --- END NEW KSEF FIELDS ---
        
        # Sekcja walut
        currency_dd = ft.Dropdown(
            label="Waluta",
            value="PLN",
            options=[ft.dropdown.Option("PLN"), ft.dropdown.Option("EUR"), ft.dropdown.Option("USD"), ft.dropdown.Option("GBP")],
            width=100
        )
        currency_rate = ft.TextField(label="Kurs", value="1.0000", width=100)
        currency_date_field = ft.TextField(label="Data kursu", value=datetime.now().strftime("%Y-%m-%d"), width=120)

        def update_currency_rate(e):
            curr = currency_dd.value
            date_str = currency_date_field.value
            is_pln = (curr == "PLN")
            
            currency_rate.visible = not is_pln
            currency_date_field.visible = not is_pln

            if not is_pln:
                try:
                    # Pobieramy kurs z dnia poprzedniego (częsta praktyka księgowa, ale tu uproszczenie do podanej daty)
                    rate = self.nbp_client.get_exchange_rate(curr, date_str)
                    if rate:
                        currency_rate.value = str(rate)
                    else:
                        if self.page:
                             self.page.snack_bar = ft.SnackBar(ft.Text(f"Nie znaleziono kursu {curr} dla {date_str}"))
                             self.page.snack_bar.open = True
                except Exception as ex:
                    print(f"Błąd NBP: {ex}")
            
            if self.page: self.page.update()

        currency_dd.on_change = update_currency_rate
        currency_date_field.on_change = update_currency_rate
        
        # Initialize visibility
        currency_rate.visible = (currency_dd.value != "PLN")
        currency_date_field.visible = (currency_dd.value != "PLN")
        
        # Generator numeru (prosty)
        invoice_seq_number = ft.TextField(label="Numer", value="", width=150, 
                                          tooltip="Numer porządkowy. Pozostała część numeru (rok itp.) jest generowana automatycznie.")
        
        # Debounce/Update logic
        def update_number_params(e=None):
             # Logic triggered by DATE or TYPE change
             if self.category == InvoiceCategory.PURCHASE:
                 # Purchase invoices are manually numbered
                 # Edit mode: Use existing
                 if edit_mode and existing_invoice:
                     invoice_seq_number.value = existing_invoice.number if existing_invoice.number else ""
                     try:
                        if invoice_seq_number.page: invoice_seq_number.update()
                     except: pass
                 return

             # If editing, DO NOT auto-update number unless type/date changes drastically? 
             # Actually, if we open edit, we show existing number. User can change it.
             # Auto-numbering logic might overwrite it if triggered.
             # We should skip logic if not e (initial call) and edit_mode is true.
             if edit_mode and not e:
                 invoice_seq_number.value = existing_invoice.number if existing_invoice.number else ""
                 return

             db = next(get_db())
             try:
                 date_issue_val = datetime.strptime(date_issue_field.value, "%Y-%m-%d")
                 inv_cat = self.category
                 inv_typ = InvoiceType(invoice_type.value)
                 
                 service = NumberingService(db)
                 setting = service.get_or_create_config(inv_cat, inv_typ)
                 
                 # 1. Update Value with Full String
                 prefix, suffix = service.get_number_parts(setting, date_issue_val)
                 
                 # Store parts for later parsing
                 invoice_seq_number.data = {"prefix": prefix, "suffix": suffix}
                 
                 # 2. Calculate sequence
                 try:
                    seq = service.find_potential_number(setting, date_issue_val)
                    current_seq = str(seq)
                 except: 
                     current_seq = "1"
                     
                 invoice_seq_number.value = f"{prefix}{current_seq}{suffix}"
                 # Ensure visual prefix/suffix are empty to avoid duplication
                 invoice_seq_number.prefix_text = ""
                 invoice_seq_number.suffix_text = ""
                     
                 try:
                    if invoice_seq_number.page: invoice_seq_number.update()
                 except: pass
             except Exception as ex:
                 print(f"Preview params error: {ex}")
             finally:
                 db.close()

        def on_date_issue_change(e):
             update_number_params(e)
             # Update payment date
             on_term_days_change(None)

        # invoice_seq_number.on_change = update_number_preview # Removed to allow free editing
        date_issue_field.on_change = on_date_issue_change
        invoice_type.on_change = update_number_params
        
        # Initial call
        update_number_params()
        
        items_list = [] 

        def create_empty_item():
             # Basic default item structure
             return {
                "product_id": None,
                "product_name": "",
                "quantity": 1.0,
                "unit": "szt",
                "net_price": 0.0,
                "vat_rate": 0.23,
                "pkwiu": "-",
                "lump_sum_rate": 0.12,
                "net_value": 0.0,
                "gross_value": 0.0,
                "is_exempt_zw": False
            }

        # Helper function for bank account loading
        if edit_mode and existing_invoice:
             if existing_invoice.bank_accounts:
                  self.bank_accounts_field.value = existing_invoice.bank_accounts
             
             if existing_invoice.contractor:
                  # Ensure contractor details are loaded on UI if distinct from DD value or if DD not enough
                  # Contractor detailed info container usually refreshes via refresh_contractor_info
                  pass

        # Load existing items if editing
        if edit_mode and existing_invoice:
            for item in existing_invoice.items:
                # Determine vat or lump sum
                is_r = (existing_invoice.tax_system == TaxSystem.RYCZALT)
                
                # Check for transient ZW flag (from KsefLogic or runtime patch) or infer from Rate 0.0 + PKWiU 'ZW'
                is_zw_flag = getattr(item, 'is_exempt_zw', False)
                if not is_zw_flag and item.vat_rate == 0.0 and item.pkwiu == "ZW": # Fallback inference
                    is_zw_flag = True

                # Careful with optional fields from DB being None
                lump_s = float(item.lump_sum_rate) if item.lump_sum_rate is not None else 0.12
                # If parsed from KSeF, we stored net_value and gross_value in DB item. Use them.
                # If calculated on fly, use formula. KSeF items are explicit.
                
                net_v = float(item.net_value) if hasattr(item, 'net_value') and item.net_value is not None else float(item.net_price * item.quantity)
                # Note: valid only if we added net_value to InvoiceItem model! 
                # Wait, I did verify InvoiceItem model has NOT net_value column effectively? 
                # Let's check models.py again. 
                # models.py shows: unit, net_price, vat_rate, gross_value. No net_value column. 
                # So we must compute it.
                net_v = float(item.net_price) * float(item.quantity)

                items_list.append({
                    "product_id": None, # Could link back if needed, but not critical for display
                    "product_name": item.product_name,
                    "quantity": float(item.quantity),
                    "unit": item.unit,
                    "net_price": float(item.net_price),
                    "vat_rate": float(item.vat_rate),
                    "pkwiu": item.pkwiu,
                    "lump_sum_rate": lump_s,
                    "net_value": net_v,
                    "gross_value": float(item.gross_value), 
                    "is_exempt_zw": is_zw_flag 
                })
        
        # Always start with one empty row if list ends with filled item or is empty
        # BUT NOT IN READONLY MODE or EDIT MODE if user doesn't want it explicitly
        should_add_empty = True
        if readonly:
            should_add_empty = False
        elif edit_mode and items_list:
            should_add_empty = False # Don't auto-add in edit mode if we have items
            
        if should_add_empty:
             if not items_list or items_list[-1]['product_name']:
                 items_list.append(create_empty_item())
                
        # DataGrid Logic
        items_view = ft.Column(scroll=ft.ScrollMode.ADAPTIVE) # Wrapper for table

        def open_item_options_menu(item):
            def handle_select_product(e):
                 dlg_options.open = False
                 self.page.update()
                 open_product_selector_dialog(item)

            def handle_add_new_product(e):
                 dlg_options.open = False
                 self.page.update()
                 quick_add_product(e) # Calls the global quick add logic

            def handle_delete_row(e):
                 dlg_options.open = False
                 if len(items_list) > 0:
                     remove_item(item)
                 self.page.update()

            dlg_options = ft.AlertDialog(
                title=ft.Text("Opcje pozycji"),
                content=ft.Column([
                    ft.ListTile(leading=ft.Text("🔍"), title=ft.Text("Wybierz towar z bazy"), on_click=handle_select_product),
                    ft.ListTile(leading=ft.Text("➕"), title=ft.Text("Dodaj nowy towar"), on_click=handle_add_new_product),
                    ft.ListTile(leading=ft.Text("🗑️", color="red"), title=ft.Text("Usuń wiersz"), on_click=handle_delete_row),
                ], height=180, width=300)
            )
            self.page.overlay.append(dlg_options)
            dlg_options.open = True
            self.page.update()

        def refresh_items_view():
            # Auto-add removed - user must explicitly add rows using button
            if not items_list:
                  items_list.append(create_empty_item())

            items_view.controls.clear()
            
            # Recalculate Totals (Initial Pass)
            # Logic moved to refresh_totals_only mostly, but ensures data coherence here
            total_net = 0.0
            total_sum_net_by_rate = {} # rate -> net_sum
            
            for item in items_list:
                qty = float(str(item['quantity']).replace(',', '.') or 0)
                net_p = float(str(item.get('net_price', 0)).replace(',', '.') or 0)
                vat = float(str(item.get('vat_rate', 0)).replace(',', '.') or 0)
                
                item['net_value'] = qty * net_p
                item['gross_value'] = item['net_value'] * (1 + vat)
                item['quantity'] = qty
                item['net_price'] = net_p

            is_ryczalt = (tax_system_dd.value == TaxSystem.RYCZALT.value)

            # Define refresh_totals_only inside scope to capture 'is_ryczalt'
            def refresh_totals_only():
                 # Group by VAT rate
                 net_by_rate = {}
                 
                 for i in items_list:
                     if not i['product_name'].strip(): continue # Skip empty rows in logic
                     
                     # Determine valid rate key
                     r = i.get('vat_rate', 0.0) if not is_ryczalt else i.get('lump_sum_rate', 0.0)
                     r = float(r)
                     
                     current_sum = net_by_rate.get(r, 0.0)
                     current_sum += i['net_value']
                     net_by_rate[r] = current_sum
                
                 final_gross = 0.0
                 final_net = 0.0
                 
                 # Formula: Sum(Net) + VAT
                 for rate, net_sum in net_by_rate.items():
                     vat_amt = net_sum * rate
                     gross = net_sum + vat_amt
                     final_gross += gross
                     final_net += net_sum
                 
                 # Need a persistent handle for summary text
                 if not hasattr(self, 'lbl_summary_total'):
                     self.lbl_summary_total = ft.Text("", size=16, weight="bold")
                 
                 self.lbl_summary_total.value = f"Razem Netto: {final_net:.2f} | Razem Brutto: {final_gross:.2f} {currency_dd.value}"
                 
                 if is_paid_switch.value:
                      paid_amt_field.value = f"{final_gross:.2f}"
                      try:
                          if paid_amt_field.page: paid_amt_field.update()
                      except: pass
                      
                 try:
                     if self.lbl_summary_total.page: self.lbl_summary_total.update()
                 except: pass

            # Columns Configuration (Headers) - Manual Row Implementation
            header_row = ft.Row(
                controls=[
                    ft.Text("Lp.", width=30, weight="bold"),
                    ft.Container(content=ft.Text("Nazwa Produktu / Opis", weight="bold"), expand=True),
                    ft.Container(content=ft.Text("Ilość", weight="bold", text_align=ft.TextAlign.RIGHT), width=60, alignment=ft.alignment.center_right if hasattr(ft.alignment, "center_right") else ft.Alignment(1.0, 0.0)),
                    ft.Text("Jm", width=40, weight="bold"),
                    ft.Container(content=ft.Text("Cena Netto" if not is_ryczalt else "Kwota", weight="bold", text_align=ft.TextAlign.RIGHT), width=80, alignment=ft.alignment.center_right if hasattr(ft.alignment, "center_right") else ft.Alignment(1.0, 0.0)),
                    ft.Container(content=ft.Text("Wartość Netto", weight="bold", text_align=ft.TextAlign.RIGHT), width=90, alignment=ft.alignment.center_right if hasattr(ft.alignment, "center_right") else ft.Alignment(1.0, 0.0)),
                    ft.Text("VAT %" if not is_ryczalt else "Ryczałt %", width=100, weight="bold"),
                    ft.Container(content=ft.Text("Wartość Brutto", weight="bold", text_align=ft.TextAlign.RIGHT), width=90, alignment=ft.alignment.center_right if hasattr(ft.alignment, "center_right") else ft.Alignment(1.0, 0.0)),
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10
            )
            # Standardize header similar to DataTable (no grey box, just headers and divider)
            items_view.controls.append(ft.Container(content=header_row, padding=ft.padding.only(bottom=5)))
            items_view.controls.append(ft.Divider(height=1, color="grey"))

            # rows list not used anymore for DataTable
            
            # Store references to update cells without full rebuild
            row_controls = {} # id(item) -> { 'net_val': Control, 'gross_val': Control, 'vat': Control }

            def make_change_handler(item, field, is_float=False):
                def handler(e):
                    val = e.control.value
                    if is_float:
                         try:
                            val = float(val.replace(',', '.'))
                         except: val = 0.0 if is_float else val
                    
                    item[field] = val
                    
                    if field in ['quantity', 'net_price', 'vat_rate']:
                         # Recalculate Row
                         q = float(str(item['quantity']).replace(',', '.') or 0)
                         np = float(str(item['net_price']).replace(',', '.') or 0)
                         vt = float(str(item['vat_rate']).replace(',', '.') or 0)
                         
                         nv = q * np
                         item['net_value'] = nv
                         gv = nv * (1 + vt)
                         item['gross_value'] = gv
                         
                         # Update UI Cells direct
                         ctrls = row_controls.get(id(item))
                         if ctrls:
                             if 'net_val' in ctrls: 
                                 ctrls['net_val'].value = f"{nv:.2f}"
                                 ctrls['net_val'].update()
                             if 'gross_val' in ctrls:
                                 ctrls['gross_val'].value = f"{gv:.2f}"
                                 ctrls['gross_val'].update()
                    
                    refresh_totals_only()

                return handler
            
            def make_vat_change_handler(item):
                def handler(e):
                    # Debug print
                    print(f"VAT Change Triggered: {e.control.value}")
                    try:
                        val_str = e.control.value
                        if val_str == "ZW":
                             new_rate = 0.0
                             item['is_exempt_zw'] = True
                        else:
                             new_rate = float(val_str)
                             item['is_exempt_zw'] = False 
                        item['vat_rate'] = new_rate
                    except Exception as ex:
                        print(f"VAT Parse Error: {ex}")
                        return

                    # Recalculate Row
                    q = float(str(item['quantity']).replace(',', '.') or 0)
                    np = float(str(item.get('net_price', 0)).replace(',', '.') or 0)
                    vt = float(str(item.get('vat_rate', 0)).replace(',', '.') or 0)
                    
                    nv = q * np
                    item['net_value'] = nv
                    gv = nv * (1 + vt)
                    item['gross_value'] = gv
                    
                    # Update UI Cells direct
                    ctrls = row_controls.get(id(item))
                    if ctrls:
                        if 'net_val' in ctrls: 
                            ctrls['net_val'].value = f"{nv:.2f}"
                            ctrls['net_val'].update()
                        if 'gross_val' in ctrls:
                            ctrls['gross_val'].value = f"{gv:.2f}"
                            ctrls['gross_val'].update()
                    
                    # Trigger global total refresh
                    refresh_totals_only()

                return handler

            def on_submit_handler(e, item=None):
                    refresh_items_view()

            # Vat Options
            vat_opts = [
                ft.dropdown.Option(key="0.23", text="23%"),
                ft.dropdown.Option(key="0.08", text="8%"),
                ft.dropdown.Option(key="0.05", text="5%"),
                ft.dropdown.Option(key="0.00", text="0%"),
                ft.dropdown.Option(key="ZW", text="ZW")
            ]

            for idx, item in enumerate(items_list):
                # Cells -> Native Controls for direct Row
                
                # Name (Editable + Popup Menu)
                def on_menu_item_click(e, item_ref=item, action=None):
                    # Disable menu actions if readonly
                    if readonly: return
                    
                    if action == "select":
                        open_product_selector_dialog(item_ref)
                    
                    elif action == "add_and_insert":
                        def on_added(new_p):
                            item_ref['product_id'] = new_p.id
                            item_ref['product_name'] = new_p.name
                            item_ref['net_price'] = float(new_p.net_price)
                            item_ref['unit'] = new_p.unit
                            
                            p_vat = getattr(new_p, 'vat_rate', 0.23)
                            item_ref['vat_rate'] = float(p_vat) if p_vat is not None else 0.23

                            q = float(str(item_ref['quantity']).replace(',', '.') or 0)
                            item_ref['net_value'] = q * item_ref['net_price']
                            item_ref['gross_value'] = item_ref['net_value'] * (1 + item_ref['vat_rate'])
                            
                            add_empty_row(None)
                            refresh_items_view()
                            
                        quick_add_product(e, on_success=on_added)
                        
                    elif action == "delete":
                        remove_item(item_ref)
                        
                    elif action == "cut":
                        self.row_clipboard = item_ref.copy()
                        remove_item(item_ref)
                        
                    elif action == "copy":
                        self.row_clipboard = item_ref.copy()
                        
                    elif action == "paste":
                        if self.row_clipboard:
                            c = self.row_clipboard
                            diff_keys = ['product_id', 'product_name', 'net_price', 'unit', 'vat_rate', 'quantity', 'net_value', 'gross_value'] 
                            for k in diff_keys:
                                if k in c: item_ref[k] = c[k]
                            refresh_items_view()
                    
                    self.page.update()

                # Robust Menu
                pts = ft.PopupMenuButton(
                    icon="more_vert",
                    tooltip="Opcje",
                    items=[
                        ft.PopupMenuItem(
                            icon="list_alt",
                            content=ft.Text("Wstaw towar"),
                            on_click=lambda e: on_menu_item_click(e, item, "select")
                        ),
                        ft.PopupMenuItem(
                            icon="add_box",
                            content=ft.Text("Dodaj i wstaw"),
                            on_click=lambda e: on_menu_item_click(e, item, "add_and_insert")
                        ),
                        ft.PopupMenuItem(
                            icon="content_cut",
                            content=ft.Text("Wytnij"),
                            on_click=lambda e: on_menu_item_click(e, item, "cut")
                        ),
                        ft.PopupMenuItem(
                            icon="content_copy",
                            content=ft.Text("Kopiuj"),
                            on_click=lambda e: on_menu_item_click(e, item, "copy")
                        ),
                        ft.PopupMenuItem(
                            icon="content_paste",
                            content=ft.Text("Wklej"),
                            on_click=lambda e: on_menu_item_click(e, item, "paste")
                        ),
                        ft.PopupMenuItem(
                            icon="delete",
                            content=ft.Text("Usuń pozycje", color="red"),
                            on_click=lambda e: on_menu_item_click(e, item, "delete")
                        ),
                    ]
                )
                
                if readonly:
                    pts.disabled = True
                    pts.opacity = 0 # Hide completely or disable? Better disable or hide.
                    pts.visible = False

                name_field = ro(ft.TextField(
                    value=item['product_name'], 
                    border=ft.InputBorder.UNDERLINE,
                    on_change=make_change_handler(item, 'product_name'),
                    on_submit=lambda e, i=item: on_submit_handler(e, i),
                    # suffix=pts, # Moved out to avoid layout issues
                    text_size=14,
                    height=45,
                    content_padding=8,
                    expand=True
                ))
                     
                name_cell = ft.Row([name_field, pts], spacing=0, expand=True) if not readonly else ft.Row([name_field], spacing=0, expand=True)
                
                qty_field = ro(ft.TextField(
                    value=str(item['quantity']), 
                    width=60, 
                    text_align=ft.TextAlign.RIGHT,
                    border=ft.InputBorder.UNDERLINE,
                    on_change=make_change_handler(item, 'quantity', True),
                    on_submit=on_submit_handler,
                    text_size=14,
                    height=40,
                    content_padding=8
                ))

                unit_field = ro(ft.TextField(
                    value=str(item['unit']), 
                    width=40, 
                    border=ft.InputBorder.UNDERLINE,
                    on_change=make_change_handler(item, 'unit'),
                    on_submit=on_submit_handler,
                    text_size=14,
                    height=40,
                    content_padding=8
                ))
                
                price_field = ro(ft.TextField(
                    value=f"{item['net_price']:.2f}", 
                    width=80, 
                    text_align=ft.TextAlign.RIGHT,
                    border=ft.InputBorder.UNDERLINE,
                    on_change=make_change_handler(item, 'net_price', True),
                    on_submit=on_submit_handler,
                    text_size=14,
                    height=40,
                    content_padding=8
                ))
                
                net_val_cell = ft.Text(f"{item['net_value']:.2f}", width=90, text_align=ft.TextAlign.RIGHT, size=14)

                # Tax Cell - Dropdown
                if is_ryczalt:
                     rates = ["0.17", "0.15", "0.14", "0.125", "0.12", "0.10", "0.085", "0.055", "0.03"]
                     tax_opts_r = [ft.dropdown.Option(key=r, text=f"{float(r)*100:.1f}%") for r in rates]
                     
                     # Explicit handler binding - post-init because init on_change caused TypeError in some versions
                     tax_cell = ro(ft.Dropdown(
                         options=tax_opts_r,
                         value=str(item.get('lump_sum_rate', 0.12)),
                         width=100,
                         text_size=13,
                         border=ft.InputBorder.UNDERLINE, 
                         height=45,
                         content_padding=5
                     ))
                     
                     def ryczalt_handler(e):
                         try:
                             item['lump_sum_rate'] = float(e.control.value)
                             refresh_totals_only()
                             if self.page: self.page.update()
                         except: pass

                     tax_cell.on_change = ryczalt_handler
                     # Apply identical fix pattern
                     tax_cell.on_select = ryczalt_handler
                else:
                    curr_v = f"{item.get('vat_rate', 0.23):.2f}"
                    is_zw = item.get('is_exempt_zw', False)
                    # Use "ZW" key if exempt flag is True, OR if rate is 0.0 but we suspect ZW usage
                    if is_zw:
                        curr_v = "ZW"
                    
                    # Ensure handler is bound POST CREATION to avoid TypeError in older flet
                    tax_cell = ro(ft.Dropdown(
                        options=vat_opts,
                        value=curr_v,
                        width=100,
                        text_size=14,
                        content_padding=8,
                        border=ft.InputBorder.UNDERLINE,
                        height=45
                    ))
                    
                    vat_handler = make_vat_change_handler(item)
                    tax_cell.on_change = vat_handler
                    # Apply identical fix pattern from payment_method_dd
                    tax_cell.on_select = vat_handler
                
                gross_val_cell = ft.Text(f"{item['gross_value']:.2f}", width=90, text_align=ft.TextAlign.RIGHT, size=14)

                # Register refs
                row_controls[id(item)] = {
                    'net_val': net_val_cell,
                    'gross_val': gross_val_cell
                }

                item_row = ft.Row(
                    controls=[
                        ft.Text(str(idx + 1), width=30, size=14),
                        name_cell,
                        qty_field,
                        unit_field,
                        price_field,
                        net_val_cell,
                        tax_cell,
                        gross_val_cell
                    ],
                    alignment=ft.MainAxisAlignment.START,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=10
                )
                items_view.controls.append(item_row)
                items_view.controls.append(ft.Divider(height=1, thickness=0.5, color="grey")) # Row separator            
            # End Loop - removed table construction

            # Add Row Button (Only if not readonly)
            if not readonly:
                 items_view.controls.append(
                    ft.Container(
                        content=ft.ElevatedButton("Dodaj pozycję", icon="add", on_click=lambda e: (add_empty_row(None), refresh_items_view())),
                        padding=10,
                        alignment=ft.Alignment(-1.0, 0.0)
                    )
                 )
            
            # Summary Logic
            refresh_totals_only()
            
            if hasattr(self, 'page') and self.page:
                 self.page.update()

        def remove_item(item):
            if item in items_list:
                items_list.remove(item)
                refresh_items_view()

        def open_product_selector_dialog(target_item):
            # Load products
            db = next(get_db())
            all_prods = db.query(Product).all()
            db.close()
            
            def insert_product(p):
                dlg_selector.open = False
                self.page.update()

                target_item['product_id'] = p.id
                target_item['product_name'] = p.name
                target_item['net_price'] = float(p.net_price)
                target_item['unit'] = p.unit
                # Default VAT if not in product (assuming 23% for now)
                # Check if p has vat_rate attribute
                p_vat = getattr(p, 'vat_rate', 0.23)
                target_item['vat_rate'] = float(p_vat) if p_vat is not None else 0.23
                
                # Recalc
                q = float(str(target_item['quantity']).replace(',', '.') or 0)
                target_item['net_value'] = q * target_item['net_price']
                target_item['gross_value'] = target_item['net_value'] * (1 + target_item.get('vat_rate', 0.23))

                refresh_items_view()

            # Using ListView instead of DataTable for reliable click events
            prod_list = ft.ListView(expand=True, spacing=0, item_extent=50)

            def build_rows(filter_text=""):
                controls = []
                ftxt = filter_text.lower()
                count = 0
                for p in all_prods:
                    if ftxt and (ftxt not in p.name.lower() and ftxt not in str(p.sku or "").lower()):
                        continue
                    
                    p_vat = getattr(p, 'vat_rate', 0.23)
                    vat = float(p_vat) if p_vat is not None else 0.23
                    gross_approx = float(p.net_price) * (1 + vat)
                    
                    # Row Layout
                    row_content = ft.Row(
                        controls=[
                            ft.Container(content=ft.Text(p.name, size=14, weight=ft.FontWeight.W_500), width=350),
                            ft.Text(p.sku or "", size=14, width=100),
                            ft.Text(f"{float(p.net_price):.2f}", size=14, width=100, text_align=ft.TextAlign.RIGHT),
                            ft.Text(f"{int(vat*100)}%", size=14, width=80, text_align=ft.TextAlign.RIGHT),
                            ft.Text(f"{gross_approx:.2f}", size=14, weight=ft.FontWeight.BOLD, width=100, text_align=ft.TextAlign.RIGHT),
                        ],
                        alignment=ft.MainAxisAlignment.START,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=20
                    )

                    # Clickable Container
                    # p=p capture in lambda is crucial
                    row_container = ft.Container(
                        content=row_content,
                        padding=ft.padding.symmetric(horizontal=10),
                        bgcolor=ft.Colors.WHITE,
                        ink=True,
                        on_click=lambda e, prod=p: insert_product(prod),
                        border=ft.border.only(bottom=ft.border.BorderSide(1, ft.Colors.BLUE_GREY_50)), # Light separator
                        height=50
                    )
                    controls.append(row_container)
                    count += 1
                    if count >= 100: break
                return controls

            prod_list.controls = build_rows()

            def filter_change(e):
                prod_list.controls = build_rows(e.control.value)
                prod_list.update()

            search_box = ft.TextField(
                label="Szukaj (wpisz nazwę lub kod)", 
                autofocus=True, 
                on_change=filter_change,
                prefix_icon="search",
                content_padding=10,
                text_size=14,
                border_color=ft.Colors.BLUE_GREY_400
            )

            # Header
            header = ft.Container(
                content=ft.Row([
                    ft.Text("Nazwa", width=350, weight="bold", size=14, color=ft.Colors.BLUE_GREY_900),
                    ft.Text("Kod", width=100, weight="bold", size=14, color=ft.Colors.BLUE_GREY_900),
                    ft.Text("Netto", width=100, weight="bold", text_align=ft.TextAlign.RIGHT, size=14, color=ft.Colors.BLUE_GREY_900),
                    ft.Text("VAT", width=80, weight="bold", text_align=ft.TextAlign.RIGHT, size=14, color=ft.Colors.BLUE_GREY_900),
                    ft.Text("Brutto", width=100, weight="bold", text_align=ft.TextAlign.RIGHT, size=14, color=ft.Colors.BLUE_GREY_900),
                ], spacing=20),
                padding=ft.padding.symmetric(horizontal=10, vertical=12),
                bgcolor=ft.Colors.BLUE_GREY_50,
                border=ft.border.all(1, ft.Colors.BLUE_GREY_200)
            )

            content = ft.Column(
                [
                    search_box,
                    header,
                    ft.Container(
                        content=prod_list,
                        height=400,
                        border=ft.border.all(1, ft.Colors.BLUE_GREY_200),
                    ),
                ],
                tight=True
            )

            dlg_selector = ft.AlertDialog(
                title=ft.Text("Wybierz towar"),
                content=ft.Container(content=content, width=900),
                actions=[
                    ft.TextButton("Anuluj", on_click=lambda e: setattr(dlg_selector, 'open', False) or self.page.update())
                ]
            )
            self.page.overlay.append(dlg_selector)
            dlg_selector.open = True
            self.page.update()

        # Placeholders for ref variables to avoid modifying whole structure
        self.lbl_summary_total = ft.Text("Razem: 0.00", size=16, weight="bold")

        def add_empty_row(e):
            is_ryczalt = (tax_system_dd.value == TaxSystem.RYCZALT.value)
            default_vat = 0.0 if (not is_vat_payer_status) else 0.23
            
            items_list.append({
                "product_id": None,
                "product_name": "",
                "quantity": 1.0,
                "unit": "szt",
                "net_price": 0.0,
                "vat_rate": default_vat,
                "pkwiu": "-",
                "lump_sum_rate": 0.12, # Default flat rate
                "net_value": 0.0,
                "gross_value": 0.0,
                "is_exempt_zw": False
            })
            refresh_items_view()

        # Replaces old items_view with structure
        # We need to render the column with table AND the summary/add button
        
        # Override items_view controls append logic by pre-populating
        items_view.controls = [] # ensure empty start
        
        # We need to wrap items_view in a container that includes the Summary and Add Line button
        # But `items_view` variable is used in main layout.
        # Let's keep `items_view` as the Column holding the table, and we append to it.

        # ... (rest of function logic preserved by context, we only replaced refresh_items_view and add_item logics) ...


        def refresh_products(selected_id=None):
            db = next(get_db())
            p_list = db.query(Product).all()
            db.close()
            nonlocal products, active_prod_dd, active_on_prod_change
            products = p_list
            
            if active_prod_dd:
                active_prod_dd.options = [ft.dropdown.Option(text=f"{p.name} ({p.net_price} zł)", key=str(p.id)) for p in products]
                if selected_id:
                    active_prod_dd.value = str(selected_id)
                    if active_on_prod_change:
                        active_on_prod_change(None)

            if self.page: self.page.update()

        def quick_add_product(e, on_success=None):
            # Pobranie stawek VAT
            db = next(get_db())
            rates_db = db.query(VatRate).all()
            db.close()
            
            vat_options = [ft.dropdown.Option(text=r.name, key=str(r.rate)) for r in rates_db]
            if not vat_options:
                vat_options = [
                    ft.dropdown.Option(text="23%", key="0.23"),
                    ft.dropdown.Option(text="8%", key="0.08"), 
                    ft.dropdown.Option(text="5%", key="0.05"), 
                    ft.dropdown.Option(text="0%", key="0.0")
                ]

            name_p_field = ft.TextField(label="Nazwa produktu", col={"md": 12})
            sku_p_field = ft.TextField(label="SKU (Kod)", col={"md": 6})
            unit_p_field = ft.TextField(label="Jednostka", value="szt.", col={"md": 6})
            
            purchase_net_field = ft.TextField(label="Cena zakupu (netto)", value="0.00", keyboard_type=ft.KeyboardType.NUMBER, col={"md": 6})
            vat_field = ft.Dropdown(label="Stawka VAT", value="0.23", options=vat_options, col={"md": 6})
            
            sales_net_field = ft.TextField(label="Cena sprzedaży (netto)", value="0.00", keyboard_type=ft.KeyboardType.NUMBER, col={"md": 6})
            sales_gross_field = ft.TextField(label="Cena sprzedaży (brutto)", value="0.00", keyboard_type=ft.KeyboardType.NUMBER, col={"md": 6})
            
            price_mode = ft.RadioGroup(content=ft.Row([
                ft.Radio(value="NET", label="Od Netto"),
                ft.Radio(value="GROSS", label="Od Brutto")
            ]), value="NET")

            def recalculate(source_field=None):
                try:
                    vat_rate = float(vat_field.value)
                except (ValueError, TypeError):
                    vat_rate = 0.0

                try:
                    net = float(sales_net_field.value.replace(",", ".") or 0)
                except ValueError:
                    net = 0.0
                    
                try:
                    gross = float(sales_gross_field.value.replace(",", ".") or 0)
                except ValueError:
                    gross = 0.0

                mode = price_mode.value
                
                # Jeśli wprowadzono cenę zakupu, a sprzedaż jest 0, skopiuj
                try:
                    p_net = float(purchase_net_field.value.replace(",", ".") or 0)
                    if source_field == "purchase" and net == 0 and gross == 0:
                        net = p_net
                        sales_net_field.value = f"{net:.2f}"
                except: pass

                if mode == "NET" and source_field != "gross":
                    gross = net * (1 + vat_rate)
                    sales_gross_field.value = f"{gross:.2f}"
                elif mode == "GROSS" and source_field != "net":
                    net = gross / (1 + vat_rate)
                    sales_net_field.value = f"{net:.2f}"
                
                if source_field == "vat":
                    if mode == "NET":
                        gross = net * (1 + vat_rate)
                        sales_gross_field.value = f"{gross:.2f}"
                    else:
                        net = gross / (1 + vat_rate)
                        sales_net_field.value = f"{net:.2f}"

                if dlg_quick_p.open: self.page.update()

            sales_net_field.on_change = lambda e: recalculate("net")
            sales_gross_field.on_change = lambda e: recalculate("gross")
            vat_field.on_change = lambda e: recalculate("vat")
            purchase_net_field.on_change = lambda e: recalculate("purchase")
            
            def on_mode_change(e):
                if price_mode.value == "NET":
                    sales_net_field.read_only = False
                    sales_gross_field.read_only = True
                else:
                    sales_net_field.read_only = True
                    sales_gross_field.read_only = False
                recalculate("vat")
                self.page.update()

            price_mode.on_change = on_mode_change
            sales_gross_field.read_only = True

            def save_quick_product(e):
                if not name_p_field.value: return
                try:
                    s_net = float(sales_net_field.value.replace(",", ".") or 0)
                    s_gross = float(sales_gross_field.value.replace(",", ".") or 0)
                    p_net = float(purchase_net_field.value.replace(",", ".") or 0)
                    vat_r = float(vat_field.value)
                    is_gross = (price_mode.value == "GROSS")
                except ValueError:
                    return

                db = next(get_db())
                new_p = Product(
                    name=name_p_field.value,
                    sku=sku_p_field.value,
                    unit=unit_p_field.value,
                    net_price=s_net,
                    vat_rate=vat_r,
                    gross_price=s_gross,
                    purchase_net_price=p_net,
                    is_gross_mode=is_gross
                )
                db.add(new_p)
                db.commit()
                new_id = new_p.id
                db.close()
                
                dlg_quick_p.open = False
                if self.page: self.page.update()
                
                if on_success:
                    on_success(new_p)
                self.page.update()
                
                refresh_products(new_id)
                if self.page:
                     self.page.snack_bar = ft.SnackBar(ft.Text("Produkt dodany."))
                     self.page.snack_bar.open = True
                     self.page.update()

            dlg_quick_p = ft.AlertDialog(
                title=ft.Text("Nowy towar/usługa"),
                content=ft.Container(
                    width=700,
                    height=500,
                    content=ft.Column([
                        name_p_field,
                        ft.Row([sku_p_field, unit_p_field]),
                        purchase_net_field,
                        ft.Divider(),
                        ft.Text("Cena sprzedaży"),
                        price_mode,
                        ft.Row([vat_field]),
                        ft.Row([sales_net_field, sales_gross_field])
                    ], scroll=ft.ScrollMode.AUTO)
                ),
                actions=[
                    ft.TextButton("Anuluj", on_click=lambda e: setattr(dlg_quick_p, 'open', False) or self.page.update()),
                    ft.ElevatedButton("Zapisz", on_click=save_quick_product)
                ]
            )
            self.page.overlay.append(dlg_quick_p)
            dlg_quick_p.open = True
            self.page.update()

        def add_item_dialog(e):
            print("Opening add_item_dialog") # Debug
            try:
                nonlocal active_prod_dd, active_on_prod_change
                # Dynamic options
                prod_options = [ft.dropdown.Option(text=f"{p.name} ({p.net_price} zł)", key=str(p.id)) for p in products]

                is_ryczalt = (tax_system_dd.value == TaxSystem.RYCZALT.value)

                prod_dd = ft.Dropdown(
                    label="Produkt",
                    options=prod_options,
                    expand=True
                )
                active_prod_dd = prod_dd
                
                # Przycisk dodawania produktu
                add_prod_btn = ft.TextButton(content=ft.Text("+", size=24, weight="bold"), tooltip="Nowy produkt", on_click=quick_add_product)
                qty_field = ft.TextField(label="Ilość", value="1", keyboard_type=ft.KeyboardType.NUMBER, width=80)
                unit_field = ft.TextField(label="Jm", value="szt", width=60)
                price_field = ft.TextField(label="Cena (lub Wartość)", width=100)
                
                # Pola specyficzne
                
                # Zwolnienie z VAT
                vat_initial_val = "23"
                vat_visible = not is_ryczalt
                vat_read_only = False
                
                if not config.is_vat_payer and not is_ryczalt:
                    vat_initial_val = "ZW"
                    
                vat_field = ft.TextField(label="VAT %", value=vat_initial_val, width=80, visible=vat_visible, read_only=vat_read_only)
                
                pkwiu_field = ft.TextField(label="PKWiU", width=100, visible=is_ryczalt)
                lump_sum_rates = ["17", "15", "14", "12.5", "12", "10", "8.5", "5.5", "3", "2"]
                lump_sum_dd = ft.Dropdown(
                    label="Stawka ryczałtu %",
                    width=150,
                    options=[ft.dropdown.Option(r) for r in lump_sum_rates],
                    value="12" if is_ryczalt else None,
                    visible=is_ryczalt
                )

                def on_prod_change(e):
                    try:
                        sel_id = int(prod_dd.value)
                        p = next((x for x in products if x.id == sel_id), None)
                        if p:
                            price_field.value = str(p.net_price)
                            unit_field.value = p.unit
                            if not is_ryczalt:
                                if not config.is_vat_payer:
                                    vat_field.value = "ZW"
                                else:
                                    vat_field.value = str(int(p.vat_rate * 100))
                            if hasattr(item_dlg, 'page') and item_dlg.page: item_dlg.page.update()
                    except: pass

                prod_dd.on_change = on_prod_change
                active_on_prod_change = on_prod_change

                def close_item_dialog(e=None):
                    nonlocal active_prod_dd, active_on_prod_change
                    active_prod_dd = None
                    active_on_prod_change = None
                    item_dlg.open = False
                    self.page.update()

                def confirm_add_item(e):
                    if not prod_dd.value or not price_field.value: return
                    
                    sel_id = int(prod_dd.value)
                    sel_prod = next((p for p in products if p.id == sel_id), None)
                    
                    qty = float(qty_field.value)
                    price = (price_field.value).replace(",", ".")
                    price = float(price)
                    
                    # Obliczenia
                    if is_ryczalt:
                        vat_rate = 0.0
                        net_val = price * qty # W ryczałcie przychód to cena * ilość
                        gross_val = net_val   # Brak VAT dla klienta
                        ls_rate = float(lump_sum_dd.value) / 100.0 if lump_sum_dd.value else 0.0
                    else:
                        vat_val_str = vat_field.value.upper()
                        if vat_val_str == "ZW":
                            vat_rate = 0.0 # Zwolniony
                        else:
                            try:
                                vat_rate = float(vat_val_str) / 100.0
                            except ValueError:
                                vat_rate = 0.0

                        items_net_val = price * qty
                        items_gross_val = items_net_val * (1 + vat_rate)
                        
                        net_val = items_net_val
                        gross_val = items_gross_val
                        ls_rate = None

                    items_list.append({
                        "product_id": sel_prod.id,
                        "product_name": sel_prod.name,
                        "quantity": qty,
                        "unit": unit_field.value,
                        "net_price": price,
                        "vat_rate": vat_rate, 
                        "pkwiu": pkwiu_field.value,
                        "lump_sum_rate": ls_rate,
                        "net_value": net_val,
                        "gross_value": gross_val,
                        "is_exempt_zw": (vat_field.value.upper() == "ZW") 
                    })
                    refresh_items_view()
                    
                    # --- AUTO UPDATE PAID AMOUNT IF CASH/CARD ---
                    try:
                        curr_method = payment_method_dd.value
                        if curr_method in ["Gotówka", "Karta"] and is_paid_switch.value:
                           # Recalculate total gross from all items
                           recalc_total = sum(i['gross_value'] for i in items_list)
                           paid_amt_field.value = f"{recalc_total:.2f}"
                           paid_amt_field.update()
                           # Also ensure paid_date is set if empty
                           if not paid_date_field.value:
                               paid_date_field.value = date_issue_field.value
                               paid_date_field.update()
                    except Exception as ex:
                        print(f"[AutoPay Update Error] {ex}")
                    # --------------------------------------------

                    close_item_dialog()

                item_dlg = ft.AlertDialog(
                    title=ft.Text("Dodaj pozycję"),
                    content=ft.Container(
                        width=700,
                        height=450,
                        content=ft.Column([
                            ft.Row([prod_dd, add_prod_btn]), 
                            ft.Row([qty_field, unit_field, price_field]),
                            ft.Row([vat_field, pkwiu_field, lump_sum_dd])
                        ])
                    ),
                    actions=[
                        ft.TextButton("Anuluj", on_click=close_item_dialog),
                        ft.ElevatedButton("Dodaj", on_click=confirm_add_item)
                    ]
                )
                self.page.overlay.append(item_dlg)
                item_dlg.open = True
                self.page.update()
            except Exception as ex:
                print(f"Error opening add_item_dialog: {ex}")
            
        def on_system_change(e):
            # Refresh logic handled in save, but visual updates here if needed
            pass
        
        # tax_system_dd.on_change = on_system_change

        def save_invoice(e):
            print("--- SAVE START ---")
            try:
                # Filter empty rows (where name is empty)
                clean_items = [i for i in items_list if i['product_name'].strip()]

                validation_errors = []
                if not contractor_dd.value:
                     current_error = "Wybierz kontrahenta"
                     contractor_dd.error_text = current_error
                     contractor_dd.update()
                     validation_errors.append(current_error)
                else:
                     contractor_dd.error_text = None
                     contractor_dd.update()

                if not clean_items:
                     validation_errors.append("Brak pozycji na fakturze")
                
                if self.category == InvoiceCategory.PURCHASE:
                    if not invoice_seq_number.value:
                        err = "Podaj numer faktury zakupowej!"
                        invoice_seq_number.error_text = err
                        invoice_seq_number.update()
                        validation_errors.append(err)
                    else:
                        invoice_seq_number.error_text = None
                        invoice_seq_number.update()
                
                if validation_errors:
                    if self.page:
                        self.page.snack_bar = ft.SnackBar(ft.Text(f"Błędy walidacji: {'; '.join(validation_errors)}"), bgcolor=ft.Colors.ERROR)
                        self.page.snack_bar.open = True
                        self.page.update()
                    return

                db = next(get_db())
                
                try:
                    t_net = sum(i['net_value'] for i in clean_items)
                    t_gross = sum(i['gross_value'] for i in clean_items)

                    inv_type_enum = InvoiceType(invoice_type.value)
                    tax_sys_enum = TaxSystem(tax_system_dd.value)

                    # Append SWIFT/Bank to keys if needed, using a trick, or just rely on UI
                    # Trick: Save to notes if not empty
                    extra_bank_info = []
                    if self.swift_field.value: extra_bank_info.append(f"SWIFT: {self.swift_field.value}")
                    if self.bank_name_field.value: extra_bank_info.append(f"Bank: {self.bank_name_field.value}")
                    
                    notes_content = "Pobrano z KSeF" if not edit_mode else (existing_invoice.notes if existing_invoice else "")
                    # Note: "Pobrano z KSeF" is weird default for manually created. usually None.
                    # The read_file showed `notes="Pobrano z KSeF"` in `download_ksef` but here we are creating manually.
                    # Default is None.
                    if (not edit_mode): notes_content = ""
                    if edit_mode and existing_invoice: notes_content = existing_invoice.notes
                    
                    if extra_bank_info:
                         append_str = "\n".join(extra_bank_info)
                         if notes_content:
                             # check if already there to avoid dupes? simple check
                             if self.swift_field.value and self.swift_field.value not in notes_content:
                                 notes_content = (notes_content + "\n" + append_str).strip()
                             elif not self.swift_field.value:
                                 notes_content = (notes_content + "\n" + append_str).strip()
                         else:
                             notes_content = append_str

                    # If editing, update existing
                    if edit_mode and existing_invoice:
                         existing_invoice.type = inv_type_enum
                         existing_invoice.tax_system = tax_sys_enum
                         existing_invoice.contractor_id = int(contractor_dd.value)
                         existing_invoice.date_issue = datetime.strptime(date_issue_field.value, "%Y-%m-%d")
                         existing_invoice.date_sale = datetime.strptime(date_sale_field.value, "%Y-%m-%d")
                         existing_invoice.place_of_issue = place_of_issue_field.value
                         existing_invoice.total_net = t_net
                         existing_invoice.total_gross = t_gross

                         existing_invoice.currency_rate = float(currency_rate.value or 1.0)
                         existing_invoice.currency_date = datetime.strptime(currency_date_field.value, "%Y-%m-%d") if currency_date_field.value else None
                         existing_invoice.payment_method = payment_method_dd.value
                         existing_invoice.is_cash_accounting = flag_cash_method.value
                         existing_invoice.is_reverse_charge = flag_reverse_charge.value
                         existing_invoice.bank_accounts = self.bank_accounts_field.value
                         existing_invoice.is_split_payment = flag_split_payment.value
                         existing_invoice.margin_procedure_type = margin_proc.value
                         
                         existing_invoice.transaction_order_number = order_num.value
                         existing_invoice.transaction_order_date = datetime.strptime(order_date.value, "%Y-%m-%d") if order_date.value else None
                         existing_invoice.transaction_contract_number = contract_num.value
                         existing_invoice.transaction_contract_date = datetime.strptime(contract_date.value, "%Y-%m-%d") if contract_date.value else None
                         
                         existing_invoice.is_paid = is_paid_switch.value
                         existing_invoice.paid_amount = float(paid_amt_field.value.replace(",", ".") or 0.0) if is_paid_switch.value else 0.0
                         existing_invoice.paid_date = datetime.strptime(paid_date_field.value, "%Y-%m-%d") if paid_date_field.value else None
                         existing_invoice.notes = notes_content

                         # Number change logic
                         if self.category == InvoiceCategory.PURCHASE:
                              existing_invoice.number = invoice_seq_number.value
                         
                         db.query(InvoiceItem).filter(InvoiceItem.invoice_id == existing_invoice.id).delete()
                         new_invoice = existing_invoice 
                    else:
                         new_invoice = Invoice(
                            category=self.category,
                            type=inv_type_enum,
                            tax_system=tax_sys_enum,
                            contractor_id=int(contractor_dd.value),
                            date_issue=datetime.strptime(date_issue_field.value, "%Y-%m-%d"),
                            date_sale=datetime.strptime(date_sale_field.value, "%Y-%m-%d"),
                            place_of_issue=place_of_issue_field.value,
                            total_net=t_net,
                            total_gross=t_gross,
                            currency=currency_dd.value,
                            currency_rate=float(currency_rate.value or 1.0),
                            currency_date=datetime.strptime(currency_date_field.value, "%Y-%m-%d") if currency_date_field.value else None,
                            payment_method=payment_method_dd.value,
                            is_cash_accounting=flag_cash_method.value,
                            is_reverse_charge=flag_reverse_charge.value,
                            bank_accounts=self.bank_accounts_field.value,
                            is_split_payment=flag_split_payment.value,
                            is_exempt=False, 
                            margin_procedure_type=margin_proc.value,
                            transaction_order_number=order_num.value,
                            transaction_order_date=datetime.strptime(order_date.value, "%Y-%m-%d") if order_date.value else None,
                            transaction_contract_number=contract_num.value,
                            transaction_contract_date=datetime.strptime(contract_date.value, "%Y-%m-%d") if contract_date.value else None,
                            is_paid=is_paid_switch.value,
                            paid_amount=float(paid_amt_field.value.replace(",", ".") or 0.0) if is_paid_switch.value else 0.0,
                            paid_date=datetime.strptime(paid_date_field.value, "%Y-%m-%d") if paid_date_field.value else None,
                            notes=notes_content
                        )

                    if self.category == InvoiceCategory.PURCHASE:
                        new_invoice.number = invoice_seq_number.value
                    elif not edit_mode: 
                        n_service = NumberingService(db)
                        manual_seq = None
                        if invoice_seq_number.value:
                            val = invoice_seq_number.value
                            try:
                                import re
                                match = re.search(r'\d+', val)
                                manual_seq = int(match.group(0)) if match else int(val)
                            except: pass
                        n_service.apply_numbering(new_invoice, manual_sequence_number=manual_seq)

                    if not edit_mode: db.add(new_invoice)
                    db.commit() # Commit main invoice

                    idx_counter = 1
                    for item in clean_items:
                        db_item = InvoiceItem(
                            invoice_id=new_invoice.id,
                            index=idx_counter,
                            product_name=item['product_name'],
                            quantity=item['quantity'],
                            unit=item.get('unit', 'szt.'),
                            net_price=item['net_price'],
                            pkwiu=item.get('pkwiu'),
                            lump_sum_rate=item.get('lump_sum_rate'),
                            vat_rate=item['vat_rate'],
                            gross_value=item['gross_value']
                        )
                        db.add(db_item)
                        idx_counter += 1
                    
                    db.commit()
                    print("--- SAVE SUCCESS ---")
                    
                    main_dlg.open = False
                    self.page.update()
                    self.load_invoices()
                
                finally:
                    db.close()

            except Exception as ex:
                if self.page:
                     self.page.snack_bar = ft.SnackBar(ft.Text(f"Błąd zapisu: {str(ex)}"), bgcolor=ft.Colors.ERROR)
                     self.page.snack_bar.open = True
                     self.page.update()
                print(f"SAVE ERROR: {ex}")
                import traceback
                traceback.print_exc()


        # Content Views
        # Move visibility logic to container content switching for better stability
        content_basic = ft.Container(
            padding=10,
            content=ft.Column([
                ft.Row([ro(invoice_type), ro(invoice_seq_number), ro(place_of_issue_field)]),
                ft.Row([ro(date_issue_field), ro(date_sale_field)]),
                contractor_row, # Inner buttons already handled via is_locked_ksef? Need check contractor_row definition
                ft.Row([ro(currency_dd), ro(currency_rate), ro(currency_date_field)]),
                ft.Divider(),
                ft.Text("Pozycje:", weight="bold"),
                items_view,
                self.lbl_summary_total,

                # Button removed as requested
                # ft.Row([
                #    ft.OutlinedButton("Dodaj pusty wiersz", icon="post_add", on_click=add_empty_row),
                #    ft.OutlinedButton("Kreator pozycji (Popup)", icon="add", on_click=add_item_dialog, disabled=is_locked_ksef)
                # ])

            ], scroll=ft.ScrollMode.AUTO)
        )

        # --- Payments Tab Static Structure ---
        # Strategy: Keep all controls in the Row, toggle their visibility property.
        
        # 1. Main Payment Params Row
        # Includes Dropdown + Deadline Fields (always present in list, toggled via visible)
        payment_params_row = ft.Row([
            ro(payment_method_dd),
            ro(payment_deadline_field),
            ro(payment_deadline_date_field)
        ])
        
        # 2. Bank Account Container (Conditional)
        bank_account_container = ft.Column([
            ft.Row([ro(self.bank_name_field), ro(self.swift_field), ro(self.bank_accounts_field)])
        ] if self.bank_accounts_field else [])

        # Logic to update the conditions (Redefined to capture payment_params_row)
        def run_payment_visibility_logic(e=None):
             method = payment_method_dd.value
             print(f"[DEBUG] run_payment_visibility_logic. Value: {method}")
             
             is_transfer_or_credit = method not in ["Gotówka", "Karta"]

             # Update Fields Property
             # We toggle visibility. Page.update() or Parent.update() should handle the rest.
             payment_deadline_field.visible = is_transfer_or_credit
             payment_deadline_date_field.visible = is_transfer_or_credit
             
             # Log status
             print(f"[DEBUG] Visibility set to {is_transfer_or_credit} for deadline fields")

             # Skip direct row update if it causes issues.
             # Using content_payments.update() (Container) or separate updates on siblings.
             
             # Update Bank Account
             if self.bank_accounts_field:
                 self.bank_accounts_field.visible = is_transfer_or_credit
                 self.swift_field.visible = is_transfer_or_credit
                 self.bank_name_field.visible = is_transfer_or_credit

                 if is_transfer_or_credit and self.category != InvoiceCategory.PURCHASE and not self.bank_accounts_field.value:
                      if config and config.bank_account:
                           self.bank_accounts_field.value = config.bank_account
                           self.swift_field.value = config.swift_code if config.swift_code else ""
                           self.bank_name_field.value = config.bank_name if config.bank_name else ""
                 
                 bank_account_container.visible = is_transfer_or_credit

             # Automatic Paid Status Logic for Cash/Card
             is_cash_or_card = method in ["Gotówka", "Karta"]
             if is_cash_or_card:
                is_paid_switch.value = True
                paid_date_field.value = date_issue_field.value 
                # Recalculate total
                total_gross = sum(i['gross_value'] for i in items_list)
                paid_amt_field.value = f"{total_gross:.2f}"
                
                paid_amt_field.disabled = False
                paid_date_field.disabled = False
                
                # Update UI
                try:
                    if is_paid_switch.page: is_paid_switch.update()
                except: pass
                
                try:
                    if paid_amt_field.page: paid_amt_field.update()
                except: pass
                
                try:
                    if paid_date_field.page: paid_date_field.update()
                except: pass

        # Payment Method Change Logic
        # Explicit function used for on_change
        def on_payment_method_change_handler(e):
             print(f"[DEBUG] Handler fired. Event type: {e.name if hasattr(e, 'name') else '?'}")
             run_payment_visibility_logic(e)
             
             # Refresh everything. 
             # In tricky Dialog scenarios, updating the container holding the row helps.
             # Updating the page should work, but let's try strict hierarchy.
             try:
                 if content_payments.page: content_payments.update()
                 if self.page: self.page.update()
             except Exception as ex:
                 print(f"[DEBUG] Update error: {ex}")
        
        # KEY FIX: Assign using Lambda to ensure late binding if needed, or direct
        # Adding on_select as well per user hint
        payment_method_dd.on_change = on_payment_method_change_handler
        payment_method_dd.on_select = on_payment_method_change_handler
        
        # Initial State Set
        run_payment_visibility_logic(None)

        content_payments = ft.Container(
            padding=10,
            content=ft.Column([
                ft.Text("Warunki płatności", weight="bold"),
                payment_params_row,
                bank_account_container,
                ft.Divider(),
                ft.Text("Status płatności", weight="bold"),
                ro(is_paid_switch),
                ft.Row([ro(paid_amt_field), ro(paid_date_field)]),
                ft.Divider(),
                ft.Text("Opcje płatności VAT", weight="bold", visible=is_vat_payer_status),
                vat_options_row
            ], scroll=ft.ScrollMode.AUTO)
        )

        # Old location of on_change assignment removed to avoid duplication/confusion
        # payment_method_dd.on_change = on_payment_method_change

        content_advanced = ft.Container(
            padding=10,
            content=ft.Column([
                ft.Text("Procedury specjalne", weight="bold"),
                ft.Row([ro(flag_reverse_charge)]),
                ro(margin_chk),
                ro(margin_proc),
                ft.Divider(),
                # Exempt removed from UI
                ft.Text("Dokumenty powiązane (Warunki transakcji)", weight="bold"),
                ro(order_chk),
                ft.Row([ro(order_num), ro(order_date)]),
                ro(contract_chk),
                ft.Row([ro(contract_num), ro(contract_date)])
            ], scroll=ft.ScrollMode.AUTO)
        )
        
        # Tabs Logic
        tabs_map = {0: content_basic, 1: content_payments, 2: content_advanced}
        
        # Container that holds the changing content
        content_host = ft.Container(content=content_basic, expand=True)

        def get_tab_style(is_active):
            return ft.ButtonStyle(
                color=ft.Colors.BLUE_900 if is_active else ft.Colors.BLACK54,
                bgcolor=ft.Colors.BLUE_50 if is_active else ft.Colors.TRANSPARENT,
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=15
            )

        def on_tab_click(idx):
             # Visual highlight
             btn_basic.style = get_tab_style(idx == 0)
             btn_pay.style = get_tab_style(idx == 1)
             btn_adv.style = get_tab_style(idx == 2)
             
             # Content switch
             content_host.content = tabs_map.get(idx, content_basic)
             
             try:
                 # Update logic
                 if self.page:
                      self.page.update()
             except Exception as ex:
                 print(f"Update error in tab switch: {ex}")

        btn_basic = ft.TextButton("Podstawowe", icon="description", on_click=lambda e: on_tab_click(0), style=get_tab_style(True))
        btn_pay = ft.TextButton("Płatności", icon="payment", on_click=lambda e: on_tab_click(1), style=get_tab_style(False))
        btn_adv = ft.TextButton("Zaawansowane / KSeF", icon="settings", on_click=lambda e: on_tab_click(2), style=get_tab_style(False))
        
        tabs_control = ft.Container(
            content=ft.Row(
                [btn_basic, btn_pay, btn_adv],
                alignment=ft.MainAxisAlignment.CENTER,
                scroll=ft.ScrollMode.AUTO
            ),
            padding=5,
            bgcolor=ft.Colors.TRANSPARENT
        )
        tabs_row = tabs_control.content

        actions_list = [
            ft.TextButton("Anuluj" if not readonly else "Zamknij", on_click=lambda e: setattr(main_dlg, 'open', False) or self.page.update())
        ]
        if not readonly:
            actions_list.append(ft.ElevatedButton("Zapisz", on_click=save_invoice))

        main_dlg = ft.AlertDialog(
            title=ft.Text(dialog_title),
            content=ft.Container(
                width=900,
                height=600,
                content=ft.Column([
                    tabs_control,
                    content_host
                ])
            ),
            actions=actions_list
        )
        # Force initial update for preview params via safe wrapper
        # Call BEFORE opening dialog so values are set but 'update' is skipped (page=None for control)
        # Then page.update() renders the dialog with correct values.
        update_number_params()
        
        # Populate initial Items Grid
        refresh_items_view()

        self.page.overlay.append(main_dlg)
        main_dlg.open = True
        self.page.update()
