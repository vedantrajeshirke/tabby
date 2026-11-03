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

    def fake(image, timeout=0):
        calls.append(image.size)
        conf = first_conf if len(calls) == 1 else second_conf
        return _words(CENTERED, conf=conf)

    monkeypatch.setattr(ocr, "_image_to_data", fake)
    monkeypatch.setattr(ocr, "MAX_SIDE", 4000)
    return ocr.run_ocr(Image.new("L", (3000, 4000), 255)), calls


def test_cropped_pass_used_when_more_confident(monkeypatch):
    result, calls = _run_with_passes(monkeypatch, 70, 85)
    assert result.mean_confidence == 85
    assert calls == [(3000, 4000), (620, 3060)]


def test_no_second_pass_when_first_is_confident(monkeypatch):
    result, calls = _run_with_passes(monkeypatch, 95, 99)
    assert result.mean_confidence == 95
    assert len(calls) == 1


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


def test_preprocess_shrinks_large_photos_and_keeps_their_shape():
    processed = ocr.preprocess(Image.new("RGB", (3024, 4032), "white"))
    assert max(processed.size) == ocr.MAX_SIDE
    assert abs(processed.width / processed.height - 3024 / 4032) < 0.01


def _photo(paper_box=None, size=(1200, 1600)):
    image = Image.new("L", size, 60)
    if paper_box:
        image.paste(235, paper_box)
    return image


def test_find_paper_cuts_a_receipt_out_of_a_dark_background():
    left, top, right, bottom = ocr.find_paper(_photo((400, 300, 800, 1300)))
    assert 300 < left < 400 and 200 < top < 300 and 800 < right < 900 and 1300 < bottom < 1400


def test_find_paper_leaves_cropped_photos_and_tiny_specks_alone():
    assert ocr.find_paper(_photo((0, 0, 1200, 1600))) is None
    assert ocr.find_paper(_photo((500, 500, 560, 560))) is None
    assert ocr.find_paper(Image.new("L", (1200, 1600), 240)) is None


def test_paper_found_means_one_pass_on_the_crop(monkeypatch):
    sizes = []
    monkeypatch.setattr(ocr, "_image_to_data", lambda image, timeout=0: sizes.append(image.size) or _words(CENTERED, conf=50))
    ocr.run_ocr(_photo((400, 300, 800, 1300)))
    assert len(sizes) == 1 and sizes[0][0] < 1200 * 2


def test_reading_too_slowly_says_so(monkeypatch):
    def slow(*args, **kwargs):
        raise RuntimeError("Tesseract process timeout")

    monkeypatch.setattr(ocr.pytesseract, "image_to_data", slow)
    with pytest.raises(ocr.OcrTooSlow):
        ocr.run_ocr(_photo())


def test_tall_narrow_receipts_are_not_blown_up():
    assert max(ocr.preprocess(Image.new("L", (500, 2400), 255)).size) <= ocr.MAX_UPSCALED_SIDE
