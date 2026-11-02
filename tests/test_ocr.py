import shutil

import pytest
from PIL import Image, ImageDraw

from core import ocr
from tests.helpers import receipt_image


def test_preprocess_returns_grayscale_and_upscales():
    result = ocr.preprocess(Image.new("RGB", (400, 200), "white"))
    assert result.mode == "L"
    assert result.size == (1600, 800)


def test_preprocess_keeps_large_width():
    assert ocr.preprocess(Image.new("RGB", (2000, 100), "white")).width == 2000


def test_dark_image_is_inverted():
    image = Image.new("L", (1300, 100), 10)
    image.paste(240, (0, 0, 50, 100))  # light text on a dark background
    result = ocr.preprocess(image)
    assert result.getpixel((1000, 50)) > 200
    assert result.getpixel((10, 50)) < 50


def test_light_image_not_inverted():
    image = Image.new("L", (1300, 100), 240)
    image.paste(10, (0, 0, 50, 100))
    assert ocr.preprocess(image).getpixel((1000, 50)) > 200


def test_transparent_background_becomes_white():
    image = Image.new("RGBA", (1300, 100), (0, 0, 0, 0))
    image.paste((0, 0, 0, 255), (0, 0, 50, 100))
    assert ocr.preprocess(image).getpixel((1000, 50)) > 200


def test_result_from_data_groups_lines_and_skips_negative_conf():
    data = {
        "text": ["", "TOTAL", "5.00", "", "VISA"],
        "conf": [-1, 90, 80, -1, 70],
        "block_num": [1, 1, 1, 1, 1],
        "par_num": [1, 1, 1, 1, 1],
        "line_num": [0, 1, 1, 0, 2],
    }
    result = ocr.result_from_data(data)
    assert result.lines == ["TOTAL 5.00", "VISA"]
    assert result.text == "TOTAL 5.00\nVISA"
    assert result.mean_confidence == 80
    assert result.source == "ocr"


def test_no_words_means_zero_confidence():
    empty = {"text": [], "conf": [], "block_num": [], "par_num": [], "line_num": []}
    assert ocr.result_from_data(empty).mean_confidence == 0


def test_combine_ignores_blank_pages():
    page = ocr.OcrResult("a", ["a"], 80)
    blank = ocr.OcrResult("")
    combined = ocr.combine([page, blank])
    assert combined.mean_confidence == 80
    assert combined.lines == ["a"]


def _words(boxes, conf=90, text="WORD"):
    """Tesseract-style data with one word per (left, top, width, height) box."""
    return {
        "text": [text] * len(boxes),
        "conf": [conf] * len(boxes),
        "left": [b[0] for b in boxes],
        "top": [b[1] for b in boxes],
        "width": [b[2] for b in boxes],
        "height": [b[3] for b in boxes],
        "block_num": [1] * len(boxes),
        "par_num": [1] * len(boxes),
        "line_num": list(range(len(boxes))),
    }


CENTERED = [(1000, 1000 + 100 * i, 500, 50) for i in range(30)]


def test_crop_box_surrounds_strong_words():
    assert ocr.crop_box(_words(CENTERED), (3000, 4000)) == (940, 940, 1560, 4000)  # bottom edge stops at the image


def test_crop_box_ignores_side_outlier():
    data = _words(CENTERED + [(2900, 1500, 90, 50)])
    assert ocr.crop_box(data, (3000, 4000))[2] == 1560


def test_crop_box_ignores_weak_and_short_words():
    assert ocr.crop_box(_words(CENTERED, conf=40), (3000, 4000)) is None
    assert ocr.crop_box(_words(CENTERED, text="ab"), (3000, 4000)) is None


def test_no_crop_when_receipt_fills_the_frame():
    boxes = [(0, 100 * i, 3000, 50) for i in range(40)]
    assert ocr.crop_box(_words(boxes), (3000, 4000)) is None


def _run_with_passes(monkeypatch, first_conf, second_conf):
    calls = []

    def fake(image):
        calls.append(image.size)
        conf = first_conf if len(calls) == 1 else second_conf
        return _words(CENTERED, conf=conf)

    monkeypatch.setattr(ocr, "_image_to_data", fake)
    return ocr.run_ocr(Image.new("L", (3000, 4000), 255)), calls


def test_cropped_pass_used_when_more_confident(monkeypatch):
    result, calls = _run_with_passes(monkeypatch, 70, 85)
    assert result.mean_confidence == 85
    assert calls == [(3000, 4000), (620, 3060)]


def test_first_pass_kept_when_crop_is_worse(monkeypatch):
    result, calls = _run_with_passes(monkeypatch, 70, 60)
    assert result.mean_confidence == 70
    assert len(calls) == 2


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract not installed")
def test_real_ocr_reads_receipt_on_a_noisy_background():
    receipt = receipt_image(["PINE MARKET", "10/28/2026", "RICE 5.00", "TOTAL 5.00", "THANK YOU"])
    scene = Image.new("RGB", (3000, 4000), (120, 110, 100))
    draw = ImageDraw.Draw(scene)
    for x in range(0, 3000, 37):
        draw.line([(x, 0), (x + 60, 4000)], fill=(90, 80, 70), width=5)
    scene.paste(receipt, (1000, 1500))
    result = ocr.run_ocr(scene)
    assert "TOTAL 5.00" in result.text
