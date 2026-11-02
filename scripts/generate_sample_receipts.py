"""Writes fixtures/sample_receipts/. Everything in them is made up. Run: python -m scripts.generate_sample_receipts"""
from pathlib import Path

from PIL import ImageFilter

from tests.helpers import image_bytes, receipt_image, text_pdf

OUT = Path(__file__).resolve().parent.parent / "fixtures" / "sample_receipts"

GROCERY = [
    "SAMPLE GROCER", "123 EXAMPLE STREET", "10/14/2026", "", "APPLES 3.00", "BREAD 4.25", "MILK 3.75",
    "SUBTOTAL 11.00", "TAX 0.88", "TOTAL 11.88", "CARD SALE",
]
RESTAURANT = ["NOODLE HOUSE EXAMPLE", "10/15/2026", "SOUP 12.00", "TEA 3.00", "SUBTOTAL 15.00", "TAX 1.20", "TIP 3.00", "TOTAL 19.20"]
MISMATCH = ["EXAMPLE MARKET", "10/16/2026", "SUBTOTAL 30.00", "TAX 2.00", "TOTAL 40.00"]
PAYMENT = ["Venmo", "You paid Sam Example", "$45.00", "Oct 17, 2026", "Dinner share"]
NOT_RECEIPT = ["Meeting notes", "Bring the project plan", "Call the team on Tuesday", "Water the plants"]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "grocery_photo.png": image_bytes(receipt_image(GROCERY)),
        "restaurant_digital.pdf": text_pdf(RESTAURANT),
        "amounts_dont_add_up.png": image_bytes(receipt_image(MISMATCH)),
        "venmo_screenshot.png": image_bytes(receipt_image(PAYMENT)),
        "not_a_receipt.png": image_bytes(receipt_image(NOT_RECEIPT)),
        "blurry_photo.png": image_bytes(receipt_image(GROCERY).filter(ImageFilter.GaussianBlur(14))),
    }
    for name, data in files.items():
        (OUT / name).write_bytes(data)
    print(f"Wrote {len(files)} files to {OUT}")


if __name__ == "__main__":
    main()
