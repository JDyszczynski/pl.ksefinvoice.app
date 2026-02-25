import flet as ft
from database.engine import get_db
from database.models import Invoice, InvoiceCategory

class SettlementsView(ft.Column):
    def __init__(self):
        super().__init__(scroll=ft.ScrollMode.AUTO, expand=True)
        
        self.current_invoices = []
        
        self.data_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Typ")),
                ft.DataColumn(ft.Text("Numer")),
                ft.DataColumn(ft.Text("Kontrahent")),
                ft.DataColumn(ft.Text("Kwota do zapłaty")),
                ft.DataColumn(ft.Text("Zapłacono")),
                ft.DataColumn(ft.Text("Pozostało")),
                ft.DataColumn(ft.Text("Status")),
                ft.DataColumn(ft.Text("Akcja")),
            ],
            rows=[]
        )

        self.controls = [
            ft.Text("Rozliczenia", size=30, weight="bold"),
            ft.ElevatedButton("Odśwież", icon="refresh", on_click=lambda e: self.load_data()),
            ft.Container(content=self.data_table, expand=True)
        ]

    def did_mount(self):
        self.load_data()

    def load_data(self):
        self.data_table.rows.clear()
        
        db = next(get_db())
        try:
            # Pobieramy wszystkie faktury
            invoices = db.query(Invoice).order_by(Invoice.date_issue.desc()).all()
            
            # --- Logika grupowania ("wątki" faktura + korekty) ---
            inv_map = {inv.id: inv for inv in invoices}
            groups = {} 
            
            def get_root_id(inv_obj):
                curr = inv_obj
                depth = 0
                while curr.parent_id and depth < 10:
                    if curr.parent_id in inv_map:
                        curr = inv_map[curr.parent_id]
                        depth += 1
                    else:
                        break
                return curr.id

            for inv in invoices:
                root = get_root_id(inv)
                if root not in groups:
                    groups[root] = []
                groups[root].append(inv)

            # Sortowanie: najnowsze "wątki" na górze
            sorted_group_keys = sorted(
                groups.keys(),
                key=lambda rid: max((i.date_issue for i in groups[rid]), default=groups[rid][0].date_issue),
                reverse=True
            )

            for root_id in sorted_group_keys:
                family = groups[root_id]
                root_inv = inv_map.get(root_id)
                if not root_inv: continue

                # Sumujemy całą grupę: (Root + Korekty)
                # FIX: Korekty w DB mają pełną wartość (nowy stan), więc nie sumujemy,
                # lecz bierzemy wartość z OSTATNIEGO dokumentu (najnowszego).
                sorted_family = sorted(family, key=lambda x: x.id) # Sortujemy po ID
                latest_doc = sorted_family[-1]
                
                total_gross_group = latest_doc.total_gross
                total_paid_group = sum(i.paid_amount for i in family)
                remaining_group = total_gross_group - total_paid_group
                
                status_color = "red"
                status_text = "Nieopłacona"
                
                # Tolerancja groszowa
                if abs(remaining_group) < 0.02:
                    status_color = "green"
                    status_text = "Rozliczona"
                    remaining_group = 0.00
                elif total_paid_group > 0:
                    status_color = "orange"
                    status_text = "Cześciowo"
                
                if remaining_group < -0.01:
                    status_color = "blue"
                    status_text = "Do zwrotu"

                # Wyświetlamy jako jeden wiersz
                corrections_count = len(family) - 1
                display_number = root_inv.number
                if corrections_count > 0:
                    display_number += f" (+{corrections_count} kor.)"

                cat_text = "Sprzedaż" if root_inv.category == InvoiceCategory.SALES else "Zakup"
                cat_color = "blue" if root_inv.category == InvoiceCategory.SALES else "orange"
                currency = root_inv.currency

                self.data_table.rows.append(
                    ft.DataRow(cells=[
                        ft.DataCell(ft.Text(cat_text, color=cat_color, weight="bold")),
                        ft.DataCell(ft.Column([
                            ft.Text(display_number, weight="bold"),
                            ft.Text(f"{root_inv.date_issue.strftime('%Y-%m-%d')}", size=10, color="grey")
                        ], spacing=2, alignment=ft.MainAxisAlignment.CENTER)),
                        ft.DataCell(ft.Text(root_inv.contractor.name if root_inv.contractor else "Brak")),
                        ft.DataCell(ft.Row([
                            ft.Text(currency), 
                            ft.Text(f"{total_gross_group:.2f}")
                        ])),
                        ft.DataCell(ft.Text(f"{total_paid_group:.2f}")),
                        ft.DataCell(ft.Text(f"{remaining_group:.2f}", color=status_color, weight="bold")),
                        ft.DataCell(ft.Container(content=ft.Text(status_text, color="white", size=12), bgcolor=status_color, padding=5, border_radius=5)),
                        ft.DataCell(ft.IconButton(
                            icon=ft.Text("💳"),
                            tooltip="Rozlicz całość (wątek)", 
                            on_click=lambda e, rid=root_id, rem=remaining_group: self.open_group_payment_dialog(rid, rem)
                        ))
                    ])
                )
            
            self.update()
        except Exception as e:
            print(f"Błąd rozliczeń: {e}")
            import traceback
            traceback.print_exc()
        finally:
            db.close()

    def open_group_payment_dialog(self, root_id, remaining_val):
        db = next(get_db())
        root_inv = db.query(Invoice).filter(Invoice.id == root_id).first()
        
        # Domyślna kwota to saldo grupy
        # Jeśli ujemne (zwrot), to też wpisujemy ujemnie? 
        # Tak, paid_amount może spadać (zwrot) lub trzeba to obsłużyć inaczej. 
        # Tutaj przyjęto konwencję: paid_amount rośnie. Więc zwrot = ???
        # Jeśli saldo jest ujemne (-200), to znaczy że klient ma nadpłatę. Zwrot pieniędzy klientowi to zmniejszenie paid_amount czy co?
        # NIE. Zwrot pieniędzy to transakcja finansowa. 
        
        # Uproszczenie: System rejestruje wpłaty OD klienta. 
        # Jeśli remaining < 0, to znaczy że musimy ODDAĆ. Jeśli oddamy, to wpłata klienta (netto) maleje? 
        # Czy rejestrujemy wypłatę?
        # Niech pole pozwala wpisać wartość ujemną jako "zwrot".
        
        payment_amount_field = ft.TextField(label="Kwota operacji", value=f"{remaining_val:.2f}", width=150)
        
        def save_payment(e):
            try:
                val = float(payment_amount_field.value)
                db_local = next(get_db())
                inv = db_local.query(Invoice).filter(Invoice.id == root_id).first()
                if inv:
                    # Dopisz do faktury matki (najprościej)
                    inv.paid_amount += val
                    
                    # Logika is_paid tylko dla matki (orientacyjnie),
                    # ale ważniejszy jest status grupy wyliczany dynamicznie.
                    if inv.paid_amount >= inv.total_gross:
                        inv.is_paid = True
                    else:
                        inv.is_paid = False
                        
                    db_local.commit()
                db_local.close()
                dlg.open = False
                self.page.update()
                self.load_data()
            except ValueError:
                pass

        dlg = ft.AlertDialog(
            title=ft.Text(f"Rozliczenie: {root_inv.number if root_inv else '?'}", size=20),
            content=ft.Column([
                ft.Text("Rozliczasz grupę (faktura pierwotna + korekty)."),
                ft.Text(f"Saldo grupy: {remaining_val:.2f} (użyj minusa dla zwrotu)"),
                payment_amount_field,
            ], height=150),
            actions=[
                ft.TextButton("Anuluj", on_click=lambda e: setattr(dlg, 'open', False) or self.page.update()),
                ft.ElevatedButton("Zapisz", on_click=save_payment)
            ]
        )
        self.page.overlay.append(dlg)
        dlg.open = True
        self.page.update()
        db.close()

    def _unused_legacy_dialog(self):
       pass