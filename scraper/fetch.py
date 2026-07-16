"""
fetch.py
========
All outbound HTTP goes through here, so "be a polite scraper" is
enforced in exactly one place:

  - every request identifies itself with a real User-Agent and a
    contact URL (the repo), instead of pretending to be a browser
  - robots.txt is checked before every request and cached per-domain
    for the run
  - requests are spaced out (default 1.5s) instead of fired in a burst
  - transient failures are retried with backoff; a PDF that still
    fails after retries is skipped (logged), not fatal to the whole run

This module makes real network calls, so it only does anything useful
when run from GitHub Actions (or any machine with normal internet
access) — it is not expected to work from a network-restricted
sandbox.
"""

from __future__ import annotations

import logging
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)


class RobotsDisallowed(Exception):
    """Raised when a site tells us — either via robots.txt, or by
    actively rejecting the request with HTTP 401/403/429 — that it
    doesn't want automated access. Both are treated as the same kind
    of deliberate, likely-permanent signal (as opposed to a transient
    5xx/timeout), so both raise this one exception; callers don't need
    to know which mechanism triggered it, just that retrying won't help."""

    def __init__(self, url: str, reason: str = "robots.txt"):
        self.url = url
        self.reason = reason
        super().__init__(f"Access denied ({reason}): {url}")


USER_AGENT = (
    "CardFeeTrackerBot/1.0 "
    "(public-interest research; monthly read-only fetch of publicly published "
    "interchange rate sheets; contact via repository owner)"
)

REQUEST_DELAY_SECONDS = 1.5
TIMEOUT_SECONDS = 20
MAX_RETRIES = 3

_robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}
_robots_raw_cache: dict[str, str] = {}


def _fetch_robots_txt(origin: str) -> str:
    """Fetches robots.txt for `origin` via `requests`, not
    RobotFileParser.read(). read() shells out to urllib.request with NO
    timeout, which can hang indefinitely if a server is slow to answer —
    every other request in this module goes through `requests` with an
    explicit TIMEOUT_SECONDS specifically to avoid that failure mode, so
    robots.txt shouldn't be the one exception. Returns "" (treated as
    "no rules found", i.e. allowed) if it's unreachable or returns a
    non-200 status."""
    robots_url = urljoin_robots(origin)
    try:
        resp = requests.get(robots_url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS)
        return resp.text if resp.status_code == 200 else ""
    except requests.RequestException as exc:
        log.warning("Could not read robots.txt for %s (%s); proceeding cautiously", origin, exc)
        return ""


def _robots_for(url: str) -> urllib.robotparser.RobotFileParser:
    origin = "{0.scheme}://{0.netloc}".format(urlparse(url))
    if origin not in _robots_cache:
        raw = _fetch_robots_txt(origin)
        _robots_raw_cache[origin] = raw
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(raw.splitlines())
        _robots_cache[origin] = rp
    return _robots_cache[origin]


def _log_raw_robots_txt(url: str) -> None:
    """Logs whatever we already fetched for this origin in _robots_for()
    — no second network call, so this can't behave differently than the
    check that actually made the decision."""
    origin = "{0.scheme}://{0.netloc}".format(urlparse(url))
    raw = _robots_raw_cache.get(origin, "")
    log.warning("---- raw %s ----\n%s\n---- end robots.txt ----",
                 urljoin_robots(origin), raw[:4000] if raw else "(empty, unreachable, or non-200 response)")


def urljoin_robots(origin: str) -> str:
    return origin.rstrip("/") + "/robots.txt"


_robots_logged: set[str] = set()


def allowed(url: str) -> bool:
    try:
        return _robots_for(url).can_fetch(USER_AGENT, url)
    except Exception:
        # If robots.txt genuinely can't be evaluated, default to
        # "allowed" for a page whose entire purpose is public
        # merchant/consumer disclosure — but this is logged above.
        return True


def _get(url: str, *, as_binary: bool) -> bytes | str | None:
    if not allowed(url):
        log.error("Blocked by robots.txt, skipping: %s", url)
        origin = "{0.scheme}://{0.netloc}".format(urlparse(url))
        if origin not in _robots_logged:
            _robots_logged.add(origin)
            _log_raw_robots_txt(url)
        raise RobotsDisallowed(url)

    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
                timeout=TIMEOUT_SECONDS,
            )
            if resp.status_code in (401, 403, 429):
                # A deliberate rejection, not a glitch — retrying the
                # same request 3 times would just hammer their server
                # for no benefit, so this bypasses the retry loop
                # entirely and is treated the same as a robots.txt block.
                log.error("%s responded HTTP %d — treating as a deliberate block, not retrying",
                          url, resp.status_code)
                raise RobotsDisallowed(url, reason=f"HTTP {resp.status_code}")
            resp.raise_for_status()
            time.sleep(REQUEST_DELAY_SECONDS)
            return resp.content if as_binary else resp.text
        except requests.RequestException as exc:
            last_exc = exc
            wait = 2**attempt
            log.warning("Fetch failed (attempt %d/%d) for %s: %s — retrying in %ss",
                        attempt, MAX_RETRIES, url, exc, wait)
            time.sleep(wait)
    log.error("Giving up on %s after %d attempts: %s", url, MAX_RETRIES, last_exc)
    return None


def fetch_html(url: str) -> str | None:
    return _get(url, as_binary=False)  # type: ignore[return-value]


def fetch_pdf_bytes(url: str) -> bytes | None:
    return _get(url, as_binary=True)  # type: ignore[return-value]
