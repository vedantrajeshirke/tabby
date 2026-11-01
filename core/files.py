"""Upload checks, hashing, image loading and PDF text/rendering."""
import hashlib
import io
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()

IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "heic"}
ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | {"pdf"}
MAX_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 3
MIN_TEXT_LAYER_CHARS = 20
PDF_RENDER_DPI = 300


class FileRejected(ValueError):
    """The upload can't be processed; the message tells the user what to do next."""


@dataclass
class PdfContent:
    text: str
    page_images: list[Image.Image] = field(default_factory=list)  # set only when there's no text layer

    @property
    def has_text_layer(self) -> bool:
        return not self.page_images


def extension(filename: str) -> str:
    return Path(filename).suffix.lstrip(".").lower()


def validate_upload(file_bytes: bytes, filename: str) -> None:
    if extension(filename) not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise FileRejected(f"This file type isn't supported. Upload one of: {allowed}, or enter the expense manually.")
    if len(file_bytes) > MAX_BYTES:
        raise FileRejected("This file is larger than 10 MB. Upload a smaller copy or enter the expense manually.")
    if not file_bytes:
        raise FileRejected("This file is empty. Upload it again or enter the expense manually.")


def file_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def load_image(file_bytes: bytes) -> Image.Image:
    """Decode an image and apply its EXIF orientation."""
    image = Image.open(io.BytesIO(file_bytes))
    image.load()
    return ImageOps.exif_transpose(image)


def alnum_count(text: str) -> int:
    return sum(ch.isalnum() for ch in text)


def load_pdf(file_bytes: bytes) -> PdfContent:
    """Return the text of the first pages, or rendered page images if there's no text layer."""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        pages = pdf.pages[:MAX_PDF_PAGES]
        text = "\n".join(page.extract_text() or "" for page in pages).strip()
        if alnum_count(text) >= MIN_TEXT_LAYER_CHARS:
            return PdfContent(text=text)
        return PdfContent(text="", page_images=[page.to_image(resolution=PDF_RENDER_DPI).original for page in pages])
