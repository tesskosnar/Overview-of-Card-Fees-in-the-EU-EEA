#!/usr/bin/env python3
"""
merge_manual_mastercard.py
===========================
Merges manual-mastercard-research.json (hand-verified by Claude,
fetched directly from Mastercard's own PDFs -- see that file's
_readme) into docs/data/latest.json, WITHOUT touching anything the
automated pipeline manages.

Run once from the repo root:
    python3 merge_manual_mastercard.py

Safe to re-run any time you add more countries to
manual-mastercard-research.json -- it always merges fresh, it doesn't
accumulate duplicates.
"""
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LATEST = ROOT / "docs" / "data" / "latest.json"
MANUAL = ROOT / "manual-mastercard-research.json"

COUNTRY_NAMES = {
    "DE": "Germany", "FR": "France", "IT": "Italy", "CZ": "Czech Republic",
    "PL": "Poland", "ES": "Spain", "NL": "Netherlands", "AT": "Austria",
    "BE": "Belgium", "HR": "Croatia", "LV": "Latvia", "HU": "Hungary",
    "CY": "Cyprus", "DK": "Denmark", "IE": "Ireland", "LU": "Luxembourg",
    "PT": "Portugal", "RO": "Romania", "SK": "Slovakia", "SI": "Slovenia",
    "GR": "Greece", "MT": "Malta", "SE": "Sweden", "NO": "Norway", "BG": "Bulgaria",
}


def block(avg, lo, hi, n=1):
    if avg is None:
        return None
    return {"avg": avg, "min": lo, "max": hi, "n_values": n}


def commercial_block(data):
    lo, hi = data.get("commercial_min"), data.get("commercial_max")
    if lo is None or hi is None:
        return None  # e.g. Bulgaria: consumer confirmed, commercial not found
    return block(statistics.mean([lo, hi]), lo, hi)


def main():
    latest = json.loads(LATEST.read_text(encoding="utf-8"))
    manual = json.loads(MANUAL.read_text(encoding="utf-8"))

    by_iso = {c["iso2"]: c for c in latest.get("countries", [])}

    for iso2, data in manual["countries"].items():
        entry = by_iso.setdefault(iso2, {
            "iso2": iso2,
            "name": COUNTRY_NAMES.get(iso2, iso2),
            "eu_member": True,
            "region": None,
        })
        warnings = [
            "MANUALLY researched (Mastercard's automated feed is blocked by their own "
            f"robots.txt) -- fetched and hand-verified by Claude on {manual['fetched_at']} "
            "directly from the source PDF, not from a live automated run."
        ]
        if data.get("notes"):
            warnings.append(data["notes"])

        mc_block = {
            "consumer_debit": block(data["consumer_debit"], data["consumer_debit"], data["consumer_debit"]),
            "consumer_credit": block(data["consumer_credit"], data["consumer_credit"], data["consumer_credit"]),
            "commercial": commercial_block(data),
            "source_url": data["source_url"],
            "used_table_extraction": False,
            "warnings": warnings,
        }
        entry["mastercard"] = mc_block

    latest["countries"] = sorted(by_iso.values(), key=lambda c: c["name"])

    # keep the visa/mastercard summary cards showing only real automated
    # averages -- these 7 manual points are too small a sample (and too
    # inconsistently sourced) to blend into the EU-wide summary honestly.
    # They show up in the country table and CSV export, just not the hero cards.
    if not latest.get("note"):
        latest["note"] = ""
    manual_note = (
        f" {len(manual['countries'])} countries have hand-researched Mastercard figures "
        "(see the warning icon per row) -- not from the automated pipeline, which remains "
        "blocked for Mastercard."
    )
    if manual_note not in latest["note"]:
        latest["note"] = (latest["note"] + manual_note).strip()

    LATEST.write_text(json.dumps(latest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Merged manual Mastercard data for {len(manual['countries'])} countries into {LATEST}")


if __name__ == "__main__":
    main()
