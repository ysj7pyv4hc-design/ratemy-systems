"""
Public read API. ZERO-BS contract: real zeroes, suppression stated, n always shown.
A1 enforced here structurally: there is no endpoint that returns companies ordered
by score, and none will be added.
"""
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config_loader, publication
from .db import get_db
from .models import AuditLog, Company
from .security import client_ip, db_rate_check, hash_ip

router = APIRouter(prefix="/v1", tags=["public"])


def normalize_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name.strip().lower())
    return re.sub(r"[^\w\s&.\-]", "", name)


@router.get("/companies")
def list_companies(q: str = "", db: Session = Depends(get_db)):
    qy = select(Company.id, Company.name).order_by(Company.name).limit(50)
    if q.strip():
        safe = q.strip()[:100].replace("%", r"\%").replace("_", r"\_")
        qy = qy.where(Company.name.ilike(f"%{safe}%", escape="\\"))
    rows = db.execute(qy).all()
    return {"ok": True, "companies": [{"id": r.id, "name": r.name} for r in rows]}


class CompanyIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)


@router.post("/companies")
def create_company(body: CompanyIn, request: Request, db: Session = Depends(get_db)):
    db_rate_check(db, f"newco:{hash_ip(client_ip(request))}", max_events=5, window_minutes=1440)
    norm = normalize_name(body.name)
    if len(norm) < 2:
        raise HTTPException(400, "invalid company name")
    existing = db.execute(select(Company).where(Company.normalized_name == norm)).scalar_one_or_none()
    if existing:
        return {"ok": True, "company": {"id": existing.id, "name": existing.name}, "deduped": True}
    c = Company(name=body.name.strip(), normalized_name=norm)
    db.add(c)
    db.flush()
    db.add(AuditLog(actor_type="anon", verb="company_created", target=c.id,
                    ip_hash=hash_ip(client_ip(request))))
    db.commit()
    return {"ok": True, "company": {"id": c.id, "name": c.name}, "deduped": False}


@router.get("/scores/global")
def scores_global(db: Session = Depends(get_db)):
    snap = publication.latest_snapshot(db, "global", None)
    cfg = config_loader.instrument()
    if snap is None:
        return {"ok": True, "published": False}
    return {"ok": True, "published": True, "published_at": snap.published_at.isoformat(),
            "n_raters": snap.n_raters, "scores": snap.scores,
            "category_labels": {k: v["label"] for k, v in cfg["categories"].items()}}


@router.get("/scores/company/{company_id}")
def scores_company(company_id: str, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "company not found")
    snap = publication.latest_snapshot(db, "company", company_id)
    cfg_s = config_loader.scoring()
    base = {"ok": True, "company": {"id": company.id, "name": company.name}}
    if snap is None:
        return {**base, "published": False, "n_raters": 0,
                "message": "no ratings published yet"}
    if snap.suppressed:
        # k-anonymity: below threshold we reveal NOTHING quantitative — not even the
        # exact count. For a small known team, "4 of 5 raters" is a participation signal
        # an employer could use for retaliation timing. Boolean only.
        return {**base, "published": False, "below_threshold": True,
                "k_required": cfg_s["privacy"]["k_anonymity"],
                "message": "not enough ratings to display yet; scores publish at "
                           f"{cfg_s['privacy']['k_anonymity']}+ raters"}
    return {**base, "published": True, "published_at": snap.published_at.isoformat(),
            "n_raters": snap.n_raters, "scores": snap.scores}


@router.get("/methodology")
def methodology():
    """The math, verbatim. Items are the only private part of the instrument."""
    cfg_s, hash_s, ver_s = config_loader.get_active("scoring")
    cfg_i = config_loader.instrument()
    return {
        "ok": True,
        "scoring": cfg_s,
        "scoring_version": ver_s,
        "config_hash": hash_s,
        "instrument_public": {
            "session": cfg_i["session"], "scale": cfg_i["scale"],
            "pillars": cfg_i["pillars"],
            "categories": {k: v for k, v in cfg_i["categories"].items()},
            "item_bank_size": len(cfg_i["items"]),
            "items_note": "item wording is private by design (see FOUNDATIONS.md: "
                          "hide the items, publish the math)",
        },
        "charter": [
            "No ads. No trackers. No selling data.",
            "No paid product affects a public score.",
            "No individual is ever exposed; k-anonymous, batched publication.",
            "No leaderboards; comparison is against expected range, never rank.",
            "North star: verified improvement, not traffic.",
        ],
    }


@router.get("/copy")
def get_copy():
    return {"ok": True, "copy": config_loader.copytext()}


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    snap = publication.latest_snapshot(db, "global", None)
    from sqlalchemy import func
    from .models import RatingSession
    total = db.execute(select(func.count()).select_from(RatingSession)
                       .where(RatingSession.submitted_at.is_not(None))).scalar_one()
    companies = db.execute(select(func.count(func.distinct(RatingSession.company_id)))
                           .where(RatingSession.submitted_at.is_not(None))).scalar_one()
    return {"ok": True, "totalRatings": total, "systemsEvaluated": companies,
            "lastPublished": snap.published_at.isoformat() if snap else None}
