import requests
import json
import logging

logger = logging.getLogger(__name__)

class GusClient:
    """
    Klient do pobierania danych o podmiotach z bazy GUS (BIR1).
    Korzysta ze środowiska testowego (klucz publiczny: abcde12345abcde12345) lub produkcyjnego.
    """
    BASE_URL_TEST = "https://wyszukiwarkaregontest.stat.gov.pl/wsBIR/UslugaBIRzewnPubl.svc/json"
    BASE_URL_PROD = "https://wyszukiwarkaregon.stat.gov.pl/wsBIR/UslugaBIRzewnPubl.svc/json"
    
    # Publiczny klucz testowy GUS
    TEST_API_KEY = "abcde12345abcde12345"

    def __init__(self, api_key=None, production=False):
        self.production = production
        self.api_key = api_key if api_key else (None if production else self.TEST_API_KEY)
        self.url = self.BASE_URL_PROD if production else self.BASE_URL_TEST
        self.session_id = None

    def login(self):
        """Logowanie do usługi GUS i pobranie sesji"""
        if not self.api_key:
             logging.warning("Brak klucza API GUS")
             return False

        login_url = f"{self.url}/Zaloguj"
        try:
             payload = {"pKluczUzytkownika": self.api_key}
             headers = {"Content-Type": "application/json"}
             resp = requests.post(login_url, json=payload, headers=headers, timeout=5)
             
             if resp.status_code == 200:
                  # Odpowiedź w formacie {"d": "sessionId"}
                  data = resp.json()
                  if "d" in data and data["d"]:
                       self.session_id = data["d"]
                       logging.info(f"Zalogowano do GUS. Sesja: {self.session_id}")
                       return True
             
             logging.error(f"Nieudane logowanie do GUS: {resp.text}")
             return False
        except Exception as e:
             logging.error(f"Błąd połączenia z GUS: {e}")
             return False

    def get_contractor_by_nip(self, nip):
        """Pobiera dane firmy po NIP z GUS (BIR1)"""
        if not self.session_id:
            if not self.login():
                 return None
        
        # Usuń kreski z NIPu
        nip_clean = nip.replace("-", "").strip()
        search_url = f"{self.url}/DaneSzukajPodmioty"
        
        try:
             headers = {
                  "Content-Type": "application/json",
                  "sid": self.session_id
             }
             payload = {"pParametryWyszukiwania": {"Nip": nip_clean}}
             
             resp = requests.post(search_url, json=payload, headers=headers, timeout=10)
             if resp.status_code == 200:
                  data = resp.json()
                  # GUS zwraca {"d": "string_xml_or_json"} - w przypadku json to string json
                  if "d" in data and data["d"]:
                       # d zawiera listę podmiotów
                       items = json.loads(data["d"])
                       if isinstance(items, list) and len(items) > 0:
                            item = items[0]
                            return self._parse_gus_item(item)
                       elif isinstance(items, dict): # Gdyby zwróciło pojedynczy obiekt
                            return self._parse_gus_item(items)
                            
             logging.warning(f"Brak danych dla NIP {nip}")
             return None
        except Exception as e:
             logging.error(f"Błąd wyszukiwania w GUS: {e}")
             return None

    def _parse_gus_item(self, item):
         """Mapuje odpowiedź GUS na strukturę aplikacji"""
         # Pola GUS: Nazwa, Ulica, NrNieruchomosci, NrLokalu, Miejscowosc, KodPocztowy
         address = f"{item.get('Ulica', '')} {item.get('NrNieruchomosci', '')}"
         if item.get('NrLokalu'):
              address += f"/{item.get('NrLokalu')}"
         address = address.strip()
         
         # Jeśli brak ulicy (małe miejscowości), użyj miejscowości
         if not address and not item.get('Ulica'):
               address = item.get('Miejscowosc', '') + " " + item.get('NrNieruchomosci', '')

         return {
              "name": item.get("Nazwa", ""),
              "nip": item.get("Nip", ""),
              "address": address,
              "city": item.get("Miejscowosc", ""),
              "postal_code": item.get("KodPocztowy", ""),
              "country": "Polska",
              "country_code": "PL",
              # Dane z GUS nie zawierają wprost flagi VAT, to oddzielna usługa MF
              "is_vat_payer": False, 
              "is_vat_ue": False
         }
