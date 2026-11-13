"""Read-only query execution with row limits and timeouts."""
import os
from sqlalchemy import create_engine, event, inspect
from .safety import validate

_engines: dict = {}


def get_engine(readonly: bool = True):
    url = os.getenv("DATABASE_URL", "sqlite:///querypilot.db")
    key = (url, readonly)
    if key not in _engines:
        engine = create_engine(url)
        if readonly and engine.dialect.name == "sqlite":
            @event.listens_for(engine, "connect")
            def _ro(dbapi_conn, _):
                dbapi_conn.execute("PRAGMA query_only = ON")
        _engines[key] = engine
    return _engines[key]


def dialect_name(engine) -> str:
    return {"postgresql": "postgres"}.get(engine.dialect.name, engine.dialect.name)


def table_names(engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def describe_schema() -> str:
    engine = get_engine()
    insp = inspect(engine)
    lines = []
    for t in sorted(insp.get_table_names()):
        cols = ", ".join(f"{c['name']} {c['type']}" for c in insp.get_columns(t))
        lines.append(f"{t}({cols})")
    return "\n".join(lines)


def run_readonly(sql: str) -> dict:
    engine = get_engine()
    d = dialect_name(engine)
    max_rows = int(os.getenv("MAX_ROWS", "200"))
    safe = validate(sql, table_names(engine), d, max_rows)
    with engine.connect() as conn:
        if d == "postgres":
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
            conn.exec_driver_sql(f"SET LOCAL statement_timeout = {int(os.getenv('QUERY_TIMEOUT_MS', '8000'))}")
        res = conn.exec_driver_sql(safe)
        rows = [list(r) for r in res.fetchall()]
        cols = list(res.keys())
    return {"columns": cols, "rows": rows, "row_count": len(rows),
            "truncated": len(rows) >= max_rows}
