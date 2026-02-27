from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, 
                             QDateEdit, QGroupBox, QFormLayout, QFrame, QMessageBox, 
                             QAbstractItemView, QSizePolicy, QStyledItemDelegate, QTabWidget, QScrollArea,
                             QFileDialog, QDialog, QTextBrowser, QDialogButtonBox)
from PySide6.QtCore import Qt, QDate, QRect
from PySide6.QtGui import QColor, QBrush, QPen
from database.engine import get_db
from database.models import Invoice, InvoiceCategory, Contractor, InvoiceType, CompanyConfig, TaxationForm
from logic.revenue_service import RevenueService
from logic.jpk_service import JpkService
import datetime
import calendar
import random
import string

class BorderRowDelegate(QStyledItemDelegate):
    def __init__(self, color, parent=None):
        super().__init__(parent)
        self.color = color

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        
        if index.data(Qt.UserRole):
            painter.save()
            pen = QPen(self.color)
            pen.setWidth(2)
            painter.setPen(pen)
            
            # Adjust rect to be inside the cell spacing
            rect = option.rect
            # Fix overlap with adjacent cells by pulling in slightly? 
            # Or draw on lines.
            
            # Top
            painter.drawLine(rect.topLeft(), rect.topRight())
            # Bottom
            painter.drawLine(rect.bottomLeft(), rect.bottomRight())
            
            # Left (only if first column)
            if index.column() == 0:
                painter.drawLine(rect.topLeft(), rect.bottomLeft())
                
            # Right (only if last column - col 5)
            if index.column() == 5:
                painter.drawLine(rect.topRight(), rect.bottomRight())
                
            painter.restore()

