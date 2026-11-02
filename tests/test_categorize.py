import pytest

from core.categorize import categorize, load_config, normalize_merchant

CONFIG = load_config()
RULES = CONFIG["rules"]


def decide(merchant="Unknown Shop", doc="receipt", text="", overrides=None):
    return categorize(merchant, doc, text, overrides or {}, RULES)


def test_override_beats_doc_type_and_rule():
    overrides = {"UBER": "Travel"}
    assert decide("Uber", "payment_screenshot", overrides=overrides) == ("Travel", "override")


def test_doc_type_beats_rule():
    assert decide("Uber", "payment_screenshot") == ("Transfers to People", "doc_type")


def test_rule_beats_default():
    assert decide("Safeway") == ("Groceries", "rule")


def test_default():
    assert decide("Unknown Shop") == ("Other", "default")


def test_no_merchant_is_default():
    assert decide(None) == ("Other", "default")


def test_uber_eats_is_delivery_not_transport():
    assert decide("Uber Eats") == ("Food Delivery", "rule")
    assert decide("UBER") == ("Transport", "rule")


def test_case_insensitive():
    assert decide("trader joe's") == ("Groceries", "rule")


def test_generic_keyword_categorizes_even_though_it_never_names_a_merchant():
    assert decide("Blue Bottle Coffee") == ("Restaurants & Cafes", "rule")


def test_keyword_in_top_lines_counts():
    assert decide("Unknown Shop", text="Unknown Shop\nSAFEWAY store 12") == ("Groceries", "rule")


def test_keyword_below_top_lines_does_not_count():
    text = "\n".join(["line"] * 10 + ["SAFEWAY"])
    assert decide("Unknown Shop", text=text) == ("Other", "default")


def test_merchant_outranks_stray_word_in_the_header():
    text = "Safeway\nNext to the METRO station"
    assert decide("Safeway", text=text) == ("Groceries", "rule")


def test_keyword_needs_whole_word():
    assert decide("Geraldine Boutique") == ("Other", "default")
    assert decide("Tuber Farm") == ("Other", "default")


def test_override_matches_normalized_merchant():
    overrides = {normalize_merchant("Joe's Deli"): "Groceries"}
    assert decide("JOE'S   DELI #1234", overrides=overrides) == ("Groceries", "override")


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("  blue   bottle ", "BLUE BOTTLE"),
        ("Safeway #1234", "SAFEWAY"),
        ("SQ *Blue Bottle", "BLUE BOTTLE"),
        ("TST* Pizza Place", "PIZZA PLACE"),
        ("Store 12", "STORE 12"),
    ],
)
def test_normalize_merchant(raw, expected):
    assert normalize_merchant(raw) == expected


def test_every_rule_uses_a_listed_category():
    assert {rule["category"] for rule in RULES} <= set(CONFIG["categories"])
    assert "Transfers to People" in CONFIG["categories"] and "Other" in CONFIG["categories"]
