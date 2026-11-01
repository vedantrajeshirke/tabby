from PIL import Image

from core import ocr


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
