import requests
from datetime import datetime

class NbpClient:
    API_URL = "http://api.nbp.pl/api/exchangerates/rates/a/{code}/{date}/?format=json"

    def get_exchange_rate(self, currency_code, date_str):
        """
        Pobiera kurs średni waluty z NBP dla danej daty.
        date_str: 'YYYY-MM-DD'
        Zwraca float lub None.
        """
        if currency_code.upper() == "PLN":
            return 1.0

        url = self.API_URL.format(code=currency_code, date=date_str)
        try:
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                return data['rates'][0]['mid']
            elif response.status_code == 404:
                # Brak notowania w tym dniu, trzeba szukać wcześniej
                print(f"Brak kursu {currency_code} dla {date_str}")
                return None
        except Exception as e:
            print(f"Błąd NBP API: {e}")
            return None
        return None
