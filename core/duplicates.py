"""Duplicate detection: exact file matches and likely matching expenses."""
import sqlite3
from dataclasses import dataclass

from core import db
from core.categorize import normalize_merchant

TOTAL_TOLERANCE = 0.01


@dataclass
class DuplicateWarning:
    kind: str  # exact | likely
    expense_id: int
    message: str
    summary: str


def _summary(row: sqlite3.Row) -> str:
    return f"{row['merchant']}, {row['date']}, ${row['total']:.2f}"


def _is_same_expense(row: sqlite3.Row, merchant: str, total: float) -> bool:
    same_total = round(abs(row["total"] - total), 2) <= TOTAL_TOLERANCE
    return same_total and normalize_merchant(row["merchant"]) == normalize_merchant(merchant)


def find_duplicates(
    conn: sqlite3.Connection,
    file_hash: str | None = None,
    merchant: str | None = None,
    day: str | None = None,
    total: float | None = None,
    exclude_id: int | None = None,
) -> list[DuplicateWarning]:
    """Exact matches come first. An expense already flagged as exact isn't repeated as likely."""
    warnings: list[DuplicateWarning] = []
    seen = {exclude_id}
    if file_hash:
        for row in db.expenses_with_hash(conn, file_hash):
            if row["id"] not in seen:
                seen.add(row["id"])
                added = row["created_at"][:10]
                message = f"You already added this file on {added}. Discard this one, or continue if it's a separate expense."
                warnings.append(DuplicateWarning("exact", row["id"], message, _summary(row)))
    if merchant and day and total is not None:
        for row in db.expenses_on_date(conn, day):
            if row["id"] not in seen and _is_same_expense(row, merchant, total):
                seen.add(row["id"])
                message = "Looks similar to an expense you already saved. Discard this one, or continue if it's a separate expense."
                warnings.append(DuplicateWarning("likely", row["id"], message, _summary(row)))
    return warnings
