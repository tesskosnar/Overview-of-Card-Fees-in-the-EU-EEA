"""
Consolidated test suite for pipeline.py (the single-file scraper used
by both the GitHub Actions workflow and the Colab notebook).

Covers, with real assertions (not just "does it run"):
- PDF table-extraction path, via a synthetic PDF with an actual ruled
  grid (pdfplumber's extract_tables(), which is what real Visa PDFs need).
- discover_visa()'s name/alias matching.
- build_output()'s per-country and summary aggregation, including that
  all 30 countries are always listed even with partial data.
- plausibility_warnings() flagging an out-of-range consumer rate.
"""
import pathlib
import sys

import pytest
from fpdf import FPDF

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pipeline  # noqa: E402


# ---------------------------------------------------------------
# PDF table extraction
# ---------------------------------------------------------------

ROWS = [
    ["Product", "Fee Tier", "General", "Petrol", "Airlines"],
    ["Visa Consumer Debit", "Contactless", "0.20%", "0.20%", "0.20%"],
    ["", "Standard", "0.20%", "0.20%", "0.20%"],
    ["Visa Consumer Credit", "Contactless", "0.30%", "0.30%", "0.30%"],
    ["", "Standard", "0.30%", "0.30%", "0.30%"],
    ["Visa Business Debit", "EMV Chip", "1.85%", "0.68%", "1.35%"],
    ["Visa Corporate", "Standard", "2.05%", "0.68%", "1.35%"],
]


def _build_synthetic_pdf(path: pathlib.Path) -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    col_widths = [55, 30, 25, 25, 25]
    row_h = 8
    for row in ROWS:
        for text, w in zip(row, col_widths):
            pdf.cell(w, row_h, text, border=1)
        pdf.ln(row_h)
    pdf.output(str(path))


def test_table_extraction_path(tmp_path):
    pdf_path = tmp_path / "synthetic_visa_table.pdf"
    _build_synthetic_pdf(pdf_path)

    result = pipeline.parse_visa(pdf_path.read_bytes(), "XX")
    assert result.used_table_extraction, "expected extract_tables() to detect the ruled grid"
    assert set(result.consumer_debit) == {0.20}
    assert set(result.consumer_credit) == {0.30}
    assert set(result.commercial) == {1.85, 0.68, 1.35, 2.05}


# Spain publishes consumer rates as value-tiered rows only ("<=EUR 20" /
# ">EUR 20"), with NO unqualified "General" row. A naive average of every
# matched percentage (0.10% and 0.20% for debit) produces 0.15% -- a number
# that matches neither tier and looked like a parsing bug to a user
# comparing against the PDF. The fix: prefer the un-tiered row as the
# headline average where one exists, and fall back to the legally-capped
# maximum (never the blended average) when every row is conditional.
SPAIN_TIERED_ROWS = [
    ["Product", "Fee Tier", "General"],
    ["Visa Consumer Debit", "Transaction value up to and including EUR 20.00", "0.10%"],
    ["Visa Consumer Prepaid", "Transactions value over EUR 20.00", "0.20%"],
    ["Visa Consumer Credit", "Transaction value up to and including EUR 20.00", "0.20%"],
    ["Visa Consumer Deferred Debit", "Transactions value over EUR 20.00", "0.30%"],
]


def test_tiered_only_rows_use_capped_max_not_blended_average(tmp_path):
    pdf_path = tmp_path / "synthetic_spain_table.pdf"
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=9)
    col_widths = [55, 90, 25]
    row_h = 8
    for row in SPAIN_TIERED_ROWS:
        for text, w in zip(row, col_widths):
            pdf.cell(w, row_h, text, border=1)
        pdf.ln(row_h)
    pdf.output(str(pdf_path))

    result = pipeline.parse_visa(pdf_path.read_bytes(), "ES")
    debit_block = pipeline._stat_block(
        result.consumer_debit,
        pipeline._headline_for("consumer_debit", result.consumer_debit, result.consumer_debit_headline),
    )
    credit_block = pipeline._stat_block(
        result.consumer_credit,
        pipeline._headline_for("consumer_credit", result.consumer_credit, result.consumer_credit_headline),
    )
    assert debit_block["avg"] == 0.20, "should report the standard tier, not the (0.10+0.20)/2=0.15 blend"
    assert credit_block["avg"] == 0.30, "should report the standard tier, not the (0.20+0.30)/2=0.25 blend"
    assert debit_block["min"] == 0.10 and debit_block["max"] == 0.20, "full range must still be preserved"


