"""Tests for the browser authentication flow (CORS + cookies + CSRF).

These tests reproduce the SPA-at-localhost:3000 talking to the API at
localhost:8000: cross-origin requests carrying session cookies and the
X-CSRF-Token header. They verify:
- Credentialed CORS preflight passes and echoes the specific origin
- CORS response headers allow cookies (Access-Control-Allow-Credentials)
- Register -> authenticated /api/me round-trip with cookies only
- Login -> CSRF-protected /api/ask flow (cookie + header must match)
- Logout clears the session server-side
- Unauthenticated /api/me stays 401 (user isolation intact)
"""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as DBSession

os.environ.setdefault("SECURE_COOKIES", "false")

from app.main import app
from app.models.base import Base
from app.dependencies.auth import get_db
from app.routers.auth import LOGIN_ATTEMPTS, REGISTER_ATTEMPTS

FRONTEND_ORIGIN = "http://localhost:3000"


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database for each test."""
    engine = create_engine(
        f"sqlite:///{tempfile.mkdtemp()}/browser_flow.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = DBSession(engine)
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(db_session):
    """Test client with overridden database and cleaned rate limiters."""
    LOGIN_ATTEMPTS.clear()
    REGISTER_ATTEMPTS.clear()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


class TestCORSForBrowserFlow:
    """Verify CORS allows the credentialed cross-origin browser flow."""

    def test_preflight_allows_frontend_origin(self, client):
        """Preflight from the frontend origin must succeed with explicit origin echo."""
        response = client.options(
            "/api/ask",
            headers={
                "Origin": FRONTEND_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,x-csrf-token",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == FRONTEND_ORIGIN

    def test_preflight_allows_csrf_header(self, client):
        """The X-CSRF-Token header must be permitted in preflight (wildcard is
        ignored by browsers for credentialed requests)."""
        response = client.options(
            "/api/ask",
            headers={
                "Origin": FRONTEND_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,x-csrf-token",
            },
        )
        allow_headers = response.headers.get("access-control-allow-headers", "")
        assert "x-csrf-token" in allow_headers.lower()

    def test_cors_allows_credentials(self, client):
        """Credentialed requests require Access-Control-Allow-Credentials: true."""
        response = client.options(
            "/api/investigations",
            headers={
                "Origin": FRONTEND_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_preflight_rejects_unknown_origin(self, client):
        """Requests from origins not on the allowlist must not be granted access."""
        response = client.options(
            "/api/ask",
            headers={
                "Origin": "http://evil-site.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert response.headers.get("access-control-allow-origin") != "http://evil-site.example"


class TestRegisterToAuthenticatedFlow:
    """Register then call an authenticated endpoint using only cookies."""

    def test_register_then_me_roundtrip(self, client):
        """A browser that registers should be immediately authenticated."""
        response = client.post(
            "/auth/register",
            json={"email": "browser@example.com", "password": "supersecret123"},
            headers={"Origin": FRONTEND_ORIGIN},
        )
        assert response.status_code == 201
        # Session cookies must be set by the response
        assert "session_id" in client.cookies
        assert "csrf_token" in client.cookies

        # Same client (cookie jar) should now be authenticated
        me = client.get("/api/me", headers={"Origin": FRONTEND_ORIGIN})
        assert me.status_code == 200
        assert me.json()["user_id"]

    def test_unauthenticated_me_is_401(self, client):
        """Without cookies, /api/me must remain 401 (user isolation intact)."""
        response = client.get("/api/me")
        assert response.status_code == 401


class TestLoginWithCSRFFlow:
    """Login then call the CSRF-protected /api/ask endpoint."""

    def test_login_sets_session_and_csrf_cookies(self, client):
        """Login must set both session_id and csrf_token cookies."""
        # Register first
        client.post(
            "/auth/register",
            json={"email": "csrfuser@example.com", "password": "supersecret123"},
        )
        # Logout to clear, then login again
        client.post("/auth/logout")
        response = client.post(
            "/auth/login",
            json={"email": "csrfuser@example.com", "password": "supersecret123"},
        )
        assert response.status_code == 200
        assert "session_id" in client.cookies
        assert "csrf_token" in client.cookies

    def test_csrf_token_endpoint_returns_token(self, client):
        """/auth/csrf-token returns the token for SPA initialization."""
        client.post(
            "/auth/register",
            json={"email": "csrftok@example.com", "password": "supersecret123"},
        )
        response = client.get("/auth/csrf-token")
        assert response.status_code == 200
        token = response.json()["csrf_token"]
        assert token == client.cookies.get("csrf_token")

    def test_wrong_csrf_token_rejected_403(self, client):
        """A state-changing request with a mismatched CSRF header must 403."""
        client.post(
            "/auth/register",
            json={"email": "csrffail@example.com", "password": "supersecret123"},
        )
        response = client.post(
            "/api/ask",
            json={"question": "What is the total revenue?"},
            headers={"X-CSRF-Token": "wrong-token"},
        )
        assert response.status_code == 403
        assert "CSRF" in response.json()["detail"]


class TestLogoutFlow:
    """Logout ends the session server-side."""

    def test_logout_invalidates_session(self, client):
        """After logout, the old session cookie must no longer authenticate."""
        client.post(
            "/auth/register",
            json={"email": "logout@example.com", "password": "supersecret123"},
        )
        assert "session_id" in client.cookies
        stale_session = client.cookies.get("session_id")

        response = client.post("/auth/logout")
        assert response.status_code == 200

        # Replaying the stale cookie must fail (session deleted server-side)
        replay = TestClient(app, raise_server_exceptions=False)
        replay.cookies.set("session_id", stale_session)
        me = replay.get("/api/me")
        assert me.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
