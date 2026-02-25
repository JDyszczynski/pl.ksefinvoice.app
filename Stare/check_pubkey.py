import requests

try:
    url = "https://ksef.mf.gov.pl/api/web/v2/payment/public-key"
    print(f"Checking {url}...")
    resp = requests.get(url, timeout=5)
    print(f"Status: {resp.status_code}")
    print(f"Content: {resp.text[:200]}")
except Exception as e:
    print(f"Error: {e}")
