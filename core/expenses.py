"""Reviewing, saving and editing expenses. Framework-free; routes call these."""
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone

import psycopg

from core import categorize, confirm, db, files, storage
from core.duplicates import find_duplicates
from core.models import Extraction
from core.validation import blocks_save, validate

SOURCE_MANUAL = "manual"


class InvalidCategory(ValueError):
    pass


@dataclass
class Review:
    original: Extraction
    edited: Extraction
    form: confirm.FormValues
    issues: list
    blocked: bool
    category: str
    category_source: str
    duplicates: list


def resolve_today(client_today: date | None) -> date:
    """The user's local date, which the server can't know. Limited to a day either side of UTC."""
    utc_today = datetime.now(timezone.utc).date()
    if client_today is None:
        return utc_today
    return min(max(client_today, utc_today - timedelta(days=1)), utc_today + timedelta(days=1))


def usable_original(original: Extraction | None) -> Extraction:
    """A document that couldn't be read continues as manual entry, with an empty form."""
    if original is None or original.document_type in confirm.UNUSABLE_DOCUMENT_TYPES:
        return confirm.start_manual(original)
    return original


def choose_category(
    conn: psycopg.Connection, user_id: str, merchant: str | None, extraction: Extraction, chosen: str | None
) -> tuple[str, str]:
    config = categorize.load_config()
    if chosen is not None and chosen not in config["categories"]:
        raise InvalidCategory("Choose one of the listed categories.")
    overrides = db.get_overrides(conn, user_id)
    suggested, source = categorize.categorize(
        merchant, extraction.document_type, extraction.raw_text, overrides, config["rules"]
    )
    return (suggested, source) if chosen in (None, suggested) else (chosen, SOURCE_MANUAL)


def review(
    conn: psycopg.Connection,
    user_id: str,
    original: Extraction | None,
    form: confirm.FormValues,
    today: date,
    category: str | None = None,
    file_hash: str | None = None,
) -> Review:
    usable = usable_original(original)
    edited = confirm.apply_edits(usable, form)
    issues = confirm.form_issues(usable, edited, today)
    chosen, source = choose_category(conn, user_id, edited.merchant, usable, category)
    duplicates = find_duplicates(conn, user_id, file_hash, edited.merchant, edited.date, edited.total)
    return Review(usable, edited, form, issues, blocks_save(issues), chosen, source, duplicates)


def review_upload(conn: psycopg.Connection, user_id: str, extraction: Extraction, file_hash: str, today: date) -> dict:
    """The first check after a file is read. Unusable documents get their one clear error."""
    if extraction.document_type in confirm.UNUSABLE_DOCUMENT_TYPES:
        issues = validate(extraction, today)
        duplicates = find_duplicates(conn, user_id, file_hash)
        return report(issues, False, *choose_category(conn, user_id, None, confirm.start_manual(extraction), None), duplicates)
    day = date.fromisoformat(extraction.date) if extraction.date else today
    form = confirm.FormValues(
        extraction.merchant or "", day, extraction.total, extraction.subtotal, extraction.tax, extraction.tip,
        extraction.payment_method,
    )
    checked = review(conn, user_id, extraction, form, today, file_hash=file_hash)
    return report_review(checked)


def report(issues: list, blocked: bool, category: str, source: str, duplicates: list) -> dict:
    return {
        "issues": [asdict(i) for i in issues],
        "blocks_save": blocked,
        "category": category,
        "category_source": source,
        "category_label": categorize.SOURCE_LABELS[source],
        "duplicates": [asdict(d) for d in duplicates],
    }


def report_review(checked: Review) -> dict:
    return report(checked.issues, checked.blocked, checked.category, checked.category_source, checked.duplicates)


def save(
    conn: psycopg.Connection,
    store: storage.Storage,
    user_id: str,
    checked: Review,
    upload: tuple[bytes, str] | None = None,
    always_use_category: bool = False,
) -> int:
    """Store the original, with metadata removed, then the expense. The hash is of the original bytes."""
    file_path = file_hash = None
    newly_stored = False
    if upload:
        file_bytes, filename = upload
        file_hash = files.file_hash(file_bytes)
        prepared = files.prepare_for_storage(file_bytes, filename)
        if prepared:
            data, ext = prepared
            file_path = storage.file_key(user_id, file_hash, ext)
            newly_stored = store.read(file_path) is None
            store.save(file_path, data)
    expense = confirm.build_expense(
        checked.original, checked.edited, checked.form, checked.category, checked.category_source, file_path, file_hash
    )
    try:
        expense_id = db.insert_expense(conn, user_id, expense)
    except Exception:
        if newly_stored:
            store.delete(file_path)
        raise
    if always_use_category and checked.edited.merchant and checked.category_source == SOURCE_MANUAL:
        db.set_override(conn, user_id, checked.edited.merchant, checked.category)
    return expense_id


def delete(conn: psycopg.Connection, store: storage.Storage, user_id: str, expense_id: int) -> bool:
    """Delete the expense, and its file unless another expense uses the same one."""
    removed = db.delete_expense(conn, user_id, expense_id)
    if removed is None:
        return False
    path = removed["file_path"]
    if path and db.count_file_uses(conn, user_id, path) == 0:
        store.delete(path)
    return True


def existing_as_extraction(row: dict) -> Extraction:
    """A saved expense as the starting point for edits. Its values have already been confirmed."""
    return Extraction(
        document_type="manual",
        merchant=row["merchant"],
        date=row["date"],
        currency=row["currency"],
        subtotal=row["subtotal"],
        tax=row["tax"],
        tip=row["tip"],
        total=row["total"],
        payment_method=row["payment_method"],
    )


def edit(conn: psycopg.Connection, user_id: str, row: dict, form: confirm.FormValues, today: date, category: str | None) -> Review:
    """Check edited values. The category stays as saved unless it's changed here."""
    base = existing_as_extraction(row)
    edited = confirm.apply_edits(base, form)
    issues = confirm.form_issues(base, edited, today)
    if category is None or category == row["category"]:
        chosen, source = row["category"], row["category_source"]
    else:
        if category not in categorize.load_config()["categories"]:
            raise InvalidCategory("Choose one of the listed categories.")
        chosen, source = category, SOURCE_MANUAL
    duplicates = find_duplicates(conn, user_id, None, edited.merchant, edited.date, edited.total, exclude_id=row["id"])
    return Review(base, edited, form, issues, blocks_save(issues), chosen, source, duplicates)
