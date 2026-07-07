"""Golden tests for the scoring engine — hand-computed expectations."""
from datetime import datetime, timedelta, timezone

from app.scoring import (Fact, classify_vs_expected, compute_scope,
                         control_context, percentile_of)

NOW = datetime(2026, 7, 1, tzinfo=timezone.utc)

CFG_S = {
    "weights": {"tier_multipliers": {"anonymous": 0.5, "verified": 1.0, "guild_3": 3.0},
                "weight_cap": 3.0, "per_rater_share_cap": 0.5},
    "recency": {"half_life_days": 270},
    "shrinkage": {"k": 8, "prior": "global_mean"},
    "privacy": {"k_anonymity": 5, "publication_cadence": "weekly", "publication_jitter_hours": 24},
    "display": {"control_limit_sigmas": 2.0, "no_leaderboards": True},
    "index": {"scale": [0, 100]},
}
CFG_I = {
    "pillars": {"p1": ["training", "safety"], "p2": ["workload"]},
    "categories": {"training": {}, "safety": {}, "workload": {}},
}


def facts(*tuples):
    return [Fact(rater_key=r, tier=t, category=c, value=v, submitted_at=NOW - timedelta(days=age), channel=ch)
            for (r, t, c, v, age, ch) in tuples]


def test_simple_mean_no_prior():
    fs = facts(("r1", "verified", "training", 4, 0, "organic"),
               ("r2", "verified", "training", 2, 0, "organic"))
    out = compute_scope(fs, CFG_S, CFG_I, prior=None, now=NOW)
    assert out["categories"]["training"] == 3.0
    assert out["categories"]["safety"] is None
    assert out["suppressed"] is True          # 2 raters < k=5
    assert out["n_raters"] == 2


CFG_NOCAP = {**CFG_S, "weights": {**CFG_S["weights"], "per_rater_share_cap": 1.0}}


def test_tier_weighting():
    # guild_3 (w=3) says 5, anonymous (w=0.5) says 1 → (3*5 + 0.5*1)/3.5 = 4.43
    fs = facts(("g", "guild_3", "training", 5, 0, "organic"),
               ("a", "anonymous", "training", 1, 0, "organic"))
    out = compute_scope(fs, CFG_NOCAP, CFG_I, prior=None, now=NOW)
    assert out["categories"]["training"] == round((3 * 5 + 0.5 * 1) / 3.5, 2)


def test_recency_decay_half_life():
    # r_old rated 5 exactly one half-life ago (w=0.5), r_new rated 1 today (w=1.0)
    fs = facts(("old", "verified", "training", 5, 270, "organic"),
               ("new", "verified", "training", 1, 0, "organic"))
    out = compute_scope(fs, CFG_NOCAP, CFG_I, prior=None, now=NOW)
    expected = (0.5 * 5 + 1.0 * 1) / 1.5
    assert out["categories"]["training"] == round(expected, 2)


def test_share_cap():
    # One guild_3 whale (w=3) vs one verified (w=1): share cap 0.5 caps whale at 2.0
    fs = facts(("whale", "guild_3", "training", 5, 0, "organic"),
               ("v", "verified", "training", 1, 0, "organic"))
    out = compute_scope(fs, CFG_S, CFG_I, prior=None, now=NOW)
    expected = (2.0 * 5 + 1.0 * 1) / 3.0     # whale capped to 0.5 * total(4.0) = 2.0
    assert out["categories"]["training"] == round(expected, 2)


def test_shrinkage_pulls_small_samples_toward_prior():
    fs = facts(("r1", "verified", "training", 5, 0, "organic"))
    prior = {"training": 3.0, "safety": 3.0, "workload": 3.0}
    out = compute_scope(fs, CFG_S, CFG_I, prior=prior, now=NOW)
    expected = (1.0 * 5 + 8 * 3.0) / (1.0 + 8)   # heavy pull at n_eff=1
    assert out["categories"]["training"] == round(expected, 2)
    assert out["categories"]["training"] < 3.5    # two 5-star reviews can't fake a 5.0


def test_k_anonymity_gate():
    fs = facts(*[(f"r{i}", "verified", "training", 4, 0, "organic") for i in range(5)])
    out = compute_scope(fs, CFG_S, CFG_I, prior=None, now=NOW)
    assert out["suppressed"] is False
    out4 = compute_scope(fs[:4], CFG_S, CFG_I, prior=None, now=NOW)
    assert out4["suppressed"] is True


def test_strength_gap_pairing_A3():
    fs = facts(("r1", "verified", "training", 5, 0, "organic"),
               ("r1", "verified", "safety", 2, 0, "organic"),
               ("r1", "verified", "workload", 3, 0, "organic"))
    out = compute_scope(fs, CFG_S, CFG_I, prior=None, now=NOW)
    assert out["strength"] == "training"
    assert out["gap"] == "safety"


def test_pulse_divergence_A4():
    fs = facts(("o1", "verified", "training", 2, 0, "organic"),
               ("p1", "verified", "training", 4, 0, "pulse"))
    out = compute_scope(fs, CFG_S, CFG_I, prior=None, now=NOW)
    # (4-2)/4 * 100 = +50 index points of suspicious cheer
    assert out["pulse_divergence"] == 50.0


def test_index_scale():
    fs = facts(*[(f"r{i}", "verified", c, 5, 0, "organic")
                 for i in range(5) for c in ("training", "safety", "workload")])
    out = compute_scope(fs, CFG_S, CFG_I, prior=None, now=NOW)
    assert out["index"] == 100.0


def test_control_context_and_classification_A1():
    ctx = control_context([50.0, 52.0, 48.0, 51.0, 49.0], CFG_S)
    assert ctx["expected_mean"] == 50.0
    assert classify_vs_expected(50.0, ctx) == "within_range"
    assert classify_vs_expected(20.0, ctx) == "below_range"
    assert classify_vs_expected(90.0, ctx) == "above_range"


def test_percentile():
    assert percentile_of(75.0, [50.0, 60.0, 70.0, 80.0]) == 75
    assert percentile_of(10.0, []) is None
