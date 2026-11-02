"""Synthetic student spending. Every row is marked is_synthetic, so it can be labeled and removed."""
import random
from datetime import date, timedelta

import psycopg

from core import db, periods
from core.models import Expense

PREVIOUS_PERIODS = 3
RENT = 650.00
MIN_IN_PERIOD = 6  # enough for the dashboard's charts and insights

# (merchant, category, payment, low, high, visits a period)
REGULAR = [
    ("Trader Joe's", "Groceries", "card", 22, 68, 5),
    ("H Mart", "Groceries", "card", 18, 55, 2),
    ("Starbucks", "Restaurants & Cafes", "card", 4, 9, 6),
    ("Chipotle", "Restaurants & Cafes", "card", 11, 17, 3),
    ("DoorDash", "Food Delivery", "card", 18, 36, 3),
    ("Uber", "Transport", "card", 9, 26, 4),
]
MONTHLY = [
    ("Rent transfer", "Transfers to People", "zelle", RENT, 2),
    ("Netflix", "Subscriptions", "card", 15.49, 5),
    ("Spotify", "Subscriptions", "card", 10.99, 8),
]


def _expense(merchant: str, category: str, payment: str, day: date, total: float) -> Expense:
    return Expense(
        merchant=merchant,
        date=day.isoformat(),
        total=round(total, 2),
        category=category,
        category_source="rule",
        payment_method=payment,
        document_type="payment_screenshot" if payment == "zelle" else "receipt",
        is_synthetic=True,
    )


def generate(today: date, cycle_start_day: int) -> list[Expense]:
    """The current period so far and the ones before it. The same inputs give the same rows."""
    expenses = []
    day = today
    for _ in range(PREVIOUS_PERIODS + 1):
        start, end = periods.current_period(day, cycle_start_day)
        rng = random.Random(start.isoformat())
        last_day = min(end, today)
        span = (last_day - start).days
        mood = rng.uniform(0.85, 1.2)  # some months cost more than others
        for merchant, category, payment, low, high, visits in REGULAR:
            for _ in range(visits):
                offset = rng.randint(0, periods.period_length(start, end) - 1)
                if offset <= span:
                    expenses.append(_expense(merchant, category, payment, start + timedelta(days=offset), rng.uniform(low, high) * mood))
        for merchant, category, payment, total, offset in MONTHLY:
            if offset <= span:
                expenses.append(_expense(merchant, category, payment, start + timedelta(days=offset), total))
        # Early in a period few rows have happened yet, and the dashboard still needs enough to show.
        in_period = sum(row.date >= start.isoformat() for row in expenses)
        for index in range(max(MIN_IN_PERIOD - in_period, 0)):
            merchant, category, payment, low, high, _ = REGULAR[index % len(REGULAR)]
            expenses.append(_expense(merchant, category, payment, start + timedelta(days=rng.randint(0, span)), rng.uniform(low, high)))
        day = start - timedelta(days=1)
    return expenses


def load(conn: psycopg.Connection, user_id: str, today: date) -> int:
    """Replaces any earlier demo rows, so loading twice doesn't double everything. Real rows aren't touched."""
    expenses = generate(today, db.load_settings(conn, user_id).cycle_start_day)
    with conn.transaction():
        db.delete_synthetic(conn, user_id)
        for expense in expenses:
            db.insert_expense(conn, user_id, expense)
    return len(expenses)
