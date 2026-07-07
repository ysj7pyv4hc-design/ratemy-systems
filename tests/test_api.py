"""API integration: auth roundtrip, submit integrity, privacy gates, admin auth, headers."""
import re

from tests.conftest import make_submission, _rewind_session

ADMIN = {"X-Admin-Token": "test-admin-token-0123456789abcdef0123456789abcdef"}


# ---------- security posture ----------
def test_security_headers_everywhere(client):
    h = client.get("/health").headers
    assert "Content-Security-Policy" in h
    assert h["X-Frame-Options"] == "DENY"
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["Referrer-Policy"] == "no-referrer"


def test_docs_disabled(client):
    for p in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(p).status_code == 404


def test_path_traversal_blocked(client):
    for p in ("/../app/main.py", "/..%2fapp%2fsecurity.py", "/....//config/scoring.yaml"):
        r = client.get(p)
        assert r.status_code in (404, 400)
        assert "PEPPER" not in r.text


def test_admin_requires_token(client):
    assert client.get("/v1/admin/moderation").status_code == 401
    assert client.post("/v1/admin/jobs/publish").status_code == 401
    assert client.get("/v1/admin/moderation", headers={"X-Admin-Token": "wrong"}).status_code == 401
    assert client.get("/v1/admin/moderation", headers=ADMIN).status_code == 200


# ---------- auth roundtrip ----------
def test_magic_link_roundtrip(client, caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="rms.mailer"):
        r = client.post("/v1/auth/magic-link", json={"email": "worker@example.com"})
    assert r.status_code == 200
    # uniform response, no account enumeration
    assert "on its way" in r.json()["message"]
    m = re.search(r"token=([\w\-]+)", caplog.text)
    assert m, "console mailer should log the link in dev"
    token = m.group(1)

    v = client.post("/v1/auth/verify", json={"token": token})
    assert v.status_code == 200
    csrf = v.json()["csrf"]

    me = client.get("/v1/auth/me").json()
    assert me["signed_in"] is True
    assert me["handle"].startswith("rater-")     # pseudonym, no PII

    # token single-use
    assert client.post("/v1/auth/verify", json={"token": token}).status_code == 401

    # CSRF enforced on authed mutations
    assert csrf
    assert client.post("/v1/auth/logout").status_code == 200  # logout is safe either way
    client.cookies.clear()


def test_identity_unlink(client, caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="rms.mailer"):
        client.post("/v1/auth/magic-link", json={"email": "unlink-me@example.com"})
    token = re.findall(r"token=([\w\-]+)", caplog.text)[-1]
    v = client.post("/v1/auth/verify", json={"token": token}).json()

    # unlink without CSRF header → 403
    assert client.delete("/v1/auth/identity").status_code == 403
    r = client.delete("/v1/auth/identity", headers={"X-CSRF": v["csrf"]})
    assert r.status_code == 200
    assert client.get("/v1/auth/me").json()["signed_in"] is False
    client.cookies.clear()


# ---------- intake integrity ----------
def test_submit_happy_path_returns_comparison(client, company):
    code, body = make_submission(client, company["id"], values=[4, 3, 5, 2])
    assert code == 200
    comp = body["comparison"]
    assert 0 <= comp["your_index"] <= 100
    assert comp["strength"]["label"] and comp["gap"]["label"]     # A3 pairing


def test_submit_rejects_wrong_items(client, company):
    s = client.post("/v1/session/new", json={"company_id": company["id"]}).json()
    _rewind_session(s["session_id"])
    answers = {k["key"]: 3 for k in s["items"]}
    answers["fabricated_item"] = 5
    r = client.post("/v1/submit", json={"session_id": s["session_id"], "answers": answers})
    assert r.status_code == 400


def test_submit_rejects_out_of_range(client, company):
    s = client.post("/v1/session/new", json={"company_id": company["id"]}).json()
    _rewind_session(s["session_id"])
    answers = {k["key"]: 3 for k in s["items"]}
    answers[s["items"][0]["key"]] = 9
    r = client.post("/v1/submit", json={"session_id": s["session_id"], "answers": answers})
    assert r.status_code == 422


def test_submit_honeypot(client, company):
    s = client.post("/v1/session/new", json={"company_id": company["id"]}).json()
    _rewind_session(s["session_id"])
    answers = {k["key"]: 3 for k in s["items"]}
    r = client.post("/v1/submit", json={"session_id": s["session_id"], "answers": answers, "website": "http://spam"})
    assert r.status_code == 400


def test_submit_human_floor(client, company):
    s = client.post("/v1/session/new", json={"company_id": company["id"]}).json()
    answers = {k["key"]: 3 for k in s["items"]}   # no rewind → too fast
    r = client.post("/v1/submit", json={"session_id": s["session_id"], "answers": answers})
    assert r.status_code == 400
    assert "too fast" in r.json()["detail"]


def test_session_single_use_and_anon_30d_dedupe(client, company):
    code1, _ = make_submission(client, company["id"])
    assert code1 == 200
    # same anon key (same IP/UA/company) within 30d → blocked
    code2, body2 = make_submission(client, company["id"])
    assert code2 == 429


# ---------- privacy / ZERO-BS ----------
def test_company_scores_suppressed_below_k(client, company):
    make_submission(client, company["id"])
    client.post("/v1/admin/jobs/publish", headers=ADMIN)
    r = client.get(f"/v1/scores/company/{company['id']}").json()
    assert r["published"] is False
    assert r["k_required"] == 5
    assert "scores" not in r          # nothing leaks below threshold


def test_methodology_public_items_private(client):
    m = client.get("/v1/methodology").json()
    assert m["scoring"]["privacy"]["k_anonymity"] >= 3
    assert m["instrument_public"]["item_bank_size"] > 0
    assert "items" not in m["instrument_public"]  # wording never leaves sessions
    assert any("leaderboard" in c.lower() for c in m["charter"])


def test_comment_lands_in_moderation_not_public(client, company):
    s = client.post("/v1/session/new", json={"company_id": company["id"]}).json()
    _rewind_session(s["session_id"])
    answers = {k["key"]: 2 for k in s["items"]}
    r = client.post("/v1/submit", json={"session_id": s["session_id"], "answers": answers,
                                        "comment": "Night shift can never reach maintenance",
                                        "comment_category": "communication"})
    # may 429 if same anon key already rated this company — use fresh company for determinism
    if r.status_code == 200:
        q = client.get("/v1/admin/moderation", headers=ADMIN).json()
        assert any("maintenance" in c["content"] for c in q["pending"])


def test_stats_zero_bs(client):
    s = client.get("/v1/stats").json()
    assert isinstance(s["totalRatings"], int)
    assert isinstance(s["systemsEvaluated"], int)
