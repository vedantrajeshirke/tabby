from core import config


def test_inline_comments_stripped(monkeypatch):
    monkeypatch.setenv("EXTRACTION_BACKEND", "mock    # local | mock")
    monkeypatch.setenv("OCR_MIN_CONFIDENCE", "60  # x")
    monkeypatch.setenv("TESSERACT_CMD", "")
    cfg = config.load_config()
    assert (cfg.extraction_backend, cfg.ocr_min_confidence) == ("mock", 60.0)


def test_missing_tesseract_cmd(monkeypatch):
    cfg = config.Config("local", "/nonexistent/tesseract", 50)
    assert config.find_tesseract(cfg) is None
