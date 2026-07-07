"""Regression tests for the pre-prod security review findings."""
import importlib


def test_xff_takes_rightmost_trusted_hop(monkeypatch):
    """C1: with 1 trusted hop, client IP is the rightmost XFF entry (proxy-appended),
    NOT the attacker-controlled leftmost."""
    from app import security
    monkeypatch.setattr(security, "TRUSTED_PROXY_HOPS", 1)

    class Req:
        headers = {"x-forwarded-for": "1.2.3.4, 9.9.9.9"}  # 1.2.3.4 is spoofed by client
        class client: host = "10.0.0.1"
    ip = security.client_ip(Req())
    assert ip == "9.9.9.9"                 # the hop App Runner appended, not the spoof


def test_suppressed_company_leaks_no_count(client):
    from tests.conftest import make_submission
    co = client.post("/v1/companies", json={"name": "Leak Check Co"}).json()["company"]
    make_submission(client, co["id"])
    client.post("/v1/admin/jobs/publish",
                headers={"X-Admin-Token": "test-admin-token-0123456789abcdef0123456789abcdef"})
    r = client.get(f"/v1/scores/company/{co['id']}").json()
    assert r["published"] is False
    assert r.get("below_threshold") is True
    assert "n_raters" not in r             # H1: exact count must not leak below k
    assert "scores" not in r


def test_rating_audit_event_has_no_company_or_ip(client):
    """M1: the rating_submitted audit row must not become a deanonymization store."""
    from tests.conftest import make_submission
    co = client.post("/v1/companies", json={"name": "Audit Check Co"}).json()["company"]
    make_submission(client, co["id"])
    events = client.get("/v1/admin/audit",
                        headers={"X-Admin-Token": "test-admin-token-0123456789abcdef0123456789abcdef"}).json()["events"]
    rating_events = [e for e in events if e["verb"] == "rating_submitted"]
    assert rating_events
    assert all(e["target"] is None for e in rating_events)   # no company id


def test_body_size_limit(client):
    big = {"session_id": "x" * 40, "answers": {}, "comment": "a" * 100000}
    r = client.post("/v1/submit", json=big, headers={"content-length": str(70000)})
    assert r.status_code == 413


def test_prod_env_fails_closed(monkeypatch):
    """H2/H3/H4/H5: prod boot refuses on missing secrets / ephemeral DB / console mail."""
    import app.security as sec
    importlib.reload(sec)
    monkeypatch.setattr(sec, "ENV", "prod")
    monkeypatch.setattr(sec, "ADMIN_TOKEN", "")
    monkeypatch.setattr(sec, "JOB_TOKEN", "")
    monkeypatch.delenv("RMS_PEPPER", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("MAIL_PROVIDER", "console")
    import pytest
    with pytest.raises(RuntimeError) as e:
        sec.validate_prod_env()
    msg = str(e.value)
    assert "RMS_PEPPER" in msg and "DATABASE_URL" in msg and "ADMIN_TOKEN" in msg


def test_origin_mismatch_refused(client):
    """M3: a cross-origin POST (forged from another site) is refused."""
    r = client.post("/v1/companies", json={"name": "Origin Co"},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
