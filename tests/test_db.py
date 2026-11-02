from core import db
from core.models import Expense, Settings

USER = "00000000-0000-0000-0000-00000000000a"
OTHER_USER = "00000000-0000-0000-0000-00000000000b"


def expense(**changes):
    values = dict(merchant="Safeway", date="2026-10-30", total=23.47, category="Groceries", category_source="rule")
    return Expense(**{**values, **changes})


def test_init_creates_schema_and_is_idempotent(conn):
    db.init_db(conn)
    rows = conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()")
    assert {r["table_name"] for r in rows} == {"expenses", "merchant_overrides", "settings"}


def test_settings_defaults_and_roundtrip(conn):
    assert db.load_settings(conn, USER) == Settings("", None, 1)
    db.save_settings(conn, USER, Settings("  Ava ", 800.0, 15))
    assert db.load_settings(conn, USER) == Settings("Ava", 800.0, 15)
    db.save_settings(conn, USER, Settings("Ava", None, 15))
    assert db.load_settings(conn, USER).monthly_budget is None


def test_settings_are_per_user(conn):
    db.save_settings(conn, USER, Settings("Ava", 800.0, 15))
    assert db.load_settings(conn, OTHER_USER) == Settings()


def test_cycle_start_day_is_limited(conn):
    import psycopg
    import pytest

    with pytest.raises(psycopg.errors.CheckViolation):
        db.save_settings(conn, USER, Settings("Ava", None, 29))


def test_overrides_roundtrip_with_normalized_key_and_per_user(conn):
    db.set_override(conn, USER, "Joe's Deli #12", "Groceries")
    db.set_override(conn, USER, "JOE'S DELI", "Other")
    assert db.get_overrides(conn, USER) == {"JOE'S DELI": "Other"}
    assert db.get_overrides(conn, OTHER_USER) == {}


def test_expense_roundtrip_types_and_user_scope(conn):
    expense_id = db.insert_expense(conn, USER, expense(file_hash="abc", extraction_json='{"total": 23.47}', tax=1.5))
    row = db.expenses_on_date(conn, USER, "2026-10-30")[0]
    assert (row["id"], row["date"], row["total"], row["tax"], row["subtotal"]) == (expense_id, "2026-10-30", 23.47, 1.5, None)
    assert row["is_synthetic"] is False
    assert db.expenses_with_hash(conn, USER, "abc")[0]["id"] == expense_id
    assert db.expenses_on_date(conn, OTHER_USER, "2026-10-30") == []
    assert db.expenses_with_hash(conn, OTHER_USER, "abc") == []


def test_amounts_are_exact_decimals(conn):
    db.insert_expense(conn, USER, expense(total=0.1))
    db.insert_expense(conn, USER, expense(total=0.2))
    total = conn.execute("SELECT sum(total) AS s FROM expenses").fetchone()["s"]
    assert str(total) == "0.30"
