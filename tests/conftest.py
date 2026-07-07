import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["RMS_ENV"] = "dev"
os.environ["ADMIN_TOKEN"] = "test-admin-token-0123456789abcdef0123456789abcdef"
os.environ["JOB_TOKEN"] = "test-job-token-0123456789abcdef0123456789abcdef00"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def relax_rate_limits():
    """Tests all share one 'IP'; clear counters between tests so limits don't cross-fire.
    Rate limiting itself is tested explicitly in test_api.py."""
    yield
    from app.db import db_session
    from app.models import RateCounter
    from app import security
    with db_session() as db:
        db.query(RateCounter).delete()
    security.GENERAL_LIMIT.hits.clear()
    security.WRITE_LIMIT.hits.clear()
    security.AUTH_LIMIT.hits.clear()


@pytest.fixture()
def company(client):
    r = client.post("/v1/companies", json={"name": f"TestCo {os.urandom(4).hex()}"})
    assert r.status_code == 200
    return r.json()["company"]


def make_submission(client, company_id, values=None, min_wait_bypass=True):
    """Issue a session and submit it. Returns (status_code, json)."""
    s = client.post("/v1/session/new", json={"company_id": company_id}).json()
    if min_wait_bypass:
        _rewind_session(s["session_id"])
    answers = {}
    for i, item in enumerate(s["items"]):
        v = 3 if values is None else values[i % len(values)]
        answers[item["key"]] = v
    r = client.post("/v1/submit", json={"session_id": s["session_id"], "answers": answers})
    return r.status_code, r.json()


def _rewind_session(session_id, seconds=60):
    """Backdate issued_at so the human-floor check passes in tests."""
    from datetime import datetime, timedelta, timezone
    from app.db import db_session
    from app.models import RatingSession
    with db_session() as db:
        sess = db.get(RatingSession, session_id)
        sess.issued_at = datetime.now(timezone.utc) - timedelta(seconds=seconds)
