import xml.etree.ElementTree as ET
from datetime import datetime

class MockCompany:
    def __init__(self):
        self.tax_office_code = "2206"
        self.is_natural_person = True
        self.nip = "1234567890"
        self.first_name = "Jan"
        self.last_name = "Kowalski"
        self.date_of_birth = "1990-01-01"

class JPKService:
    def __init__(self):
        self.ET = ET
        self.NS = "http://crd.gov.pl/wzor/2025/12/19/14090/"
        self.NS_ETD = "something"

    def _build_header(self, root, year, month, company, date_from, date_to, is_quarterly=False, is_correction=False):
        header = self.ET.SubElement(root, f"{{{self.NS}}}Naglowek")
        
        kod_sys = "JPK_V7K (3)" if is_quarterly else "JPK_V7M (3)"
        
        self.ET.SubElement(header, f"{{{self.NS}}}KodFormularza", 
                           kodSystemowy=kod_sys, wersjaSchemy="1-0E").text = "JPK_VAT"
        
        wariant = self.ET.SubElement(header, f"{{{self.NS}}}WariantFormularza")
        wariant.text = "3"
        
        cel = "2" if is_correction else "1"
        self.ET.SubElement(header, f"{{{self.NS}}}DataWytworzeniaJPK").text = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        self.ET.SubElement(header, f"{{{self.NS}}}NazwaSystemu").text = "KsefInvoice"
        self.ET.SubElement(header, f"{{{self.NS}}}CelZlozenia", poz="P_7").text = cel
        
        self.ET.SubElement(header, f"{{{self.NS}}}DataOd").text = date_from
        self.ET.SubElement(header, f"{{{self.NS}}}DataDo").text = date_to
        
        self.ET.SubElement(header, f"{{{self.NS}}}KodUrzedu").text = company.tax_office_code or "2206"

service = JPKService()
root = ET.Element("root")
service._build_header(root, 2026, 2, MockCompany(), "2026-02-01", "2026-02-28")
print(ET.tostring(root, encoding="unicode"))
