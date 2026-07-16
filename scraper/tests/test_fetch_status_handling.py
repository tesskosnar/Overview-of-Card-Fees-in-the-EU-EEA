"""
Verifies the new HTTP 401/403/429 handling in fetch.py: a deliberate
rejection should raise RobotsDisallowed immediately, WITHOUT going
through the 3-attempt retry loop meant for transient failures (that
loop would just hammer a server that has already said no).
"""

import pathlib
import sys
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import fetch  # noqa: E402


def test_403_is_not_retried():
    call_count = {"n": 0}

    def fake_get(url, headers=None, timeout=None):
        call_count["n"] += 1
        resp = mock.Mock()
        resp.status_code = 403
        return resp

    with mock.patch("fetch.requests.get", side_effect=fake_get):
        with mock.patch("fetch.allowed", return_value=True):  # skip robots.txt check itself
            try:
                fetch.fetch_html("https://example.invalid/blocked-page")
                raised = False
            except fetch.RobotsDisallowed as exc:
                raised = True
                reason = exc.reason

    assert raised, "expected RobotsDisallowed to be raised for a 403 response"
    assert reason == "HTTP 403", f"expected reason 'HTTP 403', got {reason!r}"
    assert call_count["n"] == 1, f"expected exactly 1 request attempt (no retries), got {call_count['n']}"
    print("PASS: 403 raises RobotsDisallowed(reason='HTTP 403') after exactly 1 attempt")


def test_500_is_still_retried():
    call_count = {"n": 0}

    def fake_get(url, headers=None, timeout=None):
        call_count["n"] += 1
        resp = mock.Mock()
        resp.status_code = 500
        resp.raise_for_status.side_effect = fetch.requests.HTTPError("500 error")
        return resp

    with mock.patch("fetch.requests.get", side_effect=fake_get):
        with mock.patch("fetch.allowed", return_value=True):
            with mock.patch("fetch.time.sleep"):  # don't actually wait during the test
                result = fetch.fetch_html("https://example.invalid/flaky-page")

    assert result is None
    assert call_count["n"] == fetch.MAX_RETRIES, (
        f"expected {fetch.MAX_RETRIES} attempts for a transient 500, got {call_count['n']}"
    )
    print(f"PASS: 500 still retries {fetch.MAX_RETRIES} times as before")


if __name__ == "__main__":
    test_403_is_not_retried()
    test_500_is_still_retried()
    print("\nALL ASSERTIONS PASSED")
