"""
aggregate.py
============
Combines per-country CountryRateResult objects (one per network per
country) into the single JSON file the dashboard reads:
  - a per-network, per-category summary (average / min / max across
    all successfully-parsed countries) — this is the headline
    "průměrný poplatek a rozsah" stat
  - a per-country table with each network's numbers side by side
  - a data-quality section so parsing gaps are visible instead of
    silently averaged away
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone
from typing import Any

from sources import COUNTRY_BY_ISO2, IFR_CAP, REGIONS

CATEGORIES = ["consumer_debit", "consumer_credit", "commercial"]


def _stat_block(values: list[float]) -> dict[str, Any] | None:
    if not values:
        return None
    return {
        "avg": round(statistics.mean(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "n_values": len(values),
    }


def _country_category_value(result, category: str) -> dict[str, Any] | None:
    values = getattr(result, category)
    return _stat_block(values)


def build_summary(results: list) -> dict[str, Any]:
    """`results` is a flat list of CountryRateResult (both networks
    mixed together, distinguished by .network)."""

    by_network: dict[str, list] = {"visa": [], "mastercard": []}
    for r in results:
        by_network.setdefault(r.network, []).append(r)

    summary: dict[str, Any] = {}
    for network, network_results in by_network.items():
        network_summary = {}
        for category in CATEGORIES:
            # one representative value per country (its own average,
            # so a country with many identical tier rows doesn't
            # outweigh one with few) feeds the cross-country stat
            per_country_avgs = []
            for r in network_results:
                block = _country_category_value(r, category)
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
    # Keep every EU/EEA country in the dashboard even when a particular
    # network has no data. This is essential for public-source scheme/MSC
    # observations and lets the UI hide empty network columns rather than
    # hiding the country itself.
    by_iso2: dict[str, dict[str, Any]] = {
        iso2: {
            "iso2": iso2,
            "name": country.name,
            "eu_member": country.eu_member,
            "region": country.region,
        }
        for iso2, country in COUNTRY_BY_ISO2.items()
    }
    for r in results:
        country = COUNTRY_BY_ISO2.get(r.iso2)
        entry = by_iso2.setdefault(
            r.iso2,
            {
                "iso2": r.iso2,
                "name": country.name if country else r.iso2,
                "eu_member": country.eu_member if country else None,
                "region": country.region if country else None,
            },
        )
        entry[r.network] = {
            "consumer_debit": _country_category_value(r, "consumer_debit"),
            "consumer_credit": _country_category_value(r, "consumer_credit"),
            "commercial": _country_category_value(r, "commercial"),
            "source_url": getattr(r, "source_url", None),
            "used_table_extraction": r.used_table_extraction,
            "warnings": r.warnings,
        }
    return sorted(by_iso2.values(), key=lambda e: e["name"])


def build_data_quality(results: list) -> dict[str, Any]:
    quality: dict[str, Any] = {}
    for network in ("visa", "mastercard"):
        net_results = [r for r in results if r.network == network]
        with_warnings = [r for r in net_results if r.warnings]
        unclassified_total = sum(len(r.unclassified) for r in net_results)
        quality[network] = {
            "countries_parsed": len(net_results),
            "countries_with_warnings": len(with_warnings),
            "unclassified_rows_total": unclassified_total,
            "countries_with_warnings_detail": {
                r.iso2: r.warnings for r in with_warnings
            },
        }
    return quality


def build_output(results: list, source_urls: dict[tuple[str, str], str]) -> dict[str, Any]:
    for r in results:
        r.source_url = source_urls.get((r.network, r.iso2))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope": {
            "fee_types": ["interchange", "scheme_fee", "processing_fee", "merchant_service_charge"],
            "networks": ["visa", "mastercard"],
            "region": "EU/EEA",
            "country_count": len(COUNTRY_BY_ISO2),
            "update_cadence": "monthly",
        },
        "ifr_cap": IFR_CAP,
        "regions": REGIONS,
        "summary": build_summary(results),
        "countries": build_country_table(results),
        "data_quality": build_data_quality(results),
    }
