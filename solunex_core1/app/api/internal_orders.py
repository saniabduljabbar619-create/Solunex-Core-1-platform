# app/api/internal_orders.py
# -*- coding: utf-8 -*-
"""
Internal Orders → License Issuance (Idempotent + Email)
Mounted under /api/internal/orders (POST)
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import json
import random
import string

from config import SessionLocal, LICENSE_API_KEY
from app.models.license_model import License, LicenseStatus
from app.models.logs_model import APILog
from app.utils.mailer import send_email   # ✔ use your working mailer

router = APIRouter(prefix="/api/internal", tags=["internal/orders"])


# -------------------------------------------------------
# DB Session
# -------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -------------------------------------------------------
# Request Model
# -------------------------------------------------------
class OrderIn(BaseModel):
    order_id: str
    email: str
    name: str
    product: str
    amount: float
    currency: str = "USD"
    callback_url: str = None
    days: int = None   # optional custom expiry days


# -------------------------------------------------------
# License Key Generator
# -------------------------------------------------------
def _make_key():
    """Readable license key: SOL-XXXX-XXXX-XXXX-XX"""
    parts = []
    for sizes in (4, 4, 4, 2):
        part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=sizes))
        parts.append(part)
    return "SOL-" + "-".join(parts)


# -------------------------------------------------------
# System Logging
# -------------------------------------------------------
def log_action(db: Session, user: str, action: str, details: dict):
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


# -------------------------------------------------------
# MAIN ENDPOINT:
#   Idempotent Order → Issue License
#   RULE:
#       1. Same order_id        → return existing license.
#       2. Same email+product   → return existing license.
# -------------------------------------------------------
@router.post("/orders", response_model=dict)
def create_order(order: OrderIn, request: Request, db: Session = Depends(get_db)):
    """
    Idempotent license issuance endpoint.
    - Same `order_id` → return SAME license.
    - Same (`email`, `product`) → return SAME license.
    - Sends email (HTML) using Gmail App Password.
    """

    # ---------------------------------------------------
    # 1) Idempotency check: order_id
    # ---------------------------------------------------
    existing = db.query(License).filter(License.order_id == order.order_id).first()
    if existing:
        return {
            "status": "exists",
            "order_id": existing.order_id,
            "license_key": existing.license_key,
            "expires_at": existing.expires_at.isoformat() if existing.expires_at else None,
            "idempotent": "order_id"
        }

    # ---------------------------------------------------
    # 2) Idempotency check: email + product
    # ---------------------------------------------------
    existing2 = (
        db.query(License)
        .filter(License.user_email == order.email)
        .filter(License.app_id == order.product)
        .filter(License.status != LicenseStatus.revoked)
        .first()
    )

    if existing2:
        return {
            "status": "exists",
            "order_id": existing2.order_id,
            "license_key": existing2.license_key,
            "expires_at": existing2.expires_at.isoformat() if existing2.expires_at else None,
            "idempotent": "email+product"
        }

    # ---------------------------------------------------
    # 3) Generate new license
    # ---------------------------------------------------
    days = order.days or 365 * 4  # default = 4 years
    expires_at = datetime.utcnow() + timedelta(days=days)

    # Generate unique key
    license_key = _make_key()
    tries = 0
    while db.query(License).filter(License.license_key == license_key).first() and tries < 5:
        license_key = _make_key()
        tries += 1

    L = License(
        license_key=license_key,
        user_email=order.email,
        app_id=order.product,
        status=LicenseStatus.active,
        generated_at=datetime.utcnow(),
        expires_at=expires_at,
        order_id=order.order_id,
        payment_reference=None,
        amount=order.amount,
        currency=order.currency,
        is_bound=False,
        max_devices=1
    )

    try:
        db.add(L)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create license")

    # ---------------------------------------------------
    # 4) Email HTML using your existing mailer
    # ---------------------------------------------------
    html_body = f"""
        <h2>Solunex License Issued</h2>
        <p>Hello {order.name},</p>
        <p>Thank you for your purchase of <b>{order.product}</b>.</p>

        <p><b>License Key:</b> {license_key}</p>
        <p><b>Expires At:</b> {expires_at}</p>

        <p>You can activate this license inside the Solunex client app.</p>

        <br>
        <p>Regards,<br>Solunex License core</p>
    """

    email_sent = send_email(
        order.email,
        f"Your {order.product} License",
        html_body
    )

    # ---------------------------------------------------
    # 5) Log Action
    # ---------------------------------------------------
    log_action(db, user=order.email, action="order_issue", details={
        "order_id": order.order_id,
        "license_key": license_key,
        "email": order.email,
        "product": order.product,
        "amount": order.amount,
        "email_sent": email_sent
    })

    # ---------------------------------------------------
    # 6) Success Response
    # ---------------------------------------------------
    return {
        "status": "ok",
        "order_id": order.order_id,
        "license_key": license_key,
        "expires_at": expires_at.isoformat(),
        "email_sent": bool(email_sent)
    }
