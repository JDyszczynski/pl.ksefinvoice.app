import requests
import json
import random
import datetime
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

# Konfiguracja
API_URL = "https://api-test.ksef.mf.gov.pl/v2"
NIP = "8882855215"
CERT_DIR = "ksef_keys"

def generate_pesel():
    """Generuje losowy, poprawny PESEL"""
    # Rok 1980-1999
    year = random.randint(1980, 1999)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    
    y_str = str(year)[2:]
    m_str = f"{month:02d}"
    d_str = f"{day:02d}"
    
    ssss = f"{random.randint(0, 9999):04d}"
    
    raw = y_str + m_str + d_str + ssss
    
    # Checksum 1-3-7-9
    weights = [1, 3, 7, 9, 1, 3, 7, 9, 1, 3]
    checksum = 0
    for i in range(10):
        checksum += int(raw[i]) * weights[i]
    
    last = (10 - (checksum % 10)) % 10
    return raw + str(last)

def register_test_data(nip, pesel):
    print(f"--- Rejestracja w KSeF Test (Fikcyjne Dane) ---")
    print(f"NIP Firmy: {nip}")
    print(f"PESEL Osoby (Reprezentanta): {pesel}")
    
    # 1. Rejestracja JDG/Osoby - najprostszy sposób na właściciela
    url = f"{API_URL}/testdata/person"
    payload = {
        "nip": nip,
        "pesel": pesel,
        "description": "Administrator Systemu (KsefInvoice)",
        "isBailiff": False
    }
    
    try:
        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        if resp.status_code in [200, 201, 204]:
            print("[OK] Zarejestrowano osobę/podmiot w środowisku testowym.")
        else:
            print(f"[!] Warning: {resp.status_code} {resp.text}")
            # Może już istnieje?
    except Exception as e:
        print(f"[ERROR] Błąd API: {e}")
        return False
        
    return True

def generate_certificates(nip, pesel):
    import os
    if not os.path.exists(CERT_DIR):
        os.makedirs(CERT_DIR)
        
    print("\n--- Generowanie Certyfikatu (Self-Signed) ---")
    
    # Klucz prywatny
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    
    # Zapisz klucz
    with open(f"{CERT_DIR}/private_key.pem", "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))
        
    # Certyfikat X.509
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, u"PL"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"Mazowieckie"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, u"Warszawa"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"Firma Testowa KSeF"),
        x509.NameAttribute(NameOID.COMMON_NAME, f"Osoba Testowa {pesel}"),
        # Ważne: Serial Number definiuje tożsamość w KSeF (często PESEL lub NIP)
        # Dla osoby fizycznej: PESEL
        # Dla pieczęci firmowej: NIP
        # Tutaj logujemy się jako osoba (Właściciel)
        x509.NameAttribute(NameOID.SERIAL_NUMBER, f"PESEL/{pesel}"), 
        # Alternatywa: Tytuł np. "Właściciel"
        x509.NameAttribute(NameOID.TITLE, u"Wlasciciel"),
         x509.NameAttribute(NameOID.SURNAME, u"Testowy"),
         x509.NameAttribute(NameOID.GIVEN_NAME, u"Jan"),
    ])
    
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        subject
    ).public_key(
        key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.utcnow()
    ).not_valid_after(
        # Ważny 1 rok
        datetime.datetime.utcnow() + datetime.timedelta(days=365)
    ).add_extension(
        x509.BasicConstraints(ca=False, path_length=None), critical=True,
    ).sign(key, hashes.SHA256())
    
    cert_path = f"{CERT_DIR}/certificate.pem"
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
        
    print(f"[OK] Wygenerowano: {cert_path}")
    print(f"[OK] Wygenerowano: {CERT_DIR}/private_key.pem")

    # Eksport do P12 (aby zaimportować w przeglądarce)
    # W nowszych wersjach cryptography pkcs12 jest w osobnym module
    try:
        from cryptography.hazmat.primitives.serialization import pkcs12
    except ImportError:
        # Fallback for older cryptography (though >42 usually has it)
        # But wait, 46.0.4 SHOULD have it. Maybe import location changed?
        # It's usually 'cryptography.hazmat.primitives.serialization.pkcs12'
        pass

    try:
        p12 = pkcs12.serialize_key_and_certificates(
            name=b"KsefTest",
            key=key,
            cert=cert,
            cas=None,
            encryption_algorithm=serialization.BestAvailableEncryption(b"1234") # Hasło proste
        )
        with open(f"{CERT_DIR}/auth_token_cert.p12", "wb") as f:
            f.write(p12)
        print(f"[OK] Wygenerowano P12: {CERT_DIR}/auth_token_cert.p12 (Hasło: 1234)")
    except Exception as e:
        print(f"[WARNING] Nie można wygenerować P12 (ImportError?): {e}")
        print("Możesz spróbować połączyć PEM ręcznie poleceniem openssl:")
        print(f"openssl pkcs12 -export -out {CERT_DIR}/cert.p12 -inkey {CERT_DIR}/private_key.pem -in {CERT_DIR}/certificate.pem")
    
    return True

if __name__ == "__main__":
    pesel = generate_pesel()
    if register_test_data(NIP, pesel):
        generate_certificates(NIP, pesel)
        print("\n=== CO DALEJ? ===")
        print(f"1. Twoje dane zostały zarejestrowane w KSeF Test (NIP: {NIP}, PESEL: {pesel})")
        print(f"2. Wygenerowany certyfikat P12 jest w: {CERT_DIR}/auth_token_cert.p12")
        print("3. Pobierz ten plik P12 na dysk.")
        print("4. Wejdź na https://ksef-test.mf.gov.pl/web/")
        print("5. Wybierz 'Zaloguj się' -> 'Certyfikat' -> wczytaj plik P12 (hasło: 1234).")
        print("6. Po zalogowaniu w menu wybierz 'Uprawnienia' -> 'Generuj Token'.")
        print("7. Skopiuj token i wklej go do ustawień programu.")
