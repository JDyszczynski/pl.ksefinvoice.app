import requests
import json
import base64
from cryptography import x509
from cryptography.hazmat.backends import default_backend

def check_keys():
    url = "https://api-demo.ksef.mf.gov.pl/v2/security/public-key-certificates"
    print(f"Fetching {url}...")
    resp = requests.get(url, headers={"Accept": "application/json"})
    data = resp.json()
    
    certs = data["publicKeyCertificateList"] if "publicKeyCertificateList" in data else data
    
    print(f"Found {len(certs)} certificates.")
    
    for i, cert in enumerate(certs):
        print(f"\n--- Certificate {i+1} ---")
        print(f"Serial: {cert.get('serialNumber')}")
        print(f"Usage: {cert.get('usage')}")
        
        # Decode and parse cert details
        try:
            cert_bytes = base64.b64decode(cert['certificate'])
             # Or is it raw PEM string inside JSON? Usually Base64 or PEM string.
             # The existing code treats it as content to wrap in BEGIN/END.
             # Let's try to load it.
            try:
                 # Check if it has headers
                 if "-----BEGIN" in cert['certificate']:
                      c = x509.load_pem_x509_certificate(cert['certificate'].encode('utf-8'), default_backend())
                 else:
                      # Maybe base64 der?
                      # Or just body of PEM
                      pem = f"-----BEGIN CERTIFICATE-----\n{cert['certificate']}\n-----END CERTIFICATE-----"
                      c = x509.load_pem_x509_certificate(pem.encode('utf-8'), default_backend())
                 
                 print(f"Subject: {c.subject}")
                 print(f"Issuer: {c.issuer}")
                 print(f"Not Valid Before: {c.not_valid_before}")
                 print(f"Not Valid After: {c.not_valid_after}")
            except Exception as e:
                print(f"Parse error: {e}")

        except Exception as e:
             print(f"Error processing cert: {e}")

if __name__ == "__main__":
    check_keys()
