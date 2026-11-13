"""Tests for authentication and authorization.

These tests verify:
- JWT token validation
- Expired token handling
- Invalid signature rejection
- Wrong issuer/audience rejection
- Missing token handling
- Cross-user resource access prevention
- Legacy record inaccessibility
"""
import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

# Set up test environment before importing app
os.environ["DATABASE_URL"] = "sqlite:///querypilot_test.db"
os.environ["APP_DATABASE_URL"] = "sqlite:///querypilot_test_app.db"
os.environ["SUPABASE_URL"] = "https://test-project.supabase.co"
os.environ["SUPABASE_JWT_SECRET"] = ""  # Will be set per-test
os.environ["SUPABASE_AUDIENCE"] = "authenticated"


def _generate_rs256_key_pair():
    """Generate RS256 key pair for testing."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    return {
        "private_key": private_pem.decode('utf-8'),
        "public_key": public_pem.decode('utf-8'),
    }


def _generate_test_token(user_id: str = "test-user-123", email: str = "test@example.com",
                         key_pair: dict = None, expires_hours: int = 1) -> str:
    """Generate a test JWT token."""
    from jose import jwt

    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=expires_hours)).timestamp()),
        "aud": "authenticated",
        "iss": "https://test-project.supabase.co/",
    }

    if key_pair:
        return jwt.encode(payload, key_pair["private_key"], algorithm="RS256")
    else:
        return jwt.encode(payload, "test-secret", algorithm="HS256")


class TestTokenVerification:
    """Test token verification logic."""

    @pytest.fixture(autouse=True)
    def setup_test_db(self):
        """Set up test database before each test."""
        from app.seed import seed
        seed(n_users=100)
        yield

    def test_valid_rs256_token_accepted(self, monkeypatch):
        """Test that a valid RS256 token is accepted."""
        key_pair = _generate_rs256_key_pair()
        token = _generate_test_token(user_id="user-valid-123", email="valid@example.com", key_pair=key_pair)

        with patch("app.auth.SUPABASE_JWT_SECRET", key_pair["public_key"]):
            from app.auth import verify_token
            payload = verify_token(token)
            assert payload.sub == "user-valid-123"
            assert payload.email == "valid@example.com"

    def test_expired_token_rejected(self, monkeypatch):
        """Test that an expired token is rejected."""
        key_pair = _generate_rs256_key_pair()
        token = _generate_test_token(user_id="user-expired-123", expires_hours=-1, key_pair=key_pair)

        with patch("app.auth.SUPABASE_JWT_SECRET", key_pair["public_key"]):
            from app.auth import verify_token

            with pytest.raises(Exception) as exc_info:
                verify_token(token)
            error_msg = str(exc_info.value).lower()
            assert any(x in error_msg for x in ["exp", "expired", "signature", "invalid"])

    def test_invalid_signature_rejected(self, monkeypatch):
        """Test that a token with invalid signature is rejected."""
        key_pair_1 = _generate_rs256_key_pair()
        token = _generate_test_token(user_id="user-same-123", key_pair=key_pair_1)

        key_pair_2 = _generate_rs256_key_pair()
        with patch("app.auth.SUPABASE_JWT_SECRET", key_pair_2["public_key"]):
            from app.auth import verify_token

            with pytest.raises(Exception):
                verify_token(token)

    def test_wrong_issuer_rejected(self, monkeypatch):
        """Test that a token with wrong issuer is rejected."""
        token = _generate_test_token(
            user_id="user-wrong-issuer",
            key_pair=_generate_rs256_key_pair(),
            expires_hours=1
        )
        # Patch issuer to be different
        with patch("app.auth.SUPABASE_URL", "https://evil-project.supabase.co"):
            from app.auth import verify_token

            with pytest.raises(Exception):
                verify_token(token)

    def test_wrong_audience_rejected(self, monkeypatch):
        """Test that a token with wrong audience is rejected."""
        token = _generate_test_token(
            user_id="user-wrong-audience",
            key_pair=_generate_rs256_key_pair()
        )

        with patch("app.auth.SUPABASE_URL", "https://test-project.supabase.co"), \
             patch("app.auth.SUPABASE_JWT_SECRET", _generate_rs256_key_pair()["public_key"]):
            # Create token with wrong audience
            from jose import jwt
            now = datetime.now(timezone.utc)
            payload = {
                "sub": "user-wrong-aud",
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(hours=1)).timestamp()),
                "aud": "other-project",
                "iss": "https://test-project.supabase.co/",
            }
            key_pair = _generate_rs256_key_pair()
            token = jwt.encode(payload, key_pair["private_key"], algorithm="RS256")

            with patch("app.auth.SUPABASE_JWT_SECRET", key_pair["public_key"]):
                from app.auth import verify_token

                with pytest.raises(Exception):
                    verify_token(token)


class TestAuthenticationEndpoint:
    """Test authentication on API endpoints."""

    @pytest.fixture(autouse=True)
    def setup_test_db(self):
        """Set up test database before each test."""
        from app.seed import seed
        seed(n_users=100)
        yield

    def test_missing_token_returns_401(self):
        """Test that missing token returns 401 Unauthorized."""
        from app.main import app

        client = TestClient(app)
        response = client.get("/api/investigations", headers={})

        assert response.status_code == 401
        assert "authenticated" in response.json().get("detail", "").lower()

    def test_invalid_token_returns_401(self):
        """Test that invalid token returns 401 Unauthorized."""
        from app.main import app

        client = TestClient(app)
        response = client.get("/api/investigations", headers={
            "Authorization": "Bearer invalid-token-xyz"
        })

        assert response.status_code == 401

    def test_ask_endpoint_requires_auth(self):
        """Test that POST /api/ask requires authentication."""
        from app.main import app

        client = TestClient(app)
        response = client.post("/api/ask", json={"question": "test question"}, headers={})

        assert response.status_code == 401

    def test_health_endpoint_no_auth_required(self):
        """Test that health endpoint requires no authentication."""
        from app.main import app

        client = TestClient(app)
        response = client.get("/api/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestCrossUserAccess:
    """Test that users cannot access other users' resources."""

    @pytest.fixture(autouse=True)
    def setup_test_db(self):
        """Set up test database and create test data."""
        from app.seed import seed
        from app import store

        seed(n_users=100)

        # Create investigations for different users
        # User 1 creates an investigation
        store.save(
            question="User 1's question",
            answer="User 1's answer",
            queries=[{"sql": "SELECT 1", "ok": True, "columns": ["1"], "rows": [[1]]}],
            duration_ms=100,
            findings=[],
            user_id="user-1-id"
        )
        # User 2 creates an investigation
        self.inv_id_2 = store.save(
            question="User 2's question",
            answer="User 2's answer",
            queries=[{"sql": "SELECT 2", "ok": True, "columns": ["2"], "rows": [[2]]}],
            duration_ms=200,
            findings=[],
            user_id="user-2-id"
        )
        yield
        # Cleanup: delete test investigations using the same engine
        from app import store as store_mod
        from sqlalchemy import text
        engine = store_mod._engine()
        with engine.begin() as c:
            c.execute(text("DELETE FROM investigations WHERE user_id IN ('user-1-id', 'user-2-id')"))

    def test_user_cannot_access_other_user_investigation(self):
        """Test that user cannot access another user's investigation."""
        from app.main import app
        from app.dependencies.auth import get_current_user_id

        # Mock the dependency to return user-1-id
        app.dependency_overrides[get_current_user_id] = lambda: "user-1-id"

        client = TestClient(app)
        response = client.get(f"/api/investigations/{self.inv_id_2}")

        # Should get 404 (investigation not found for this user)
        assert response.status_code == 404

        # Clean up override
        app.dependency_overrides.clear()

    def test_user_can_only_see_own_investigations(self):
        """Test that users only see their own investigations."""
        from app.main import app
        from app.dependencies.auth import get_current_user_id
        from app import store
        from app import store as store_mod
        from sqlalchemy import text

        # Use unique user IDs to avoid conflicts
        user_1 = "test-user-can-see-1"
        user_2 = "test-user-can-see-2"

        # User 1 creates 2 investigations
        store.save(question="Q1", answer="A1", queries=[], duration_ms=10, user_id=user_1)
        store.save(question="Q2", answer="A2", queries=[], duration_ms=10, user_id=user_1)

        # User 2 creates 1 investigation
        inv3 = store.save(question="Q3", answer="A3", queries=[], duration_ms=10, user_id=user_2)

        client = TestClient(app)

        # User 1's list should show 2 investigations
        app.dependency_overrides[get_current_user_id] = lambda: user_1
        response = client.get("/api/investigations")
        assert response.status_code == 200
        invs = response.json()
        assert len(invs) == 2

        # User 2's list should show only their 1 investigation
        app.dependency_overrides.clear()
        app.dependency_overrides[get_current_user_id] = lambda: user_2
        response = client.get("/api/investigations")
        assert response.status_code == 200
        invs = response.json()
        assert len(invs) == 1
        assert invs[0]["id"] == inv3

        app.dependency_overrides.clear()

        # Cleanup
        engine = store_mod._engine()
        with engine.begin() as c:
            c.execute(text(f"DELETE FROM investigations WHERE user_id IN ('{user_1}', '{user_2}')"))


