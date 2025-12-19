# app/api/license_bank.py
# -*- coding: utf-8 -*-
"""
License Bank API (Admin)
------------------------
Provides administrative endpoints to list / search / view / revoke / renew
and manage licenses stored in the system.

Mount under /admin/licenses (this router uses admin auth if available).
"""

from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional
from datetime import datetime, timedelta
import csv
import io
import json

from config import SessionLocal
from app.models.license_model import License, LicenseStatus
from app.models.logs_model import APILog
from app.utils.auth import get_current_admin

router = APIRouter(prefix="/admin/licenses", tags=["admin/licenses"])


# ---- DB dependency -------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---- Pydantic schemas ----------------------------------------------------
class RevokeIn(BaseModel):
    reason: Optional[str] = None


class RenewIn(BaseModel):
    extend_days: int = 365


class UpdateLicenseIn(BaseModel):
    user_email: Optional[str] = None
    app_name: Optional[str] = None
    expires_at: Optional[datetime] = None


# ---- Utilities -----------------------------------------------------------
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


# --------------------------------------------------------------------------
# SPECIAL ROUTES FIRST
# --------------------------------------------------------------------------

@router.post("/by_key/revoke", response_model=dict)
def revoke_by_key(
    license_key: str = Query(...),
    reason: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin)
):
    L = db.query(License).filter(License.license_key == license_key).first()

    if not L:
        raise HTTPException(status_code=404, detail="License not found")

    L.status = LicenseStatus.revoked
    try:
        db.commit()
    except:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to revoke license")

    log_action(
        db, user=_admin, action="license_revoke_by_key",
        details={"license_key": license_key, "reason": reason}
    )

    return {"status": "revoked", "license_key": license_key, "reason": reason or ""}


@router.get("/by_key/{license_key}", response_model=dict)
def get_by_key(
    license_key: str,
    request: Request,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin)
):
    L = db.query(License).filter(License.license_key == license_key).first()

    if not L:
        raise HTTPException(status_code=404, detail="License not found")

    log_action(db, user=_admin, action="license_view_by_key", details={"license_key": license_key})

    return {
        "id": L.id,
        "license_key": L.license_key,
        "user_email": L.user_email,
        "app_name": L.app_id,
        "status": L.status.value,
        "generated_at": L.generated_at.isoformat() if L.generated_at else None,
        "expires_at": L.expires_at.isoformat() if L.expires_at else None,
    }


@router.get("/export", response_class=StreamingResponse)
def export_csv(
    request: Request,
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin)
):
    query = db.query(License)
    if status:
        try:
            st = LicenseStatus(status)
            query = query.filter(License.status == st)
        except:
            raise HTTPException(status_code=400, detail="Invalid status filter.")

    items = query.order_by(License.generated_at.desc()).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "id", "license_key", "user_email", "app_name", "status",
        "generated_at", "expires_at", "order_id", "payment_reference",
        "amount", "currency"
    ])

    for L in items:
        writer.writerow([
            L.id,
            L.license_key,
            L.user_email,
            L.app_id,
            L.status.value,
            L.generated_at.isoformat() if L.generated_at else "",
            L.expires_at.isoformat() if L.expires_at else "",
            L.order_id or "",
            L.payment_reference or "",
            L.amount or "",
            L.currency or "",
        ])

    buffer.seek(0)
    filename = f"licenses_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"

    log_action(db, user=_admin, action="licenses_export", details={"count": len(items)})

    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# --------------------------------------------------------------------------
# MAIN LIST
# --------------------------------------------------------------------------

@router.get("")
def list_licenses_no_slash(
    request: Request,
    page: int = Query(1),
    per_page: int = Query(20),
    status: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin)
):
    return list_licenses(request, page, per_page, status, q, db, _admin)


