"""Database engine + session. SQLite for dev, Postgres for prod via DATABASE_URL."""
import os
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:////app/data/ratemy.db")
# Render (and Heroku) hand out postgres:// URLs; SQLAlchemy 2.x needs postgresql://.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


@contextmanager
def db_session():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_db():
    """FastAPI dependency. NO auto-commit: mutating handlers MUST call db.commit()
    before returning, so the write is durable before the client sees a response
    (post-response commits create a double-submit race — found in E2E, kept fixed)."""
    s = SessionLocal()
    try:
        yield s
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()  # implicit rollback of anything uncommitted
