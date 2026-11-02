"""Runs the real page through Streamlit's test harness with a stand-in for the upload widget."""
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from core import db
from tests.helpers import image_bytes, receipt_image, text_pdf

PAGE = str(Path(__file__).resolve().parent.parent / "pages/1_Add_Expense.py")
RECEIPT = ["TRADER JOES MARKET", "10/28/2026", "BANANAS 1.67", "SUBTOTAL 1.67", "TAX 0.13", "TOTAL 1.80", "VISA"]


class FakeUpload:
    def __init__(self, name, data):
        self.name, self.data = name, data

    def getvalue(self):
        return self.data


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setenv("EXTRACTION_BACKEND", "local")
    monkeypatch.setenv("HOSTED_DEMO", "false")
    holder = {"file": None}
    monkeypatch.setattr(st, "file_uploader", lambda *a, **k: holder["file"])
    return tmp_path, holder


def rows(tmp_path):
    with db.connect(tmp_path / "app.db") as conn:
        return conn.execute("SELECT * FROM expenses").fetchall()


def button(at, text):
    return next(b for b in at.button if text in b.label)


def text_input(at, text):
    return next(t for t in at.text_input if text in t.label)


def number_input(at, text):
    return next(n for n in at.number_input if text in n.label)


def selectbox(at, text):
    return next(s for s in at.selectbox if text in s.label)


def warnings(at):
    return " ".join(w.value for w in at.warning)


def open_page():
    at = AppTest.from_file(PAGE, default_timeout=30).run()
    assert not at.exception
    return at


def test_pdf_receipt_to_saved_expense(env):
    tmp_path, holder = env
    holder["file"] = FakeUpload("r.pdf", text_pdf(RECEIPT))
    at = open_page()
    assert number_input(at, "Total").value == 1.80
    assert selectbox(at, "Category").value == "Groceries"
    assert rows(tmp_path) == []  # nothing is saved before the user confirms
    assert not (tmp_path / "files").exists()
    button(at, "Save expense").click().run()
    assert not at.exception
    saved = rows(tmp_path)
    assert len(saved) == 1
    assert (saved[0]["total"], saved[0]["date"], saved[0]["document_type"]) == (1.80, "2026-10-28", "receipt")
    assert (tmp_path / saved[0]["file_path"]).read_bytes() == holder["file"].data
    assert any("Saved:" in s.value for s in at.success)


def test_same_file_twice_warns_but_can_still_save(env):
    tmp_path, holder = env
    holder["file"] = FakeUpload("r.pdf", text_pdf(RECEIPT))
    at = open_page()
    button(at, "Save expense").click().run()
    at = open_page()
    assert "already added this file" in warnings(at)
    assert not button(at, "Save expense").disabled
    button(at, "Save expense").click().run()
    assert len(rows(tmp_path)) == 2


def test_discard_saves_nothing(env):
    tmp_path, holder = env
    holder["file"] = FakeUpload("r.pdf", text_pdf(RECEIPT))
    at = open_page()
    button(at, "Discard").click().run()
    assert not at.exception
    assert rows(tmp_path) == []


def test_zero_total_disables_save(env):
    _, holder = env
    holder["file"] = FakeUpload("r.pdf", text_pdf(RECEIPT))
    at = open_page()
    number_input(at, "Total").set_value(0.0).run()
    assert not at.exception
    assert button(at, "Save expense").disabled
    assert any("greater than zero" in e.value for e in at.error)
    number_input(at, "Total").set_value(9.0).run()
    assert not button(at, "Save expense").disabled


def test_edited_values_are_what_gets_saved(env):
    tmp_path, holder = env
    holder["file"] = FakeUpload("r.pdf", text_pdf(RECEIPT))
    at = open_page()
    number_input(at, "Total").set_value(5.55).run()
    text_input(at, "Merchant").set_value("Corner Deli").run()
    button(at, "Save expense").click().run()
    saved = rows(tmp_path)[0]
    assert (saved["total"], saved["merchant"]) == (5.55, "Corner Deli")


