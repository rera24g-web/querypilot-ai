"""SQL safety layer: every query the agent writes must pass validate() first."""
import sqlglot
from sqlglot import exp


class UnsafeSQL(ValueError):
    pass


_BLOCKED_NAMES = ["Insert", "Update", "Delete", "Drop", "Create", "Alter", "Command",
                  "Merge", "Into", "Pragma", "TruncateTable", "Set", "Copy"]
BLOCKED_NODES = tuple(getattr(exp, n) for n in _BLOCKED_NAMES if hasattr(exp, n))
BLOCKED_FUNCS = {"pg_sleep", "pg_read_file", "pg_read_binary_file", "pg_ls_dir",
                 "lo_import", "lo_export", "dblink", "load_extension",
                 "readfile", "writefile", "set_config"}
ROOT_TYPES = tuple(getattr(exp, n) for n in ["Select", "Union", "Intersect", "Except"]
                   if hasattr(exp, n))


def validate(sql: str, allowed_tables: set[str], dialect: str, max_rows: int) -> str:
    """Return a safe, row-limited version of `sql` or raise UnsafeSQL."""
    try:
        statements = [s for s in sqlglot.parse(sql, read=dialect) if s is not None]
    except sqlglot.errors.SqlglotError as e:
        raise UnsafeSQL(f"Could not parse SQL: {e}")
    if len(statements) != 1:
        raise UnsafeSQL("Exactly one SQL statement is allowed.")
    tree = statements[0]
    if not isinstance(tree, ROOT_TYPES):
        raise UnsafeSQL("Only SELECT queries are allowed.")

    nodes = list(tree.find_all(exp.Expression))
    for node in nodes:
        if isinstance(node, BLOCKED_NODES):
            raise UnsafeSQL(f"Forbidden operation: {type(node).__name__}")
        if isinstance(node, exp.Anonymous) and node.name.lower() in BLOCKED_FUNCS:
            raise UnsafeSQL(f"Forbidden function: {node.name}")

    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    allowed = {t.lower() for t in allowed_tables} | ctes
    for table in tree.find_all(exp.Table):
        if table.name.lower() not in allowed:
            raise UnsafeSQL(f"Unknown or disallowed table: {table.name}")

    inner = tree.sql(dialect=dialect)
    return f"SELECT * FROM ({inner}) AS q LIMIT {int(max_rows)}"
