"""
Rate My Systems — app factory.
Same-origin by design: static frontend + API on one origin, so NO CORS middleware
exists (its absence is the policy). Security headers on everything.
"""
import logging
import mimetypes
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from . import admin, auth, config_loader, intake, public
from .db import Base, db_session, engine
from .publication import ensure_initial_snapshot
from .security import (RateLimitMiddleware, SecurityHeadersMiddleware,
                       validate_prod_env)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("rms")

STATIC_DIR = Path(os.environ.get("STATIC_DIR", Path(__file__).resolve().parent.parent / "public"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_prod_env()   # fail closed: a misconfigured privacy system must not boot
    Base.metadata.create_all(engine)
    published = config_loader.publish_if_changed()   # invalid config raises → deploy fails loudly, old version keeps running
    if published:
        log.info("config published: %s", published)
    with db_session() as db:
        ensure_initial_snapshot(db)
    yield


app = FastAPI(title="Rate My Systems", docs_url=None, redoc_url=None, openapi_url=None,
              lifespan=lifespan)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)

app.include_router(auth.router)
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
