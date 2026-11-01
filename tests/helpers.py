"""Builders for real test files, so these tests exercise the actual libraries."""
import io

from PIL import Image, ImageDraw, ImageFont


def text_pdf(lines: list[str], pages: int = 1) -> bytes:
    """A minimal valid PDF with a real text layer and no extra dependencies."""
    stream = "BT /F1 12 Tf 14 TL 50 750 Td " + " ".join(f"({line}) Tj T*" for line in lines) + " ET"
    objects = {1: "<< /Type /Catalog /Pages 2 0 R >>", 3: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               4: f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"}
    page_ids = [5 + i for i in range(pages)]
    kids = " ".join(f"{i} 0 R" for i in page_ids)
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>"
    for i in page_ids:
        objects[i] = ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                      "/Contents 4 0 R /Resources << /Font << /F1 3 0 R >> >> >>")
    out = b"%PDF-1.4\n"
    offsets = {}
    for num in sorted(objects):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n{objects[num]}\nendobj\n".encode()
    xref = len(out)
    count = len(objects) + 1
    out += f"xref\n0 {count}\n0000000000 65535 f \n".encode()
    for num in sorted(objects):
        out += f"{offsets[num]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {count} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def receipt_image(lines: list[str], background="white", ink="black") -> Image.Image:
    font = ImageFont.load_default(size=40)
    image = Image.new("RGB", (1000, 80 + 60 * len(lines)), background)
    draw = ImageDraw.Draw(image)
    for i, line in enumerate(lines):
        draw.text((40, 40 + 60 * i), line, fill=ink, font=font)
    return image


def image_bytes(image: Image.Image, fmt: str = "PNG", **kwargs) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, **kwargs)
    return buffer.getvalue()
