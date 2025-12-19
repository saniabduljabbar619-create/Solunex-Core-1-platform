# app/api/public_license_api.py
# External License API (public-facing)
# Minimal, secure, and fast endpoints for client apps.

from fastapi import APIRouter, Depends, HTTPException, Header, status, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime
import json

from config import SessionLocal, LICENSE_API_KEY
from app.models.license_model import License, LicenseStatus
from app.models.logs_model import APILog
from app.utils.signer import require_hmac   # 🔐 HMAC security layer

router = APIRouter(prefix="/api/v1/license", tags=["public/license"])


# ---------- DB dependency ----------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------- API key auth dependency ----------
def require_api_key(x_api_key: Optional[str] = Header(None)):
    """
    Very small API-key check. Expects header:
      X-API-KEY: <SECRET>
    """
    if not x_api_key or x_api_key != LICENSE_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key")
    return True


# ---------- Pydantic Schemas ----------
class ValidateIn(BaseModel):
    license_key: str
    device_id: Optional[str] = None
    app_id: Optional[str] = None


class ActivateIn(BaseModel):
    license_key: str
    device_id: str
    device_meta: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = None   # alias for compatibility
    app_id: Optional[str] = None


class ValidateOut(BaseModel):
    valid: bool
    status: str
    expires_at: Optional[str]
    bound_devices: Optional[List[Dict[str, Any]]] = None
    message: Optional[str] = None


# ---------- Utilities ----------
def log_action(db: Session, user: Optional[str], action: str, details: dict):
    try:
        entry = APILog(
            user=user,
            action=action,
            details=json.dumps(details, default=str),
            timestamp=datetime.utcnow()
        )
        db.add(entry)
        db.commit()
    except Exception:
        db.rollback()


# ---------- Endpoints (HMAC PROTECTED) ----------

@router.post("/validate", response_model=ValidateOut, include_in_schema=True)
def validate_license(
    payload: ValidateIn,
    request: Request,
    _sig: bool = Depends(require_hmac),          # 🔐 HMAC verification
    _ok: bool = Depends(require_api_key),        # API key check
    db: Session = Depends(get_db)
):
    """
    Validate a license key. Safe to call frequently by clients.
    Returns minimal info: valid, status, expiry, number of bound devices.
    """
    L: License = db.query(License).filter(License.license_key == payload.license_key).first()

    if not L:
        return ValidateOut(valid=False, status="not_found", expires_at=None, message="License not found")

    # status checks
    if L.status == LicenseStatus.revoked:
        return ValidateOut(valid=False, status="revoked", expires_at=L.expires_at.isoformat() if L.expires_at else None, message="License revoked")

    if L.expires_at and L.expires_at < datetime.utcnow():
        return ValidateOut(valid=False, status="expired", expires_at=L.expires_at.isoformat(), message="License expired")

    bound = L.bound_devices or []
    if isinstance(bound, str):
        try:
            bound = json.loads(bound)
        except Exception:
            bound = []

    return ValidateOut(
        valid=True,
        status="active",
        expires_at=L.expires_at.isoformat() if L.expires_at else None,
        bound_devices=bound
    )


@router.post("/activate", response_model=Dict[str, Any], include_in_schema=True)
def activate_license(
    payload: ActivateIn,
    request: Request,
    _sig: bool = Depends(require_hmac),          # 🔐 HMAC first
    _ok: bool = Depends(require_api_key),        # API key second
    db: Session = Depends(get_db)
):
    """
    Activate a license for a device_id (bind device).
    Enforces max_devices and respects revoked/expired state.
    """
    L: License = db.query(License).filter(License.license_key == payload.license_key).first()
    if not L:
        raise HTTPException(status_code=404, detail="License not found")

    if L.status == LicenseStatus.revoked:
        raise HTTPException(status_code=403, detail="License revoked")
    if L.expires_at and L.expires_at < datetime.utcnow():
        raise HTTPException(status_code=403, detail="License expired")

    bound = L.bound_devices or []
    if isinstance(bound, str):
        try:
            bound = json.loads(bound)
        except Exception:
            bound = []

    # normalized meta: support both 'device_meta' and 'meta' for compatibility
    incoming_meta = {}
    if getattr(payload, "device_meta", None):
        incoming_meta = payload.device_meta or {}
    elif getattr(payload, "meta", None):
        incoming_meta = payload.meta or {}

    existing = next((d for d in bound if d.get("device_id") == payload.device_id), None)
    now = datetime.utcnow().isoformat()

    if existing:
        existing["last_seen"] = now
        if incoming_meta:
            existing["meta"] = incoming_meta
    else:
        if L.max_devices and len(bound) >= (L.max_devices or 1):
            raise HTTPException(status_code=403, detail="Max devices reached")

        bound.append({
            "device_id": payload.device_id,
            "meta": incoming_meta or {},
            "bound_at": now,
            "last_seen": now
        })

    L.bound_devices = bound
    L.is_bound = True

    try:
        db.add(L)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to activate license")

    log_action(db, user=None, action="public_activate", details={
        "license_key": L.license_key,
        "device_id": payload.device_id,
        "app_id": payload.app_id
    })

    return {
        "status": "activated",
        "license_key": L.license_key,
        "device_count": len(bound),
        "expires_at": L.expires_at.isoformat() if L.expires_at else None
    }


@router.get("/check/{license_key}", response_model=ValidateOut, include_in_schema=True)
def check_license(
    license_key: str,
    request: Request,
    _sig: bool = Depends(require_hmac),          # 🔐 required
    _ok: bool = Depends(require_api_key),
    db: Session = Depends(get_db)
):
    """
    Check a license (GET version). Minimal info for clients.
    """
    L: License = db.query(License).filter(License.license_key == license_key).first()
    if not L:
        return ValidateOut(valid=False, status="not_found", expires_at=None, message="License not found")

    if L.status == LicenseStatus.revoked:
        return ValidateOut(valid=False, status="revoked", expires_at=L.expires_at.isoformat() if L.expires_at else None, message="License revoked")

    if L.expires_at and L.expires_at < datetime.utcnow():
        return ValidateOut(valid=False, status="expired", expires_at=L.expires_at.isoformat(), message="License expired")

    bound = L.bound_devices or []
    if isinstance(bound, str):
        try:
            bound = json.loads(bound)
        except Exception:
            bound = []

    return ValidateOut(
        valid=True,
        status="active",
        expires_at=L.expires_at.isoformat() if L.expires_at else None,
        bound_devices=bound
    )


@router.get("/info/{license_key}", response_model=Dict[str, Any], include_in_schema=True)
def license_info(
    license_key: str,
    request: Request,
    _sig: bool = Depends(require_hmac),          # 🔐 required
    _ok: bool = Depends(require_api_key),
    db: Session = Depends(get_db)
):
    """
    Admin-lite info (used by support tools). Returns a few more fields but still safe.
    """
    L: License = db.query(License).filter(License.license_key == license_key).first()
    if not L:
        raise HTTPException(status_code=404, detail="License not found")

    bound = L.bound_devices or []
    if isinstance(bound, str):
        try:
            bound = json.loads(bound)
        except Exception:
            bound = []

    return {
        "id": L.id,
        "license_key": L.license_key,
        "user_email": L.user_email,
        "app_id": getattr(L, "app_id", None),
        "status": L.status.value if hasattr(L.status, "value") else str(L.status),
        "generated_at": L.generated_at.isoformat() if L.generated_at else None,
        "expires_at": L.expires_at.isoformat() if L.expires_at else None,
        "is_bound": L.is_bound,
        "max_devices": L.max_devices,
        "bound_devices": bound
    }
