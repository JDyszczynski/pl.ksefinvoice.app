from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableView, QHeaderView, 
                             QPushButton, QAbstractItemView, QMessageBox, QLabel, QMenu, 
                             QDialog, QFormLayout, QLineEdit, QCheckBox, QDialogButtonBox,
                             QInputDialog)
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSettings
from PySide6.QtGui import QAction
from database.engine import get_db
from database.models import Contractor, Invoice
from gus.client import GusClient
from vies.client import ViesClient
from mf_whitelist.client import MfWhitelistClient
from gui_qt.utils import safe_restore_geometry, save_geometry
import re

class ContractorTableModel(QAbstractTableModel):
    def __init__(self, contractors=None):
        super().__init__()
        self.contractors = contractors or []
        self.headers = ["NIP", "Nazwa", "Adres", "Miasto", "Email", "Telefon"]

    def rowCount(self, parent=QModelIndex()):
        return len(self.contractors)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid(): return None
        c = self.contractors[index.row()]
        col = index.column()
        
        if role == Qt.DisplayRole:
            if col == 0: return c.nip
            elif col == 1: return c.name
            elif col == 2: return c.address
            elif col == 3: return c.city
            elif col == 4: return c.email
            elif col == 5: return c.phone
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.headers[section]
        return None
    
    def update_data(self, new_data):
        self.beginResetModel()
        self.contractors = new_data
        self.endResetModel()

    def get_contractor(self, row):
        return self.contractors[row]

