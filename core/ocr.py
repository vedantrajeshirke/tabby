"""Image preprocessing and Tesseract OCR."""
import time
from dataclasses import dataclass, field

import numpy as np
import pytesseract
from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageStat
from pytesseract import Output

MIN_WIDTH = 1200
UPSCALE_WIDTH = 1600
MAX_SIDE = 2400  # receipts read just as well at this size, and far faster on a small server
MAX_UPSCALED_SIDE = 2600  # upscaling a tall, narrow receipt stops here
DARK_MEAN_BRIGHTNESS = 100
OCR_TIMEOUT_SECONDS = 45
OCR_BUDGET_SECONDS = 80  # all passes together; the hosted front end gives up on a request at about 120
MIN_SECOND_PASS_SECONDS = 10
TOO_SLOW = "This photo took too long to read. Crop it closer to the receipt and try again, or enter the expense manually."
PAPER_THUMB_SIDE = 300
PAPER_MIN_SHARE = 0.04  # of the photo; anything smaller isn't the receipt
PAPER_MAX_SHARE = 0.85  # anything bigger means the photo is already cropped
PAPER_MIN_FILL = 0.45  # of its bounding box, so a bright, ragged patch of background isn't taken for paper
PAPER_MARGIN = 0.03
PAPER_MAX_REGIONS = 200
CONFIDENT_ENOUGH = 90  # above this, a second pass on the crop is not worth the wait
CROP_MIN_WORD_CONF = 60
CROP_MIN_WORD_CHARS = 3
CROP_MIN_WORDS = 5
CROP_MARGIN = 60
CROP_OUTLIER_SHARE = 0.05
CROP_MAX_AREA_SHARE = 0.8  # a bigger crop wouldn't remove enough background to justify a second pass


class OcrTooSlow(Exception):
    """Reading ran past its time limit."""


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


def _otsu_threshold(pixels: np.ndarray) -> int:
    hist = np.bincount(pixels.ravel(), minlength=256).astype(float)
    count = hist.cumsum()
    weighted = (hist * np.arange(256)).cumsum()
    between = (weighted[-1] * count - weighted * count[-1]) ** 2 / (count * (count[-1] - count) + 1e-9)
    return int(between.argmax())


def _regions(mask: Image.Image):
    """(area, box) of each white region, found by flood-filling them one at a time."""
    work = mask.copy()
    for _ in range(PAPER_MAX_REGIONS):
        pixels = np.asarray(work)
        start = np.flatnonzero(pixels == 255)
        if not start.size:
            return
        y, x = divmod(int(start[0]), work.width)
        ImageDraw.floodfill(work, (x, y), 128)
        ys, xs = np.nonzero(np.asarray(work) == 128)
        yield len(xs), (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        ImageDraw.floodfill(work, (x, y), 0)


def find_paper(gray: Image.Image) -> tuple[int, int, int, int] | None:
    """Box around the receipt when it's light paper on a darker background, or None if there's nothing to cut."""
    small = ImageOps.contain(gray, (PAPER_THUMB_SIDE, PAPER_THUMB_SIDE))
    pixels = np.asarray(small)
    light = Image.fromarray(np.where(pixels > _otsu_threshold(pixels), 255, 0).astype(np.uint8))
    # Opening removes specks of background; closing fills the printed text inside the paper.
    light = light.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    light = light.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))
    found = max(_regions(light), default=None)
    if found is None:
        return None
    area, (left, top, right, bottom) = found
    photo_area = small.width * small.height
    box_area = (right - left) * (bottom - top)
    if area < PAPER_MIN_SHARE * photo_area or box_area > PAPER_MAX_SHARE * photo_area or area < PAPER_MIN_FILL * box_area:
        return None
    scale = gray.width / small.width
    margin = PAPER_MARGIN * max(gray.size)
    return (
        max(0, round(left * scale - margin)),
        max(0, round(top * scale - margin)),
        min(gray.width, round(right * scale + margin)),
        min(gray.height, round(bottom * scale + margin)),
    )


def preprocess(image: Image.Image) -> Image.Image:
    """Grayscale, resize, stretch contrast, invert dark-mode screenshots."""
    gray = _flatten_alpha(image).convert("L")
    if max(gray.size) > MAX_SIDE:
        gray = ImageOps.contain(gray, (MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    elif gray.width < MIN_WIDTH:
        scale = min(UPSCALE_WIDTH / gray.width, MAX_UPSCALED_SIDE / max(gray.size))
        if scale > 1:
            gray = gray.resize((round(gray.width * scale), round(gray.height * scale)), Image.Resampling.LANCZOS)
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


def _image_to_data(image: Image.Image, timeout: float = OCR_TIMEOUT_SECONDS) -> dict:
    try:
        return pytesseract.image_to_data(image, config="--psm 6", output_type=Output.DICT, timeout=timeout)
    except RuntimeError as e:
        if "timeout" in str(e).lower():
            raise OcrTooSlow from e
        raise


def run_ocr(image: Image.Image, tesseract_cmd: str = "") -> OcrResult:
    """Cut the receipt out of its background, OCR it, and, if that was unsure, try again cropped to the text."""
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    started = time.monotonic()
    gray = _flatten_alpha(image).convert("L")
    paper = find_paper(gray)
    processed = preprocess(gray.crop(paper) if paper else gray)
    data = _image_to_data(processed)
    result = result_from_data(data)
    box = None if paper else crop_box(data, processed.size)
    time_left = OCR_BUDGET_SECONDS - (time.monotonic() - started)
    if box is None or result.mean_confidence >= CONFIDENT_ENOUGH or time_left < MIN_SECOND_PASS_SECONDS:
        return result
    try:
        cropped = result_from_data(_image_to_data(processed.crop(box), min(time_left, OCR_TIMEOUT_SECONDS)))
    except OcrTooSlow:
        return result  # the first read is still usable
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
