import requests
import os

API_URL = "https://api-demo.ksef.mf.gov.pl/v2"
PUBLIC_KEY_PATH = "ksef/public_key_test.pem"

def fetch_and_save_key():
    url = f"{API_URL}/security/public-key-certificates"
    print(f"Fetching from {url}...")
    try:
        resp = requests.get(url, headers={"Accept": "application/json"})
        resp.raise_for_status()
        data = resp.json()
        print("Response received.")
        
        # Handle structure
        certificates = data["publicKeyCertificateList"] if "publicKeyCertificateList" in data else data
        
        target_cert = None
        for cert in certificates:
             print(f"Checking cert serial: {cert.get('serialNumber')} usage: {cert.get('usage')}")
             # Looking for 'encipherment' or 'KsefTokenEncryption' or general usage?
             # For Session Encryption (symmetric key), we usually use the same key or one marked for encryption.
             # Usage usually contains "encryption" or is generic.
             # KSeF documentation says we need key for encrypting the AES key.
             # Usually usage: "challenge" or just standard.
             # Let's see what usages available.
             usage = cert.get("usage", [])
             if "encryption" in str(usage).lower() or "kseftokenencryption" in str(usage).lower(): # Broad check
                  target_cert = cert
                  # Prefer the one with latest date if multiple? Usually only one valid for enc.
        
        if target_cert:
            key_content = target_cert["certificate"]
            print(f"Found certificate for encryption. Serial: {target_cert.get('serialNumber')}")
            
            pem_key = f"-----BEGIN CERTIFICATE-----\n{key_content}\n-----END CERTIFICATE-----"
            
            # Read existing
            if os.path.exists(PUBLIC_KEY_PATH):
                with open(PUBLIC_KEY_PATH, "r") as f:
                    existing = f.read()
                if existing.strip() == pem_key.strip():
                     print("Key is already up to date.")
                     return
                else:
                     print("Local key differs from API key. Updating...")
            else:
                print("Local key does not exist. Creating...")
                
            with open(PUBLIC_KEY_PATH, "w") as f:
                f.write(pem_key)
            print("Key saved.")
        else:
            print("No suitable certificate found.")
            print("Full list:", certificates)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fetch_and_save_key()