def test_manual_entry_with_rule_suggestion(env):
    tmp_path, _ = env
    at = open_page()
    button(at, "Enter manually instead").click().run()
    assert button(at, "Save expense").disabled  # no total yet
    text_input(at, "Merchant").set_value("Safeway").run()
    assert selectbox(at, "Category").value == "Groceries"
    number_input(at, "Total").set_value(12.0).run()
    button(at, "Save expense").click().run()
    saved = rows(tmp_path)[0]
    assert (saved["document_type"], saved["category"], saved["category_source"]) == ("manual", "Groceries", "rule")
    assert saved["file_path"] is None


def test_always_use_this_category_applies_next_time(env):
    tmp_path, _ = env
    at = open_page()
    button(at, "Enter manually instead").click().run()
    text_input(at, "Merchant").set_value("Joe's Deli").run()
    number_input(at, "Total").set_value(8.0).run()
    selectbox(at, "Category").set_value("Groceries").run()
    next(c for c in at.checkbox if "Always use" in c.label).check().run()
    button(at, "Save expense").click().run()
    assert rows(tmp_path)[0]["category_source"] == "manual"
    at = open_page()
    button(at, "Enter manually instead").click().run()
    text_input(at, "Merchant").set_value("JOE'S DELI").run()
    assert selectbox(at, "Category").value == "Groceries"
    assert any("your past choice" in c.value for c in at.caption)


def test_non_receipt_offers_manual_entry_and_no_form(env):
    tmp_path, holder = env
    holder["file"] = FakeUpload("notes.pdf", text_pdf(["Lecture notes about databases and normalization"]))
    at = open_page()
    assert any("doesn't look like a receipt" in e.value for e in at.error)
    assert not [b for b in at.button if "Save expense" in b.label]
    button(at, "Enter manually").click().run()
    assert number_input(at, "Total").value is None
    assert not at.exception


def test_unsupported_type_explains_what_to_do(env):
    _, holder = env
    holder["file"] = FakeUpload("a.gif", b"GIF89a")
    at = open_page()
    assert any("isn't supported" in e.value for e in at.error)
    assert not at.exception


def test_corrupt_image_does_not_crash(env):
    _, holder = env
    holder["file"] = FakeUpload("a.png", b"not an image")
    at = open_page()
    assert any("Couldn't read" in e.value for e in at.error)


def test_image_upload_runs_ocr_once_across_reruns(env, monkeypatch):
    _, holder = env
    from core import extraction

    calls = []
    real = extraction.ocr.run_ocr
    monkeypatch.setattr(extraction.ocr, "run_ocr", lambda *a, **k: calls.append(1) or real(*a, **k))
    holder["file"] = FakeUpload("r.png", image_bytes(receipt_image(RECEIPT)))
    at = open_page()
    assert number_input(at, "Total").value == 1.80
    text_input(at, "Merchant").set_value("Edited").run()
    assert len(calls) == 1


def test_mock_mode_is_labeled_and_works(env, monkeypatch):
    _, holder = env
    monkeypatch.setenv("EXTRACTION_BACKEND", "mock")
    holder["file"] = FakeUpload("mismatch.jpg", b"anything")
    at = open_page()
    assert "MOCK MODE" in warnings(at)
    assert "Subtotal + tax + tip" in warnings(at)


def test_hosted_sessions_are_separate_and_notice_shown(env, monkeypatch):
    tmp_path, holder = env
    monkeypatch.setenv("HOSTED_DEMO", "true")
    holder["file"] = FakeUpload("r.pdf", text_pdf(RECEIPT))
    first = open_page()
    assert any("Public demo" in i.value for i in first.info)
    assert not any("only on this device" in c.value for c in first.caption)
    button(first, "Save expense").click().run()
    assert not (tmp_path / "app.db").exists()
    assert len(list((tmp_path / "sessions").iterdir())) == 1
    second = open_page()  # a new visitor sees no duplicate of the first visitor's file
    assert "already added" not in warnings(second)
    assert len(list((tmp_path / "sessions").iterdir())) == 2


def test_local_mode_shows_device_note(env):
    at = open_page()
    assert any("only on this device" in c.value for c in at.caption)
