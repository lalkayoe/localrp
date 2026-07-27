"""
Auth routes.

Flow:
- First run: no users exist -> POST /auth/setup creates the admin account.
  This endpoint is only reachable while the users table is empty.
- Login: POST /auth/login -> sets HttpOnly refresh cookie, returns access
  token + csrf token in the body (access token is kept in memory on the
  frontend, never in a cookie, so it can't be exfiltrated via CSRF).
- Refresh: POST /auth/refresh -> reads the refresh cookie + CSRF header,
  rotates the refresh token (old one revoked), issues a new access token.
- Logout: POST /auth/logout -> revokes the refresh token, clears cookie.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.models import RefreshToken, User
from app.schemas.auth import (
    ChangePasswordRequest, LoginRequest, RegisterAdminRequest, TokenResponse, UserResponse,
)
from app.services.auth.deps import get_current_user, limiter
from app.services.auth.security import (
    create_access_token, generate_csrf_token, generate_refresh_token, hash_password,
    hash_refresh_token, verify_csrf_token, verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "localrp_refresh"


def _set_refresh_cookie(response: Response, raw_token: str, expires_at: datetime) -> None:
    # expires_at is stored/compared as naive UTC elsewhere (DB column, refresh-token
    # expiry checks); Starlette's set_cookie(usegmt=True) requires a tz-aware datetime,
    # so attach UTC tzinfo only for this call.
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        secure=True,
        samesite="strict",
        expires=expires_at.replace(tzinfo=timezone.utc),
        path="/auth",
    )


@router.get("/setup-required")
async def setup_required(db: AsyncSession = Depends(get_db)) -> dict:
    count = (await db.execute(select(func.count(User.id)))).scalar_one()
    return {"setup_required": count == 0}


@router.post("/setup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def setup_admin(payload: RegisterAdminRequest, db: AsyncSession = Depends(get_db)) -> User:
    count = (await db.execute(select(func.count(User.id)))).scalar_one()
    if count > 0:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin already configured")

    user = User(username=payload.username, password_hash=hash_password(payload.password), is_admin=True)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, response: Response, payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    result = await db.execute(select(User).where(User.username == payload.username))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    raw_refresh, refresh_hash, expires_at = generate_refresh_token()
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=expires_at,
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()

    _set_refresh_cookie(response, raw_refresh, expires_at)
    access_token = create_access_token(user.id, user.is_admin)
    csrf_token = generate_csrf_token(user.id)
    return TokenResponse(access_token=access_token, csrf_token=csrf_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    raw_token = request.cookies.get(REFRESH_COOKIE_NAME)
    csrf_header = request.headers.get("X-CSRF-Token")
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")

    token_hash = hash_refresh_token(raw_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    token_row = result.scalar_one_or_none()

    if token_row is None or token_row.revoked or token_row.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token invalid or expired")

    if not csrf_header or not verify_csrf_token(token_row.user_id, csrf_header):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")

    user = await db.get(User, token_row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    # Only rotate the refresh token itself once it's getting close to its own
    # expiry. Rotating on every single silent refresh is what causes random
    # logouts: a browser fires several requests in parallel, more than one of
    # them hits this 401-and-refresh path at once, and if the first refresh
    # call revokes the token before the second one is checked, the second
    # gets a false "invalid" error even though the session is fine. Leaving
    # the same refresh token/cookie in place for most of its life means
    # concurrent refreshes just succeed against the same still-valid row.
    rotate_threshold = timedelta(days=settings.refresh_rotate_threshold_days)
    if token_row.expires_at - datetime.utcnow() < rotate_threshold:
        token_row.revoked = True
        new_raw, new_hash, new_expires = generate_refresh_token()
        db.add(RefreshToken(
            user_id=user.id,
            token_hash=new_hash,
            expires_at=new_expires,
            user_agent=request.headers.get("user-agent"),
        ))
        await db.commit()
        _set_refresh_cookie(response, new_raw, new_expires)

    access_token = create_access_token(user.id, user.is_admin)
    csrf_token = generate_csrf_token(user.id)
    return TokenResponse(access_token=access_token, csrf_token=csrf_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> None:
    raw_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw_token:
        token_hash = hash_refresh_token(raw_token)
        result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        token_row = result.scalar_one_or_none()
        if token_row:
            token_row.revoked = True
            await db.commit()
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/auth")


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Old password incorrect")
    user.password_hash = hash_password(payload.new_password)
    # revoke all existing refresh tokens on password change
    result = await db.execute(select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked == False))  # noqa: E712
    for token_row in result.scalars():
        token_row.revoked = True
    await db.commit()


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
