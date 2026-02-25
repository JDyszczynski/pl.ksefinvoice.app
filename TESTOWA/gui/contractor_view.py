import flet as ft
from database.engine import get_db
from database.models import Contractor, Invoice
from gus.client import GusClient
from vies.client import ViesClient
from mf_whitelist.client import MfWhitelistClient

class ContractorView(ft.Column):
    def __init__(self):
        super().__init__(scroll=ft.ScrollMode.AUTO, expand=True)
        self.contractors_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("NIP")),
                ft.DataColumn(ft.Text("Nazwa")),
                ft.DataColumn(ft.Text("Adres")),
                ft.DataColumn(ft.Text("Miasto")),
                ft.DataColumn(ft.Text("Akcje")),
            ],
            rows=[]
        )
        self.gus_client = GusClient()
        self.vies_client = ViesClient()
        self.mf_client = MfWhitelistClient()
        
        self.controls = [
            ft.Row([
                ft.Text("Kontrahenci", size=30, weight="bold"),
                ft.Row([
                    ft.ElevatedButton("Pobierz z GUS", icon="search", on_click=self.open_gus_dialog),
                    ft.ElevatedButton("Dodaj ręcznie", icon="add", on_click=lambda e: self.open_edit_dialog())
                ])
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            self.contractors_table
        ]
        self.load_contractors()

    def load_contractors(self):
        self.contractors_table.rows.clear()
        db = next(get_db())
        contractors = db.query(Contractor).all()
        
        for c in contractors:
            # Prepare data dict for edit
            c_data = {
                "id": c.id,
                "name": c.name,
                "nip": c.nip,
                "address": c.address,
                "city": c.city,
                "postal_code": c.postal_code,
                "phone": c.phone,
                "email": c.email,
                "country": c.country,
                "country_code": c.country_code,
                "is_vat_payer": c.is_vat_payer,
                "is_vat_ue": c.is_vat_ue
            }
            
            self.contractors_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(c.nip)),
                        ft.DataCell(ft.Text(c.name)),
                        ft.DataCell(ft.Text(c.address or "")),
                        ft.DataCell(ft.Text(c.city or "")),
                        ft.DataCell(ft.Row([
                            ft.IconButton(
                                icon=ft.Text("✎"),
                                tooltip="Edytuj",
                                on_click=lambda e, data=c_data: self.open_edit_dialog(data)
                            ),
                            ft.IconButton(
                                icon=ft.Text("🗑", color="red"), 
                                tooltip="Usuń",
                                on_click=lambda e, data=c_data: self.delete_contractor_direct(data)
                            )
                        ]))
                    ],
                    on_select_change=lambda e, data=c_data: self.open_edit_dialog(data)
                )
            )
        db.close()
        try:
            if self.page:
                self.update()
        except Exception:
            pass
            
    def delete_contractor_direct(self, data):
        # Helper to trigger delete logic directly 
        cid = int(data["id"])
        db_chk = next(get_db())
        usage_count = db_chk.query(Invoice).filter(Invoice.contractor_id == cid).count()
        db_chk.close()
        
        if usage_count > 0:
            if self.page:
                self.page.snack_bar = ft.SnackBar(ft.Text(f"Nie można usunąć: Kontrahent przypisany do {usage_count} faktur!"))
                self.page.snack_bar.open = True
                self.page.update()
            return

        def confirm_del(e):
            db = next(get_db())
            db.query(Contractor).filter(Contractor.id == cid).delete()
            db.commit()
            db.close()
            dlg_del.open = False
            self.page.update()
            self.load_contractors()

        dlg_del = ft.AlertDialog(
            title=ft.Text("Potwierdź usunięcie"),
            content=ft.Text(f"Czy na pewno chcesz usunąć kontrahenta {data['name']}?"),
            actions=[
                ft.TextButton("Nie", on_click=lambda e: setattr(dlg_del, 'open', False) or self.page.update()),
                ft.ElevatedButton("Tak, usuń", color="red", on_click=confirm_del)
            ]
        )
        self.page.overlay.append(dlg_del)
        dlg_del.open = True
        self.page.update()
    
    def did_mount(self):
        self.update()

    def open_gus_dialog(self, e):
        id_field = ft.TextField(label="Wpisz numer", width=200)
        id_type = ft.RadioGroup(content=ft.Row([
            ft.Radio(value="NIP", label="NIP"),
            ft.Radio(value="REGON", label="REGON")
        ]), value="NIP")

        def search_gus(e):
            if not id_field.value: return
            
            # TODO: Obsługa REGON, na razie zakładamy NIP
            data = self.gus_client.get_contractor_by_nip(id_field.value)
            
            if self.page:
                dlg.open = False
                self.page.update()
                self.open_edit_dialog(data)

        dlg = ft.AlertDialog(
            title=ft.Text("Pobierz z GUS"),
            content=ft.Column([
                ft.Text("Wybierz identyfikator:"),
                id_type,
                ft.Text("Numer:"),
                id_field
            ], height=150),
            actions=[
                ft.TextButton("Anuluj", on_click=lambda e: setattr(dlg, 'open', False) or self.page.update() if self.page else None),
                ft.ElevatedButton("Szukaj", on_click=search_gus)
            ]
        )
        if self.page:
             self.page.overlay.append(dlg)
             dlg.open = True
             self.page.update()

        def verify_vat_ue(e):
             # ... imports needed? Assumed available in scope or file
             pass # Kept existing logic implicitly
        
        # logic...

    def open_edit_dialog(self, initial_data=None):
        from database.models import Invoice # Import here or top
        is_edit = initial_data is not None and "id" in initial_data
        
        if initial_data is None: initial_data = {}
        
        # ... fields definition as before ...
        name_field = ft.TextField(label="Nazwa", value=initial_data.get("name", ""))
        nip_field = ft.TextField(label="NIP", value=initial_data.get("nip", ""))
        address_field = ft.TextField(label="Adres (ulica i nr)", value=initial_data.get("address", ""))
        city_field = ft.TextField(label="Miasto", value=initial_data.get("city", ""))
        postal_field = ft.TextField(label="Kod pocztowy", value=initial_data.get("postal_code", ""))
        phone_field = ft.TextField(label="Telefon", value=initial_data.get("phone", ""))
        email_field = ft.TextField(label="Email", value=initial_data.get("email", ""))
        
        country_field = ft.TextField(label="Kraj", value=initial_data.get("country", "Polska"), width=200)
        country_code_field = ft.TextField(label="Kod kraju (ISO)", value=initial_data.get("country_code", "PL"), width=100)
        
        is_vat_field = ft.Checkbox(label="Czynny podatnik VAT", value=initial_data.get("is_vat_payer", True))
        is_vat_ue_field = ft.Checkbox(label="Podatnik VAT UE", value=initial_data.get("is_vat_ue", False))

        # ... verify functions ...
        def verify_vat(e):
             if not nip_field.value: return
             if self.page:
                  self.page.snack_bar = ft.SnackBar(ft.Text("Weryfikacja w systemie MF..."), duration=1000)
                  self.page.snack_bar.open = True
                  self.page.update()
             result = self.mf_client.check_nip(nip_field.value)
             is_error = not result.get("success")
             msg = f"Status: {result.get('status')}" if not is_error else f"Błąd: {result.get('error')}"
             if not is_error and result.get("active"): is_vat_field.value = True
             if self.page:
                 self.page.dialog = ft.AlertDialog(title=ft.Text("MF"), content=ft.Text(msg))
                 self.page.dialog.open = True
                 self.page.update()

        def verify_vat_ue(e):
             if not nip_field.value: return
             if self.page:
                  self.page.snack_bar = ft.SnackBar(ft.Text("Weryfikacja VIES..."), duration=1000)
                  self.page.snack_bar.open = True
                  self.page.update()
             result = self.vies_client.check_vat(country_code_field.value, nip_field.value)
             is_error = not result.get("success")
             msg = f"Status: {'Aktywny' if result.get('valid') else 'Nieaktywny'}" if not is_error else f"Błąd: {result.get('error')}"
             if not is_error and result.get("valid"): is_vat_ue_field.value = True
             if self.page:
                 self.page.dialog = ft.AlertDialog(title=ft.Text("VIES"), content=ft.Text(msg))
                 self.page.dialog.open = True
                 self.page.update()

        def delete_contractor(e):
            if not is_edit: return
            cid = int(initial_data["id"])
            db = next(get_db())
            
            # Check usage
            usage_count = db.query(Invoice).filter(Invoice.contractor_id == cid).count()
            if usage_count > 0:
                db.close()
                if self.page:
                    self.page.snack_bar = ft.SnackBar(ft.Text(f"Nie można usunąć: Kontrahent przypisany do {usage_count} faktur!"))
                    self.page.snack_bar.open = True
                    self.page.update()
                return

            # Confirm
            def confirm_del(e):
                db.query(Contractor).filter(Contractor.id == cid).delete()
                db.commit()
                db.close()
                dlg_del.open = False
                dlg.open = False
                self.page.update()
                self.load_contractors()

            dlg_del = ft.AlertDialog(
                title=ft.Text("Potwierdź usunięcie"),
                content=ft.Text("Czy na pewno chcesz usunąć tego kontrahenta?"),
                actions=[
                    ft.TextButton("Nie", on_click=lambda e: setattr(dlg_del, 'open', False) or self.page.update()),
                    ft.ElevatedButton("Tak, usuń", color="red", on_click=confirm_del)
                ]
            )
            self.page.overlay.append(dlg_del)
            dlg_del.open = True
            self.page.update()

        def save_contractor(e):
            if not name_field.value or not nip_field.value: return
            
            db = next(get_db())
            existing = db.query(Contractor).filter(Contractor.nip == nip_field.value).first()
            if existing:
                existing.name = name_field.value
                existing.address = address_field.value
                existing.city = city_field.value
                existing.postal_code = postal_field.value
                existing.phone = phone_field.value
                existing.email = email_field.value
                existing.country = country_field.value
                existing.country_code = country_code_field.value
                existing.is_vat_payer = is_vat_field.value
                existing.is_vat_ue = is_vat_ue_field.value
            else:
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
            db.close()
            
            if self.page and dlg:
                 dlg.open = False
                 self.page.update()
            self.load_contractors()

        dlg = ft.AlertDialog(
            title=ft.Text("Dane kontrahenta"),
            content=ft.Container(
                content=ft.Column([
                    ft.Text("Dane podstawowe", weight="bold"),
                    name_field, 
                    ft.Row([
                        nip_field, 
                        postal_field
                    ]),
                    ft.Row([
                        is_vat_field,
                        ft.ElevatedButton("Weryfikuj MF", on_click=verify_vat, height=30)
                    ]),
                    ft.Row([
                        is_vat_ue_field,
                        ft.ElevatedButton("Weryfikuj VIES", on_click=verify_vat_ue, height=30)
                    ]),
                    ft.Divider(),
                    ft.Text("Adres", weight="bold"),
                    ft.Row([country_field, country_code_field]),
                    address_field, 
                    city_field,
                    ft.Divider(),
                    ft.Text("Kontakt", weight="bold"),
                    ft.Row([phone_field, email_field])
                ], scroll=ft.ScrollMode.AUTO),
                height=500,
                width=600
            ),
            actions=[
                ft.TextButton("Usuń", on_click=delete_contractor, style=ft.ButtonStyle(color="red"), visible=is_edit),
                ft.TextButton("Anuluj", on_click=lambda e: setattr(dlg, 'open', False) or self.page.update() if self.page else None),
                ft.ElevatedButton("Zapisz", on_click=save_contractor)
            ]
        )
        
        if self.page:
            self.page.overlay.append(dlg)
            dlg.open = True
            self.page.update()
