"""Budget-cycle periods. With a start day of 1 these are calendar months."""
from datetime import date, timedelta


def _shift_month(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return day.replace(year=index // 12, month=index % 12 + 1)  # start days stop at 28, so the day always exists


def current_period(today: date, cycle_start_day: int) -> tuple[date, date]:
    start = today.replace(day=cycle_start_day)
    if today.day < cycle_start_day:
        start = _shift_month(start, -1)
    return start, _shift_month(start, 1) - timedelta(days=1)


def previous_period(today: date, cycle_start_day: int) -> tuple[date, date]:
    start, _ = current_period(today, cycle_start_day)
    return current_period(start - timedelta(days=1), cycle_start_day)


def period_length(start: date, end: date) -> int:
    return (end - start).days + 1


def days_elapsed(today: date, start: date, end: date) -> int:
    """Days so far, counting today."""
    return period_length(start, min(today, end))


def days_left(today: date, end: date) -> int:
    """Days remaining, not counting today."""
    return max((end - today).days, 0)


def period_label(start: date, end: date) -> str:
    if start.day == 1:
        return f"{start:%B %Y}"
    return f"{start:%b} {start.day}, {start:%Y} – {end:%b} {end.day}, {end:%Y}"


def recent_periods(today: date, cycle_start_day: int, count: int = 12) -> list[dict]:
    """The current period and the ones before it, newest first."""
    periods = []
    day = today
    for _ in range(count):
        start, end = current_period(day, cycle_start_day)
        periods.append({"start": start.isoformat(), "end": end.isoformat(), "label": period_label(start, end)})
        day = start - timedelta(days=1)
    return periods
