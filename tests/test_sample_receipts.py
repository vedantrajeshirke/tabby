"""The committed sample receipts behave as the README's demo scenarios say."""
from datetime import date
from pathlib import Path

import pytest

from core.config import find_tesseract, load_config
from core.extraction import get_backend
from core.validation import validate

SAMPLES = Path(__file__).resolve().parent.parent / "fixtures" / "sample_receipts"
needs_ocr = pytest.mark.skipif(find_tesseract(load_config()) is None, reason="Tesseract isn't installed")


def read(name: str):
    return get_backend().extract((SAMPLES / name).read_bytes(), name)


@pytest.fixture(autouse=True)
def real_backend(monkeypatch):
    monkeypatch.setenv("EXTRACTION_BACKEND", "local")


def codes(extraction) -> set[str]:
    return {issue.code for issue in validate(extraction, date(2026, 11, 1))}


def test_digital_pdf_is_read_from_its_text_layer():
    extraction = read("restaurant_digital.pdf")
    assert extraction.text_source == "pdf_text"
    assert (extraction.total, extraction.tip, extraction.date) == (19.20, 3.00, "2026-10-15")


@needs_ocr
def test_grocery_photo():
    extraction = read("grocery_photo.png")
    assert extraction.document_type == "receipt"
    assert (extraction.total, extraction.subtotal, extraction.tax) == (11.88, 11.00, 0.88)
    assert extraction.date == "2026-10-14"
    assert extraction.merchant.lower() == "sample grocer"


@needs_ocr
def test_amounts_that_dont_add_up_warn_without_blocking():
    extraction = read("amounts_dont_add_up.png")
    assert extraction.total == 40.00
    assert "V08" in codes(extraction)


@needs_ocr
def test_payment_screenshot():
    extraction = read("venmo_screenshot.png")
    assert extraction.document_type == "payment_screenshot"
    assert extraction.total == 45.00
    assert "Sam Example" in extraction.merchant


@needs_ocr
def test_something_that_isnt_a_receipt():
    extraction = read("not_a_receipt.png")
    assert extraction.document_type in {"not_an_expense", "unreadable"}
    assert extraction.total is None
    assert codes(extraction) & {"V01", "V02"}


@needs_ocr
def test_blurry_photo_fills_nothing():
    extraction = read("blurry_photo.png")
    assert extraction.total is None
    assert extraction.merchant is None
    assert extraction.document_type in {"unreadable", "not_an_expense"}
