import requests, time, json, hmac, hashlib, uuid, time
from datetime import datetime

BASE = "http://127.0.0.1:8000/api/v1/license"
ORDER_API = "http://127.0.0.1:8000/api/internal/orders"

API_KEY = "r03d814ec2e04c80dc9eb7bf2076d7907b2f1933a9909bee227dd472c531a2dda"
HMAC_SECRET = "1f8c4a41d42b6e7e219a02c9d257fbafc9b171f4a5d8b011bf4dc9a2f03d718a"   


# ---------------------------------------------------------
# HMAC SIGNATURE GENERATOR (same logic as server)
# ---------------------------------------------------------
def sign(method, path, body=""):
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    base = f"{timestamp}:{nonce}:{method.upper()}:{path}:{body}"
    signature = hmac.new(HMAC_SECRET.encode(), base.encode(), hashlib.sha256).hexdigest()

    return {
        "x-solunex-timestamp": timestamp,
        "x-solunex-nonce": nonce,
        "x-solunex-signature": signature
    }


def jprint(title, url, r):
    print(f"\n===== {title} =====\n")
    print(f"{r.status_code} {url}")
    try:
        print(json.dumps(r.json(), indent=2))
    except:
        print(r.text)


# ---------------------------------------------------------
# 1) CREATE NEW LICENSE (simulate purchase)
# ---------------------------------------------------------
order_payload = {
    "order_id": "ORDER-TEST-1001",
    "email": "abduljabbarsani1212@gmail.com",
    "name": "Solunex client",
    "product": "SOL-LAB",
    "amount": 100.00,
    "currency": "USD",
}

print("\n\n===== 1) Creating New License (Purchase Simulation) =====")
res = requests.post(ORDER_API, json=order_payload)
jprint("ORDER → LICENSE ISSUED", ORDER_API, res)

try:
    license_key = res.json().get("license_key")
except:
    license_key = None

print("\nNEW LICENSE =", license_key)
if not license_key:
    print("❌ Could not create license. Stopping.")
    exit()

time.sleep(1)


# ---------------------------------------------------------
# 2) VALIDATE LICENSE (Before activation)
# ---------------------------------------------------------
path = "/api/v1/license/validate"
body = json.dumps({"license_key": license_key})
headers = {
    "Content-Type": "application/json",
    "X-API-KEY": API_KEY,
}
headers.update(sign("POST", path, body))

res = requests.post(BASE + "/validate", data=body, headers=headers)
jprint("VALIDATE BEFORE ACTIVATION", path, res)

time.sleep(1)


# ---------------------------------------------------------
# 3) ACTIVATE DEVICE 1
# ---------------------------------------------------------
activation_body = json.dumps({
    "license_key": license_key,
    "device_id": "DEVICE-NEW-111",
    "meta": {"os": "Windows 11", "cpu": "AMD Ryzen"}
})

path = "/api/v1/license/activate"
headers = {
    "Content-Type": "application/json",
    "X-API-KEY": API_KEY,
}
headers.update(sign("POST", path, activation_body))

res = requests.post(BASE + "/activate", data=activation_body, headers=headers)
jprint("ACTIVATE DEVICE 1", path, res)

time.sleep(1)


# ---------------------------------------------------------
# 4) ACTIVATE DEVICE 2 (should fail if max_devices = 1)
# ---------------------------------------------------------
activation_body_2 = json.dumps({
    "license_key": license_key,
    "device_id": "DEVICE-NEW-222",
    "meta": {"os": "Windows 10", "cpu": "Intel Core i5"}
})

headers = {
    "Content-Type": "application/json",
    "X-API-KEY": API_KEY,
}
headers.update(sign("POST", "/api/v1/license/activate", activation_body_2))

res = requests.post(BASE + "/activate", data=activation_body_2, headers=headers)
jprint("ACTIVATE DEVICE 2 (Expected fail)", "/api/v1/license/activate", res)

time.sleep(1)


# ---------------------------------------------------------
# 5) CHECK LICENSE
# ---------------------------------------------------------
path = f"/api/v1/license/check/{license_key}"
headers = sign("GET", path)
headers["X-API-KEY"] = API_KEY

res = requests.get(BASE + f"/check/{license_key}", headers=headers)
jprint("GET CHECK", path, res)

time.sleep(1)


# ---------------------------------------------------------
# 6) GET INFO
# ---------------------------------------------------------
path = f"/api/v1/license/info/{license_key}"
headers = sign("GET", path)
headers["X-API-KEY"] = API_KEY

res = requests.get(BASE + f"/info/{license_key}", headers=headers)
jprint("GET INFO", path, res)

print("\n===== TEST COMPLETE =====\n")