class TestLegacyRecordAccess:
    """Test that legacy records without verified ownership are inaccessible."""

    @pytest.fixture(autouse=True)
    def setup_test_db(self):
        """Set up test database with legacy records."""
        from app.seed import seed
        from app import store as store_mod
        from sqlalchemy import text
        seed(n_users=100)
        yield
        # Cleanup
        engine = store_mod._engine()
        with engine.begin() as c:
            c.execute(text("DELETE FROM investigations WHERE user_id = 'legacy-test-user' OR user_id = '__legacy_unassigned__'"))

    def test_legacy_records_not_accessible_to_authenticated_users(self):
        """Test that legacy records (without proper user_id) are not accessible."""
        from app.main import app
        from app.dependencies.auth import get_current_user_id
        from app import store

        # Create a legacy investigation
        legacy_inv_id = store.save(
            question="Legacy question",
            answer="Legacy answer",
            queries=[],
            duration_ms=10,
            user_id="__legacy_unassigned__"
        )

        client = TestClient(app)

        # Authenticated user should not be able to access legacy record
        app.dependency_overrides[get_current_user_id] = lambda: "user-new-123"
        response = client.get(f"/api/investigations/{legacy_inv_id}")

        # Should get 404 - legacy record not accessible to this user
        assert response.status_code == 404

        app.dependency_overrides.clear()

    def test_legacy_investigations_not_in_list(self):
        """Test that legacy investigations don't appear in user lists."""
        from app.main import app
        from app.dependencies.auth import get_current_user_id
        from app import store

        # Create some legacy records
        store.save(question="Legacy 1", answer="A1", queries=[], duration_ms=10)
        store.save(question="Legacy 2", answer="A2", queries=[], duration_ms=10)

        # Create owned records for a unique user
        test_user = "legacy-test-user"
        store.save(question="Owned 1", answer="A1", queries=[], duration_ms=10, user_id=test_user)

        client = TestClient(app)

        # List for user should only show their records
        app.dependency_overrides[get_current_user_id] = lambda: test_user
        response = client.get("/api/investigations")

        # Should only see 1 investigation (their owned one, not legacy)
        assert response.status_code == 200
        invs = response.json()
        assert len(invs) == 1

        app.dependency_overrides.clear()


