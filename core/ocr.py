"""Image preprocessing and Tesseract OCR."""
from dataclasses import dataclass, field

import pytesseract
from PIL import Image, ImageOps, ImageStat
from pytesseract import Output

MIN_WIDTH = 1200
UPSCALE_WIDTH = 1600
DARK_MEAN_BRIGHTNESS = 100
OCR_TIMEOUT_SECONDS = 60


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


def run_ocr(image: Image.Image, tesseract_cmd: str = "") -> OcrResult:
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    data = pytesseract.image_to_data(
        preprocess(image), config="--psm 6", output_type=Output.DICT, timeout=OCR_TIMEOUT_SECONDS
    )
    return result_from_data(data)


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
