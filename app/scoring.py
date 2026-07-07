"""
Scoring engine — a pure function of (config, facts). ARCHITECTURE §5 + amendments.
Stages: weights (tier, cap) → recency decay → share cap → item→category→pillar→index
→ shrinkage toward prior → k-anonymity gate → control-chart context (A1)
→ strength/gap pairing (A3) → organic/pulse divergence (A4).
No I/O in compute_*; callers fetch facts and persist snapshots.
"""
import math
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Fact:
    """One response, flattened."""
    rater_key: str          # rater_id or anon session key — share-cap identity
    tier: str
    category: str
    value: int              # 1..5
    submitted_at: datetime
    channel: str            # organic | pulse


def _decay(age_days: float, half_life: float) -> float:
    return 0.5 ** (max(age_days, 0.0) / half_life)


def _weights(facts: list[Fact], cfg: dict, now: datetime) -> dict[str, float]:
    """Per-rater weight (tier × decay of their most recent contribution), share-capped."""
    tiers = cfg["weights"]["tier_multipliers"]
    cap = cfg["weights"]["weight_cap"]
    half = cfg["recency"]["half_life_days"]
    share_cap = cfg["weights"]["per_rater_share_cap"]

    per_rater: dict[str, float] = {}
    for f in facts:
        age = (now - f.submitted_at).total_seconds() / 86400.0
        w = min(tiers.get(f.tier, tiers["anonymous"]), cap) * _decay(age, half)
        per_rater[f.rater_key] = max(per_rater.get(f.rater_key, 0.0), w)

    total = sum(per_rater.values())
    if total > 0 and per_rater:
        # Share cap with a 1/n floor: with n raters nobody can be forced below an
        # equal share, so the effective cap is max(share_cap, 1/n) of total mass.
        effective = max(share_cap, 1.0 / len(per_rater))
        max_share = effective * total
        return {k: min(v, max_share) for k, v in per_rater.items()}
    return per_rater


def compute_scope(facts: list[Fact], cfg_scoring: dict, cfg_instrument: dict,
                  prior: dict[str, float] | None, now: datetime | None = None) -> dict:
    """
    Score one scope (a company, or global when prior is None).
    Returns dict with categories, pillars, index, n, n_eff, suppressed, divergence.
    """
    now = now or datetime.now(timezone.utc)
    pillars_def = cfg_instrument["pillars"]
    categories = list(cfg_instrument["categories"].keys())
    k_anon = cfg_scoring["privacy"]["k_anonymity"]
    shrink_k = cfg_scoring["shrinkage"]["k"]
    lo, hi = cfg_scoring["index"]["scale"]

    raters = {f.rater_key for f in facts}
    n = len(raters)
    rw = _weights(facts, cfg_scoring, now)
    n_eff = sum(rw.values())

    def cat_mean(fs: list[Fact]) -> dict[str, float | None]:
        by_cat: dict[str, list[tuple[float, float]]] = {c: [] for c in categories}
        for f in fs:
            w = rw.get(f.rater_key, 0.0)
            if w > 0:
                by_cat[f.category].append((w, float(f.value)))
        out: dict[str, float | None] = {}
        for c, pairs in by_cat.items():
            tw = sum(w for w, _ in pairs)
            out[c] = (sum(w * v for w, v in pairs) / tw) if tw > 0 else None
        return out

    raw = cat_mean(facts)

    # Shrinkage toward prior (global scope passes prior=None → no shrink; it IS the prior).
    cats: dict[str, float | None] = {}
    for c in categories:
        v = raw[c]
        if v is None:
            cats[c] = None
        elif prior and prior.get(c) is not None and shrink_k > 0:
            cats[c] = (n_eff * v + shrink_k * prior[c]) / (n_eff + shrink_k)
        else:
            cats[c] = v

    pillars: dict[str, float | None] = {}
    for p, pcats in pillars_def.items():
        vals = [cats[c] for c in pcats if cats[c] is not None]
        pillars[p] = sum(vals) / len(vals) if vals else None

    all_vals = [v for v in cats.values() if v is not None]
    overall_1_5 = sum(all_vals) / len(all_vals) if all_vals else None
    index = None if overall_1_5 is None else round(lo + (overall_1_5 - 1.0) / 4.0 * (hi - lo), 1)

    # A3: strength / gap pairing
    present = {c: v for c, v in cats.items() if v is not None}
    strength = max(present, key=present.get) if present else None
    gap = min(present, key=present.get) if present else None

    # A4: organic vs pulse divergence (index-scale), null until pulses exist
    divergence = None
    organic = [f for f in facts if f.channel == "organic"]
    pulse = [f for f in facts if f.channel == "pulse"]
    if organic and pulse:
        def simple_mean(fs):
            vs = [float(f.value) for f in fs]
            return sum(vs) / len(vs)
        divergence = round((simple_mean(pulse) - simple_mean(organic)) / 4.0 * (hi - lo), 1)

    return {
        "categories": {c: (round(v, 2) if v is not None else None) for c, v in cats.items()},
        "pillars": {p: (round(v, 2) if v is not None else None) for p, v in pillars.items()},
        "index": index,
        "n_raters": n,
        "n_eff": round(n_eff, 2),
        "suppressed": n < k_anon,
        "strength": strength,
        "gap": gap,
        "pulse_divergence": divergence,
    }


def control_context(company_indices: list[float], cfg_scoring: dict) -> dict:
    """
    A1: the expected range across rated workplaces — mean ± Nσ of company index scores.
    This replaces rankings. A company is 'signal' only outside the limits.
    """
    sigmas = cfg_scoring["display"]["control_limit_sigmas"]
    if len(company_indices) < 2:
        return {"expected_mean": None, "expected_low": None, "expected_high": None,
                "n_companies": len(company_indices)}
    mean = sum(company_indices) / len(company_indices)
    var = sum((x - mean) ** 2 for x in company_indices) / (len(company_indices) - 1)
    sd = math.sqrt(var)
    return {
        "expected_mean": round(mean, 1),
        "expected_low": round(max(mean - sigmas * sd, 0), 1),
        "expected_high": round(min(mean + sigmas * sd, 100), 1),
        "n_companies": len(company_indices),
    }


def classify_vs_expected(index: float | None, ctx: dict) -> str | None:
    """within_range | above_range | below_range — never a rank."""
    if index is None or ctx.get("expected_low") is None:
        return None
    if index < ctx["expected_low"]:
        return "below_range"
    if index > ctx["expected_high"]:
        return "above_range"
    return "within_range"


def percentile_of(value: float, population: list[float]) -> int | None:
    """For the post-rating comparison screen only (private to the rater, not a public rank)."""
    if not population:
        return None
    below = sum(1 for x in population if x < value)
    return round(100 * below / len(population))
