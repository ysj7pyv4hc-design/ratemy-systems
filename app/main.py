"""
Rate My Systems — app factory.
Same-origin by design: static frontend + API on one origin, so NO CORS middleware
exists (its absence is the policy). Security headers on everything.
"""
import asyncio
import logging
import mimetypes
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from . import admin, auth, config_loader, intake, oauth, public
from .db import Base, db_session, engine
from .publication import ensure_initial_snapshot, run_publication
from .security import (RateLimitMiddleware, SecurityHeadersMiddleware,
                       validate_prod_env)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("rms")

STATIC_DIR = Path(os.environ.get("STATIC_DIR", Path(__file__).resolve().parent.parent / "public"))
# In-process publication scheduler: keeps public scores fresh with ZERO external
# setup (no cron service needed). Default daily; set 10080 for weekly (max privacy),
# or 0 to disable and drive publication via the admin/job endpoint or an external cron.
PUBLISH_INTERVAL_MINUTES = int(os.environ.get("PUBLISH_INTERVAL_MINUTES", "1440"))


async def _publication_loop():
    """Periodically recompute snapshots. Never lets an error kill the loop."""
    interval = PUBLISH_INTERVAL_MINUTES * 60
    while True:
        try:
            await asyncio.sleep(interval)
            with db_session() as db:
                run_publication(db)
                db.commit()
            log.info("scheduled publication complete")
        except asyncio.CancelledError:
            break
        except Exception:
            log.exception("scheduled publication failed; will retry next interval")


def _wait_for_db(attempts: int = 10, delay: float = 3.0):
    """On a fresh PaaS deploy the web service can start a beat before the database
    is reachable. Retry the first connection instead of crash-looping."""
    import time

    from sqlalchemy import text
    last = None
    for i in range(attempts):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception as e:  # noqa: BLE001
            last = e
            log.warning("database not ready (attempt %d/%d): %s", i + 1, attempts, e)
            time.sleep(delay)
    raise RuntimeError(f"database unreachable after {attempts} attempts: {last}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_prod_env()   # fail closed: a misconfigured privacy system must not boot
    _wait_for_db()
    Base.metadata.create_all(engine)
    published = config_loader.publish_if_changed()   # invalid config raises → deploy fails loudly, old version keeps running
    if published:
        log.info("config published: %s", published)
    with db_session() as db:
        ensure_initial_snapshot(db)
    task = None
    if PUBLISH_INTERVAL_MINUTES > 0:
        task = asyncio.create_task(_publication_loop())
        log.info("publication scheduler on: every %d min", PUBLISH_INTERVAL_MINUTES)
    try:
        yield
    finally:
        if task:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass


app = FastAPI(title="Rate My Systems", docs_url=None, redoc_url=None, openapi_url=None,
              lifespan=lifespan)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)

app.include_router(auth.router)
app.include_router(oauth.router)
app.include_router(intake.router)
app.include_router(public.router)
app.include_router(admin.router)


@app.get("/health")
def health():
    return {"ok": True, "service": "ratemy-systems"}


@app.exception_handler(Exception)
async def unhandled(request, exc):
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"ok": False, "detail": "internal error"})


# ---- Static frontend (same-origin) ----
ALLOWED_SUFFIXES = {".html", ".css", ".js", ".svg", ".png", ".ico", ".txt", ".webmanifest"}


def _within(base: Path, candidate: Path) -> bool:
    try:
        return candidate.resolve().is_relative_to(base)   # exact, no prefix-sibling match
    except (ValueError, OSError):
        return False


@app.get("/{path:path}")
async def serve_static(path: str):
    if not path:
        path = "index.html"
    base = STATIC_DIR.resolve()
    target = (base / path).resolve()
    if not _within(base, target):                          # path traversal hard stop
        raise HTTPException(404, "not found")
    if not target.suffix:
        candidates = [target.parent / (target.name + ".html"), target / "index.html", target]
    else:
        candidates = [target]
    for c in candidates:
        if not _within(base, c):
            continue
        if c.is_file() and c.suffix in ALLOWED_SUFFIXES:
            mt = mimetypes.guess_type(str(c))[0] or "application/octet-stream"
            return FileResponse(c, media_type=mt)
    raise HTTPException(404, "not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
