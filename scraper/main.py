#!/usr/bin/env python3
"""Run the monthly card-fee collection pipeline.

Layers:
1. Official Visa/Mastercard interchange rate sheets.
2. Public observations of interchange, scheme/processing fees and merchant
   service charges discovered through Brave Search and GDELT.
3. Dated snapshots for dashboard trend charts.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import aggregate
import discover
import fetch
import media_search
import parse_mastercard
import parse_visa
from sources import EU_EEA_COUNTRIES, MASTERCARD_LISTING_URL, VISA_LISTING_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("main")

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "docs" / "data"
MIN_SUCCESS_FRACTION = 0.5


def load_previous_output() -> dict | None:
    try:
        payload = json.loads((DATA_DIR / "latest.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def preserve_stale_networks(output: dict, previous: dict | None, network_status: dict[str, str]) -> dict:
    """Retain the last good network data when the current scrape fails."""
    generated_at = output.get("generated_at")
    previous_generated_at = previous.get("generated_at") if previous else None
    freshness: dict[str, dict] = {}
    current_by_iso = {c["iso2"]: c for c in output.get("countries", []) if c.get("iso2")}
    previous_by_iso = {c["iso2"]: c for c in (previous or {}).get("countries", []) if c.get("iso2")}

    for network in ("visa", "mastercard"):
        status = network_status.get(network, "failed")
        if status == "ok":
            freshness[network] = {"status": "fresh", "as_of": generated_at}
            continue

        preserved = False
        if previous:
            previous_summary = previous.get("summary", {}).get(network)
            if previous_summary:
                output.setdefault("summary", {})[network] = previous_summary
                preserved = True
            previous_quality = previous.get("data_quality", {}).get(network)
            if previous_quality:
                output.setdefault("data_quality", {})[network] = previous_quality
            for iso2, old_country in previous_by_iso.items():
                old_block = old_country.get(network)
                if not old_block:
                    continue
                target = current_by_iso.setdefault(
                    iso2,
                    {
                        "iso2": iso2,
                        "name": old_country.get("name", iso2),
                        "eu_member": old_country.get("eu_member"),
                        "region": old_country.get("region"),
                    },
                )
                target[network] = old_block
                preserved = True

        freshness[network] = {
            "status": "stale" if preserved else "unavailable",
            "as_of": previous_generated_at if preserved else None,
            "reason": status,
        }

    output["countries"] = sorted(current_by_iso.values(), key=lambda c: c.get("name", c["iso2"]))
    output["data_freshness"] = freshness
    return output


def run_network(network: str) -> tuple[list, dict[tuple[str, str], str], str]:
    if network == "visa":
        listing_url, discover_fn, parser_module = VISA_LISTING_URL, discover.discover_visa, parse_visa
    else:
        listing_url, discover_fn, parser_module = MASTERCARD_LISTING_URL, discover.discover_mastercard, parse_mastercard

    log.info("[%s] fetching listing page: %s", network, listing_url)
    try:
        html = fetch.fetch_html(listing_url)
    except fetch.RobotsDisallowed:
        return [], {}, "blocked"
    if not html:
        return [], {}, "failed"

    pdf_urls = discover_fn(html, listing_url, EU_EEA_COUNTRIES)
    log.info("[%s] discovered %d/%d country PDFs", network, len(pdf_urls), len(EU_EEA_COUNTRIES))

    results = []
    source_urls: dict[tuple[str, str], str] = {}
    blocked_count = 0
    for country in EU_EEA_COUNTRIES:
        url = pdf_urls.get(country.iso2)
        if not url:
            continue
        try:
            pdf_bytes = fetch.fetch_pdf_bytes(url)
        except fetch.RobotsDisallowed:
            blocked_count += 1
            continue
        if not pdf_bytes:
            continue
        try:
            result = parser_module.parse(pdf_bytes, country.iso2)
        except Exception as exc:
            log.error("[%s] %s parsing failed: %s", network, country.name, exc)
            continue
        results.append(result)
        source_urls[(network, country.iso2)] = url

    if blocked_count == len(EU_EEA_COUNTRIES):
        return results, source_urls, "blocked"
    fraction = len(results) / len(EU_EEA_COUNTRIES)
    return results, source_urls, "ok" if fraction >= MIN_SUCCESS_FRACTION else "failed"


def _empty_output() -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope": {
            "fee_types": ["interchange", "scheme_fee", "processing_fee", "merchant_service_charge"],
            "networks": ["visa", "mastercard"],
            "region": "EU/EEA",
            "country_count": len(EU_EEA_COUNTRIES),
            "update_cadence": "monthly",
        },
        "summary": {},
        "countries": [],
        "data_quality": {},
    }


def _write_history(output: dict) -> None:
    history_dir = DATA_DIR / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    history_path = history_dir / f"{stamp}.json"
    history_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    index_path = history_dir / "index.json"
    try:
        existing = json.loads(index_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        existing = []
    existing = [item for item in existing if item.get("date") != stamp]
    existing.append({"date": stamp, "file": f"{stamp}.json"})
    existing.sort(key=lambda item: item["date"])
    index_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    previous_output = load_previous_output()

    all_results = []
    all_source_urls: dict[tuple[str, str], str] = {}
    network_status: dict[str, str] = {}
    for network in ("visa", "mastercard"):
        results, source_urls, status = run_network(network)
        network_status[network] = status
        if status == "ok":
            all_results.extend(results)
            all_source_urls.update(source_urls)
        else:
            log.warning("[%s] current scrape status: %s; previous data will be retained when available", network, status)

    if all_results:
        output = aggregate.build_output(all_results, all_source_urls)
    elif previous_output:
        output = _empty_output()
        output["note"] = "The official rate-sheet scrape failed this month; previous verified network data is retained and marked stale."
    else:
        log.error("No official data and no previous snapshot are available; refusing to create an empty dashboard.")
        return 1

    output["network_status"] = network_status
    output = preserve_stale_networks(output, previous_output, network_status)

    archive_path = DATA_DIR / "media_archive.json"
    previous_archive = media_search.load_archive(archive_path)
    try:
        current_public = media_search.search_public_fee_observations()
    except Exception as exc:  # media is useful but must not break the official layer
        log.exception("Public-source discovery failed: %s", exc)
        current_public = {
            "generated_at": output["generated_at"],
            "lookback_days": 400,
            "items": [],
            "search_status": {"fatal_error": str(exc)},
        }

    archive = media_search.merge_archive(previous_archive, current_public)
    archive_path.write_text(json.dumps(archive, indent=2, ensure_ascii=False), encoding="utf-8")
    lookback_days = int(current_public.get("lookback_days", 400))
    active_items = media_search.active_archive_items(archive, lookback_days)
    max_dashboard_items = int(__import__("os").getenv("MEDIA_DASHBOARD_MAX_ITEMS", "800"))
    output["public_fee_observations"] = {
        "generated_at": current_public.get("generated_at"),
        "lookback_days": lookback_days,
        "items": active_items[:max_dashboard_items],
        "summary": media_search.aggregate_observations(active_items),
        "active_count": len(active_items),
        "archive_count": len(archive.get("items", [])),
        "search_status": current_public.get("search_status", {}),
        "methodology": (
            "Publicly reported observations are kept separate from official interchange rate sheets. "
            "Averages are simple averages of explicit percentage values found in the active lookback window; "
            "they are not transaction-weighted market averages."
        ),
    }

    latest_path = DATA_DIR / "latest.json"
    latest_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_history(output)

    log.info("Wrote %s", latest_path)
    log.info("Public observations: %d active / %d archived", len(active_items), len(archive.get("items", [])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
