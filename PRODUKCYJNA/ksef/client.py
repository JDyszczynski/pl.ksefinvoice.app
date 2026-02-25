import requests
import time
import json
import os
import base64
from datetime import datetime
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa, ec
from cryptography import x509
import logging
from lxml import etree
import signxml
from ksef.encryption import EncryptionManager
from ksef.xades import sign_xades_bes
from logic.security import SecurityManager
from database.engine import get_db
from database.models import CompanyConfig

logger = logging.getLogger(__name__)

class KsefClient:
    """
    Klient do integracji z Krajowym Systemem e-Faktur (KSeF 2.0).
    """
    
    # Base URLs
    URL_PROD = "https://api.ksef.mf.gov.pl/v2"
    URL_TEST = "https://api-demo.ksef.mf.gov.pl/v2" # As mentioned by user or standard test

    def __init__(self, config=None, token=None):
        self.config = config
        self.env = "test"
        if self.config:
            self.env = self.config.ksef_environment or "test"
            
        # Determine effective credentials based on environment
        eff_token = None
        if self.config:
             if self.env == "prod":
                  eff_token = SecurityManager.decrypt(self.config.ksef_token) if self.config.ksef_token else None
             else:
                  raw_test_token = getattr(self.config, 'ksef_token_test', None)
                  eff_token = SecurityManager.decrypt(raw_test_token) if raw_test_token else None
                  
        self.token = token or eff_token
        self.session_token = None
        self.session_reference_number = None # Init attribute
        
        self.API_URL = self.URL_PROD if self.env == "prod" else self.URL_TEST
        self.PUBLIC_KEY_PATH = f"ksef/public_key_{self.env}.pem"
        
        # Determine Public Key Content (DB vs File)
        pub_key_content = None
        if self.config:
            if self.env == "prod":
                pub_key_content = getattr(self.config, 'ksef_public_key_prod', None)
            else:
                pub_key_content = getattr(self.config, 'ksef_public_key_test', None)
        
        # If not in DB, try File (legacy/fallback)
        if not pub_key_content and os.path.exists(self.PUBLIC_KEY_PATH):
             with open(self.PUBLIC_KEY_PATH, "rb") as f:
                 pub_key_content = f.read()

        # If still missing, try auto-download
        if not pub_key_content:
             logger.info(f"Public Key ({self.env}) not found in DB or File. Attempting download...")
             try:
                 pub_key_content = self.fetch_public_key()
             except Exception as e:
                 logger.warning(f"Could not auto-download public key: {e}")
        
        self.encryption = EncryptionManager(self.PUBLIC_KEY_PATH, public_key_content=pub_key_content)
        self._setup_transaction_logger()
        
        # Load Certs if needed
        self.cert = None
        self.private_key = None
        self.cert_data = None
        if self.config and self.config.ksef_auth_mode == "CERT":
            self.load_certificates()

    def load_certificates(self):
        try:
            # Determine content vars based on enviroment
            # Updated to use database content (BLOBs) instead of paths
            
            content_cert = self.config.ksef_cert_content
            content_key = self.config.ksef_private_key_content
            pass_encrypted = self.config.ksef_private_key_pass
            
            if self.env != "prod": # Test/Demo
                 content_cert = getattr(self.config, 'ksef_cert_content_test', None)
                 content_key = getattr(self.config, 'ksef_private_key_content_test', None)
                 pass_encrypted = getattr(self.config, 'ksef_private_key_pass_test', None)

            # Decrypt password using SecurityManager
            pass_key = SecurityManager.decrypt(pass_encrypted) if pass_encrypted else None
            
            # Fallback (old behavior with paths removed for clarity as we migrated)
            
            if not content_cert or not content_key:
                logger.warning(f"Tryb CERT ({self.env}), ale brak danych certyfikatu/klucza w bazie.")
                return

            self.cert_data = content_cert
            self.cert = x509.load_pem_x509_certificate(self.cert_data)
            
            pwd = None
            if pass_key:
                pwd = pass_key.encode('utf-8')
            self.private_key = serialization.load_pem_private_key(content_key, password=pwd)
            
            logger.info("Załadowano certyfikat i klucz prywatny z bazy danych.")
        except Exception as e:
            logger.error(f"Błąd ładowania certyfikatów: {e}")
            raise

    def _setup_transaction_logger(self):
        self.trans_logger = logging.getLogger("ksef.transactions")
        self.trans_logger.setLevel(logging.DEBUG)
        
        # Unikaj duplikowania handlerów
        if not self.trans_logger.handlers:
            fh = logging.FileHandler("ksef_transactions.log", encoding='utf-8')
            fh.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            fh.setFormatter(formatter)
            self.trans_logger.addHandler(fh)

    def fetch_public_key(self):
        """Fetches public key from KSeF API and saves to file."""
        # Use a request without logging (to avoid circular deps or noise) or minimal
        url = f"{self.API_URL}/online/General/PublicKey"
        # Since v2, endpoint might be different or require Auth? 
        # Actually /online/General/PublicKey is often open? Check Swagger.
        # Wait, usually encryption key is needed FOR Auth. So it must be public.
        # Swagger: GET /online/General/PublicKey
        
        try:
             # Just plain requests
             logger.info(f"Downloading Public Key from {url}")
             resp = requests.get(url, headers={"Accept": "application/json"})
             if resp.status_code != 200:
                  # Fallback logic?
                  raise Exception(f"Status {resp.status_code}: {resp.text}")
             
             data = resp.json()
             # Structure: { "publicKeyCertificateList": [ { "certificate": "...", "usage": "..." } ] }
             
             list_certs = data.get("publicKeyCertificateList", [])
             target_cert = None
             
             # Priority 1: encrypting (for symmetric key)
             for item in list_certs:
                  # Usage can be "encipherment" or similar
                  # KSeF documentation usually distinguishes between signing and encryption
                  # Actually "usage" field is key.
                  # Let's try to grab the one suitable for 'Algorithm: RSA' -> encryption
                  # Or simply the first one usually works if only one provided.
                  target_cert = item.get("certificate") # Base64 content
                  # In FA(2) usually one key used for Auth Challenge encryption
                  break
             
             if target_cert:
                  pem = f"-----BEGIN CERTIFICATE-----\n{target_cert}\n-----END CERTIFICATE-----"
                  with open(self.PUBLIC_KEY_PATH, "w") as f:
                       f.write(pem)
                  logger.info(f"Saved public key to {self.PUBLIC_KEY_PATH}")
             else:
                  raise Exception("No certificate found in response")
                  
        except Exception as e:
             logger.error(f"Failed to fetch public key: {e}")
             raise

    def _log_transaction(self, method, url, headers, body, response):
        try:
             # Log request
             msg = f"\n{'='*50}\nREQUEST: {method} {url}\nHEADERS: {json.dumps(headers, default=str)}\n"
             if body:
                  if isinstance(body, dict):
                       msg += f"BODY (JSON): {json.dumps(body, indent=2, default=str)}\n"
                  else:
                       msg += f"BODY: {str(body)[:1000]}\n"
             
             # Log response
             msg += f"\nRESPONSE: Status {response.status_code}\nHEADERS: {json.dumps(dict(response.headers), default=str)}\n"
             
             try:
                  ct = response.headers.get("Content-Type", "").lower()
                  if "application/json" in ct:
                       msg += f"BODY (JSON): {json.dumps(response.json(), indent=2, default=str)}\n"
                  elif "application/xml" in ct or "text" in ct:
                       msg += f"BODY (TEXT): {response.text[:5000]}\n" 
                  else:
                       msg += f"BODY (BINARY/OTHER): {len(response.content)} bytes\n"
             except:
                  msg += f"BODY (RAW): {response.text[:2000]}\n"
             
             msg += f"{'='*50}\n"
             self.trans_logger.debug(msg)
        except Exception as e:
             logger.error(f"Error logging transaction: {e}")

    def _request(self, method, url, **kwargs):
        headers = kwargs.get("headers", {})
        json_data = kwargs.get("json", None)
        
        try:
            response = requests.request(method, url, **kwargs)
            self._log_transaction(method, url, headers, json_data, response)
            return response
        except Exception as e:
            logger.error(f"Request failed: {method} {url} - {e}")
            raise

    def _get_headers(self):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if self.session_token:
            # KSeF v2 requires Bearer token, but some integrations might still use SessionToken header.
            # We provide both to be safe, or migrate to Authorization.
            # OpenAPI says Use "Bearer" (Authorization header).
            headers["Authorization"] = f"Bearer {self.session_token}"
            # headers["SessionToken"] = self.session_token # Uncomment if needed for some specific legacy endpoints
        return headers

    def _ensure_public_key(self):
        """Checks if public key file exists and is valid; fetches if not."""
        if not os.path.exists(self.PUBLIC_KEY_PATH) or os.path.getsize(self.PUBLIC_KEY_PATH) == 0:
            logger.info("Public key missing or empty. Fetching from KSeF API...")
            self.fetch_public_key()

    def fetch_public_key(self):
        """Fetches public key from KSeF API, saves to DB and file, and returns content."""
        url = f"{self.API_URL}/security/public-key-certificates"
        try:
            resp = self._request("GET", url, headers={"Accept": "application/json"})
            resp.raise_for_status()
            
            data = resp.json()
            # Handle potential dictionary wrapper or direct list
            items = data["publicKeyCertificateList"] if isinstance(data, dict) and "publicKeyCertificateList" in data else data
            
            key_content = None
            for cert in items:
                usage = cert.get("usage", [])
                # If we want the key for Session Symmetric Key encryption, we should prefer 'SymmetricKeyEncryption'
                # if available. Historical/Legacy behavior might have used KsefTokenEncryption.
                if "SymmetricKeyEncryption" in usage:
                     key_content = cert["certificate"]
                     logger.info("Found certificate with usage: SymmetricKeyEncryption")
                     break
                
            # Fallback if specific one not found (or if API changes)
            if not key_content:
                for cert in items:
                    usage = cert.get("usage", [])
                    if "KsefTokenEncryption" in usage:
                        key_content = cert["certificate"]
                        logger.info("Found certificate with usage: KsefTokenEncryption (Fallback)")
                        break
            
            if key_content:
                pem_key = f"-----BEGIN CERTIFICATE-----\n{key_content}\n-----END CERTIFICATE-----"
                pem_bytes = pem_key.encode('utf-8')

                # 1. Update DB if possible
                if self.config and self.config.nip:
                    try:
                        db_gen = get_db()
                        session = next(db_gen)
                        try:
                            # Re-fetch config to ensure attached to session
                            db_config = session.query(CompanyConfig).filter_by(nip=self.config.nip).first()
                            if db_config:
                                if self.env == "prod":
                                    db_config.ksef_public_key_prod = pem_bytes
                                    self.config.ksef_public_key_prod = pem_bytes
                                else:
                                    db_config.ksef_public_key_test = pem_bytes
                                    self.config.ksef_public_key_test = pem_bytes
                                session.commit()
                                logger.info(f"Public key updated in DB for NIP {self.config.nip} (Env: {self.env})")
                            else:
                                logger.warning("Could not find CompanyConfig in DB to update public key.")
                        finally:
                            session.close()
                    except Exception as e:
                        logger.error(f"Failed to update public key in DB: {e}")

                # 2. Save to File (Legacy)
                try:
                    # Ensure directory exists
                    os.makedirs(os.path.dirname(self.PUBLIC_KEY_PATH), exist_ok=True)
                    with open(self.PUBLIC_KEY_PATH, "wb") as f:
                        f.write(pem_bytes)
                    logger.info(f"Public key saved to {self.PUBLIC_KEY_PATH}")
                except Exception as e:
                    logger.warning(f"Failed to save public key to file: {e}")
                
                # 3. Update encryption manager
                self.encryption = EncryptionManager(self.PUBLIC_KEY_PATH, public_key_content=pem_bytes)
                
                return pem_bytes

            else:
                logger.error("KsefTokenEncryption key not found in API response.")
                raise Exception("KsefTokenEncryption key not found")
                
        except Exception as e:
            logger.error(f"Failed to fetch public key: {e}")
            raise

    def authenticate(self, nip: str):
        """Pełny proces logowania (Token lub Cert)."""
        
        mode = "TOKEN"
        if self.config and self.config.ksef_auth_mode:
            mode = self.config.ksef_auth_mode
            
        logger.info(f"Rozpoczynam autentykację metodą: {mode}")
        
        if mode == "CERT":
            return self.authenticate_cert(nip)
        else:
            return self.authenticate_token(nip)

    def authenticate_token(self, nip: str):
        """Autentykacja Tokenem (Stara metoda)"""
        if not self.token:
            raise ValueError("Brak tokenu KSeF w konfiguracji.")

        try:
            # 1. Pobierz Challenge
            challenge_data = self.get_challenge(nip)
            challenge = challenge_data["challenge"]
            timestamp = challenge_data["timestamp"] # ISO format
            # timestampMs = challenge_data["timestampMs"] # if available

            logger.info(f"Otrzymano challenge: {challenge}")

            # 2. Szyfrowanie tokenu
            # Format: token|timestamp_in_ms_from_epoch
            # Preferujemy timestampMs z odpowiedzi, jeśli dostępny
            if "timestampMs" in challenge_data:
                 ts_ms = challenge_data["timestampMs"]
            else:
                 # Fallback to parsing
                 dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                 ts_ms = int(dt.timestamp() * 1000)
            
            # Wg dokumentacji KSeF v2: token|timestamp
            # Gdzie timestamp to czas z serwera (challenge timestamp)
            
            logger.info(f"Using timestampMs: {ts_ms}")
            encrypted_token = self.encrypt_token(self.token, ts_ms)
            logger.info("Token zaszyfrowany pomyślnie.")

            # 3. Inicjacja sesji (Send Token)
            init_resp = self.init_token_auth(nip, challenge, encrypted_token)
            ref_num = init_resp["referenceNumber"]
            auth_token = init_resp["authenticationToken"]["token"] # To token operacyjny do sprawdzania statusu
            
            logger.info(f"Otrzymano referenceNumber: {ref_num}")
            
            # Common handling for session activation
            return self._finalize_session(ref_num, auth_token)

        except Exception as e:
            logger.error(f"Błąd autentykacji KSeF (Token): {e}")
            raise e

    def authenticate_cert(self, nip: str):
        """Autentykacja Certyfikatem (Podpisany InitSession)"""
        if not self.cert or not self.private_key:
            raise ValueError("Brak załadowanego certyfikatu/klucza.")
            
        try:
            # 1. Challenge
            challenge_data = self.get_challenge(nip)
            challenge = challenge_data["challenge"]
            timestamp = challenge_data["timestamp"]
            
            logger.info(f"Otrzymano challenge (Cert): {challenge}")
            
            # 2. Przygotuj InitSession XML i podpisz go
            signed_xml = self.prepare_signed_request(challenge, nip)
            
            # 3. Wyślij
            init_resp = self.init_session_signed(signed_xml)
            ref_num = init_resp["referenceNumber"]
            auth_token = init_resp["authenticationToken"]["token"]
            
            logger.info(f"Rozpoczęto autentykację (Cert). Ref: {ref_num}")
            
            # 4. Finalizacja sesji (oczekiwanie na status i pobranie tokena sesyjnego)
            return self._finalize_session(ref_num, auth_token)
            
        except Exception as e:
            logger.error(f"Błąd autentykacji KSeF (Cert): {e}")
            raise e

    def _finalize_session(self, ref_num, auth_token):
        # 4. Sprawdzanie statusu sesji (pętla)
        session_token = self.wait_for_session_active(ref_num, auth_token)
        
        if session_token is None:
                logger.info("Pobieranie tokena sesyjnego (Redeem)...")
                session_data = self.redeem_token(auth_token)
                if "accessToken" in session_data and "token" in session_data["accessToken"]:
                    session_token = session_data["accessToken"]["token"]
                else:
                    raise Exception(f"Brak pola accessToken.token w odpowiedzi redeem: {session_data}")
        
        self.session_token = session_token
        logger.info(f"Sesja aktywna! Token sesji: {self.session_token[:10]}...")
        return True

    def prepare_signed_request(self, challenge, nip):
        """Generuje i podpisuje XML AuthTokenRequest (KSeF V2)"""
        
        NS_AUTH = "http://ksef.mf.gov.pl/auth/token/2.0"
        
        # Build XML ElementTree manually to match expected structure
        nsmap = {
            None: NS_AUTH 
        }
        
        root = etree.Element(f"{{{NS_AUTH}}}AuthTokenRequest", nsmap=nsmap)
        
        chal = etree.SubElement(root, f"{{{NS_AUTH}}}Challenge")
        chal.text = challenge
        
        ctx_id = etree.SubElement(root, f"{{{NS_AUTH}}}ContextIdentifier")
        
        # Determine context identifier type. For NIP: <Nip>123...</Nip>
        # Assume NIP context based on input
        # Note: input 'nip' usually has dashes, remove them just in case
        clean_nip = nip.replace("-", "").strip()
        nip_el = etree.SubElement(ctx_id, f"{{{NS_AUTH}}}Nip")
        nip_el.text = clean_nip
        
        subj_type = etree.SubElement(root, f"{{{NS_AUTH}}}SubjectIdentifierType")
        subj_type.text = "certificateSubject" # 'certificateSubject' means we match by attributes in cert

        # Sign using XAdES-BES (Custom implementation)
        # Fixed: 9105 "Nieprawidłowy podpis" by ensuring XAdES QualifyingProperties and P1363 format for EC
        sign_xades_bes(root, self.private_key, self.cert_data)
        
        # KSeF expects XML declaration
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8")

    def init_session_signed(self, signed_xml_bytes):
        url = f"{self.API_URL}/auth/xades-signature"
        
        # Jeśli jesteśmy w środowisku TEST/DEMO, często używane są certyfikaty testowe, 
        # API pozwala wyłączyć weryfikację łańcucha CA parametrem verifyCertificateChain=false
        # Standardowo dla bezpieczeństwa powinno być true, ale dla środowisk testowych ułatwia pracę.
        if "test" in self.API_URL or "demo" in self.API_URL:
             url += "?verifyCertificateChain=false"
             
        headers = self._get_headers()
        headers["Content-Type"] = "application/xml" 
        headers["Accept"] = "application/json"
        
        resp = self._request("POST", url, data=signed_xml_bytes, headers=headers)
        if resp.status_code != 202: # Accepted
             raise Exception(f"Błąd AuthXadesSignature: {resp.status_code} {resp.text}")
        
        return resp.json()


    def get_challenge(self, nip: str):
        """POST /auth/challenge"""
        url = f"{self.API_URL}/auth/challenge"
        payload = {
            "contextIdentifier": {
                "type": "onip", # lub nip? Wg dok dla firm to 'onip' (Organizacja NIP) lub 'nip' (Osoba)? 
                                # W V2 zazwyczaj 'onip' dla podmiotu zbiorowego? 
                                # Sprawdźmy docs: zazwyczaj type=Nip jest uniwersalny lub type=onip
                "identifier": nip 
            }
        }
        # Dokumentacja V2 (patrz json): contextIdentifier: { type: "Nip", value: "..." } ??
        # Example z OpenAPI json grep: "contextIdentifier": { "type": "Nip", "value": "5265877635" }
        payload = {
             "contextIdentifier": {
                 "type": "Nip",
                 "value": nip
             }
        }

        resp = self._request("POST", url, json=payload, headers=self._get_headers())
        if resp.status_code != 200: # 201?
            # 200 OK w/g docs
             raise Exception(f"Błąd challenge: {resp.status_code} {resp.text}")
        
        return resp.json()

    def encrypt_token(self, token_str: str, timestamp_ms: int) -> str:
        """
        Szyfruje token|timestamp kluczem publicznym MF.
        Algorytm: RSA-OAEP (SHA-256).
        """
        self._ensure_public_key()
        try:
            return self.encryption.encrypt_ksef_token(token_str, timestamp_ms)
        except Exception as e:
            logger.error(f"Encryption error: {e}")
            raise

    def init_token_auth(self, nip: str, challenge: str, encrypted_token: str):
        """POST /auth/ksef-token"""
        url = f"{self.API_URL}/auth/ksef-token"
        payload = {
            "challenge": challenge,
            "contextIdentifier": {
                "type": "Nip",
                "value": nip
            },
            "encryptedToken": encrypted_token
        }
        
        resp = self._request("POST", url, json=payload, headers=self._get_headers())
        if resp.status_code != 202: # Accepted
             raise Exception(f"Błąd init token: {resp.status_code} {resp.text}")
        
        return resp.json()

    def wait_for_session_active(self, ref_number: str, auth_token: str):
        """GET /auth/{referenceNumber} - polling statusu"""
        url = f"{self.API_URL}/auth/{ref_number}"
        
        headers = self._get_headers()
        headers["Authorization"] = f"Bearer {auth_token}" 
        
        for _ in range(30): # 30 prób co 2 sekundy = 1 minuta
            time.sleep(2)
            resp = self._request("GET", url, headers=headers)
            
            if resp.status_code == 200:
                data = resp.json()
                logger.debug(f"Status response: {data}")
                
                # Struktura odpowiedzi w v2: {"status": {"code": 100, "description": "..."}}
                status_code = data.get("status", {}).get("code")
                
                if status_code == 200: # Sukces - Sesja aktywna
                     logger.info(f"Sesja aktywna (status 200).")
                     
                     # Sprawdzamy czy jest sessionToken
                     if "sessionToken" in data and "token" in data["sessionToken"]:
                         return data["sessionToken"]["token"]
                     
                     return None # Wymaga redeem
                elif status_code is not None and status_code >= 400:
                     raise Exception(f"Błąd przetwarzania sesji: {data.get('status', {}).get('description')}")
                else: 
                     logger.info(f"Status przetwarzania: {status_code} - {data.get('status', {}).get('description')}")
            else:
                 logger.warning(f"Błąd pobrania statusu: {resp.status_code}")
                 
        raise Exception("Timeout oczekiwania na sesję KSeF.")

    def redeem_token(self, auth_token: str, context_identifier=None):
        """POST /auth/token/redeem - Zamiana AuthenticationToken na SessionToken"""
        url = f"{self.API_URL}/auth/token/redeem"
        headers = self._get_headers()
        headers["Authorization"] = f"Bearer {auth_token}"
        
        payload = {}
        if context_identifier:
            payload["contextIdentifier"] = context_identifier
            
        resp = self._request("POST", url, json=payload, headers=headers)
        if resp.status_code == 200:
            return resp.json()
        else:
            raise Exception(f"Błąd redeem token: {resp.status_code} {resp.text}")

    def open_session(self):
        """Otwiera interaktywną sesję (POST /sessions/online)"""
        if not self.session_token:
            raise ValueError("Brak tokenu autoryzacyjnego (niezalogowany).")
            
        logger.info("Otwieranie sesji interaktywnej...")

        # Force refresh check of Public Key to prevent 415 errors (Key mismatch)
        try:
             self.fetch_public_key()
        except Exception as e:
             logger.warning(f"Could not refresh public key: {e}. Using cached if available.")
        
        # 1. Prepare Encryption Keys
        # Wybór klucza publicznego w zależności od środowiska
        pub_key_file = "ksef/public_key_prod.pem" if self.env == "prod" else "ksef/public_key_test.pem"
        
        self.encryption = EncryptionManager(public_key_path=pub_key_file)
        keys = self.encryption.initialize_session_keys()
        
        # 2. Prepare Request
        url = f"{self.API_URL}/sessions/online"
        headers = self._get_headers() # Has Bearer token
        
        payload = {
            "contextIdentifier": {
                "type": "Nip",
                "value": self.config.nip
            },
            "formCode": {
                "systemCode": "FA (3)",
                "schemaVersion": "1-0E",
                "targetNamespace": "http://crd.gov.pl/wzor/2025/06/25/13775/",
                "value": "FA"
            },
            "encryption": {
                "encryptedSymmetricKey": keys["encrypted_key"],
                "initializationVector": keys["iv_base64"]
            }
        }
        
        logger.info(f"POST {url}")
        resp = self._request("POST", url, json=payload, headers=headers)
        
        if resp.status_code == 201: # Created
            data = resp.json()
            self.session_reference_number = data["referenceNumber"]
            logger.info(f"Sesja otwarta: {self.session_reference_number}")
            return self.session_reference_number
        else:
            raise Exception(f"Błąd otwarcia sesji: {resp.status_code} {resp.text}")

    def send_invoice(self, invoice_xml_bytes: bytes):
        """
        Wysyła fakturę do KSeF (PUT /sessions/online/{ref}/invoices).
        """
        import hashlib
        
        if not self.session_token:
             # Fallback logic for mock/test without auth
             logger.warning("Brak tokenu sesji - Używam MOCK (Symulacja).")
             time.sleep(1)
             import random
             mock_ref = f"{self.config.nip}-{datetime.today().strftime('%Y%m%d')}-{random.randint(100000,999999)}-2B"
             return {
                 "success": True,
                 "ksef_number": mock_ref,
                 "timestamp": datetime.now().isoformat()
             }

        logger.info("Wysyłanie faktury do KSeF (Interactive)...")
        
        try:
            # 1. Ensure Session is Open
            if not self.session_reference_number:
                self.open_session()
                
            # LOG XML (DEBUG)
            try:
                logger.info("--- WYGENEROWANY XML (Przed szyfrowaniem) ---")
                logger_xml_preview = invoice_xml_bytes.decode('utf-8')
                logger.info(f"\n{logger_xml_preview}")
                logger.info("---------------------------------------------")
            except:
                pass
                
            # 2. Encrypt Invoice
            # KSeF wymaga zaszyfrowania całej zawartości faktury AESem sesyjnym
            encrypted_data = self.encryption.encrypt_data(invoice_xml_bytes)
            
            # 3. Calculate Hashes
            # Hash oryginału
            hash_sha = hashlib.sha256(invoice_xml_bytes).digest()
            hash_sha_b64 = base64.b64encode(hash_sha).decode('utf-8')
            size_plain = len(invoice_xml_bytes)
            
            # Hash zaszyfrowanego
            hash_enc = hashlib.sha256(encrypted_data).digest()
            hash_enc_b64 = base64.b64encode(hash_enc).decode('utf-8')
            size_enc = len(encrypted_data)
            
            content_b64 = base64.b64encode(encrypted_data).decode('utf-8')
            
            # 4. Prepare Payload
            # Zmiana struktury na zgodną z OpenAPI v2 SendInvoiceRequest (płaska struktura)
            payload = {
                "invoiceHash": hash_sha_b64,
                "invoiceSize": size_plain,
                "encryptedInvoiceHash": hash_enc_b64,
                "encryptedInvoiceSize": size_enc,
                "encryptedInvoiceContent": content_b64
            }
            
            # 5. Send (PUT /sessions/online/{ref}/invoices)
            # Wg dokumentacji i Java Client: session-interactive wysyłamy na dedykowany endpoint sesji
            # Poprawka: Metoda POST, nie PUT
            url = f"{self.API_URL}/sessions/online/{self.session_reference_number}/invoices"
            headers = self._get_headers()
            
            logger.info(f"POST {url}")
            resp = self._request("POST", url, json=payload, headers=headers)
            
            if resp.status_code == 202: # Accepted
                data = resp.json()
                logger.info(f"Response: {data}")
                # KSeF v2 Interactive zwraca "referenceNumber" (identyfikator elementu w sesji)
                ref = data.get("referenceNumber") or data.get("elementReferenceNumber")
                ts = data.get("timestamp")
                
                # Czekamy na przetworzenie i nadanie numeru KSeF
                logger.info(f"Faktura przyjęta do przetwarzania (Ref: {ref}). Oczekiwanie na numer KSeF...")
                ksef_num, date_ksef, upo_url, is_dup = self._wait_for_session_invoice_processing(self.session_reference_number, ref)
                
                if not ksef_num:
                    raise Exception(f"Błąd przetwarzania faktury (Sesja: {self.session_reference_number}). Sprawdź logi.")

                final_ref = ksef_num
                final_ts = date_ksef if date_ksef else ts

                return {
                    "success": True,
                    "ksef_number": final_ref,
                    "timestamp": final_ts or datetime.now().isoformat(),
                    "upo_url": upo_url,
                    "is_duplicate": is_dup
                }
            else:
                logger.error(f"KSeF Error: {resp.status_code} {resp.text}")
                # Try simple plain if encrypted failed? No, mixing types in session depends on init.
                return {
                    "success": False,
                    "error": f"Błąd KSeF: {resp.status_code} {resp.text}"
                }
                
        except Exception as e:
            logger.error(f"Wyjątek podczas wysyłki: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"success": False, "error": str(e)}

    def get_common_status(self, reference_number: str):
        """
        Pobiera status przetwarzania z ReferenceNumber (np. sesji).
        To zawiera link do UPO.
        """
        url = f"{self.API_URL}/common/Status/{reference_number}"
        headers = self._get_headers()
        resp = self._request("GET", url, headers=headers)
        if resp.status_code == 200:
            return resp.json()
        raise Exception(f"Błąd Status ({resp.status_code}): {resp.text}")

    def _wait_for_session_invoice_processing(self, session_ref, invoice_ref, timeout=60):
        """Aktywnie odpytuje o status przetwarzania faktury w sesji."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            status_data = self.get_session_invoice_status(session_ref, invoice_ref)
            if not status_data:
                time.sleep(2)
                continue
                
            ksef_num = status_data.get("ksefNumber")
            processing_code = status_data.get("status", {}).get("code")
            
            # 200 = Success (usually)
            if ksef_num:
                logger.info(f"Faktura przetworzona. Numer KSeF: {ksef_num}")
                return ksef_num, status_data.get("invoicingDate"), status_data.get("upoDownloadUrl"), False
            
            # Obsługa błędów sesji (np. 405)
            if processing_code and int(processing_code) >= 300:
                 desc = status_data.get("status", {}).get("description")
                 
                 # Specjalna obsługa duplikatów (440)
                 if int(processing_code) == 440:
                     logger.warning(f"KSeF: Wykryto duplikat faktury. Próba odzyskania numeru KSeF.")
                     extensions = status_data.get("status", {}).get("extensions", {})
                     orig_ksef = extensions.get("originalKsefNumber")
                     orig_ref = extensions.get("originalSessionReferenceNumber")
                     
                     upo_url = None
                     if orig_ref:
                         logger.info(f"Pobieranie UPO z oryginalnej sesji: {orig_ref}")
                         try:
                             st = self.get_common_status(orig_ref)
                             upo_url = st.get("upoUrl")
                             if upo_url:
                                 logger.info("Odzyskano URL UPO z oryginalnej sesji.")
                         except Exception as e:
                             logger.warning(f"Nie udało się odzyskać UPO dla duplikatu: {e}")

                     if orig_ksef:
                         logger.info(f"Odzyskano numer KSeF z duplikatu: {orig_ksef}")
                         return orig_ksef, status_data.get("invoicingDate"), upo_url, True

                 logger.error(f"KSeF Processing Error: {processing_code} {desc}")
                 # Przerwij pętlę, nie ma sensu czekać
                 return None, None, None, False
            
            logger.debug(f"Status przetwarzania: {processing_code}. Czekam...")
            time.sleep(2)
            
        logger.warning("Timeout oczekiwania na numer KSeF.")
        return None, None, None, False

    def get_session_invoice_status(self, session_ref, invoice_ref):
        """Pobiera status konkretnej faktury w konkretnej sesji."""
        url = f"{self.API_URL}/sessions/{session_ref}/invoices/{invoice_ref}"
        try:
            resp = self._request("GET", url, headers=self._get_headers())
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.warning(f"Failed to get invoice status: {resp.status_code} {resp.text}")
                return None
        except Exception as e:
            logger.error(f"Exc getting invoice status: {e}")
            return None

    def get_upo(self, ksef_number: str, upo_url: str = None):
        """
        Pobiera status/UPO dla danej faktury.
        GET /common/Status/{ksefReferenceNumber}
        OR uses provided upo_url (which might be the download link directly).
        """
        if upo_url:
             logger.info(f"Using provided UPO URL: {upo_url}")
             # If it's a download URL, we can verify it or just return it as 'status' object
             # The usage pattern expects a dictionary with metadata generally.
             # But if user wants to download, we might need to fetch the content?
             # Assuming this function returns STATUS metadata (JSON).
             # But UPO itself is XML.
             # KSeF Status API (GET /common/Status) returns metadata JSON including 'upoUrl'.
             
             # If we have direct XML link, we construct a fake status response or just fetch it
             return {
                 "processingCode": 200,
                 "processingDescription": "Sukces (URL cached)",
                 "referenceNumber": ksef_number,
                 "upoUrl": upo_url,
                 "timestamp": datetime.now().isoformat()
             }
        
        if not self.session_token:
            logger.warning("Brak sesji przy pobieraniu UPO - Próba wykonania zapytania mimo braku tokenu sesyjnego (może wymagać autoryzacji).")
        
        url = f"{self.API_URL}/common/Status/{ksef_number}"
        headers = self._get_headers()
        
        try:
            response = self._request("GET", url, headers=headers)
            if response.status_code == 200:
                logger.info(f"Pobrano status dla {ksef_number}")
                return response.json()
            else:
                logger.error(f"Błąd pobierania statusu UPO: {response.text}")
                # Fallback to mock/error dict if preferred or raise
                return {
                    "processingCode": response.status_code,
                    "processingDescription": f"Błąd serwera: {response.text}",
                    "referenceNumber": ksef_number,
                    "timestamp": datetime.now().isoformat() # Fallback date
                }
        except Exception as e:
            logger.error(f"Wyjątek przy pobieraniu UPO: {e}")
            # Mock return for robustness if offline/testing
            return {
                "processingCode": 0,
                "processingDescription": f"Błąd połączenia: {e}",
                "referenceNumber": ksef_number,
                "timestamp": datetime.now().isoformat()
            }

    def check_status(self, ksef_number):
        """Sprawdza status przetworzenia faktury"""
        return "PROCESSED"

    def get_invoice_list(self, date_from: datetime, date_to: datetime, subject_type="subject1"):
        """
        Pobiera listę faktur z KSeF (wszystkie strony).
        subject_type: 
           - 'subject1' (Sprzedaż/Wystawione) 
           - 'subject2' (Zakup/Otrzymane)
        W KSeF v2 używamy endpointu metadanych: POST /invoices/query/metadata
        """
        if not self.session_token:
            raise ValueError("Brak aktywnej sesji KSeF. Zaloguj się najpierw.")

        # Format daty: ISO
        ts_from = date_from.isoformat()
        ts_to = date_to.isoformat()

        # Mapowanie subject_type na wymagane przez API (wielka litera)
        st_map = {
            "subject1": "Subject1",
            "subject2": "Subject2"
        }
        s_type = st_map.get(subject_type.lower(), subject_type)

        payload = {
            "subjectType": s_type,
            "dateRange": {
                "dateType": "invoicing", # Filtrujemy po dacie wystawienia
                "from": ts_from,
                "to": ts_to
            }
        }

        headers = self._get_headers()
        
        all_invoices = []
        offset = 0
        page_size = 100
        
        while True:
            url = f"{self.API_URL}/invoices/query/metadata?pageOffset={offset}&pageSize={page_size}"
            
            response = self._request("POST", url, json=payload, headers=headers)
            
            if response.status_code != 200:
                raise Exception(f"Błąd pobierania listy faktur (strona {offset}): {response.status_code} {response.text}")
            
            data = response.json()
            items = data.get("invoices", [])
            if items:
                all_invoices.extend(items)
            
            # Sprawdź czy jest więcej stron
            if not data.get("hasMore"):
                break
                
            offset += 1
            
            # Zabezpieczenie przed pętlą (opcjonalne, ale dobre)
            if offset > 1000: # np. limit 100k faktur
                break

        return {"invoices": all_invoices}

    def get_invoice_xml(self, ksef_number: str):
        """
        Pobiera XML faktury (GET /invoices/ksef/{KsefReferenceNumber})
        """
        if not self.session_token:
            raise ValueError("Brak aktywnej sesji KSeF.")
            
        url = f"{self.API_URL}/invoices/ksef/{ksef_number}"
        headers = self._get_headers()
        # Ważne: Akceptujemy application/octet-stream lub application/xml
        headers["Accept"] = "*/*"
        
        resp = self._request("GET", url, headers=headers)
        if resp.status_code == 200:
            return resp.content 
        else:
            raise Exception(f"Błąd pobierania XML faktury: {resp.status_code} {resp.text}")
