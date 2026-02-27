import logging
import sys
import os

# Ensure project root is in path
sys.path.append(os.getcwd())

from ksef.client import KsefClient

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO)

# Dane użytkownika - PRODUKCJA
# NIP i TOKEN podane przez użytkownika
NIP = "8882855215"
# Token wygenerowany 2026-02-01 na Produkcji (wnioskując z przedrostka 20260201-EC)
# Pełny ciąg: "20260201-EC-2C2B19F000-09AC30E1FB-37|nip-8882855215|534b88cbf4974e30b30ab2e7bf5c4f1318a13f13fae5488395a2e816b126807c"
# Token właściwy (sekret/hash) to zazwyczaj ostatnia część po znaku '|'
RAW_INPUT = "20260201-EC-2C2B19F000-09AC30E1FB-37|nip-8882855215|534b88cbf4974e30b30ab2e7bf5c4f1318a13f13fae5488395a2e816b126807c"
REAL_TOKEN = RAW_INPUT.split("|")[-1]


# Warianty do przetestowania
variants = [
    ("Suffix Hex", RAW_INPUT.split("|")[-1]),
    ("Full String", RAW_INPUT),
    ("Reference Number", RAW_INPUT.split("|")[0])
]

print(f"Środowisko: PRODUKCJA (api.ksef.mf.gov.pl)")

# Wymuszenie pobrania nowego klucza publicznego dla produkcji
pub_key_path = "ksef/public_key_prod.pem"
if os.path.exists(pub_key_path):
    try:
        os.remove(pub_key_path)
    except:
        pass

# Używamy działającego formatu: FULL STRING
token_val = RAW_INPUT

print(f"\n--- TEST: Full String (PRODUKCJA) ---")
print(f"Token: {token_val[:10]}...{token_val[-10:]}")

client = KsefClient(token=token_val)
try:
    client.authenticate(NIP)
    if client.session_token:
        print(f"!!! SUKCES !!!")
        print(f"Session Token: {client.session_token}")
        sys.exit(0)
    else:
        print("Autoryzacja udana, ale brak Session Token w obiekcie klienta.")
except Exception as e:
    print(f"Błąd: {e}")
    import traceback
    traceback.print_exc()

print("\n=== KONIEC TESTU ===")


