"""SQLite schema and CRUD (stdlib sqlite3, no ORM)."""
import sqlite3
from dataclasses import asdict
from pathlib import Path

from core.categorize import normalize_merchant
from core.config import DB_PATH
from core.models import Expense, Settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  merchant TEXT NOT NULL,
  date TEXT NOT NULL,
  total REAL NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD',
  subtotal REAL, tax REAL, tip REAL,
  category TEXT NOT NULL,
  category_source TEXT NOT NULL,
  payment_method TEXT,
  document_type TEXT,
  note TEXT,
  file_path TEXT,
  file_hash TEXT,
  extraction_json TEXT,
  is_synthetic INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS line_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  expense_id INTEGER NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  quantity REAL,
  price REAL
);

CREATE TABLE IF NOT EXISTS merchant_overrides (
  merchant_key TEXT PRIMARY KEY,
  category TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT
);
CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);
CREATE INDEX IF NOT EXISTS idx_expenses_hash ON expenses(file_hash);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    path = path or DB_PATH
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: Path | str | None = None) -> None:
    """Create the schema if it doesn't exist. Safe to call on every startup."""
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
    finally:
        conn.close()


def get_setting(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row and row["value"] is not None else default


def set_setting(conn: sqlite3.Connection, key: str, value: str | None) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def load_settings(conn: sqlite3.Connection) -> Settings:
    budget = get_setting(conn, "monthly_budget")
    try:
        day = int(get_setting(conn, "cycle_start_day", "1"))
    except ValueError:
        day = 1
    return Settings(
        name=get_setting(conn, "name", "") or "",
        monthly_budget=float(budget) if budget else None,
        cycle_start_day=min(max(day, 1), 28),
    )


def save_settings(conn: sqlite3.Connection, s: Settings) -> None:
    set_setting(conn, "name", s.name.strip())
    set_setting(conn, "monthly_budget", None if s.monthly_budget is None else str(s.monthly_budget))
    set_setting(conn, "cycle_start_day", str(s.cycle_start_day))
    conn.commit()


def get_overrides(conn: sqlite3.Connection) -> dict[str, str]:
    return {r["merchant_key"]: r["category"] for r in conn.execute("SELECT * FROM merchant_overrides")}


def set_override(conn: sqlite3.Connection, merchant: str, category: str) -> None:
    conn.execute(
        "INSERT INTO merchant_overrides (merchant_key, category) VALUES (?, ?) "
        "ON CONFLICT(merchant_key) DO UPDATE SET category = excluded.category",
        (normalize_merchant(merchant), category),
    )
    conn.commit()


def expenses_with_hash(conn: sqlite3.Connection, file_hash: str) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM expenses WHERE file_hash = ? ORDER BY id", (file_hash,)).fetchall()


def expenses_on_date(conn: sqlite3.Connection, day: str) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM expenses WHERE date = ? ORDER BY id", (day,)).fetchall()


def insert_expense(conn: sqlite3.Connection, expense: Expense) -> int:
    values = asdict(expense)
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    cursor = conn.execute(f"INSERT INTO expenses ({columns}) VALUES ({placeholders})", tuple(values.values()))
    conn.commit()
    return cursor.lastrowid
