from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableView, QHeaderView, 
                             QPushButton, QAbstractItemView, QMessageBox, QLabel, QMenu, 
                             QDialog, QFormLayout, QLineEdit, QComboBox, QDialogButtonBox,
                             QRadioButton, QButtonGroup, QFrame)
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PySide6.QtGui import QAction
from database.engine import get_db
from database.models import Product, VatRate, InvoiceItem, CompanyConfig

class ProductTableModel(QAbstractTableModel):
    def __init__(self, products=None):
        super().__init__()
        self.products = products or []
        self.headers = ["Nazwa", "SKU", "PKWiU", "Cena Netto", "VAT", "Jednostka"]

    def rowCount(self, parent=QModelIndex()):
        return len(self.products)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid(): return None
        p = self.products[index.row()]
        col = index.column()
        
        if role == Qt.DisplayRole:
            if col == 0: return p.name
            elif col == 1: return p.sku or "-"
            elif col == 2: return p.pkwiu or "-"
            elif col == 3: return f"{p.net_price:.2f}"
            elif col == 4: 
                # Display VAT as percentage
                return f"{int(p.vat_rate*100)}%" if p.vat_rate is not None else "0%"
            elif col == 5: return p.unit
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.headers[section]
        return None
    
    def update_data(self, new_data):
        self.beginResetModel()
        self.products = new_data
        self.endResetModel()

    def get_product(self, row):
        return self.products[row]

