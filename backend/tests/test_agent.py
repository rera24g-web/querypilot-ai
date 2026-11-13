import json
from types import SimpleNamespace as NS
import pytest
from app.agent import Limits, investigate
from app.seed import seed
from app.verify import verify_findings, unmatched_numbers


@pytest.fixture(scope="module", autouse=True)
def data():
    seed(n_users=800)


def call(sql, purpose="p", cid="c1"):
    return NS(choices=[NS(message=NS(content=None, tool_calls=[NS(id=cid, function=NS(arguments=json.dumps({"sql": sql, "purpose": purpose})))]))], usage=NS(total_tokens=100))


def final(text):
    return NS(choices=[NS(message=NS(content=text, tool_calls=None))], usage=NS(total_tokens=100))


class Fake:
    """Scripted stand-in for the OpenAI client: returns queued responses in order."""
    def __init__(self, *responses):
        self.queue = list(responses)
        self.chat = NS(completions=NS(create=lambda **kw: self.queue.pop(0)))


def test_full_loop_with_findings_verification():
    findings = {"findings": [
        {"claim": "The dataset has 800 users.", "type": "fact", "supporting_query_ids": ["q1"]},
        {"claim": "Churn is driven by pricing.", "type": "fact", "supporting_query_ids": ["q9"]},
        {"claim": "There are 12345 users.", "type": "fact", "supporting_query_ids": ["q1"]},
        {"claim": "Review the onboarding flow.", "type": "recommendation", "supporting_query_ids": []}]}
    client = Fake(call("SELECT COUNT(*) AS n FROM users"), final("**Summary** done"), final(json.dumps(findings)))
    r = investigate("How many users?", client=client)
    assert r["queries"][0]["id"] == "q1" and r["queries"][0]["rows"] == [[800]]
    st = [(f["type"], f["verification_status"]) for f in r["findings"]]
    assert st == [("fact", "verified"), ("hypothesis", "unsupported"), ("fact", "unverified_numbers"), ("recommendation", "not_applicable")]
    assert r["tokens_used"] == 200


def test_unsafe_sql_from_model_is_blocked_and_recorded():
    client = Fake(call("DROP TABLE users"), final("could not do it"), final('{"findings": []}'))
    r = investigate("drop it", client=client)
    assert r["queries"][0]["ok"] is False
    assert "Only SELECT" in r["queries"][0]["error"]
    from app.db import run_readonly
    assert run_readonly("SELECT COUNT(*) FROM users")["rows"] == [[800]]


def test_query_limit_enforced():
    client = Fake(call("SELECT 1 FROM users", cid="a"), call("SELECT 2 FROM users", cid="b"), final("stop"), final('{"findings": []}'))
    r = investigate("x", client=client, limits=Limits(max_queries=1))
    assert len(r["queries"]) == 1


def test_step_limit_returns_notice_not_crash():
    client = Fake(call("SELECT 1 FROM users", cid="a"), call("SELECT 2 FROM users", cid="b"))
    r = investigate("x", client=client, limits=Limits(max_steps=2))
    assert "stopped" in r["answer"] and r["findings"] == []


def test_number_matching_handles_percent_and_dates():
    q = [{"ok": True, "id": "q1", "rows": [[0.343, "2026-10"]]}]
    assert unmatched_numbers("Retention was 34% in 2026-10, week 2.", q) == []
    assert unmatched_numbers("Retention was 50%.", q) == [50.0]
    assert verify_findings("garbage", q) == []
