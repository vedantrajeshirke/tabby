from datetime import date, timedelta

import pytest

from core.models import Extraction
from core.validation import blocks_save, validate

TODAY = date(2026, 11, 1)


def good(**changes):
    values = dict(document_type="receipt", merchant="Safeway", date="2026-10-30", currency="USD", total=10.0)
    return Extraction(**{**values, **changes})


def codes(e):
    return [issue.code for issue in validate(e, TODAY)]


def test_good_receipt_has_no_issues():
    assert codes(good()) == []


@pytest.mark.parametrize("doc_type, code", [("not_an_expense", "V01"), ("unreadable", "V02")])
def test_unusable_document_gets_one_error(doc_type, code):
    issues = validate(Extraction(document_type=doc_type), TODAY)
    assert [i.code for i in issues] == [code]
    assert issues[0].severity == "error"
    assert "manually" in issues[0].message
    assert not blocks_save(issues)  # the way forward is manual entry, which opens a fresh form


def test_v03_missing_total_blocks():
    issues = validate(good(total=None), TODAY)
    assert [i.code for i in issues] == ["V03"]
    assert blocks_save(issues)


@pytest.mark.parametrize("total", [0, -5.0])
def test_v04_non_positive_total_blocks(total):
    issues = validate(good(total=total), TODAY)
    assert [i.code for i in issues] == ["V04"]
    assert blocks_save(issues)


def test_small_positive_total_is_fine():
    assert codes(good(total=0.01)) == []


@pytest.mark.parametrize("value", [None, "", "not-a-date"])
def test_v05_missing_date_warns(value):
    issues = validate(good(date=value), TODAY)
    assert [i.code for i in issues] == ["V05"]
    assert not blocks_save(issues)


def test_v06_future_date_blocks():
    issues = validate(good(date=(TODAY + timedelta(days=1)).isoformat()), TODAY)
    assert [i.code for i in issues] == ["V06"]
    assert blocks_save(issues)


def test_today_is_allowed():
    assert codes(good(date=TODAY.isoformat())) == []


def test_v07_age_boundary():
    assert codes(good(date=(TODAY - timedelta(days=365)).isoformat())) == []
    assert codes(good(date=(TODAY - timedelta(days=366)).isoformat())) == ["V07"]


@pytest.mark.parametrize(
    "subtotal, tax, tip, total, fires",
    [
        (10.00, 1.00, 2.00, 13.00, False),
        (10.00, 1.00, 2.00, 13.05, False),  # exactly at the tolerance
        (10.00, 1.00, 2.00, 12.95, False),
        (10.00, 1.00, 2.00, 13.06, True),  # just past it
        (10.00, 1.00, 2.00, 12.94, True),
        (10.00, None, None, 10.00, False),
        (10.10, 0.20, None, 10.25, False),  # float sums must not cause a false alarm
        (None, 1.00, 2.00, 50.00, False),  # no subtotal, nothing to compare
    ],
)
def test_v08_amounts_add_up(subtotal, tax, tip, total, fires):
    assert ("V08" in codes(good(subtotal=subtotal, tax=tax, tip=tip, total=total))) is fires


def test_v08_message_has_the_numbers_and_does_not_block():
    issues = validate(good(subtotal=30.0, tax=2.5, total=40.0), TODAY)
    assert issues[0].message == "Subtotal + tax + tip = $32.50 but total is $40.00. Please check the amounts."
    assert not blocks_save(issues)


def test_item_sums_are_not_checked():
    from core.models import LineItem

    e = good(subtotal=10.0, total=10.0, line_items=[LineItem("A", None, 1.0)])
    assert codes(e) == []


def test_v11_low_confidence_names_the_field():
    issues = validate(good(field_confidence={"total": "low", "date": "medium", "merchant": "high"}), TODAY)
    assert [(i.code, i.field) for i in issues] == [("V11", "total")]
    assert issues[0].message == "Please double-check the total."


def test_v12_missing_merchant_warns():
    assert codes(good(merchant=None)) == ["V12"]
    assert codes(good(merchant="")) == ["V12"]


def test_payment_screenshot_is_validated_normally():
    assert codes(good(document_type="payment_screenshot")) == []
