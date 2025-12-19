# app/utils/signer.py
import hmac
import hashlib
import time
import json
import threading
from typing import Optional
from fastapi import Request, HTTPException, status
from starlette.datastructures import Headers

try:
    import redis
except Exception:
    redis = None

from config import (
    HMAC_SECRET,
    HMAC_TIMESTAMP_TOLERANCE,
    HMAC_NONCE_TTL,
    REDIS_URL,
    HMAC_ALLOW_LOCAL_BYPASS,
)

# -----------------------------
# NONCE STORAGE
# -----------------------------
_nonce_lock = threading.Lock()
_nonce_store = {}  # nonce -> expiry_ts


def _get_redis_client():
    if REDIS_URL and redis:
        try:
            return redis.from_url(REDIS_URL)
        except Exception:
            return None
    return None


def _store_nonce_redis(rcli, nonce, ttl):
    key = f"solunex:nonce:{nonce}"
    was_set = rcli.setnx(key, 1)
    if was_set:
        rcli.expire(key, ttl)
    return was_set


def _store_nonce_memory(nonce, ttl):
    with _nonce_lock:
        now = int(time.time())
        expired = [n for n, e in _nonce_store.items() if e <= now]
        for n in expired:
            _nonce_store.pop(n, None)

        if nonce in _nonce_store:
            return False

        _nonce_store[nonce] = now + ttl
        return True


def _validate_and_store_nonce(nonce: str) -> bool:
    ttl = int(HMAC_NONCE_TTL or 60)
    rcli = _get_redis_client()

    if rcli:
        try:
            return _store_nonce_redis(rcli, nonce, ttl)
        except Exception:
            return _store_nonce_memory(nonce, ttl)
    else:
        return _store_nonce_memory(nonce, ttl)


# -----------------------------
# JSON CANONICALIZATION
# -----------------------------
def canonical_json(text: str) -> str:
    if not text:
        return ""
    try:
        obj = json.loads(text)
        return json.dumps(obj, separators=(",", ":"), sort_keys=True)
    except Exception:
        return text.strip()


# -----------------------------
# SIGNATURE COMPUTATION
# -----------------------------
def compute_signature(secret: str, timestamp: str, nonce: str, method: str, path: str, body: str) -> str:
    base = f"{timestamp}:{nonce}:{method.upper()}:{path}:{body}"
    mac = hmac.new(secret.encode("utf-8"), base.encode("utf-8"), hashlib.sha256)
    return mac.hexdigest().lower()


# -----------------------------
# SIGNATURE VERIFICATION
# -----------------------------
def verify_request_signature(headers: Headers, method: str, path: str, body: str):
    if not HMAC_SECRET:
        raise HTTPException(500, "HMAC_SECRET not configured")

    sig = headers.get("x-solunex-signature")
    ts = headers.get("x-solunex-timestamp")
    nonce = headers.get("x-solunex-nonce")

    if not sig or not ts or not nonce:
        raise HTTPException(401, "Missing HMAC headers")

    sig = sig.lower()

    # Timestamp validation
    try:
        ts_int = int(ts)
    except Exception:
        raise HTTPException(400, "Invalid timestamp")

    now = int(time.time())
    if abs(now - ts_int) > int(HMAC_TIMESTAMP_TOLERANCE or 15):
        raise HTTPException(401, "Timestamp outside allowed window")

    # Replay protection
    if not _validate_and_store_nonce(nonce):
        raise HTTPException(401, "Nonce already used")

    # Compute expected
    expected = compute_signature(HMAC_SECRET, ts, nonce, method, path, body)

    if not hmac.compare_digest(expected, sig):
        raise HTTPException(401, "Invalid signature")


# -----------------------------
# FASTAPI DEPENDENCY
# -----------------------------
async def require_hmac(request: Request):
    # OPTIONAL: localhost bypass for dev-only
    if HMAC_ALLOW_LOCAL_BYPASS:
        client = request.client.host if request.client else None
        if client in ("127.0.0.1", "::1", "localhost"):
            return True

    # Canonical body
    try:
        raw = await request.body()
        try:
            body = raw.decode("utf-8")
        except:
            body = ""
    except:
        body = ""

    body = canonical_json(body)

    # Path normalization
    path = request.url.path.rstrip("/") or "/"
    if request.url.query:
        path = f"{path}?{request.url.query}"

    verify_request_signature(
        request.headers,
        request.method,
        path,
        body,
    )

    return True
