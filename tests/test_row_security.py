"""Row-level security must hold even when a query forgets its user filter."""
import psycopg
import pytest

from core import db
from core.models import Expense, Settings

A = "00000000-0000-0000-0000-00000000000a"
B = "00000000-0000-0000-0000-00000000000b"


def expense():
    return Expense(merchant="Private Shop", date="2026-10-30", total=5.0, category="Other", category_source="default")


@pytest.fixture
def two_users(conn):
    db.insert_expense(conn, A, expense())
    db.insert_expense(conn, B, expense())
    db.save_settings(conn, A, Settings("Ann"))
    db.save_settings(conn, B, Settings("Bo"))
    db.set_override(conn, A, "Shop", "Other")
    db.set_override(conn, B, "Shop", "Travel")
    return conn


@pytest.mark.parametrize("table", db.USER_TABLES)
def test_unfiltered_select_sees_only_own_rows(two_users, table):
    db.act_as(two_users, A)
    rows = two_users.execute(f"SELECT user_id::text AS u FROM {table}").fetchall()
    assert [r["u"] for r in rows] == [A]


@pytest.mark.parametrize("table", db.USER_TABLES)
def test_unfiltered_update_and_delete_leave_others_alone(two_users, table):
    db.act_as(two_users, A)
    two_users.execute(f"DELETE FROM {table}")
    two_users.execute("RESET ROLE")
    rows = two_users.execute(f"SELECT user_id::text AS u FROM {table}").fetchall()
    assert [r["u"] for r in rows] == [B]


def test_unfiltered_update_changes_only_own_rows(two_users):
    db.act_as(two_users, A)
    two_users.execute("UPDATE expenses SET merchant = 'changed'")
    two_users.execute("RESET ROLE")
    changed = two_users.execute("SELECT user_id::text AS u FROM expenses WHERE merchant = 'changed'").fetchall()
    assert [r["u"] for r in changed] == [A]


def test_cannot_insert_a_row_for_someone_else(two_users):
    db.act_as(two_users, A)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.insert_expense(two_users, B, expense())


def test_cannot_move_own_row_to_someone_else(two_users):
    db.act_as(two_users, A)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        two_users.execute("UPDATE expenses SET user_id = %s", (B,))


@pytest.mark.parametrize("value", [None, ""])
def test_no_user_set_sees_nothing(two_users, value):
    two_users.execute(f"SET ROLE {db.APP_ROLE}")
    if value is not None:
        two_users.execute("SELECT set_config('app.user_id', %s, false)", (value,))
    assert two_users.execute("SELECT * FROM expenses").fetchall() == []


def test_restricted_role_cannot_turn_security_off(two_users):
    db.act_as(two_users, A)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        two_users.execute("ALTER TABLE expenses DISABLE ROW LEVEL SECURITY")


def test_role_is_not_privileged(conn):
    row = conn.execute("SELECT rolsuper, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname = %s", (db.APP_ROLE,)).fetchone()
    assert row == {"rolsuper": False, "rolbypassrls": False, "rolcanlogin": False}


def test_force_and_enable_are_on_for_every_table(conn):
    for table in db.USER_TABLES:
        row = conn.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid = %s::regclass", (table,)
        ).fetchone()
        assert row == {"relrowsecurity": True, "relforcerowsecurity": True}


def test_init_db_is_safe_to_repeat(conn):
    db.init_db(conn)
    db.init_db(conn)
    db.act_as(conn, A)
    db.insert_expense(conn, A, expense())


def test_delete_user_data_only_touches_that_user(two_users):
    db.act_as(two_users, A)
    db.delete_user_data(two_users, A)
    two_users.execute("RESET ROLE")
    for table in db.USER_TABLES:
        rows = two_users.execute(f"SELECT user_id::text AS u FROM {table}").fetchall()
        assert [r["u"] for r in rows] == [B]
