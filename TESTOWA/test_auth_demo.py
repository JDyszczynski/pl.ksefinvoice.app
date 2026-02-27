import logging
import sys
import os

# Ensure project root is in path
sys.path.append(os.getcwd())

from ksef.client import KsefClient

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO)

# Dane użytkownika
NIP = "8882855215"
# Wprowadź tutaj TYLKO token (sekret) - 64 znaki hex (lub ten długi ciąg jeśli jesteś pewien)
# Ostatnio używany przez usera:
RAW_INPUT = "20260201-EC-2A4E3BF000-32C15D39DD-3B|nip-8882855215|be39326db4864dbaa0480f52d70cbf348ff69381570e4c2ba0eb28ab26f143d6"

# Obecnie zakładamy, że token to ostatnia część
REAL_TOKEN = RAW_INPUT.split("|")[-1]

print(f"Używam tokenu: {REAL_TOKEN}")

client = KsefClient(token=REAL_TOKEN)

try:
    print("Rozpoczynam uwierzytelnianie w środowisku DEMO...")
    client.authenticate(NIP)
    if client.session_token:
        print("SUKCES! Zalogowano pomyślnie.")
        print(f"Session Token: {client.session_token}")
    else:
        print("Status 200 (OK), ale nie zwrócono SessionToken w odpowiedzi statusowej (TokenSession). Być może trzeba pobrać token przez /auth/token/redeem?")
except Exception as e:
    print(f"BŁĄD: {e}")
