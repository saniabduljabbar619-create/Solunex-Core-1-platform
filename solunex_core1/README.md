# 🔐 Solunex Core 1 — Public License API Documentation

## 🌍 BASE URL

```
https://yourserver.com/api/license
```

Local development:
```
http://127.0.0.1:8000/api/license
```

---

# 1️⃣ CHECK / VALIDATE LICENSE  
### **GET /api/license/check/{license_key}**

Validate a license **without binding a device**.

### Purpose
- Check validity before login  
- Does *not* bind device  
- Used on app startup  

### ▶ Request
```
GET /api/license/check/SOL-XXXX-XXXX-XXXX-XXXX-XX
```

### ✔ Success (200)
```json
{
  "valid": true,
  "status": "active",
  "expires_at": "2029-11-15T17:40:00",
  "bound_devices": [
    {
      "device_id": "DEVICE-UUID-222",
      "bound_at": "2025-11-17T00:09:45.238279",
      "meta": {}
    }
  ],
  "message": null
}
```

### ❌ Invalid (200 but `valid:false`)
```json
{
  "valid": false,
  "status": "revoked",
  "expires_at": "2029-11-15T17:40:00",
  "bound_devices": null,
  "message": "License revoked"
}
```

---

# 2️⃣ ACTIVATE / BIND DEVICE  
### **POST /api/license/activate**

Bind a device to the license.

### ▶ Request
```
POST /api/license/activate
Content-Type: application/json
```

```json
{
  "license_key": "SOL-W56J-UPH1-N3YG-2B9R-EA",
  "device_id": "DEVICE-UUID-222",
  "meta": {
    "os": "Windows",
    "version": "1.0",
    "device_name": "Office PC A"
  }
}
```

### ✔ Success
```json
{
  "activated": true,
  "bound_devices": [
    {
      "device_id": "DEVICE-UUID-222",
      "bound_at": "2025-11-17T00:09:45.238279",
      "meta": {
        "os": "Windows",
        "version": "1.0",
        "device_name": "Office PC A"
      }
    }
  ],
  "max_devices": 1
}
```

### ❌ Max Devices Reached
```json
{"detail": "Max devices reached"}
```

### ❌ Revoked License
```json
{"detail": "License revoked"}
```

---

# 3️⃣ VALIDATE (POST VERSION)  
### **POST /api/license/validate**

Same as `/check`, but allows optional metadata.

### ▶ Request
```json
{
  "license_key": "SOL-XXXX",
  "device_id": "DEVICE-UUID-1",
  "meta": {
    "os": "Windows 11",
    "app_version": "6.2"
  }
}
```

Response is identical to `/check`.

---

# 4️⃣ LICENSE INFORMATION  
### **GET /api/license/info/{license_key}**

Returns readable license details.

### ▶ Example
```
GET /api/license/info/SOL-W56J-UPH1-N3YG-2B9R-EA
```

### ✔ Response
```json
{
  "id": 1,
  "license_key": "SOL-W56J-UPH1-N3YG-2B9R-EA",
  "user_email": "saniabduljabbar619@gmail.com",
  "app_id": "SOL-LAB",
  "status": "active",
  "generated_at": "2025-11-16T23:40:16",
  "expires_at": "2029-11-15T17:40:00",
  "is_bound": true,
  "max_devices": 1,
  "bound_devices": [
    {
      "device_id": "DEVICE-UUID-222",
      "bound_at": "2025-11-17T00:09:45.238279",
      "meta": {}
    }
  ]
}
```

---

# 5️⃣ LICENSE STATUS VALUES

| Status     | Meaning                |
|------------|------------------------|
| active     | Valid & usable         |
| revoked    | Permanently blocked    |
| expired    | Past expiration date   |
| pending    | Future use (trial etc.) |

---

# 6️⃣ ERROR CODES

### 404
```json
{"detail": "License not found"}
```

### 400
```json
{"detail": "Missing license_key"}
```

### 403
```json
{"detail": "License revoked"}
```

---

# 7️⃣ DEVICE BINDING RULES

| Rule                             | Description                |
|----------------------------------|----------------------------|
| License may have **1–N devices** | via `max_devices`          |
| Binding = activation             |                            |
| Exceeding device limit → fail    |                            |
| Revoked license → blocked        | all validation fails       |

---

# 8️⃣ VERIFIED TEST RESULTS  
You confirmed:

```
VALID: true
REVOKED: blocked
ACTIVATION: limited by max_devices
```

Everything functions exactly as expected.

---

# 9️⃣ Python Demo Client

```python
import requests, json

BASE = "http://127.0.0.1:8000/api/license"
KEY = "SOL-W56J-UPH1-N3YG-2B9R-EA"

print("1) Validate BEFORE activation")
print(requests.get(f"{BASE}/check/{KEY}").json())

print("\n2) Activate")
print(requests.post(f"{BASE}/activate", json={
    "license_key": KEY,
    "device_id": "DEVICE-UUID-222"
}).json())

print("\n3) Validate AFTER activation")
print(requests.get(f"{BASE}/check/{KEY}").json())

print("\n4) Info endpoint")
print(requests.get(f"{BASE}/info/{KEY}").json())
```

---

# ✅ End of Solunex Core 1 Public API  
This API is fully stable, production-ready, and tested.