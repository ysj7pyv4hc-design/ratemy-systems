"""
Admin surface: moderation queue, config publish, publication job trigger, audit tail.
Token-authed (X-Admin-Token). v1 accepted risk: single strong token instead of
TOTP 2FA (documented in SECURITY.md; TOTP lands with the employer phase).
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config_loader, publication
from .db import get_db
from .models import AuditLog, Comment
from .security import require_admin, require_job

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.get("/moderation")
def moderation_queue(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    rows = db.execute(select(Comment).where(Comment.status == "pending")
                      .order_by(Comment.id).limit(100)).scalars().all()
    return {"ok": True, "pending": [
        {"id": c.id, "category": c.category_key, "content": c.content_raw} for c in rows]}


class ModerateIn(BaseModel):
    comment_id: str
    action: str          # approve | reject
    content_clean: str | None = None


@router.post("/moderation")
def moderate(body: ModerateIn, request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    if body.action not in ("approve", "reject"):
        raise HTTPException(400, "action must be approve|reject")
    c = db.get(Comment, body.comment_id)
    if c is None:
        raise HTTPException(404, "comment not found")
    c.status = "approved" if body.action == "approve" else "rejected"
    if body.action == "approve":
        c.content_clean = (body.content_clean or c.content_raw)[:1000]
    db.add(AuditLog(actor_type="admin", verb=f"comment_{body.action}", target=c.id))
    db.commit()
    return {"ok": True}


@router.post("/config/publish")
def config_publish(request: Request):
    require_admin(request)
    try:
        published = config_loader.publish_if_changed()
    except config_loader.ConfigError as e:
        raise HTTPException(422, f"config rejected, previous version still live: {e}")
    return {"ok": True, "published": published or "no changes"}


@router.post("/jobs/publish")
def jobs_publish(request: Request, db: Session = Depends(get_db)):
    require_job(request)   # EventBridge (JOB_TOKEN) or admin
    result = publication.run_publication(db)
    db.commit()
    return {"ok": True, **result}


@router.get("/audit")
def audit_tail(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    rows = db.execute(select(AuditLog).order_by(AuditLog.at.desc()).limit(200)).scalars().all()
    return {"ok": True, "events": [
        {"at": r.at.isoformat(), "actor": r.actor_type, "verb": r.verb, "target": r.target}
        for r in rows]}
