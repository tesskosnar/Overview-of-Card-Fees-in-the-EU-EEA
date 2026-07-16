"""
parse_mastercard.py
====================
Turns one Mastercard "<Country> intra-location POS interchange fees"
PDF into a CountryRateResult.

Verified by hand against the real Germany sheet (Jan 2026 edition):
the consumer section lists flat rates per product ("Mastercard
Consumer Credit" -> 0.30%, "Mastercard Consumer Debit" / "Consumer
Prepaid" / "Maestro Consumer" -> 0.20%), matching the EU IFR caps
exactly. The commercial section is a Product x Fee-Tier x
Merchant-Category matrix (Airlines, Petrol, Touristic, Grocery,
Household, Drugstores, Equipment/Furniture, plus a "General" column)
with values observed from 0.68% up to 2.40% — i.e. the real spread in
"card scheme fees" comes almost entirely from the uncapped commercial
side, not consumer cards.

Classification works on the *label text* of each row (after carrying
product names forward across tier-only continuation rows), not on
page position — this makes it robust even when a smaller country's
whole rate sheet fits on a single page.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from parse_common import Row, carry_forward_product_prefix, parse_pdf

# Every product row in a Mastercard sheet starts with one of these —
# used to detect "this row starts a new product" vs. "this row is a
# bare fee-tier continuing the last product" (see parse_common).
PRODUCT_MARKERS = ["mastercard", "maestro", "debit"]

CONSUMER_CREDIT_HINTS = ["consumer credit"]
CONSUMER_DEBIT_HINTS = [
    "consumer debit",
    "consumer prepaid",
    "maestro consumer",
    "debit mastercard consumer",
]
COMMERCIAL_HINTS = [
    "business",
    "commercial",
    "corporate",
    "purchasing",
    "fleet",
    "professional card",
]


@dataclass
class CountryRateResult:
    iso2: str
    network: str = "mastercard"
    consumer_debit: list[float] = field(default_factory=list)
    consumer_credit: list[float] = field(default_factory=list)
    commercial: list[float] = field(default_factory=list)
    unclassified: list[tuple[str, list[float]]] = field(default_factory=list)
    used_table_extraction: bool = False
    warnings: list[str] = field(default_factory=list)


def _classify(label: str) -> str:
    low = label.lower()
    if any(h in low for h in CONSUMER_CREDIT_HINTS):
        return "consumer_credit"
    if any(h in low for h in CONSUMER_DEBIT_HINTS):
        return "consumer_debit"
    if any(h in low for h in COMMERCIAL_HINTS):
        return "commercial"
    return "unclassified"


def parse(pdf_bytes: bytes, iso2: str) -> CountryRateResult:
    parsed = parse_pdf(pdf_bytes)
    rows: list[Row] = carry_forward_product_prefix(parsed.rows, PRODUCT_MARKERS)

    result = CountryRateResult(
        iso2=iso2,
        used_table_extraction=parsed.used_table_extraction,
        warnings=list(parsed.warnings),
    )

    for row in rows:
        bucket = _classify(row.label)
        if bucket == "consumer_credit":
            result.consumer_credit.extend(row.values)
        elif bucket == "consumer_debit":
            result.consumer_debit.extend(row.values)
        elif bucket == "commercial":
            result.commercial.extend(row.values)
        else:
            result.unclassified.append((row.label, row.values))

    if not result.consumer_debit:
        result.warnings.append("no consumer_debit rate matched")
    if not result.consumer_credit:
        result.warnings.append("no consumer_credit rate matched")
    if not result.commercial:
        result.warnings.append("no commercial rate matched")

    return result
