from datetime import date

import pytest

from core import dashboard
from core.models import Settings

TODAY = date(2026, 11, 14)
next_id = iter(range(1, 10_000))


def row(day: str, total: float, category: str = "Other", merchant: str = "Shop", currency: str = "USD", synthetic: bool = False) -> dict:
    return {"id": next(next_id), "merchant": merchant, "date": day, "total": total, "currency": currency, "category": category, "is_synthetic": synthetic}


def build(rows, settings=None, today=TODAY, **options):
    return dashboard.build(rows, settings or Settings(), today, **options)


def test_nothing_saved_yet_doesnt_crash():
    result = build([])
    assert (result["spent"], result["expense_count"], result["average_daily"]) == (0, 0, 0)
    assert result["budget"] is None and result["comparison"] is None
    assert result["categories"]["rows"] == [] and result["top"]["rows"] == []
    assert len(result["trend"]["points"]) == 1
    assert result["insights_message"]


def test_budget_and_daily_numbers():
    result = build([row("2026-11-02", 70), row("2026-11-10", 70)], Settings(monthly_budget=500))
    assert result["spent"] == 140
    assert result["average_daily"] == 10
    assert result["period"]["days_left"] == 16
    assert result["budget"] == {"budget": 500, "spent": 140, "remaining": 360, "over": 0, "safe_per_day": 22.5}


def test_over_budget():
    budget = build([row("2026-11-02", 600)], Settings(monthly_budget=500))["budget"]
    assert (budget["over"], budget["safe_per_day"], budget["remaining"]) == (100, 0, -100)


def test_last_day_of_the_period_doesnt_divide_by_zero():
    budget = build([row("2026-11-02", 100)], Settings(monthly_budget=500), date(2026, 11, 30))["budget"]
    assert budget["safe_per_day"] == 400


def test_categories_are_sorted_with_shares():
    rows = build([row("2026-11-02", 25, "Fun"), row("2026-11-03", 75, "Food")])["categories"]["rows"]
    assert rows == [{"category": "Food", "total": 75, "share": 0.75}, {"category": "Fun", "total": 25, "share": 0.25}]


def test_comparison_only_counts_the_same_days_of_last_period():
    result = build([
        row("2026-11-05", 60, "Food"),
        row("2026-10-14", 40, "Food"),  # inside the fair window
        row("2026-10-15", 500, "Food"),  # a day past it, so left out
        row("2026-10-03", 10, "Gone"),
    ])["comparison"]
    assert result["label"] == "Nov 1–14 vs Oct 1–14"
    assert result["rows"] == [
        {"category": "Food", "current": 60, "previous": 40, "change": 20, "change_ratio": 0.5},
        {"category": "Gone", "current": 0, "previous": 10, "change": -10, "change_ratio": -1},
    ]


def test_comparison_stays_within_a_shorter_previous_period():
    result = build([row("2026-02-28", 40), row("2026-03-02", 60)], today=date(2026, 3, 31))["comparison"]
    assert result["label"] == "Mar 1–31 vs Feb 1–28"
    assert result["rows"][0]["previous"] == 40


def test_comparison_follows_a_custom_cycle():
    result = build([row("2026-10-16", 60), row("2026-09-20", 30)], Settings(cycle_start_day=15), date(2026, 10, 20))["comparison"]
    assert result["label"] == "Oct 15–20 vs Sep 15–20"
    assert result["rows"][0]["previous"] == 30


def test_no_comparison_against_a_period_with_no_data():
    assert build([row("2026-11-05", 60), row("2026-10-20", 60)])["comparison"] is None  # Oct 20 is past the window


def test_trend_starts_at_the_first_period_with_data():
    points = build([row("2026-09-05", 30), row("2026-11-05", 60)])["trend"]["points"]
    assert [(p["label"], p["total"], p["in_progress"]) for p in points] == [
        ("Sep", 30, False), ("Oct", 0, False), ("Nov", 60, True),
    ]


def test_trend_is_at_most_six_periods():
    rows = [row(f"2026-{month:02}-05", 10) for month in range(1, 12)]
    assert [p["label"] for p in build(rows)["trend"]["points"]] == ["Jun", "Jul", "Aug", "Sep", "Oct", "Nov"]


def test_top_five_by_amount():
    rows = [row("2026-11-02", amount, merchant=f"M{amount}") for amount in (1, 2, 3, 4, 5, 6, 7)]
    assert [r["merchant"] for r in build(rows)["top"]["rows"]] == ["M7", "M6", "M5", "M4", "M3"]


def test_other_currencies_are_counted_separately_not_added_in():
    result = build([row("2026-11-02", 10), row("2026-11-03", 900, currency="EUR")])
    assert result["spent"] == 10
    assert result["expense_count"] == 1
    assert result["other_currency_count"] == 1
    assert [r["total"] for r in result["top"]["rows"]] == [10]


def test_synthetic_rows_are_labeled_per_section_and_can_be_hidden():
    rows = [row("2026-11-02", 10), row("2026-11-03", 90, "Fun", synthetic=True), row("2026-10-03", 5, synthetic=True)]
    shown = build(rows)
    assert shown["spent"] == 100
    assert shown["any_synthetic"] and shown["categories"]["includes_synthetic"] and shown["top"]["includes_synthetic"]
    assert shown["comparison"]["includes_synthetic"] and shown["trend"]["includes_synthetic"]

    hidden = build(rows, hide_synthetic=True)
    assert hidden["spent"] == 10
    assert hidden["any_synthetic"]  # so the toggle stays available
    assert not hidden["categories"]["includes_synthetic"] and not hidden["trend"]["includes_synthetic"]
    assert hidden["comparison"] is None


def test_real_only_data_isnt_labeled_synthetic():
    result = build([row("2026-11-02", 10), row("2026-10-02", 10)])
    assert not result["any_synthetic"] and not result["categories"]["includes_synthetic"]


@pytest.mark.parametrize("count, shows_message", [(4, True), (5, False)])
def test_insights_message_threshold(count, shows_message):
    result = build([row("2026-11-02", 1) for _ in range(count)])
    assert bool(result["insights_message"]) is shows_message
