"""Turn a saved investigation into a shareable Markdown report."""


def to_markdown(inv: dict) -> str:
    out = [f"# Investigation: {inv['question']}", "",
           f"*Generated {inv['created_at']} UTC by QueryPilot AI. Synthetic or user-provided data; verify before acting.*",
           "", "## Findings", "", inv["answer"], ""]
    if inv.get("findings"):
        out += ["## Structured findings", ""]
        out += [f"- **{f['type'].upper()} · {f['verification_status'].replace('_', ' ')}**: {f['claim']} (evidence: {', '.join(f['supporting_query_ids']) or 'none'})" for f in inv["findings"]]
        out.append("")
    out += ["## Evidence", ""]
    for i, q in enumerate(inv["queries"], 1):
        status = "OK" if q.get("ok") else "FAILED"
        out += [f"### {q.get('id', i)}. {q.get('purpose') or 'Query'} ({status})", "", "```sql", q["sql"], "```", ""]
        if q.get("error"):
            out += [f"Error: {q['error']}", ""]
        cols, rows = q.get("columns"), q.get("rows")
        if cols and rows:
            out += ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
            out += ["| " + " | ".join(str(v) for v in r) + " |" for r in rows[:10]]
            if len(rows) > 10:
                out.append(f"\n*Showing 10 of {len(rows)} rows.*")
            out.append("")
    return "\n".join(out)