class ContractorDialog(QDialog):
    def __init__(self, parent=None, contractor_data=None):
        super().__init__(parent)
        self.setWindowTitle("Dane kontrahenta")
        self.setModal(True)
        
        safe_restore_geometry(self, "contractorDialogGeometry", default_percent_w=0.4, default_percent_h=0.6, min_w=500, min_h=400)

        self.data = contractor_data or {}
        self.mf_client = MfWhitelistClient()
        self.vies_client = ViesClient()
        self.init_ui()

    def done(self, r):
        save_geometry(self, "contractorDialogGeometry")
        super().done(r)

    def init_ui(self):
        layout = QFormLayout(self)
        
        # Fields
        self.nip_edit = QLineEdit(self.data.get("nip", ""))
        
        # Person vs Company Logic
        self.is_person_cb = QCheckBox("Osoba Fizyczna")
        is_person_val = self.data.get("is_person", False)
        self.is_person_cb.setChecked(is_person_val)
        self.is_person_cb.toggled.connect(self.toggle_person_mode)

        # Name containers
        self.name_edit = QLineEdit(self.data.get("name", "")) # Default for Company
        
        self.first_name_edit = QLineEdit()
        self.last_name_edit = QLineEdit()
        
        # If is_person, split name to get initial values
        if is_person_val and self.data.get("name"):
            full = self.data.get("name", "").strip()
            # Simplistic split
            parts = full.split(' ', 1)
            self.first_name_edit.setText(parts[0])
            if len(parts) > 1:
                self.last_name_edit.setText(parts[1])

        self.address_edit = QLineEdit(self.data.get("address", ""))
        self.city_edit = QLineEdit(self.data.get("city", ""))
        self.postal_edit = QLineEdit(self.data.get("postal_code", ""))
        self.phone_edit = QLineEdit(self.data.get("phone", ""))
        self.email_edit = QLineEdit(self.data.get("email", ""))
        self.country_edit = QLineEdit(self.data.get("country", "Polska"))
        self.country_code_edit = QLineEdit(self.data.get("country_code", "PL"))
        
        self.vat_cb = QCheckBox("Czynny podatnik VAT")
        self.vat_cb.setChecked(self.data.get("is_vat_payer", True))
        
        # MF Status Display
        self.mf_status_lbl = QLabel(self.data.get("mf_status", "Nieznany"))
        if self.data.get("mf_status") == "Zwolniony" or self.data.get("mf_status") == "Nieznany":
             self.mf_status_lbl.setStyleSheet("color: red; font-weight: bold;")
        elif self.data.get("mf_status") == "Czynny":
             self.mf_status_lbl.setStyleSheet("color: green; font-weight: bold;")
        
        self.vat_ue_cb = QCheckBox("Podatnik VAT UE")
        self.vat_ue_cb.setChecked(self.data.get("is_vat_ue", False))

        # Buttons in a horizontal layout for verification
        ver_layout = QHBoxLayout()
        verify_mf_btn = QPushButton("Weryfikuj MF")
        verify_mf_btn.clicked.connect(self.verify_mf)
        
        verify_vies_btn = QPushButton("Weryfikuj VIES")
        verify_vies_btn.clicked.connect(self.verify_vies)
        
        ver_layout.addWidget(verify_mf_btn)
        ver_layout.addWidget(verify_vies_btn)

        layout.addRow("NIP:", self.nip_edit)
        layout.addRow("", self.is_person_cb)
        
        # Dynamic Rows
        self.lbl_name = QLabel("Nazwa:")
        self.lbl_first = QLabel("Imię:")
        self.lbl_last = QLabel("Nazwisko:")

        layout.addRow(self.lbl_name, self.name_edit)
        layout.addRow(self.lbl_first, self.first_name_edit)
        layout.addRow(self.lbl_last, self.last_name_edit)

        layout.addRow("Adres:", self.address_edit)
        layout.addRow("Miasto:", self.city_edit)
        layout.addRow("Kod pocztowy:", self.postal_edit)
        layout.addRow("Telefon:", self.phone_edit)
        layout.addRow("Email:", self.email_edit)
        layout.addRow("Kraj:", self.country_edit)
        layout.addRow("Kod Kraju:", self.country_code_edit)
        layout.addRow("", self.vat_cb)
        layout.addRow("Status MF:", self.mf_status_lbl)
        layout.addRow("", self.vat_ue_cb)
        layout.addRow("Weryfikacja:", ver_layout)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept_data) # Custom accept to join names
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        
        self.toggle_person_mode() # Set initial state

    def toggle_person_mode(self):
        is_person = self.is_person_cb.isChecked()
        if is_person:
             self.name_edit.hide()
             self.lbl_name.hide()
             self.first_name_edit.show()
             self.lbl_first.show()
             self.last_name_edit.show()
             self.lbl_last.show()
        else:
             self.name_edit.show()
             self.lbl_name.show()
             self.first_name_edit.hide()
             self.lbl_first.hide()
             self.last_name_edit.hide()
             self.lbl_last.hide()

    def accept_data(self):
        # Join name if person
        is_person = self.is_person_cb.isChecked()
        if is_person:
            first = self.first_name_edit.text().strip()
            last = self.last_name_edit.text().strip()
            full_name = f"{first} {last}".strip()
            
            # Simple fallback if only one is provided
            if not full_name:
                # If required? 
                pass
            
            # Update the hidden name field or directly data
            self.data['name'] = full_name
        else:
            self.data['name'] = self.name_edit.text().strip()
        
        self.data['is_person'] = is_person
        self.accept()

    def get_data(self):
        # Override data retrieval logic from form to self.data
        # Actually standard practice is read fields here.
        # But I updated self.data in accept_data for Name.
        # So populate others back to self.data
        self.data['nip'] = self.nip_edit.text()
        # name and is_person already set in accept_data
        self.data['address'] = self.address_edit.text()
        self.data['city'] = self.city_edit.text()
        self.data['postal_code'] = self.postal_edit.text()
        self.data['phone'] = self.phone_edit.text()
        self.data['email'] = self.email_edit.text()
        self.data['country'] = self.country_edit.text()
        self.data['country_code'] = self.country_code_edit.text()
        self.data['is_vat_payer'] = self.vat_cb.isChecked()
        self.data['is_vat_ue'] = self.vat_ue_cb.isChecked()
        return self.data

    def verify_mf(self):
        nip = self.nip_edit.text().replace("-", "").strip()
        if not nip: return
        try:
            res = self.mf_client.check_nip(nip)
            if res.get('success'):
                status = res.get('status', 'Nieznany')
                self.mf_status_lbl.setText(status)
                if status in ["Zwolniony", "Nieznany"]:
                     self.mf_status_lbl.setStyleSheet("color: red; font-weight: bold;")
                elif status == "Czynny":
                     self.mf_status_lbl.setStyleSheet("color: green; font-weight: bold;")
                
                msg = f"Status: {status}\n"
                
                if res.get('active') is not None:
                     self.vat_cb.setChecked(res.get('active'))
                
                if res.get('name'):
                    self.name_edit.setText(res['name'])
                    msg += f"Nazwa zaktualizowana.\n"
                    
                # MF Address Logic
                if res.get('residence_address'):
                    msg += "Adres zaktualizowany (z MF).\n"
                    if not self.address_edit.text(): # Only if empty or always? Let's overwrite? usually verification -> overwrite
                         mf_addr = res["residence_address"]
                         self.address_edit.setText(mf_addr)
                         parsed = False
                         if "," in mf_addr:
                             parts = mf_addr.rsplit(",", 1)
                             if len(parts) == 2:
                                 self.address_edit.setText(parts[0].strip())
                                 zip_city = parts[1].strip()
                                 match = re.match(r'^(\d{2}-\d{3})\s+(.+)$', zip_city)
                                 if match:
                                     self.postal_edit.setText(match.group(1))
                                     self.city_edit.setText(match.group(2))
                                     parsed = True
                         if not parsed:
                             self.address_edit.setText(mf_addr)
                
                if res.get('account_numbers'):
                    accs = "\n".join(res['account_numbers'][:3]) # show max 3
                    if len(res['account_numbers']) > 3: accs += "\n..."
                    msg += f"\nKonta bankowe:\n{accs}"
                
                QMessageBox.information(self, "MF Whitelist", msg)
            else:
                QMessageBox.warning(self, "MF Whitelist", f"Błąd: {res.get('error')}")
                
        except Exception as e:
            QMessageBox.warning(self, "Błąd", str(e))

    def verify_vies(self):
        nip = self.nip_edit.text().replace("-", "").strip()
        cc = self.country_code_edit.text().strip().upper() or "PL"
        if not nip: return
        
        try:
            res = self.vies_client.check_vat(cc, nip)
            if res.get('success'):
                valid = res.get('valid', False)
                self.vat_ue_cb.setChecked(valid)
                msg = f"VAT UE Ważny: {valid}\n"
                
                if valid:
                    if res.get('name'): 
                        self.name_edit.setText(res['name'])
                    if res.get('address'):
                        addr_raw = res['address']
                        parts = [p.strip() for p in addr_raw.split('\n') if p.strip()]
                        
                        parsed = False
                        if cc == 'PL' and len(parts) >= 2:
                            zip_city = parts[-1]
                            match = re.match(r'^(\d{2}-\d{3})\s+(.+)$', zip_city)
                            if match:
                                self.postal_edit.setText(match.group(1))
                                self.city_edit.setText(match.group(2))
                                self.address_edit.setText(", ".join(parts[:-1]))
                                parsed = True
                        
                        if not parsed:
                            self.address_edit.setText(addr_raw.replace("\n", ", "))
                        msg += "Dane adresowe zaktualizowane."
                        
                QMessageBox.information(self, "VIES", msg)
            else:
                QMessageBox.warning(self, "VIES", f"Błąd: {res.get('error')}")

        except Exception as e:
             QMessageBox.warning(self, "Błąd", str(e))

    def get_data(self):
        return {
            "nip": self.nip_edit.text(),
            "name": self.name_edit.text(),
            "address": self.address_edit.text(),
            "city": self.city_edit.text(),
            "postal_code": self.postal_edit.text(),
            "phone": self.phone_edit.text(),
            "email": self.email_edit.text(),
            "country": self.country_edit.text(),
            "country_code": self.country_code_edit.text(),
            "is_vat_payer": self.vat_cb.isChecked(),
            "is_vat_ue": self.vat_ue_cb.isChecked()
        }

