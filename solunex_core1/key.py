# api_test.py
# End-to-end test for the Public License API (Core 1)
import requests
import json
from datetime import datetime

BASE = "http://127.0.0.1:8000"
API_KEY = "r03d814ec2e04c80dc9eb7bf2076d7907b2f1933a9909bee227dd472c531a2dda"   # from config.LICENSE_API_KEY

LICENSE_KEY = "SOL-W56J-UPH1-N3YG-2B9R-EA"  # change to any license in DB
DEVICE_ID = "DEV-" + datetime.utcnow().strftime("%H%M%S")
APP_ID = "SOL-LAB"                        # match your app

headers = {
    "Content-Type": "application/json",
    "X-API-KEY": API_KEY
}

def pretty(title, data):
    print("\n===============================")
    print(title)
    print("===============================")
    print(json.dumps(data, indent=4))


# ----------------------------------------------
# STEP 1 — Validate license BEFORE activation
# ----------------------------------------------
payload = {
    "license_key": LICENSE_KEY,
    "device_id": DEVICE_ID,
    "app_id": APP_ID
}

r = requests.post(f"{BASE}/api/v1/license/validate", headers=headers, json=payload)
pretty("1) Validate BEFORE Activation", r.json())


# ----------------------------------------------
# STEP 2 — Activate license (bind device)
# ----------------------------------------------
payload = {
    "license_key": LICENSE_KEY,
    "device_id": DEVICE_ID,
    "app_id": APP_ID,
    "device_meta": {
        "os": "Windows",
        "version": "1.0",
        "cpu": "Intel"
    }
}

r = requests.post(f"{BASE}/api/v1/license/activate", headers=headers, json=payload)
pretty("2) Activate License / Bind Device", r.json())


# ----------------------------------------------
# STEP 3 — Validate AGAIN (should now be bound)
# ----------------------------------------------
payload = {
    "license_key": LICENSE_KEY,
    "device_id": DEVICE_ID,
    "app_id": APP_ID
}

r = requests.post(f"{BASE}/api/v1/license/validate", headers=headers, json=payload)
pretty("3) Validate AFTER Activation", r.json())


# ----------------------------------------------
# STEP 4 — Check license (GET version)
# ----------------------------------------------
r = requests.get(f"{BASE}/api/v1/license/check/{LICENSE_KEY}", headers={"X-API-KEY": API_KEY})
pretty("4) GET /check/<license_key>", r.json())


# ----------------------------------------------
# STEP 5 — Admin-lite info
# ----------------------------------------------
r = requests.get(f"{BASE}/api/v1/license/info/{LICENSE_KEY}", headers={"X-API-KEY": API_KEY})
pretty("5) GET /info/<license_key>", r.json())
