# app/api/services.py
# -*- coding: utf-8 -*-
"""
Services API + Auto-Restart Daemon for Solunex Core-1

Features:
- List services, toggle, manual restart, manual health check (existing)
- Background daemon that checks services every 30s and auto-restarts
- Daemon control endpoints (status / toggle)
- Logs daemon actions into APILog via log_event()
- A pluggable `real_health_check()` placeholder for future integrations
"""

import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, Dict, Any
import traceback

from config import SessionLocal
from app.models.service_model import SystemService
from app.models.logs_model import APILog, log_event
from app.utils.auth import get_current_admin

router = APIRouter(prefix="/admin/api/services", tags=["admin/services"])

# -----------------------
# Configurable values
# -----------------------
DAEMON_INTERVAL_SECONDS = 30  # chosen: option C
_DAEMON_RUNNING = False      # runtime flag
# internal lock to avoid multiple daemons in same process
_daemon_lock = asyncio.Lock()

# -----------------------
# DB dependency
# -----------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -----------------------
# Health helpers
# -----------------------
def simulate_health() -> str:
    # same as before: mostly online, sometimes error/offline
    import random
    return random.choice(["online", "online", "online", "error", "offline"])


async def real_health_check(service: SystemService) -> str:
    """
    Placeholder for an actual health check:
    - ping HTTP endpoint
    - TCP connect
    - run a custom probe
    Return "online" | "offline" | "error"
    """
    # Keep it simple for now: fallback to simulate_health.
    # Replace this with a real probe (requests.get / socket check) if you add service probe config.
    await asyncio.sleep(0)  # keep function async-friendly
    return simulate_health()


# -----------------------
# Core helper: restart logic
# -----------------------
def _restart_service_db(db: Session, svc: SystemService) -> bool:
    """
    Perform restart in DB (mark online, update last_check).
    Return True on success.
    """
    try:
        svc.health = "online"
        svc.last_check = datetime.utcnow()
        # keep status enabled
        db.add(svc)
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False


# -----------------------
# API routes (existing + expanded)
# -----------------------
@router.get("", response_model=Dict[str, Any])
def list_services(db: Session = Depends(get_db), _admin: str = Depends(get_current_admin)):
    items = db.query(SystemService).order_by(SystemService.id).all()
    return {"services": [
        {
            "id": s.id,
            "name": s.name,
            "label": s.label,
            "status": bool(s.status),
            "health": s.health,
            "last_check": s.last_check.isoformat() if s.last_check else None,
            "description": s.description,
            "auto_restart": bool(s.auto_restart),
        }
        for s in items
    ]}


@router.post("/{service_id}/toggle")
def toggle_service(service_id: int, db: Session = Depends(get_db), _admin: str = Depends(get_current_admin)):
    S = db.query(SystemService).filter(SystemService.id == service_id).first()
    if not S:
        raise HTTPException(404, "Service not found")

    S.status = not S.status
    db.commit()
    log_event(db, user=_admin, action="service_toggled", details={"service_id": service_id, "new_state": S.status})
    return {"status": "ok", "new_state": S.status}


@router.post("/{service_id}/restart")
def restart_service(service_id: int, db: Session = Depends(get_db), _admin: str = Depends(get_current_admin)):
    S = db.query(SystemService).filter(SystemService.id == service_id).first()
    if not S:
        raise HTTPException(404, "Service not found")

    ok = _restart_service_db(db, S)
    if ok:
        log_event(db, user=_admin, action="service_manual_restart", details={"service_id": service_id})
        return {"status": "restarted", "health": S.health}
    else:
        raise HTTPException(status_code=500, detail="Failed to restart service")


@router.post("/{service_id}/health")
def health_check(service_id: int, db: Session = Depends(get_db), _admin: str = Depends(get_current_admin)):
    S = db.query(SystemService).filter(SystemService.id == service_id).first()
    if not S:
        raise HTTPException(404, "Service not found")

    # update health using simulate (or replace with real probe)
    S.health = simulate_health()
    S.last_check = datetime.utcnow()
    db.commit()

    log_event(db, user=_admin, action="service_health_check", details={
        "service_id": service_id,
        "health": S.health
    })
    return {"status": "ok", "health": S.health, "timestamp": S.last_check.isoformat()}


# -----------------------
# Daemon control endpoints
# -----------------------
@router.get("/daemon/status")
def daemon_status(_admin: str = Depends(get_current_admin)):
    """
    Returns whether the auto-restart daemon is running in this process.
    Note: in clustered deployments each process reports its own state.
    """
    return {"daemon_running": bool(_DAEMON_RUNNING), "interval_seconds": DAEMON_INTERVAL_SECONDS}


