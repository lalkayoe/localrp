"""
Security primitives used by the auth module.

- Argon2id for password hashing (argon2-cffi, sane default params).
- JWT access tokens, short-lived, sent in an Authorization header.
- Refresh tokens, long-lived, stored hashed in DB, delivered via
  HttpOnly + Secure + SameSite=strict cookie.
- CSRF: double-submit token, required on any state-changing request
  that relies on the refresh cookie (i.e. the /auth/refresh endpoint).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import settings

_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


# --- Passwords ---------------------------------------------------------

def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plain)
    except VerifyMismatchError:
        return False


def password_needs_rehash(hashed: str) -> bool:
    return _ph.check_needs_rehash(hashed)


# --- JWT access tokens ---------------------------------------------------

def create_access_token(user_id: str, is_admin: bool) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "adm": is_admin,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    """Raises jwt exceptions on invalid/expired tokens — caller (dependency) handles them."""
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


# --- Refresh tokens (opaque, stored hashed in DB) -------------------------

def generate_refresh_token() -> tuple[str, str, datetime]:
    """Returns (raw_token_for_cookie, sha256_hash_for_db, expires_at)."""
    raw = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    expires_at = datetime.utcnow() + timedelta(days=settings.refresh_token_ttl_days)
    return raw, token_hash, expires_at


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# --- CSRF (double-submit cookie pattern) ----------------------------------

def generate_csrf_token(session_id: str) -> str:
    ts = str(int(time.time()))
    msg = f"{session_id}:{ts}"
    sig = hmac.new(settings.csrf_secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return f"{ts}.{sig}"


def verify_csrf_token(session_id: str, token: str, max_age_seconds: int = 60 * 60 * 24) -> bool:
    try:
        ts_str, sig = token.split(".", 1)
        ts = int(ts_str)
    except (ValueError, AttributeError):
        return False
    if time.time() - ts > max_age_seconds:
        return False
    expected_msg = f"{session_id}:{ts_str}"
    expected_sig = hmac.new(settings.csrf_secret.encode(), expected_msg.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_sig, sig)
