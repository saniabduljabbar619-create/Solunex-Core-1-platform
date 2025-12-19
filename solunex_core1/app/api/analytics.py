# app/api/analytics.py
# -*- coding: utf-8 -*-
"""
Advanced Analytics API for Solunex Core-1
Provides dashboard-ready endpoints built on APILog and License records.

Endpoints (high level)
- GET  /analytics/summary                -> enhanced overview (daily, endpoints, license highlights)
- GET  /analytics/recent                 -> recent logs (existing)
- GET  /analytics/filter                 -> filtered logs (existing)
- GET  /analytics/top-endpoints          -> top endpoints (detailed)
- GET  /analytics/endpoint-breakdown     -> endpoint counts by timeframe
- GET  /analytics/per-license            -> validations/activations per license
- GET  /analytics/top-ips                -> top client IP addresses
- GET  /analytics/error-timeline         -> time series of errors (hourly/day)
- GET  /analytics/heatmap-30             -> 30-day daily counts (heatmap)
- GET  /analytics/license-churn          -> issued / revoked / expired counts
- GET  /analytics/hmac-failures          -> HMAC failure trends (if logged)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
import math
import json

from config import SessionLocal, REDIS_URL
from app.models.logs_model import APILog
from app.models.license_model import License

# Optional redis for caching (multi-instance)
try:
    import redis
except Exception:
    redis = None

router = APIRouter(prefix="/analytics", tags=["analytics"])


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
# Redis client (optional)
# -------------------------
_cache_client = None
if REDIS_URL and redis:
    try:
        _cache_client = redis.from_url(REDIS_URL)
    except Exception:
        _cache_client = None


def _cache_get(key: str):
    if _cache_client:
        try:
            v = _cache_client.get(key)
            if v:
                return json.loads(v)
        except Exception:
            return None
    return None


def _cache_set(key: str, obj: Any, ttl: int = 30):
    if _cache_client:
        try:
            _cache_client.setex(key, ttl, json.dumps(obj, default=str))
        except Exception:
            pass


# -------------------------
# Utility helpers
# -------------------------
def _date_range(start: datetime, end: datetime, step_days: int = 1):
    out = []
    cur = start
    while cur <= end:
        out.append(cur)
        cur = cur + timedelta(days=step_days)
    return out


def group_by_day_query(db: Session, since_days: int = 7):
    today = datetime.utcnow()
    since = today - timedelta(days=since_days)
    rows = (
        db.query(func.date(APILog.timestamp).label("day"), func.count(APILog.id).label("count"))
        .filter(APILog.timestamp >= since)
        .group_by(func.date(APILog.timestamp))
        .order_by("day")
        .all()
    )
    return [{"date": str(r.day), "count": r.count} for r in rows]


# -------------------------
# Existing endpoint: Summary (enhanced)
# -------------------------
@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    """
    Enhanced overview:
      - total_logs
      - unique_users
      - top_actions (5)
      - daily_activity (7 days)
      - top_endpoints (5)
      - avg_daily (30 days)
    """
    try:
        total_logs = db.query(func.count(APILog.id)).scalar() or 0
        unique_users = db.query(func.count(func.distinct(APILog.user))).scalar() or 0

        top_actions = (
            db.query(APILog.action, func.count(APILog.id).label("count"))
            .group_by(APILog.action)
            .order_by(desc("count"))
            .limit(5)
            .all()
        )

        daily_stats = group_by_day_query(db, 7)

        top_endpoints = (
            db.query(APILog.endpoint, func.count(APILog.id).label("count"))
            .group_by(APILog.endpoint)
            .order_by(desc("count"))
            .limit(5)
            .all()
        )

        # average daily last 30 days
        days = 30
        total_30 = (
            db.query(func.count(APILog.id))
            .filter(APILog.timestamp >= datetime.utcnow() - timedelta(days=days))
            .scalar() or 0
        )
        avg_daily = round(total_30 / days, 2)

        return {
            "total_logs": total_logs,
            "unique_users": unique_users,
            "top_actions": [{"action": a[0], "count": a[1]} for a in top_actions],
            "daily_activity_7d": daily_stats,
            "top_endpoints": [{"endpoint": e[0], "count": e[1]} for e in top_endpoints],
            "average_daily_hits_30d": avg_daily,
            "total_30_days": total_30,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating summary: {e}")


# -------------------------
# Recent logs (existing)
# -------------------------
@router.get("/recent")
def get_recent_logs(limit: int = 20, db: Session = Depends(get_db)):
    logs = (
        db.query(APILog)
        .order_by(desc(APILog.timestamp))
        .limit(limit)
        .all()
    )

    return [
        {
            "id": log.id,
            "user": log.user,
            "action": log.action,
            "endpoint": log.endpoint,
            "details": log.details,
            "ip": getattr(log, "ip_address", None),
            "timestamp": log.timestamp.isoformat() if log.timestamp else None
        }
        for log in logs
    ]


# -------------------------
# Filtered logs (existing)
# -------------------------
@router.get("/filter")
def filter_logs(
    user: Optional[str] = None,
    action: Optional[str] = None,
    days: int = 7,
    db: Session = Depends(get_db)
):
    query = db.query(APILog)
    if user:
        query = query.filter(APILog.user == user)
    if action:
        query = query.filter(APILog.action == action)
    if days:
        since = datetime.utcnow() - timedelta(days=days)
        query = query.filter(APILog.timestamp >= since)

    result = query.order_by(desc(APILog.timestamp)).limit(100).all()

    return [
        {
            "id": r.id,
            "user": r.user,
            "action": r.action,
            "endpoint": r.endpoint,
            "details": r.details,
            "ip": getattr(r, "ip_address", None),
            "timestamp": r.timestamp.isoformat() if r.timestamp else None
        }
        for r in result
    ]


# -------------------------
# Top endpoints (detailed)
# -------------------------
@router.get("/top-endpoints")
def get_top_endpoints(db: Session = Depends(get_db), limit: int = 20):
    """
    Return top endpoints with counts and percent share.
    """
    try:
        total = db.query(func.count(APILog.id)).scalar() or 1
        results = (
            db.query(APILog.endpoint, func.count(APILog.id).label("count"))
            .group_by(APILog.endpoint)
            .order_by(desc("count"))
            .limit(limit)
            .all()
        )

        data = []
        for r in results:
            cnt = r[1]
            pct = round((cnt / total) * 100, 2)
            data.append({"endpoint": r[0], "count": cnt, "percent": pct})
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching endpoints: {e}")


# -------------------------
# Endpoint breakdown (by endpoint over time)
# -------------------------
@router.get("/endpoint-breakdown")
def endpoint_breakdown(
    endpoint: str,
    period: str = Query("24h", regex="^[0-9]+[hd]$"),  # e.g. 1h, 24h, 7d
    db: Session = Depends(get_db)
):
    """
    Return counts grouped by hour (if <48h) or by day.
    period examples: 1h, 24h, 7d, 30d
    """
    try:
        # parse period
        unit = period[-1]
        qty = int(period[:-1])
        now = datetime.utcnow()

        if unit == "h":
            since = now - timedelta(hours=qty)
            rows = (
                db.query(func.date_trunc('hour', APILog.timestamp).label("slot"), func.count(APILog.id).label("count"))
                .filter(APILog.timestamp >= since)
                .filter(APILog.endpoint == endpoint)
                .group_by("slot")
                .order_by("slot")
                .all()
            )
            return [{"slot": r.slot.isoformat(), "count": r.count} for r in rows]
        else:
            # days
            since = now - timedelta(days=qty)
            rows = (
                db.query(func.date(APILog.timestamp).label("day"), func.count(APILog.id).label("count"))
                .filter(APILog.timestamp >= since)
                .filter(APILog.endpoint == endpoint)
                .group_by("day")
                .order_by("day")
                .all()
            )
            return [{"day": str(r.day), "count": r.count} for r in rows]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating endpoint breakdown: {e}")


# -------------------------
# Per-license analytics
# -------------------------
@router.get("/per-license")
def per_license_stats(
    license_key: Optional[str] = None,
    days: int = 30,
    db: Session = Depends(get_db)
):
    """
    Returns stats for license keys:
      - validations_count
      - activations_count
      - last_seen (last timestamp)
    If license_key omitted, returns top N licenses by activity.
    """
    try:
        since = datetime.utcnow() - timedelta(days=days)

        # Basic heuristic: actions containing 'validate', 'activate', 'public_activate', 'activate_ok'
        validate_like = "%validate%"
        activate_like = "%activate%"

        q = db.query(
            APILog.action,
            APILog.details
        ).filter(APILog.timestamp >= since)

        if license_key:
            # attempt to match license_key in details json/text
            q = q.filter(APILog.details.like(f"%{license_key}%"))

        rows = q.all()

        # aggregate in python to be flexible with varying action names and details format
        stats = {}
        for r in rows:
            action = (r.action or "").lower()
            details = r.details or ""
            # attempt to extract license_key from details (if JSON)
            lk = None
            try:
                d = json.loads(details)
                lk = d.get("license_key") or d.get("license") or None
            except Exception:
                # fallback: naive substring search if license_key provided
                lk = license_key if license_key and license_key in details else None

            # if user asked for specific license_key but we couldn't parse, skip
            if license_key and not lk:
                # only increment if details contain the license_key string
                if license_key in details:
                    lk = license_key
                else:
                    continue

            if not lk:
                # for top-listing, try to parse any license-like tokens in details (naive)
                # skip if not found
                continue

            entry = stats.setdefault(lk, {"validations": 0, "activations": 0, "last_seen": None})
            if "validate" in action:
                entry["validations"] += 1
            if "activate" in action or "public_activate" in action:
                entry["activations"] += 1
            # last seen from APILog timestamp is not returned by row; query separately
        # fill last_seen per license if requested
        if license_key:
            last = (
                db.query(APILog.timestamp)
                .filter(APILog.details.like(f"%{license_key}%"))
                .order_by(desc(APILog.timestamp))
                .limit(1)
                .first()
            )
            if last:
                stats.setdefault(license_key, {"validations": 0, "activations": 0, "last_seen": None})
                stats[license_key]["last_seen"] = last[0].isoformat()

        # if no license_key asked, return top licenses by (validations+activations)
        if not license_key:
            out = []
            for k, v in stats.items():
                out.append({"license_key": k, "validations": v["validations"], "activations": v["activations"], "last_seen": v["last_seen"]})
            # sort by activity
            out.sort(key=lambda x: (x["validations"] + x["activations"]), reverse=True)
            return out[:50]

        return {license_key: stats.get(license_key, {"validations": 0, "activations": 0, "last_seen": None})}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating per-license stats: {e}")


# -------------------------
# Top IPs
# -------------------------
@router.get("/top-ips")
def top_ips(limit: int = 25, days: int = 30, db: Session = Depends(get_db)):
    """
    Returns top IP addresses by request count.
    """
    try:
        since = datetime.utcnow() - timedelta(days=days)
        rows = (
            db.query(APILog.ip_address, func.count(APILog.id).label("count"))
            .filter(APILog.timestamp >= since)
            .group_by(APILog.ip_address)
            .order_by(desc("count"))
            .limit(limit)
            .all()
        )
        return [{"ip": r[0], "count": r[1]} for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching top IPs: {e}")


# -------------------------
# Error timeline (hourly or daily)
# -------------------------
@router.get("/error-timeline")
def error_timeline(period: str = Query("7d", regex="^[0-9]+[hd]$"), db: Session = Depends(get_db)):
    """
    Returns a time series of error counts.
    period: e.g. 24h, 7d, 30d
    If hours -> group by hour, if days -> group by day
    """
    try:
        unit = period[-1]
        qty = int(period[:-1])
        now = datetime.utcnow()

        if unit == "h":
            since = now - timedelta(hours=qty)
            rows = (
                db.query(func.date_trunc('hour', APILog.timestamp).label("slot"), func.count(APILog.id).label("count"))
                .filter(APILog.timestamp >= since)
                .filter(APILog.details.ilike("%error%") | APILog.action.ilike("%error%"))
                .group_by("slot")
                .order_by("slot")
                .all()
            )
            return [{"slot": r.slot.isoformat(), "errors": r.count} for r in rows]
        else:
            since = now - timedelta(days=qty)
            rows = (
                db.query(func.date(APILog.timestamp).label("day"), func.count(APILog.id).label("count"))
                .filter(APILog.timestamp >= since)
                .filter(APILog.details.ilike("%error%") | APILog.action.ilike("%error%"))
                .group_by("day")
                .order_by("day")
                .all()
            )
            return [{"day": str(r.day), "errors": r.count} for r in rows]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating error timeline: {e}")


# -------------------------
# 30-day heatmap
# -------------------------
@router.get("/heatmap-30")
def heatmap_30(db: Session = Depends(get_db)):
    """
    Returns last 30 days counts per day suitable for heatmap plotting.
    """
    try:
        days = 30
        end = datetime.utcnow().date()
        start = end - timedelta(days=days - 1)

        rows = (
            db.query(func.date(APILog.timestamp).label("day"), func.count(APILog.id).label("count"))
            .filter(APILog.timestamp >= datetime.combine(start, datetime.min.time()))
            .group_by(func.date(APILog.timestamp))
            .order_by("day")
            .all()
        )
        # build full 30-day list with zeros filled
        counts_map = {str(r.day): r.count for r in rows}
        out = []
        cur = start
        while cur <= end:
            out.append({"date": str(cur), "count": counts_map.get(str(cur), 0)})
            cur = cur + timedelta(days=1)
        return out
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error building heatmap: {e}")


# -------------------------
# License churn (issued / revoked / expired)
# -------------------------
@router.get("/license-churn")
def license_churn(days: int = 30, db: Session = Depends(get_db)):
    """
    Returns:
      - issued_count (licenses generated in period)
      - revoked_count (licenses set to revoked in period)  [requires APILog or status change recording]
      - expired_count (licenses that expired in period)
    """
    try:
        since = datetime.utcnow() - timedelta(days=days)

        # issued: generated_at in range
        issued = db.query(func.count(License.id)).filter(License.generated_at >= since).scalar() or 0

        # expired: expires_at within range
        expired = db.query(func.count(License.id)).filter(and_(License.expires_at != None, License.expires_at >= since)).scalar() or 0

        # revoked: best-effort via APILog searching for 'revoked' actions
        revoked = (
            db.query(func.count(APILog.id))
            .filter(APILog.timestamp >= since)
            .filter(APILog.action.ilike("%revok%"))
            .scalar() or 0
        )

        return {"issued": issued, "revoked": revoked, "expired": expired}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error computing churn: {e}")


# -------------------------
# HMAC failure trends (if you log them)
# -------------------------
@router.get("/hmac-failures")
def hmac_failures(days: int = 7, db: Session = Depends(get_db)):
    """
    If you log HMAC signature failures into APILog (e.g. action='hmac_signature_failure'),
    this endpoint returns counts per day for the last N days.
    """
    try:
        since = datetime.utcnow() - timedelta(days=days)
        rows = (
            db.query(func.date(APILog.timestamp).label("day"), func.count(APILog.id).label("count"))
            .filter(APILog.timestamp >= since)
            .filter(APILog.action == "hmac_signature_failure")
            .group_by(func.date(APILog.timestamp))
            .order_by("day")
            .all()
        )
        return [{"date": str(r.day), "count": r.count} for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching hmac failures: {e}")
