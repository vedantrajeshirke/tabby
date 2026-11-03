import base64
import io
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from core import files
from tests.helpers import image_bytes, text_pdf


def test_hash_is_sha256_of_original_bytes():
    assert files.file_hash(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


@pytest.mark.parametrize("name", ["a.jpg", "a.JPEG", "a.png", "a.webp", "a.heic", "a.pdf"])
def test_allowed_types(name):
    files.validate_upload(b"x", name)


@pytest.mark.parametrize("name", ["a.gif", "a.exe", "noextension"])
def test_rejected_types(name):
    with pytest.raises(files.FileRejected, match="isn't supported"):
        files.validate_upload(b"x", name)


def test_size_limit():
    files.validate_upload(b"x" * files.MAX_BYTES, "a.png")
    with pytest.raises(files.FileRejected, match="10 MB"):
        files.validate_upload(b"x" * (files.MAX_BYTES + 1), "a.png")


def test_empty_file_rejected():
    with pytest.raises(files.FileRejected, match="empty"):
        files.validate_upload(b"", "a.png")


def test_load_image_applies_exif_rotation():
    image = Image.new("RGB", (200, 100), "white")
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 degrees
    assert files.load_image(image_bytes(image, "JPEG", exif=exif)).size == (100, 200)


def test_load_heic():
    data = image_bytes(Image.new("RGB", (64, 64), "white"), "HEIF")
    assert files.load_image(data).size == (64, 64)


def test_heic_gets_a_small_jpeg_preview():
    data = image_bytes(Image.new("RGB", (3000, 2000), "white"), "HEIF")
    preview = files.browser_preview(data, "receipt.HEIC")
    assert preview.startswith("data:image/jpeg;base64,")
    shown = Image.open(io.BytesIO(base64.b64decode(preview.split(",", 1)[1])))
    assert max(shown.size) == files.PREVIEW_SIDE


def test_preview_only_for_formats_browsers_cant_show():
    assert files.browser_preview(image_bytes(Image.new("RGB", (64, 64)), "PNG"), "a.png") is None
    assert files.browser_preview(b"not an image", "a.heic") is None


def test_pdf_with_text_layer_returns_text():
    content = files.load_pdf(text_pdf(["TRADER JOES MARKET", "TOTAL 23.47"]))
    assert content.has_text_layer
    assert "TOTAL 23.47" in content.text
    assert content.page_images == []


def test_pdf_reads_at_most_three_pages():
    lines = ["Same page text that is long enough"]
    content = files.load_pdf(text_pdf(lines, pages=5))
    assert content.text.count("Same page text") == 3


def test_scanned_pdf_renders_pages_with_no_text():
    data = image_bytes(Image.new("RGB", (612, 792), "white"), "PDF")
    content = files.load_pdf(data)
    assert not content.has_text_layer
    assert len(content.page_images) == 1
    assert content.page_images[0].width > 612  # rendered at 300 DPI


def test_short_text_triggers_render_path():
    page = MagicMock()
    page.extract_text.return_value = "ab 12"
    pdf = MagicMock(pages=[page])
    pdf.__enter__.return_value = pdf
    with patch("core.files.pdfplumber.open", return_value=pdf):
        content = files.load_pdf(b"irrelevant")
    page.to_image.assert_called_once_with(resolution=300)
    assert not content.has_text_layer
