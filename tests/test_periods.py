from datetime import date

import pytest

from core import periods


@pytest.mark.parametrize(
    "today, start_day, start, end",
    [
        (date(2026, 10, 15), 1, date(2026, 10, 1), date(2026, 10, 31)),
        (date(2026, 10, 15), 15, date(2026, 10, 15), date(2026, 11, 14)),
        (date(2026, 10, 14), 15, date(2026, 9, 15), date(2026, 10, 14)),
        (date(2026, 1, 5), 20, date(2025, 12, 20), date(2026, 1, 19)),
        (date(2026, 12, 25), 20, date(2026, 12, 20), date(2027, 1, 19)),
        (date(2028, 2, 29), 1, date(2028, 2, 1), date(2028, 2, 29)),
        (date(2026, 3, 1), 28, date(2026, 2, 28), date(2026, 3, 27)),
    ],
)
def test_current_period(today, start_day, start, end):
    assert periods.current_period(today, start_day) == (start, end)


def test_previous_period_ends_the_day_before_the_current_one():
    assert periods.previous_period(date(2026, 1, 5), 1) == (date(2025, 12, 1), date(2025, 12, 31))
    assert periods.previous_period(date(2026, 1, 5), 20) == (date(2025, 11, 20), date(2025, 12, 19))


def test_day_counts():
    start, end = date(2026, 10, 1), date(2026, 10, 31)
    assert periods.period_length(start, end) == 31
    assert periods.days_elapsed(date(2026, 10, 1), start, end) == 1
    assert periods.days_elapsed(date(2026, 11, 3), start, end) == 31
    assert periods.days_left(date(2026, 10, 30), end) == 1
    assert periods.days_left(date(2026, 11, 3), end) == 0


def test_labels():
    assert periods.period_label(date(2026, 10, 1), date(2026, 10, 31)) == "October 2026"
    assert periods.period_label(date(2026, 12, 15), date(2027, 1, 14)) == "Dec 15, 2026 – Jan 14, 2027"


@pytest.mark.parametrize("start_day", [1, 15, 28])
def test_recent_periods_are_contiguous_and_newest_first(start_day):
    found = periods.recent_periods(date(2026, 3, 10), start_day, 14)
    assert len(found) == 14
    assert periods.current_period(date(2026, 3, 10), start_day)[0].isoformat() == found[0]["start"]
    for newer, older in zip(found, found[1:]):
        assert date.fromisoformat(older["end"]).toordinal() + 1 == date.fromisoformat(newer["start"]).toordinal()
