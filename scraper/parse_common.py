"""
parse_common.py
================
Shared helpers for turning a rate-sheet PDF into structured numbers.

Both Visa and Mastercard publish these as multi-column tables
(Product x Fee-Tier x Merchant-Category), and — this matters — they do
NOT extract identically as plain text. Mastercard's tables happen to
linearize cleanly (label and value stay on the same line). Visa's do
not: the "General" column often stays with its row, but the other
merchant-category columns get pulled out into a separate block,
disconnected from their row label, when read as a flat text stream.

So the primary extraction path here is pdfplumber's *table* mode
(`page.extract_tables()`), which reconstructs rows/columns from the
PDF's actual ruling lines and cell positions rather than reading
order. Plain text extraction is kept only as a fallback for pages
where no table is detected (some countries' PDFs are simpler and
don't draw ruled tables at all).

Output of this module is intentionally low-level and un-opinionated:
a flat list of (label, [values], page_number) rows, plus the raw
per-page text (used only to locate section boundaries). Turning that
into "consumer_debit = 0.20%" is the job of parse_mastercard.py /
parse_visa.py, because the label vocabulary genuinely differs between
the two networks.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field

import pdfplumber

log = logging.getLogger(__name__)

PCT_RE = re.compile(r"(\d{1,2}[.,]\d{1,3})\s*%")


@dataclass
class Row:
    label: str
    values: list[float]
    page: int


@dataclass
class ParsedPdf:
    rows: list[Row]
    page_text: list[str]  # page_text[i] = full text of page i (0-indexed)
    used_table_extraction: bool
    warnings: list[str] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n".join(self.page_text)


def _percents_in(cell: str) -> list[float]:
    return [float(m.group(1).replace(",", ".")) for m in PCT_RE.finditer(cell)]


def _row_from_table_row(cells: list[str | None]) -> Row | None:
    clean = [c.strip() for c in cells if c and c.strip()]
    if not clean:
        return None
    values: list[float] = []
    label_parts: list[str] = []
    for cell in clean:
        found = _percents_in(cell)
        if found:
            values.extend(found)
        else:
            label_parts.append(cell)
    if not values:
        return None
    return Row(label=" ".join(label_parts), values=values, page=-1)  # page filled by caller


def _rows_from_text(text: str) -> list[Row]:
    """Fallback for pages with no detected table: one row per text
    line that contains at least one percentage. A line with no
    percentage but real text updates nothing here — carrying forward
    labels for value-only lines is handled by the caller, since only
    it knows whether that's meaningful for this network's layout."""
    rows = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        vals = _percents_in(line)
        if not vals:
            continue
        first_pct_pos = PCT_RE.search(line).start()
        label = line[:first_pct_pos].strip(" \t-–")
        rows.append(Row(label=label, values=vals, page=-1))
    return rows


def parse_pdf(pdf_bytes: bytes) -> ParsedPdf:
    rows: list[Row] = []
    page_text: list[str] = []
    used_tables = False
    warnings: list[str] = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_no, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            page_text.append(text)

            tables = []
            try:
                tables = page.extract_tables() or []
            except Exception as exc:  # pdfplumber can choke on odd PDFs
                warnings.append(f"page {page_no}: extract_tables() failed: {exc}")

            page_rows: list[Row] = []
            for table in tables:
                for raw_row in table:
                    r = _row_from_table_row(raw_row)
                    if r:
                        r.page = page_no
                        page_rows.append(r)

            if page_rows:
                used_tables = True
                rows.extend(page_rows)
            elif text:
                # no ruled table detected on this page -> fall back to text scan
                for r in _rows_from_text(text):
                    r.page = page_no
                    rows.append(r)

    return ParsedPdf(rows=rows, page_text=page_text, used_table_extraction=used_tables, warnings=warnings)


def find_section_page(page_text: list[str], markers: list[str]) -> int | None:
    """Returns the 0-indexed page number of the first page whose text
    contains any of `markers` (case-insensitive), or None if none of
    the pages match. Callers use this to split "consumer" pages from
    "commercial" pages."""
    for i, text in enumerate(page_text):
        low = text.lower()
        if any(m.lower() in low for m in markers):
            return i
    return None


def carry_forward_labels(rows: list[Row]) -> list[Row]:
    """Handles the case where a row's label is *entirely* empty
    (some table extractions genuinely drop it) by repeating the last
    non-empty label. This alone is NOT enough for these rate sheets —
    see carry_forward_product_prefix below for the pattern that
    actually shows up in practice."""
    out = []
    last_label = ""
    last_page = None
    for r in rows:
        if r.page != last_page:
            last_page = r.page
            last_label = r.label or last_label
        label = r.label if r.label else last_label
        if r.label:
            last_label = r.label
        out.append(Row(label=label, values=r.values, page=r.page))
    return out


def carry_forward_product_prefix(rows: list[Row], product_markers: list[str]) -> list[Row]:
    """
    Rate sheets print the product name once, on the row for its
    *first* fee tier, and every following tier-only row (e.g. "Chip
    0.30%", "Base 0.30%") omits it — so those rows are NOT empty (the
    tier name itself is a perfectly good, non-empty label), they're
    just missing the product prefix that gives them meaning. Plain
    carry_forward_labels() does nothing for them, since their label
    isn't empty.

    This instead prepends the most recently seen product name to any
    row whose label does not itself start with one of
    `product_markers` (case-insensitive), so "Chip" following
    "Mastercard Consumer Credit Contactless" becomes "Mastercard
    Consumer Credit Chip". The carry never crosses a page break, since
    a new page reliably starts a fresh table in these sheets.
    """
    out = []
    last_product = ""
    last_page = None
    markers = [m.lower() for m in product_markers]
    for r in rows:
        if r.page != last_page:
            last_page = r.page
            last_product = ""
        low = r.label.lower()
        if any(low.startswith(m) for m in markers):
            last_product = r.label
            out.append(r)
        elif last_product:
            out.append(Row(label=f"{last_product} {r.label}".strip(), values=r.values, page=r.page))
        else:
            out.append(r)
    return out


# Consumer interchange in the EU/EEA is capped EU-wide by Regulation
# (EU) 2015/751 at 0.20% (debit) / 0.30% (credit). A handful of
# countries publish slightly different figures (a bit lower, mainly),
# but nothing has ever been seen anywhere near, say, 0.65% — a value
# that far out is much more likely a stray number pulled from the
# wrong table cell (e.g. a commercial-card column bleeding into a
# consumer row) than a real published rate. These bands are
# deliberately generous (not just "exactly 0.20/0.30") so a genuine,
# documented country exception doesn't trip this — the point is to
# catch parsing slips, not to second-guess real regulatory variation.
PLAUSIBLE_RANGE = {
    "consumer_debit": (0.15, 0.25),
    "consumer_credit": (0.15, 0.35),
}


def plausibility_warnings(bucket_name: str, values: list[float]) -> list[str]:
    """Returns one warning string per value that falls outside the
    plausible band for `bucket_name` (see PLAUSIBLE_RANGE). Values are
    NOT dropped or altered — this only adds visible warnings, so an
    unusual-but-real number stays in the data rather than being
    silently discarded, while still being flagged for a human to
    glance at."""
    lo_hi = PLAUSIBLE_RANGE.get(bucket_name)
    if lo_hi is None or not values:
        return []
    lo, hi = lo_hi
    return [
        f"{bucket_name} value {v}% is outside the expected {lo}%-{hi}% range "
        f"for an EU/EEA consumer card — likely a parsing slip (wrong table "
        f"cell), verify against the source PDF"
        for v in values
        if v < lo or v > hi
    ]
