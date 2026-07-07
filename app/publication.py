"""
Publication job: fetch facts → scoring.compute_scope per scope → persist ScoreSnapshots.
Runs weekly (EventBridge → /v1/admin/jobs/publish) and once at startup if empty.
Public reads only ever touch the latest snapshots (heavy math at publish, cheap reads).
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config_loader, scoring
from .models import AuditLog, Company, RatingSession, Response, ScoreSnapshot

log = logging.getLogger("rms.publication")


def _facts(db: Session) -> dict[str, list[scoring.Fact]]:
    """All submitted responses, grouped by company."""
    rows = db.execute(
        select(Response.category_key, Response.value, RatingSession.company_id,
               RatingSession.rater_id, RatingSession.anon_key_hash,
               RatingSession.tier_at_submit, RatingSession.channel,
               RatingSession.submitted_at, RatingSession.id)
        .join(RatingSession, RatingSession.id == Response.session_id)
        .where(RatingSession.submitted_at.is_not(None))
    ).all()
    by_company: dict[str, list[scoring.Fact]] = {}
    for cat, val, company_id, rater_id, anon_key, tier, channel, submitted_at, sess_id in rows:
        sub = submitted_at if submitted_at.tzinfo else submitted_at.replace(tzinfo=timezone.utc)
        fact = scoring.Fact(
            rater_key=rater_id or anon_key or f"s:{sess_id}",
            tier=tier or "anonymous",
            category=cat, value=val, submitted_at=sub, channel=channel or "organic",
        )
        by_company.setdefault(company_id, []).append(fact)
    return by_company


def run_publication(db: Session, force: bool = False) -> dict:
    cfg_s, hash_s, ver_s = config_loader.get_active("scoring")
    cfg_i, _, _ = config_loader.get_active("instrument")
    now = datetime.now(timezone.utc)

    by_company = _facts(db)
    all_facts = [f for fs in by_company.values() for f in fs]

    # Global first — it is the shrinkage prior.
    global_scores = scoring.compute_scope(all_facts, cfg_s, cfg_i, prior=None, now=now)
    prior = {c: v for c, v in global_scores["categories"].items() if v is not None}

    company_snapshots = []
    indices = []
    for company_id, facts in by_company.items():
        s = scoring.compute_scope(facts, cfg_s, cfg_i, prior=prior or None, now=now)
        company_snapshots.append((company_id, s))
        if not s["suppressed"] and s["index"] is not None:
            indices.append(s["index"])

    ctx = scoring.control_context(indices, cfg_s)
    global_scores["control_context"] = ctx

    db.add(ScoreSnapshot(scope="global", scope_id=None, scores=global_scores,
                         index_0_100=global_scores["index"], n_raters=global_scores["n_raters"],
                         n_eff=global_scores["n_eff"], suppressed=False,
                         scoring_version=ver_s, config_hash=hash_s))
    for company_id, s in company_snapshots:
        s["vs_expected"] = scoring.classify_vs_expected(s["index"] if not s["suppressed"] else None, ctx)
        db.add(ScoreSnapshot(scope="company", scope_id=company_id, scores=s,
                             index_0_100=s["index"], n_raters=s["n_raters"], n_eff=s["n_eff"],
                             suppressed=s["suppressed"], scoring_version=ver_s, config_hash=hash_s))

    db.add(AuditLog(actor_type="system", verb="publication_run",
                    target=f"companies={len(company_snapshots)} raters_global={global_scores['n_raters']}"))
    log.info("publication: %d companies, global n=%d", len(company_snapshots), global_scores["n_raters"])
    return {"companies": len(company_snapshots), "global_n": global_scores["n_raters"]}


def latest_snapshot(db: Session, scope: str, scope_id: str | None) -> ScoreSnapshot | None:
    q = select(ScoreSnapshot).where(ScoreSnapshot.scope == scope)
    q = q.where(ScoreSnapshot.scope_id == scope_id) if scope_id else q.where(ScoreSnapshot.scope_id.is_(None))
    return db.execute(q.order_by(ScoreSnapshot.published_at.desc())).scalars().first()


def ensure_initial_snapshot(db: Session) -> None:
    if latest_snapshot(db, "global", None) is None:
        run_publication(db)


def live_population_indices(db: Session) -> list[float]:
    """Latest snapshot index per company (for the private post-rating percentile)."""
    rows = db.execute(
        select(ScoreSnapshot.scope_id, ScoreSnapshot.index_0_100, ScoreSnapshot.published_at)
        .where(ScoreSnapshot.scope == "company", ScoreSnapshot.suppressed.is_(False))
        .order_by(ScoreSnapshot.published_at.desc())
    ).all()
    seen: dict[str, float] = {}
    for scope_id, idx, _ in rows:
        if scope_id not in seen and idx is not None:
            seen[scope_id] = idx
    companies_total = db.execute(select(Company.id)).all()
    _ = companies_total  # population = rated companies only, by design
    return list(seen.values())
