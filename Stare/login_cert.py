import requests
import json
import base64
import time
from lxml import etree
import signxml
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography import x509
import logging

# Logger config
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_URL = "https://api-test.ksef.mf.gov.pl/v2"

# Paths
CERT_PATH = "ksef_keys/certificate.pem"
PRIVATE_KEY_PATH = "ksef_keys/private_key.pem"

def load_keys():
    with open(CERT_PATH, "rb") as f:
        cert_data = f.read()
        cert = x509.load_pem_x509_certificate(cert_data)
    
    with open(PRIVATE_KEY_PATH, "rb") as f:
        key_data = f.read()
        private_key = serialization.load_pem_private_key(key_data, password=None)
        
    return cert, private_key, cert_data, key_data

def get_challenge(nip):
    url = f"{API_URL}/auth/challenge"
    payload = {
        "contextIdentifier": {
            "type": "onip", # 'onip' for organization/company
            "identifier": nip
        }
    }
    resp = requests.post(url, json=payload, headers={"Content-Type": "application/json", "Accept": "application/json"})
    if resp.status_code != 200:
        # Fallback to 'Nip' type if 'onip' fails? V2 usually uses 'onip' for orgs.
        logger.error(f"Challenge error: {resp.text}")
        payload["contextIdentifier"]["type"] = "Nip" 
        payload["contextIdentifier"]["value"] = nip # V1 legacy style? Or 'identifier'->'value'?
        # The schema says:
        # TContextIdentifier choice: Nip, InternalId, etc.
        # But JSON API usually maps fields differently. 
        # API Client Java source: 'contextIdentifier' : { 'type': ..., 'identifier': ... }
        # Let's retry with 'Nip' and 'identifier'
        payload = { "contextIdentifier": { "type": "Nip", "identifier": nip } }
        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        resp.raise_for_status()

    return resp.json()

def build_auth_token_request_xml(challenge, nip):
    NS = "http://ksef.mf.gov.pl/auth/token/2.0"
    nsmap = {None: NS}
    
    root = etree.Element(f"{{{NS}}}AuthTokenRequest", nsmap=nsmap)
    
    challenge_el = etree.SubElement(root, f"{{{NS}}}Challenge")
    challenge_el.text = challenge
    
    context_el = etree.SubElement(root, f"{{{NS}}}ContextIdentifier")
    nip_el = etree.SubElement(context_el, f"{{{NS}}}Nip")
    nip_el.text = nip
    
    subject_el = etree.SubElement(root, f"{{{NS}}}SubjectIdentifierType")
    subject_el.text = "certificateSubject" # We sign with cert and identify by subject
    
    return root

def sign_xml_xades(xml_root, cert_pem, priv_key_pem):
    """
    Signs the XML using XAdES-BES.
    """
    signer = signxml.XMLSigner(
        method=signxml.methods.enveloped,
        signature_algorithm="rsa-sha256",
        digest_algorithm="sha256",
        c14n_algorithm="http://www.w3.org/2006/12/xml-c14n11"
    )
    
    signed_root = signer.sign(
        xml_root,
        key=priv_key_pem,
        cert=cert_pem,
        always_add_key_value=True # Often required
    )
    
    # KSeF requires specific XAdES structure (QualifyingProperties etc)
    # create_xades_signature usually adds it.
    
    return etree.tostring(signed_root, encoding="UTF-8")

def submit_signed_request(signed_xml_bytes):
    url = f"{API_URL}/auth/xades-signature" # Endpoint confirmed from Java code
    # Params: verifyCertificateChain=false (since self-signed)
    url += "?verifyCertificateChain=false" 
    
    headers = {
        "Content-Type": "application/xml",
        "Accept": "application/json"
    }
    
    resp = requests.post(url, data=signed_xml_bytes, headers=headers)
    if resp.status_code != 202:
         logger.error(f"Submit error: {resp.text}")
         resp.raise_for_status()
         
    return resp.json()

def wait_for_auth(ref_number, token):
    url = f"{API_URL}/auth/{ref_number}"
    headers = {
        "Authorization": f"Bearer {token}", # Special auth token for status check
        "Accept": "application/json"
    }
    
    for _ in range(30):
        time.sleep(2)
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            status = data.get("processingStatus")
            logger.info(f"Status: {status}")
            if status == 200:
                return True
        else:
             logger.warning(f"Status check failed: {resp.status_code}")
             
    return False

