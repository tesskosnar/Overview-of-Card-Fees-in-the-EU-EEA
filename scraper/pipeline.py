"""
pipeline.py
===========
Consolidated Visa interchange-fee scraper for the Colab-based
workflow. This is the SAME logic as the original GitHub Actions
scraper (sources.py, fetch.py, discover.py, parse_common.py,
parse_visa.py, aggregate.py), combined into one file because a
notebook works better with fewer, larger cells than a package of
small files.

What's intentionally NOT here, vs. the GitHub Actions version:
  - Mastercard live scraping (mastercard.com blocks automated
    fetches at the listing-page level -- confirmed repeatedly).
    Mastercard data instead comes from manual_mastercard.json,
    hand-researched country by country.
  - media_search.py (Brave Search + GDELT "public observations").
    Dropped for simplicity; can be re-added later if wanted.
"""

from __future__ import annotations

import io
import logging
import re
import statistics
import time
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

import pdfplumber
import requests
from bs4 import BeautifulSoup

log = logging.getLogger("pipeline")

# ---------------------------------------------------------------
# sources.py
# ---------------------------------------------------------------


@dataclass(frozen=True)
class Country:
    name: str
    iso2: str
    eu_member: bool
    region: str


EU_EEA_COUNTRIES = [
    Country("Austria", "AT", True, "Western"),
    Country("Belgium", "BE", True, "Western"),
    Country("Bulgaria", "BG", True, "CEE"),
    Country("Croatia", "HR", True, "CEE"),
    Country("Cyprus", "CY", True, "Southern"),
    Country("Czech Republic", "CZ", True, "CEE"),
    Country("Denmark", "DK", True, "Nordic"),
    Country("Estonia", "EE", True, "CEE"),
    Country("Finland", "FI", True, "Nordic"),
    Country("France", "FR", True, "Western"),
    Country("Germany", "DE", True, "Western"),
    Country("Greece", "GR", True, "Southern"),
    Country("Hungary", "HU", True, "CEE"),
    Country("Ireland", "IE", True, "Western"),
    Country("Italy", "IT", True, "Southern"),
    Country("Latvia", "LV", True, "CEE"),
    Country("Lithuania", "LT", True, "CEE"),
    Country("Luxembourg", "LU", True, "Western"),
    Country("Malta", "MT", True, "Southern"),
    Country("Netherlands", "NL", True, "Western"),
    Country("Poland", "PL", True, "CEE"),
    Country("Portugal", "PT", True, "Southern"),
    Country("Romania", "RO", True, "CEE"),
    Country("Slovakia", "SK", True, "CEE"),
    Country("Slovenia", "SI", True, "CEE"),
    Country("Spain", "ES", True, "Southern"),
    Country("Sweden", "SE", True, "Nordic"),
    Country("Iceland", "IS", False, "Nordic"),
    Country("Liechtenstein", "LI", False, "Western"),
    Country("Norway", "NO", False, "Nordic"),
]

REGIONS = ["CEE", "Western", "Nordic", "Southern"]
COUNTRY_BY_ISO2 = {c.iso2: c for c in EU_EEA_COUNTRIES}

NAME_ALIASES = {
    "Czech Republic": ["Czechia"],
    "Denmark": ["Denmark, Greenland & Faroe Islands", "Denmark, Greenland"],
}

VISA_LISTING_URL = (
    "https://www.visa.co.uk/about-visa/visa-in-europe/fees-and-interchange.html"
)

IFR_CAP = {"consumer_debit": 0.20, "consumer_credit": 0.30}

# ---------------------------------------------------------------
# fetch.py
# ---------------------------------------------------------------


class RobotsDisallowed(Exception):
    def __init__(self, url: str, reason: str = "robots.txt"):
        self.url = url
        self.reason = reason
        super().__init__(f"Access denied ({reason}): {url}")


USER_AGENT = (
    "CardFeeTrackerBot/1.0 "
    "(public-interest research; occasional read-only fetch of publicly "
    "published interchange rate sheets; run manually by the project owner)"
)

REQUEST_DELAY_SECONDS = 1.5
TIMEOUT_SECONDS = 20
MAX_RETRIES = 3

_robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}