@router.get("/", response_model=dict)
def list_licenses(
    request: Request,
    page: int = Query(1),
    per_page: int = Query(20),
    status: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin)
):
    query = db.query(License)

    if status:
        try:
            st = LicenseStatus(status)
            query = query.filter(License.status == st)
        except:
            raise HTTPException(status_code=400, detail="Invalid status filter.")

    if q:
        q_like = f"%{q}%"
        query = query.filter(
            or_(
                License.user_email.ilike(q_like),
                License.app_id.ilike(q_like),
                License.license_key.ilike(q_like)
            )
        )

    total = query.count()
    items = (
        query.order_by(License.generated_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    results = []
    for L in items:
        results.append({
            "id": L.id,
            "license_key": L.license_key,
            "user_email": L.user_email,
            "app_name": L.app_id,
            "status": L.status.value,
            "generated_at": L.generated_at.isoformat() if L.generated_at else None,
            "expires_at": L.expires_at.isoformat() if L.expires_at else None,
            "order_id": L.order_id,
            "payment_reference": L.payment_reference,
            "amount": L.amount,
            "currency": L.currency,
        })

    log_action(
        db, user=_admin, action="licenses_list",
        details={"page": page, "per_page": per_page, "q": q, "status": status}
    )

    return {"total": total, "page": page, "per_page": per_page, "items": results}


# --------------------------------------------------------------------------
# NUMERIC-ID ROUTES (placed last)
# --------------------------------------------------------------------------

@router.get("/{license_id}", response_model=dict)
def get_license(
    license_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin)
):
    L = db.query(License).filter(License.id == license_id).first()

    if not L:
        raise HTTPException(status_code=404, detail="License not found")

    log_action(db, user=_admin, action="license_view", details={"id": license_id})

    return {
        "id": L.id,
        "license_key": L.license_key,
        "user_email": L.user_email,
        "app_name": L.app_id,
        "status": L.status.value,
        "generated_at": L.generated_at.isoformat() if L.generated_at else None,
        "expires_at": L.expires_at.isoformat() if L.expires_at else None,
        "order_id": L.order_id,
        "payment_reference": L.payment_reference,
        "amount": L.amount,
        "currency": L.currency,
    }


@router.post("/{license_id}/revoke", response_model=dict)
def revoke_license(
    license_id: int,
    payload: RevokeIn,
    request: Request,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin)
):
    L = db.query(License).filter(License.id == license_id).first()

    if not L:
        raise HTTPException(status_code=404, detail="License not found")

    L.status = LicenseStatus.revoked

    try:
        db.commit()
    except:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to revoke license")

    log_action(
        db, user=_admin, action="license_revoke",
        details={"id": license_id, "reason": payload.reason}
    )

    return {"status": "revoked", "id": license_id, "reason": payload.reason or ""}


@router.post("/{license_id}/renew", response_model=dict)
def renew_license(
    license_id: int,
    payload: RenewIn,
    request: Request,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin)
):
    L = db.query(License).filter(License.id == license_id).first()

    if not L:
        raise HTTPException(status_code=404, detail="License not found")

    base = L.expires_at or datetime.utcnow()
    new_expiry = base + timedelta(days=payload.extend_days)

    L.expires_at = new_expiry
    L.status = LicenseStatus.active

    try:
        db.commit()
    except:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to renew license")

    log_action(
        db, user=_admin, action="license_renew",
        details={"id": license_id, "extend_days": payload.extend_days}
    )

    return {"status": "renewed", "id": license_id, "expires_at": new_expiry.isoformat()}


@router.put("/{license_id}", response_model=dict)
def update_license(
    license_id: int,
    payload: UpdateLicenseIn,
    request: Request,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin)
):
    L = db.query(License).filter(License.id == license_id).first()

    if not L:
        raise HTTPException(status_code=404, detail="License not found")

    changed = {}

    if payload.user_email and payload.user_email != L.user_email:
        changed["user_email"] = {"from": L.user_email, "to": payload.user_email}
        L.user_email = payload.user_email

    if payload.app_name and payload.app_name != L.app_id:
        changed["app_id"] = {"from": L.app_id, "to": payload.app_name}
        L.app_id = payload.app_name

    if payload.expires_at:
        old = L.expires_at.isoformat() if L.expires_at else None
        changed["expires_at"] = {"from": old, "to": payload.expires_at.isoformat()}
        L.expires_at = payload.expires_at

    try:
        db.commit()
    except:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update license")

    log_action(
        db, user=_admin, action="license_update",
        details={"id": license_id, "changes": changed}
    )

    return {"status": "updated", "id": license_id, "changes": changed}


@router.delete("/{license_id}", response_model=dict)
def delete_license(
    license_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin)
):
    L = db.query(License).filter(License.id == license_id).first()

    if not L:
        raise HTTPException(status_code=404, detail="License not found")

    try:
        db.delete(L)
        db.commit()
    except:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete license")

    log_action(db, user=_admin, action="license_delete", details={"id": license_id})
    return {"status": "deleted", "id": license_id}