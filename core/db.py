"""Postgres schema and CRUD (psycopg, no ORM). Every query is scoped by a required user_id."""
from dataclasses import asdict

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from core.categorize import normalize_merchant
from core.config import load_config
from core.models import Expense, Settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL,
  merchant TEXT NOT NULL,
  date DATE NOT NULL,
  total NUMERIC(12,2) NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD',
  subtotal NUMERIC(12,2), tax NUMERIC(12,2), tip NUMERIC(12,2),
  category TEXT NOT NULL,
  category_source TEXT NOT NULL,
  payment_method TEXT,
  document_type TEXT,
  note TEXT,
  file_hash TEXT,
  extraction_json JSONB,
  is_synthetic BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS merchant_overrides (
  user_id UUID NOT NULL,
  merchant_key TEXT NOT NULL,
  category TEXT NOT NULL,
  PRIMARY KEY (user_id, merchant_key)
);

CREATE TABLE IF NOT EXISTS settings (
  user_id UUID PRIMARY KEY,
  name TEXT NOT NULL DEFAULT '',
  monthly_budget NUMERIC(12,2),
  cycle_start_day INTEGER NOT NULL DEFAULT 1 CHECK (cycle_start_day BETWEEN 1 AND 28)
);
CREATE INDEX IF NOT EXISTS idx_expenses_user_date ON expenses(user_id, date);
CREATE INDEX IF NOT EXISTS idx_expenses_user_hash ON expenses(user_id, file_hash);
ALTER TABLE expenses DROP COLUMN IF EXISTS file_path;
"""

APP_ROLE = "snapspend_app"
USER_TABLES = ("expenses", "merchant_overrides", "settings")
CREATE_APP_ROLE = f"""
DO $$ BEGIN
  CREATE ROLE {APP_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS;
EXCEPTION WHEN duplicate_object OR unique_violation THEN NULL;
END $$;
"""

# Dates and amounts come back as plain strings and floats, the types the rest of core uses.
EXPENSE_COLUMNS = """
  id, user_id::text AS user_id, merchant, date::text AS date, total::float8 AS total, currency,
  subtotal::float8 AS subtotal, tax::float8 AS tax, tip::float8 AS tip, category, category_source,
  payment_method, document_type, note, file_hash, is_synthetic, created_at::text AS created_at
"""


def connect(conninfo: str | None = None) -> psycopg.Connection:
    url = load_config().database_url if conninfo is None else conninfo
    return psycopg.connect(url, row_factory=dict_row, autocommit=True)


def init_db(conn: psycopg.Connection) -> None:
    """Create the schema and row-level security. Safe to call on every startup."""
    conn.execute(SCHEMA)
    conn.execute(CREATE_APP_ROLE)
    conn.execute(f"GRANT {APP_ROLE} TO CURRENT_USER")
    schema = sql.Identifier(conn.execute("SELECT current_schema() AS s").fetchone()["s"])
    conn.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO " + APP_ROLE).format(schema))
    conn.execute(sql.SQL("GRANT USAGE ON ALL SEQUENCES IN SCHEMA {} TO " + APP_ROLE).format(schema))
    for table in USER_TABLES:
        conn.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
        conn.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        conn.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        conn.execute(f"DROP POLICY IF EXISTS own_rows ON {table}")
        conn.execute(
            f"CREATE POLICY own_rows ON {table} TO {APP_ROLE} "
            "USING (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid) "
            "WITH CHECK (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)"
        )


def act_as(conn: psycopg.Connection, user_id: str) -> None:
    """Limit this connection to one user's rows, so even a query missing its filter can't cross users."""
    conn.execute(f"SET ROLE {APP_ROLE}")
    conn.execute("SELECT set_config('app.user_id', %s, false)", (user_id,))


def delete_user_data(conn: psycopg.Connection, user_id: str) -> None:
    with conn.transaction():
        for table in USER_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE user_id = %s", (user_id,))


def delete_synthetic(conn: psycopg.Connection, user_id: str) -> int:
    return conn.execute("DELETE FROM expenses WHERE user_id = %s AND is_synthetic", (user_id,)).rowcount


def load_settings(conn: psycopg.Connection, user_id: str) -> Settings:
    row = conn.execute(
        "SELECT name, monthly_budget::float8 AS monthly_budget, cycle_start_day FROM settings WHERE user_id = %s",
        (user_id,),
    ).fetchone()
    return Settings(**row) if row else Settings()


def save_settings(conn: psycopg.Connection, user_id: str, s: Settings) -> None:
    conn.execute(
        "INSERT INTO settings (user_id, name, monthly_budget, cycle_start_day) VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (user_id) DO UPDATE SET name = excluded.name, "
        "monthly_budget = excluded.monthly_budget, cycle_start_day = excluded.cycle_start_day",
        (user_id, s.name.strip(), s.monthly_budget, s.cycle_start_day),
    )


def get_overrides(conn: psycopg.Connection, user_id: str) -> dict[str, str]:
    rows = conn.execute("SELECT merchant_key, category FROM merchant_overrides WHERE user_id = %s", (user_id,))
    return {r["merchant_key"]: r["category"] for r in rows}


def set_override(conn: psycopg.Connection, user_id: str, merchant: str, category: str) -> None:
    conn.execute(
        "INSERT INTO merchant_overrides (user_id, merchant_key, category) VALUES (%s, %s, %s) "
        "ON CONFLICT (user_id, merchant_key) DO UPDATE SET category = excluded.category",
        (user_id, normalize_merchant(merchant), category),
    )


def expenses_with_hash(conn: psycopg.Connection, user_id: str, file_hash: str) -> list[dict]:
    query = f"SELECT {EXPENSE_COLUMNS} FROM expenses WHERE user_id = %s AND file_hash = %s ORDER BY id"
    return conn.execute(query, (user_id, file_hash)).fetchall()


def expenses_on_date(conn: psycopg.Connection, user_id: str, day: str) -> list[dict]:
    query = f"SELECT {EXPENSE_COLUMNS} FROM expenses WHERE user_id = %s AND date = %s::date ORDER BY id"
    return conn.execute(query, (user_id, day)).fetchall()


def insert_expense(conn: psycopg.Connection, user_id: str, expense: Expense) -> int:
    values = {**asdict(expense), "user_id": user_id}
    columns = ", ".join(values)
    placeholders = ", ".join("%s" for _ in values)
    row = conn.execute(
        f"INSERT INTO expenses ({columns}) VALUES ({placeholders}) RETURNING id", tuple(values.values())
    ).fetchone()
    return row["id"]


def get_expense(conn: psycopg.Connection, user_id: str, expense_id: int) -> dict | None:
    query = f"SELECT {EXPENSE_COLUMNS}, extraction_json FROM expenses WHERE user_id = %s AND id = %s"
    return conn.execute(query, (user_id, expense_id)).fetchone()


def list_expenses(
    conn: psycopg.Connection,
    user_id: str,
    start: str | None = None,
    end: str | None = None,
    category: str | None = None,
    limit: int = 500,
) -> list[dict]:
    query = f"SELECT {EXPENSE_COLUMNS} FROM expenses WHERE user_id = %s"
    params: list = [user_id]
    if start:
        query += " AND date >= %s::date"
        params.append(start)
    if end:
        query += " AND date <= %s::date"
        params.append(end)
    if category:
        query += " AND category = %s"
        params.append(category)
    query += " ORDER BY date DESC, id DESC LIMIT %s"
    return conn.execute(query, (*params, limit)).fetchall()


def update_expense(conn: psycopg.Connection, user_id: str, expense_id: int, values: dict) -> None:
    """`values` comes from code, never from a request, so its keys are safe as column names."""
    assignments = ", ".join(f"{column} = %s" for column in values)
    conn.execute(
        f"UPDATE expenses SET {assignments} WHERE user_id = %s AND id = %s", (*values.values(), user_id, expense_id)
    )


def delete_expense(conn: psycopg.Connection, user_id: str, expense_id: int) -> bool:
    cursor = conn.execute("DELETE FROM expenses WHERE user_id = %s AND id = %s", (user_id, expense_id))
    return cursor.rowcount > 0
