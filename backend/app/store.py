"""Application data (separate from the read-only analytics DB): saved investigations."""
import json, os, uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, text

_engines: dict = {}


def _engine():
    url = os.getenv("APP_DATABASE_URL", "sqlite:///querypilot_app.db")
    if url not in _engines:
        e = create_engine(url)
        with e.begin() as c:
            # Note: Migration should add user_id column.
            # This creates the table without user_id for backward compatibility,
            # but production should use Alembic migrations.
            c.execute(text("""CREATE TABLE IF NOT EXISTS investigations (
                id TEXT PRIMARY KEY, question TEXT NOT NULL, answer TEXT NOT NULL,
                queries_json TEXT NOT NULL, duration_ms INTEGER, created_at TEXT NOT NULL, findings_json TEXT)"""))
            # Check if user_id column exists, add if missing (migration fallback)
            try:
                c.execute(text("SELECT user_id FROM investigations LIMIT 1"))
            except Exception:
                # Column doesn't exist, add it
                c.execute(text("ALTER TABLE investigations ADD COLUMN user_id TEXT"))
        _engines[url] = e
    return _engines[url]


def save(question: str, answer: str, queries: list, duration_ms: int, findings: list | None = None, user_id: str | None = None) -> str:
    """
    Save an investigation to the database.

    Args:
        question: The user's question
        answer: The AI-generated answer
        queries: List of query results
        duration_ms: Time taken for investigation
        findings: Optional structured findings
        user_id: User ID for ownership (required for new records)

    Returns:
        Investigation ID
    """
    if not user_id:
        # For backward compatibility, legacy records get a special marker
        # New authenticated records MUST have user_id
        user_id = "__legacy_unassigned__"

    inv_id = uuid.uuid4().hex[:12]
    with _engine().begin() as c:
        c.execute(text("INSERT INTO investigations (id, question, answer, queries_json, duration_ms, created_at, findings_json, user_id) VALUES (:i,:q,:a,:j,:d,:t,:f,:u)"),
                  {"i": inv_id, "q": question, "a": answer, "j": json.dumps(queries, default=str),
                   "d": duration_ms, "f": json.dumps(findings or []), "t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "u": user_id})
    return inv_id


def list_recent(limit: int = 30, user_id: str | None = None) -> list[dict]:
    """
    List recent investigations, optionally filtered by user.

    Args:
        limit: Maximum number of investigations to return
        user_id: If provided, only return investigations owned by this user

    Returns:
        List of investigation metadata dictionaries
    """
    with _engine().connect() as c:
        if user_id:
            rows = c.execute(text("SELECT id, question, created_at FROM investigations "
                                  "WHERE user_id = :u ORDER BY created_at DESC LIMIT :n"),
                             {"u": user_id, "n": limit}).fetchall()
        else:
            # Backward compatible: return all (for migration period)
            rows = c.execute(text("SELECT id, question, created_at FROM investigations "
                                  "ORDER BY created_at DESC LIMIT :n"), {"n": limit}).fetchall()
    return [{"id": r[0], "question": r[1], "created_at": r[2]} for r in rows]


def get(inv_id: str, user_id: str | None = None) -> dict | None:
    """
    Get an investigation by ID, optionally verifying ownership.

    Args:
        inv_id: Investigation ID
        user_id: If provided, only return if owned by this user

    Returns:
        Investigation dictionary or None if not found/unauthorized
    """
    with _engine().connect() as c:
        if user_id:
            # Check for user_id column (needed for new installs)
            try:
                c.execute(text("SELECT user_id FROM investigations LIMIT 1"))
                r = c.execute(text("SELECT id, question, answer, queries_json, duration_ms, created_at, findings_json, user_id "
                                   "FROM investigations WHERE id = :i AND user_id = :u"),
                              {"i": inv_id, "u": user_id}).fetchone()
            except Exception:
                # Column doesn't exist - legacy database
                r = c.execute(text("SELECT id, question, answer, queries_json, duration_ms, created_at, findings_json "
                                   "FROM investigations WHERE id = :i"), {"i": inv_id}).fetchone()
                if r:
                    # Check ownership marker in legacy records
                    # Legacy records have user_id = '__legacy_unassigned__'
                    # They should return None for authenticated user requests
                    return None
        else:
            r = c.execute(text("SELECT id, question, answer, queries_json, duration_ms, created_at, findings_json "
                               "FROM investigations WHERE id = :i"), {"i": inv_id}).fetchone()

    if not r:
        return None

    # Convert Row object to tuple for reliable index access
    row_tuple = tuple(r)

    result = {"id": row_tuple[0], "question": row_tuple[1], "answer": row_tuple[2], "queries": json.loads(row_tuple[3]),
              "duration_ms": row_tuple[4], "created_at": row_tuple[5], "findings": json.loads(row_tuple[6] or "[]")}

    # Include user_id in response if available (8 columns: 0-7)
    # When user_id filter is applied, we select 8 columns with user_id at index 7
    if len(row_tuple) > 7:
        result["user_id"] = row_tuple[7]

    return result
