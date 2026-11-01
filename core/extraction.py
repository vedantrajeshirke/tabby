"""Extraction backends. The rest of the app depends only on ExtractionBackend."""
import json
import logging
from pathlib import Path
from typing import Protocol

import pytesseract

from core import files, ocr, parser
from core.config import CATEGORIES_PATH, ROOT, Config, load_config
from core.models import Extraction

log = logging.getLogger(__name__)

MOCK_DIR = ROOT / "fixtures" / "mock_extractions"


class ExtractionBackend(Protocol):
    def extract(self, file_bytes: bytes, filename: str) -> Extraction: ...


def load_merchant_keywords(path: Path = CATEGORIES_PATH) -> list[str]:
    """Keywords that name a merchant. Generic ones like COFFEE only help categorize."""
    config = json.loads(path.read_text())
    generic = set(config.get("generic_keywords", []))
    return [kw for rule in config["rules"] for kw in rule["keywords"] if kw not in generic]


def unreadable(reason: str) -> Extraction:
    return Extraction(document_type="unreadable", field_reason={"document_type": reason})


class LocalBackend:
    """PDF text layer -> OCR fallback -> rule-based parser. Nothing leaves the device."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.keywords = load_merchant_keywords()

    def _parse(self, text: str, source: str, confidence: float) -> Extraction:
        return parser.parse(text, source, confidence, self.keywords, self.cfg.ocr_min_confidence)

    def _parse_ocr(self, result: ocr.OcrResult) -> Extraction:
        return self._parse(result.text, result.source, result.mean_confidence)

    def extract(self, file_bytes: bytes, filename: str) -> Extraction:
        files.validate_upload(file_bytes, filename)
        if files.extension(filename) != "pdf":
            return self._parse_ocr(ocr.run_ocr(files.load_image(file_bytes), self.cfg.tesseract_cmd))
        pdf = files.load_pdf(file_bytes)
        if pdf.has_text_layer:
            return self._parse(pdf.text, "pdf_text", 100.0)
        pages = [ocr.run_ocr(image, self.cfg.tesseract_cmd) for image in pdf.page_images]
        return self._parse_ocr(ocr.combine(pages))


class MockBackend:
    """Returns a canned result chosen by filename stem, for development and tests."""

    def __init__(self, fixtures_dir: Path = MOCK_DIR):
        self.fixtures_dir = fixtures_dir

    def extract(self, file_bytes: bytes, filename: str) -> Extraction:
        path = self.fixtures_dir / f"{Path(filename).stem}.json"
        if not path.is_file():
            path = self.fixtures_dir / "default.json"
        return Extraction.from_dict(json.loads(path.read_text()))


class SafeBackend:
    """Turns any backend exception into an `unreadable` extraction so pages never crash."""

    def __init__(self, backend: ExtractionBackend):
        self.backend = backend

    def extract(self, file_bytes: bytes, filename: str) -> Extraction:
        try:
            return self.backend.extract(file_bytes, filename)
        except files.FileRejected as e:
            return unreadable(str(e))
        except pytesseract.TesseractNotFoundError:
            return unreadable("Tesseract OCR isn't installed, so this file can't be read. Install it or enter the expense manually.")
        except Exception as e:
            log.error("Extraction failed: %s", type(e).__name__)  # never log file contents
            return unreadable("This file couldn't be processed. Try another file or enter the expense manually.")


def get_backend(cfg: Config | None = None) -> ExtractionBackend:
    cfg = cfg or load_config()
    backend = MockBackend() if cfg.extraction_backend == "mock" else LocalBackend(cfg)
    return SafeBackend(backend)
