"""
Security primitives: token generation/hashing, security headers, rate limiting,
IP hashing, admin/job auth. No passwords exist in this system — magic links only —
so token hashing is sha256 over 256-bit random values (slow hashes are for
low-entropy secrets; these are high-entropy).
"""
import hashlib
import hmac
import os
import secrets
import time
from collections import deque
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy import delete, func, select
from starlette.middleware.base import BaseHTTPMiddleware

from .models import RateCounter

# Pepper for hashing emails/IPs at rest. Set in prod; random-per-boot in dev
# (dev consequence: identities don't survive restarts, which is fine).
PEPPER = os.environ.get("RMS_PEPPER") or secrets.token_hex(32)
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
JOB_TOKEN = os.environ.get("JOB_TOKEN", "")
ENV = os.environ.get("RMS_ENV", "dev")  # dev | prod
# Number of trusted proxy hops in front of the app (App Runner/ALB = 1).
# The client IP is taken this many entries from the RIGHT of X-Forwarded-For,
# because upstream proxies APPEND; the leftmost entries are attacker-controlled.
TRUSTED_PROXY_HOPS = int(os.environ.get("TRUSTED_PROXY_HOPS", "1"))
ALLOWED_ORIGINS = [o for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o]


def validate_prod_env() -> None:
    """Fail closed at startup in prod. A misconfigured privacy system must NOT boot."""
    if ENV != "prod":
        return
    problems = []
    if not os.environ.get("RMS_PEPPER") or len(os.environ.get("RMS_PEPPER", "")) < 32:
        problems.append("RMS_PEPPER must be set (>=32 chars) in prod — random per-boot pepper orphans identities")
    if not os.environ.get("DATABASE_URL", "").startswith("postgres"):
        problems.append("DATABASE_URL must be a Postgres URL in prod — SQLite is ephemeral on a PaaS")
    if not ADMIN_TOKEN or len(ADMIN_TOKEN) < 32:
        problems.append("ADMIN_TOKEN must be set (>=32 chars) in prod")
    if not JOB_TOKEN or len(JOB_TOKEN) < 32:
        problems.append("JOB_TOKEN must be set (>=32 chars) in prod")
    mp = os.environ.get("MAIL_PROVIDER", "console")
    if mp == "console":
        # console mailer logs live magic links — never in prod. (Anonymous-only launch:
        # set MAIL_PROVIDER=disabled to run with sign-in switched off but not logging links.)
        problems.append("MAIL_PROVIDER=console leaks magic links to logs in prod; set 'smtp' or 'disabled'")
    elif mp == "smtp" and not os.environ.get("SMTP_HOST"):
        problems.append("MAIL_PROVIDER=smtp but SMTP_HOST is empty (would silently fall back to logging links)")
    if problems:
        raise RuntimeError("PROD CONFIG REFUSED:\n  - " + "\n  - ".join(problems))


def new_token() -> str:
    return secrets.token_urlsafe(32)  # 256 bits


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_email(email: str) -> str:
    return hmac.new(PEPPER.encode(), email.strip().lower().encode(), hashlib.sha256).hexdigest()


def hash_ip(ip: str) -> str:
    return hmac.new(PEPPER.encode(), ip.encode(), hashlib.sha256).hexdigest()[:32]


def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


# ---------- Password hashing (stdlib PBKDF2, peppered) ----------
_PBKDF2_ITERS = 210_000