def _fetch_robots_txt(origin: str) -> str:
    robots_url = origin.rstrip("/") + "/robots.txt"
    try:
        resp = requests.get(robots_url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS)
        return resp.text if resp.status_code == 200 else ""
    except requests.RequestException as exc:
        log.warning("Could not read robots.txt for %s (%s); proceeding cautiously", origin, exc)
        return ""


def _robots_for(url: str) -> urllib.robotparser.RobotFileParser:
    origin = "{0.scheme}://{0.netloc}".format(urlparse(url))
    if origin not in _robots_cache:
        raw = _fetch_robots_txt(origin)
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(raw.splitlines())
        _robots_cache[origin] = rp
    return _robots_cache[origin]


def allowed(url: str) -> bool:
    try:
        return _robots_for(url).can_fetch(USER_AGENT, url)
    except Exception:
        return True


def _get(url: str, *, as_binary: bool):
    if not allowed(url):
        log.error("Blocked by robots.txt, skipping: %s", url)
        raise RobotsDisallowed(url)

    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"}, timeout=TIMEOUT_SECONDS)
            if resp.status_code in (401, 403, 429):
                log.error("%s responded HTTP %d -- treating as a deliberate block, not retrying", url, resp.status_code)
                raise RobotsDisallowed(url, reason=f"HTTP {resp.status_code}")
            resp.raise_for_status()
            time.sleep(REQUEST_DELAY_SECONDS)
            return resp.content if as_binary else resp.text
        except requests.RequestException as exc:
            last_exc = exc
            wait = 2**attempt
            log.warning("Fetch failed (attempt %d/%d) for %s: %s -- retrying in %ss", attempt, MAX_RETRIES, url, exc, wait)
            time.sleep(wait)
    log.error("Giving up on %s after %d attempts: %s", url, MAX_RETRIES, last_exc)
    return None


def fetch_html(url: str):
    return _get(url, as_binary=False)


def fetch_pdf_bytes(url: str):
    return _get(url, as_binary=True)


# ---------------------------------------------------------------
# discover.py
# ---------------------------------------------------------------

PDF_HREF_RE = re.compile(r"\.pdf(\?.*)?$", re.IGNORECASE)


def _names_for(country: Country) -> list[str]:
    return [country.name] + NAME_ALIASES.get(country.name, [])


def discover_visa(html: str, base_url: str, countries: list[Country]) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    pdf_links = soup.find_all("a", href=PDF_HREF_RE)

    found: dict[str, str] = {}
    for country in countries:
        for link in pdf_links:
            text = link.get_text(" ", strip=True).lower()
            if not text:
                continue
            if any(text.startswith(name.lower()) for name in _names_for(country)):
                found[country.iso2] = urljoin(base_url, link["href"])
                break
        if country.iso2 not in found:
            log.warning("Visa: no PDF link matched for %s", country.name)
    return found


# ---------------------------------------------------------------
# parse_common.py
# ---------------------------------------------------------------

PCT_RE = re.compile(r"(\d{1,2}[.,]\d{1,3})\s*%")


@dataclass
class Row:
    label: str
    values: list[float]
    page: int
    raw_text: str = ""


@dataclass
class ParsedPdf:
    rows: list[Row]
    page_text: list[str]
    used_table_extraction: bool
    warnings: list[str] = field(default_factory=list)


def _percents_in(cell: str) -> list[float]:
    return [float(m.group(1).replace(",", ".")) for m in PCT_RE.finditer(cell)]


def _row_from_table_row(cells) -> Row | None:
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
    return Row(label=" ".join(label_parts), values=values, page=-1, raw_text=" ".join(clean))


def _rows_from_text(text: str) -> list[Row]:
    rows = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        vals = _percents_in(line)
        if not vals:
            continue
        first_pct_pos = PCT_RE.search(line).start()
        label = line[:first_pct_pos].strip(" \t-\u2013")
        rows.append(Row(label=label, values=vals, page=-1, raw_text=line))
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
            except Exception as exc:
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
                for r in _rows_from_text(text):
                    r.page = page_no
                    rows.append(r)

    return ParsedPdf(rows=rows, page_text=page_text, used_table_extraction=used_tables, warnings=warnings)


def carry_forward_product_prefix(rows: list[Row], product_markers: list[str]) -> list[Row]:
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
            out.append(Row(label=f"{last_product} {r.label}".strip(), values=r.values, page=r.page, raw_text=r.raw_text))
        else:
            out.append(r)
    return out


