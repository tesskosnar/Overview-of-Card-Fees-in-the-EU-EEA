"""Consolidated test suite for pipeline.py."""
import pathlib
import sys

import pytest
from fpdf import FPDF

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pipeline  # noqa: E402


def _pdf(rows, widths, path):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=8)
    for row in rows:
        for text, w in zip(row, widths):
            pdf.cell(w, 8, text, border=1)
        pdf.ln(8)
    pdf.output(str(path))
    return path.read_bytes()


def test_table_extraction_path(tmp_path):
    rows = [
        ["Product", "Fee Tier", "General", "Petrol", "Airlines"],
        ["Visa Consumer Debit", "Contactless", "0.20%", "0.20%", "0.20%"],
        ["Visa Consumer Credit", "Contactless", "0.30%", "0.30%", "0.30%"],
        ["Visa Business Debit", "EMV Chip", "1.85%", "0.68%", "1.35%"],
    ]
    b = _pdf(rows, [55, 30, 25, 25, 25], tmp_path / "a.pdf")
    result = pipeline.parse_visa(b, "XX")
    assert result.used_table_extraction
    assert set(result.consumer_debit) == {0.20}
    assert set(result.consumer_credit) == {0.30}


def test_tiered_only_rows_use_capped_max_not_blended_average(tmp_path):
    rows = [
        ["Product", "Fee Tier", "General"],
        ["Visa Consumer Debit", "Transaction value up to and including EUR 20.00", "0.10%"],
        ["Visa Consumer Prepaid", "Transactions value over EUR 20.00", "0.20%"],
        ["Visa Consumer Credit", "Transaction value up to and including EUR 20.00", "0.20%"],
        ["Visa Consumer Deferred Debit", "Transactions value over EUR 20.00", "0.30%"],
    ]
    b = _pdf(rows, [55, 90, 25], tmp_path / "es.pdf")
    result = pipeline.parse_visa(b, "ES")
    db = pipeline._stat_block(result.consumer_debit, pipeline._headline_for("consumer_debit", result.consumer_debit, result.consumer_debit_headline, "ES"))
    cb = pipeline._stat_block(result.consumer_credit, pipeline._headline_for("consumer_credit", result.consumer_credit, result.consumer_credit_headline, "ES"))
    assert db["avg"] == 0.20
    assert cb["avg"] == 0.30
    assert db["min"] == 0.10 and db["max"] == 0.20


def test_unlabeled_commercial_rows_do_not_contaminate_capped_consumer_buckets(tmp_path):
    rows = [
        ["Product", "Fee Tier", "General"],
        ["Visa Consumer Debit", "Transaction value up to and including EUR 20.00", "0.10%"],
        ["Visa Consumer Prepaid", "Transactions value over EUR 20.00", "0.20%"],
        ["Visa Consumer Credit", "Transaction value up to and including EUR 20.00", "0.20%"],
        ["Visa Consumer Deferred Debit", "Transactions value over EUR 20.00", "0.30%"],
        ["Non-Sector Specific", "Standard", "0.76%"],
        ["Sector Specific", "Retailer - Food", "0.65%"],
        ["", "Retailer - Other", "0.76%"],
        ["", "Petrol Station", "0.65%"],
        ["", "Night Club", "0.76%"],
    ]
    b = _pdf(rows, [60, 90, 25], tmp_path / "es2.pdf")
    result = pipeline.parse_visa(b, "ES")
    assert 0.76 not in result.consumer_credit and 0.65 not in result.consumer_credit
    cb = pipeline._stat_block(result.consumer_credit, pipeline._headline_for("consumer_credit", result.consumer_credit, result.consumer_credit_headline, "ES"))
    assert cb["avg"] == 0.30
    assert any("dropped" in w for w in result.warnings)


def test_premium_commercial_tiers_excluded_from_headline_average(tmp_path):
    rows = [
        ["Product", "Fee Tier", "General"],
        ["Visa Business Debit", "EMV Chip", "1.30%"],
        ["", "Standard", "1.65%"],
        ["Visa Platinum Business Debit", "EMV Chip", "1.55%"],
        ["", "Standard", "1.90%"],
        ["Visa Infinite Business Debit", "EMV Chip", "1.65%"],
        ["", "Standard", "2.00%"],
    ]
    b = _pdf(rows, [60, 50, 40], tmp_path / "at.pdf")
    result = pipeline.parse_visa(b, "AT")
    block = pipeline._stat_block(result.commercial, result.commercial_headline)
    assert block["avg"] < 1.6
    assert block["max"] == 2.00


