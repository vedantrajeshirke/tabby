from datetime import date

import pandas as pd
import pytest

from core import insights
from core.dashboard import COLUMNS
from core.models import Settings

TODAY = date(2026, 11, 15)
WINDOW = insights.Window(TODAY, date(2026, 11, 1), date(2026, 11, 30))


def frame(*rows: tuple) -> pd.DataFrame:
    """Rows of (merchant, total, category)."""
    records = [
        {"id": i, "merchant": m, "date": "2026-11-05", "total": t, "currency": "USD", "category": c, "is_synthetic": False}
        for i, (m, t, c) in enumerate(rows)
    ]
    return pd.DataFrame(records, columns=COLUMNS).astype({"total": "float64"})


# Budget pace


def test_budget_pace_needs_a_budget_and_three_days():
    current = frame(("A", 50, "Other"))
    assert insights.budget_pace(current, Settings(), WINDOW) is None
    second_day = insights.Window(date(2026, 11, 2), WINDOW.start, WINDOW.end)
    assert insights.budget_pace(current, Settings(monthly_budget=500), second_day) is None
    third_day = insights.Window(date(2026, 11, 3), WINDOW.start, WINDOW.end)
    assert insights.budget_pace(current, Settings(monthly_budget=500), third_day) is not None


def test_budget_pace_on_track_gives_safe_daily_amount_and_greets():
    found = insights.budget_pace(frame(("A", 100, "Other")), Settings("Sam", 500), WINDOW)
    assert found.text == "Hi Sam, you've spent $100.00 of your $500.00 budget with 15 days left, about $26.67/day to stay on track."
    assert found.tone == "neutral"


def test_budget_pace_warns_about_the_projection():
    found = insights.budget_pace(frame(("A", 400, "Other")), Settings("", 500), WINDOW)
    assert found.text.startswith("You've spent $400.00")
    assert "At this pace you'll be about $300.00 over budget." in found.text
    assert found.tone == "warning"


def test_budget_pace_when_already_over_and_on_the_last_day():
    last_day = insights.Window(date(2026, 11, 30), WINDOW.start, WINDOW.end)
    found = insights.budget_pace(frame(("A", 600, "Other")), Settings("", 500), last_day)
    assert "with today left, $100.00 over." in found.text
    assert found.tone == "warning"


# Category change


def test_category_change_thresholds_are_inclusive():
    before = frame(("A", 100, "Food"))
    assert insights.category_change(frame(("A", 120, "Food")), before, 1).data["diff"] == 20
    assert insights.category_change(frame(("A", 119.99, "Food")), before, 1) is None  # under $20
    assert insights.category_change(frame(("A", 225, "Food")), frame(("A", 200, "Food")), 1) is None  # $25, but under 20%


def test_category_change_picks_the_largest_rise_and_says_so():
    found = insights.category_change(
        frame(("A", 150, "Food"), ("B", 90, "Fun")), frame(("A", 100, "Food"), ("B", 30, "Fun")), 1
    )
    assert found.text == "Fun: $90.00 so far, $60.00 more than this point last month."


def test_category_change_says_period_for_custom_cycles():
    assert "last period" in insights.category_change(frame(("A", 150, "Food")), frame(("A", 100, "Food")), 15).text


def test_category_change_never_compares_against_no_data():
    assert insights.category_change(frame(("A", 150, "Food")), frame(), 1) is None


def test_category_change_counts_a_new_category():
    found = insights.category_change(frame(("A", 25, "New")), frame(("A", 100, "Food")), 1)
    assert found.data["category"] == "New"


# Frequent merchant


def test_frequent_merchant_fires_at_three_visits_ignoring_case():
    assert insights.frequent_merchant(frame(("Cafe", 5, "F"), ("CAFE", 5, "F"))) is None
    found = insights.frequent_merchant(frame(("Cafe", 5, "F"), ("CAFE", 5, "F"), ("cafe", 5.5, "F")))
    assert found.text == "You've been to Cafe 3 times this period ($15.50)."


def test_frequent_merchant_chooses_the_most_money_and_skips_unknown():
    found = insights.frequent_merchant(frame(*[("Small", 1, "F")] * 4, *[("Big", 50, "F")] * 3, *[("Unknown merchant", 99, "F")] * 5))
    assert found.data["merchant"] == "Big"


# Small purchases


def test_small_purchases_thresholds():
    five = [("A", 5, "F")] * 5
    assert insights.small_purchases(frame(*five)).text == "Purchases under $10 added up to $25.00 across 5 items."
    assert insights.small_purchases(frame(*five[:4])) is None  # too few
    assert insights.small_purchases(frame(*[("A", 4.99, "F")] * 5)) is None  # under $25
    assert insights.small_purchases(frame(*[("A", 10, "F")] * 5)) is None  # $10 isn't under $10


# Ranking


def make(kind: str, score: float) -> insights.Insight:
    return insights.Insight(kind, kind, score, "neutral")


def test_budget_pace_is_pinned_then_by_impact_and_capped_at_three():
    ranked = insights.rank([make("a", 1), make("budget_pace", 0), None, make("b", 9), make("c", 5)])
    assert [i.type for i in ranked] == ["budget_pace", "b", "c"]


@pytest.mark.parametrize("count, expected", [(4, False), (5, True)])
def test_no_insights_until_five_expenses(count, expected):
    current = frame(*[("A", 100, "Other")] * count)
    assert bool(insights.generate(current, frame(), Settings(monthly_budget=500), WINDOW)) is expected
