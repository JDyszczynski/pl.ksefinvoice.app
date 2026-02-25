from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, 
                             QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QLabel,
                             QMessageBox, QAbstractItemView)
from PySide6.QtCore import Qt, QSettings
from database.engine import get_db
from database.models import Product
from gui_qt.utils import safe_restore_geometry, save_geometry

class ProductSelector(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Wybierz Produkt")
        
        safe_restore_geometry(self, "productSelectorGeometry", default_percent_w=0.6, default_percent_h=0.6, min_w=600, min_h=400)

        self.selected_product = None
        self.db = next(get_db())
        
        self.init_ui()
        self.load_products()

    def done(self, r):
        save_geometry(self, "productSelectorGeometry")
        super().done(r)
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Search
        search_lay = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Szukaj produktu...")
        self.search_edit.textChanged.connect(self.filter_products)
        search_lay.addWidget(QLabel("Szukaj:"))
        search_lay.addWidget(self.search_edit)
        layout.addLayout(search_lay)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Nazwa", "Indeks/SKU", "Cena Netto", "JM"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self.select_product)
        layout.addWidget(self.table)
        
        # Buttons
        btn_box = QHBoxLayout()
        
        # New Product Button
        self.add_btn = QPushButton("+ Dodaj nowy towar")
        self.add_btn.clicked.connect(self.add_new_product)
        btn_box.addWidget(self.add_btn)
        
        # Standard buttons
        self.select_btn = QPushButton("Wybierz")
        self.select_btn.clicked.connect(self.select_product)
        self.cancel_btn = QPushButton("Anuluj")
        self.cancel_btn.clicked.connect(self.reject)
        
        btn_box.addStretch()
        btn_box.addWidget(self.cancel_btn)
        btn_box.addWidget(self.select_btn)
        layout.addLayout(btn_box)

    def add_new_product(self):
        from gui_qt.warehouse_view import ProductDialog
        dlg = ProductDialog(self)
        if dlg.exec():
            data = dlg.get_data()
            try:
                new_prod = Product(**data)
                self.db.add(new_prod)
                self.db.commit()
                self.db.refresh(new_prod)
                
                # Refresh list
                self.search_edit.clear()
                self.load_products()
                
                # Find the new product in table to verify and select
                for r in range(self.table.rowCount()):
                    pid = self.table.item(r, 0).data(Qt.UserRole)
                    if pid == new_prod.id:
                        self.table.selectRow(r)
                        self.selected_product = new_prod
                        # Auto-select and close
                        self.accept()
                        break
                        
            except Exception as e:
                self.db.rollback()
                QMessageBox.critical(self, "Błąd", str(e))

    def load_products(self):
        self.products = self.db.query(Product).all()
        self.update_table(self.products)

    def filter_products(self, text):
        text = text.lower()
        filtered = [p for p in self.products if text in p.name.lower() or (p.sku and text in p.sku.lower())]
        self.update_table(filtered)

    def update_table(self, products):
        self.table.setRowCount(0)
        for p in products:
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            self.table.setItem(row, 0, QTableWidgetItem(p.name))
            self.table.setItem(row, 1, QTableWidgetItem(p.sku or ""))
            self.table.setItem(row, 2, QTableWidgetItem(f"{p.net_price:.2f}"))
            self.table.setItem(row, 3, QTableWidgetItem(p.unit))
            
            # Store ID in first item
            self.table.item(row, 0).setData(Qt.UserRole, p.id)

    def select_product(self):
        row = self.table.currentRow()
        if row >= 0:
            pid = self.table.item(row, 0).data(Qt.UserRole)
            self.selected_product = self.db.query(Product).filter(Product.id == pid).first()
            self.accept()
        else:
            self.reject()

from PySide6.QtWidgets import QAbstractItemView