# Romania's rate sheet has a "General" column and a separate "Government
# Payments" column for the SAME product row -- but "Government Payments"
# only appears once, in the table header, never repeated in each data row.
# A per-row keyword check alone can't catch this. The positional rule (first
# value in a row is the general/headline rate) is the fallback that does.
ROMANIA_STYLE_ROWS = [
    ["Product", "Fee Tier", "General", "Government Payments"],
    ["Visa Consumer Debit", "Contactless", "0.20%", "0.10% capped at RON 20.00"],
    ["Visa Consumer Credit", "Contactless", "0.30%", "0.20%"],
]


def test_unlabeled_second_column_does_not_pollute_headline_average(tmp_path):
    pdf_path = tmp_path / "synthetic_romania_table.pdf"
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=8)
    col_widths = [50, 35, 35, 75]
    row_h = 8
    for row in ROMANIA_STYLE_ROWS:
        for text, w in zip(row, col_widths):
            pdf.cell(w, row_h, text, border=1)
        pdf.ln(row_h)
    pdf.output(str(pdf_path))

    result = pipeline.parse_visa(pdf_path.read_bytes(), "RO")
    debit_block = pipeline._stat_block(
        result.consumer_debit,
        pipeline._headline_for("consumer_debit", result.consumer_debit, result.consumer_debit_headline),
    )
    assert result.consumer_debit == [0.20, 0.10], "both published values should still be captured for min/max"
    assert debit_block["avg"] == 0.20, "the unlabeled Government Payments column must not blend into the headline rate"
    assert any("capped at" in w for w in result.warnings), "the RON 20.00 cap should surface as a warning"


def test_cap_amount_surfaces_as_warning_without_corrupting_the_rate(tmp_path):
    rows = [
        ["Product", "Fee Tier", "General"],
        ["Visa Consumer Debit", "Standard", "0.20% (capped at GBP 0.50)"],
    ]
    pdf_path = tmp_path / "synthetic_uk_cap_table.pdf"
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=9)
    for row in rows:
        for text, w in zip(row, [55, 60, 70]):
            pdf.cell(w, 8, text, border=1)
        pdf.ln(8)
    pdf.output(str(pdf_path))

    result = pipeline.parse_visa(pdf_path.read_bytes(), "GB")
    debit_block = pipeline._stat_block(
        result.consumer_debit,
        pipeline._headline_for("consumer_debit", result.consumer_debit, result.consumer_debit_headline),
    )
    assert debit_block["avg"] == 0.20
    assert any("capped at" in w and "GBP 0.50" in w for w in result.warnings)


# The Netherlands publishes "0.20% capped at EUR 0.02" for consumer debit --
# a cap so tight it binds on essentially any real transaction over EUR 10,
# making the percentage figure alone actively misleading. Some rate sheets
# phrase this as "Max EUR X" rather than "capped at EUR X"; both must be caught.
@pytest.mark.parametrize("phrasing", [
    "0.20% (capped at EUR 0.02)",
    "0.20% Max EUR 0.02",
    "0.20% (Maximum of EUR 0.02)",
])
def test_cap_detection_covers_max_phrasing_variant(tmp_path, phrasing):
    rows = [
        ["Product", "Fee Tier", "General"],
        ["Visa Consumer Debit", "Standard", phrasing],
    ]
    pdf_path = tmp_path / "synthetic_nl_cap_table.pdf"
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=9)
    for row in rows:
        for text, w in zip(row, [55, 60, 70]):
            pdf.cell(w, 8, text, border=1)
        pdf.ln(8)
    pdf.output(str(pdf_path))

    result = pipeline.parse_visa(pdf_path.read_bytes(), "NL")
    assert any("EUR 0.02" in w for w in result.warnings), f"cap not detected for phrasing: {phrasing!r}"


