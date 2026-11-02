import pytest

from core.redact import redact_text, redact_value


@pytest.mark.parametrize(
    "line",
    [
        "VISA ****1234", "*9215 DISCOVER NETWORK CHARGE", "XXXX 1234", "Card #1234",
        " ".join(["4111"] * 4), "RECH2-6286-3217-0164-7786-7", "A000000152301001",
    ],
)
def test_card_and_long_numbers_are_masked(line):
    out = redact_text(line)
    assert not any(part in out for part in ("1234", "9215", "4111", "6286", "000152"))


@pytest.mark.parametrize(
    "line", ["User ID: 7371", "Password; 922 133", "AUTH CODE: 01376R", "AID: A0001", "MID: 12", "PIN: 9"]
)
def test_login_and_payment_code_lines_are_hidden(line):
    assert redact_text(line) == "[line hidden]"


@pytest.mark.parametrize(
    "line",
    [
        "TOTAL 23.47", "10/13/2026 08:23 PM", "2026-10-13", "Store 408-555-0100", "PINE MARKET",
        "OPIN COFFEE 3.50", "SUBTOTAL 1,234.56", "Tax 8.25%", "Thank you for shopping",
    ],
)
def test_ordinary_lines_are_kept(line):
    assert redact_text(line) == line


def test_keeps_line_structure():
    assert redact_text("A\nPIN: 1\nB") == "A\n[line hidden]\nB"


def test_redact_value_walks_nested_data_and_leaves_numbers():
    data = {"total": 5.0, "field_reason": {"t": "VISA *1234"}, "line_items": [{"name": "*1234", "price": 1.0}], "tip": None}
    assert redact_value(data) == {
        "total": 5.0, "field_reason": {"t": "VISA [card hidden]"}, "line_items": [{"name": "[card hidden]", "price": 1.0}], "tip": None,
    }