def hash_password(pw: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", (pw + PEPPER).encode(), bytes.fromhex(salt), _PBKDF2_ITERS)
    return f"pbkdf2_sha256${_PBKDF2_ITERS}${salt}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _algo, iters, salt, h = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", (pw + PEPPER).encode(), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(dk.hex(), h)
    except Exception:  # noqa: BLE001
        return False


def client_ip(request: Request) -> str:
    """Take the IP TRUSTED_PROXY_HOPS from the RIGHT of X-Forwarded-For.
    Upstream proxies append, so the rightmost hops are trustworthy and the
    leftmost are attacker-supplied. Trusting the left (the old bug) let an
    attacker forge a fresh identity per request and defeat every IP-keyed control."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            idx = len(parts) - TRUSTED_PROXY_HOPS
            if 0 <= idx < len(parts):
                return parts[idx]
            return parts[0]  # fewer hops than expected: fall back to leftmost (still bounded)
    return request.client.host if request.client else "unknown"


# ---------- Security headers ----------
CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        resp.headers["Content-Security-Policy"] = CSP
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        if ENV == "prod":
            resp.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return resp


# ---------- In-memory per-IP sliding window (general endpoints, per instance) ----------
class SlidingWindowLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max = max_requests
        self.window = window_seconds
        self.hits: dict[str, deque] = {}

    def check(self, key: str) -> bool:
        now = time.monotonic()
        q = self.hits.setdefault(key, deque())
        while q and q[0] < now - self.window:
            q.popleft()
        if len(q) >= self.max:
            return False
        q.append(now)
        if len(self.hits) > 50_000:  # memory guard
            self.hits.clear()
        return True


GENERAL_LIMIT = SlidingWindowLimiter(max_requests=120, window_seconds=60)
WRITE_LIMIT = SlidingWindowLimiter(max_requests=20, window_seconds=60)
AUTH_LIMIT = SlidingWindowLimiter(max_requests=10, window_seconds=300)


MAX_BODY_BYTES = 64 * 1024  # 64 KB: generous for a 10-item rating, hostile to flooders


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Reject oversized bodies before parsing (DoS amplifier guard).
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > MAX_BODY_BYTES:
            from starlette.responses import JSONResponse
            return JSONResponse(status_code=413, content={"ok": False, "detail": "request body too large"})
        ip = client_ip(request)
        if not GENERAL_LIMIT.check(f"g:{ip}"):
            return _resp_429()
        if request.method in ("POST", "DELETE", "PUT", "PATCH"):
            # Login-CSRF / cross-origin write guard: when an Origin is present it
            # must be same-origin (or explicitly allowlisted). Same-origin browser
            # requests omit Origin or send our own; forged cross-site posts send theirs.
            origin = request.headers.get("origin")
            if origin and not _origin_ok(request, origin):
                from starlette.responses import JSONResponse
                return JSONResponse(status_code=403, content={"ok": False, "detail": "cross-origin request refused"})
            limiter = AUTH_LIMIT if request.url.path.startswith("/v1/auth") else WRITE_LIMIT
            if not limiter.check(f"w:{ip}"):
                return _resp_429()
        return await call_next(request)


def _origin_ok(request, origin: str) -> bool:
    if origin in ALLOWED_ORIGINS:
        return True
    # Same-origin: Origin scheme+host[:port] equals the request's own.
    base = os.environ.get("BASE_URL", "")
    if base and origin.rstrip("/") == base.rstrip("/"):
        return True
    host = request.headers.get("host", "")
    return origin.split("://")[-1] == host


def _resp_429():
    from starlette.responses import JSONResponse
    return JSONResponse(status_code=429, content={"ok": False, "detail": "Too many requests. Slow down."})


def raise_429():
    raise HTTPException(status_code=429, detail="Too many requests. Slow down.")


# ---------- DB-backed counters (multi-instance safe, for sensitive buckets) ----------
def db_rate_check(db, bucket: str, max_events: int, window_minutes: int) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    db.execute(delete(RateCounter).where(RateCounter.at < cutoff))
    n = db.execute(select(func.count()).select_from(RateCounter)
                   .where(RateCounter.bucket == bucket, RateCounter.at >= cutoff)).scalar_one()
    if n >= max_events:
        db.commit()  # keep the cleanup delete durable even when we refuse
        raise_429()
    db.add(RateCounter(bucket=bucket))
    db.flush()


# ---------- Admin / job auth ----------
def require_admin(request: Request) -> None:
    tok = request.headers.get("x-admin-token", "")
    if ENV == "prod" and (not ADMIN_TOKEN or len(ADMIN_TOKEN) < 32):
        raise HTTPException(503, "admin disabled: ADMIN_TOKEN not configured")
    if not ADMIN_TOKEN or not tok or not constant_time_eq(tok, ADMIN_TOKEN):
        raise HTTPException(401, "admin auth required")


def require_job(request: Request) -> None:
    """Accepts the job token (EventBridge) or the admin token (manual trigger)."""
    if ENV == "prod" and (not JOB_TOKEN or len(JOB_TOKEN) < 32) and (not ADMIN_TOKEN or len(ADMIN_TOKEN) < 32):
        raise HTTPException(503, "jobs disabled: no strong token configured")
    job_tok = request.headers.get("x-job-token", "")
    adm_tok = request.headers.get("x-admin-token", "")
    ok_job = JOB_TOKEN and len(JOB_TOKEN) >= 32 and job_tok and constant_time_eq(job_tok, JOB_TOKEN)
    ok_admin = ADMIN_TOKEN and len(ADMIN_TOKEN) >= 32 and adm_tok and constant_time_eq(adm_tok, ADMIN_TOKEN)
    if not (ok_job or ok_admin):
        raise HTTPException(401, "job auth required")
