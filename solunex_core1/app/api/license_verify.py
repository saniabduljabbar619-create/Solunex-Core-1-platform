# app/api/license_verify.py
# -*- coding: utf-8 -*-
"""
License Verification & Activation API for Solunex Core-1
- POST /license/validate   : Validate license (Core-2 calls when user enters key)
- POST /license/activate   : Activate & bind device (App calls on first run)
- GET  /license/ping/{key} : Lightweight heartbeat (App runtime)
"""

from fastapi import APIRouter, Depends, Header, Request, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, Dict, Any
import traceback

from config import SessionLocal, LICENSE_API_KEY
from app.models.license_model import License, LicenseStatus
from app.models.logs_model import log_event

# 🔐 HMAC signer dependency
from app.utils.signer import require_hmac

router = APIRouter(prefix="/license", tags=["license"])


# -------------------------
# Security: API key dependency
# -------------------------
def verify_api_key(x_solunex_key: str = Header(None)):
    """Ensure only Core-2 and official apps can call license APIs."""
    if LICENSE_API_KEY and x_solunex_key != LICENSE_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Solunex API Key."
        )
    return True


# -------------------------
# DB dependency
# -------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -------------------------
# Request models
# -------------------------
class ValidateRequest(BaseModel):
    license_key: str
    device_id: Optional[str] = None
    app_id: Optional[str] = None
    machine_meta: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = None           # 🆕 compatibility alias


class ActivateRequest(BaseModel):
    license_key: str
    device_id: str
    app_id: Optional[str] = None
    machine_meta: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = None           # 🆕 compatibility alias


# -------------------------
# Helper: normalize meta
# -------------------------
def extract_meta(payload):
    """
    Normalize incoming metadata to support both:
    - machine_meta
    - meta
    """
    if getattr(payload, "machine_meta", None):
        return payload.machine_meta or {}
    if getattr(payload, "meta", None):
        return payload.meta or {}
    return {}


# -------------------------
# Helper: license -> dict
# -------------------------
def license_to_dict(lic: License):
    return {
        "license_key": lic.license_key,
        "user_email": lic.user_email,
        "app_id": lic.app_id,
        "status": lic.status.value if isinstance(lic.status, LicenseStatus) else str(lic.status),
        "is_bound": bool(lic.is_bound),
        "max_devices": lic.max_devices,
        "bound_devices": lic.bound_devices or [],
        "generated_at": lic.generated_at.isoformat() if lic.generated_at else None,
        "expires_at": lic.expires_at.isoformat() if lic.expires_at else None,
        "meta": lic.meta or {}
    }


# -------------------------
# Endpoint: Validate license
# -------------------------
@router.post("/validate")
def validate_license(
    payload: ValidateRequest,
    request: Request,
    _sig = Depends(require_hmac),     # 🔐 require HMAC
    db: Session = Depends(get_db),
    _ = Depends(verify_api_key)       # API key second
):
    lk = (payload.license_key or "").strip()
    if not lk:
        raise HTTPException(status_code=422, detail="license_key is required")

    now = datetime.utcnow()

    try:
        lic: License = db.query(License).filter(License.license_key == lk).first()
    except Exception:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="DB error")

    def _log(action, details=None):
        try:
            log_event(db, user=payload.license_key, action=action, details=details, endpoint="/license/validate")
        except Exception:
            pass

    if not lic:
        _log("validate_missing", f"License {lk} not found")
        raise HTTPException(status_code=404, detail="License not found")

    # Status checks
    if lic.status == LicenseStatus.revoked:
        _log("validate_revoked", f"{lk} revoked")
        return JSONResponse(status_code=403, content={"valid": False, "status": "revoked", "message": "License revoked"})

    if lic.expires_at and lic.expires_at < now:
        try:
            lic.status = LicenseStatus.expired
            db.add(lic); db.commit()
        except Exception:
            db.rollback()
        _log("validate_expired", f"{lk} expired")
        return JSONResponse(status_code=403, content={"valid": False, "status": "expired", "message": "License expired"})

    # App match
    if payload.app_id and lic.app_id != payload.app_id:
        _log("validate_app_mismatch", f"{lk} mismatch")
        return JSONResponse(status_code=403, content={"valid": False, "status": "app_mismatch", "message": "License not valid for this application"})

    # Bound license handling
    if lic.is_bound:
        device_id = payload.device_id
        bound = lic.bound_devices or []

        if not device_id:
            _log("validate_requires_device", "device missing")
            return JSONResponse(status_code=422, content={"valid": False, "status": "requires_device", "message": "Device ID required"})

        found = next((d for d in bound if d.get("device_id") == device_id), None)

        if found:
            lic.last_verified = now
            try:
                db.add(lic); db.commit()
            except Exception:
                db.rollback()

            _log("validate_ok_bound", f"{lk} ok")
            return {"valid": True, "status": "active", "license": license_to_dict(lic)}

        # can bind?
        maxd = lic.max_devices if lic.max_devices is not None else 1
        if len(bound) < maxd or maxd == 0:
            _log("validate_can_bind", f"{lk} can bind")
            return {"valid": True, "status": "can_bind", "license": license_to_dict(lic)}

        _log("validate_limit", "limit reached")
        return JSONResponse(status_code=403, content={"valid": False, "status": "device_limit_reached", "message": "Device limit reached"})

    # unbound license
    lic.last_verified = now
    try:
        db.add(lic); db.commit()
    except Exception:
        db.rollback()

    _log("validate_ok_unbound", f"{lk} ok")
    return {"valid": True, "status": "active", "license": license_to_dict(lic)}


