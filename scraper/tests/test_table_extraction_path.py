"""
Builds a small synthetic PDF with an ACTUAL ruled table (real grid
lines, not just positioned text) and runs it through the full
parse_common.parse_pdf() -> carry_forward_product_prefix() ->
classify() pipeline.

This exists because the two real-world samples we validated by hand
(tests/fixtures/mastercard_germany_raw.txt) only exercise the
text-fallback path. The table-extraction path (pdfplumber's
extract_tables(), which is what we're actually counting on for Visa's
PDFs — see parse_visa.py's module docstring) had never been run
end-to-end. This closes that gap: it can't validate against the real
Visa layout pixel-for-pixel, but it does prove the mechanics —
opening a PDF, detecting a ruled table, reconstructing rows/columns
from it, and classifying the result — actually work, not just "look
right" on paper.
"""

import pathlib
import sys

from fpdf import FPDF

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from parse_common import carry_forward_product_prefix, parse_pdf  # noqa: E402
from parse_visa import PRODUCT_MARKERS, _classify  # noqa: E402

OUT = pathlib.Path(__file__).parent / "fixtures" / "synthetic_visa_table.pdf"

# Mirrors the real shape: a product's first tier row carries the
# product name, later tier rows for the same product don't.
ROWS = [
    ["Product", "Fee Tier", "General", "Petrol", "Airlines"],
    ["Visa Consumer Debit", "Contactless", "0.20%", "0.20%", "0.20%"],
    ["", "Standard", "0.20%", "0.20%", "0.20%"],
    ["Visa Consumer Credit", "Contactless", "0.30%", "0.30%", "0.30%"],
    ["", "Standard", "0.30%", "0.30%", "0.30%"],
    ["Visa Business Debit", "EMV Chip", "1.85%", "0.68%", "1.35%"],
    ["Visa Corporate", "Standard", "2.05%", "0.68%", "1.35%"],
]


def build_pdf() -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    col_widths = [55, 30, 25, 25, 25]
    row_h = 8
    for row in ROWS:
        for text, w in zip(row, col_widths):
            pdf.cell(w, row_h, text, border=1)
        pdf.ln(row_h)
    pdf.output(str(OUT))


def main() -> None:
    build_pdf()
    print(f"built {OUT} ({OUT.stat().st_size} bytes)")

    parsed = parse_pdf(OUT.read_bytes())
    print(f"used_table_extraction = {parsed.used_table_extraction}")
    assert parsed.used_table_extraction, "expected extract_tables() to detect the ruled grid"

    rows = carry_forward_product_prefix(parsed.rows, PRODUCT_MARKERS)
    for r in rows:
        print(f"  {r.label!r:45s} {r.values}  -> {_classify(r.label)}")

    buckets = {"consumer_debit": [], "consumer_credit": [], "commercial": []}
    for r in rows:
        b = _classify(r.label)
        if b in buckets:
            buckets[b].extend(r.values)

    assert set(buckets["consumer_debit"]) == {0.20}, buckets["consumer_debit"]
    assert set(buckets["consumer_credit"]) == {0.30}, buckets["consumer_credit"]
    assert set(buckets["commercial"]) == {1.85, 0.68, 1.35, 2.05}, buckets["commercial"]

    print("\nALL ASSERTIONS PASSED — table-extraction path works end to end")


if __name__ == "__main__":
    main()