class ProductDialog(QDialog):
    def __init__(self, parent=None, product_model=None):
        super().__init__(parent)
        self.setWindowTitle("Dane towaru")
        self.setModal(True)
        self.resize(500, 400)
        self.product = product_model
        # Pobierz stawki
        db = next(get_db())
        self.config = db.query(CompanyConfig).first()
        self.rates = db.query(VatRate).all()
        db.close()
        
        self.init_ui()

    def init_ui(self):
        layout = QFormLayout(self)
        
        is_edit = self.product is not None
        is_vat_payer = True
        if self.config and not self.config.is_vat_payer:
             is_vat_payer = False
        
        self.name_edit = QLineEdit(self.product.name if is_edit else "")
        self.sku_edit = QLineEdit(self.product.sku if is_edit else "")
        # Add PKWiU field
        self.pkwiu_edit = QLineEdit(self.product.pkwiu if is_edit else "")
        
        self.unit_edit = QLineEdit(self.product.unit if is_edit else "szt.")
        
        self.purchase_net_edit = QLineEdit(str(self.product.purchase_net_price) if is_edit else "0.00")
        
        # Markup/Margin
        self.markup_edit = QLineEdit("0.00") # Narzut
        self.markup_edit.setPlaceholderText("Narzut %")
        self.margin_edit = QLineEdit("0.00") # Marża
        self.margin_edit.setPlaceholderText("Marża %")
        
        # VAT Combo
        self.vat_combo = QComboBox()
        # Default options if DB empty
        if not self.rates:
            default_rates = [("23%", 0.23), ("8%", 0.08), ("5%", 0.05), ("0%", 0.0)]
        else:
            default_rates = [(r.name, r.rate) for r in self.rates]
            
        for name, rate in default_rates:
            self.vat_combo.addItem(name, rate)
            
        # Select current vat
        current_rate = self.product.vat_rate if is_edit else 0.23
        # Simple match
        idx = -1
        for i in range(self.vat_combo.count()):
             val = self.vat_combo.itemData(i)
             if abs(val - current_rate) < 0.001:
                 idx = i
                 break
        if idx >= 0: self.vat_combo.setCurrentIndex(idx)
        else: self.vat_combo.setCurrentIndex(0) # Logic fallback
        
        self.vat_combo.currentIndexChanged.connect(lambda: self.recalculate("vat"))

        # Price Fields AND Mode Logic
        self.mode_group = QButtonGroup(self)
        self.mode_net = QRadioButton("Od Netto")
        self.mode_gross = QRadioButton("Od Brutto")
        self.mode_group.addButton(self.mode_net)
        self.mode_group.addButton(self.mode_gross)
        
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(self.mode_net)
        mode_layout.addWidget(self.mode_gross)
        
        is_gross = self.product.is_gross_mode if is_edit else False
        if is_gross: self.mode_gross.setChecked(True)
        else: self.mode_net.setChecked(True)
        
        self.mode_group.buttonClicked.connect(self.on_mode_change)

        self.sales_net_edit = QLineEdit(f"{self.product.net_price:.2f}" if is_edit else "0.00")
        self.sales_gross_edit = QLineEdit(f"{self.product.gross_price:.2f}" if is_edit else "0.00")
        
        self.sales_net_edit.textEdited.connect(lambda: self.recalculate("net"))
        self.sales_gross_edit.textEdited.connect(lambda: self.recalculate("gross"))
        
        self.purchase_net_edit.textEdited.connect(lambda: self.recalculate("purchase"))
        self.markup_edit.textEdited.connect(lambda: self.recalculate("markup"))
        self.margin_edit.textEdited.connect(lambda: self.recalculate("margin"))

        # Kod GTU
        self.gtu_combo = QComboBox()
        self.gtu_combo.addItem("Brak", None)
        for i in range(1, 14):
            code = f"GTU_{i:02d}"
            self.gtu_combo.addItem(code, code)
        
        # Set current GTU
        current_gtu = getattr(self.product, 'gtu', None)
        if current_gtu:
             idx = self.gtu_combo.findText(current_gtu)
             if idx >= 0: self.gtu_combo.setCurrentIndex(idx)

        layout.addRow("Nazwa:", self.name_edit)
        layout.addRow("SKU:", self.sku_edit)
        layout.addRow("PKWiU (lub CN/PKOB):", self.pkwiu_edit)
        
        if is_vat_payer:
             layout.addRow("Kod GTU:", self.gtu_combo)
             
        layout.addRow("Jednostka:", self.unit_edit)
        layout.addRow("Cena Zakupu (Netto):", self.purchase_net_edit)
        layout.addRow("Narzut (%):", self.markup_edit)
        layout.addRow("Marża (%):", self.margin_edit)
        layout.addRow("Stawka VAT:", self.vat_combo)
        layout.addRow("Tryb wyliczania:", mode_layout)
        layout.addRow("Sprzedaż Netto:", self.sales_net_edit)
        layout.addRow("Sprzedaż Brutto:", self.sales_gross_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        
        self.on_mode_change() # Apply readonly state
        # Initial calc of margin/markup based on loaded values
        self.recalculate("init") 

    def on_mode_change(self):
        if self.mode_net.isChecked():
            self.sales_net_edit.setReadOnly(False)
            self.sales_gross_edit.setReadOnly(True)
            self.recalculate("vat") # Re-base on net
        else:
            self.sales_net_edit.setReadOnly(True)
            self.sales_gross_edit.setReadOnly(False)
            self.recalculate("vat") # Re-base on gross

    def recalculate(self, source):
        try:
            vat_rate = self.vat_combo.currentData()
        except: vat_rate = 0.0

        try:
            net = float(self.sales_net_edit.text().replace(",", ".") or 0)
        except: net = 0.0
            
        try:
            gross = float(self.sales_gross_edit.text().replace(",", ".") or 0)
        except: gross = 0.0
        
        try:
            p_price = float(self.purchase_net_edit.text().replace(",", ".") or 0)
        except: p_price = 0.0

        try:
            markup = float(self.markup_edit.text().replace(",", ".") or 0)
        except: markup = 0.0
        
        try:
            margin = float(self.margin_edit.text().replace(",", ".") or 0)
        except: margin = 0.0

        # Purchase to Sales copy logic (Auto-fill sales price from purchase price if sales is empty or untouched in ADD mode)
        if source == "purchase":
             is_empty = (net == 0 and gross == 0)
             # In Add New Mode, if user hasn't manually touched sales fields, keep syncing with purchase
             # But check if we are not editing markup/margin
             is_clean_add = (self.product is None and not self.sales_net_edit.isModified() and not self.sales_gross_edit.isModified())
             
             if is_empty or is_clean_add:
                  net = p_price
                  self.sales_net_edit.setText(f"{net:.2f}")
                  # Force calc rest as if net changed
                  source = "net" 
        
        # Logic for Markup/Margin Editing
        if source == "markup":
            # Narzut: (S - P) / P * 100 => S = P * (1 + Narzut/100)
             if p_price > 0:
                 net = p_price * (1 + markup / 100.0)
                 self.sales_net_edit.setText(f"{net:.2f}")
                 source = "net" # continue to calc gross
             else:
                 pass # Cannot calc sales from 0 purchase based on markup

        elif source == "margin":
            # Marża: (S - P) / S * 100 => S = P / (1 - Marża/100)
            if p_price > 0 and margin < 100:
                net = p_price / (1 - margin / 100.0)
                self.sales_net_edit.setText(f"{net:.2f}")
                source = "net"

        if self.mode_net.isChecked():
            # Base is Net
            if source == "net" or source == "vat" or source == "purchase" or source == "init":
                gross = net * (1 + vat_rate)
                self.sales_gross_edit.setText(f"{gross:.2f}")
        else:
            # Base is Gross
            if source == "gross" or source == "vat":
                net = gross / (1 + vat_rate)
                self.sales_net_edit.setText(f"{net:.2f}")
        
        # Final pass: Recalculate Markup/Margin based on final Net and Purchase
        # But ONLY if we didn't just edit them directly to avoid fighting rounding errors while typing
        if source != "markup" and source != "margin":
             # Calc Markup
             if p_price > 0:
                 new_markup = ((net - p_price) / p_price) * 100.0
             else:
                 new_markup = 0.0
             
             # Calc Margin
             if net > 0:
                 new_margin = ((net - p_price) / net) * 100.0
             else:
                 new_margin = 0.0
             
             self.markup_edit.setText(f"{new_markup:.2f}")
             self.margin_edit.setText(f"{new_margin:.2f}")
             
        elif source == "markup":
             # Update Margin only
             if net > 0:
                 new_margin = ((net - p_price) / net) * 100.0
                 self.margin_edit.setText(f"{new_margin:.2f}")
                 
        elif source == "margin":
             # Update Markup only
             if p_price > 0:
                 new_markup = ((net - p_price) / p_price) * 100.0
                 self.markup_edit.setText(f"{new_markup:.2f}")

    def get_data(self):
        return {
            "name": self.name_edit.text(),
            "sku": self.sku_edit.text(),
            "pkwiu": self.pkwiu_edit.text(),
            "gtu": self.gtu_combo.currentText() if self.gtu_combo.currentText() != "Brak" else None,
            "unit": self.unit_edit.text(),
            "purchase_net_price": float(self.purchase_net_edit.text().replace(",", ".") or 0) if self.purchase_net_edit.text() else 0.0,
            "vat_rate": self.vat_combo.currentData(),
            "net_price": float(self.sales_net_edit.text().replace(",", ".") or 0) if self.sales_net_edit.text() else 0.0,
            "gross_price": float(self.sales_gross_edit.text().replace(",", ".") or 0) if self.sales_gross_edit.text() else 0.0,
            "is_gross_mode": self.mode_gross.isChecked()
        }

class WarehouseView(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.load_products()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Toolbar
        tools = QHBoxLayout()
        title = QLabel("Towary")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        tools.addWidget(title)
        
        add_btn = QPushButton("Dodaj towar")
        add_btn.clicked.connect(self.open_add_dialog)
        
        tools.addStretch()
        tools.addWidget(add_btn)
        layout.addLayout(tools)

        # Table
        self.table = QTableView()
        self.model = ProductTableModel()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.doubleClicked.connect(self.open_edit_dialog)
        
        # Context Menu
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.open_context_menu)

        layout.addWidget(self.table)
        
    def load_products(self):
        db = next(get_db())
        try:
            data = db.query(Product).all()
            self.model.update_data(data)
        finally:
            db.close()

    def open_add_dialog(self):
        dlg = ProductDialog(self)
        if dlg.exec():
            data = dlg.get_data()
            self.save_product(data)

    def open_edit_dialog(self, index):
        if not index.isValid(): return
        p = self.model.get_product(index.row())
        dlg = ProductDialog(self, p)
        if dlg.exec():
            data = dlg.get_data()
            self.save_product(data, p.id)

    def save_product(self, data, pid=None):
        db = next(get_db())
        try:
            if pid:
                p = db.query(Product).filter(Product.id == pid).first()
                if p:
                    for k, v in data.items():
                        setattr(p, k, v)
                    db.commit()
            else:
                p = Product(**data)
                db.add(p)
                db.commit()
            self.load_products()
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
        del_action.triggered.connect(lambda: self.delete_product(idx))
        
        menu.addAction(edit_action)
        menu.addAction(del_action)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def delete_product(self, index):
        p = self.model.get_product(index.row())
        
        db = next(get_db())
        try:
             # Check usage by name logic as per original Flet code
             cnt = db.query(InvoiceItem).filter(InvoiceItem.product_name == p.name).count()
        finally:
             db.close()
             
        if cnt > 0:
            QMessageBox.warning(self, "Błąd", f"Nie można usunąć: Towar użyty w {cnt} pozycjach!")
            return

        res = QMessageBox.question(self, "Potwierdź", f"Czy usunąć towar {p.name}?", QMessageBox.Yes | QMessageBox.No)
        if res == QMessageBox.Yes:
            db = next(get_db())
            try:
                db.query(Product).filter(Product.id == p.id).delete()
                db.commit()
            finally:
                db.close()
            self.load_products()