# -------------------------
# Endpoint: Activate license
# -------------------------
@router.post("/activate")
def activate_license(
    payload: ActivateRequest,
    request: Request,
    _sig = Depends(require_hmac),     # 🔐 require HMAC
    db: Session = Depends(get_db),
    _ = Depends(verify_api_key)
):
    lk = (payload.license_key or "").strip()
    if not lk:
        raise HTTPException(status_code=422, detail="license_key is required")

    now = datetime.utcnow()
    incoming_meta = extract_meta(payload)       # 🆕 meta normalization

    try:
        lic: License = db.query(License).filter(License.license_key == lk).with_for_update().first()
    except Exception:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="DB error on lookup")

    def _log(action, details=None):
        try:
            log_event(db, user=payload.device_id or payload.license_key, action=action, details=details, endpoint="/license/activate")
        except Exception:
            pass

    if not lic:
        _log("activate_missing", f"{lk} missing")
        raise HTTPException(status_code=404, detail="License not found")

    if lic.status == LicenseStatus.revoked:
        _log("activate_revoked", f"{lk} revoked")
        return JSONResponse(status_code=403, content={"activated": False, "status": "revoked", "message": "License revoked"})

    if lic.expires_at and lic.expires_at < now:
        lic.status = LicenseStatus.expired
        try:
            db.add(lic); db.commit()
        except Exception:
            db.rollback()

        _log("activate_expired", f"{lk} expired")
        return JSONResponse(status_code=403, content={"activated": False, "status": "expired", "message": "License expired"})

    if payload.app_id and lic.app_id != payload.app_id:
        _log("activate_app_mismatch", f"{lk} mismatch")
        return JSONResponse(status_code=403, content={"activated": False, "status": "app_mismatch", "message": "License not valid for this application"})

    # -------------------------
    # Unbound license: just mark active
    # -------------------------
    if not lic.is_bound:
        lic.last_verified = now
        lic.status = LicenseStatus.active
        try:
            db.add(lic); db.commit()
        except Exception:
            db.rollback()

        _log("activate_ok_unbound", f"{lk} activated")
        return {"activated": True, "status": "active", "license": license_to_dict(lic)}

    # -------------------------
    # Bound license logic
    # -------------------------
    device_id = payload.device_id
    if not device_id:
        _log("activate_requires_device", "missing")
        return JSONResponse(status_code=422, content={"activated": False, "status": "requires_device", "message": "Device ID required"})

    bound = lic.bound_devices or []
    found = next((d for d in bound if d.get("device_id") == device_id), None)

    # If device already bound -> refresh
    if found:
        found["bound_at"] = now.isoformat()
        if incoming_meta:
            found["meta"] = incoming_meta
        lic.last_verified = now
        lic.status = LicenseStatus.active
        try:
            lic.bound_devices = bound
            db.add(lic); db.commit()
        except Exception:
            db.rollback()

        _log("activate_ok_existing", f"{lk} refreshed")
        return {"activated": True, "status": "active", "license": license_to_dict(lic)}

    # New bind attempt
    maxd = lic.max_devices if lic.max_devices is not None else 1
    current = len(bound)

    # Single slot: rebind override
    if maxd == 1 and current >= 1:
        lic.bound_devices = [{
            "device_id": device_id,
            "bound_at": now.isoformat(),
            "meta": incoming_meta
        }]
        lic.last_verified = now
        lic.status = LicenseStatus.active
        try:
            db.add(lic); db.commit()
        except Exception:
            db.rollback()

        _log("activate_rebind_override", f"{lk} override bound")
        return {"activated": True, "status": "active", "license": license_to_dict(lic)}

    # Multi-slot
    if maxd == 0 or current < maxd:
        bound.append({
            "device_id": device_id,
            "bound_at": now.isoformat(),
            "meta": incoming_meta
        })
        lic.bound_devices = bound
        lic.last_verified = now
        lic.status = LicenseStatus.active

        try:
            db.add(lic); db.commit()
        except Exception:
            db.rollback()

        _log("activate_ok_bound", f"{lk} new device bound")
        return {"activated": True, "status": "active", "license": license_to_dict(lic)}

    _log("activate_no_slots", f"{lk} slots full")
    return JSONResponse(status_code=403, content={"activated": False, "status": "device_limit_reached", "message": "Device limit reached"})


# -------------------------
# Endpoint: Ping (lightweight)
# -------------------------
@router.get("/ping/{license_key}")
def ping_license(
    license_key: str,
    request: Request,
    _sig = Depends(require_hmac),     # 🔐 require HMAC
    db: Session = Depends(get_db),
    _ = Depends(verify_api_key)
):
    lk = (license_key or "").strip()
    now = datetime.utcnow()

    lic = db.query(License).filter(License.license_key == lk).first()
    if not lic:
        return {"alive": False, "status": "not_found"}

    if lic.status == LicenseStatus.revoked:
        return {"alive": False, "status": "revoked"}

    if lic.expires_at and lic.expires_at < now:
        return {"alive": False, "status": "expired"}

    return {
        "alive": True,
        "status": "active",
        "is_bound": lic.is_bound,
        "expires_at": lic.expires_at.isoformat() if lic.expires_at else None
    }
