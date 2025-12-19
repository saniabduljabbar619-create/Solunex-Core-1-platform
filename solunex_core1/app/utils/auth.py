# -*- coding: utf-8 -*-
"""
Authentication & JWT for Solunex Admin (Cookie-Based)
"""

import jwt
from datetime import datetime, timedelta
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends, Request
from config import JWT_SECRET, JWT_ALGORITHM

# -------------------------------------------------------------
# Password Hashing (bcrypt)
# -------------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password[:72])

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password[:72], hashed_password)
    except Exception:
        return False


# -------------------------------------------------------------
# JWT Token Management
# -------------------------------------------------------------
def create_admin_token(username: str, expires_in_minutes: int = 240) -> str:
    payload = {
        "sub": username,
        "exp": datetime.utcnow() + timedelta(minutes=expires_in_minutes),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please login again."
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token."
        )


# -------------------------------------------------------------
# COOKIE-BASED ADMIN AUTH (FINAL, STABLE VERSION)
# -------------------------------------------------------------

from fastapi import Request, HTTPException

def get_current_admin(request: Request):
    token = request.cookies.get("sol_admin")

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_token(token)
    username = payload.get("sub")

    if not username:
        raise HTTPException(status_code=401, detail="Invalid token")

    return username
