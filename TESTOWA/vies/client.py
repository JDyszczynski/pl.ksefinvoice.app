import requests
import xml.etree.ElementTree as ET

class ViesClient:
    URL = "http://ec.europa.eu/taxation_customs/vies/services/checkVatService"

    def check_vat(self, country_code, vat_number):
        """
        Weryfikuje numer VAT UE w systemie VIES.
        :param country_code: Kod kraju (np. PL, DE)
        :param vat_number: Numer VAT (bez kodu kraju)
        :return: Słownik z wynikami weryfikacji
        """
        soap_request = f"""
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:urn="urn:ec.europa.eu:taxud:vies:services:checkVat:types">
           <soapenv:Header/>
           <soapenv:Body>
              <urn:checkVat>
                 <urn:countryCode>{country_code}</urn:countryCode>
                 <urn:vatNumber>{vat_number}</urn:vatNumber>
              </urn:checkVat>
           </soapenv:Body>
        </soapenv:Envelope>
        """
        
        headers = {'Content-Type': 'text/xml'}
        try:
            response = requests.post(self.URL, data=soap_request, headers=headers, timeout=10)
            if response.status_code == 200:
                # Parsowanie odpowiedzi XML
                root = ET.fromstring(response.content)
                
                valid = False
                name = None
                address = None
                
                # Przeszukiwanie drzewa XML (z uwzględnieniem przestrzeni nazw)
                # Używamy iter() żeby znaleźć tagi niezależnie od dokładnej struktury NS
                for child in root.iter():
                    if 'valid' in child.tag:
                        valid = (child.text == 'true')
                    elif 'name' in child.tag:
                         name = child.text
                    elif 'address' in child.tag:
                        address = child.text
                        
                return {
                    "valid": valid,
                    "name": name if name and name != "---" else None,
                    "address": address if address and address != "---" else None,
                    "success": True
                }
            else:
                return {"success": False, "error": f"HTTP Error {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
