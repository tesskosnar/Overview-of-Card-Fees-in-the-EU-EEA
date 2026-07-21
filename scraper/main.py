#!/usr/bin/env python3
"""
Run the monthly card-fee collection pipeline (GitHub Actions entry point).

1. Live scrape of Visa's official rate sheets (30 EU/EEA countries).
2. Merge in manual_mastercard_research.json (Mastercard blocks automated
   fetches at the listing-page level, so this stays a hand-researched
   file -- update it yourself periodically the same way it was built:
   fetch each country's PDF from
   https://www.mastercard.com/europe/en/business/support/merchant-interchange-rates.html
   and fill in a new entry).
3. Writes docs/data/latest.json and appends today's snapshot to
   docs/data/history/.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pipeline  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger("main")

ROOT = Path(__file__).parent.parent
DOCS = ROOT / "docs"
DATA = DOCS / "data"
HISTORY = DATA / "history"
MANUAL_MC = ROOT / "manual-mastercard-research.json"


def load_manual_mastercard() -> list[pipeline.CountryRateResult]:
    manual = json.loads(MANUAL_MC.read_text(encoding="utf-8"))
    results = []
    for iso2, d in manual["countries"].items():
        lo, hi = d.get("commercial_min"), d.get("commercial_max")
        comm = [lo, hi] if (lo is not None and hi is not None) else []
        contactless = d.get("commercial_contactless")
        comm_headline = [contactless] if contactless is not None else []
        debit = [d["consumer_debit"]] if d["consumer_debit"] is not None else []
        results.append(pipeline.CountryRateResult(
            iso2=iso2, network="mastercard",
            consumer_debit=debit, consumer_credit=[d["consumer_credit"]],
            commercial=comm, commercial_headline=comm_headline,
            commercial_labeled=[("Contactless (Business)", contactless)] if contactless is not None else [],
            used_table_extraction=False,
            warnings=["Manually researched, not live-scraped -- see manual-mastercard-research.json"]
            + ([d["notes"]] if d.get("notes") else [])
            + ([] if contactless is not None else ["Contactless-specific rate not yet re-verified for this country -- headline uses the midpoint of the published range instead"]),
            source_url=d["source_url"],
        ))
    log.info("Loaded manual Mastercard data for %d countries (fetched_at=%s)", len(results), manual["fetched_at"])
    return results



def update_history(output: dict) -> None:
    HISTORY.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    (HISTORY / f"{today}.json").write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    entries = []
    for f in sorted(HISTORY.glob("*.json")):
        if f.name == "index.json":
            continue
        entries.append({"date": f.stem, "file": f.name})
    entries.sort(key=lambda e: e["date"])
    (HISTORY / "index.json").write_text(json.dumps(entries, indent=2), encoding="utf-8")
    log.info("History now has %d snapshots", len(entries))


def main() -> int:
    try:
        visa_results = pipeline.run_visa_scrape()
    except Exception:
        log.exception("Visa scrape failed entirely -- keeping previous latest.json untouched")
        return 1
    log.info("Visa: %d/%d countries parsed", len(visa_results), len(pipeline.EU_EEA_COUNTRIES))

    mastercard_results = load_manual_mastercard()

    output = pipeline.build_output(visa_results + mastercard_results)

    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "latest.json").write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Wrote %s", DATA / "latest.json")

    update_history(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())    manual = json.loads(MANUAL_MC.read_text(encoding="utf-8"))
    results = []
    for iso2, d in manual["countries"].items():
        lo, hi = d.get("commercial_min"), d.get("commercial_max")
        comm = [lo, hi] if (lo is not None and hi is not None) else []
        debit = [d["consumer_debit"]] if d["consumer_debit"] is not None else []
        results.append(pipeline.CountryRateResult(
            iso2=iso2, network="mastercard",
            consumer_debit=debit, consumer_credit=[d["consumer_credit"]],
            commercial=comm, used_table_extraction=False,
            warnings=["Manually researched, not live-scraped -- see manual-mastercard-research.json"]
            + ([d["notes"]] if d.get("notes") else []),
            source_url=d["source_url"],
        ))
    log.info("Loaded manual Mastercard data for %d countries (fetched_at=%s)", len(results), manual["fetched_at"])
    return results


def update_history(output: dict) -> None:
    HISTORY.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    (HISTORY / f"{today}.json").write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    entries = []
    for f in sorted(HISTORY.glob("*.json")):
        if f.name == "index.json":
            continue
        entries.append({"date": f.stem, "file": f.name})
    entries.sort(key=lambda e: e["date"])
    (HISTORY / "index.json").write_text(json.dumps(entries, indent=2), encoding="utf-8")
    log.info("History now has %d snapshots", len(entries))


def main() -> int:
    try:
        visa_results = pipeline.run_visa_scrape()
    except Exception:
        log.exception("Visa scrape failed entirely -- keeping previous latest.json untouched")
        return 1
    log.info("Visa: %d/%d countries parsed", len(visa_results), len(pipeline.EU_EEA_COUNTRIES))

    mastercard_results = load_manual_mastercard()

    output = pipeline.build_output(visa_results + mastercard_results)

    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "latest.json").write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Wrote %s", DATA / "latest.json")

    update_history(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
