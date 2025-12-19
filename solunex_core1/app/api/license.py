# app/api/license.py
# -*- coding: utf-8 -*-
"""
License Issuance API - improved and production-focused
"""

from fastapi import APIRouter, Depends, Request, BackgroundTasks, HTTPException
from pydantic import BaseModel, EmailStr, HttpUrl
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta
from typing import Optional
import json
import traceback
import requests
import time

from config import SessionLocal
from app.models.license_model import License, LicenseStatus
from app.models.logs_model import APILog
from app.utils.generator import generate_license_key
from app.utils.mailer import send_email, SMTP_USER

router = APIRouter(prefix="/api/internal", tags=["internal"])


# -----------------------------------------------------
# DB session dependency
# -----------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -----------------------------------------------------
# Incoming request schema
# -----------------------------------------------------
class OrderPayload(BaseModel):
    order_id: Optional[str]
    email: EmailStr
    name: Optional[str] = None
    product: str
    payment_reference: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = "USD"
    callback_url: Optional[HttpUrl] = None  # optional callback for Core2


# -----------------------------------------------------
# Logging utilities
# -----------------------------------------------------
def log_api(db: Session, endpoint: str, payload: dict, status_code: int, ip: Optional[str] = None, error: Optional[str] = None):
    try:
        entry = APILog(
            user=payload.get("email"),
            action=f"{endpoint} [{status_code}]",
            details=json.dumps({"payload": payload, "error": error}, default=str),
            timestamp=datetime.utcnow()
        )
        db.add(entry)
        db.commit()
    except Exception:
        db.rollback()


def log_license_event(db: Session, license_obj: License, event_type: str, description: Optional[str] = None):
    try:
        details = {"license_key": license_obj.license_key, "event": event_type, "desc": description}
        entry = APILog(
            user=license_obj.user_email,
            action=f"license_{event_type}",
            details=json.dumps(details, default=str),
            timestamp=datetime.utcnow()
        )
        db.add(entry)
        db.commit()
    except Exception:
        db.rollback()


# -----------------------------------------------------
# Background helpers
# -----------------------------------------------------
def _bg_send_license_email(email: str, license_key: str, product: str):
    subject = f"Your {product} License from Solunex"
    body = f"""
    <p>Hello,</p>
    <p>Thank you for your purchase.</p>
    <p>Your license has been successfully issued.</p>
    <p><b>License Key:</b> {license_key}</p>
    <p>Please keep it safe. Use it to activate your Solunex product.</p>
    <br>
    <p>Warm regards,<br><b>Solunex Core Team</b></p>
    """
    try:
        send_email(email, subject, body)
    except Exception as e:
        print(f"[MAIL ERROR] Failed to send license email to {email}: {e}")


def _bg_callback_to_core(callback_url: str, payload: dict):
    try:
        resp = requests.post(callback_url, json=payload, timeout=8)
        print(f"Callback to core2 {callback_url} status: {resp.status_code}")
    except Exception as e:
        print(f"[CALLBACK ERROR] Failed to callback to core2: {e}")


# -----------------------------------------------------
# Main Issuance Endpoint
# -----------------------------------------------------
@router.post("/orders")
def create_order(payload: OrderPayload, background: BackgroundTasks, request: Request, db: Session = Depends(get_db)):
    """
    Process license issuance for a given order.

    Idempotency rules:
    1. If order_id exists -> lookup by order_id
    2. Else -> lookup existing active license (email + product)
    """
    try:
        # --- STEP 1: Check for already issued license (idempotency) ---
        existing = None

        if payload.order_id:
            existing = db.query(License).filter(License.order_id == payload.order_id).first()

        if not existing:
            existing = (
                db.query(License)
                .filter(License.user_email == payload.email)
                .filter(License.app_id == payload.product)
                .filter(License.status == LicenseStatus.active)
                .first()
            )

        if existing:
            log_api(db, "/api/internal/orders", payload.dict(), 200, request.client.host)
            return {
                "status": "already_issued",
                "license_key": existing.license_key,
                "issued_at": existing.generated_at.isoformat() if existing.generated_at else None
            }

        # -----------------------------------------------------
        # STEP 2: Generate + Insert License (Production-grade)
        # -----------------------------------------------------
        max_gen_retries = 8
        max_db_retries = 3
        license_key = None

        for gen_attempt in range(max_gen_retries):

            # Generate candidate key
            candidate = generate_license_key(prefix="SOL", length=16)

            # Quick DB collision check
            if db.query(License).filter(License.license_key == candidate).first():
                continue

            # Create object
            expires_at = datetime.utcnow() + timedelta(days=365)
            new_license = License(
                license_key=candidate,
                user_email=payload.email,
                app_id=payload.product,
                status=LicenseStatus.active,
                generated_at=datetime.utcnow(),
                expires_at=expires_at,
                order_id=payload.order_id,
                payment_reference=payload.payment_reference,
                amount=payload.amount,
                currency=payload.currency
            )

            db.add(new_license)
            committed = False

            # DB commit retries (handles IntegrityError collisions)
            for db_attempt in range(max_db_retries):
                try:
                    db.commit()
                    db.refresh(new_license)
                    committed = True
                    break
                except IntegrityError:
                    db.rollback()
                    time.sleep(0.12 * (db_attempt + 1))
                    break
                except Exception:
                    db.rollback()
                    raise

            if committed:
                license_key = candidate
                break

        if not license_key:
            raise HTTPException(status_code=500, detail="Unable to generate unique license key (exhausted retries)")

        # Log license issuance event
        log_license_event(db, new_license, "issued", description="Issued by API /orders")

        # Send email (background)
        background.add_task(_bg_send_license_email, payload.email, license_key, payload.product)

        # Trigger callback (background)
        if payload.callback_url:
            callback_payload = {
                "status": "issued",
                "order_id": payload.order_id,
                "license_key": license_key,
                "email": payload.email,
                "issued_at": new_license.generated_at.isoformat()
            }
            background.add_task(_bg_callback_to_core, str(payload.callback_url), callback_payload)

        # Log success
        log_api(db, "/api/internal/orders", payload.dict(), 201, request.client.host)

        # Final response
        return {
            "status": "issued",
            "license_key": license_key,
            "issued_at": new_license.generated_at.isoformat(),
            "expires_at": new_license.expires_at.isoformat()
        }

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        error_msg = str(e)
        traceback.print_exc()
        log_api(db, "/api/internal/orders", payload.dict(), 500, request.client.host, error=error_msg)
        raise HTTPException(status_code=500, detail=f"Internal error: {error_msg}")


# -----------------------------------------------------
# Test Mail Endpoint
# -----------------------------------------------------
@router.post("/test-mail")
def test_mail(request: Request, db: Session = Depends(get_db)):
    """
    Verify SMTP email sending to configured SMTP_USER.
    """
    test_subject = "Solunex Core1 | Mailer Test"
    test_body = """
    <h2>✅ Solunex Mailer Test Successful</h2>
    <p>If you received this message, your SMTP settings are valid.</p>
    """

    try:
        result = send_email(to_email=SMTP_USER, subject=test_subject, html_body=test_body)
        if result:
            log_api(db, "/api/internal/test-mail", {"message": "Mailer test success"}, 200, request.client.host)
            return {"status": "success", "message": "Test email sent successfully."}
        else:
            raise HTTPException(status_code=500, detail="Email sending failed.")
    except Exception as e:
        log_api(db, "/api/internal/test-mail", {"error": str(e)}, 500, request.client.host)
        raise HTTPException(status_code=500, detail=f"Error: {e}")