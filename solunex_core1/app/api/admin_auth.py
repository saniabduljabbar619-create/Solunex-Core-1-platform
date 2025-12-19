# app/api/admin_auth.py
# -*- coding: utf-8 -*-

from fastapi import APIRouter, Form, HTTPException, status, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from config import ADMIN_USERNAME
from app.utils.auth import verify_password, create_admin_token

ADMIN_PASSWORD_HASH = "$2b$12$lDTNAvKdb/N81WNFPsy/0.LGXNjC4HQe/7oNfKSiDyCCnIz5zJLJ2"

router = APIRouter(prefix="/admin", tags=["admin-auth"])

templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):

    if username != ADMIN_USERNAME:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if not verify_password(password, ADMIN_PASSWORD_HASH):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_admin_token(username)

    response = RedirectResponse("/admin/dashboard/view", status_code=302)


    response.set_cookie(
        key="sol_admin",
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=86400,
        path="/"
    )

    return response


@router.get("/logout")
def logout():
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie("sol_admin", path="/")
    return response
