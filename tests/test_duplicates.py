import pytest

from core.duplicates import find_duplicates


USER = "00000000-0000-0000-0000-00000000000a"
OTHER_USER = "00000000-0000-0000-0000-00000000000b"


def add(conn, merchant="Safeway", day="2026-10-30", total=23.47, file_hash=None, user=USER):
    return conn.execute(
        "INSERT INTO expenses (user_id, merchant, date, total, category, category_source, file_hash, created_at) "
        "VALUES (%s, %s, %s, %s, 'Groceries', 'rule', %s, '2026-10-31 12:00:00+00') RETURNING id",
        (user, merchant, day, total, file_hash),
    ).fetchone()["id"]


def test_exact_hash_match(conn):
    expense_id = add(conn, file_hash="abc")
    warnings = find_duplicates(conn, USER, file_hash="abc")
    assert [(w.kind, w.expense_id) for w in warnings] == [("exact", expense_id)]
    assert "already added this file on 2026-10-31" in warnings[0].message


def test_different_hash_is_not_exact(conn):
    add(conn, file_hash="abc")
    assert find_duplicates(conn, USER, file_hash="xyz") == []


def test_likely_match(conn):
    expense_id = add(conn)
    warnings = find_duplicates(conn, USER, merchant="SAFEWAY", day="2026-10-30", total=23.47)
    assert [(w.kind, w.expense_id) for w in warnings] == [("likely", expense_id)]
    assert warnings[0].summary == "Safeway, 2026-10-30, $23.47"


@pytest.mark.parametrize("total, found", [(23.48, True), (23.46, True), (23.49, False), (23.45, False)])
def test_likely_total_tolerance(conn, total, found):
    add(conn)
    assert bool(find_duplicates(conn, USER, merchant="Safeway", day="2026-10-30", total=total)) is found


def test_same_merchant_different_date_is_not_a_duplicate(conn):
    add(conn)
    assert find_duplicates(conn, USER, merchant="Safeway", day="2026-10-29", total=23.47) == []


def test_different_merchant_same_day_and_total_is_not_a_duplicate(conn):
    add(conn)
    assert find_duplicates(conn, USER, merchant="Target", day="2026-10-30", total=23.47) == []


def test_store_number_does_not_hide_a_duplicate(conn):
    add(conn, merchant="Safeway #1234")
    assert find_duplicates(conn, USER, merchant="Safeway", day="2026-10-30", total=23.47)


def test_exact_match_is_not_repeated_as_likely(conn):
    add(conn, file_hash="abc")
    warnings = find_duplicates(conn, USER, file_hash="abc", merchant="Safeway", day="2026-10-30", total=23.47)
    assert [w.kind for w in warnings] == ["exact"]


def test_expense_being_edited_does_not_match_itself(conn):
    expense_id = add(conn, file_hash="abc")
    assert find_duplicates(conn, USER, "abc", "Safeway", "2026-10-30", 23.47, exclude_id=expense_id) == []


def test_missing_fields_find_nothing(conn):
    add(conn)
    assert find_duplicates(conn, USER) == []
    assert find_duplicates(conn, USER, merchant=None, day="2026-10-30", total=23.47) == []


def test_another_users_expenses_are_never_duplicates(conn):
    add(conn, file_hash="abc", user=OTHER_USER)
    assert find_duplicates(conn, USER, "abc", "Safeway", "2026-10-30", 23.47) == []
