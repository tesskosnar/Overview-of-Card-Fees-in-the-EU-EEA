import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import main  # noqa: E402


def test_preserves_previous_network_when_current_run_is_blocked():
    current = {
        "generated_at": "2026-07-20T05:00:00+00:00",
        "summary": {
            "visa": {"consumer_debit": {"avg": 0.2}},
            "mastercard": {"consumer_debit": None},
        },
        "countries": [
            {
                "iso2": "DE",
                "name": "Germany",
                "eu_member": True,
                "region": "Western",
                "visa": {"consumer_debit": {"avg": 0.2}},
            }
        ],
        "data_quality": {"visa": {}, "mastercard": {}},
    }
    previous = {
        "generated_at": "2026-07-13T05:00:00+00:00",
        "summary": {
            "visa": {"consumer_debit": {"avg": 0.2}},
            "mastercard": {"consumer_debit": {"avg": 0.2}},
        },
        "countries": [
            {
                "iso2": "DE",
                "name": "Germany",
                "eu_member": True,
                "region": "Western",
                "mastercard": {"consumer_debit": {"avg": 0.2}},
            }
        ],
        "data_quality": {"mastercard": {"countries_parsed": 1}},
    }

    merged = main.preserve_stale_networks(
        current,
        previous,
        {"visa": "ok", "mastercard": "blocked"},
    )

    assert merged["summary"]["mastercard"]["consumer_debit"]["avg"] == 0.2
    assert merged["countries"][0]["mastercard"]["consumer_debit"]["avg"] == 0.2
    assert merged["data_freshness"]["visa"]["status"] == "fresh"
    assert merged["data_freshness"]["mastercard"] == {
        "status": "stale",
        "as_of": "2026-07-13T05:00:00+00:00",
        "reason": "blocked",
    }
