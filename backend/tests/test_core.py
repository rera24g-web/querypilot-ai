import pytest
from fastapi.testclient import TestClient
from app.seed import seed
from app.db import run_readonly
from app.safety import validate, UnsafeSQL
from app.main import app

T = {"users", "events", "orders", "subscriptions"}
v = lambda s: validate(s, T, "sqlite", 200)


@pytest.fixture(scope="module", autouse=True)
def data():
    seed(n_users=800)


def test_select_allowed_and_limited():
    assert v("SELECT * FROM users").endswith("LIMIT 200")


def test_cte_and_union_allowed():
    v("WITH a AS (SELECT user_id FROM users) SELECT * FROM a")
    v("SELECT user_id FROM users UNION SELECT user_id FROM orders")


@pytest.mark.parametrize("sql", [
    "DROP TABLE users", "DELETE FROM users", "UPDATE users SET country='X'",
    "INSERT INTO users VALUES (1,'2026-01-01','IN','organic')",
    "SELECT 1; DROP TABLE users", "SELECT * FROM secret_table",
    "SELECT pg_sleep(100)", "SELECT * INTO newt FROM users", "PRAGMA table_info(users)", "",
])
def test_unsafe_blocked(sql):
    with pytest.raises(UnsafeSQL):
        v(sql)


def test_real_query_runs():
    r = run_readonly("SELECT acquisition_channel, COUNT(*) AS n FROM users GROUP BY 1")
    assert r["row_count"] == 5


def test_writes_fail_even_if_guard_bypassed():
    from app.db import get_engine
    with pytest.raises(Exception):
        with get_engine().connect() as c:
            c.exec_driver_sql("DELETE FROM users")


def test_api():
    c = TestClient(app)
    assert c.get("/api/health").json() == {"status": "ok"}
    assert "users(" in c.get("/api/schema").json()["schema"]
    # /api/ask now requires authentication - expect 401 for missing token
    assert c.post("/api/ask", json={"question": "x"}).status_code == 401


def test_list_investigations_requires_auth():
    """Test that /api/investigations requires authentication."""
    c = TestClient(app)
    response = c.get("/api/investigations")
    assert response.status_code == 401


def test_benchmark_gold_queries_are_valid():
    import json, os
    cases = json.load(open(os.path.join(os.path.dirname(__file__), "..", "..", "evaluations", "cases.json")))
    assert len(cases) >= 10
    for c in cases:
        assert run_readonly(c["gold"])["row_count"] >= 1, c["q"]


def test_history_and_export(monkeypatch):
    import app.agent as agent
    fake = {"question": "Why did retention drop?", "answer": "**Summary** test answer",
            "queries": [{"purpose": "count users", "sql": "SELECT COUNT(*) AS n FROM users", "ok": True,
                         "columns": ["n"], "rows": [[800]]}]}
    monkeypatch.setattr(agent, "investigate", lambda q: dict(fake, question=q))

    # Mock authentication using FastAPI dependency override
    from app.dependencies.auth import get_current_user_id
    app.dependency_overrides[get_current_user_id] = lambda: "test-user-123"

    c = TestClient(app)
    r = c.post("/api/ask", json={"question": "Why did retention drop?"}).json()
    assert r["id"] and r["duration_ms"] >= 0
    invs = c.get("/api/investigations").json()
    assert any(i["id"] == r["id"] for i in invs)
    assert c.get(f"/api/investigations/{r['id']}").json()["answer"].startswith("**Summary**")
    md = c.get(f"/api/investigations/{r['id']}/export")
    # Check that the SQL appears in the markdown report (use substring that works)
    assert "COUNT" in md.text and "users" in md.text and "Why did retention drop?" in md.text
    assert "attachment" in md.headers["content-disposition"]
    assert c.get("/api/investigations/nope").status_code == 404

    # Clean up
    app.dependency_overrides.clear()
