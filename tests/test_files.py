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


def _photo_with_gps():
    exif = Image.Exif()
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2] = "N", (34.0, 1.0, 2.0)
    exif[0x010F] = "Test Camera"
    exif[0x0112] = 6
    return image_bytes(Image.new("RGB", (400, 200), "white"), "JPEG", exif=exif)


def test_prepare_strips_gps_and_all_metadata_but_keeps_rotation():
    original = _photo_with_gps()
    assert Image.open(io.BytesIO(original)).getexif().get_ifd(0x8825)
    data, ext = files.prepare_for_storage(original, "photo.jpg")
    stored = Image.open(io.BytesIO(data))
    assert ext == "jpg"
    assert dict(stored.getexif()) == {}
    assert b"Test Camera" not in data
    assert stored.size == (200, 400)


def test_prepare_shrinks_large_photos_and_converts_heic():
    data, ext = files.prepare_for_storage(image_bytes(Image.new("RGB", (4000, 6000), "white"), "HEIF"), "a.HEIC")
    assert ext == "jpg"
    assert max(Image.open(io.BytesIO(data)).size) == 2000


def test_prepare_flattens_transparent_png():
    assert files.prepare_for_storage(image_bytes(Image.new("RGBA", (10, 10))), "a.png")[1] == "jpg"


def test_prepare_keeps_pdf_and_refuses_corrupt_image():
    assert files.prepare_for_storage(b"%PDF", "a.pdf") == (b"%PDF", "pdf")
    assert files.prepare_for_storage(b"junk", "a.png") is None
