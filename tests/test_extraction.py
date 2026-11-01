import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from core import extraction
from core.config import Config
from core.extraction import MOCK_DIR, LocalBackend, MockBackend, SafeBackend, get_backend
from core.models import Extraction
from tests.helpers import image_bytes, receipt_image, text_pdf

CFG = Config("local", "", 50.0)
needs_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract not installed")

RECEIPT = ["TRADER JOES", "10/28/2026", "BANANAS 1.67", "SUBTOTAL 1.67", "TAX 0.13", "TOTAL 1.80", "VISA"]


@pytest.mark.parametrize(
    "stem, doc_type",
    [("anything", "receipt"), ("blurry", "unreadable"), ("not_receipt", "not_an_expense"),
     ("mismatch", "receipt"), ("venmo", "payment_screenshot")],
)
def test_mock_chooses_fixture_by_stem(stem, doc_type):
    result = MockBackend().extract(b"", f"{stem}.jpg")
    assert isinstance(result, Extraction)
    assert result.document_type == doc_type
    assert result.raw_text.startswith("[MOCK DATA]")


def test_mock_filename_cannot_escape_fixture_dir():
    assert MockBackend().extract(b"", "../../secret.jpg").merchant == "Trader Joe"


def test_every_mock_fixture_is_labeled_and_loads():
    paths = list(Path(MOCK_DIR).glob("*.json"))
    assert {p.stem for p in paths} >= {"default", "blurry", "not_receipt", "mismatch", "venmo"}
    for path in paths:
        Extraction.from_dict(json.loads(path.read_text()))


def test_selects_backend_from_config():
    assert isinstance(get_backend(Config("mock", "", 50.0)).backend, MockBackend)
    assert isinstance(get_backend(CFG).backend, LocalBackend)


def test_pdf_text_layer_end_to_end_without_ocr():
    result = get_backend(CFG).extract(text_pdf(RECEIPT), "r.pdf")
    assert (result.document_type, result.text_source, result.text_confidence) == ("receipt", "pdf_text", 100.0)
    assert (result.total, result.subtotal, result.tax, result.date) == (1.80, 1.67, 0.13, "2026-10-28")


def test_backend_exception_becomes_unreadable():
    class Broken:
        def extract(self, file_bytes, filename):
            raise RuntimeError("boom with secret receipt text")

    result = SafeBackend(Broken()).extract(b"x", "a.png")
    assert result.document_type == "unreadable"
    assert "secret" not in result.field_reason["document_type"]


def test_corrupt_files_become_unreadable():
    backend = get_backend(CFG)
    assert backend.extract(b"not an image", "a.png").document_type == "unreadable"
    assert backend.extract(b"not a pdf", "a.pdf").document_type == "unreadable"


def test_unsupported_type_message_reaches_user():
    result = get_backend(CFG).extract(b"x", "a.gif")
    assert result.document_type == "unreadable"
    assert "isn't supported" in result.field_reason["document_type"]


def test_missing_tesseract_gives_helpful_reason(monkeypatch):
    def missing(*args, **kwargs):
        raise extraction.pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(extraction.ocr, "run_ocr", missing)
    result = get_backend(CFG).extract(image_bytes(Image.new("RGB", (10, 10))), "a.png")
    assert "isn't installed" in result.field_reason["document_type"]


@needs_tesseract
def test_real_ocr_on_receipt_image():
    result = get_backend(CFG).extract(image_bytes(receipt_image(RECEIPT)), "r.png")
    assert (result.document_type, result.text_source) == ("receipt", "ocr")
    assert result.total == 1.80
    assert result.date == "2026-10-28"
    assert result.text_confidence > 50


@needs_tesseract
def test_real_ocr_on_dark_mode_screenshot():
    lines = ["Venmo", "You paid Jane Doe", "$45.00", "Oct 20, 2026"]
    data = image_bytes(receipt_image(lines, background="black", ink="white"))
    result = get_backend(CFG).extract(data, "s.png")
    assert result.document_type == "payment_screenshot"
    assert (result.merchant, result.total) == ("Jane Doe", 45.00)


@needs_tesseract
def test_real_ocr_on_scanned_pdf():
    data = image_bytes(receipt_image(RECEIPT), "PDF")
    result = get_backend(CFG).extract(data, "scan.pdf")
    assert result.text_source == "ocr"
    assert result.total == 1.80


@needs_tesseract
def test_real_ocr_on_blank_image_is_unreadable():
    result = get_backend(CFG).extract(image_bytes(Image.new("RGB", (800, 800), "white")), "blank.png")
    assert result.document_type == "unreadable"