PLAUSIBLE_RANGE = {
    "consumer_debit": (0.15, 0.25),
    "consumer_credit": (0.15, 0.35),
}


def plausibility_warnings(bucket_name: str, values: list[float]) -> list[str]:
    lo_hi = PLAUSIBLE_RANGE.get(bucket_name)
    if lo_hi is None or not values:
        return []
    lo, hi = lo_hi
    return [
        f"{bucket_name} value {v}% is outside the expected {lo}%-{hi}% range "
        f"for an EU/EEA consumer card -- likely a parsing slip, verify against the source PDF"
        for v in values
        if v < lo or v > hi
    ]


# ---------------------------------------------------------------
# parse_visa.py
# ---------------------------------------------------------------

PRODUCT_MARKERS = ["visa", "v pay"]
CONSUMER_CREDIT_HINTS = ["consumer credit", "consumer deferred debit"]
CONSUMER_DEBIT_HINTS = ["consumer debit", "consumer prepaid", "v pay debit", "v pay prepaid"]
COMMERCIAL_HINTS = ["business", "corporate", "purchasing", "fleet", "platinum", "infinite"]

# Value-conditional qualifiers (small-transaction discounts, merchant-volume
# tiers, category-specific surcharges/discounts) describe a SPECIAL rate for
# a specific condition, not the headline rate. A country like Spain publishes
# both a "<= EUR 20" discounted tier and the standard tier for the same
# product; averaging them together produces a number that matches neither
# the EU-cap headline rate nor any single real transaction. These rows still
# count toward min/max (they're real, published rates) but are excluded from
# the primary/headline average.
TIER_QUALIFIER_RE = re.compile(
    r"\b(up to|over|less than|more than|tier[\s-]?\d|micro[\s-]?payment|low value|"
    r"high value|petrol|toll|charity|government|retail|contactless high value|"
    r"sector development|bill payment|meal voucher|fuel|electric vehicle|"
    r"wholesale|fleet|purchasing|large market|small market|late presentment|"
    r"large ticket|incentive)\b",
    re.IGNORECASE,
)

# Some rate sheets state a percentage AND an absolute cap in the same cell
# (e.g. "0.20% (capped at RON 20.00)", "0.20% (capped at £0.50)"). The
# percentage alone understates the true cost only for very large
# transactions, but the cap itself is genuinely useful information that a
# plain average would silently drop. Surface it as a warning rather than
# trying to model it numerically (the cap currency/amount varies by country
# and isn't comparable across them without a transaction-size assumption).
CAP_RE = re.compile(
    r"(?:capped at|cap of|max(?:imum)?(?:\s+of)?)\s*:?\s*([A-Z]{0,3}\s?[\d.,]+)",
    re.IGNORECASE,
)


def _is_headline_row(label: str) -> bool:
    return not TIER_QUALIFIER_RE.search(label)


def _cap_note(label: str) -> str | None:
    m = CAP_RE.search(label)
    if not m:
        return None
    return f"rate sheet also states a cap: \"{m.group(0)}\" (per-transaction ceiling on the absolute fee, not reflected in the % figure)"


@dataclass
class CountryRateResult:
    iso2: str
    network: str = "visa"
    consumer_debit: list[float] = field(default_factory=list)
    consumer_credit: list[float] = field(default_factory=list)
    commercial: list[float] = field(default_factory=list)
    consumer_debit_headline: list[float] = field(default_factory=list)
    consumer_credit_headline: list[float] = field(default_factory=list)
    commercial_headline: list[float] = field(default_factory=list)
    consumer_debit_labeled: list[tuple[str, float]] = field(default_factory=list)
    consumer_credit_labeled: list[tuple[str, float]] = field(default_factory=list)
    commercial_labeled: list[tuple[str, float]] = field(default_factory=list)
    unclassified: list[tuple[str, list[float]]] = field(default_factory=list)
    used_table_extraction: bool = False
    warnings: list[str] = field(default_factory=list)
    source_url: str | None = None


def _clean_category_label(row_label: str, product_prefix_hint: str) -> str:
    """Strip the repeated product name (e.g. "Visa Consumer Debit") off a
    row's label so what's left is just the merchant-category/tier part
    (e.g. "Petrol", "Retail Tier 3") -- the bit that actually explains why
    this particular value is the min or the max."""
    low = row_label.lower()
    for hint in product_prefix_hint.split("|"):
        hint = hint.strip()
        if hint and low.startswith(hint):
            return row_label[len(hint):].strip(" -\u2013") or "General"
    return row_label.strip() or "General"


