"""Monthly multilingual web/news discovery for public card-fee observations.

Brave Search supplies broad web coverage (requires BRAVE_SEARCH_API_KEY).
GDELT supplies an additional global news layer without an API key. The module
extracts explicit percentages/basis points/fixed fees from snippets and, for a
limited number of high-relevance results, from the source page itself.

These observations are intentionally stored separately from official network
interchange rate sheets. They are evidence with provenance, not automatically
assumed to be comparable tariff rows.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import statistics
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pdfplumber
import requests
from bs4 import BeautifulSoup

import fetch
from search_terms import (
    CARD_SEGMENT_TERMS,
    COMMON_TERMS,
    LOCAL_TERMS,
    NETWORK_TERMS,
    SOURCE_TYPE_DOMAINS,
    terms_for,
)
from sources import COUNTRY_BY_ISO2, EU_EEA_COUNTRIES

log = logging.getLogger(__name__)

BRAVE_WEB_URL = "https://api.search.brave.com/res/v1/web/search"
GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
REQUEST_TIMEOUT = 30
MAX_TEXT_CHARS = 60_000
DEFAULT_LOOKBACK_DAYS = 400
DEFAULT_BRAVE_RESULTS = 20
DEFAULT_PAGE_FETCH_LIMIT = 45
MANUAL_SOURCES_PATH = Path(__file__).resolve().parent / "config" / "manual_sources.json"

FEE_TYPES = ("interchange", "scheme_fee", "processing_fee", "merchant_service_charge")

PERCENT_RANGE_RE = re.compile(
    r"(?<![\d.,])(?P<low>\d{1,2}(?:[.,]\d{1,4})?)\s*%?\s*"
    r"(?:-|–|—|to|až|bis|à|do|hasta|al|tot)\s*"
    r"(?P<high>\d{1,2}(?:[.,]\d{1,4})?)\s*(?:%|percent|procent|prozent|pour\s*cent|por\s*ciento)",
    re.IGNORECASE,
)
PERCENT_RE = re.compile(
    r"(?<![\d.,])(?P<value>\d{1,2}(?:[.,]\d{1,4})?)\s*"
    r"(?:%|percent|procent|prozent|pour\s*cent|por\s*ciento)(?!\w)",
    re.IGNORECASE,
)
BPS_RE = re.compile(
    r"(?<!\d)(?P<value>\d{1,4}(?:[.,]\d+)?)\s*"
    r"(?:bps|bp|basis\s+points?|bazick(?:ých|é)\s+bod(?:ů|u)|basispunkte?)",
    re.IGNORECASE,
)
CURRENCY_CODES = "EUR|GBP|USD|CHF|CZK|PLN|HUF|RON|BGN|HRK|DKK|SEK|NOK|ISK"
FIXED_PREFIX_RE = re.compile(
    rf"(?P<currency>€|£|\$)\s*(?P<value>\d{{1,5}}(?:[.,]\d{{1,4}})?)",
    re.IGNORECASE,
)
FIXED_SUFFIX_RE = re.compile(
    rf"(?<![\d.,])(?P<value>\d{{1,5}}(?:[.,]\d{{1,4}})?)\s*(?P<currency>{CURRENCY_CODES}|€|£|\$)(?!\w)",
    re.IGNORECASE,
)

PER_TRANSACTION_TERMS = (
    "per transaction", "per payment", "per card transaction", "za transakci",
    "pro transakci", "je transactie", "pro transaktion", "par transaction",
    "per transazione", "por transacción", "za transakcję",
)
TRANSACTION_AMOUNT_TERMS = (
    "transaction of", "payment of", "purchase of", "amount of", "value of",
    "transakce ve výši", "platba ve výši", "hodnota transakce", "částka transakce",
    "transaktion über", "paiement de", "pago de", "transazione di",
)
FIXED_VALUE_LIMITS = {
    "EUR": 5, "GBP": 5, "USD": 5, "CHF": 5,
    "CZK": 200, "PLN": 30, "HUF": 2500, "RON": 30, "BGN": 30,
    "DKK": 100, "SEK": 100, "NOK": 100, "ISK": 1000, "HRK": 50,
}


def _normalise_url(url: str) -> str:
    try:
        parts = urlparse(url)
        path = parts.path.rstrip("/") or "/"
        return urlunparse((parts.scheme.lower(), parts.netloc.lower(), path, "", parts.query, ""))
    except Exception:
        return url


def _source_name(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return host or "unknown source"


def _source_type(url: str) -> str:
    host = urlparse(url).netloc.lower()
    for source_type, domains in SOURCE_TYPE_DOMAINS.items():
        if any(host == d or host.endswith("." + d) for d in domains):
            return source_type
    if any(domain in host for domain in ("youtube.com", "youtu.be", "vimeo.com", "spotify.com", "soundcloud.com")):
        return "video_or_interview"
    if any(token in host for token in ("bank", "banka", "banki", "payments", "payment", "pay")):
        return "bank_or_payments_provider"
    return "media_or_other_public_source"


def _safe_float(value: str) -> float:
    return float(value.replace(" ", "").replace(",", "."))


def _currency_code(raw: str) -> str:
    return {"€": "EUR", "£": "GBP", "$": "USD"}.get(raw.upper(), raw.upper())


def _flatten_terms() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {fee_type: list(COMMON_TERMS[fee_type]) for fee_type in FEE_TYPES}
    for local in LOCAL_TERMS.values():
        for fee_type in FEE_TYPES:
            result[fee_type].extend(local.get(fee_type, []))
    return {k: list(dict.fromkeys(v)) for k, v in result.items()}


ALL_FEE_TERMS = _flatten_terms()


def _nearest_label(context: str, terms_by_label: dict[str, list[str]], center: int) -> tuple[str | None, int | None]:
    low = context.lower()
    best_label: str | None = None
    best_distance: int | None = None
    for label, terms in terms_by_label.items():
        for term in terms:
            start = 0
            needle = term.lower()
            while True:
                pos = low.find(needle, start)
                if pos < 0:
                    break
                distance = abs((pos + len(needle) // 2) - center)
                if best_distance is None or distance < best_distance:
                    best_label, best_distance = label, distance
                start = pos + 1
    return best_label, best_distance


def _classify_segment(context: str, center: int) -> str:
    label, distance = _nearest_label(context, CARD_SEGMENT_TERMS, center)
    return label if label and distance is not None and distance <= 220 else "unspecified"


def _classify_network(context: str, center: int) -> str:
    label, distance = _nearest_label(context, NETWORK_TERMS, center)
    return label if label and distance is not None and distance <= 260 else "unspecified"


def _classify_fee_type(context: str, center: int) -> tuple[str | None, int | None]:
    return _nearest_label(context, ALL_FEE_TERMS, center)


def _context_window(text: str, start: int, end: int, radius: int = 300) -> tuple[str, int]:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return text[left:right], start - left


def _display_value(kind: str, low: float, high: float, currency: str | None = None) -> str:
    if kind == "percent":
        return f"{low:.4g}%" if low == high else f"{low:.4g}–{high:.4g}%"
    suffix = f" {currency}" if currency else ""
    return f"{low:.4g}{suffix}" if low == high else f"{low:.4g}–{high:.4g}{suffix}"


def extract_observations(candidate: dict, text: str, *, from_full_page: bool) -> list[dict]:
    """Extract explicit fee observations from one candidate's text."""
    if not text:
        return []
    text = re.sub(r"\s+", " ", text)[:MAX_TEXT_CHARS]
    matches: list[tuple[int, int, str, float, float, str | None, str]] = []
    occupied: list[tuple[int, int]] = []

    for match in PERCENT_RANGE_RE.finditer(text):
        low, high = sorted((_safe_float(match.group("low")), _safe_float(match.group("high"))))
        if high <= 20:
            matches.append((match.start(), match.end(), "percent", low, high, None, match.group(0)))
            occupied.append((match.start(), match.end()))

    def overlaps(start: int, end: int) -> bool:
        return any(start < old_end and end > old_start for old_start, old_end in occupied)

    for match in PERCENT_RE.finditer(text):
        if overlaps(match.start(), match.end()):
            continue
        value = _safe_float(match.group("value"))
        if value <= 20:
            matches.append((match.start(), match.end(), "percent", value, value, None, match.group(0)))

    for match in BPS_RE.finditer(text):
        value = _safe_float(match.group("value")) / 100.0
        if value <= 20:
            matches.append((match.start(), match.end(), "percent", value, value, None, match.group(0)))

    for regex in (FIXED_PREFIX_RE, FIXED_SUFFIX_RE):
        for match in regex.finditer(text):
            value = _safe_float(match.group("value"))
            currency = _currency_code(match.group("currency"))
            matches.append((match.start(), match.end(), "fixed", value, value, currency, match.group(0)))

    observations: list[dict] = []
    seen_local: set[tuple] = set()
    for start, end, value_kind, low, high, currency, raw_value in matches:
        context, center = _context_window(text, start, end)
        fee_type, fee_distance = _classify_fee_type(context, center)
        if not fee_type or fee_distance is None or fee_distance > 240:
            continue
        # Fixed monetary values are especially prone to false positives. Require
        # explicit per-transaction wording or a very close fee phrase.
        if value_kind == "fixed":
            low_context = context.lower()
            per_transaction = any(term in low_context for term in PER_TRANSACTION_TERMS)
            immediate_before = context[max(0, center - 80):center].lower()
            if any(term in immediate_before for term in TRANSACTION_AMOUNT_TERMS):
                continue
            if currency and low > FIXED_VALUE_LIMITS.get(currency, 100):
                continue
            if not per_transaction and fee_distance > 90:
                continue
        else:
            per_transaction = True

        segment = _classify_segment(context, center)
        network = _classify_network(context, center)
        source_type = candidate["source_type"]

        confidence = 0.42
        confidence += 0.18 if fee_distance <= 100 else 0.10
        confidence += 0.22 if source_type in {"official_network", "regulator"} else 0.06
        confidence += 0.08 if network != "unspecified" else 0
        confidence += 0.05 if segment != "unspecified" else 0
        confidence += 0.08 if from_full_page else 0
        if value_kind == "fixed" and not per_transaction:
            confidence -= 0.10
        confidence = round(min(confidence, 0.98), 2)
        if confidence < 0.55:
            continue

        key = (fee_type, segment, network, value_kind, round(low, 6), round(high, 6), currency)
        if key in seen_local:
            continue
        seen_local.add(key)

        context_excerpt = context[max(0, center - 140): min(len(context), center + 220)].strip()
        observation_id = hashlib.sha256(
            f"{candidate['country']}|{candidate['url']}|{key}".encode("utf-8")
        ).hexdigest()[:20]
        observations.append({
            "id": observation_id,
            "country": candidate["country"],
            "fee_type": fee_type,
            "card_segment": segment,
            "network": network,
            "channel": "unspecified",
            "value_kind": value_kind,
            "value_low": round(low, 6),
            "value_high": round(high, 6),
            "currency": currency,
            "basis": "per_transaction" if value_kind == "fixed" and per_transaction else "percentage_of_value" if value_kind == "percent" else "unspecified",
            "reported_value": raw_value.strip(),
            "display_value": _display_value(value_kind, low, high, currency),
            "headline": candidate.get("title") or "Public fee mention",
            "source_name": candidate.get("source_name") or _source_name(candidate["url"]),
            "source_url": candidate["url"],
            "source_type": source_type,
            "published_date": candidate.get("published_date"),
            "source_language": candidate.get("language"),
            "search_engine": candidate.get("search_engine"),
            "context": context_excerpt,
            "confidence": confidence,
            "extraction_source": "full_page" if from_full_page else "search_snippet",
        })
    return observations


