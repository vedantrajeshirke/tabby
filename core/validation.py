"""Validation rules: an extraction or edited form values -> a list of issues."""
from datetime import date

from core.models import Extraction, ValidationIssue

AMOUNT_TOLERANCE = 0.05
MAX_AGE_DAYS = 365
BLOCKING_CODES = {"V03", "V04", "V06"}
DOCUMENT_ERRORS = {
    "not_an_expense": ("V01", "This doesn't look like a receipt or payment. Try another file or enter it manually."),
    "unreadable": ("V02", "Couldn't read this image clearly. Retake the photo or enter it manually."),
}


def _error(code: str, field: str | None, message: str) -> ValidationIssue:
    return ValidationIssue(code, "error", field, message)


def _warning(code: str, field: str | None, message: str) -> ValidationIssue:
    return ValidationIssue(code, "warning", field, message)


def _check_total(e: Extraction) -> list[ValidationIssue]:
    if e.total is None:
        return [_error("V03", "total", "Total amount is required. Enter the amount from your receipt.")]
    if e.total <= 0:
        return [_error("V04", "total", "Total must be greater than zero. Enter the amount you paid.")]
    return []


def _parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _check_date(e: Extraction, today: date) -> list[ValidationIssue]:
    day = _parse_date(e.date)
    if day is None:
        return [_warning("V05", "date", "No date found; defaulting to today. Change it if that's wrong.")]
    if day > today:
        return [_error("V06", "date", "Date is in the future. Enter the date of the purchase.")]
    if (today - day).days > MAX_AGE_DAYS:
        return [_warning("V07", "date", "This expense is over a year old. Is the date right?")]
    return []


def _check_amounts(e: Extraction) -> list[ValidationIssue]:
    if e.subtotal is None or e.total is None:
        return []
    computed = round(e.subtotal + (e.tax or 0) + (e.tip or 0), 2)
    if round(abs(computed - e.total), 2) <= AMOUNT_TOLERANCE:
        return []
    message = f"Subtotal + tax + tip = ${computed:.2f} but total is ${e.total:.2f}. Please check the amounts."
    return [_warning("V08", "total", message)]


def _check_currency(e: Extraction) -> list[ValidationIssue]:
    if e.currency and e.currency != "USD":
        message = f"Currency is {e.currency}. Amounts are stored as-is; conversion isn't supported yet."
        return [_warning("V10", "currency", message)]
    return []


def _check_confidence(e: Extraction) -> list[ValidationIssue]:
    return [
        _warning("V11", field, f"Please double-check the {field}.")
        for field, confidence in e.field_confidence.items()
        if confidence == "low"
    ]


def _check_merchant(e: Extraction) -> list[ValidationIssue]:
    return [] if e.merchant else [_warning("V12", "merchant", "Merchant not found; please add one.")]


def validate(e: Extraction, today: date | None = None) -> list[ValidationIssue]:
    """Unusable documents get one clear error, with no pile of missing-field issues after it."""
    if e.document_type in DOCUMENT_ERRORS:
        code, message = DOCUMENT_ERRORS[e.document_type]
        return [_error(code, None, message)]
    return [
        *_check_total(e),
        *_check_date(e, today or date.today()),
        *_check_amounts(e),
        *_check_currency(e),
        *_check_confidence(e),
        *_check_merchant(e),
    ]


def blocks_save(issues: list[ValidationIssue]) -> bool:
    return any(issue.code in BLOCKING_CODES for issue in issues)