def redeem_token(auth_token):
    # This might be tricky. Usually 'redeem' gives the session token.
    # Check Java code: ksefClient.redeemToken(token) -> calls /auth/token/redeem?
    # No, URL.AUTH_TOKEN_REEDEM = "auth/token/redeem"
    # Wait, usually after InitSigned we check status, and then we have the Session?
    # No, AuthController calls 'ksefClient.redeemToken'
    # DefaultKsefClient.java: redeemToken:
    # "GET /auth/token/redeem" ? No. Java Url.java: "auth/token/redeem"
    # But usually REDEEM returns the Authorization Token (persistent) if we requested one?
    # Or Session Token?
    # The user wants "Generated Token" to put in settings. This corresponds to a long-lived Authorisation Token maybe?
    # If the flow in Java is "authStepByStepAsOwner", it seemingly returns "AuthOperationStatusResponse" structure.
    
    # Actually wait. If we use this flow to just *Get a Token*, we want `auth/token/redeem` likely. Only if we requested token generation?
    # But AuthTokenRequest xml didn't ask for generic token generation explicitly?
    # Ah, `AuthTokenRequest` serves to InitSession OR GenerateToken depending on context?
    # In V1/V2 distinct endpoints?
    # If we want a long-lived token (like "Generuj Token" in web app), we might need `POST /tokens` endpoint (Generate Token) authenticated by Session.
    
    # Strategy:
    # 1. Login to a Session using Certificate (InitSigned).
    # 2. Once Session is active, use Session Token to call `POST /tokens` (Generate Token).
    # 3. This Token is what the user needs.
    
    # HOWEVER, the 'InitSigned' flow itself might return a SessionToken in the status response upon completion.
    
    # Let's assume InitSigned gives us a Session.
    
    # Wait, "redeemToken" in Java seems to just call GET /auth/token/redeem using the temp token?
    # No, let's look at `DefaultKsefClient.redeemToken` implementation (didn't read it).
    
    # Let's try to just get the Session working first.
    pass

def init_session_by_cert(nip):
    logger.info("1. Loading keys...")
    cert_obj, priv_key_obj, cert_bytes, priv_key_bytes = load_keys()
    
    logger.info("2. Getting challenge...")
    challenge_data = get_challenge(nip)
    challenge = challenge_data["challenge"]
    logger.info(f"Challenge: {challenge}")
    
    logger.info("3. Building XML...")
    xml_root = build_auth_token_request_xml(challenge, nip)
    
    logger.info("4. Signing XML...")
    # signxml needs pem bytes
    signed_xml = sign_xml_xades(xml_root, cert_bytes, priv_key_bytes)
    # Debug: save signed xml
    with open("signed_request.xml", "wb") as f:
        f.write(signed_xml)
        
    logger.info("5. Submitting...")
    init_resp = submit_signed_request(signed_xml)
    ref_num = init_resp["referenceNumber"]
    auth_token = init_resp["authenticationToken"]["token"]
    logger.info(f"Ref: {ref_num}")
    
    logger.info("6. Waiting for session...")
    if wait_for_auth(ref_number=ref_num, token=auth_token):
        logger.info("Session Active (or Auth Complete).")
        # Check if we have session token?
        # Status response usually contains session token if it was session init.
        # Let's check the last status response again.
        
        # We need to make one more call to status to get the final data
        url = f"{API_URL}/auth/{ref_num}"
        headers = {"Authorization": f"Bearer {auth_token}", "Accept": "application/json"}
        resp = requests.get(url, headers=headers)
        data = resp.json()
        print("Final Status Response:")
        print(json.dumps(data, indent=2))
        
        session_token = data.get("sessionToken", {}).get("token")
        if session_token:
            return session_token, auth_token
            
    return None, None

def generate_api_token(session_token):
    """
    Generates a long-lived API token using the active session.
    POST /tokens
    """
    url = f"{API_URL}/tokens"
    headers = {
        "SessionToken": session_token,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    # Minimal payload?
    payload = {
        "credentialsRoleList": [
            {
               "roleType": "invoice_read", # Check enum
               "roleDescription": "Odczyt faktur"
            },
             {
               "roleType": "invoice_write",
               "roleDescription": "Wystawianie faktur"
            }
        ],
        "description": "Token wygenerowany przez skrypt Python"
    }
    # Enum might be: 'InvoiceRead', 'InvoiceWrite'?
    # Checking docs/openapi... 
    # RoleType: InvoiceRead, InvoiceWrite, PaymentRequestWrite, CredentialsRead, CredentialsManage, EnforcementOperations...
    # Case sensitive?
    
    payload = {
        "credentialsRoleList": [
            {"roleType": "InvoiceRead", "roleDescription": "Odczyt"},
            {"roleType": "InvoiceWrite", "roleDescription": "Zapis"}
        ],
        "description": "AutoToken"
    }
    
    resp = requests.post(url, json=payload, headers=headers)
    if resp.status_code == 200:
        return resp.json()["authorizationToken"] # token
    else:
        logger.error(f"Token generation failed: {resp.text}")
        return None

if __name__ == "__main__":
    NIP = "8882855215"
    s_token, a_token = init_session_by_cert(NIP)
    if s_token:
        print(f"\nSESJA NAWIĄZANA. SessionToken: {s_token}")
        print("Generuję token długoterminowy...")
        api_token = generate_api_token(s_token)
        if api_token:
            print(f"\n=== TWÓJ TOKEN API (WKLEJ DO PROGRAMU) ===\n{api_token}\n===========================================")
            # Save to file maybe?
            with open("my_ksef_token.txt", "w") as f:
                f.write(api_token)
        else:
            print("Nie udało się wygenerować tokenu API.")
    else:
        print("Nie udało się zalogować certyfikatem.")