@router.post("/daemon/toggle")
def daemon_toggle(enabled: bool, _admin: str = Depends(get_current_admin)):
    """
    Toggle the daemon flag on/off. This only flips the in-process flag;
    use startup/shutdown hooks to permanently control behavior or use orchestration.
    """
    global _DAEMON_RUNNING
    _DAEMON_RUNNING = bool(enabled)
    # log via DB best-effort
    try:
        db = SessionLocal()
        log_event(db, user=_admin, action="daemon_toggled", details={"enabled": _DAEMON_RUNNING})
        db.close()
    except Exception:
        pass
    return {"daemon_running": _DAEMON_RUNNING}


@router.get("/daemon/logs")
def daemon_logs(limit: int = 100, db: Session = Depends(get_db), _admin: str = Depends(get_current_admin)):
    """
    Returns recent daemon/service related log events from APILog.
    """
    rows = (
        db.query(APILog)
        .filter(APILog.action.in_([
            "service_down", "service_auto_restart", "service_auto_restart_failed",
            "service_manual_restart", "service_health_check", "service_toggled", "daemon_toggled"
        ]))
        .order_by(APILog.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [
        {"id": r.id, "user": r.user, "action": r.action, "details": r.details, "timestamp": r.timestamp.isoformat()}
        for r in rows
    ]


# -----------------------
# Background daemon
# -----------------------
async def _service_daemon_loop():
    """
    Background loop that periodically checks services and auto-restarts if configured.
    Runs while global _DAEMON_RUNNING is True.
    """
    global _DAEMON_RUNNING
    # ensure only one loop runs in this process
    async with _daemon_lock:
        try:
            while _DAEMON_RUNNING:
                # iterate services
                db = SessionLocal()
                try:
                    services = db.query(SystemService).filter(SystemService.status == True).all()
                    for svc in services:
                        try:
                            # perform health probe (async)
                            health = await real_health_check(svc)
                        except Exception:
                            health = "error"

                        svc.last_check = datetime.utcnow()
                        svc.health = health
                        db.add(svc)
                        db.commit()

                        if health in ("offline", "error") and svc.auto_restart:
                            # attempt restart
                            log_event(db, user=None, action="service_down", details={"service_id": svc.id, "name": svc.name, "health": health})
                            ok = _restart_service_db(db, svc)
                            if ok:
                                log_event(db, user=None, action="service_auto_restart", details={"service_id": svc.id, "name": svc.name})
                            else:
                                log_event(db, user=None, action="service_auto_restart_failed", details={"service_id": svc.id, "name": svc.name})
                    # close db for this run
                except Exception:
                    # ensure we don't crash the daemon loop
                    traceback.print_exc()
                    try:
                        db.rollback()
                    except Exception:
                        pass
                finally:
                    db.close()

                # sleep until next interval (allow graceful cancellation)
                await asyncio.sleep(DAEMON_INTERVAL_SECONDS)
        finally:
            # daemon exiting; ensure flag is false
            _DAEMON_RUNNING = False


# -----------------------
# Public helper to start the daemon (to be called from main.py startup)
# -----------------------
def register_background_daemon(app):
    """
    Call this from main.py during startup:
        app.add_event_handler("startup", lambda: start_services_daemon(app))
        app.add_event_handler("shutdown", lambda: stop_services_daemon())
    Or simply:
        start_services_daemon()  # synchronous call schedules the async loop
    This function sets the running flag and schedules the async loop.
    """
    # set running flag and schedule loop
    global _DAEMON_RUNNING
    if _DAEMON_RUNNING:
        return False

    _DAEMON_RUNNING = True

    # schedule the loop in the running event loop
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None

    async def _spawn():
        # ensure small delay to let app finish startup tasks
        await asyncio.sleep(1)
        await _service_daemon_loop()

    if loop and loop.is_running():
        # schedule without blocking
        asyncio.create_task(_spawn())
    else:
        # no running loop (unlikely in FastAPI) — run in new loop
        def _runner():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            new_loop.run_until_complete(_spawn())
            new_loop.close()
        import threading
        t = threading.Thread(target=_runner, daemon=True)
        t.start()

    # log start event (best-effort)
    try:
        db = SessionLocal()
        log_event(db, user=None, action="daemon_started", details={"interval": DAEMON_INTERVAL_SECONDS})
        db.close()
    except Exception:
        pass

    return True


def stop_services_daemon():
    """
    Stop the daemon loop by clearing running flag.
    """
    global _DAEMON_RUNNING
    _DAEMON_RUNNING = False
    # log stop event (best-effort)
    try:
        db = SessionLocal()
        log_event(db, user=None, action="daemon_stopped", details={})
        db.close()
    except Exception:
        pass
    return True
