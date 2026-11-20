import json
import re
import sqlite3

from config import config
from logger import get_logger

logger = get_logger("sql_tool")

FORBIDDEN_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "ATTACH", "DETACH",
    "PRAGMA", "VACUUM", "REPLACE", "CREATE"
]
FORBIDDEN_PATTERN = re.compile(
    r"\b(" + "|".join(FORBIDDEN_KEYWORDS) + r")\b",
    re.IGNORECASE
)

MAX_OPCODES = 250_000
OPCODE_STEP = 1_000
MAX_ROW_LIMIT = 100


def _get_readonly_connection() -> sqlite3.Connection:
    """Opens a SQLite connection in true read-only URI mode with query_only pragma."""
    resolved_path = config.DB_PATH.resolve()
    db_uri = f"file:{resolved_path}?mode=ro"
    conn = sqlite3.connect(db_uri, uri=True, timeout=5.0)
    conn.execute("PRAGMA query_only = ON;")
    return conn


def get_database_schema() -> str:
    """Returns the schema of the database to help formulate SQL queries."""
    try:
        conn = _get_readonly_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()

            schema = {}
            for table in tables:
                table_name = table[0]
                if table_name != 'sqlite_sequence':
                    cursor.execute(f"PRAGMA table_info({table_name});")
                    columns = cursor.fetchall()
                    schema[table_name] = [col[1] + f" ({col[2]})" for col in columns]

            return json.dumps(schema, indent=2)
        finally:
            conn.close()
    except Exception as e:
        logger.error("Error fetching schema: %s", e)
        return json.dumps({"error": f"Error fetching schema: {e}"})


def execute_sql_query(query: str) -> str:
    """Executes a read-only SQL query with token boundary checks and resource caps."""
    if not isinstance(query, str) or not query.strip():
        return json.dumps({"error": "Only SELECT queries are allowed. Query cannot be empty."})

    raw_query = query.strip()

    # Reject SQL comments
    if "--" in raw_query or "/*" in raw_query or "*/" in raw_query:
        return json.dumps({"error": "Only SELECT queries are allowed. Comments are forbidden."})

    # Handle optional single trailing semicolon; reject internal semicolons
    if raw_query.endswith(";"):
        inner_query = raw_query[:-1].strip()
    else:
        inner_query = raw_query

    if ";" in inner_query:
        return json.dumps({"error": "Only SELECT queries are allowed. Multi-statement queries and semicolons are forbidden."})

    # Validate that the statement begins with SELECT
    if not re.match(r"^SELECT\b", inner_query, re.IGNORECASE):
        return json.dumps({"error": "Only SELECT queries are allowed."})

    # Token/regex boundary checks for prohibited non-SELECT keywords
    keyword_match = FORBIDDEN_PATTERN.search(inner_query)
    if keyword_match:
        return json.dumps({"error": f"Only SELECT queries are allowed. Forbidden keyword: '{keyword_match.group(0)}'."})

    # Enforce maximum row cap by wrapping the statement
    safe_query = f"SELECT * FROM ({inner_query}) LIMIT {MAX_ROW_LIMIT}"

    total_opcodes = 0

    def progress_handler():
        nonlocal total_opcodes
        total_opcodes += OPCODE_STEP
        if total_opcodes > MAX_OPCODES:
            return 1  # Aborts execution
        return 0

    try:
        conn = _get_readonly_connection()
        conn.row_factory = sqlite3.Row
        conn.set_progress_handler(progress_handler, OPCODE_STEP)

        try:
            cursor = conn.cursor()
            cursor.execute(safe_query)
            rows = cursor.fetchall()
            results = [dict(row) for row in rows[:MAX_ROW_LIMIT]]
            return json.dumps(results)
        finally:
            try:
                conn.set_progress_handler(None, 0)
            except Exception:
                pass
            conn.close()

    except sqlite3.OperationalError as e:
        err_msg = str(e).lower()
        if "interrupted" in err_msg:
            logger.warning("Query exceeded VM opcode limit (%d opcodes): %s", total_opcodes, query)
            return json.dumps({"error": "Query aborted: resource opcode limit exceeded."})
        logger.error("SQLite OperationalError: %s", e)
        return json.dumps({"error": f"Database query error: {e}"})
    except Exception as e:
        logger.error("Error executing SQL query: %s", e)
        return json.dumps({"error": f"Error executing SQL query: {e}"})