def _classify(label: str) -> str:
    low = label.lower()
    if any(h in low for h in CONSUMER_CREDIT_HINTS):
        return "consumer_credit"
    if any(h in low for h in CONSUMER_DEBIT_HINTS):
        return "consumer_debit"
    if any(h in low for h in COMMERCIAL_HINTS):
        return "commercial"
    return "unclassified"


def parse_visa(pdf_bytes: bytes, iso2: str) -> CountryRateResult:
    parsed = parse_pdf(pdf_bytes)
    rows = carry_forward_product_prefix(parsed.rows, PRODUCT_MARKERS)

    result = CountryRateResult(iso2=iso2, used_table_extraction=parsed.used_table_extraction, warnings=list(parsed.warnings))

    cap_notes_seen = set()
    for row in rows:
        bucket = _classify(row.label)
        headline = _is_headline_row(row.label)
        cap = _cap_note(row.raw_text or row.label)
        if cap and cap not in cap_notes_seen and bucket in ("consumer_credit", "consumer_debit"):
            cap_notes_seen.add(cap)
            result.warnings.append(cap)
        # A row can hold several values across unlabeled columns (e.g. a
        # "General" column followed by a "Government Payments" column that
        # only appears in the table's header, never repeated per-row). The
        # keyword check above catches qualifiers that DO show up in the row
        # text; this positional check is the fallback for ones that don't --
        # across every rate sheet seen so far, the first (leftmost) value in
        # a row is consistently the general/standard rate, with narrower
        # merchant-category or payment-type rates following it.
        headline_values = [row.values[0]] if headline and row.values else []
        category_label = _clean_category_label(row.label, "|".join(PRODUCT_MARKERS))
        labeled = [(category_label, v) for v in row.values]
        if bucket == "consumer_credit":
            result.consumer_credit.extend(row.values)
            result.consumer_credit_headline.extend(headline_values)
            result.consumer_credit_labeled.extend(labeled)
        elif bucket == "consumer_debit":
            result.consumer_debit.extend(row.values)
            result.consumer_debit_headline.extend(headline_values)
            result.consumer_debit_labeled.extend(labeled)
        elif bucket == "commercial":
            result.commercial.extend(row.values)
            result.commercial_headline.extend(headline_values)
            result.commercial_labeled.extend(labeled)
        else:
            result.unclassified.append((row.label, row.values))

    if not result.used_table_extraction:
        result.warnings.append("no ruled table detected -- fell back to text-line parsing, numbers for this country are lower confidence")
    if not result.consumer_debit:
        result.warnings.append("no consumer_debit rate matched")
    if not result.consumer_credit:
        result.warnings.append("no consumer_credit rate matched")
    if not result.commercial:
        result.warnings.append("no commercial rate matched")

    result.warnings.extend(plausibility_warnings("consumer_debit", result.consumer_debit))
    result.warnings.extend(plausibility_warnings("consumer_credit", result.consumer_credit))

    return result


# ---------------------------------------------------------------
# aggregate.py
# ---------------------------------------------------------------

CATEGORIES = ["consumer_debit", "consumer_credit", "commercial"]


def _stat_block(all_values: list[float], headline_values: list[float] | None = None, labeled_values: list[tuple[str, float]] | None = None):
    if not all_values:
        return None
    avg_source = headline_values if headline_values else all_values
    block = {
        "avg": round(statistics.mean(avg_source), 4),
        "min": round(min(all_values), 4),
        "max": round(max(all_values), 4),
        "n_values": len(all_values),
    }
    if labeled_values:
        min_v, max_v = block["min"], block["max"]
        min_match = next((lbl for lbl, v in labeled_values if round(v, 4) == min_v), None)
        max_match = next((lbl for lbl, v in labeled_values if round(v, 4) == max_v), None)
        if min_match:
            block["min_label"] = min_match
        if max_match:
            block["max_label"] = max_match
    return block


