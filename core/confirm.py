"""Pure logic behind the confirm screen: applying form edits and building the saved expense."""
import json
from dataclasses import dataclass, replace
from datetime import date

from core.models import Expense, Extraction, ValidationIssue
from core.redact import redact_value
from core.validation import validate

UNKNOWN_MERCHANT = "Unknown merchant"  # on expenses saved before a merchant was required
UNUSABLE_DOCUMENT_TYPES = {"unreadable", "not_an_expense"}


@dataclass
class FormValues:
    merchant: str
    date: date
    total: float | None
    subtotal: float | None = None
    tax: float | None = None
    tip: float | None = None
    payment_method: str | None = None
    note: str = ""


def start_manual(original: Extraction | None = None) -> Extraction:
    """An empty form. Text from a failed read is kept, so the user can still look at it."""
    return Extraction(
        document_type="manual",
        raw_text=original.raw_text if original else "",
        text_confidence=original.text_confidence if original else 0.0,
    )


def apply_edits(original: Extraction, form: FormValues) -> Extraction:
    """The extraction as edited. A corrected field is no longer low confidence."""
    merchant = form.merchant.strip() or None
    edited = {
        "merchant": merchant,
        "date": form.date.isoformat(),
        "total": form.total,
        "subtotal": form.subtotal,
        "tax": form.tax,
        "tip": form.tip,
    }
    confidence = {k: v for k, v in original.field_confidence.items() if k not in edited or edited[k] == getattr(original, k)}
    return replace(original, **edited, payment_method=form.payment_method, field_confidence=confidence)


def form_issues(original: Extraction, edited: Extraction, today: date) -> list[ValidationIssue]:
    """Validate the edited values. The form prefills today, so V05 stays until the date is changed."""
    issues = validate(edited, today)
    if original.document_type != "manual" and original.date is None and edited.date == today.isoformat():
        issues.append(ValidationIssue("V05", "warning", "date", "No date found; defaulting to today. Change it if that's wrong."))
    return issues


def build_expense(
    original: Extraction,
    edited: Extraction,
    form: FormValues,
    category: str,
    category_source: str,
    file_hash: str | None = None,
) -> Expense:
    """`original` is stored as read, minus sensitive details, so the extraction stays traceable after edits."""
    has_extraction = original.document_type != "manual" or original.raw_text
    return Expense(
        merchant=edited.merchant,
        date=edited.date,
        total=round(edited.total, 2),
        subtotal=edited.subtotal,
        tax=edited.tax,
        tip=edited.tip,
        category=category,
        category_source=category_source,
        payment_method=edited.payment_method,
        document_type=original.document_type,
        note=form.note.strip() or None,
        file_hash=file_hash,
        extraction_json=json.dumps(redact_value(original.to_dict())) if has_extraction else None,
    )
