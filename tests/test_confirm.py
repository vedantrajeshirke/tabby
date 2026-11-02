import json
from datetime import date

from core import confirm
from core.confirm import FormValues
from core.models import Extraction

TODAY = date(2026, 11, 1)


def read(**changes):
    values = dict(
        document_type="receipt", merchant="Safeway", date="2026-10-30", total=10.0, currency="USD",
        field_confidence={"merchant": "low", "date": "low", "total": "low"}, raw_text="SAFEWAY",
    )
    return Extraction(**{**values, **changes})


def form(**changes):
    values = dict(merchant="Safeway", date=date(2026, 10, 30), total=10.0)
    return FormValues(**{**values, **changes})


def test_unchanged_low_field_stays_flagged():
    edited = confirm.apply_edits(read(), form())
    assert edited.field_confidence == {"merchant": "low", "date": "low", "total": "low"}


def test_corrected_low_field_clears_only_that_flag():
    edited = confirm.apply_edits(read(), form(total=14.99))
    assert edited.total == 14.99
    assert "total" not in edited.field_confidence
    assert edited.field_confidence["merchant"] == "low"


def test_blank_merchant_becomes_missing():
    assert confirm.apply_edits(read(), form(merchant="   ")).merchant is None


def test_edits_do_not_change_the_original():
    original = read()
    confirm.apply_edits(original, form(total=99.0))
    assert original.total == 10.0


def test_missing_date_warns_until_changed():
    original = read(date=None, field_confidence={})
    prefilled = confirm.apply_edits(original, form(date=TODAY))
    assert [i.code for i in confirm.form_issues(original, prefilled, TODAY)] == ["V05"]
    changed = confirm.apply_edits(original, form(date=date(2026, 10, 1)))
    assert confirm.form_issues(original, changed, TODAY) == []


def test_manual_entry_has_no_v05_and_blocks_without_total():
    original = confirm.start_manual()
    edited = confirm.apply_edits(original, form(merchant="Deli", date=TODAY, total=None))
    assert [i.code for i in confirm.form_issues(original, edited, TODAY)] == ["V03"]


def test_start_manual_after_failed_read_keeps_text_only():
    original = read(document_type="unreadable", total=5.0)
    manual = confirm.start_manual(original)
    assert (manual.document_type, manual.total, manual.merchant, manual.raw_text) == ("manual", None, None, "SAFEWAY")


def test_build_expense_stores_edits_and_the_original_read():
    original = read(currency="EUR")
    values = form(total=12.345, note="  lunch ")
    edited = confirm.apply_edits(original, values)
    expense = confirm.build_expense(original, edited, values, "Groceries", "rule", "files/a.png", "abc")
    assert (expense.total, expense.currency, expense.note, expense.file_hash) == (12.35, "EUR", "lunch", "abc")
    assert json.loads(expense.extraction_json)["total"] == 10.0


def test_build_expense_without_merchant_or_extraction():
    original = confirm.start_manual()
    values = form(merchant="", date=TODAY)
    expense = confirm.build_expense(original, confirm.apply_edits(original, values), values, "Other", "default")
    assert expense.merchant == confirm.UNKNOWN_MERCHANT
    assert expense.document_type == "manual"
    assert expense.extraction_json is None


def test_stored_extraction_is_redacted():
    original = read(raw_text="SAFEWAY\nVISA ****1234\nUser ID: 1234", field_reason={"total": "found on line 'CARD *1234 10.00'"})
    values = form()
    stored = json.loads(confirm.build_expense(original, confirm.apply_edits(original, values), values, "Other", "rule").extraction_json)
    assert "1234" not in stored["raw_text"]
    assert "1234" not in stored["field_reason"]["total"]
    assert "SAFEWAY" in stored["raw_text"]
    assert "****1234" in original.raw_text  # the in-memory copy is left alone
