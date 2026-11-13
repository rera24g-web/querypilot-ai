"""Deterministic verification of structured findings against query evidence (plan steps 5.7, 7.1, 7.5).
Not an LLM reviewer: it checks that cited queries exist and that numbers in a claim appear in the evidence."""
import re

TYPES = {"fact", "hypothesis", "recommendation"}
_NUM = re.compile(r"(?<![\w.])-?\d[\d,]*\.?\d*%?")


def numbers(text: str) -> list[tuple[float, int]]:
    text = re.sub(r"\b\d{4}-\d{2}(-\d{2})?\b", "", text)                       # dates
    text = re.sub(r"\b(?:week|day|query|step|q)s?\s*\d+\b", "", text, flags=re.I)  # labels like "week 2"
    out = []
    for m in _NUM.finditer(text):
        raw = m.group().rstrip(".,").rstrip("%").replace(",", "")
        if re.fullmatch(r"(19|20)\d\d", raw):
            continue
        try:
            val = float(raw)
        except ValueError:
            continue
        out.append((val, len(raw.split(".")[1]) if "." in raw else 0))
    return out


def _evidence_values(queries: list[dict]) -> list[float]:
    vals = []
    for q in queries:
        for row in q.get("rows") or []:
            for v in row:
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    vals += [float(v), float(v) * 100]  # also match fractions quoted as percentages
    return vals


def unmatched_numbers(claim: str, queries: list[dict]) -> list[float]:
    ev = _evidence_values(queries)
    return [n for n, d in numbers(claim) if not any(abs(n - c) <= 0.5 * 10 ** -d + 1e-9 for c in ev)]


def verify_findings(findings: list, queries: list[dict]) -> list[dict]:
    ok = {q["id"]: q for q in queries if q.get("ok") and q.get("id")}
    out = []
    for raw in findings if isinstance(findings, list) else []:
        if not isinstance(raw, dict):
            continue
        ids = [i for i in (raw.get("supporting_query_ids") or []) if isinstance(i, str)]
        cited = [i for i in ids if i in ok]
        f = {"claim": str(raw.get("claim", "")), "type": raw.get("type") if raw.get("type") in TYPES else "hypothesis",
             "supporting_query_ids": cited, "limitations": list(raw.get("limitations") or [])}
        if f["type"] == "fact":
            if not cited:
                f.update(type="hypothesis", verification_status="unsupported")
                f["limitations"].append("Stated as fact but cited no successful query; downgraded to hypothesis.")
            else:
                bad = unmatched_numbers(f["claim"], [ok[i] for i in cited])
                f["verification_status"] = "unverified_numbers" if bad else "verified"
                if bad:
                    f["unmatched_numbers"] = bad
        else:
            f["verification_status"] = "not_applicable"
        out.append(f)
    return out
