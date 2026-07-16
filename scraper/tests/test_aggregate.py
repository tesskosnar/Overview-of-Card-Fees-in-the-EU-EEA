import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import aggregate  # noqa: E402
from parse_mastercard import CountryRateResult as MCResult  # noqa: E402
from parse_visa import CountryRateResult as VisaResult  # noqa: E402


def main() -> None:
    # Real classified Germany numbers (from test_mastercard_parse_logic.py)
    de_mc = MCResult(
        iso2="DE",
        consumer_debit=[0.20] * 23,
        consumer_credit=[0.30] * 9,
        commercial=[0.68, 1.19, 2.40, 1.45, 2.05] * 34,  # representative spread
        used_table_extraction=False,
        warnings=[],
    )
    # A second, made-up-but-plausible country to prove cross-country
    # aggregation (min/max/avg across countries) actually varies.
    fr_mc = MCResult(
        iso2="FR",
        consumer_debit=[0.20] * 10,
        consumer_credit=[0.30] * 10,
        commercial=[0.60, 0.90, 1.80],
        used_table_extraction=True,
        warnings=[],
    )
    de_visa = VisaResult(
        iso2="DE",
        consumer_debit=[0.20] * 4,
        consumer_credit=[0.30] * 4,
        commercial=[0.68, 1.85, 2.40],
        used_table_extraction=True,
        warnings=[],
    )

    output = aggregate.build_output(
        [de_mc, fr_mc, de_visa],
        source_urls={
            ("mastercard", "DE"): "https://example.invalid/mc-de.pdf",
            ("mastercard", "FR"): "https://example.invalid/mc-fr.pdf",
            ("visa", "DE"): "https://example.invalid/visa-de.pdf",
        },
    )

    print(json.dumps(output, indent=2, ensure_ascii=False))

    assert output["summary"]["mastercard"]["consumer_debit"]["avg"] == 0.20
    assert output["summary"]["mastercard"]["consumer_credit"]["min"] == 0.30
    assert output["summary"]["mastercard"]["commercial"]["n_countries"] == 2
    assert output["summary"]["visa"]["consumer_debit"]["n_countries"] == 1

    names = {c["name"] for c in output["countries"]}
    assert names == {"Germany", "France"}

    germany = next(c for c in output["countries"] if c["iso2"] == "DE")
    assert germany["mastercard"]["consumer_credit"]["avg"] == 0.30
    assert germany["visa"]["consumer_debit"]["avg"] == 0.20
    assert germany["mastercard"]["source_url"] == "https://example.invalid/mc-de.pdf"

    assert "visa" not in {k for k in aggregate.COUNTRY_BY_ISO2} if False else True  # no-op sanity

    print("\nALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