def _brave_queries(country) -> list[str]:
    queries = []
    for group in (("interchange",), ("scheme_fee", "processing_fee"), ("merchant_service_charge",)):
        terms: list[str] = []
        for fee_type in group:
            terms.extend(terms_for(country.language, fee_type)[:5])
        quoted = " OR ".join(f'"{term}"' for term in dict.fromkeys(terms))
        if group == ("merchant_service_charge",):
            queries.append(f"({quoted}) (card OR cards OR merchant OR acquiring)")
        else:
            network_clause = '(Visa OR Mastercard OR "Master Card")'
            segment_clause = '(consumer OR commercial OR business OR debit OR credit)'
            queries.append(f"({quoted}) {network_clause} {segment_clause}")
    return queries


def brave_candidates(api_key: str, lookback_days: int) -> tuple[list[dict], dict]:
    candidates: list[dict] = []
    request_count = 0
    errors: list[str] = []
    freshness = "py" if lookback_days <= 370 else f"{(date.today() - timedelta(days=lookback_days)).isoformat()}to{date.today().isoformat()}"
    max_results = max(1, min(int(os.getenv("BRAVE_RESULTS_PER_QUERY", DEFAULT_BRAVE_RESULTS)), 20))
    max_queries = int(os.getenv("BRAVE_MAX_QUERIES", "120"))

    for country in EU_EEA_COUNTRIES:
        for query in _brave_queries(country):
            if request_count >= max_queries:
                break
            request_count += 1
            params = {
                "q": query,
                "country": country.iso2,
                "search_lang": country.language,
                "count": max_results,
                "freshness": freshness,
                "extra_snippets": "true",
                "safesearch": "moderate",
            }
            try:
                response = requests.get(
                    BRAVE_WEB_URL,
                    params=params,
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": api_key,
                        "User-Agent": fetch.USER_AGENT,
                    },
                    timeout=REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                payload = response.json()
            except (requests.RequestException, ValueError) as exc:
                errors.append(f"{country.iso2}: {exc}")
                log.warning("Brave query failed for %s: %s", country.iso2, exc)
                continue

            for result in payload.get("web", {}).get("results", []):
                url = result.get("url")
                if not url:
                    continue
                snippets = [result.get("description", "")]
                snippets.extend(result.get("extra_snippets") or [])
                clean_snippets = [BeautifulSoup(s, "html.parser").get_text(" ", strip=True) for s in snippets if s]
                candidates.append({
                    "country": country.iso2,
                    "title": BeautifulSoup(result.get("title", ""), "html.parser").get_text(" ", strip=True),
                    "url": _normalise_url(url),
                    "description": " ".join(clean_snippets),
                    "published_date": None,
                    "language": country.language,
                    "source_name": _source_name(url),
                    "source_type": _source_type(url),
                    "search_engine": "brave",
                })
            time.sleep(0.08)
        if request_count >= max_queries:
            break

    status = {
        "enabled": True,
        "requests": request_count,
        "candidates": len(candidates),
        "errors": errors[:20],
    }
    return candidates, status


