from typing import List, Dict
import os
import psycopg2
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
from decimal import Decimal
from datetime import date, datetime


# Load environment variables from .env file
load_dotenv()

# Initializes your MCP server instance. It's used to register your tools.
mcp = FastMCP("postgres-server")

# Database connection configuration from environment variables
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "practice_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.environ["DB_PASSWORD"],
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
}

MAX_ROWS = 200

def _clean(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v

@mcp.tool()
async def execute_sql(query: str) -> List[Dict]:
    """Run a read-only SELECT and return up to 200 rows as dicts."""
    q = query.strip().rstrip(";")
    if not q.lower().startswith(("select", "with")):
        raise ValueError("Only SELECT queries are allowed.")

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        conn.set_session(readonly=True)          # Postgres refuses writes
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = 10000")   # 10 seconds
            cur.execute(q)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchmany(MAX_ROWS + 1)  # one extra row tells us if we cut off
            result = [dict(zip(cols, map(_clean, r))) for r in rows[:MAX_ROWS]]
            if len(rows) > MAX_ROWS:
                result.append({"_note": f"Truncated at {MAX_ROWS} rows; add a LIMIT or aggregate."})
            return result
    finally:
        conn.close()

@mcp.tool()
async def get_schema(table: str) -> List[Dict]:
    """Return column names and types for a given table."""
    sql = """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = %s
    """
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (table,))
            rows = [{"column": r[0], "type": r[1]} for r in cur.fetchall()]
    return rows

@mcp.tool()
async def list_tables(schema: str = "") -> List[Dict]:
    """List tables and views in the database, with their schema.

    Leave `schema` empty to see every user schema (system schemas are skipped),
    or pass a name such as "public" to see just that one.
    """
    sql = """
        SELECT table_schema, table_name, table_type
        FROM information_schema.tables
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
          AND (%s = '' OR table_schema = %s)
        ORDER BY table_schema, table_name
    """
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            cur.execute(sql, (schema, schema))
            return [
                {"schema": r[0], "table": r[1], "type": r[2]}
                for r in cur.fetchall()
            ]
    finally:
        conn.close()

def main():
    # Run MCP server using stdio transport for AI assistant integration
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
