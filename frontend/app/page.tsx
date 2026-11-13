"use client";
import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const EXAMPLES = [
  "Why did retention drop for users who signed up in October?",
  "Which acquisition channel brings the most revenue?",
  "How do cancellations differ by plan?",
];

type Finding = { claim: string; type: string; verification_status: string; supporting_query_ids: string[]; limitations?: string[]; unmatched_numbers?: number[] };
type Query = { id?: string; purpose?: string; sql: string; ok: boolean; columns?: string[]; rows?: unknown[][]; error?: string };
type Past = { id: string; question: string; created_at: string };
type Result = { findings?: Finding[]; id?: string; duration_ms?: number; question: string; answer: string; queries: Query[] };

function inline(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((p, i) =>
    p.startsWith("**") && p.endsWith("**") ? <strong key={i}>{p.slice(2, -2)}</strong> : <span key={i}>{p}</span>
  );
}

function Chart({ q }: { q: Query }) {
  const { columns, rows } = q;
  if (!columns || !rows || columns.length < 2 || rows.length < 2 || rows.length > 30) return null;
  const col = columns.findIndex((_, i) => i > 0 && rows.every((r) => typeof r[i] === "number"));
  if (col < 1) return null;
  const data = rows.map((r) => ({ label: String(r[0]), value: r[col] as number }));
  return (
    <div style={{ height: 220 }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="label" fontSize={12} />
          <YAxis fontSize={12} />
          <Tooltip />
          <Bar dataKey="value" name={columns[col]} fill="#748ffc" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function Home() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [history, setHistory] = useState<Past[]>([]);

  async function loadHistory() {
    try { const r = await fetch(`${API}/api/investigations`); if (r.ok) setHistory(await r.json()); } catch { /* history is optional */ }
  }
  useEffect(() => { loadHistory(); }, []);

  async function openPast(id: string) {
    setError("");
    try {
      const r = await fetch(`${API}/api/investigations/${id}`);
      if (!r.ok) throw new Error("Could not load that investigation");
      setResult(await r.json());
    } catch (e) { setError(e instanceof Error ? e.message : "Something went wrong"); }
  }

  async function ask(q: string) {
    if (q.trim().length < 3) return;
    setLoading(true); setError(""); setResult(null);
    try {
      const res = await fetch(`${API}/api/ask`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? `Request failed (${res.status})`);
      setResult(await res.json());
      loadHistory();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally { setLoading(false); }
  }

  return (
    <main>
      <h1>QueryPilot AI</h1>
      <p className="sub">Ask a business question. The agent runs several read-only SQL queries and shows its evidence.</p>
      <textarea rows={3} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="e.g. Why did retention drop last month?" />
      <div className="row">
        <button className="primary" disabled={loading} onClick={() => ask(question)}>{loading ? "Investigating…" : "Investigate"}</button>
        {EXAMPLES.map((ex) => (
          <button key={ex} className="chip" disabled={loading} onClick={() => { setQuestion(ex); ask(ex); }}>{ex}</button>
        ))}
      </div>
      {error && <div className="card err">{error}</div>}
      {result && (
        <>
          <div className="card">{result.answer.split("\n").map((l, i) => <p key={i}>{inline(l)}</p>)}</div>
          <div className="row" style={{ alignItems: "center", justifyContent: "space-between" }}>
            {result.findings && result.findings.length > 0 && (
            <>
              <h3>Findings</h3>
              {result.findings.map((f, i) => (
                <div className="card" key={i}>
                  <span className="muted">{f.type.toUpperCase()} · {f.verification_status.replace(/_/g, " ")}</span>
                  <p>{f.claim}</p>
                  {f.supporting_query_ids.length > 0 && <p className="muted">Evidence: {f.supporting_query_ids.join(", ")}</p>}
                  {f.unmatched_numbers && f.unmatched_numbers.length > 0 && <p className="err">Numbers not found in cited evidence: {f.unmatched_numbers.join(", ")}</p>}
                  {f.limitations?.map((l, li) => <p key={li} className="muted">Limitation: {l}</p>)}
                </div>
              ))}
            </>
          )}
          <h3>Evidence: {result.queries.length} queries{result.duration_ms ? <span className="muted"> · {(result.duration_ms / 1000).toFixed(1)}s</span> : null}</h3>
            {result.id && <a href={`${API}/api/investigations/${result.id}/export`}><button>Download report (.md)</button></a>}
          </div>
          {result.queries.map((q, i) => (
            <details key={i}>
              <summary>
                <span className={q.ok ? "ok" : "err"}>{q.ok ? "✓" : "✗"}</span> {q.id ? `[${q.id}] ` : ""}{q.purpose ?? `Query ${i + 1}`}
              </summary>
              <pre>{q.sql}</pre>
              {q.error && <p className="err">{q.error}</p>}
              <Chart q={q} />
              {q.columns && q.rows && (
                <div className="tablewrap"><table>
                  <thead><tr>{q.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
                  <tbody>{q.rows.slice(0, 20).map((r, ri) => <tr key={ri}>{r.map((v, ci) => <td key={ci}>{String(v)}</td>)}</tr>)}</tbody>
                </table></div>
              )}
            </details>
          ))}
        </>
      )}
      {history.length > 0 && (
        <>
          <h3>Past investigations</h3>
          {history.map((h) => (
            <div key={h.id}><button className="chip" onClick={() => openPast(h.id)}>{h.question}</button></div>
          ))}
        </>
      )}
    </main>
  );
}
