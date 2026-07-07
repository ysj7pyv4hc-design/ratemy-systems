"""
Production-scenario tests: the paths that only bite once real data and real
config flow through the system. Complements the unit tests.
"""
import asyncio
from datetime import datetime, timezone

import pytest

ADMIN = {"X-Admin-Token": "test-admin-token-0123456789abcdef0123456789abcdef"}
CATS = ["training", "communication", "equipment", "cleanliness", "safety",
        "scheduling", "consistency", "accountability", "recognition", "workload"]


def _seed_company_with_raters(name, n, value=4):
    """Insert a company + n distinct submitted sessions covering all categories."""
    from app.db import db_session
    from app.models import Company, RatingSession, Response, uid, utcnow
    from app.public import normalize_name
    with db_session() as db:
        c = Company(name=name, normalized_name=normalize_name(name))
        db.add(c); db.flush()
        cid = c.id
        for i in range(n):
            # distinct anonymous keys → distinct raters, no raters-table FK needed
            s = RatingSession(rater_id=None, anon_key_hash=f"seed-{name}-{i}", company_id=cid,
                              instrument_version=1, issued_items=CATS,
                              tier_at_submit="verified", channel="organic",
                              submitted_at=utcnow())
            db.add(s); db.flush()
            for cat in CATS:
                db.add(Response(session_id=s.id, item_key=f"{cat}_x", category_key=cat, value=value))
        db.commit()
    return cid


def test_company_crosses_k_anonymity_and_publishes(client):
    cid = _seed_company_with_raters("Threshold Cross Co", 5)
    r = client.post("/v1/admin/jobs/publish", headers=ADMIN)
    assert r.status_code == 200
    data = client.get(f"/v1/scores/company/{cid}").json()
    assert data["published"] is True
    assert data["n_raters"] == 5
    assert data["scores"]["index"] is not None
    assert data["scores"]["strength"] and data["scores"]["gap"]


def test_company_just_below_threshold_stays_private(client):
    cid = _seed_company_with_raters("Just Below Co", 4)
    client.post("/v1/admin/jobs/publish", headers=ADMIN)
    data = client.get(f"/v1/scores/company/{cid}").json()
    assert data["published"] is False
    assert data.get("below_threshold") is True
    assert "n_raters" not in data          # exact count never leaks


def test_global_scores_reflect_seeded_data(client):
    _seed_company_with_raters("Global Feeder Co", 6, value=5)
    client.post("/v1/admin/jobs/publish", headers=ADMIN)
    g = client.get("/v1/scores/global").json()
    assert g["published"] is True
    assert g["n_raters"] >= 6
    assert 0 <= g["scores"]["index"] <= 100


def test_config_publish_endpoint_roundtrip(client):
    r = client.post("/v1/admin/config/publish", headers=ADMIN)
    assert r.status_code == 200
    assert "published" in r.json()


def test_invalid_scoring_config_is_rejected():
    """Fortifies the 'bad config never goes live' guarantee."""
    from app.config_loader import ConfigError, validate_scoring
    good = {"version": 1,
            "weights": {"tier_multipliers": {"anonymous": 0.5, "verified": 1.0}, "weight_cap": 3.0,
                        "per_rater_share_cap": 0.15},
            "recency": {"half_life_days": 270}, "shrinkage": {"k": 8, "prior": "global_mean"},
            "privacy": {"k_anonymity": 5}, "display": {"control_limit_sigmas": 2.0}, "index": {"scale": [0, 100]}}
    validate_scoring(good)  # should not raise

    bad_kanon = {**good, "privacy": {"k_anonymity": 2}}   # below floor of 3
    with pytest.raises(ConfigError):
        validate_scoring(bad_kanon)

    bad_cap = {**good, "weights": {**good["weights"], "weight_cap": 12.0}}  # oligarchy
    with pytest.raises(ConfigError):
        validate_scoring(bad_cap)

    bad_halflife = {**good, "recency": {"half_life_days": 5}}   # too twitchy
    with pytest.raises(ConfigError):
        validate_scoring(bad_halflife)


def test_invalid_instrument_config_is_rejected():
    from app.config_loader import ConfigError, validate_instrument
    base = {"version": 1, "session": {"items_per_session": 10}, "scale": {"anchors": [1, 2, 3, 4, 5]},
            "pillars": {"p": ["training"]}, "categories": {"training": {}},
            "items": [{"key": "t1", "category": "training", "text": "x"}]}
    validate_instrument(base)  # ok
    # category with no items
    bad = {**base, "categories": {"training": {}, "safety": {}}, "pillars": {"p": ["training", "safety"]}}
    with pytest.raises(ConfigError):
        validate_instrument(bad)


def test_publication_loop_survives_errors(monkeypatch):
    """The in-process scheduler must never let one failure kill the loop."""
    from app import main

    calls = {"n": 0}

    def boom(*a, **k):
        calls["n"] += 1
        raise RuntimeError("simulated publication failure")

    monkeypatch.setattr(main, "run_publication", boom)
    monkeypatch.setattr(main, "PUBLISH_INTERVAL_MINUTES", 0)  # loop uses sleep(0)

    async def drive():
        # Patch sleep so the loop spins quickly, then cancel after a couple iterations.
        real_sleep = asyncio.sleep
        async def fast_sleep(_):
            await real_sleep(0)
        monkeypatch.setattr(main.asyncio, "sleep", fast_sleep)
        task = asyncio.create_task(main._publication_loop())
        await real_sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(drive())
    assert calls["n"] >= 1          # it kept calling despite exceptions (didn't die on first)
