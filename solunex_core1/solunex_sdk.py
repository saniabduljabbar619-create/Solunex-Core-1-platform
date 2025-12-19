# solunex_sdk.py
# ----------------------------------------
# Solunex Core 1 - Python Client SDK
# Hybrid Device ID (auto + override)
# ----------------------------------------

import requests
import subprocess
import platform
import uuid
import json


class SolunexLicenseClient:
    def __init__(self, base_url: str, device_id: str = None, timeout: int = 6):
        """
        base_url = "http://127.0.0.1:8000/api/license"
        device_id = None → auto detect
        """
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.device_id = device_id or self._auto_device_id()

    # ----------------------------------------------------------------------
    # AUTO DETECT SYSTEM DEVICE ID
    # ----------------------------------------------------------------------
    def _auto_device_id(self):
        system = platform.system().lower()

        try:
            if system == "windows":
                return self._get_windows_uuid()
            elif system == "linux":
                return self._get_linux_uuid()
            elif system == "darwin":
                return self._get_mac_uuid()

        except Exception:
            pass  # fallback next

        # fallback → stable python-generated
        return str(uuid.UUID(int=uuid.getnode()))

    def _get_windows_uuid(self):
        try:
            result = subprocess.check_output("wmic csproduct get uuid", shell=True)
            lines = result.decode().split("\n")
            return lines[1].strip()
        except:
            return None

    def _get_linux_uuid(self):
        try:
            with open("/etc/machine-id", "r") as f:
                return f.read().strip()
        except:
            return None

    def _get_mac_uuid(self):
        try:
            cmd = "ioreg -rd1 -c IOPlatformExpertDevice | grep IOPlatformUUID"
            result = subprocess.check_output(cmd, shell=True).decode()
            return result.split('"')[-2]
        except:
            return None

    # ----------------------------------------------------------------------
    # INTERNAL HTTP WRAPPER
    # ----------------------------------------------------------------------
    def _request(self, method, path, **kwargs):
        url = f"{self.base}{path}"

        try:
            res = requests.request(method, url, timeout=self.timeout, **kwargs)
        except Exception as ex:
            return {"error": True, "detail": str(ex)}

        # always try json
        try:
            data = res.json()
        except:
            data = {"detail": res.text}

        data["_status_code"] = res.status_code
        return data

    # ----------------------------------------------------------------------
    # PUBLIC CLIENT METHODS
    # ----------------------------------------------------------------------

    def check(self, license_key: str):
        """Validate license WITHOUT binding device."""
        return self._request("GET", f"/check/{license_key}")

    def validate(self, license_key: str, meta: dict = None):
        """POST validate + metadata (optional)."""
        payload = {
            "license_key": license_key,
            "device_id": self.device_id,
            "meta": meta or {}
        }
        return self._request("POST", "/validate", json=payload)

    def activate(self, license_key: str, meta: dict = None):
        """Bind/Activate device to this license."""
        payload = {
            "license_key": license_key,
            "device_id": self.device_id,
            "meta": meta or {}
        }
        return self._request("POST", "/activate", json=payload)

    def info(self, license_key: str):
        """Get general license information."""
        return self._request("GET", f"/info/{license_key}")


# ----------------------------------------------------------------------
# DEMO USAGE (optional)
# ----------------------------------------------------------------------
if __name__ == "__main__":

    BASE = "http://127.0.0.1:8000/api/license"
    KEY = "SOL-W56J-UPH1-N3YG-2B9R-EA"

    sdk = SolunexLicenseClient(base_url=BASE)

    print("\n--- Device ID:", sdk.device_id)

    print("\n1) Validate BEFORE activation")
    print(json.dumps(sdk.check(KEY), indent=4))

    print("\n2) Activate")
    print(json.dumps(sdk.activate(KEY, meta={"os": platform.platform()}), indent=4))

    print("\n3) Validate AFTER activation")
    print(json.dumps(sdk.check(KEY), indent=4))

    print("\n4) Info endpoint")
    print(json.dumps(sdk.info(KEY), indent=4))
