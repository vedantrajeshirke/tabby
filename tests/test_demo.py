from datetime import date

import pytest

from core import db, demo, periods
from tests.test_api_expenses import USER_A, USER_B, api, form, post_expense  # noqa: F401

TODAY = date(2026, 11, 14)


@pytest.mark.parametrize("start_day", [1, 15, 28])
def test_every_row_is_synthetic_in_the_past_and_covers_four_periods(start_day):
    rows = demo.generate(TODAY, start_day)
    assert all(row.is_synthetic for row in rows)
    assert all(row.date <= TODAY.isoformat() for row in rows)
    assert all(row.total > 0 for row in rows)
    assert len({row.date[:7] for row in rows}) >= 3
    assert len(rows) > 50


@pytest.mark.parametrize("today, start_day", [(date(2026, 11, 1), 1), (date(2026, 11, 2), 1), (date(2026, 11, 15), 15), (date(2026, 11, 30), 1)])
def test_the_current_period_always_has_enough_to_show(today, start_day):
    start, _ = periods.current_period(today, start_day)
    rows = [row for row in demo.generate(today, start_day) if row.date >= start.isoformat()]
    assert len(rows) >= demo.MIN_IN_PERIOD
    assert all(row.date <= today.isoformat() for row in rows)


def test_the_same_inputs_give_the_same_rows():
    assert demo.generate(TODAY, 1) == demo.generate(TODAY, 1)


def test_categories_are_real_ones():
    import json
    from core.config import CATEGORIES_PATH

    allowed = set(json.loads(CATEGORIES_PATH.read_text())["categories"])
    assert {row.category for row in demo.generate(TODAY, 1)} <= allowed


def test_loading_twice_replaces_rather_than_doubles(api):  # noqa: F811
    first = api.post("/api/demo-data").json()["added"]
    assert first > 0
    assert api.post("/api/demo-data").json()["added"] == first
    assert api.db.execute("SELECT count(*) AS n FROM expenses").fetchone()["n"] == first


def test_removing_leaves_real_expenses_alone(api):  # noqa: F811
    real = post_expense(api).json()["expense"]["id"]
    added = api.post("/api/demo-data").json()["added"]
    assert api.delete("/api/demo-data").json() == {"removed": added}
    remaining = api.db.execute("SELECT id FROM expenses").fetchall()
    assert [row["id"] for row in remaining] == [real]


def test_a_real_expense_is_never_marked_synthetic_or_replaced_by_loading(api):  # noqa: F811
    real = post_expense(api).json()["expense"]
    assert real["is_synthetic"] is False
    api.post("/api/demo-data")
    assert api.get(f"/api/expenses/{real['id']}").status_code == 200


def test_demo_data_never_crosses_users(api):  # noqa: F811
    added = api.post("/api/demo-data").json()["added"]
    api.state["user"] = USER_B
    assert api.get("/api/expenses").json() == []
    assert api.delete("/api/demo-data").json() == {"removed": 0}
    api.state["user"] = USER_A
    assert len(api.get("/api/expenses?limit=1000").json()) == added


def test_demo_rows_are_labeled_on_the_dashboard(api):  # noqa: F811
    api.post("/api/demo-data")
    result = api.get("/api/dashboard").json()
    assert result["any_synthetic"] is True
    assert api.get("/api/dashboard?hide_synthetic=true").json()["spent"] == 0


def test_demo_data_follows_the_users_cycle(api, conn):  # noqa: F811
    api.put("/api/settings", json={"cycle_start_day": 15})
    assert api.post("/api/demo-data").status_code == 200
    assert db.load_settings(conn, USER_A).cycle_start_day == 15
