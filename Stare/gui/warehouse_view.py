import flet as ft
from database.engine import get_db
from database.models import Product

class WarehouseView(ft.Column):
    def __init__(self):
        super().__init__(scroll=ft.ScrollMode.AUTO, expand=True)
        self.products_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Nazwa")),
                ft.DataColumn(ft.Text("SKU")),
                ft.DataColumn(ft.Text("Cena Netto")),
                ft.DataColumn(ft.Text("VAT")),
                ft.DataColumn(ft.Text("Jednostka")),
            ],
            rows=[]
        )
        
        self.controls = [
            ft.Row([
                ft.Text("Towary", size=30, weight="bold"),
                ft.Row([
                    ft.ElevatedButton("Dodaj towar", icon="add", on_click=self.open_add_product_dialog),
                    # ft.ElevatedButton("Edytuj", icon="edit"),
                    # ft.ElevatedButton("Usuń", icon="delete", color="red"),
                    ft.VerticalDivider(),
                    ft.TextField(label="Szukaj", width=200, icon="search"),
                ])
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Container(
                 expand=True,
                 content=ft.Column([self.products_table], scroll=ft.ScrollMode.AUTO)
            )
        ]
        self.load_products()

    def load_products(self):
        self.products_table.rows.clear()
        
        db = next(get_db())
        products = db.query(Product).all()
        
        for p in products:
            self.products_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(p.name)),
                        ft.DataCell(ft.Text(p.sku or "-")),
                        ft.DataCell(ft.Text(f"{p.net_price:.2f}")),
                        ft.DataCell(ft.Text(f"{p.vat_rate}%")),
                        ft.DataCell(ft.Text(p.unit)),
                    ],
                    on_select_change=lambda e, p=p: self.open_add_product_dialog(e, p)
                )
            )
        db.close()
        try:
            if self.page:
                self.update()
        except Exception:
            pass

    def did_mount(self):
        self.update()

    def open_add_product_dialog(self, e, product=None):
        from database.models import InvoiceItem
        is_edit = product is not None
        
        # Pobierz stawki VAT z bazy
        db = next(get_db())
        from database.models import VatRate
        rates = db.query(VatRate).all()
        db.close()
        
        # Domyślne stawki jeśli brak w bazie
        vat_options = [ft.dropdown.Option(text=r.name, key=str(r.rate)) for r in rates]
        if not vat_options:
            vat_options = [
                ft.dropdown.Option(text="23%", key="0.23"),
                ft.dropdown.Option(text="8%", key="0.08"), 
                ft.dropdown.Option(text="5%", key="0.05"), 
                ft.dropdown.Option(text="0%", key="0.0")
            ]

        name_field = ft.TextField(label="Nazwa produktu", col={"md": 12}, value=product.name if is_edit else "")
        sku_field = ft.TextField(label="SKU (Kod)", col={"md": 6}, value=product.sku if is_edit and product.sku else "")
        unit_field = ft.TextField(label="Jednostka", value=product.unit if is_edit else "szt.", col={"md": 6})
        
        # Pola cenowe init
        init_vat_val = str(product.vat_rate) if is_edit else "0.23"
        # Find matching option or select first
        if not any(o.key == init_vat_val for o in vat_options):
             # Try formatting ?
             pass

        purchase_net_field = ft.TextField(label="Cena zakupu (netto)", value=str(product.purchase_net_price) if is_edit else "0.00", keyboard_type=ft.KeyboardType.NUMBER, col={"md": 6})
        
        vat_field = ft.Dropdown(label="Stawka VAT", value=init_vat_val, options=vat_options, col={"md": 6})
        
        init_net = f"{product.net_price:.2f}" if is_edit else "0.00"
        init_gross = f"{product.gross_price:.2f}" if is_edit else "0.00"

        sales_net_field = ft.TextField(label="Cena sprzedaży (netto)", value=init_net, keyboard_type=ft.KeyboardType.NUMBER, col={"md": 6})
        sales_gross_field = ft.TextField(label="Cena sprzedaży (brutto)", value=init_gross, keyboard_type=ft.KeyboardType.NUMBER, col={"md": 6})
        
        init_mode = "GROSS" if (is_edit and product.is_gross_mode) else "NET"
        
        price_mode = ft.RadioGroup(content=ft.Row([
            ft.Radio(value="NET", label="Od Netto"),
            ft.Radio(value="GROSS", label="Od Brutto")
        ]), value=init_mode)

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
                # Liczymy brutto od netto
                gross = net * (1 + vat_rate)
                sales_gross_field.value = f"{gross:.2f}"
            elif mode == "GROSS" and source_field != "net":
                # Liczymy netto od brutto
                net = gross / (1 + vat_rate)
                sales_net_field.value = f"{net:.2f}"
            
            # Recalculate other direction if needed (e.g. VAT change)
            if source_field == "vat":
                if mode == "NET":
                     gross = net * (1 + vat_rate)
                     sales_gross_field.value = f"{gross:.2f}"
                else:
                     net = gross / (1 + vat_rate)
                     sales_net_field.value = f"{net:.2f}"

            if dlg.open: self.page.update()

        # Listeners
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
            recalculate("vat") # Refresh current state
            self.page.update()

        price_mode.on_change = on_mode_change
        
        # Init state
        if init_mode == "NET":
             sales_net_field.read_only = False
             sales_gross_field.read_only = True
        else:
             sales_net_field.read_only = True
             sales_gross_field.read_only = False
             
        def delete_product(e):
            if not is_edit: return
            pid = product.id
            pname = product.name
            db = next(get_db())
            # InvoiceItem nie ma product_id, sprawdzamy po nazwie
            cnt = db.query(InvoiceItem).filter(InvoiceItem.product_name == pname).count()
            if cnt > 0:
                db.close()
                if self.page:
                    self.page.snack_bar = ft.SnackBar(ft.Text(f"Nie można usunąć: Towar użyty w {cnt} pozycjach!"))
                    self.page.snack_bar.open = True
                    self.page.update()
                return
            
            def confirm_del(e):
                db.query(Product).filter(Product.id == pid).delete()
                db.commit()
                db.close()
                dlg_del.open = False
                dlg.open = False
                self.page.update()
                self.load_products()

            dlg_del = ft.AlertDialog(
                title=ft.Text("Usuń towar"), content=ft.Text("Czy na pewno?"),
                actions=[ft.TextButton("Nie", on_click=lambda e: setattr(dlg_del, 'open', False) or self.page.update()), 
                         ft.ElevatedButton("Tak", color="red", on_click=confirm_del)]
            )
            self.page.overlay.append(dlg_del)
            dlg_del.open = True
            self.page.update()

        def save_product(e):
            if not name_field.value:
                return 
            
            try:
                p_net = float(purchase_net_field.value.replace(",", ".") or 0)
                s_net = float(sales_net_field.value.replace(",", ".") or 0)
                s_gross = float(sales_gross_field.value.replace(",", ".") or 0)
                vat_r = float(vat_field.value)
                is_gross = (price_mode.value == "GROSS")
            except ValueError:
                return

            db = next(get_db())
            
            if is_edit:
                curr = db.query(Product).filter(Product.id == product.id).first()
                if curr:
                    curr.name = name_field.value
                    curr.sku = sku_field.value
                    curr.unit = unit_field.value
                    curr.purchase_net_price = p_net
                    curr.net_price = s_net
                    curr.gross_price = s_gross
                    curr.vat_rate = vat_r
                    curr.is_gross_mode = is_gross
            else:
                new_product = Product(
                    name=name_field.value,
                    sku=sku_field.value,
                    unit=unit_field.value,
                    purchase_net_price=p_net,
                    net_price=s_net,
                    gross_price=s_gross,
                    vat_rate=vat_r,
                    is_gross_mode=is_gross
                )
                db.add(new_product)
                
            db.commit()
            db.close()
            
            if self.page:
                 dlg.open = False
                 self.page.update()
            self.load_products()

        dlg = ft.AlertDialog(
            title=ft.Text("Dodaj towar"),
            content=ft.Container(
                width=600,
                content=ft.Column([
                    ft.Text("Podstawowe", weight="bold"),
                    ft.ResponsiveRow([name_field, sku_field, unit_field]),
                    ft.Divider(),
                    ft.Text("Ceny", weight="bold"),
                    ft.ResponsiveRow([
                        ft.Column([ft.Text("Metoda wyliczania:"), price_mode], col=6),
                        vat_field
                    ]),
                    ft.ResponsiveRow([purchase_net_field, sales_net_field, sales_gross_field])
                ], height=400, scroll=ft.ScrollMode.AUTO)
            ),
            actions=[
                ft.TextButton("Usuń", on_click=delete_product, style=ft.ButtonStyle(color="red"), visible=is_edit),
                ft.TextButton("Anuluj", on_click=lambda e: setattr(dlg, 'open', False) or self.page.update() if self.page else None),
                ft.ElevatedButton("Zapisz", on_click=save_product)
            ]
        )
        if self.page:
            self.page.overlay.append(dlg)
            dlg.open = True
            self.page.update()
