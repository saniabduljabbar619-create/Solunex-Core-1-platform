# app/api/dashboard.py
# -*- coding: utf-8 -*-

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime, timedelta, date

from config import SessionLocal
from app.models.license_model import License, LicenseStatus
from app.models.logs_model import APILog
from app.utils.auth import get_current_admin

router = APIRouter(prefix="/admin/dashboard", tags=["admin/dashboard"])


# --------------------------
# DB dependency
# --------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --------------------------
# Dashboard Stats Endpoint
# --------------------------
@router.get("/stats", response_model=dict)
def dashboard_stats(
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin)
):
    """Return full dashboard numbers + chart analytics."""
    today = date.today()
    today_start = datetime(today.year, today.month, today.day)
    now = datetime.utcnow()

    # --------------------------
    # Primary Cards
    #--------------------------
    total_licenses = db.query(func.count(License.id)).scalar() or 0

    active_clients = db.query(func.count(License.id)) \
        .filter(License.status == LicenseStatus.active) \
        .scalar() or 0

    todays_issuances = db.query(func.count(License.id)) \
        .filter(License.generated_at >= today_start) \
        .scalar() or 0

    # Licenses expiring soon (next 7 days)
    next_7_days = now + timedelta(days=7)
    pending_renewals = db.query(func.count(License.id)) \
        .filter(License.expires_at != None) \
        .filter(
            and_(
                License.expires_at >= now,
                License.expires_at <= next_7_days
            )
        ).scalar() or 0

    # --------------------------
    # Chart: License Activity (last 7 days)
    # --------------------------
    seven_days_ago = now - timedelta(days=7)

    activity_rows = db.query(
        func.date(APILog.timestamp).label("day"),
        func.count(APILog.id).label("count")
    ).filter(
        APILog.timestamp >= seven_days_ago
    ).group_by(
        func.date(APILog.timestamp)
    ).order_by(
        "day"
    ).all()

    activity_days = [str(r.day) for r in activity_rows]
    activity_counts = [r.count for r in activity_rows]

    # --------------------------
    # Status Breakdown (for doughnut chart)
    # --------------------------
    revoked_count = db.query(func.count(License.id)) \
        .filter(License.status == LicenseStatus.revoked) \
        .scalar() or 0

    expired_count = db.query(func.count(License.id)) \
        .filter(License.status == LicenseStatus.expired) \
        .scalar() or 0

    # --------------------------
    # Final return bundle
    # --------------------------
    return {
        "total_licenses": total_licenses,
        "active_clients": active_clients,
        "todays_issuances": todays_issuances,
        "pending_renewals": pending_renewals,

        # charts
        "activity_days": activity_days,
        "activity_counts": activity_counts,

        # usage overview
        "revoked": revoked_count,
        "expired": expired_count
    }
