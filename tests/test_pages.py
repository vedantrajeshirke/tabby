from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
PAGES = ["app.py", "pages/1_Add_Expense.py", "pages/2_Expenses.py", "pages/3_Dashboard.py", "pages/4_Settings.py"]


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    import core.db as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")


@pytest.mark.parametrize("page", PAGES)
def test_page_runs(page):
    at = AppTest.from_file(str(ROOT / page)).run()
    assert not at.exception


def test_settings_save_and_load():
    at = AppTest.from_file(str(ROOT / "pages/4_Settings.py")).run()
    at.text_input[0].set_value("Ava")
    at.number_input[0].set_value(900.0)
    at.number_input[1].set_value(15)
    at.button[0].click().run()
    assert not at.exception
    at2 = AppTest.from_file(str(ROOT / "pages/4_Settings.py")).run()
    assert at2.text_input[0].value == "Ava"
    assert at2.number_input[0].value == 900.0
    assert at2.number_input[1].value == 15


def test_tesseract_banner(monkeypatch):
    monkeypatch.setenv("TESSERACT_CMD", "/nonexistent/tesseract")
    at = AppTest.from_file(str(ROOT / "app.py")).run()
    assert any("Tesseract OCR not found" in w.value for w in at.warning)


def test_mock_banner_on_capture_page(monkeypatch):
    monkeypatch.setenv("EXTRACTION_BACKEND", "mock")
    at = AppTest.from_file(str(ROOT / "pages/1_Add_Expense.py")).run()
    assert any("MOCK MODE" in w.value for w in at.warning)


def test_no_mock_banner_in_local_mode(monkeypatch):
    monkeypatch.setenv("EXTRACTION_BACKEND", "local")
    at = AppTest.from_file(str(ROOT / "pages/1_Add_Expense.py")).run()
    assert not any("MOCK MODE" in w.value for w in at.warning)
