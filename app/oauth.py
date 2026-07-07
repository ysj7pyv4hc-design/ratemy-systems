"""
Social sign-in (OAuth 2.0) — Google, GitHub, Apple.

Design goals mirror the rest of the app:
- A provider is ENABLED only if its client id + secret are set in env, so the site
  runs with whatever subset is configured (long-tail friendly, nothing hard-required).
- We store only a *hashed* provider user id linked to a rater — no third-party tokens,
  no profile data retained. Same identity-separation posture as magic-link.
- Standard authorization-code flow with a DB-stored `state` (CSRF) that expires.

Stdlib HTTP only (urllib) — no new dependencies.
"""
import hashlib
import hmac
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .auth import establish_session, mint_handle
from .db import get_db
from .models import AuditLog, OauthIdentity, OauthState, Rater
from .security import PEPPER, new_token

router = APIRouter(prefix="/v1/auth/oauth", tags=["oauth"])

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080")


def _cfg(provider: str):
    cid = os.environ.get(f"{provider.upper()}_CLIENT_ID", "")
    csecret = os.environ.get(f"{provider.upper()}_CLIENT_SECRET", "")
    return cid, csecret


# Provider endpoints + how to read the user id/email from their response.
PROVIDERS = {
    "google": {
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "userinfo": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email",
        "extra_authorize": {"access_type": "online", "prompt": "select_account"},
    },
    "github": {
        "authorize": "https://github.com/login/oauth/authorize",
        "token": "https://github.com/login/oauth/access_token",
        "userinfo": "https://api.github.com/user",
        "scope": "read:user user:email",
        "extra_authorize": {},
    },
    # Apple is scaffolded but requires a paid Apple Developer account + a signed-JWT
    # client secret (APPLE_* keys). Enabled only when fully configured; left dormant otherwise.
    "apple": {
        "authorize": "https://appleid.apple.com/auth/authorize",
        "token": "https://appleid.apple.com/auth/token",
        "userinfo": None,          # Apple returns an id_token instead of a userinfo endpoint
        "scope": "name email",
        "extra_authorize": {"response_mode": "form_post"},
    },
}


def enabled_providers() -> list[str]:
    out = []
    for p in PROVIDERS:
        cid, csecret = _cfg(p)
        if cid and csecret:
            out.append(p)
    return out


def _redirect_uri(provider: str) -> str:
    return f"{BASE_URL}/v1/auth/oauth/{provider}/callback"


def _hash_uid(provider: str, subject: str) -> str:
    return hmac.new(PEPPER.encode(), f"{provider}:{subject}".encode(), hashlib.sha256).hexdigest()


def _http_post_form(url: str, data: dict, headers: dict) -> dict:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, headers={"Accept": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _http_get_json(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                               "Accept": "application/json",
                                               "User-Agent": "ratemy-systems"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


@router.get("/{provider}/login")
def oauth_login(provider: str, db: Session = Depends(get_db)):
    if provider not in enabled_providers():
        raise HTTPException(404, "provider not enabled")
    cid, _ = _cfg(provider)
    state = new_token()
    db.add(OauthState(state=state, provider=provider,
                      expires_at=datetime.now(timezone.utc) + timedelta(minutes=15)))
    db.commit()
    params = {
        "client_id": cid,
        "redirect_uri": _redirect_uri(provider),
        "response_type": "code",
        "scope": PROVIDERS[provider]["scope"],
        "state": state,
        **PROVIDERS[provider]["extra_authorize"],
    }
    url = PROVIDERS[provider]["authorize"] + "?" + urllib.parse.urlencode(params)
    return Response(status_code=307, headers={"Location": url})


@router.get("/{provider}/callback")
def oauth_callback(provider: str, request: Request, db: Session = Depends(get_db),
                   code: str = "", state: str = ""):
    if provider not in enabled_providers():
        raise HTTPException(404, "provider not enabled")
    # Verify + consume state (CSRF).
    row = db.execute(select(OauthState).where(OauthState.state == state,
                                              OauthState.provider == provider)).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    exp = row.expires_at if (row and row.expires_at.tzinfo) else (row.expires_at.replace(tzinfo=timezone.utc) if row else None)
    if row is None or exp < now:
        raise HTTPException(400, "invalid or expired sign-in state")
    db.execute(delete(OauthState).where(OauthState.id == row.id))
    if not code:
        raise HTTPException(400, "missing authorization code")

    cid, csecret = _cfg(provider)
    tok = _http_post_form(PROVIDERS[provider]["token"], {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": _redirect_uri(provider),
        "client_id": cid,
        "client_secret": csecret,
    }, headers={})
    access_token = tok.get("access_token")
    if not access_token:
        raise HTTPException(502, "token exchange failed")

    subject = _read_subject(provider, access_token, tok)
    if not subject:
        raise HTTPException(502, "could not read account id from provider")

    uid_hash = _hash_uid(provider, str(subject))
    ident = db.execute(select(OauthIdentity).where(
        OauthIdentity.provider == provider, OauthIdentity.provider_uid_hash == uid_hash
    )).scalar_one_or_none()
    if ident is None:
        rater = Rater(handle=mint_handle(db), tier="verified")
        db.add(rater)
        db.flush()
        db.add(OauthIdentity(provider=provider, provider_uid_hash=uid_hash, rater_id=rater.id))
        rater_id = rater.id
        db.add(AuditLog(actor_type="rater", actor_id=rater_id, verb=f"signup_{provider}"))
    else:
        rater_id = ident.rater_id
        db.add(AuditLog(actor_type="rater", actor_id=rater_id, verb=f"signin_{provider}"))

    resp = Response(status_code=307, headers={"Location": "/rate"})
    establish_session(db, rater_id, resp)
    db.commit()
    return resp


def _read_subject(provider: str, access_token: str, token_resp: dict) -> str | None:
    if provider == "google":
        info = _http_get_json(PROVIDERS["google"]["userinfo"], access_token)
        return info.get("sub")
    if provider == "github":
        info = _http_get_json(PROVIDERS["github"]["userinfo"], access_token)
        return str(info.get("id")) if info.get("id") is not None else None
    if provider == "apple":
        # Apple returns an id_token (JWT); the 'sub' claim is the stable user id.
        idt = token_resp.get("id_token")
        if not idt:
            return None
        try:
            import base64
            payload = idt.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload))
            return claims.get("sub")
        except Exception:
            return None
    return None
