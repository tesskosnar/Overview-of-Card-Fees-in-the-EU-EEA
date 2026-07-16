"""
discover.py
============
Turns the two "listing pages" into {iso2: pdf_url} maps.

Both source pages are plain, server-rendered HTML (verified by hand
before writing this): every country's PDF link is already present in
the initial response, so a simple `requests.get()` is enough — no
headless browser / JS execution needed.

We do NOT hardcode PDF URLs (see sources.py for why): both scrapers
re-discover the current link on every run, matching on visible text
rather than on CSS classes or DOM depth, so small template tweaks on
Visa's/Mastercard's side don't silently break us.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from sources import NAME_ALIASES, Country

log = logging.getLogger(__name__)

PDF_HREF_RE = re.compile(r"\.pdf(\?.*)?$", re.IGNORECASE)


def _names_for(country: Country) -> list[str]:
    return [country.name] + NAME_ALIASES.get(country.name, [])


def discover_visa(html: str, base_url: str, countries: list[Country]) -> dict[str, str]:
    """
    Visa's page lists one <a> per country, and the link's own visible
    text already *is* the country name, e.g. "Austria Interchange
    Fees". We match on that text directly.
    """
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


def discover_mastercard(html: str, base_url: str, countries: list[Country]) -> dict[str, str]:
    """
    Mastercard's page repeats "Download Current Fees" as the link
    text for every country, so the country name instead lives in the
    heading/paragraph that immediately precedes the link
    ("<Country> intra-location POS interchange fees..."). We scan a
    generous set of tag types for text that *starts with* the country
    name and mentions "interchange"/"intra-location", then grab the
    next PDF link that follows it in document order. `find_next`
    walks the whole subsequent tree (including into children), so
    this is tolerant of whichever heading level / wrapper Mastercard
    actually uses.
    """
    soup = BeautifulSoup(html, "html.parser")
    candidates = soup.find_all(["h1", "h2", "h3", "h4", "h5", "strong", "p", "div", "li"])

    found: dict[str, str] = {}
    for country in countries:
        names = [n.lower() for n in _names_for(country)]
        for tag in candidates:
            text = tag.get_text(" ", strip=True).lower()
            if not text:
                continue
            starts_right = any(text.startswith(n) for n in names)
            mentions_fees = "interchange" in text or "intra-location" in text
            if starts_right and mentions_fees:
                link = tag.find_next("a", href=PDF_HREF_RE)
                if link and link.get("href"):
                    found[country.iso2] = urljoin(base_url, link["href"])
                    break
        if country.iso2 not in found:
            log.warning("Mastercard: no PDF link matched for %s", country.name)
    return found
