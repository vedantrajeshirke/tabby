"""Image preprocessing and Tesseract OCR."""
from dataclasses import dataclass, field

import pytesseract
from PIL import Image, ImageOps, ImageStat
from pytesseract import Output

MIN_WIDTH = 1200
UPSCALE_WIDTH = 1600
DARK_MEAN_BRIGHTNESS = 100
OCR_TIMEOUT_SECONDS = 60
CROP_MIN_WORD_CONF = 60
CROP_MIN_WORD_CHARS = 3
CROP_MIN_WORDS = 5
CROP_MARGIN = 60
CROP_OUTLIER_SHARE = 0.05
CROP_MAX_AREA_SHARE = 0.8  # a bigger crop wouldn't remove enough background to justify a second pass


@dataclass
class OcrResult:
    text: str
    lines: list[str] = field(default_factory=list)
    mean_confidence: float = 0.0
    source: str = "ocr"


def _flatten_alpha(image: Image.Image) -> Image.Image:
    if image.mode in ("RGBA", "LA", "PA"):
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, "white")
        return Image.alpha_composite(background, rgba)
    return image


def preprocess(image: Image.Image) -> Image.Image:
    """Grayscale, upscale small images, stretch contrast, invert dark-mode screenshots."""
    gray = _flatten_alpha(image).convert("L")
    if gray.width < MIN_WIDTH:
        height = round(gray.height * UPSCALE_WIDTH / gray.width)
        gray = gray.resize((UPSCALE_WIDTH, height), Image.Resampling.LANCZOS)
    gray = ImageOps.autocontrast(gray)
    if ImageStat.Stat(gray).mean[0] < DARK_MEAN_BRIGHTNESS:
        gray = ImageOps.invert(gray)
    return gray


def result_from_data(data: dict) -> OcrResult:
    """Rebuild lines and the mean word confidence from Tesseract's image_to_data output."""
    lines: dict[tuple, list[str]] = {}
    confidences: list[float] = []
    for i, word in enumerate(data["text"]):
        word = str(word).strip()
        confidence = float(data["conf"][i])
        if not word or confidence < 0:
            continue
        confidences.append(confidence)
        lines.setdefault((data["block_num"][i], data["par_num"][i], data["line_num"][i]), []).append(word)
    joined = [" ".join(words) for words in lines.values()]
    mean = sum(confidences) / len(confidences) if confidences else 0.0
    return OcrResult(text="\n".join(joined), lines=joined, mean_confidence=mean)


def crop_box(data: dict, size: tuple[int, int]) -> tuple[int, int, int, int] | None:
    """Box around the confidently read words, or None if cropping wouldn't remove much background."""
    strong = [
        i for i, word in enumerate(data["text"])
        if len(str(word).strip()) >= CROP_MIN_WORD_CHARS and float(data["conf"][i]) >= CROP_MIN_WORD_CONF
    ]
    if len(strong) < CROP_MIN_WORDS:
        return None
    lefts = sorted(data["left"][i] for i in strong)
    rights = sorted(data["left"][i] + data["width"][i] for i in strong)
    # Trim the sides so a stray word in the background can't stretch the box. Keep the full
    # height, because the merchant and total are often single words at the very top and bottom.
    outliers = int(len(strong) * CROP_OUTLIER_SHARE)
    box = (
        max(0, lefts[outliers] - CROP_MARGIN),
        max(0, min(data["top"][i] for i in strong) - CROP_MARGIN),
        min(size[0], rights[-1 - outliers] + CROP_MARGIN),
        min(size[1], max(data["top"][i] + data["height"][i] for i in strong) + CROP_MARGIN),
    )
    area = (box[2] - box[0]) * (box[3] - box[1])
    return box if area < CROP_MAX_AREA_SHARE * size[0] * size[1] else None


def _image_to_data(image: Image.Image) -> dict:
    return pytesseract.image_to_data(image, config="--psm 6", output_type=Output.DICT, timeout=OCR_TIMEOUT_SECONDS)


def run_ocr(image: Image.Image, tesseract_cmd: str = "") -> OcrResult:
    """OCR the image, then again cropped to the receipt, and keep the more confident result."""
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    processed = preprocess(image)
    data = _image_to_data(processed)
    result = result_from_data(data)
    box = crop_box(data, processed.size)
    if box is None:
        return result
    cropped = result_from_data(_image_to_data(processed.crop(box)))
    return cropped if cropped.mean_confidence > result.mean_confidence else result


def combine(results: list[OcrResult]) -> OcrResult:
    """Merge the pages of a scanned PDF. Blank pages don't lower the confidence."""
    pages = [r for r in results if r.lines]
    if not pages:
        return OcrResult(text="")
    lines = [line for page in pages for line in page.lines]
    return OcrResult(
        text="\n".join(lines),
        lines=lines,
        mean_confidence=sum(p.mean_confidence for p in pages) / len(pages),
    )