# consumer_debit/consumer_credit are legally capped EU-wide (IFR Art. 3-4) at
# 0.20%/0.30%. Any row is at or below that cap; discounted/conditional tiers
# are always <= the standard rate, never above. So when EVERY captured row
# for these two categories carries a tier qualifier (e.g. Spain, where both
# the "<=EUR 20" and ">EUR 20" tiers have qualifying language), the max
# observed value is a safe, legally-grounded proxy for the standard rate --
# unlike commercial, which has no cap and no such guarantee.
CAPPED_CATEGORIES = {"consumer_debit", "consumer_credit"}


def _headline_for(category: str, all_values: list[float], headline_values: list[float]) -> list[float]:
    if headline_values:
        return headline_values
    if category in CAPPED_CATEGORIES and all_values:
        return [max(all_values)]
    return []


def build_summary(results: list) -> dict[str, Any]:
    by_network: dict[str, list] = {"visa": [], "mastercard": []}
    for r in results:
        by_network.setdefault(r.network, []).append(r)

    summary: dict[str, Any] = {}
    for network, network_results in by_network.items():
        network_summary = {}
        for category in CATEGORIES:
            per_country_avgs = []
            for r in network_results:
                all_vals = getattr(r, category)
                headline = _headline_for(category, all_vals, getattr(r, f"{category}_headline", []))
                block = _stat_block(all_vals, headline)
                if block:
                    per_country_avgs.append(block["avg"])
            if per_country_avgs:
                network_summary[category] = {
                    "avg": round(statistics.mean(per_country_avgs), 4),
                    "min": round(min(per_country_avgs), 4),
                    "max": round(max(per_country_avgs), 4),
                    "n_countries": len(per_country_avgs),
                }
            else:
                network_summary[category] = None
        summary[network] = network_summary
    return summary


def build_country_table(results: list) -> list[dict[str, Any]]:
    by_iso2: dict[str, dict[str, Any]] = {
        iso2: {"iso2": iso2, "name": country.name, "eu_member": country.eu_member, "region": country.region}
        for iso2, country in COUNTRY_BY_ISO2.items()
    }
    for r in results:
        entry = by_iso2[r.iso2]
        entry[r.network] = {
            "consumer_debit": _stat_block(r.consumer_debit, _headline_for("consumer_debit", r.consumer_debit, r.consumer_debit_headline), r.consumer_debit_labeled),
            "consumer_credit": _stat_block(r.consumer_credit, _headline_for("consumer_credit", r.consumer_credit, r.consumer_credit_headline), r.consumer_credit_labeled),
            "commercial": _stat_block(r.commercial, r.commercial_headline, r.commercial_labeled),
            "source_url": r.source_url,
            "used_table_extraction": r.used_table_extraction,
            "warnings": r.warnings,
        }
    return sorted(by_iso2.values(), key=lambda e: e["name"])


def build_output(results: list) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope": {"fee_type": "interchange", "networks": ["visa", "mastercard"], "region": "EU/EEA", "country_count": len(COUNTRY_BY_ISO2)},
        "note": "",
        "ifr_cap": IFR_CAP,
        "regions": REGIONS,
        "summary": build_summary(results),
        "countries": build_country_table(results),
    }


# ---------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------


def run_visa_scrape() -> list[CountryRateResult]:
    """Full live run: discover, fetch, parse all 30 countries' Visa PDFs.
    Needs real internet access (won't work from a network-restricted sandbox)."""
    html = fetch_html(VISA_LISTING_URL)
    if not html:
        raise RuntimeError("Could not load the Visa listing page")

    pdf_urls = discover_visa(html, VISA_LISTING_URL, EU_EEA_COUNTRIES)
    log.info("Discovered %d/%d Visa PDF links", len(pdf_urls), len(EU_EEA_COUNTRIES))

    results = []
    for country in EU_EEA_COUNTRIES:
        url = pdf_urls.get(country.iso2)
        if not url:
            continue
        try:
            pdf_bytes = fetch_pdf_bytes(url)
            if not pdf_bytes:
                continue
            result = parse_visa(pdf_bytes, country.iso2)
            result.source_url = url
            results.append(result)
            log.info("Parsed %s: debit=%s credit=%s commercial=%s", country.name, result.consumer_debit[:1], result.consumer_credit[:1], result.commercial[:1])
        except RobotsDisallowed as exc:
            log.error("Skipping %s: %s", country.name, exc)
    return results
