"""Membership: provider discovery, login gate, OAuth flow."""
import os

import pytest


def test_providers_endpoint_shape(client):
    p = client.get("/v1/auth/providers").json()
    assert p["ok"] is True
    assert "oauth" in p and isinstance(p["oauth"], list)
    assert "email" in p and "require_login" in p


def test_require_login_blocks_anonymous_submit(client, company, monkeypatch):
    from tests.conftest import _rewind_session
    monkeypatch.setenv("REQUIRE_LOGIN", "true")
    s = client.post("/v1/session/new", json={"company_id": company["id"]}).json()
    _rewind_session(s["session_id"])
    answers = {i["key"]: 3 for i in s["items"]}
    r = client.post("/v1/submit", json={"session_id": s["session_id"], "answers": answers})
    assert r.status_code == 401
    assert "sign in" in r.json()["detail"].lower()


def test_oauth_disabled_provider_404(client):
    assert client.get("/v1/auth/oauth/google/login").status_code == 404


def test_oauth_login_redirects_when_enabled(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
    r = client.get("/v1/auth/oauth/google/login", follow_redirects=False)
    assert r.status_code == 307
    loc = r.headers["location"]
    assert loc.startswith("https://accounts.google.com/o/oauth2/v2/auth")
    assert "state=" in loc and "client_id=test-client" in loc
    # providers now lists google
    assert "google" in client.get("/v1/auth/providers").json()["oauth"]


def test_oauth_callback_creates_member(client, monkeypatch):
    monkeypatch.setenv("GITHUB_CLIENT_ID", "gh-id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "gh-secret")
    # stub the provider network calls
    from app import oauth
    monkeypatch.setattr(oauth, "_http_post_form", lambda url, data, headers: {"access_token": "tok"})
    monkeypatch.setattr(oauth, "_read_subject", lambda provider, token, tr: "gh-user-42")

    # start login to mint a valid state
    r = client.get("/v1/auth/oauth/github/login", follow_redirects=False)
    import urllib.parse as up
    state = up.parse_qs(up.urlparse(r.headers["location"]).query)["state"][0]

    cb = client.get(f"/v1/auth/oauth/github/callback?code=abc&state={state}", follow_redirects=False)
    assert cb.status_code == 307
    assert cb.headers["location"] == "/rate"
    me = client.get("/v1/auth/me").json()
    assert me["signed_in"] is True
    assert me["handle"].startswith("rater-")
    client.cookies.clear()


def test_oauth_callback_bad_state_rejected(client, monkeypatch):
    monkeypatch.setenv("GITHUB_CLIENT_ID", "gh-id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "gh-secret")
    r = client.get("/v1/auth/oauth/github/callback?code=abc&state=not-a-real-state",
                   follow_redirects=False)
    assert r.status_code == 400