class DeclarationsView(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.load_annual_data()

    def showEvent(self, event):
        self.load_annual_data()
        super().showEvent(event)
        
    def init_ui(self):
        self.layout = QVBoxLayout(self)
        
        # Header
        header = QHBoxLayout()
        title = QLabel("Deklaracje i Raporty")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()
        self.layout.addLayout(header)
        
        # Tools
        tools = QGroupBox("Filtr Okresu")
        tools_layout = QHBoxLayout()
        
        self.year_combo = QComboBox()
        curr_year = datetime.datetime.now().year
        for y in range(curr_year - 5, curr_year + 5):
            self.year_combo.addItem(str(y))
        self.year_combo.setCurrentText(str(curr_year))
        self.year_combo.currentTextChanged.connect(self.load_annual_data)
        
        btn_refresh = QPushButton("Odśwież")
        btn_refresh.clicked.connect(self.load_annual_data)
        
        tools_layout.addWidget(QLabel("Rok:"))
        tools_layout.addWidget(self.year_combo)
        tools_layout.addWidget(btn_refresh)
        tools_layout.addStretch()
        
        tools.setLayout(tools_layout)
        self.layout.addWidget(tools)
        
        # Tabs Logic
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)
        
        # --- TAB 1: PPE (Ryczałt) ---
        self.tab_ppe = QWidget()
        self.tab_ppe_layout = QVBoxLayout(self.tab_ppe)
        
        self.table_ppe = QTableWidget() # Old self.table
        self.table_ppe.verticalHeader().setVisible(False)
        self.table_ppe.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        # self.table_ppe.setMinimumHeight(450) 
        
        self.tab_ppe_layout.addWidget(self.table_ppe)
        self.tabs.addTab(self.tab_ppe, "Rozliczenie Ryczałtu (PPE)")
        
        # --- TAB 2: VAT Register (Wide Table) ---
        self.tab_vat = QWidget()
        self.tab_vat_layout = QVBoxLayout(self.tab_vat)
        
        self.table_vat = QTableWidget()
        self.table_vat.verticalHeader().setVisible(False)
        self.table_vat.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        
        self.tab_vat_layout.addWidget(self.table_vat)
        self.tabs.addTab(self.tab_vat, "Ewidencja VAT (Sprzedaż i Zakup)")
        
        # --- TAB 3: JPK Declarations ---
        self.tab_jpk = QWidget()
        self.tab_jpk_layout = QVBoxLayout(self.tab_jpk)
        
        # Header for Tab 3 with Help
        jpk_header = QHBoxLayout()
        jpk_header.addWidget(QLabel("<b>Generowanie plików JPK V7 (M/K)</b>"))
        jpk_header.addStretch()
        
        btn_jpk_help = QPushButton("?")
        btn_jpk_help.setFixedWidth(30)
        btn_jpk_help.setToolTip("Instrukcja pól JPK")
        btn_jpk_help.clicked.connect(self.show_jpk_help)
        jpk_header.addWidget(btn_jpk_help)
        
        self.tab_jpk_layout.addLayout(jpk_header)
        
        # Simple list of months for JPK generation
        self.table_jpk = QTableWidget()
        self.table_jpk.setColumnCount(4)
        self.table_jpk.setHorizontalHeaderLabels(["Okres", "Złożenie", "Korekta", "Inne"])
        self.table_jpk.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_jpk.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_jpk.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_jpk.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_jpk.verticalHeader().setVisible(False)
        
        self.tab_jpk_layout.addWidget(self.table_jpk)
        self.tabs.addTab(self.tab_jpk, "Deklaracje JPK")

        # Backward compatibility alias for existing methods calling self.table
        self.table = self.table_ppe
        
    def show_jpk_help(self):
        text = """
        <h3>Struktura JPK_V7 (M/K)</h3>
        <p>Plik JPK_V7 składa się z dwóch części:</p>
        <ul>
            <li><b>Ewidencja:</b> Szczegółowy wykaz wszystkich faktur sprzedaży i zakupu.</li>
            <li><b>Deklaracja:</b> Obliczenie podatku VAT do wpłaty lub zwrotu (odpowiednik dawnej deklaracji VAT-7).</li>
        </ul>
        
        <h4>Kluczowe Pola Deklaracji:</h4>
        <table border="1" cellpadding="4" cellspacing="0">
            <tr><td><b>P_37</b></td><td>Łączna wysokość podstawy opodatkowania (Suma netto sprzedaży)</td></tr>
            <tr><td><b>P_38</b></td><td>Łączna wysokość podatku należnego (VAT od sprzedaży)</td></tr>
            <tr><td><b>P_48</b></td><td>Łączna wysokość podatku naliczonego do odliczenia (VAT z zakupów)</td></tr>
            <tr><td><b>P_51</b></td><td>Kwota do wpłaty do Urzędu Skarbowego (P_38 - P_48)</td></tr>
            <tr><td><b>P_62</b></td><td>Kwota do przeniesienia na następny okres (Nadwyżka zakupu nad sprzedażą)</td></tr>
        </table>
        
        <h4>Dostępne Akcje:</h4>
        <ul>
            <li><b>Generuj JPK_V7M / V7K:</b> Tworzy standardowy plik za dany okres (Cel złożenia: 1).</li>
            <li><b>Korekta JPK:</b> Tworzy plik korekty (Cel złożenia: 2). Należy złożyć, gdy w poprzednim pliku wykryto błąd.</li>
            <li><b>JPK_FA:</b> Plik zawierający wyłącznie faktury sprzedaży (zwykle na osobne wezwanie organu podatkowego).</li>
        </ul>
        <p><i>Upewnij się, że w Ustawieniach "Księgowość" wybrano poprawną metodę rozliczeń (Miesięczna/Kwartalna).</i></p>
        """
        
        dlg = QDialog(self)
        dlg.setWindowTitle("Instrukcja JPK")
        dlg.resize(650, 600)
        layout = QVBoxLayout(dlg)
        
        browser = QTextBrowser()
        browser.setHtml(text)
        layout.addWidget(browser)
        
        btns = QDialogButtonBox(QDialogButtonBox.Ok)
        btns.accepted.connect(dlg.accept)
        layout.addWidget(btns)
        
        dlg.exec()

    def not_impl(self, name):
        QMessageBox.information(self, "W Budowie", f"Funkcja '{name}' jest w trakcie implementacji.")

    def load_annual_data(self):
        db = next(get_db())
        try:
            config = db.query(CompanyConfig).first()
            is_ryczalt = (config.taxation_form == TaxationForm.RYCZALT) if config else True
            is_vat_payer = config.is_vat_payer if config else True

            # Tab 1: PPE or General Sales
            if is_ryczalt:
                self.render_ppe_table(db, config)
            else:
                self.render_sales_summary_table(db, config)
            
            # Manage visibility of VAT tabs
            self.update_vat_tabs_visibility(is_vat_payer)

            # Tab 2 & 3: VAT Register & JPK
            if is_vat_payer:
                self.render_vat_register_table(db, config)
                self.render_jpk_table(db, config)
            
        finally:
            db.close()
            
    def update_vat_tabs_visibility(self, is_vat_payer):
        vat_idx = self.tabs.indexOf(self.tab_vat)
        jpk_idx = self.tabs.indexOf(self.tab_jpk)
        
        if is_vat_payer:
            # Add if missing
            if vat_idx == -1:
                self.tabs.insertTab(1, self.tab_vat, "Ewidencja VAT (Sprzedaż i Zakup)")
            if jpk_idx == -1:
                # Append JPK (likely at index 2 if VAT is at 1, or append at end)
                self.tabs.addTab(self.tab_jpk, "Deklaracje JPK")
        else:
            # Remove if present
            if jpk_idx != -1:
                self.tabs.removeTab(jpk_idx)
            # Re-check VAT index as it might change if we removed something before it (unlikely here)
            vat_idx = self.tabs.indexOf(self.tab_vat)
            if vat_idx != -1:
                self.tabs.removeTab(vat_idx)

    def render_jpk_table(self, db, config):
        self.table_jpk.setRowCount(0)
        
        year = int(self.year_combo.currentText())
        
        # Check Settlement Method
        method = "MONTHLY"
        if hasattr(config, 'vat_settlement_method') and config.vat_settlement_method:
             method = config.vat_settlement_method
        
        is_quarterly = (method == "QUARTERLY")
        
        months = ["Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec", 
                  "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień"]
            
        for i, m_name in enumerate(months):
            month_num = i + 1
            
            row = self.table_jpk.rowCount()
            self.table_jpk.insertRow(row)
            
            quarter_num = None
            if is_quarterly:
                quarter_num = (month_num - 1) // 3 + 1
                display_label = f"{m_name} {year} (Kwartał {quarter_num})"
                btn_label = "Generuj JPK_V7K"
                # Determine sub-type for tooltip/clarity
                is_full = (month_num % 3 == 0)
                desc = "Ewidencja + Deklaracja" if is_full else "Tylko Ewidencja"
                btn_color = "" # Default
            else:
                display_label = f"{m_name} {year}"
                btn_label = "Generuj JPK_V7M"
                desc = "Miesięczny"
                
            self.table_jpk.setItem(row, 0, QTableWidgetItem(display_label))
            
            # Złożenie
            btn_v7 = QPushButton(btn_label)
            btn_v7.setToolTip(f"{btn_label} - {desc}")
            if is_quarterly:
                 # Pass both month and quarter
                 btn_v7.clicked.connect(lambda checked=False, m=month_num, q=quarter_num: self.generate_jpk_v7(month=m, quarter=q))
            else:
                 btn_v7.clicked.connect(lambda checked=False, m=month_num: self.generate_jpk_v7(month=m))
                 
            self.table_jpk.setCellWidget(row, 1, btn_v7)
            
            # Korekta
            btn_kor = QPushButton("Korekta")
            btn_kor.setStyleSheet("color: red")
            btn_kor.setToolTip("Korekta " + desc)
            if is_quarterly:
                btn_kor.clicked.connect(lambda checked=False, m=month_num, q=quarter_num: self.generate_jpk_v7(month=m, quarter=q, is_correction=True))
            else:
                btn_kor.clicked.connect(lambda checked=False, m=month_num: self.generate_jpk_v7(month=m, is_correction=True))
            self.table_jpk.setCellWidget(row, 2, btn_kor)
            
            # Inne (JPK_FA)
            # JPK_FA is purely period based. Month is fine.
            btn_fa = QPushButton("JPK_FA")
            btn_fa.clicked.connect(lambda checked=False, m=month_num: self.generate_jpk_fa(month=m))
            self.table_jpk.setCellWidget(row, 3, btn_fa)

    def generate_jpk_v7(self, month=None, quarter=None, is_correction=False):
        year = int(self.year_combo.currentText())
        
        file_type = "JPK_V7K" if quarter else "JPK_V7M"
        # Since we now ALWAYS have month:
        suffix = f"{month:02d}"
        if quarter:
             suffix += f"_Q{quarter}"
             
        if is_correction:
            suffix += "_KOREKTA"
            
        default_name = f"{file_type}_{year}_{suffix}.xml"
        path, _ = QFileDialog.getSaveFileName(self, f"Zapisz {file_type}", default_name, "XML Files (*.xml)")
        
        if not path:
            return
            
        # Run generation
        db = next(get_db())
        try:
            service = JpkService(db)
            # Pass correct args
            service.generate_jpk_v7m(year, month if month else 1, path, quarter=quarter, is_correction=is_correction)
            QMessageBox.information(self, "Sukces", f"Plik {path} został wygenerowany pomyślnie.")
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie udało się wygenerować JPK:\n{str(e)}")
        finally:
            db.close()

    def generate_jpk_fa(self, month=None, quarter=None):
        year = int(self.year_combo.currentText())
        
        suffix = f"Q{quarter}" if quarter else f"{month:02d}"
        default_name = f"JPK_FA_{year}_{suffix}.xml"
        path, _ = QFileDialog.getSaveFileName(self, "Zapisz JPK_FA", default_name, "XML Files (*.xml)")
        
        if not path:
            return
            
        # Run generation
        db = next(get_db())
        try:
            service = JpkService(db)
            service.generate_jpk_fa(year, month if month else 1, path, quarter=quarter)
            QMessageBox.information(self, "Sukces", f"Plik {path} został wygenerowany pomyślnie.")
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie udało się wygenerować JPK_FA:\n{str(e)}")
        finally:
            db.close()


    def render_vat_register_table(self, db, config):
        year = int(self.year_combo.currentText())
        months = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
        
        # Define Columns
        # M-c | Sprzedaż Netto | Sprzedaż VAT | Sprzedaż Brutto | 23% Net | 23% Vat | 8% Net | 8% Vat | 5% Net | 5% Vat | ZW/0 Net | Zakup Netto | Zakup VAT | Zakup Brutto | Bilans VAT | Narast. VAT
        headers = [
            "M-c", 
            "Sprzedaż\nNetto", "Sprzedaż\nVAT", "Sprzedaż\nBrutto",
            "23% Net", "23% VAT", 
            "8% Net", "8% VAT", 
            "5% Net", "5% VAT", 
            "0%/ZW Net", "Inne Net",
            "Zakup\nNetto", "Zakup\nVAT", "Zakup\nBrutto", 
            "VAT Należny\n(Do Zapłaty)", "VAT\nNarastająco"
        ]
        
        self.table_vat.setColumnCount(len(headers))
        self.table_vat.setHorizontalHeaderLabels(headers)
        
        # Tooltips setup using Model Data (More reliable)
        for i, h_text in enumerate(headers):
             tooltip_text = h_text.replace('\n', ' ')
             self.table_vat.model().setHeaderData(i, Qt.Horizontal, tooltip_text, Qt.ToolTipRole)

        # Resize modes
        header = self.table_vat.horizontalHeader()
        
        # Strategy: Use Interactive usually, but Stretch if user wants "Full Width".
        # If we use Stretch, it forces fit and ignores scrollbar (squeezing content).
        # User said: "tabela powinna dać się przewijać w poziomie jeśli nie mieści się w okienku"
        # BUT also "kolumny były rozłożone na całą szerokość".
        # This implies: Minimum width = Window width. If content > Window, Scroll.
        # If content < Window, Stretch to fit.
        
        # Standard QTableWidget doesn't support "Stretch but Scroll" easily.
        # Best compromise: ResizeToContents for all, but ensure last column stretches? 
        # Or set a MINIMUM width for columns (approx 80px) and allow Stretch?
        
        # Let's try explicit Loop settings
        # 0 (Month) -> Fixed/Content
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        
        # Others try to be distributed.
        # If we use 'Interactive' (default), they don't auto-spread.
        # If we use 'Stretch', they spread but don't scroll.
        # If we want both? We can set a minimum width on the table or columns.
        
        header.setMinimumSectionSize(80) # Enforce min width to trigger scroll if squeezed
        header.setSectionResizeMode(QHeaderView.Interactive) # User can resize
        
        # But to initial "Spread", we can calculate widths? No.
        # Let's use Stretch, but with the warning that it might squeeze. 
        # Actually `setDefaultSectionSize` might help?
        
        # RE-ATTEMPT: Use STRETCH for visibility filling, but if users says "Not Working" maybe they mean
        # the table didn't expand to the widget size?
        
        # Let's try a different Approach:
        # Set all to ResizeToContents initially to see data, then Stretch last?
        # Or just ResizeToContents + StretchLastSection=True?
        
        # User feedback "1. nie zadziałało" suggests `Stretch` forced them to be tiny or didn't spread.
        # Let's switch to `ResizeToContents` for clarity, with `StretchLastSection`.
        # AND set tooltips via model.
        
        for i in range(1, len(headers)):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
            
        header.setStretchLastSection(True) # Fill remaining space

        header.setMinimumSectionSize(60) # Prevent total collapse on small screens
        
        # Exception: Month column can be Fixed/ResizeToContents to save space for numbers
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)

        self.table_vat.setRowCount(0)
        
        service = RevenueService(db)
        today = datetime.date.today()
        cumulative_vat_balance = 0.0
        
        for i, m_name in enumerate(months):
            month_num = i + 1
            if year == today.year and month_num > today.month:
                continue
            
            # Use the new service method
            data = service.get_vat_register_summary(year, month_num)
            
            sales = data['sales']
            purch = data['purchases']
            bal = data['balance']
            
            breakdown = sales['breakdown']
            
            vat_balance_month = bal['vat_due']
            cumulative_vat_balance += vat_balance_month
            
            row = self.table_vat.rowCount()
            self.table_vat.insertRow(row)
            
            # Helper for creating item
            def make_item(val, bold=False, color=None):
                txt = f"{val:.2f}"
                it = QTableWidgetItem(txt)
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if bold:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                if color:
                    it.setForeground(QBrush(QColor(color)))
                return it

            # Col 0: Month
            self.table_vat.setItem(row, 0, QTableWidgetItem(m_name))
            
            # Sales Totals
            self.table_vat.setItem(row, 1, make_item(sales['net'], True))
            self.table_vat.setItem(row, 2, make_item(sales['vat']))
            self.table_vat.setItem(row, 3, make_item(sales['gross']))
            
            # Breakdown
            # 23%
            self.table_vat.setItem(row, 4, make_item(breakdown['0.23']['net']))
            self.table_vat.setItem(row, 5, make_item(breakdown['0.23']['vat']))
            # 8%
            self.table_vat.setItem(row, 6, make_item(breakdown['0.08']['net']))
            self.table_vat.setItem(row, 7, make_item(breakdown['0.08']['vat']))
            # 5%
            self.table_vat.setItem(row, 8, make_item(breakdown['0.05']['net']))
            self.table_vat.setItem(row, 9, make_item(breakdown['0.05']['vat']))
            # 0/ZW
            self.table_vat.setItem(row, 10, make_item(breakdown['0.0']['net']))
            # Other
            self.table_vat.setItem(row, 11, make_item(breakdown['other']['net']))
            
            # Purchases
            self.table_vat.setItem(row, 12, make_item(purch['net']))
            self.table_vat.setItem(row, 13, make_item(purch['vat']))
            self.table_vat.setItem(row, 14, make_item(purch['gross']))
            
            # Balance
            bal_item = make_item(vat_balance_month, True)
            if vat_balance_month > 0:
                bal_item.setForeground(QBrush(QColor("red")))
            elif vat_balance_month < 0:
                bal_item.setForeground(QBrush(QColor("green")))
            self.table_vat.setItem(row, 15, bal_item)
            
            # Cumulative
            cumu_item = make_item(cumulative_vat_balance, True)
            self.table_vat.setItem(row, 16, cumu_item)

    def render_ppe_table(self, db, config):
        year = int(self.year_combo.currentText())
        months = ["Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec", 
                  "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień"]
        
        self.table_ppe.setColumnCount(6)
        self.table_ppe.setHorizontalHeaderLabels(["Miesiąc", "Przychód (M-c)", "Przychód (Narastająco)", "Podatek (PPE)", "Termin Płatności", "Akcja"])
        self.table_ppe.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_ppe.setRowCount(0)
        
        # Set delegate for borders
        self.table_ppe.setItemDelegate(BorderRowDelegate(QColor(180, 220, 255), self.table_ppe))
        
        service = RevenueService(db)
        
        today = datetime.date.today()
        current_year_real = today.year
        current_month_real = today.month

        # We assume active tax period is LAST month (e.g. in Feb we pay Jan)
        active_tax_idx = -1
        if year == current_year_real:
             if current_month_real > 1:
                 active_tax_idx = current_month_real - 2 # 0-indexed: Jan=0. If month=2(Feb), prev=1(Jan) -> idx 0.
             else:
                 # It's Jan, so active period is Dec of PREV year (not in this table view usually, unless checking prev year)
                 pass

        cumu_revenue = 0.0

        for i, m_name in enumerate(months):
            month_num = i + 1
            
            # Future months check
            if year > current_year_real or (year == current_year_real and month_num > current_month_real):
                # Don't process future months? Or show empty
                pass
            
            data = service.get_monthly_summary(year, month_num)
            rev_month = data['total_revenue']
            tax_month = data['total_tax_rounded']
            
            if rev_month == 0 and tax_month == 0:
                 # Check if future
                 if year == current_year_real and month_num > current_month_real:
                     continue
            
            cumu_revenue += rev_month
            
            row = self.table_ppe.rowCount()
            self.table_ppe.insertRow(row)
            
            # Month Name
            item_month = QTableWidgetItem(m_name)
            
            # Rev
            item_rev = QTableWidgetItem(f"{rev_month:.2f} zł")
            item_rev.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            
            # Cumu
            item_cumu = QTableWidgetItem(f"{cumu_revenue:.2f} zł")
            item_cumu.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            
            # Tax
            item_tax = QTableWidgetItem(f"{tax_month:.0f} zł")
            item_tax.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            item_tax.setFont(self.get_bold_font())
            
            # Due Date
            next_m = month_num + 1
            next_y = year
            if next_m > 12:
                next_m = 1
                next_y += 1
            due_date_str = f"20-{next_m:02d}-{next_y}"
            item_due = QTableWidgetItem(due_date_str)
            item_due.setTextAlignment(Qt.AlignCenter)
            
            # Action (Button to add to settlements)
            # Create a widget to hold the button
            widget = QWidget()
            h_lay = QHBoxLayout(widget)
            h_lay.setContentsMargins(2, 2, 2, 2)
            h_lay.setSpacing(0)
            
            # Condition: Show button only if month is finished (past month)
            # Current date
            now = datetime.datetime.now()
            # The month 'month_num' is finished if:
            # 1. Year < Current Year
            # 2. Year == Current Year AND Month < Current Month
            
            is_month_finished = False
            if year < now.year:
                is_month_finished = True
            elif year == now.year and month_num < now.month:
                is_month_finished = True
                
            if is_month_finished:
                btn = QPushButton("Dodaj do Rozrachunków")
                btn.setStyleSheet("font-size: 10px; padding: 2px;")
                # Logic: Add 'Podatek' invoice to DB
                btn.clicked.connect(lambda ch, y=year, m=month_num, amt=tax_month: self.upsert_settlement(y, m, amt, "PPE"))
                h_lay.addWidget(btn)
            else:
                # Optionally add Label "W trakcie" or empty
                lbl = QLabel("W trakcie")
                lbl.setStyleSheet("color: gray; font-size: 10px;")
                h_lay.addWidget(lbl)
            
            h_lay.setAlignment(Qt.AlignCenter)
            
            self.table_ppe.setItem(row, 0, item_month)
            self.table_ppe.setItem(row, 1, item_rev)
            self.table_ppe.setItem(row, 2, item_cumu)
            self.table_ppe.setItem(row, 3, item_tax)
            self.table_ppe.setItem(row, 4, item_due)
            
            # Dummy item for col 5 to allow delegate to draw border
            item_action = QTableWidgetItem("")
            self.table_ppe.setItem(row, 5, item_action)
            self.table_ppe.setCellWidget(row, 5, widget)
            
            # Highlight active
            if i == active_tax_idx and year == current_year_real:
                # Use UserRole to trigger delegate drawing
                for c in range(6):
                     it = self.table_ppe.item(row, c)
                     if it:
                        it.setData(Qt.UserRole, True)
                        # Keep bold font for text clarity
                        font = it.font()
                        font.setBold(True)
                        it.setFont(font)
                        it.setToolTip("Aktualny okres rozliczeniowy")

    def render_sales_summary_table(self, db, config):
        # Table for General Sales Register (VAT/Net/Gross)
        year = int(self.year_combo.currentText())
        months = ["Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec", 
                  "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień"]
        
        # Use proper table reference if not PPE
        # But wait, self.table_ppe was introduced for PPE. 
        # For VAT/General sales, we might want to use another table or rename self.table?
        # Actually in init_ui we decided:
        # self.table = self.table_ppe (backward compat)
        # So render_sales_summary_table should use self.table_ppe if we are reusing?
        # No, init_ui sets self.table = self.table_ppe.
        # But render_sales_summary_table is for the "old" view IF NOT RYCZALT.
        # If user IS RYCZALT, they see PPE + VAT Register tabs.
        # If user IS NOT RYCZALT (e.g. Scale), they see... Sales Summary + VAT Register?
        # The prompt implies we are VAT payer on Ryczałt.
        # So render_sales_summary_table might be redundant in that specific mode, 
        # OR render_sales_summary_table should target self.table_ppe (tab 1)?
        
        # Let's assume we reuse table_ppe (tab 1) for main tax calculation view.
        tbl = self.table_ppe
        
        tbl.setColumnCount(7)
        tbl.setHorizontalHeaderLabels([
            "Miesiąc", "Sprzedaż Netto", "VAT Należny", "Sprzedaż Brutto", 
            "Narastająco (Netto)", "Narastająco (VAT)", "Akcja"
        ])
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tbl.setRowCount(0)
        
        service = RevenueService(db)
        
        cumu_net = 0.0
        cumu_vat = 0.0
        
        today = datetime.date.today()
        
        for i, m_name in enumerate(months):
            month_num = i + 1
            if year == today.year and month_num > today.month:
                continue
                
            stats = service.get_monthly_sales_stats(year, month_num)
            
            net = stats['net']
            vat = stats['vat']
            gross = stats['gross']
            
            cumu_net += net
            cumu_vat += vat
            
            row = tbl.rowCount()
            tbl.insertRow(row)
            
            tbl.setItem(row, 0, QTableWidgetItem(m_name))
            tbl.setItem(row, 1, QTableWidgetItem(f"{net:.2f}"))
            tbl.setItem(row, 2, QTableWidgetItem(f"{vat:.2f}"))
            tbl.setItem(row, 3, QTableWidgetItem(f"{gross:.2f}"))
            tbl.setItem(row, 4, QTableWidgetItem(f"{cumu_net:.2f}"))
            tbl.setItem(row, 5, QTableWidgetItem(f"{cumu_vat:.2f}"))
            
            # Details Button
            btn = QPushButton("Szczegóły")
            btn.clicked.connect(lambda ch, s=stats: self.show_details_popup(s))
            tbl.setCellWidget(row, 6, btn)

    def show_details_popup(self, stats):
        msg = "Podsumowanie stawek VAT:\n\n"
        rates = stats.get('rates', {})
        for r, vals in rates.items():
            rate_lbl = f"{float(r)*100:.0f}%" if r else "?"
            msg += f"Stawka {rate_lbl}:\n"
            msg += f"  Netto: {vals['net']:.2f}\n"
            msg += f"  VAT:   {vals['vat']:.2f}\n"
            msg += f"  Brutto:{vals['gross']:.2f}\n\n"
        
        QMessageBox.information(self, "Szczegóły sprzedaży", msg)

    def upsert_settlement(self, year, month, amount, type_code):
        # Implementation to add PPE invoice like logic
        # ... (Same as before, simplified copy for context)
        # Using placeholder for brevity as logic was in previous turns
        # I'll invoke settlements generic adder or query DB directly
        db = next(get_db())
        try:
            # Check existing
            desc = f"Podatek {type_code} {month:02d}/{year}"
            exist = db.query(Invoice).filter(Invoice.category==InvoiceCategory.PURCHASE, Invoice.number==desc).first()
            
            if exist:
                QMessageBox.information(self, "Info", f"Rozrachunek o nazwie '{desc}' już istnieje.")
                return

            # Find default Contractor 'Urząd Skarbowy'
            # Check for customized Tax Office from Config
            tax_office_contractor_name = "Urząd Skarbowy"
            
            # Fetch config
            config = db.query(CompanyConfig).first()

            # Use data from TAX_OFFICES if available via config
            if config and config.tax_office_code:
                 from logic.tax_offices import TAX_OFFICES
                 if config.tax_office_code in TAX_OFFICES:
                     tax_office_contractor_name = TAX_OFFICES[config.tax_office_code]

            contractor = db.query(Contractor).filter(Contractor.name == tax_office_contractor_name).first()
            if not contractor:
                # Generate unique dummy NIP to avoid IntegrityError
                dummy_nip = "0000000000"
                while db.query(Contractor).filter(Contractor.nip == dummy_nip).first():
                     dummy_nip = ''.join(random.choices(string.digits, k=10))
                
                contractor = Contractor(name=tax_office_contractor_name, nip=dummy_nip)
                db.add(contractor)
                db.commit()
            
            # Create Invoice
            next_m = month + 1
            next_y = year
            if next_m > 12:
                next_m = 1
                next_y += 1
            due_dt = datetime.datetime(next_y, next_m, 20)
            
            inv = Invoice(
                contractor_id=contractor.id,
                category=InvoiceCategory.PURCHASE,
                type=InvoiceType.PODATEK, # Fixed Type
                number=desc,
                date_issue=datetime.datetime.now(),
                date_sale=datetime.datetime.now(),
                payment_deadline=due_dt,
                total_net=amount,
                total_gross=amount,
                is_paid=False,
                currency="PLN",
                notes=f"Automatyczny wpis z modułu Deklaracje ({type_code})"
            )
            db.add(inv)
            db.commit()
            QMessageBox.information(self, "Sukces", "Dodano do rozrachunków.")
            self.load_annual_data()
        except Exception as e:
            QMessageBox.critical(self, "Błąd", str(e))
        finally:
            db.close()

    def get_bold_font(self):
        f = self.font()
        f.setBold(True)
        return f


