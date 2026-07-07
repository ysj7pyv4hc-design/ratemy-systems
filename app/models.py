"""
Schema per ARCHITECTURE.md §6.
Rule: FACTS are immutable/append-only. DERIVED tables are rebuildable.
Identity separation: rater_identities is the ONLY table linking a person to a pseudonym.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Index,
                        Integer, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def uid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------- IDENTITY (separable) ----------
class Rater(Base):
    __tablename__ = "raters"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    handle: Mapped[str] = mapped_column(String(32), unique=True)       # pseudonym, no PII
    tier: Mapped[str] = mapped_column(String(16), default="verified")  # anonymous|verified|worker|guild_N
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RaterIdentity(Base):
    """ONLY link between a person and a pseudonym. Deletable (identity unlink)."""
    __tablename__ = "rater_identities"
    rater_id: Mapped[str] = mapped_column(String(36), ForeignKey("raters.id"), primary_key=True)
    email_hash: Mapped[str] = mapped_column(String(64), unique=True)   # sha256(lowercase email + pepper)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MagicLink(Base):
    __tablename__ = "magic_links"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email_hash: Mapped[str] = mapped_column(String(64), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)   # sha256 of 256-bit token
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    rater_id: Mapped[str] = mapped_column(String(36), ForeignKey("raters.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Credential(Base):
    __tablename__ = "credentials"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    rater_id: Mapped[str] = mapped_column(String(36), ForeignKey("raters.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))                      # guild_cert | worker_verify
    level: Mapped[int] = mapped_column(Integer, default=1)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------- DIRECTORY ----------
class Company(Base):
    __tablename__ = "companies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(100))
    normalized_name: Mapped[str] = mapped_column(String(100), unique=True)
    industry_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="approved")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Site(Base):
    __tablename__ = "sites"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------- INSTRUMENT / CONFIG ----------
class ConfigVersion(Base):
    __tablename__ = "config_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(16))                      # instrument | scoring | copy
    content: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("kind", "content_hash", name="uq_config_kind_hash"),)


# ---------- FACTS (immutable) ----------
class RatingSession(Base):
    __tablename__ = "rating_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    rater_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("raters.id"), nullable=True)  # NULL = tier 0
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"), index=True)
    site_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sites.id"), nullable=True)
    instrument_version: Mapped[int] = mapped_column(Integer)
    issued_items: Mapped[list] = mapped_column(JSON)                   # item keys issued to this session
    tier_at_submit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    channel: Mapped[str] = mapped_column(String(16), default="organic")  # organic | pulse
    anon_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)  # tier-0 dedupe
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class Response(Base):
    __tablename__ = "responses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("rating_sessions.id"), index=True)
    item_key: Mapped[str] = mapped_column(String(64))
    category_key: Mapped[str] = mapped_column(String(32), index=True)
    value: Mapped[int] = mapped_column(Integer)                        # 1..5, validated at intake


class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("rating_sessions.id"), index=True)
    category_key: Mapped[str] = mapped_column(String(32))
    content_raw: Mapped[str] = mapped_column(Text)
    content_clean: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending|approved|rejected


# ---------- DERIVED (rebuildable) ----------
class ScoreSnapshot(Base):
    __tablename__ = "score_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    scope: Mapped[str] = mapped_column(String(16), index=True)          # global | company
    scope_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    scores: Mapped[dict] = mapped_column(JSON)                          # categories, pillars, strength/gap, context
    index_0_100: Mapped[float | None] = mapped_column(Float, nullable=True)
    n_raters: Mapped[int] = mapped_column(Integer)
    n_eff: Mapped[float] = mapped_column(Float)
    suppressed: Mapped[bool] = mapped_column(Boolean, default=False)    # k-anonymity gate
    scoring_version: Mapped[int] = mapped_column(Integer)
    config_hash: Mapped[str] = mapped_column(String(64))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# ---------- OPERATIONS ----------
class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_type: Mapped[str] = mapped_column(String(16))                 # admin | system | rater | anon
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verb: Mapped[str] = mapped_column(String(48), index=True)
    target: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class RateCounter(Base):
    """DB-backed rate limiting for sensitive actions (survives multi-instance)."""
    __tablename__ = "rate_counters"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    bucket: Mapped[str] = mapped_column(String(128), index=True)        # e.g. magiclink:<email_hash>
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


Index("ix_sessions_company_submitted", RatingSession.company_id, RatingSession.submitted_at)
