"""All dashboard numbers, worked out on the server. Framework-free; the route calls this."""
from dataclasses import asdict
from datetime import date, timedelta

import pandas as pd

from core import insights, periods
from core.models import Settings

TREND_PERIODS = 6
TOP_EXPENSES = 5
COLUMNS = ["id", "merchant", "date", "total", "category", "is_synthetic"]


def _between(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    return df[(df["date"] >= start.isoformat()) & (df["date"] <= end.isoformat())]


def _has_synthetic(df: pd.DataFrame) -> bool:
    return bool(df["is_synthetic"].any())


def _budget(spent: float, settings: Settings, today: date, end: date) -> dict | None:
    budget = settings.monthly_budget
    if not budget:
        return None
    days_left = periods.days_left(today, end)
    return {
        "budget": budget,
        "spent": spent,
        "remaining": round(budget - spent, 2),
        "over": round(max(spent - budget, 0), 2),
        "safe_per_day": round(max(budget - spent, 0) / max(days_left, 1), 2),  # the last day still has today
    }


def _categories(current: pd.DataFrame, spent: float) -> list[dict]:
    totals = current.groupby("category")["total"].sum().sort_values(ascending=False)
    return [{"category": name, "total": round(float(total), 2), "share": round(float(total) / spent, 4)} for name, total in totals.items()]


def _comparison(current: pd.DataFrame, previous: pd.DataFrame, today: date, start: date, fair_start: date, fair_end: date) -> dict | None:
    if previous.empty:  # never compare against a period with no data
        return None
    now = current.groupby("category")["total"].sum()
    before = previous.groupby("category")["total"].sum()
    rows = []
    for name in now.index.union(before.index):
        amount, earlier = round(float(now.get(name, 0)), 2), round(float(before.get(name, 0)), 2)
        rows.append({
            "category": name,
            "current": amount,
            "previous": earlier,
            "change": round(amount - earlier, 2),
            "change_ratio": round((amount - earlier) / earlier, 4) if earlier else None,
        })
    rows.sort(key=lambda row: (-max(row["current"], row["previous"]), row["category"]))
    return {
        "label": f"{periods.short_range(start, today)} vs {periods.short_range(fair_start, fair_end)}",
        "rows": rows,
        "includes_synthetic": _has_synthetic(current) or _has_synthetic(previous),
    }


def _trend(df: pd.DataFrame, today: date, cycle_start_day: int) -> dict:
    points = []
    for period in reversed(periods.recent_periods(today, cycle_start_day, TREND_PERIODS)):
        start, end = date.fromisoformat(period["start"]), date.fromisoformat(period["end"])
        rows = _between(df, start, end)
        points.append({
            "label": f"{start:%b}" if start.day == 1 else f"{start:%b} {start.day}",
            "full_label": period["label"],
            "total": round(float(rows["total"].sum()), 2),
            "count": len(rows),
            "in_progress": today <= end,
        })
    first = next((i for i, point in enumerate(points) if point["count"]), len(points) - 1)  # before any data isn't $0 spent
    return {"points": points[first:], "history": _history(df, today, cycle_start_day), "includes_synthetic": _has_synthetic(df)}


def _history(df: pd.DataFrame, today: date, cycle_start_day: int) -> list[dict]:
    """The current period and every earlier one with expenses, newest first."""
    current_start, current_end = periods.current_period(today, cycle_start_day)
    starts = {current_start}
    for day in df["date"].unique():
        starts.add(periods.current_period(min(date.fromisoformat(day), today), cycle_start_day)[0])
    found = []
    for start in sorted(starts, reverse=True):
        start, end = periods.current_period(start, cycle_start_day)
        rows = _between(df, start, end)
        found.append({
            "start": start.isoformat(),
            "full_label": periods.period_label(start, end),
            "total": round(float(rows["total"].sum()), 2),
            "count": len(rows),
            "in_progress": start == current_start,
        })
    return found


def build(rows: list[dict], settings: Settings, today: date, hide_synthetic: bool = False, period_day: date | None = None) -> dict:
    """Numbers for the period containing `period_day`, or the current one. A past period is seen as finished."""
    everything = pd.DataFrame(rows, columns=COLUMNS).astype({"total": "float64", "is_synthetic": "bool"})
    current_start, _ = periods.current_period(today, settings.cycle_start_day)
    start, end = periods.current_period(min(period_day or today, today), settings.cycle_start_day)
    is_current = start == current_start
    as_of = today if is_current else end
    any_synthetic = _has_synthetic(everything)

    df = everything
    if hide_synthetic:
        df = df[~df["is_synthetic"]]

    current = _between(df, start, end)
    spent = round(float(current["total"].sum()), 2)
    elapsed = periods.days_elapsed(as_of, start, end)
    previous_start, previous_end = periods.previous_period(as_of, settings.cycle_start_day)
    fair_end = min(previous_start + timedelta(days=elapsed - 1), previous_end)  # Nov 1–14 against Oct 1–14
    fair_previous = _between(df, previous_start, fair_end)
    top = current.sort_values(["total", "id"], ascending=False).head(TOP_EXPENSES)
    # Budgets aren't stored per period, and insights talk about the period still under way.
    full_previous = _between(df, previous_start, previous_end)
    window = insights.Window(today, start, end, previous_start, fair_end)
    found = insights.generate(current, fair_previous, full_previous, settings, window) if is_current else []

    return {
        "period": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "label": periods.period_label(start, end),
            "days_elapsed": elapsed,
            "days_left": periods.days_left(as_of, end),
            "is_current": is_current,
            "length": periods.period_length(start, end),
        },
        "expense_count": len(current),
        "any_synthetic": any_synthetic,
        "spent": spent,
        "average_daily": round(spent / elapsed, 2),
        "budget": _budget(spent, settings, today, end) if is_current else None,
        "insights": [asdict(insight) for insight in found],
        "insights_message": insights.NOT_ENOUGH if is_current and len(current) < insights.MIN_EXPENSES else None,
        "categories": {"rows": _categories(current, spent) if spent else [], "includes_synthetic": _has_synthetic(current)},
        "comparison": _comparison(current, fair_previous, as_of, start, previous_start, fair_end),
        "trend": _trend(df, today, settings.cycle_start_day),
        "top": {
            "rows": [
                {"id": int(row.id), "merchant": row.merchant, "date": row.date, "category": row.category, "total": float(row.total), "is_synthetic": bool(row.is_synthetic)}
                for row in top.itertuples()
            ],
            "includes_synthetic": _has_synthetic(top),
        },
    }
