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
type User = { id: string; email: string; is_active: boolean; created_at: string };

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

// Auth Modal Component
function AuthModal({
  isOpen,
  onClose,
  mode,
  onSuccess,
  onSwitchMode
}: {
  isOpen: boolean;
  onClose: () => void;
  mode: 'login' | 'register';
  onSuccess: () => void;
  onSwitchMode: (mode: 'login' | 'register') => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isOpen) {
      setEmail("");
      setPassword("");
      setError("");
    }
  }, [isOpen]);

  async function handleSubmit() {
    setLoading(true);
    setError("");
    try {
      const endpoint = mode === 'login' ? '/auth/login' : '/auth/register';
      const res = await fetch(`${API}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
        credentials: 'include',
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? 'Request failed');
      }
      onSuccess();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong');
    } finally {
      setLoading(false);
    }
  }

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: 'rgba(0,0,0,0.5)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
    }}>
      <div className="card" style={{
        minWidth: '300px',
        maxWidth: '400px',
        padding: '24px',
      }}>
        <h3 style={{ margin: '0 0 16px 0' }}>{mode === 'login' ? 'Login' : 'Register'}</h3>
        {error && <div className="card err" style={{ margin: '0 0 12px 0' }}>{error}</div>}
        <input
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email"
          type="email"
          autoComplete="email"
          style={{ marginBottom: '12px', width: '100%', padding: '12px', border: '1px solid var(--line)', borderRadius: '8px', background: 'var(--card)', color: 'var(--fg)', font: 'inherit' }}
        />
        <input
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password (min 8 characters)"
          type="password"
          autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          style={{ marginBottom: '16px', width: '100%', padding: '12px', border: '1px solid var(--line)', borderRadius: '8px', background: 'var(--card)', color: 'var(--fg)', font: 'inherit' }}
        />
        <div className="row">
          <button className="primary" disabled={loading} onClick={handleSubmit}>
            {loading ? 'Submitting...' : mode === 'login' ? 'Login' : 'Register'}
          </button>
          <button onClick={onClose} disabled={loading}>Cancel</button>
        </div>
        <p style={{ fontSize: '14px', marginTop: '16px', color: 'var(--muted)', textAlign: 'center' }}>
          {mode === 'login' ? "Don't have an account?" : "Already have an account?"}
          <button
            onClick={() => onSwitchMode(mode === 'login' ? 'register' : 'login')}
            style={{ color: 'var(--accent)', padding: '0 4px', background: 'none', border: 'none', textDecoration: 'underline', cursor: 'pointer', marginLeft: '4px' }}
          >
            {mode === 'login' ? 'Register' : 'Login'}
          </button>
        </p>
      </div>
    </div>
  );
}

// Auth Controls Component
function AuthControls({
  user,
  onLogout,
  onShowLogin,
  onShowRegister
}: {
  user: User | null;
  onLogout: () => void;
  onShowLogin: () => void;
  onShowRegister: () => void;
}) {
  return (
    <div className="row" style={{ alignItems: 'center', justifyContent: 'space-between' }}>
      <h1>QueryPilot AI</h1>
      {user ? (
        <div className="row" style={{ alignItems: 'center', gap: '12px' }}>
          <span className="muted" style={{ fontSize: '14px' }}>{user.email}</span>
          <button onClick={onLogout} style={{ background: 'var(--bad)', color: '#fff' }}>Logout</button>
        </div>
      ) : (
        <div className="row">
          <button onClick={onShowLogin}>Login</button>
          <button onClick={onShowRegister}>Register</button>
        </div>
      )}
    </div>
  );
}

export default function Home() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [history, setHistory] = useState<Past[]>([]);
  const [user, setUser] = useState<User | null>(null);
  const [authMode, setAuthMode] = useState<'login' | 'register' | null>(null);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);

  // Check authentication status on mount
  useEffect(() => {
    checkAuth();
  }, []);

  async function checkAuth() {
    try {
      const r = await fetch(`${API}/auth/me`, { credentials: 'include' });
      if (r.ok) {
        const data = await r.json();
        setUser(data);
        loadCsrfToken();
      } else {
        setUser(null);
        setCsrfToken(null);
      }
    } catch {
      setUser(null);
      setCsrfToken(null);
    }
  }

  async function loadCsrfToken() {
    try {
      const r = await fetch(`${API}/auth/csrf-token`, { credentials: 'include' });
      if (r.ok) {
        const data = await r.json();
        setCsrfToken(data.csrf_token);
      }
    } catch {
      setCsrfToken(null);
    }
  }

  async function handleLogout() {
    try {
      await fetch(`${API}/auth/logout`, {
        method: 'POST',
        credentials: 'include'
      });
    } catch {
      // Ignore errors on logout
    }
    setUser(null);
    setCsrfToken(null);
  }

  async function loadHistory() {
    if (!user) {
      setHistory([]);
      return;
    }
    try {
      const r = await fetch(`${API}/api/investigations`, { credentials: 'include' });
      if (r.ok) setHistory(await r.json());
    } catch { /* history is optional */ }
  }

  useEffect(() => { loadHistory(); }, [user]);

  async function openPast(id: string) {
    setError("");
    try {
      const r = await fetch(`${API}/api/investigations/${id}`, { credentials: 'include' });
      if (!r.ok) throw new Error("Could not load that investigation");
      setResult(await r.json());
    } catch (e) { setError(e instanceof Error ? e.message : "Something went wrong"); }
  }

  async function ask(q: string) {
    if (q.trim().length < 3 || !user) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const headers: HeadersInit = { "Content-Type": "application/json" };
      if (csrfToken) {
        headers["X-CSRF-Token"] = csrfToken;
      }
      const res = await fetch(`${API}/api/ask`, {
        method: "POST",
        headers,
        body: JSON.stringify({ question: q }),
        credentials: "include"
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? `Request failed (${res.status})`);
      const data = await res.json();
      setResult(data);
      // Refresh CSRF token if it changed (some backends rotate it)
      if (res.headers.get("set-cookie")) {
        await loadCsrfToken();
      }
      loadHistory();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally { setLoading(false); }
  }

  async function handleAuthSuccess() {
    setAuthMode(null);
    await checkAuth();
  }

  return (
    <main>
      <AuthControls
        user={user}
        onLogout={handleLogout}
        onShowLogin={() => setAuthMode('login')}
        onShowRegister={() => setAuthMode('register')}
      />
      <p className="sub">Ask a business question. The agent runs several read-only SQL queries and shows its evidence.</p>
      {!user ? (
        <div className="card" style={{ textAlign: 'center', padding: '32px' }}>
          <p style={{ margin: 0, color: 'var(--muted)' }}>Please login or register to investigate queries.</p>
        </div>
      ) : (
        <>
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
        </>
      )}

      {/* Auth Modal */}
      <AuthModal
        isOpen={authMode === 'login'}
        onClose={() => setAuthMode(null)}
        mode="login"
        onSuccess={handleAuthSuccess}
        onSwitchMode={(m) => setAuthMode(m)}
      />
      <AuthModal
        isOpen={authMode === 'register'}
        onClose={() => setAuthMode(null)}
        mode="register"
        onSuccess={handleAuthSuccess}
        onSwitchMode={(m) => setAuthMode(m)}
      />
    </main>
  );
}