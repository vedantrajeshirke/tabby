"""Request bodies. Limits keep bad input out of the database; meaning is checked in core/."""
from datetime import date as Date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.models import Extraction, Settings

Amount = Annotated[float, Field(ge=-9_999_999_999, le=9_999_999_999)]
PaymentMethod = Literal["card", "cash", "venmo", "zelle", "paypal", "other"]
MAX_RAW_TEXT = 100_000


def invalid_fields_message(errors: list[dict]) -> tuple[str, list[str]]:
    """Name the bad fields, without repeating the submitted values."""
    fields = sorted({str(e["loc"][-1]) for e in errors if e["loc"] and e["type"] != "json_invalid"})
    if not fields:
        return "This request couldn't be read. Refresh the page and try again.", []
    return f"Please check these fields: {', '.join(fields)}.", fields


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class LineItemIn(Strict):
    name: str = Field(max_length=500)
    quantity: float | None = None
    price: float | None = None


class ExtractionIn(Strict):
    document_type: Literal["receipt", "payment_screenshot", "not_an_expense", "unreadable", "manual"]
    merchant: str | None = Field(default=None, max_length=200)
    date: str | None = Field(default=None, max_length=10)
    currency: str | None = Field(default=None, max_length=3)
    subtotal: Amount | None = None
    tax: Amount | None = None
    tip: Amount | None = None
    total: Amount | None = None
    payment_method: PaymentMethod | None = None
    line_items: list[LineItemIn] = Field(default_factory=list, max_length=500)
    field_confidence: dict[str, Literal["high", "medium", "low"]] = Field(default_factory=dict, max_length=20)
    field_reason: dict[str, Annotated[str, Field(max_length=2000)]] = Field(default_factory=dict, max_length=20)
    text_source: Literal["pdf_text", "ocr"] = "ocr"
    text_confidence: float = Field(default=0.0, ge=0, le=100)
    raw_text: str = Field(default="", max_length=MAX_RAW_TEXT)

    def to_extraction(self) -> Extraction:
        return Extraction.from_dict(self.model_dump())


class ExpenseForm(Strict):
    """The confirm form. `extraction` is what the app read, sent back unchanged."""

    merchant: str = Field(default="", max_length=200)
    date: Date
    total: Amount | None = None
    subtotal: Amount | None = None
    tax: Amount | None = None
    tip: Amount | None = None
    payment_method: PaymentMethod | None = None
    note: str = Field(default="", max_length=1000)
    category: str | None = Field(default=None, max_length=100)
    always_use_category: bool = False
    client_today: Date | None = None
    extraction: ExtractionIn | None = None
    file_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")  # for duplicate checks only


class ExpenseEdit(Strict):
    """Only the fields being changed."""

    merchant: str | None = Field(default=None, max_length=200)
    date: Date | None = None
    total: Amount | None = None
    subtotal: Amount | None = None
    tax: Amount | None = None
    tip: Amount | None = None
    payment_method: PaymentMethod | None = None
    note: str | None = Field(default=None, max_length=1000)
    category: str | None = Field(default=None, max_length=100)
    client_today: Date | None = None


class SettingsIn(Strict):
    name: str = Field(default="", max_length=100)
    monthly_budget: float | None = Field(default=None, ge=0, le=9_999_999_999)
    cycle_start_day: int = Field(default=1, ge=1, le=28)

    def to_settings(self) -> Settings:
        return Settings(self.name, self.monthly_budget or None, self.cycle_start_day)
