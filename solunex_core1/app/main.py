# -*- coding: utf-8 -*-
"""
Solunex Core 1 - License Control Server
---------------------------------------
Central engine for:
- License management
- Device binding
- Public + Internal verification
- Admin tools
- Analytics
- Core service health
"""

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import Base, engine, SessionLocal
from sqlalchemy.orm import Session
import os

# -----------------------------
# Create DB tables FIRST
# -----------------------------
print("🔧 Creating database tables...")
Base.metadata.create_all(bind=engine)
print("✅ All tables created successfully!")


# -----------------------------
# Import Models
# -----------------------------
from app.models.user_model import User
from app.models.license_model import License
from app.models.logs_model import APILog


# -----------------------------
# Import Routers
# -----------------------------
from app.api.admin_auth import router as admin_auth_router
from app.api.dashboard import router as dashboard_router
from app.api.users import router as users_router
from app.api.announcements import router as announcements_router
from app.api.analytics import router as analytics_router
from app.api.license_bank import router as license_bank_router
from app.api.services import router as services_router
from app.api.internal_orders import router as internal_orders_router



# 🔐 INTERNAL secure license API
from app.api.license_verify import router as license_verify_router

# 🔐 PUBLIC secure client API
from app.api.public_license_api import router as public_license_router

# Import dependencies
from app.utils.auth import get_current_admin

# -----------------------------
# FastAPI Init
# -----------------------------
app = FastAPI(title="Solunex Core 1 - License Server")


# -----------------------------
# Static + Templates
# -----------------------------
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

print(">>> Template path:", templates.env.loader.searchpath)
print(">>> Running from:", os.path.abspath(os.getcwd()))
print(">>> main.py located at:", os.path.abspath(__file__))


# ----------------------------------------------------------
# ROUTER ORDER (VERY IMPORTANT)
# ----------------------------------------------------------

# 1. Admin auth & dashboard
app.include_router(admin_auth_router)
app.include_router(dashboard_router)

# 2. Admin functional APIs
app.include_router(users_router)
app.include_router(announcements_router)
app.include_router(license_bank_router)
app.include_router(analytics_router)
app.include_router(services_router)
app.include_router(internal_orders_router)

# 3. Internal license API (Core-2 → Core-1)
app.include_router(license_verify_router)

# 4. Public developer API (SDKs)
app.include_router(public_license_router)

# after app = FastAPI(...)
from app.api import services as services_module

# start the daemon when the app starts
app.add_event_handler("startup", lambda: services_module.register_background_daemon(app))
app.add_event_handler("shutdown", lambda: services_module.stop_services_daemon())


# ❌  WARNING:
# The OLD license router is intentionally removed for security:
# app.include_router(license_router)


# ----------------------------------------------------------
# ROOT ROUTE — Always redirect to admin/login
# ----------------------------------------------------------
@app.get("/", include_in_schema=False)
def root_redirect(request: Request):

    # Check if first-time setup
    db: Session = SessionLocal()
    admin_exists = db.query(User).first()
    db.close()

    if not admin_exists:
        return RedirectResponse(url="/admin/register", status_code=303)

    return RedirectResponse(url="/admin/login", status_code=303)


# ----------------------------------------------------------
# Admin HTML Pages
# ----------------------------------------------------------
@app.get("/admin/dashboard/view", response_class=HTMLResponse)
def dashboard_page(request: Request, _admin=Depends(get_current_admin)):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/admin/posting", include_in_schema=False)
def posting_page(request: Request, _admin=Depends(get_current_admin)):
    return templates.TemplateResponse("posting.html", {"request": request})

@app.get("/admin/license_bank", response_class=HTMLResponse)
def license_bank_page(request: Request, _admin=Depends(get_current_admin)):
    return templates.TemplateResponse("license_bank.html", {"request": request})

@app.get("/admin/services/view", response_class=HTMLResponse)
def services_page(request: Request, _admin=Depends(get_current_admin)):
    return templates.TemplateResponse("services.html", {"request": request})


# ----------------------------------------------------------
# System Status
# ----------------------------------------------------------
@app.get("/api/status", tags=["system"])
def root_status():
    return {"status": "solunex_core1", "message": "License control server running"}