# ---------------------------------------------------------------
# discover_visa
# ---------------------------------------------------------------

VISA_HTML = """
<html><body>
<a href="/dam/PDF/fees-and-interchange/april-25/austria-apr25.pdf">Austria Interchange Fees</a>
<a href="/dam/PDF/fees-and-interchange/april-25/germany-jan26.pdf">Germany Interchange Fees</a>
<a href="/dam/PDF/fees-and-interchange/april-25/denmark-apr25.pdf">Denmark, Greenland &amp; Faroe Islands Interchange Fees</a>
</body></html>
"""


def test_discover_visa_matches_name_and_alias():
    countries = [c for c in pipeline.EU_EEA_COUNTRIES if c.iso2 in {"AT", "DE", "DK"}]
    found = pipeline.discover_visa(VISA_HTML, "https://www.visa.co.uk/x.html", countries)
    assert found["AT"].endswith("austria-apr25.pdf")
    assert found["DE"].endswith("germany-jan26.pdf")
    assert found["DK"].endswith("denmark-apr25.pdf"), "Denmark alias match failed"


# ---------------------------------------------------------------
# aggregate / build_output
# ---------------------------------------------------------------

def test_build_output_lists_all_30_countries_even_with_partial_data():
    r1 = pipeline.CountryRateResult(iso2="AT", consumer_debit=[0.2], consumer_credit=[0.3], commercial=[1.5], used_table_extraction=True)
    r2 = pipeline.CountryRateResult(iso2="DE", consumer_debit=[0.2], consumer_credit=[0.3], commercial=[1.8], used_table_extraction=True)

    output = pipeline.build_output([r1, r2])

    assert len(output["countries"]) == 30
    assert output["summary"]["visa"]["consumer_debit"]["avg"] == 0.2
    assert output["summary"]["visa"]["commercial"]["n_countries"] == 2

    at_entry = next(c for c in output["countries"] if c["iso2"] == "AT")
    assert at_entry["visa"]["consumer_debit"]["avg"] == 0.2
    fr_entry = next(c for c in output["countries"] if c["iso2"] == "FR")
    assert fr_entry.get("visa") is None, "countries with no data should have no visa block, not a fabricated one"


# ---------------------------------------------------------------
# plausibility warnings
# ---------------------------------------------------------------

@pytest.mark.parametrize("bucket,value,should_warn", [
    ("consumer_debit", 0.20, False),
    ("consumer_debit", 1.85, True),   # a commercial-looking number leaking into debit = likely mis-parse
    ("consumer_credit", 0.30, False),
    ("consumer_credit", 0.05, True),
])
def test_plausibility_warnings_flag_out_of_range_consumer_rates(bucket, value, should_warn):
    warnings = pipeline.plausibility_warnings(bucket, [value])
    assert bool(warnings) == should_warn


def test_min_max_are_attributed_to_the_category_that_produced_them(tmp_path):
    rows = [
        ["Product", "Fee Tier", "General", "Petrol", "Airlines"],
        ["Visa Business Debit", "EMV Chip", "1.85%", "0.68%", "1.35%"],
        ["Visa Corporate", "Standard", "2.05%", "0.68%", "1.35%"],
    ]
    pdf_path = tmp_path / "synthetic_commercial_spread.pdf"
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=9)
    for row in rows:
        for text, w in zip(row, [55, 30, 25, 25, 25]):
            pdf.cell(w, 8, text, border=1)
        pdf.ln(8)
    pdf.output(str(pdf_path))

    result = pipeline.parse_visa(pdf_path.read_bytes(), "XX")
    block = pipeline._stat_block(result.commercial, result.commercial_headline, result.commercial_labeled)
    assert block["min"] == 0.68
    assert block["max"] == 2.05
    assert "min_label" in block and "max_label" in block, "range should say WHICH product/category produced each end"
