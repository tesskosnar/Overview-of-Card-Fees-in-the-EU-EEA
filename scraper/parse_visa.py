"""
parse_visa.py
=============
Turns one Visa "<Country> Interchange Fees" PDF into a
CountryRateResult.

Verified by hand against the real Germany sheet (Apr 2025 edition).
Two things are worth knowing before touching this file:

1. Visa's table layout does NOT linearize cleanly as plain text — the
   "General" column tends to stay attached to its row, but the other
   merchant-category columns (Petrol, Airlines, Railways, ...) get
   pulled into a separate block later in the reading order,
   disconnected from their row label. This is exactly the failure
   mode pdfplumber's *table* extraction (ruling-line based, not
   reading-order based) is meant to fix, which is why parse_common
   tries `extract_tables()` first and only falls back to text lines
   per page when no table is detected. If `used_table_extraction`
   comes back False for a Visa PDF, treat its numbers as low
   confidence and check the source PDF directly.

2. "Consumer Deferred Debit" is bucketed with *credit*, not debit.
   Deferred-debit products settle like a credit card (delayed, batched
   settlement) rather than an immediate debit, and published
   cross-country comparisons (e.g. the Kansas City Fed's interchange
   series) group "credit / delayed debit" together as one category
   for this reason. This is a judgment call, not a regulatory
   citation — flagged here so it's easy to revisit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from parse_common import Row, carry_forward_product_prefix, parse_pdf, plausibility_warnings

# Every product row in a Visa sheet starts with one of these — see
# parse_common.carry_forward_product_prefix for what this is for.
PRODUCT_MARKERS = ["visa", "v pay"]

CONSUMER_CREDIT_HINTS = ["consumer credit", "consumer deferred debit"]
CONSUMER_DEBIT_HINTS = [
    "consumer debit",
    "consumer prepaid",
    "v pay debit",
    "v pay prepaid",
]
COMMERCIAL_HINTS = [
    "business",
    "corporate",
    "purchasing",
    "fleet",
    "platinum",
    "infinite",
]


@dataclass
class CountryRateResult:
    iso2: str
    network: str = "visa"
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

    if not result.used_table_extraction:
        result.warnings.append(
            "no ruled table detected — fell back to text-line parsing, "
            "numbers for this country are lower confidence"
        )
    if not result.consumer_debit:
        result.warnings.append("no consumer_debit rate matched")
    if not result.consumer_credit:
        result.warnings.append("no consumer_credit rate matched")
    if not result.commercial:
        result.warnings.append("no commercial rate matched")

    result.warnings.extend(plausibility_warnings("consumer_debit", result.consumer_debit))
    result.warnings.extend(plausibility_warnings("consumer_credit", result.consumer_credit))

    return result
