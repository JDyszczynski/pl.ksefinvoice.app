import re
import xml.etree.ElementTree as ET

xml_content = """<Faktura xmlns="http://crd.gov.pl/wzor/2025/06/25/13775/"
         xmlns:etd="http://crd.gov.pl/xml/schematy/dziedzinowe/mf/2022/01/05/eD/DefinicjeTypy/"
         xmlns:sc="http://www.edt.fr/sc/functions"
         xmlns:xs="http://www.w3.org/2001/XMLSchema"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://crd.gov.pl/wzor/2025/06/25/13775/ schemat.xsd">
   <Naglowek>
      <KodFormularza kodSystemowy="FA (3)" wersjaSchemy="1-0E">FA</KodFormularza>
   </Naglowek>
</Faktura>"""

def parse(xml_str):
    print("--- ORIG ---")
    print(xml_str)
    
    # 1. Agresywne usunięcie xsi:schemaLocation
    xml_str = re.sub(r'xsi:schemaLocation\s*=\s*"[^"]*"', '', xml_str, flags=re.DOTALL)
    
    # 2. Usunięcie deklaracji przestrzeni nazw xmlns="..." i xmlns:prefix="..."
    xml_str = re.sub(r'xmlns(:[a-zA-Z0-9_]+)?\s*=\s*"[^"]*"', '', xml_str, flags=re.DOTALL)
    
    # 3. Usunięcie wszelkich pozostałych atrybutów z prefiksami (np. xsi:type="...")
    xml_str = re.sub(r'\s[a-zA-Z0-9_]+:[a-zA-Z0-9_]+\s*=\s*"[^"]*"', '', xml_str, flags=re.DOTALL)
    
    # 4. Usunięcie prefiksów z tagów
    xml_str = re.sub(r'(<|/)[a-zA-Z0-9_]+:', r'\1', xml_str)

    print("--- PROCESSED ---")
    print(xml_str)
    
    try:
        ET.fromstring(xml_str)
        print("SUCCESS")
    except Exception as e:
        print(f"ERROR: {e}")

parse(xml_content)
