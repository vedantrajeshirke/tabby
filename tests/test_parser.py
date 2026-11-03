from pathlib import Path

import pytest

from core.extraction import load_merchant_keywords
from core.parser import find_amounts, parse

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "ocr_text"
KEYWORDS = load_merchant_keywords()


def parse_fixture(name):
    return parse((FIXTURES / f"{name}.txt").read_text(), merchant_keywords=KEYWORDS)


def receipt_with(extra):
    return parse(f"Some Shop Name\n{extra}\nWidget 5.00\nTOTAL 5.00", merchant_keywords=KEYWORDS)


def test_grocery_total_not_subtotal():
    e = parse_fixture("grocery")
    assert e.document_type == "receipt"
    assert (e.total, e.subtotal, e.tax) == (11.53, 10.65, 0.88)
    assert e.field_confidence["total"] == "high"
    assert e.field_reason["total"] == "found on line 'TOTAL 11.53'"
    assert e.merchant == "Trader Joe"
    assert e.field_confidence["merchant"] == "high"
    assert e.date == "2026-11-03"
    assert e.payment_method == "card"
    assert [(i.name, i.price) for i in e.line_items] == [("BANANAS", 1.67), ("OAT MILK", 3.99), ("FROZEN PIZZA", 4.99)]


def test_savings_and_discounts_ignored():
    e = parse_fixture("savings")
    assert (e.total, e.subtotal, e.tax) == (7.50, 7.00, 0.50)
    assert e.payment_method == "cash"
    assert sum(i.price for i in e.line_items) == e.subtotal  # discounts stay as negative items


def test_restaurant_tip_and_grand_total():
    e = parse_fixture("restaurant_tip")
    assert e.tip == 5.00  # not the suggested tip
    assert e.total == 31.10
    assert e.tax == 2.10
    assert e.merchant == "Luigi's Trattoria"
    assert e.field_confidence["merchant"] == "medium"


def test_multiple_taxes_summed_ignoring_rates_and_total_tax():
    e = parse_fixture("multi_tax")
    assert e.tax == 1.45
    assert e.total == 21.45


def test_zero_balance_due_is_not_the_total():
    assert parse_fixture("paid_balance").total == 12.00


@pytest.mark.parametrize(
    "text, expected",
    [
        ("11/03/2026", "2026-11-03"),
        ("11/03/26", "2026-11-03"),
        ("2026-11-03", "2026-11-03"),
        ("Nov 3, 2026", "2026-11-03"),
        ("November 3, 2026", "2026-11-03"),
        ("3 Nov 2026", "2026-11-03"),
    ],
)
def test_date_formats(text, expected):
    e = receipt_with(text)
    assert e.date == expected
    assert e.field_confidence["date"] == "high"


def test_no_date_is_null_with_no_confidence():
    e = receipt_with("no date on this line")
    assert e.date is None
    assert "date" not in e.field_confidence


def test_several_dates_use_first_with_medium_confidence():
    e = receipt_with("10/01/2026\nReturn by 11/01/2026")
    assert e.date == "2026-10-01"
    assert e.field_confidence["date"] == "medium"


def test_invalid_date_ignored():
    assert receipt_with("13/45/2026").date is None


def test_merchant_heuristic_skips_generic_address_phone_url():
    assert parse_fixture("generic_header").merchant == "Blue Door Books"


def test_generic_keyword_does_not_name_the_merchant():
    assert parse_fixture("generic_keyword").merchant == "Blue Bottle Coffee"


def test_keyword_merchant_longest_match_wins():
    assert parse("UBER EATS\nBurger 12.00\nTOTAL 12.00 today", merchant_keywords=KEYWORDS).merchant == "Uber Eats"


def test_keyword_needs_whole_word():
    e = parse("Geraldi Shoes\nBoots 50.00\nTOTAL 50.00 today", merchant_keywords=KEYWORDS)
    assert e.merchant == "Geraldi Shoes"
    assert e.field_confidence["merchant"] == "medium"


def test_quantity_patterns():
    items = {i.name: (i.quantity, i.price) for i in parse_fixture("quantities").line_items}
    assert items == {
        "MILK": (2, 7.98),
        "EGGS": (3, 6.00),
        "BREAD": (2, 5.00),
        "JUICE": (2, 3.00),
        "BANANA": (3, 0.87),
    }


def test_venmo_screenshot():
    e = parse_fixture("venmo")
    assert e.document_type == "payment_screenshot"
    assert (e.merchant, e.total, e.payment_method, e.date) == ("Jane Doe", 45.00, "venmo", "2026-10-20")
    assert e.line_items == []


def test_zelle_screenshot_amount_before_recipient():
    e = parse_fixture("zelle")
    assert e.document_type == "payment_screenshot"
    assert (e.merchant, e.total, e.payment_method) == ("Sam Patel", 120.50, "zelle")


def test_not_an_expense():
    assert parse_fixture("no_amounts").document_type == "not_an_expense"


def test_too_little_text_unreadable():
    assert parse_fixture("too_short").document_type == "unreadable"


def test_low_confidence_fills_in_nothing_even_with_total_and_date():
    e = parse((FIXTURES / "grocery.txt").read_text(), text_confidence=49.9, min_confidence=50.0, merchant_keywords=KEYWORDS)
    assert e.document_type == "unreadable"
    assert (e.total, e.date, e.merchant, e.tax, e.line_items, e.field_confidence) == (None, None, None, None, [], {})
    assert "below the minimum" in e.field_reason["document_type"]


def test_confidence_at_the_minimum_is_read():
    e = parse((FIXTURES / "grocery.txt").read_text(), text_confidence=50.0, min_confidence=50.0)
    assert (e.document_type, e.total) == ("receipt", 11.53)


