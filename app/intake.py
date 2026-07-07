"""
Session issue + submit. Integrity rules:
- items are issued server-side (coverage-balanced rotation); submits must answer exactly those items
- sessions are single-use, expire, and enforce a minimum human floor (bot resistance)
- tier-0 (anonymous) allowed: weight 0.5, one submission per company per 30d per anon key
- comments land in moderation, never published raw
"""
import hashlib
import random
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config_loader, publication, scoring
from .auth import optional_rater
from .db import get_db
from .models import (AuditLog, Comment, Company, RatingSession, Response,
                     ScoreSnapshot)
from .security import PEPPER, client_ip, db_rate_check, hash_ip

router = APIRouter(prefix="/v1", tags=["intake"])


def _now():
    return datetime.now(timezone.utc)


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _anon_key(request: Request, company_id: str) -> str:
    """Stable-ish anonymous dedupe key: peppered hash of IP+UA+company. Not stored raw."""
    raw = f"{client_ip(request)}|{request.headers.get('user-agent','')[:80]}|{company_id}|{PEPPER}"
    return hashlib.sha256(raw.encode()).hexdigest()


class SessionNewIn(BaseModel):
    company_id: str = Field(min_length=36, max_length=36)


class SubmitIn(BaseModel):
    session_id: str = Field(min_length=36, max_length=36)
    answers: dict[str, int]                 # item_key -> 1..5
    comment: str | None = Field(default=None, max_length=1000)
    comment_category: str | None = Field(default=None, max_length=32)
    website: str | None = None              # honeypot: humans never fill this

    @field_validator("answers")
    @classmethod
    def values_in_range(cls, v):
        if len(v) > 40:                       # bound before we iterate (DoS guard)
            raise ValueError("too many answers")
        for k, val in v.items():
            if not isinstance(val, int) or not (1 <= val <= 5):
                raise ValueError(f"answer {k} must be integer 1..5")
        return v


@router.post("/session/new")
def session_new(body: SessionNewIn, request: Request, db: Session = Depends(get_db)):
    cfg = config_loader.instrument()
    _, _, iver = config_loader.get_active("instrument")

    company = db.get(Company, body.company_id)
    if company is None:
        raise HTTPException(404, "company not found")

    # Coverage-balanced rotation: one random item per category, then top up randomly.
    per_cat: dict[str, list[dict]] = {}
    for item in cfg["items"]:
        per_cat.setdefault(item["category"], []).append(item)
    chosen = [random.choice(items) for items in per_cat.values()]
    n_target = cfg["session"]["items_per_session"]
    if len(chosen) < n_target:
        remaining = [i for i in cfg["items"] if i not in chosen]
        random.shuffle(remaining)
        chosen += remaining[: n_target - len(chosen)]
    random.shuffle(chosen)
    chosen = chosen[:n_target]

    rater = optional_rater(request, db)
    sess = RatingSession(
        rater_id=rater.id if rater else None,
        company_id=company.id,
        instrument_version=iver,
        issued_items=[i["key"] for i in chosen],
        anon_key_hash=None if rater else _anon_key(request, company.id),
    )
    db.add(sess)
    db.commit()
    return {
        "ok": True,
        "session_id": sess.id,
        "anchors": cfg["scale"]["anchors"],
        "items": [{"key": i["key"], "text": i["text"],
                   "category": i["category"],
                   "category_label": cfg["categories"][i["category"]]["label"]} for i in chosen],
        "categories": {k: v["label"] for k, v in cfg["categories"].items()},
    }