def test_flat_fee_row_surfaces_instead_of_vanishing(tmp_path):
    rows = [
        ["Product", "Fee Tier", "General"],
        ["Visa Consumer Debit", "Contactless", "EUR 0.02"],
        ["Visa Consumer Credit", "Contactless", "0.30%"],
    ]
    b = _pdf(rows, [55, 60, 60], tmp_path / "nl.pdf")
    result = pipeline.parse_visa(b, "NL")
    assert result.consumer_debit == []
    assert result.consumer_debit_flat_fee is not None and "0.02" in result.consumer_debit_flat_fee
    assert any("flat fee" in w for w in result.warnings)


def test_cap_amount_surfaces_as_warning(tmp_path):
    rows = [
        ["Product", "Fee Tier", "General"],
        ["Visa Consumer Debit", "Standard", "0.20% (capped at GBP 0.50)"],
    ]
    b = _pdf(rows, [55, 60, 70], tmp_path / "gb.pdf")
    result = pipeline.parse_visa(b, "IE")
    assert any("capped at" in w and "GBP 0.50" in w for w in result.warnings)


@pytest.mark.parametrize("phrasing", ["0.20% (capped at EUR 0.02)", "0.20% Max EUR 0.02", "0.20% (Maximum of EUR 0.02)"])
def test_cap_detection_covers_max_phrasing_variant(tmp_path, phrasing):
    rows = [["Product", "Fee Tier", "General"], ["Visa Consumer Debit", "Standard", phrasing]]
    b = _pdf(rows, [55, 60, 70], tmp_path / f"nl_{hash(phrasing)}.pdf")
    result = pipeline.parse_visa(b, "NL")
    assert any("EUR 0.02" in w for w in result.warnings)


def test_min_max_are_attributed_to_the_category_that_produced_them(tmp_path):
    rows = [
        ["Product", "Fee Tier", "General", "Petrol", "Airlines"],
        ["Visa Business Debit", "EMV Chip", "1.85%", "0.68%", "1.35%"],
        ["Visa Corporate", "Standard", "2.05%", "0.68%", "1.35%"],
    ]
    b = _pdf(rows, [55, 30, 25, 25, 25], tmp_path / "de.pdf")
    result = pipeline.parse_visa(b, "XX")
    block = pipeline._stat_block(result.commercial, result.commercial_headline, result.commercial_labeled)
    assert block["min"] == 0.68
    assert block["max"] == 2.05
    assert "min_label" in block and "max_label" in block


def test_switzerland_is_exempt_from_the_eu_legal_cap_filter(tmp_path):
    rows = [["Product", "Fee Tier", "General"], ["Visa Consumer Credit", "Standard", "0.55%"]]
    b = _pdf(rows, [55, 60, 60], tmp_path / "ch.pdf")
    result = pipeline.parse_visa(b, "CH")
    assert result.consumer_credit == [0.55]
    assert not any("dropped" in w for w in result.warnings)


def test_ifr_capped_lookup_excludes_switzerland():
    assert "CH" not in pipeline.IFR_CAPPED_ISO2
    assert "DE" in pipeline.IFR_CAPPED_ISO2
    assert "NO" in pipeline.IFR_CAPPED_ISO2


def test_min_max_labels_include_additional_fixed_fee(tmp_path):
    rows = [
        ["Product", "Fee Tier", "General"],
        ["Visa Business Credit", "Small Market Expense", "0.30%"],
        ["Visa Infinite Business Credit", "Standard, Tier-1", "0.86% + EUR 0.03"],
    ]
    b = _pdf(rows, [70, 70, 50], tmp_path / "es3.pdf")
    result = pipeline.parse_visa(b, "ES")
    block = pipeline._stat_block(result.commercial, result.commercial_headline, result.commercial_labeled)
    assert "+ EUR 0.03" in block["max_label"]