def test_card_charge_line_is_medium_total():
    e = parse("Some Shop Name\nWidget 40.00\nSoda 2.00\nCredit $36.94\nmore text here")
    assert (e.total, e.field_confidence["total"]) == (36.94, "medium")
    assert "card charge" in e.field_reason["total"]


def test_total_line_beats_card_charge():
    assert parse("Some Shop Name\nDEBIT 5.00\nTOTAL 9.00\nmore text here").total == 9.00


def test_refund_line_is_not_a_card_charge():
    e = parse("Some Shop Name\nREFUND TO CREDIT CARD 36.94\nItem 5.00\nmore text here")
    assert e.field_confidence["total"] == "low"


def test_total_number_of_items_is_not_a_total():
    e = parse("Some Shop Name\nBALANCE 9.00\nTOTAL NUMBER OF ITEMS 2.00\nmore text")
    assert e.total == 9.00


def test_no_total_keyword_falls_back_low():
    e = parse_fixture("no_total_keyword")
    assert e.total == 12.50
    assert e.field_confidence["total"] == "low"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1,234.56", [(1234.56, False)]),
        ("$ 5.00", [(5.00, False)]),
        ("3.00-", [(3.00, True)]),
        ("(3.00)", [(3.00, True)]),
        ("-$3.00", [(3.00, True)]),
        ("TAX 8.25%", []),
        ("408.555.0100", []),
        ("11.03.26", []),
    ],
)
def test_find_amounts(text, expected):
    assert [(a.value, a.negative) for a in find_amounts(text)] == expected


@pytest.mark.parametrize("marker", ["€5.00", "£5.00", "₹5.00", "CA$5.00", "$5.00", "5.00"])
def test_every_amount_is_usd_whatever_symbol_is_read(marker):
    e = parse(f"Some Shop Name Here\nWidget {marker}\nTOTAL {marker}\nGBP")
    assert e.currency == "USD"
    assert "currency" not in e.field_confidence
    assert e.total == 5.00


def test_cashier_is_not_cash():
    assert receipt_with("Cashier: Bob").payment_method is None


def test_items_above_a_merchant_keyword_line_are_kept():
    e = parse_fixture("keyword_on_item_line")
    assert e.merchant == "Target"
    assert [(i.name, i.quantity, i.price) for i in e.line_items] == [
        ("GG MILK NF", None, 2.50),
        ("ONION Ne", 2, 1.80),
        ("Bag Fee", None, 0.10),
    ]
    assert round(sum(i.price for i in e.line_items), 2) == e.subtotal


def test_noisy_photo_text():
    e = parse_fixture("photo_noise")
    assert e.currency == "USD"  # the stray pound sign isn't next to a number
    assert e.date == "2026-10-27"
    assert (e.total, e.field_confidence["total"]) == (7.59, "high")
    assert e.merchant == "Trader Joe"  # from the footer, curly apostrophe included
    assert e.field_confidence["merchant"] == "medium"
    assert [(i.name, i.quantity, i.price) for i in e.line_items] == [
        ("Tomato Soup", None, 3.49),
        ("TEA BOX", None, 2.50),
        ("PEAR EACH", 2, 1.60),
    ]


def test_bare_balance_is_a_total_but_ranks_below_total():
    assert parse("Some Shop Name\nWidget 9.00\nBALANCE 9.00\nmore text here").total == 9.00
    assert parse("Some Shop Name\nTOTAL 9.00\nGIFT CARD BALANCE 50.00").total == 9.00


def test_merchant_trailing_noise_stripped():
    assert parse("PINE GROCERS ;\nWidget 5.00\nTOTAL 5.00 and more").merchant == "Pine Grocers"


@pytest.mark.parametrize(
    "text, expected",
    [("$3,49", 3.49), ("€12,50", 12.50), ("$1,234.56", 1234.56)],
)
def test_decimal_comma_next_to_symbol(text, expected):
    assert [a.value for a in find_amounts(text)] == [expected]


@pytest.mark.parametrize("text", ["3,49", "$1,234", "12-34-56"])
def test_not_amounts(text):
    assert find_amounts(text) == []


def test_short_dashed_numbers_are_not_dates():
    assert receipt_with("Ref 10-12-26").date is None


def test_taxes_plural_is_tax():
    assert receipt_with("Taxes $2.33").tax == 2.33


def test_number_led_line_is_not_a_merchant():
    assert parse("2600 South Main\nPine Grocers\nWidget 5.00\nTOTAL 5.00").merchant == "Pine Grocers"


def test_ralphs_is_known_even_as_plural_keyword():
    assert parse("RALPHS rewards CUSTOMER\nWidget 5.00\nTOTAL 5.00", merchant_keywords=KEYWORDS).merchant == "Ralphs"


PRINTED_ORDER = """1/20/2027, 09:15 Order details - madeupmart.com
Made Up Mart
Mar 03, 2026 order
Order# 0000-1111
Subtotal $20.00
Taxes $1.50
Total $21.50
https://www.madeupmart.com/orders/0000 1/1"""


def test_print_timestamp_loses_to_the_order_date():
    assert parse(PRINTED_ORDER).date == "2026-03-03"
    assert parse(PRINTED_ORDER).field_confidence["date"] == "high"


def test_labelled_date_wins_over_an_earlier_unlabelled_one():
    text = "MADE UP SHOP\n02/14/2026 RETURN BY\nPurchase date: 01/15/2026\nTOTAL 9.00"
    assert parse(text).date == "2026-01-15"


def test_print_timestamp_is_only_a_last_resort():
    e = parse("1/20/2027, 09:15 Order details - madeupmart.com\nMADE UP SHOP\nTOTAL 9.00")
    assert e.date == "2027-01-20"
    assert e.field_confidence["date"] == "low"