def gdelt_candidates(lookback_days: int) -> tuple[list[dict], dict]:
    candidates: list[dict] = []
    errors: list[str] = []
    request_count = 0
    max_records = max(10, min(int(os.getenv("GDELT_RESULTS_PER_COUNTRY", "50")), 250))
    timespan = f"{max(1, lookback_days)}d"
    base_terms = '("interchange fee" OR "scheme fee" OR "card network fee" OR "processing fee" OR "merchant service charge" OR "card acceptance fee")'

    for country in EU_EEA_COUNTRIES:
        request_count += 1
        params = {
            "query": f"{base_terms} sourcecountry:{country.gdelt_source_country}",
            "mode": "artlist",
            "maxrecords": max_records,
            "timespan": timespan,
            "sort": "datedesc",
            "format": "json",
        }
        try:
            response = requests.get(GDELT_DOC_URL, params=params, headers={"User-Agent": fetch.USER_AGENT}, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            errors.append(f"{country.iso2}: {exc}")
            log.warning("GDELT query failed for %s: %s", country.iso2, exc)
            continue

        for article in payload.get("articles", []):
            url = article.get("url")
            if not url:
                continue
            seen = article.get("seendate")
            published_date = None
            if isinstance(seen, str) and len(seen) >= 8:
                try:
                    published_date = datetime.strptime(seen[:8], "%Y%m%d").date().isoformat()
                except ValueError:
                    pass
            candidates.append({
                "country": country.iso2,
                "title": article.get("title") or "",
                "url": _normalise_url(url),
                "description": article.get("title") or "",
                "published_date": published_date,
                "language": article.get("language") or country.language,
                "source_name": article.get("domain") or _source_name(url),
                "source_type": _source_type(url),
                "search_engine": "gdelt",
            })
        time.sleep(0.12)

    status = {
        "enabled": True,
        "requests": request_count,
        "candidates": len(candidates),
        "errors": errors[:20],
    }
    return candidates, status



def manual_candidates(path: Path = MANUAL_SOURCES_PATH) -> tuple[list[dict], dict]:
    """Load stable public URLs that should be rechecked every month.

    This complements search-engine discovery for official price lists or
    regulator pages that are important but may not rank in every monthly query.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        return [], {"enabled": False, "candidates": 0, "errors": [str(exc)]}
    candidates = []
    errors = []
    for index, item in enumerate(payload.get("sources", [])):
        iso2 = str(item.get("country", "")).upper()
        url = item.get("url")
        if iso2 not in COUNTRY_BY_ISO2 or not url:
            errors.append(f"row {index + 1}: country/url missing or invalid")
            continue
        country = COUNTRY_BY_ISO2[iso2]
        hints = " ".join(str(item.get(key, "")) for key in ("fee_type_hint", "card_segment_hint", "network_hint"))
        candidates.append({
            "country": iso2,
            "title": item.get("title") or "Manually registered public source",
            "url": _normalise_url(url),
            "description": hints,
            "published_date": item.get("published_date"),
            "language": item.get("language") or country.language,
            "source_name": item.get("source_name") or _source_name(url),
            "source_type": item.get("source_type") or _source_type(url),
            "search_engine": "manual_registry",
        })
    return candidates, {"enabled": True, "candidates": len(candidates), "errors": errors}

def _dedupe_candidates(candidates: list[dict]) -> list[dict]:
    by_key: dict[tuple[str, str], dict] = {}
    for candidate in candidates:
        key = (candidate["country"], _normalise_url(candidate["url"]))
        current = by_key.get(key)
        if current is None:
            by_key[key] = candidate
            continue
        # Merge snippets/engine names when both search layers found the same URL.
        descriptions = [current.get("description", ""), candidate.get("description", "")]
        current["description"] = " ".join(dict.fromkeys(d for d in descriptions if d))
        engines = set(str(current.get("search_engine", "")).split("+"))
        engines.add(candidate.get("search_engine", ""))
        current["search_engine"] = "+".join(sorted(e for e in engines if e))
        if not current.get("published_date"):
            current["published_date"] = candidate.get("published_date")
    return list(by_key.values())


def _extract_published_date(soup: BeautifulSoup) -> str | None:
    selectors = [
        ('meta[property="article:published_time"]', "content"),
        ('meta[name="date"]', "content"),
        ('meta[name="pubdate"]', "content"),
        ('time[datetime]', "datetime"),
    ]
    for selector, attr in selectors:
        node = soup.select_one(selector)
        raw = node.get(attr) if node else None
        if not raw:
            continue
        match = re.search(r"\d{4}-\d{2}-\d{2}", raw)
        if match:
            return match.group(0)
    return None


def fetch_document_text(candidate: dict) -> tuple[str | None, str | None]:
    url = candidate["url"]
    try:
        if not fetch.allowed(url):
            return None, None
        response = requests.get(
            url,
            headers={"User-Agent": fetch.USER_AGENT, "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.5"},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        if response.status_code in (401, 403, 429):
            return None, None
        response.raise_for_status()
    except requests.RequestException:
        return None, None

    content_type = response.headers.get("content-type", "").lower()
    final_url = _normalise_url(response.url)
    if "application/pdf" in content_type or final_url.lower().endswith(".pdf"):
        try:
            with pdfplumber.open(io.BytesIO(response.content)) as pdf:
                text = "\n".join((page.extract_text() or "") for page in pdf.pages[:80])
            return text[:MAX_TEXT_CHARS], candidate.get("published_date")
        except Exception:
            return None, None

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "form"]):
        tag.decompose()
    article = soup.find("article") or soup.find("main") or soup.body or soup
    paragraphs = [p.get_text(" ", strip=True) for p in article.find_all(["p", "li", "h1", "h2", "h3"])]
    text = " ".join(p for p in paragraphs if len(p) >= 20)
    return text[:MAX_TEXT_CHARS], candidate.get("published_date") or _extract_published_date(soup)


def _candidate_relevance(candidate: dict) -> int:
    text = f"{candidate.get('title', '')} {candidate.get('description', '')}".lower()
    fee_hits = sum(1 for terms in ALL_FEE_TERMS.values() for term in terms if term.lower() in text)
    number_hit = 1 if (PERCENT_RE.search(text) or BPS_RE.search(text) or FIXED_PREFIX_RE.search(text) or FIXED_SUFFIX_RE.search(text)) else 0
    source_bonus = 3 if candidate["source_type"] in {"official_network", "regulator"} else 1
    return fee_hits * 3 + number_hit * 4 + source_bonus


def search_public_fee_observations() -> dict:
    lookback_days = int(os.getenv("MEDIA_LOOKBACK_DAYS", str(DEFAULT_LOOKBACK_DAYS)))
    brave_key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()

    all_candidates: list[dict] = []
    manual, manual_status = manual_candidates()
    all_candidates.extend(manual)
    if brave_key:
        brave, brave_status = brave_candidates(brave_key, lookback_days)
        all_candidates.extend(brave)
    else:
        brave_status = {
            "enabled": False,
            "requests": 0,
            "candidates": 0,
            "errors": ["BRAVE_SEARCH_API_KEY is not configured"],
        }
        log.warning("BRAVE_SEARCH_API_KEY not set — broad web search is disabled; GDELT still runs.")

    gdelt, gdelt_status = gdelt_candidates(lookback_days)
    all_candidates.extend(gdelt)
    candidates = _dedupe_candidates(all_candidates)

    observations: list[dict] = []
    for candidate in candidates:
        observations.extend(
            extract_observations(candidate, candidate.get("description", ""), from_full_page=False)
        )

    page_fetch_limit = max(0, int(os.getenv("MEDIA_PAGE_FETCH_LIMIT", str(DEFAULT_PAGE_FETCH_LIMIT))))
    fetch_queue = sorted(candidates, key=_candidate_relevance, reverse=True)
    fetched_pages = 0
    for candidate in fetch_queue[:page_fetch_limit]:
        text, published_date = fetch_document_text(candidate)
        fetched_pages += 1
        if published_date:
            candidate["published_date"] = published_date
        if text:
            observations.extend(extract_observations(candidate, text, from_full_page=True))
        time.sleep(0.20)

    # One observation id is deterministic, so a cross-engine duplicate collapses.
    deduped = {item["id"]: item for item in observations}
    items = sorted(
        deduped.values(),
        key=lambda item: (item.get("published_date") or "", item["confidence"]),
        reverse=True,
    )
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for item in items:
        item["discovered_at"] = now

    return {
        "generated_at": now,
        "lookback_days": lookback_days,
        "items": items,
        "search_status": {
            "brave": brave_status,
            "gdelt": gdelt_status,
            "manual_registry": manual_status,
            "unique_candidates": len(candidates),
            "pages_fetched": fetched_pages,
            "observations_extracted": len(items),
        },
    }


def load_archive(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"items": []}
    return payload if isinstance(payload, dict) and isinstance(payload.get("items"), list) else {"items": []}


def merge_archive(previous: dict, current: dict) -> dict:
    merged = {item["id"]: dict(item) for item in previous.get("items", []) if item.get("id")}
    for item in current.get("items", []):
        old = merged.get(item["id"], {})
        new_item = dict(old)
        new_item.update(item)
        new_item["first_seen_at"] = old.get("first_seen_at") or old.get("discovered_at") or item.get("discovered_at")
        new_item["last_seen_at"] = item.get("discovered_at")
        merged[item["id"]] = new_item
    items = sorted(merged.values(), key=lambda i: (i.get("published_date") or "", i.get("last_seen_at") or ""), reverse=True)
    max_items = int(os.getenv("MEDIA_ARCHIVE_MAX_ITEMS", "10000"))
    return {
        "generated_at": current.get("generated_at"),
        "items": items[:max_items],
        "search_status": current.get("search_status", {}),
    }


def active_archive_items(archive: dict, lookback_days: int) -> list[dict]:
    cutoff = date.today() - timedelta(days=lookback_days)
    active = []
    for item in archive.get("items", []):
        raw_date = item.get("published_date") or item.get("last_seen_at") or item.get("discovered_at")
        if raw_date:
            try:
                if date.fromisoformat(raw_date[:10]) < cutoff:
                    continue
            except ValueError:
                pass
        active.append(item)
    return active


def _stat(values: list[float]) -> dict | None:
    if not values:
        return None
    return {
        "avg": round(statistics.mean(values), 6),
        "median": round(statistics.median(values), 6),
        "min": round(min(values), 6),
        "max": round(max(values), 6),
        "n": len(values),
    }


def aggregate_observations(items: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str, str, str], list[dict]] = {}
    for item in items:
        key = (
            item.get("country", ""),
            item.get("fee_type", ""),
            item.get("card_segment", "unspecified"),
            item.get("network", "unspecified"),
        )
        groups.setdefault(key, []).append(item)

    summary = []
    for (country, fee_type, segment, network), group in groups.items():
        percent_values = [
            (float(i["value_low"]) + float(i["value_high"])) / 2
            for i in group if i.get("value_kind") == "percent"
        ]
        fixed_groups: dict[tuple[str, str], list[float]] = {}
        for item in group:
            if item.get("value_kind") != "fixed":
                continue
            fixed_groups.setdefault((item.get("currency") or "", item.get("basis") or "unspecified"), []).append(
                (float(item["value_low"]) + float(item["value_high"])) / 2
            )
        fixed = [
            {"currency": currency, "basis": basis, **(_stat(values) or {})}
            for (currency, basis), values in sorted(fixed_groups.items())
        ]
        summary.append({
            "country": country,
            "fee_type": fee_type,
            "card_segment": segment,
            "network": network,
            "percent": _stat(percent_values),
            "fixed": fixed,
            "source_count": len({i.get("source_url") for i in group}),
            "observation_count": len(group),
            "max_confidence": max((i.get("confidence", 0) for i in group), default=0),
        })
    return sorted(summary, key=lambda x: (x["country"], x["fee_type"], x["card_segment"], x["network"]))
