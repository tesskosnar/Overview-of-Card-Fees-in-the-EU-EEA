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
