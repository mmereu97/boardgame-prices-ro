"""A polite HTTP client: honest User-Agent, robots.txt, a minimum delay per host, retries.

Every shop is a small business. The collector reads only public pages that robots.txt
allows, never faster than the shop's Crawl-delay (or our own minimum), and stops on errors
instead of hammering.
"""
import logging
import time
import urllib.robotparser
from urllib.parse import urlsplit

import requests

log = logging.getLogger(__name__)

USER_AGENT = "boardgame-prices-ro/1.0 (personal price tracker; https://github.com/mmereu97/boardgame-prices-ro)"
DEFAULT_DELAY = 2.0          # seconds between two requests to the same host
RETRIES = 4


class Blocked(Exception):
    """robots.txt does not allow this URL."""


class PoliteSession:
    def __init__(self, min_delay: float = DEFAULT_DELAY, timeout: float = 30):
        self.http = requests.Session()
        self.http.headers["User-Agent"] = USER_AGENT
        self.min_delay = min_delay
        self.timeout = timeout
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._last: dict[str, float] = {}

    def _robots_for(self, url: str) -> urllib.robotparser.RobotFileParser:
        parts = urlsplit(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.http.get(host + "/robots.txt", timeout=self.timeout)
                rp.parse(r.text.splitlines() if r.ok else [])
            except requests.RequestException:
                rp.parse([])
            self._robots[host] = rp
        return self._robots[host]

    def delay_for(self, url: str) -> float:
        cd = self._robots_for(url).crawl_delay(USER_AGENT)
        return max(self.min_delay, float(cd or 0))

    def get(self, url: str, **kw) -> requests.Response:
        if not self._robots_for(url).can_fetch(USER_AGENT, url):
            raise Blocked(url)
        host = urlsplit(url).netloc
        wait = self.delay_for(url) - (time.monotonic() - self._last.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        for attempt in range(1, RETRIES + 1):
            self._last[host] = time.monotonic()
            try:
                r = self.http.get(url, timeout=self.timeout, **kw)
                if r.status_code in (429, 500, 502, 503, 504) and attempt < RETRIES:
                    # Honour Retry-After when the shop sends it; otherwise back off 1, 2, 3 minutes.
                    retry_after = r.headers.get("Retry-After", "")
                    pause = int(retry_after) if retry_after.isdigit() else 60 * attempt
                    log.warning("%s -> %s, retry in %ss", url, r.status_code, pause)
                    time.sleep(pause)
                    continue
                r.raise_for_status()
                return r
            except requests.ConnectionError:
                if attempt == RETRIES:
                    raise
                time.sleep(30 * attempt)
        raise RuntimeError("unreachable")
