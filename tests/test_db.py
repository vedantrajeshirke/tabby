from core import db
from core.models import Settings


def test_init_creates_schema(tmp_path):
    path = tmp_path / "t.db"
    db.init_db(path)
    db.init_db(path)  # idempotent
    with db.connect(path) as conn:
        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"expenses", "line_items", "merchant_overrides", "settings"} <= tables
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_settings_defaults_and_roundtrip(tmp_path):
    path = tmp_path / "t.db"
    db.init_db(path)
    with db.connect(path) as conn:
        assert db.load_settings(conn) == Settings("", None, 1)
        db.save_settings(conn, Settings("  Ava ", 800.0, 15))
        assert db.load_settings(conn) == Settings("Ava", 800.0, 15)
        db.save_settings(conn, Settings("Ava", None, 15))
        assert db.load_settings(conn).monthly_budget is None


def test_line_items_cascade(tmp_path):
    path = tmp_path / "t.db"
    db.init_db(path)
    with db.connect(path) as conn:
        conn.execute("INSERT INTO expenses (merchant,date,total,category,category_source) VALUES ('A','2026-01-01',1,'Other','default')")
        conn.execute("INSERT INTO line_items (expense_id,name) VALUES (1,'x')")
        conn.execute("DELETE FROM expenses WHERE id=1")
        assert conn.execute("SELECT COUNT(*) FROM line_items").fetchone()[0] == 0
