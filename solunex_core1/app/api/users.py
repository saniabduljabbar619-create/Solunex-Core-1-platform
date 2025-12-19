# -*- coding: utf-8 -*-
"""
Admin Authentication & Access Control
-------------------------------------
Handles registration, login, session cookies, and dashboard protection.
All Solunex Core 1 admin access flows pass through this router.
"""

from fastapi import (
    APIRouter, Depends, HTTPException, Request, Form, Response
)
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.utils.auth import (
    hash_password, verify_password, create_admin_token, decode_token
)
from app.models.user_model import User
from config import SessionLocal

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")

# ----------------------------------------------------------
# Database Dependency
# ----------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ----------------------------------------------------------
# Register Page (GET)
# ----------------------------------------------------------
@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    """Render the admin registration page."""
    return templates.TemplateResponse("register.html", {"request": request})

# ----------------------------------------------------------
# Register (POST)
# ----------------------------------------------------------
@router.post("/register", response_class=HTMLResponse)
def register_admin(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Creates a new admin account if not already registered."""
    existing_user = (
        db.query(User)
        .filter((User.username == username) | (User.email == email))
        .first()
    )

    if existing_user:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Username or email already exists. Please login instead."
            }
        )

    hashed_pwd = hash_password(password)
    new_user = User(username=username, email=email, password_hash=hashed_pwd, role="admin")
    db.add(new_user)
    db.commit()

    return RedirectResponse(url="/login", status_code=303)

# ----------------------------------------------------------
# Login Page (GET)
# ----------------------------------------------------------
@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    """Render the admin login page."""
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

# ----------------------------------------------------------
# Login (POST)
# ----------------------------------------------------------
@router.post("/login", response_class=HTMLResponse)
def login_admin(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Handles login, verifies credentials, and sets JWT cookie."""
    user = db.query(User).filter(User.username == username).first()

    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password."}
        )

    token = create_admin_token(user.username)
    expire_time = datetime.utcnow() + timedelta(hours=12)

    # ✅ Redirect to correct path (/admin/dashboard)
    response = RedirectResponse(url="/admin/dashboard", status_code=303)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=False,  # set to True when deploying with HTTPS
        samesite="lax",
        expires=expire_time.strftime("%a, %d-%b-%Y %H:%M:%S GMT")
    )
    return response


# ----------------------------------------------------------
# Dashboard (Protected)
# ----------------------------------------------------------
@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    """Accessible only to authenticated admins."""
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse(url="/admin/login", status_code=303)

    try:
        user_data = decode_token(token)
        username = user_data.get("sub")
    except Exception:
        return RedirectResponse(url="/admin/login", status_code=303)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "username": username,
            "server_status": "✅ Online",
            "description": "Welcome to the Solunex Core 1 Control Center."
        }
    )


# ----------------------------------------------------------
# Logout (Clear Cookie)
# ----------------------------------------------------------
@router.get("/logout")
def logout():
    """Logs out admin by clearing the session token."""
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("access_token")
    return response