class ContractorView(QWidget):
    def __init__(self):
        super().__init__()
        self.mf_client = MfWhitelistClient()
        self.vies_client = ViesClient()
        self.init_ui()
        self.load_contractors()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Toolbar
        tools = QHBoxLayout()
        title = QLabel("Kontrahenci")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        tools.addWidget(title)
        
        download_btn = QPushButton("Pobierz i wstaw")
        download_btn.clicked.connect(self.open_online_search)
        
        add_btn = QPushButton("Dodaj ręcznie")
        add_btn.clicked.connect(self.open_add_dialog)
        
        tools.addStretch()
        tools.addWidget(download_btn)
        tools.addWidget(add_btn)
        layout.addLayout(tools)

        # Table
        self.table = QTableView()
        self.model = ContractorTableModel()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.doubleClicked.connect(self.open_edit_dialog)
        
        # Context Menu
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.open_context_menu)

        layout.addWidget(self.table)
        
    def load_contractors(self):
        db = next(get_db())
        try:
            data = db.query(Contractor).all()
            self.model.update_data(data)
        finally:
            db.close()

    def open_online_search(self):
        nip, ok = QInputDialog.getText(self, "Pobierz dane (MF/VIES)", "Podaj NIP (bez kresek):")
        if not (ok and nip): return
        
        nip = nip.replace("-", "").replace(" ", "").strip()
        data = {}
        found = False

        # 1. MF Whitelist (Poland)
        try:
            res = self.mf_client.check_nip(nip)
            if res.get('success'):
                name = res.get('name')
                if name:
                    data['nip'] = nip
                    data['name'] = name
                    data['mf_status'] = res.get('status', '')
                    data['is_vat_payer'] = res.get('active', False)
                    found = True
                    
                    # Parse Address MF
                    if res.get('residence_address'):
                        addr = res['residence_address']
                        if "," in addr:
                             parts = addr.rsplit(",", 1)
                             if len(parts) == 2:
                                 data['address'] = parts[0].strip()
                                 zip_city = parts[1].strip()
                                 match = re.match(r'^(\d{2}-\d{3})\s+(.+)$', zip_city)
                                 if match:
                                     data['postal_code'] = match.group(1)
                                     data['city'] = match.group(2)
                                 else:
                                     data['city'] = zip_city
                             else:
                                 data['address'] = addr
                        else:
                             data['address'] = addr
        except Exception as e:
            print(f"MF Error: {e}")

        # 2. VIES (Europe) - if not found in MF implies logic or try VIES anyway? 
        # Usually users might use EU NIPs.
        if not found:
            try:
                # Basic country detection
                cc = "PL"
                id_val = nip
                if not nip[0].isdigit():
                    cc = nip[:2]
                    id_val = nip[2:]
                
                res = self.vies_client.check_vat(cc, id_val)
                if res.get('success') and res.get('valid'):
                    data['nip'] = nip
                    data['country_code'] = cc
                    data['name'] = res.get('name', '')
                    data['is_vat_ue'] = True
                    found = True
                    
                    # Address VIES
                    if res.get('address'):
                        # Basic VIES address parsing
                        lines = [x.strip() for x in res['address'].split('\n') if x.strip()]
                        if lines:
                            if len(lines) >= 2:
                                data['address'] = ", ".join(lines[:-1])
                                data['city'] = lines[-1] # Assumption
                            else:
                                data['address'] = lines[0]
            except Exception as e:
                print(f"VIES Error: {e}")

        if found:
            self.show_contractor_dialog(data)
        else:
            QMessageBox.warning(self, "Brak danych", "Nie znaleziono danych kontrahenta w rejestrach MF (Biała Lista) ani VIES.")

    def open_add_dialog(self):
        self.show_contractor_dialog()

    def open_edit_dialog(self, index):
        if not index.isValid(): return
        c = self.model.get_contractor(index.row())
        data = {
            "id": c.id,
            "nip": c.nip, "name": c.name, "address": c.address, "city": c.city,
            "postal_code": c.postal_code, "phone": c.phone, "email": c.email,
            "country": c.country, "country_code": c.country_code,
            "is_vat_payer": c.is_vat_payer, "is_vat_ue": c.is_vat_ue
        }
        self.show_contractor_dialog(data, is_edit=True)

    def show_contractor_dialog(self, data=None, is_edit=False):
        dlg = ContractorDialog(self, data)
        if dlg.exec():
            new_data = dlg.get_data()
            self.save_contractor(new_data, data.get("id") if data and is_edit else None)

    def save_contractor(self, data, cid=None):
        db = next(get_db())
        try:
            if cid:
                c = db.query(Contractor).filter(Contractor.id == cid).first()
                if c:
                    for k, v in data.items():
                        setattr(c, k, v)
                    db.commit()
            else:
                existing = db.query(Contractor).filter(Contractor.nip == data["nip"]).first()
                if existing:
                    QMessageBox.warning(self, "Duplikat", "Kontrahent z tym NIP już istnieje.")
                    return
                # Sanitize empty strings to None if needed, or keep as string
                c = Contractor(**data)
                db.add(c)
                db.commit()
            self.load_contractors()
        except Exception as e:
            QMessageBox.critical(self, "Błąd zapisu", str(e))
        finally:
            db.close()

    def open_context_menu(self, pos):
        idx = self.table.indexAt(pos)
        if not idx.isValid(): return
        
        menu = QMenu()
        edit_action = QAction("Edytuj", self)
        edit_action.triggered.connect(lambda: self.open_edit_dialog(idx))
        del_action = QAction("Usuń", self)
        del_action.triggered.connect(lambda: self.delete_contractor(idx))
        
        menu.addAction(edit_action)
        menu.addAction(del_action)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def delete_contractor(self, index):
        c = self.model.get_contractor(index.row())
        
        # Check usage
        db = next(get_db())
        try:
            # Check for Settlements (PODATEK or INNE)
            # Both PODATEK and INNE are typically manual settlements in this context
            from database.models import InvoiceType
            usage_settlements = db.query(Invoice).filter(
                Invoice.contractor_id == c.id, 
                Invoice.type.in_([InvoiceType.PODATEK, InvoiceType.INNE])
            ).count()
            
            # Check for Invoices (Neither PODATEK nor INNE)
            usage_inv = db.query(Invoice).filter(
                Invoice.contractor_id == c.id,
                ~Invoice.type.in_([InvoiceType.PODATEK, InvoiceType.INNE])
            ).count()
        finally:
            db.close()
        
        if usage_settlements > 0:
             QMessageBox.warning(self, "Błąd", f"Nie można usunąć: Kontrahent przypisany do {usage_settlements} rozliczeń (Podatki/ZUS/Inne).")
             return

        if usage_inv > 0:
            QMessageBox.warning(self, "Błąd", f"Nie można usunąć: Kontrahent przypisany do {usage_inv} faktur.")
            return

        res = QMessageBox.question(self, "Potwierdź", f"Czy usunąć kontrahenta {c.name}?", QMessageBox.Yes | QMessageBox.No)
        if res == QMessageBox.Yes:
            db = next(get_db())
            try:
                db.query(Contractor).filter(Contractor.id == c.id).delete()
                db.commit()
            finally:
                db.close()
            self.load_contractors()