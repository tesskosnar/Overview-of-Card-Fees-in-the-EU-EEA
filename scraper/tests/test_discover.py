"""
Structural sanity check for discover.py against small HAND-BUILT HTML
snippets that mirror the *pattern* observed on the real pages (a
heading immediately followed by a same-text "Download Current Fees"
link for Mastercard; a self-describing link for Visa). This is not
byte-for-byte real HTML (we can't pull that from this sandbox — no
network route to mastercard.com/visa.co.uk here), so it validates the
parsing *logic*, not the live site. main.py's own run logs (discovered
N/30 links) are the real-world check once this runs in GitHub Actions.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from discover import discover_mastercard, discover_visa  # noqa: E402
from sources import EU_EEA_COUNTRIES  # noqa: E402

VISA_HTML = """
<html><body>
<h2>Interchange fees by country</h2>
<a href="/dam/PDF/fees-and-interchange/april-25/austria-apr25.pdf">Austria Interchange Fees</a>
<a href="/dam/PDF/fees-and-interchange/april-25/germany-jan26.pdf">Germany Interchange Fees</a>
<a href="/dam/PDF/fees-and-interchange/april-25/denmark-apr25.pdf">Denmark, Greenland &amp; Faroe Islands Interchange Fees</a>
</body></html>
"""

MASTERCARD_HTML = """
<html><body>
<div class="accordion-item">
  <h3>Austria intra-location POS interchange fees</h3>
  <p>Austria Intra-Location Mastercard, Debit Mastercard and Maestro POS interchange fees are detailed below.</p>
  <a href="/content/dam/mccom/eu/.../Website_Austria_Intracountry_Interchange_Fees_1_Jan_2026.pdf">Download Current Fees</a>
</div>
<div class="accordion-item">
  <h3>Germany intra-location POS interchange fees</h3>
  <p>Germany Intra-Location Mastercard fees are detailed below.</p>
  <a href="/content/dam/mccom/eu/.../Website_Germany_Intracountry_Interchange_Fees_New_1_Jan_2026.pdf">Download Current Fees</a>
</div>
</body></html>
"""


def main() -> None:
    countries = [c for c in EU_EEA_COUNTRIES if c.iso2 in {"AT", "DE", "DK"}]

    visa_found = discover_visa(VISA_HTML, "https://www.visa.co.uk/x.html", countries)
    print("visa:", visa_found)
    assert visa_found["AT"].endswith("austria-apr25.pdf")
    assert visa_found["DE"].endswith("germany-jan26.pdf")
    assert visa_found["DK"].endswith("denmark-apr25.pdf"), "Denmark alias/prefix match failed"

    mc_countries = [c for c in EU_EEA_COUNTRIES if c.iso2 in {"AT", "DE"}]
    mc_found = discover_mastercard(MASTERCARD_HTML, "https://www.mastercard.com/x.html", mc_countries)
    print("mastercard:", mc_found)
    assert mc_found["AT"].endswith("Website_Austria_Intracountry_Interchange_Fees_1_Jan_2026.pdf")
    assert mc_found["DE"].endswith("Website_Germany_Intracountry_Interchange_Fees_New_1_Jan_2026.pdf")

    print("\nALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
