import requests
from datetime import datetime

class MfWhitelistClient:
    BASE_URL = "https://wl-api.mf.gov.pl/api/search/nip/"

    def check_nip(self, nip):
        """
        Sprawdza status podatnika VAT w Wykazie (Biała Lista) Ministerstwa Finansów.
        :param nip: Numer NIP do sprawdzenia
        :return: Słownik z danymi podatnika i statusem
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        url = f"{self.BASE_URL}{nip}?date={date_str}"
        
        try:
            # Nagłówki udające przeglądarkę mogą pomóc, ale API publiczne powinno działać bez nich
            headers = {
                'User-Agent': 'KsefInvoiceApp/1.0'
            }
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if "result" in data:
                     subject = data["result"]["subject"]
                     request_id = data["result"]["requestId"]
                     
                     if subject:
                         status = subject.get("statusVat")
                         name = subject.get("name")
                         
                         # Extended Data
                         regon = subject.get("regon")
                         krs = subject.get("krs")
                         residence_address = subject.get("residenceAddress")
                         working_address = subject.get("workingAddress")
                         account_numbers = subject.get("accountNumbers", [])
                         
                         return {
                             "active": status == "Czynny",
                             "status": status,
                             "request_id": request_id,
                             "name": name,
                             "regon": regon,
                             "krs": krs,
                             "residence_address": residence_address,
                             "working_address": working_address,
                             "account_numbers": account_numbers,
                             "success": True
                         }
                     else:
                         return {
                             "active": False,
                             "status": "Nieznany",
                             "success": True, # Zapytanie się udało, ale nie ma podmiotu
                             "error": "Podmiot nie figuruje w rejestrze"
                         }
                else:
                    return {"success": False, "error": "Brak pola result w odpowiedzi"}
            else:
                return {"success": False, "error": f"Błąd HTTP {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
