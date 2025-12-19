import time, json, hmac, hashlib, uuid
import requests

BASE = "http://127.0.0.1:8000/api/v1/license"

API_KEY = "r03d814ec2e04c80dc9eb7bf2076d7907b2f1933a9909bee227dd472c531a2dda"
HMAC_SECRET = "1f8c4a41d42b6e7e219a02c9d257fbafc9b171f4a5d8b011bf4dc9a2f03d718a" 

def canonical_json(data):
    if not data:
        return ""
    return json.dumps(data, separators=(",", ":"), sort_keys=True)

def sign(method, path, body):
    ts = str(int(time.time()))
    nonce = uuid.uuid4().hex
    body_str = canonical_json(body)

    base = f"{ts}:{nonce}:{method}:{path}:{body_str}"
    sig = hmac.new(
        HMAC_SECRET.encode(),
        base.encode(),
        hashlib.sha256
    ).hexdigest()

    return ts, nonce, sig, body_str


def post(path, payload):
    full_path = path  # path must match EXACTLY server.url.path including prefix
    ts, nonce, sig, body = sign("POST", full_path, payload)

    headers = {
        "X-Solunex-Signature": sig,
        "X-Solunex-Timestamp": ts,
        "X-Solunex-Nonce": nonce,
        "X-API-KEY": API_KEY,
        "Content-Type": "application/json"
    }

    print("\nPOST", full_path)
    res = requests.post(BASE + path[len("/api/v1/license"):], headers=headers, data=body)
    print("Status:", res.status_code)
    print(res.text)
    return res


def get(path):
    full_path = path
    ts, nonce, sig, body = sign("GET", full_path, "")

    headers = {
        "X-Solunex-Signature": sig,
        "X-Solunex-Timestamp": ts,
        "X-Solunex-Nonce": nonce,
        "X-API-KEY": API_KEY
    }

    print("\nGET", full_path)
    res = requests.get(BASE + path[len("/api/v1/license"):], headers=headers)
    print("Status:", res.status_code)
    print(res.text)
    return res


# ---------------------------------------------------------
# TEST: CHANGE THIS LICENSE KEY
# ---------------------------------------------------------
LICENSE = input("Enter license key: ").strip()

print("\n===== 1) VALIDATE BEFORE ACTIVATION =====")
post("/api/v1/license/validate", {
    "license_key": LICENSE,
    "app_id": "SOL-LAB"
})

print("\n===== 2) ACTIVATE DEVICE 1 =====")
post("/api/v1/license/activate", {
    "license_key": LICENSE,
    "device_id": "DEVICE-111",
    "meta": {"os": "Windows 11"}
})

print("\n===== 3) ACTIVATE DEVICE 2 =====")
post("/api/v1/license/activate", {
    "license_key": LICENSE,
    "device_id": "DEVICE-222",
    "meta": {"os": "Windows 10"}
})

print("\n===== 4) GET CHECK =====")
get(f"/api/v1/license/check/{LICENSE}")

print("\n===== 5) GET INFO =====")
get(f"/api/v1/license/info/{LICENSE}")