# Switzerland's real Visa PDF splits consumer debit across acceptance
# channels (Card Present - General / Token, Card Absent) IN THE SAME
# CELL as the product name, and V PAY is a separate niche debit brand.
# A user comparing the live dashboard to the source PDF caught this: the
# headline blended all channels and both brands together (0.20/0.31/0.31/
# 0.12/0.31/0.31 -> ~0.26%) instead of reporting the 0.20% "General" rate
# that's actually on the price list.
SWITZERLAND_REAL_ROWS = [
    ["Product", "Fee Tier", "General", "Everyday Spend", "Airlines"],
    ["Visa Consumer Debit", "Card Present - General", "0.20%", "0.12% (Capped CHF 0.36)", "-"],
    ["", "Card Present - Token", "0.31%", "-", "-"],
    ["", "Card Absent", "0.31%", "-", "-"],
    ["V PAY Debit", "Card Present - General", "0.12% (Capped CHF 0.36)", "-", "-"],
    ["V PAY Prepaid", "Card Present - Token", "0.31%", "-", "-"],
    ["", "Card Absent", "0.31%", "-", "-"],
]


def test_switzerland_channel_and_niche_brand_blend(tmp_path):
    b = _pdf(SWITZERLAND_REAL_ROWS, [40, 50, 35, 45, 25], tmp_path / "ch2.pdf")
    result = pipeline.parse_visa(b, "CH")
    block = pipeline._stat_block(result.consumer_debit, pipeline._headline_for("consumer_debit", result.consumer_debit, result.consumer_debit_headline, "CH"))
    assert block["avg"] == 0.20, f"expected the General-channel, main-brand rate (0.20%), got {block['avg']}"
    assert block["min"] == 0.12 and block["max"] == 0.31, "full range across channels/brands must still be preserved"


def test_carry_forward_does_not_leak_channel_text_into_continuation_rows(tmp_path):
    """The deeper root cause: a product+channel combined in one row must
    not drag the channel text into rows that continue with a DIFFERENT
    channel below it."""
    b = _pdf(SWITZERLAND_REAL_ROWS, [40, 50, 35, 45, 25], tmp_path / "ch3.pdf")
    parsed = pipeline.parse_pdf(b)
    rows = pipeline.carry_forward_product_prefix(parsed.rows, pipeline.PRODUCT_MARKERS)
    token_row = next(r for r in rows if "Token" in r.label and r.values == [0.31] and "V PAY" not in r.label)
    assert "General" not in token_row.label, f"channel text leaked forward: {token_row.label!r}"


# Switzerland's real Visa PDF names its commercial products literally "Visa
# Commercial Debit" / "Visa Commercial Credit" -- unlike every other country
# tested so far, which used "Business"/"Corporate"/"Platinum"/"Infinite".
# "commercial" was never in COMMERCIAL_HINTS, so these rows fell through to
# "unclassified" and the whole commercial category came back empty.
def test_visa_commercial_product_name_is_classified_correctly(tmp_path):
    rows = [
        ["Product", "Fee Tier", "General"],
        ["Visa Commercial Debit", "Card Present - Token", "0.29%"],
        ["Visa Commercial Credit", "Secure Electronic Commerce", "0.35%"],
    ]
    b = _pdf(rows, [55, 60, 40], tmp_path / "ch4.pdf")
    result = pipeline.parse_visa(b, "CH")
    assert result.commercial == [0.29, 0.35], "rows literally named 'Commercial' must classify into the commercial bucket"


# Switzerland's commercial debit "Card Present - General" tier is a flat
# CHF amount that scales with transaction size (CHF 0.05/0.20/0.28/0.55 for
# <=20/<=50/<=100/>100), not a percentage at all. FLAT_FEE_RE only matched
# EUR/GBP/£ -- CHF rows had no "%" and didn't match the flat-fee pattern
# either, so _row_from_table_row() silently dropped them before carry-
# forward ever ran, taking the "Visa Commercial Debit" product name with
# them and orphaning every row below it.
def test_flat_fee_detection_covers_non_euro_currency_codes(tmp_path):
    rows = [
        ["Product", "Fee Tier", "General"],
        ["Visa Commercial Debit", "Card Present - General (<=CHF 20)", "CHF 0.05"],
        ["", "Card Present - Token - Secure", "0.29%"],
    ]
    b = _pdf(rows, [55, 70, 40], tmp_path / "ch5.pdf")
    result = pipeline.parse_visa(b, "CH")
    assert result.commercial_flat_fee is not None and "CHF 0.05" in result.commercial_flat_fee
    assert result.commercial == [0.29], "the product name must survive to the next row even when the first row is a non-EUR flat fee"