class TestAuthConfiguration:
    """Test authentication configuration validation."""

    def test_missing_jwt_secret_raises_error(self, monkeypatch):
        """Test that missing JWT secret raises configuration error."""
        from app.auth import verify_token

        with patch("app.auth.SUPABASE_JWT_SECRET", ""):
            with pytest.raises(Exception):
                verify_token("some-token")

    def test_missing_url_raises_error(self, monkeypatch):
        """Test that missing URL raises configuration error."""
        from app.auth import verify_token

        with patch("app.auth.SUPABASE_URL", ""), \
             patch("app.auth.SUPABASE_JWT_SECRET", "some-secret"):
            with pytest.raises(Exception):
                verify_token("some-token")


class TestMeEndpoint:
    """Test the /api/me endpoint."""

    def test_me_returns_user_id(self):
        """Test that /api/me returns the authenticated user's ID."""
        from app.main import app
        from app.dependencies.auth import get_current_user_id

        client = TestClient(app)

        app.dependency_overrides[get_current_user_id] = lambda: "test-user-456"
        response = client.get("/api/me")

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "test-user-456"

        app.dependency_overrides.clear()


class TestInvestigationOwnership:
    """Test investigation ownership functionality."""

    @pytest.fixture(autouse=True)
    def setup_test_db(self):
        """Set up test database."""
        from app.seed import seed
        from app import store

        seed(n_users=50)
        yield

    def test_investigation_saved_with_user_id(self):
        """Test that investigation ownership is stored correctly."""
        from app import store

        inv_id = store.save(
            question="Test question",
            answer="Test answer",
            queries=[],
            duration_ms=10,
            user_id="test-user-owner"
        )

        inv = store.get(inv_id, user_id="test-user-owner")
        assert inv is not None
        assert inv["question"] == "Test question"
        # Note: store.get() doesn't return user_id in the dict for backward compatibility

    def test_cannot_access_other_user_investigation(self):
        """Test cross-user access prevention."""
        from app import store

        inv_id = store.save(
            question="Owner's question",
            answer="Owner's answer",
            queries=[],
            duration_ms=10,
            user_id="owner-user"
        )

        # Owner can access
        inv = store.get(inv_id, user_id="owner-user")
        assert inv is not None

        # Other user cannot access
        inv = store.get(inv_id, user_id="other-user")
        assert inv is None