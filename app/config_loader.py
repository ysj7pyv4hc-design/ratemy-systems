"""
Config layer: YAML files are the source of truth; runtime reads the latest
published ConfigVersion row. On startup, files are validated and auto-published
if their hash changed (edit → redeploy → live). Invalid config NEVER goes live:
publish raises, the previous version keeps serving.
"""
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy import select

from .db import db_session
from .models import ConfigVersion

CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", Path(__file__).resolve().parent.parent / "config"))
KINDS = ("instrument", "scoring", "copy")


class ConfigError(ValueError):
    pass


def _hash(content: dict) -> str:
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def validate_instrument(c: dict) -> None:
    for f in ("version", "session", "scale", "pillars", "categories", "items"):
        if f not in c:
            raise ConfigError(f"instrument.yaml missing '{f}'")
    n = c["session"].get("items_per_session")
    if not isinstance(n, int) or not (3 <= n <= 30):
        raise ConfigError("items_per_session must be 3..30")
    if len(c["scale"]["anchors"]) != 5:
        raise ConfigError("scale.anchors must have exactly 5 anchors (1..5)")
    cats = set(c["categories"].keys())
    pillar_cats = {cat for cats_ in c["pillars"].values() for cat in cats_}
    if cats != pillar_cats:
        raise ConfigError(f"categories/pillars mismatch: {cats ^ pillar_cats}")
    keys = [i["key"] for i in c["items"]]
    if len(keys) != len(set(keys)):
        raise ConfigError("duplicate item keys")
    per_cat: dict[str, int] = {}
    for item in c["items"]:
        if item["category"] not in cats:
            raise ConfigError(f"item {item['key']}: unknown category {item['category']}")
        if not item.get("text", "").strip():
            raise ConfigError(f"item {item['key']}: empty text")
        per_cat[item["category"]] = per_cat.get(item["category"], 0) + 1
    missing = cats - set(per_cat)
    if missing:
        raise ConfigError(f"categories with no items: {missing}")
    if n < len(cats):
        raise ConfigError("items_per_session smaller than category count breaks coverage rotation")


def validate_scoring(c: dict) -> None:
    for f in ("version", "weights", "recency", "shrinkage", "privacy", "display", "index"):
        if f not in c:
            raise ConfigError(f"scoring.yaml missing '{f}'")
    w = c["weights"]
    cap = w.get("weight_cap", 0)
    if not (1.0 <= cap <= 5.0):
        raise ConfigError("weight_cap must be 1..5 (published band, keep it tight)")
    for tier, m in w["tier_multipliers"].items():
        if not (0 < m <= cap):
            raise ConfigError(f"tier multiplier {tier}={m} outside (0, cap]")
    if not (0 < w.get("per_rater_share_cap", 0) <= 1):
        raise ConfigError("per_rater_share_cap must be (0,1]")
    if c["recency"].get("half_life_days", 0) < 30:
        raise ConfigError("half_life_days < 30 makes scores twitchy; refuse")
    if c["privacy"].get("k_anonymity", 0) < 3:
        raise ConfigError("k_anonymity below 3 is not acceptable (raise-only dial)")
    if c["shrinkage"].get("k", -1) < 0:
        raise ConfigError("shrinkage.k must be >= 0")


def validate_copy(c: dict) -> None:
    if "version" not in c:
        raise ConfigError("copy.yaml missing version")


VALIDATORS = {"instrument": validate_instrument, "scoring": validate_scoring, "copy": validate_copy}


def load_file(kind: str) -> dict:
    p = CONFIG_DIR / f"{kind}.yaml"
    with open(p, "r") as f:
        content = yaml.safe_load(f)
    if not isinstance(content, dict):
        raise ConfigError(f"{kind}.yaml is not a mapping")
    return content


def publish_if_changed() -> list[str]:
    """Startup hook: validate files, publish any whose hash changed. Returns published kinds."""
    published = []
    with db_session() as db:
        for kind in KINDS:
            content = load_file(kind)
            VALIDATORS[kind](content)
            h = _hash(content)
            existing = db.execute(
                select(ConfigVersion).where(ConfigVersion.kind == kind, ConfigVersion.content_hash == h)
            ).scalar_one_or_none()
            if existing is None:
                db.add(ConfigVersion(kind=kind, content=content, content_hash=h))
                published.append(kind)
    get_active.cache_clear()
    return published


@lru_cache(maxsize=8)
def get_active(kind: str) -> tuple[dict, str, int]:
    """Latest published config: (content, hash, version). Cached; cleared on publish."""
    with db_session() as db:
        row = db.execute(
            select(ConfigVersion).where(ConfigVersion.kind == kind).order_by(ConfigVersion.published_at.desc())
        ).scalars().first()
        if row is None:
            raise RuntimeError(f"no published config for {kind}; startup publish failed?")
        return row.content, row.content_hash, int(row.content["version"])


def instrument() -> dict:
    return get_active("instrument")[0]


def scoring() -> dict:
    return get_active("scoring")[0]


def copytext() -> dict:
    return get_active("copy")[0]
