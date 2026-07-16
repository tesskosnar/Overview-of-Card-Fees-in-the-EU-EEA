"""
Reproduces the EXACT real-world scenario from the first live GitHub
Actions run: Visa's listing page and PDFs all succeed, Mastercard's
listing page fetch raises RobotsDisallowed. Verifies main.py now (a)
still writes Visa's data, (b) records network_status correctly, and
(c) exits 0 instead of discarding everything.

This mocks the network layer (fetch.*) and the parsing entry points,
since main.py's own control flow — not parsing correctness, which is
covered by the other tests — is what's under test here.
"""

import json
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import main as main_module  # noqa: E402
import fetch  # noqa: E402
from parse_visa import CountryRateResult as VisaResult  # noqa: E402


def fake_fetch_html(url):
    if "visa" in url:
        return "<html>fake visa listing</html>"
    raise fetch.RobotsDisallowed(url)


def fake_fetch_pdf_bytes(url):
    return b"fake-pdf-bytes-not-actually-parsed"


def fake_discover_visa(html, base_url, countries):
    return {c.iso2: f"https://visa.example/{c.iso2}.pdf" for c in countries}


def fake_parse_visa(pdf_bytes, iso2):
    return VisaResult(iso2=iso2, consumer_debit=[0.20], consumer_credit=[0.30], commercial=[1.0, 2.0])


def main() -> None:
    test_countries = [c for c in main_module.EU_EEA_COUNTRIES if c.iso2 in {"AT", "DE"}]
    main_module.EU_EEA_COUNTRIES = test_countries

    main_module.fetch.fetch_html = fake_fetch_html
    main_module.fetch.fetch_pdf_bytes = fake_fetch_pdf_bytes
    main_module.discover.discover_visa = fake_discover_visa
    main_module.parse_visa.parse = fake_parse_visa

    data_dir = pathlib.Path("/tmp/main_test_data")
    shutil.rmtree(data_dir, ignore_errors=True)
    main_module.DATA_DIR = data_dir

    exit_code = main_module.main()
    print(f"exit_code = {exit_code}")
    assert exit_code == 0, "expected exit 0 — Visa succeeded, that alone should be enough to write+commit"

    output = json.loads((data_dir / "latest.json").read_text())
    print(json.dumps(output["network_status"], indent=2))
    print(json.dumps(output["summary"], indent=2))

    assert output["network_status"]["visa"] == "ok"
    assert output["network_status"]["mastercard"] == "blocked"
    assert output["summary"]["visa"]["consumer_credit"]["n_countries"] == 2
    assert output["summary"]["visa"]["consumer_credit"]["avg"] == 0.30
    assert output["summary"]["mastercard"]["consumer_credit"] is None
    assert len(output["countries"]) == 2

    print("\nALL ASSERTIONS PASSED — Visa's data survives a Mastercard robots.txt block")


if __name__ == "__main__":
    main()
