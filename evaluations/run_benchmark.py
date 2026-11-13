"""Honest benchmark: runs the agent on each case, then compares the agent's LAST successful
query result with the gold query result (strict: same rows, same columns; floats rounded to int).
The agent never sees the gold SQL or answer. Usage (from repo root, with OPENAI_API_KEY set):
    python evaluations/run_benchmark.py"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.db import run_readonly


def norm(rows):
    fix = lambda v: round(v) if isinstance(v, float) else v
    return sorted(tuple(fix(v) for v in r) for r in rows)


def main():
    from app.agent import investigate
    cases = json.load(open(os.path.join(os.path.dirname(__file__), "cases.json")))
    passed, report = 0, []
    for c in cases:
        gold = norm(run_readonly(c["gold"])["rows"])
        out = investigate(c["q"])
        ok_queries = [q for q in out["queries"] if q["ok"]]
        got = norm(run_readonly(ok_queries[-1]["sql"])["rows"]) if ok_queries else None
        hit = got == gold
        passed += hit
        report.append({"question": c["q"], "correct": hit, "queries_used": len(out["queries"])})
        print(("PASS" if hit else "FAIL"), c["q"])
    print(f"\nResult correctness: {passed}/{len(cases)} = {100*passed/len(cases):.0f}%")
    json.dump(report, open(os.path.join(os.path.dirname(__file__), "last_report.json"), "w"), indent=2)


if __name__ == "__main__":
    main()
