"""
Passwordless auth: magic links → server-side sessions (httpOnly cookie) + CSRF header.
Identity separation: we store only HMAC-peppered email hashes; the address itself
is used once to send the link and never persisted.
"""
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import mailer
from .db import get_db
from .models import AuditLog, AuthSession, MagicLink, Rater, RaterIdentity
from .security import (ENV, client_ip, constant_time_eq, db_rate_check,
                       hash_email, hash_ip, hash_token, new_token)

router = APIRouter(prefix="/v1/auth", tags=["auth"])

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080")
SESSION_TTL_DAYS = 30
LINK_TTL_MINUTES = 15
COOKIE = "rms_session"


def _now():
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; treat stored values as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class MagicLinkIn(BaseModel):
    email: EmailStr


class VerifyIn(BaseModel):
    token: str = Field(min_length=20, max_length=128)


def _mint_handle(db: Session) -> str:
    for _ in range(20):
        h = f"rater-{secrets.token_hex(4)}"
        if not db.execute(select(Rater).where(Rater.handle == h)).scalar_one_or_none():
            return h
    raise HTTPException(500, "handle space exhausted (impossible)")


def mint_handle(db: Session) -> str:
    """Public alias — used by the OAuth module."""
    return _mint_handle(db)


def establish_session(db: Session, rater_id: str, response: Response) -> str:
    """Create a server-side session for a rater and set the cookie. Returns the CSRF token.
    Shared by magic-link verify and OAuth callbacks."""
    session_token = new_token()
    csrf = new_token()
    db.add(AuthSession(rater_id=rater_id, token_hash=hash_token(session_token), csrf_token=csrf,
                       expires_at=_now() + timedelta(days=SESSION_TTL_DAYS)))
    response.set_cookie(COOKIE, session_token, max_age=SESSION_TTL_DAYS * 86400,
                        httponly=True, samesite="lax", secure=(ENV == "prod"), path="/")
    return csrf


@router.post("/magic-link")
def request_magic_link(body: MagicLinkIn, request: Request, db: Session = Depends(get_db)):
    eh = hash_email(body.email)
    # DB-backed limits: 3 links/hour/email, 10/hour/IP — multi-instance safe.
    db_rate_check(db, f"ml:{eh}", max_events=3, window_minutes=60)
    db_rate_check(db, f"mlip:{hash_ip(client_ip(request))}", max_events=10, window_minutes=60)

    token = new_token()
    db.add(MagicLink(email_hash=eh, token_hash=hash_token(token),
                     expires_at=_now() + timedelta(minutes=LINK_TTL_MINUTES)))
    db.add(AuditLog(actor_type="anon", verb="magic_link_requested",
                    ip_hash=hash_ip(client_ip(request))))
    db.commit()  # durable before the mail leaves
    link = f"{BASE_URL}/verify?token={token}"
    try:
        mailer.send_magic_link(body.email, link)
    except mailer.MailUnavailable:
        # Sign-in switched off (anonymous-only launch). Uniform response either way —
        # never reveal config or whether the address is known.
        pass
    return {"ok": True, "message": "If that address is valid, a sign-in link is on its way."}


@router.post("/verify")
def verify_magic_link(body: VerifyIn, request: Request, response: Response,
                      db: Session = Depends(get_db)):
    th = hash_token(body.token)
    ml = db.execute(select(MagicLink).where(MagicLink.token_hash == th)).scalar_one_or_none()
    if ml is None or ml.used_at is not None or _aware(ml.expires_at) < _now():
        raise HTTPException(401, "Link is invalid, used, or expired. Request a fresh one.")
    ml.used_at = _now()

    ident = db.execute(select(RaterIdentity).where(RaterIdentity.email_hash == ml.email_hash)
                       ).scalar_one_or_none()
    if ident is None:
        rater = Rater(handle=_mint_handle(db), tier="verified")
        db.add(rater)
        db.flush()
        db.add(RaterIdentity(rater_id=rater.id, email_hash=ml.email_hash))
        rater_id = rater.id
    else:
        rater_id = ident.rater_id

    session_token = new_token()
    csrf = new_token()
    db.add(AuthSession(rater_id=rater_id, token_hash=hash_token(session_token), csrf_token=csrf,
                       expires_at=_now() + timedelta(days=SESSION_TTL_DAYS)))
    db.add(AuditLog(actor_type="rater", actor_id=rater_id, verb="signed_in",
                    ip_hash=hash_ip(client_ip(request))))
    db.commit()
    response.set_cookie(COOKIE, session_token, max_age=SESSION_TTL_DAYS * 86400,
                        httponly=True, samesite="lax", secure=(ENV == "prod"), path="/")
    return {"ok": True, "csrf": csrf}


def current_session(request: Request, db: Session) -> AuthSession | None:
    tok = request.cookies.get(COOKIE)
    if not tok:
        return None
    s = db.execute(select(AuthSession).where(AuthSession.token_hash == hash_token(tok))
                   ).scalar_one_or_none()
    if s is None or s.revoked_at is not None or _aware(s.expires_at) < _now():
        return None
    return s


def require_rater(request: Request, db: Session = Depends(get_db)) -> Rater:
    s = current_session(request, db)
    if s is None:
        raise HTTPException(401, "sign-in required")
    # CSRF: state-changing requests must echo the session's CSRF token.
    if request.method in ("POST", "DELETE", "PUT", "PATCH"):
        hdr = request.headers.get("x-csrf", "")
        if not hdr or not constant_time_eq(hdr, s.csrf_token):
            raise HTTPException(403, "missing or bad CSRF token")
    rater = db.get(Rater, s.rater_id)
    if rater is None:
        raise HTTPException(401, "sign-in required")
    return rater


def optional_rater(request: Request, db: Session) -> Rater | None:
    s = current_session(request, db)
    return db.get(Rater, s.rater_id) if s else None


@router.get("/providers")
def auth_providers():
    """Which sign-in methods are live (so the UI shows only working buttons)."""
    from .oauth import enabled_providers
    return {"ok": True,
            "email": os.environ.get("MAIL_PROVIDER", "console") not in ("disabled",),
            "oauth": enabled_providers(),
            "require_login": os.environ.get("REQUIRE_LOGIN", "false").lower() == "true"}


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    s = current_session(request, db)
    if s is None:
        return {"ok": True, "signed_in": False}
    r = db.get(Rater, s.rater_id)
    return {"ok": True, "signed_in": True, "handle": r.handle, "tier": r.tier, "csrf": s.csrf_token}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    s = current_session(request, db)
    if s:
        s.revoked_at = _now()
        db.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.delete("/identity")
def unlink_identity(request: Request, db: Session = Depends(get_db),
                    rater: Rater = Depends(require_rater)):
    """Charter §2.7: permanently unlink personhood from history. Facts survive, the person is gone."""
    db.execute(delete(RaterIdentity).where(RaterIdentity.rater_id == rater.id))
    db.execute(delete(AuthSession).where(AuthSession.rater_id == rater.id))
    db.add(AuditLog(actor_type="rater", actor_id=rater.id, verb="identity_unlinked"))
    db.commit()
    resp = Response(status_code=200, media_type="application/json",
                    content='{"ok": true, "message": "Identity unlinked. Your ratings remain as anonymous facts; nothing links them to you."}')
    resp.delete_cookie(COOKIE, path="/")
    return resp