@router.post("/submit")
def submit(body: SubmitIn, request: Request, db: Session = Depends(get_db)):
    if body.website:  # honeypot tripped
        raise HTTPException(400, "invalid submission")

    cfg = config_loader.instrument()
    cfg_s = config_loader.scoring()
    sess = db.get(RatingSession, body.session_id)
    if sess is None:
        raise HTTPException(404, "session not found")
    if sess.submitted_at is not None:
        raise HTTPException(409, "session already submitted")
    age = _now() - _aware(sess.issued_at)
    if age > timedelta(hours=cfg["session"]["max_session_age_hours"]):
        raise HTTPException(410, "session expired; start again")
    if age < timedelta(seconds=cfg["session"]["min_seconds_before_submit"]):
        raise HTTPException(400, "that was too fast to be a considered rating")

    issued = set(sess.issued_items)
    if set(body.answers.keys()) != issued:
        raise HTTPException(400, "answers must cover exactly the issued items")

    rater = optional_rater(request, db)
    if rater is not None and sess.rater_id not in (None, rater.id):
        raise HTTPException(403, "session belongs to another account")

    # One rating per company per 30d (per account, or per anon key).
    window = _now() - timedelta(days=30)
    dupe_q = select(RatingSession.id).where(
        RatingSession.company_id == sess.company_id,
        RatingSession.submitted_at.is_not(None),
        RatingSession.submitted_at >= window,
        RatingSession.id != sess.id,
    )
    if rater:
        dupe_q = dupe_q.where(RatingSession.rater_id == rater.id)
    else:
        dupe_q = dupe_q.where(RatingSession.anon_key_hash == sess.anon_key_hash)
    if db.execute(dupe_q.limit(1)).first():
        raise HTTPException(429, "already rated this workplace in the last 30 days")

    # IP-level submit throttle (DB-backed): 5 submits/day/IP.
    db_rate_check(db, f"submit:{hash_ip(client_ip(request))}", max_events=5, window_minutes=1440)

    item_cat = {i["key"]: i["category"] for i in cfg["items"]}
    for key, val in body.answers.items():
        db.add(Response(session_id=sess.id, item_key=key, category_key=item_cat[key], value=val))

    sess.submitted_at = _now()
    sess.tier_at_submit = rater.tier if rater else "anonymous"
    if rater:
        sess.rater_id = rater.id

    if body.comment and body.comment.strip():
        cat = body.comment_category if body.comment_category in cfg["categories"] else ""
        db.add(Comment(session_id=sess.id, category_key=cat, content_raw=body.comment.strip()[:1000]))

    # Deliberately NO company target and NO ip_hash on this event: a per-rating,
    # per-company, timestamped, IP-tagged row is a latent deanonymization store.
    # Abuse throttling is handled by rate_counters (which auto-expire), not the audit log.
    db.add(AuditLog(actor_type="rater" if rater else "anon", verb="rating_submitted"))
    db.commit()  # facts durable BEFORE the comparison is computed or returned

    return {"ok": True, "comparison": _comparison(db, sess, body.answers, item_cat, cfg, cfg_s)}


def _comparison(db, sess, answers, item_cat, cfg, cfg_s) -> dict:
    """Instant post-rating screen (A3): private to the rater, never a public rank."""
    lo, hi = cfg_s["index"]["scale"]
    by_cat: dict[str, list[int]] = {}
    for k, v in answers.items():
        by_cat.setdefault(item_cat[k], []).append(v)
    your_cats = {c: sum(vs) / len(vs) for c, vs in by_cat.items()}
    your_index = round(lo + (sum(your_cats.values()) / len(your_cats) - 1) / 4 * (hi - lo), 1)
    strength = max(your_cats, key=your_cats.get)
    gap = min(your_cats, key=your_cats.get)

    snap = publication.latest_snapshot(db, "global", None)
    ctx = (snap.scores.get("control_context") if snap else None) or {}
    population = publication.live_population_indices(db)
    pct = scoring.percentile_of(your_index, population)

    consensus = None
    if snap and snap.scores["categories"].get(gap) is not None and snap.n_raters >= cfg_s["privacy"]["k_anonymity"]:
        global_gap = min((v, c) for c, v in snap.scores["categories"].items() if v is not None)[1]
        consensus = {"same_gap_as_global": global_gap == gap, "global_gap": global_gap}

    labels = {k: v["label"] for k, v in cfg["categories"].items()}
    return {
        "your_index": your_index,
        "your_categories": {c: round(v, 2) for c, v in your_cats.items()},
        "strength": {"key": strength, "label": labels[strength], "score": round(your_cats[strength], 2)},
        "gap": {"key": gap, "label": labels[gap], "score": round(your_cats[gap], 2)},
        "expected": ctx,
        "percentile_vs_rated": pct,
        "consensus": consensus,
        "global_n": snap.n_raters if snap else 0,
    }
