"""Insight generators. Each is a pure function, and every number in the text comes from the data."""
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from core import periods
from core.categorize import normalize_merchant
from core.confirm import UNKNOWN_MERCHANT
from core.models import Settings

MIN_EXPENSES = 5
MAX_SHOWN = 3
BUDGET_PACE_MIN_DAYS = 3
CATEGORY_CHANGE_MIN_DAYS = 7  # a day or two of spending says nothing about a month
CATEGORY_CHANGE_MIN_DOLLARS = 20
LAST_TOTAL_MIN_DOLLARS = 20
CATEGORY_CHANGE_MIN_RATIO = 0.20
FREQUENT_VISITS = 3
SMALL_PURCHASE_UNDER = 10
SMALL_PURCHASE_MIN_COUNT = 5
SMALL_PURCHASE_MIN_TOTAL = 25
NOT_ENOUGH = "Add a few more expenses to see insights."


@dataclass
class Insight:
    type: str
    text: str
    score: float  # $ impact, used for ranking
    tone: str  # neutral | warning | positive
    data: dict = field(default_factory=dict)


@dataclass
class Window:
    today: date
    start: date
    end: date
    fair_start: date  # the same days of the previous period
    fair_end: date


def money(amount: float) -> str:
    return f"${amount:,.2f}"


def _days(count: int) -> str:
    return "today left" if count == 0 else f"{count} day{'' if count == 1 else 's'} left"


def budget_pace(current: pd.DataFrame, settings: Settings, window: Window) -> Insight | None:
    budget = settings.monthly_budget
    elapsed = periods.days_elapsed(window.today, window.start, window.end)
    if not budget or elapsed < BUDGET_PACE_MIN_DAYS:
        return None
    spent = float(current["total"].sum())
    days_left = periods.days_left(window.today, window.end)
    projected = spent / elapsed * periods.period_length(window.start, window.end)
    safe_per_day = max(budget - spent, 0) / max(days_left, 1)
    opening = f"Hi {settings.name}, you've" if settings.name else "You've"
    text = f"{opening} spent {money(spent)} of your {money(budget)} budget with {_days(days_left)}"
    if spent > budget:
        text += f", {money(spent - budget)} over."
        tone = "warning"
    else:
        text += f", about {money(safe_per_day)}/day to stay on track."
        tone = "neutral"
        if projected > budget:
            text += f" At this pace you'll be about {money(projected - budget)} over budget."
            tone = "warning"
    data = {"spent": spent, "budget": budget, "days_left": days_left, "safe_per_day": safe_per_day, "projected": projected}
    return Insight("budget_pace", text, spent, tone, data)


def category_change(current: pd.DataFrame, previous: pd.DataFrame, window: Window) -> Insight | None:
    """The largest rise. `previous` is the fair window: the same number of days into the last period."""
    if periods.days_elapsed(window.today, window.start, window.end) < CATEGORY_CHANGE_MIN_DAYS:
        return None
    if previous.empty:  # never compare against a period with no data
        return None
    now = current.groupby("category")["total"].sum()
    before = previous.groupby("category")["total"].sum()
    best = None
    for category, amount in now.items():
        earlier = float(before.get(category, 0))
        diff = round(float(amount) - earlier, 2)
        rose_enough = earlier == 0 or diff / earlier >= CATEGORY_CHANGE_MIN_RATIO
        if diff >= CATEGORY_CHANGE_MIN_DOLLARS and rose_enough and (best is None or diff > best[2]):
            best = (category, float(amount), diff, earlier)
    if best is None:
        return None
    category, amount, diff, earlier = best
    now_range = periods.short_range(window.start, window.today)
    then_range = periods.short_range(window.fair_start, window.fair_end)
    text = f"{category}: {money(amount)} so far ({now_range}), {money(diff)} more than {then_range}."
    return Insight("category_change", text, diff, "warning", {"category": category, "current": amount, "previous": earlier, "diff": diff})


def category_last_total(current: pd.DataFrame, full_previous: pd.DataFrame, cycle_start_day: int, skip: str | None = None) -> Insight | None:
    """A plain reference point, with no claim about being ahead or behind. Skips a category already called out."""
    now = current.groupby("category")["total"].sum().sort_values(ascending=False)
    before = full_previous.groupby("category")["total"].sum()
    for category, amount in now.items():
        earlier = float(before.get(category, 0))
        if category != skip and earlier > 0 and amount >= LAST_TOTAL_MIN_DOLLARS:
            last = "Last month's" if cycle_start_day == 1 else "Last period's"
            text = f"You've spent {money(float(amount))} on {category} so far. {last} total was {money(earlier)}."
            return Insight("category_last_total", text, float(amount), "neutral", {"category": category, "current": float(amount), "previous_total": earlier})
    return None


def frequent_merchant(current: pd.DataFrame) -> Insight | None:
    known = current[current["merchant"] != UNKNOWN_MERCHANT]
    if known.empty:
        return None
    visits = known.groupby(known["merchant"].map(normalize_merchant), sort=False)
    frequent = [(float(group["total"].sum()), group) for _, group in visits if len(group) >= FREQUENT_VISITS]
    if not frequent:
        return None
    total, group = max(frequent, key=lambda found: found[0])
    merchant, count = group["merchant"].iloc[0], len(group)
    text = f"You've been to {merchant} {count} times this period ({money(total)})."
    return Insight("frequent_merchant", text, total, "neutral", {"merchant": merchant, "count": count, "total": total})


def small_purchases(current: pd.DataFrame) -> Insight | None:
    small = current[current["total"] < SMALL_PURCHASE_UNDER]
    total = round(float(small["total"].sum()), 2)
    if len(small) < SMALL_PURCHASE_MIN_COUNT or total < SMALL_PURCHASE_MIN_TOTAL:
        return None
    text = f"Purchases under ${SMALL_PURCHASE_UNDER} added up to {money(total)} across {len(small)} items."
    return Insight("small_purchases", text, total, "neutral", {"total": total, "count": len(small)})


def rank(found: list[Insight | None]) -> list[Insight]:
    """Budget pace is pinned first; the rest go by dollar impact."""
    present = [insight for insight in found if insight is not None]
    pinned = [i for i in present if i.type == "budget_pace"]
    rest = sorted((i for i in present if i.type != "budget_pace"), key=lambda i: i.score, reverse=True)
    return (pinned + rest)[:MAX_SHOWN]


def generate(current: pd.DataFrame, fair_previous: pd.DataFrame, full_previous: pd.DataFrame, settings: Settings, window: Window) -> list[Insight]:
    if len(current) < MIN_EXPENSES:
        return []
    change = category_change(current, fair_previous, window)
    return rank([
        budget_pace(current, settings, window),
        change,
        category_last_total(current, full_previous, settings.cycle_start_day, change.data["category"] if change else None),
        frequent_merchant(current),
        small_purchases(current),
    ])
