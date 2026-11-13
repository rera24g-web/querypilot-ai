"""Plain tool-calling analytics agent: plan -> run SQL -> answer -> structured findings -> deterministic verification.
Operational limits stop runaway investigations (plan step 5.9)."""
import json
import os
import time
from dataclasses import dataclass
from openai import OpenAI
from .db import describe_schema, dialect_name, get_engine, run_readonly
from .metrics import metrics_prompt
from .safety import UnsafeSQL
from .verify import verify_findings


@dataclass
class Limits:
    max_steps: int = 8
    max_queries: int = 10
    max_seconds: int = 120
    max_tokens: int = 80000


TOOLS = [{"type": "function", "function": {
    "name": "run_sql",
    "description": "Run ONE read-only SELECT query against the analytics database.",
    "parameters": {"type": "object", "properties": {
        "purpose": {"type": "string", "description": "What this query tests or measures"},
        "sql": {"type": "string"}}, "required": ["purpose", "sql"]}}}]

FINDINGS_PROMPT = """Extract the findings from this analytics investigation as JSON:
{"findings": [{"claim": str, "type": "fact"|"hypothesis"|"recommendation", "supporting_query_ids": ["q1"], "limitations": [str]}]}
Rules: a "fact" must be directly supported by the cited query results and quote their numbers exactly.
Explanations that need more evidence are "hypothesis". Proposed actions are "recommendation".
Use only query ids from the evidence list. Output JSON only."""


def system_prompt() -> str:
    d = dialect_name(get_engine())
    return f"""You are a product analytics agent for a Product Manager.
Database dialect: {d}. Tables:
{describe_schema()}

{metrics_prompt(d)}

Process: (1) state a short investigation plan, (2) run several focused queries with run_sql
(compare cohorts, channels, countries, time periods), (3) test your hypotheses against the numbers,
(4) answer.
Rules:
- Only use data you actually queried. Never invent numbers.
- Distinguish correlation from causation. Say plainly when the data is insufficient.
- If a query errors, fix it and retry; do not repeat the same failing query.
Final answer format (markdown): **Summary**, **Evidence** (key numbers), **Likely explanation**,
**Confidence & caveats**, **Recommended next steps**."""


def extract_findings(client, model: str, question: str, answer: str, queries: list[dict]) -> list:
    evidence = [{"id": q["id"], "purpose": q.get("purpose"), "columns": q.get("columns"), "rows": (q.get("rows") or [])[:15]}
                for q in queries if q.get("ok")]
    try:
        resp = client.chat.completions.create(
            model=model, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": FINDINGS_PROMPT},
                      {"role": "user", "content": json.dumps({"question": question, "answer": answer, "evidence": evidence}, default=str)}])
        return json.loads(resp.choices[0].message.content).get("findings", [])
    except Exception:
        return []  # findings are an add-on; never fail the investigation because of them


def investigate(question: str, client=None, limits: Limits | None = None) -> dict:
    client = client or OpenAI()
    limits = limits or Limits()
    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    start, tokens, stopped, answer = time.monotonic(), 0, None, None
    messages = [{"role": "system", "content": system_prompt()}, {"role": "user", "content": question}]
    queries: list[dict] = []
    for _ in range(limits.max_steps):
        if time.monotonic() - start > limits.max_seconds:
            stopped = "time limit"; break
        if tokens > limits.max_tokens:
            stopped = "token limit"; break
        resp = client.chat.completions.create(model=model, messages=messages, tools=TOOLS)
        tokens += getattr(getattr(resp, "usage", None), "total_tokens", 0) or 0
        msg = resp.choices[0].message
        messages.append(msg)
        if not msg.tool_calls:
            answer = msg.content
            break
        for call in msg.tool_calls:
            args = json.loads(call.function.arguments)
            if len(queries) >= limits.max_queries:
                result = {"error": "Query limit reached. Write your final answer from the evidence you already have."}
            else:
                entry = {"id": f"q{len(queries) + 1}", "purpose": args.get("purpose"), "sql": args["sql"]}
                try:
                    result = run_readonly(args["sql"])
                    entry.update(ok=True, columns=result["columns"], rows=result["rows"][:50])
                except UnsafeSQL as e:
                    result = {"error": f"Blocked by safety layer: {e}"}
                    entry.update(ok=False, error=str(e))
                except Exception as e:  # SQL errors go back to the model so it can self-correct
                    result = {"error": str(e)[:500]}
                    entry.update(ok=False, error=str(e)[:500])
                queries.append(entry)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, default=str)[:6000]})
    if answer is None:
        answer = f"Investigation stopped ({stopped or 'step limit'}) before a final answer."
    findings = verify_findings(extract_findings(client, model, question, answer, queries), queries) if queries and stopped is None else []
    return {"question": question, "answer": answer, "queries": queries, "findings": findings, "tokens_used": tokens}
