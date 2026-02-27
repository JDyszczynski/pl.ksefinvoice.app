import flet as ft
from gui.settings_view import NumberingRow
from database.models import PeriodType, NumberingSetting, InvoiceCategory, InvoiceType
from database.engine import init_db

def main(page: ft.Page):
    page.add(ft.Text("Test NumberingRow"))
    
    # Mock setting
    class MockSetting:
        period_type = PeriodType.YEARLY
        template = "{nr}/{rok}"
        
    row = NumberingRow(InvoiceCategory.SALES, InvoiceType.VAT, "Test Row", MockSetting())
    
    page.add(row)

if __name__ == "__main__":
    ft.app(target=main)