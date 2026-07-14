"""Best-effort setlist.fm lookup. Every failure degrades to None; nothing raises."""
import hashlib
import json
import logging
import os
import time
from pathlib import Path

import httpx

from llama.config import Config
from llama.songs import normalize_song

SEARCH_URL = "https://api.setlist.fm/rest/1.0/search/setlists"

log = logging.getLogger("llama")


def _name_match(a: str, b: str) -> bool:
    na, nb = normalize_song(a), normalize_song(b)
    return bool(na) and bool(nb) and (na in nb or nb in na)


def _pick(setlists: list[dict], venue: str | None, city: str | None) -> dict | None:
    if not setlists:
        return None
    if venue is None:
        # Without a venue to verify against, only a sole result is safe.
        return setlists[0] if len(setlists) == 1 else None
    for s in setlists:
        v = s.get("venue") or {}
        if _name_match(venue, v.get("name") or ""):
            return s
    if city:
        for s in setlists:
            v = s.get("venue") or {}
            if _name_match(city, (v.get("city") or {}).get("name") or ""):
                return s
    return None


class SetlistFMClient:
    def __init__(
        self,
        cache_dir: Path,
        api_key: str,
        client: httpx.Client | None = None,
        max_retries: int = 3,
        backoff_s: float = 1.0,
        rate_limit_s: float = 1.0,
    ):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = api_key
        self.client = client or httpx.Client(
            timeout=30,
            headers={"x-api-key": api_key, "accept": "application/json",
                     "user-agent": "llama-radio/0.1"},
        )
        self.max_retries = max_retries
        self.backoff_s = backoff_s
        self.rate_limit_s = rate_limit_s
        self._last_request = 0.0

    def _throttle(self) -> None:
        wait = self.rate_limit_s - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def setlist(self, artist: str, date: str,
                venue: str | None = None, city: str | None = None) -> dict | None:
        """The setlist.fm setlist for (artist, date) matching venue/city, or None.

        Never raises: any failure (network, malformed response, corrupted
        cache) degrades to None so setlist.fm lookups never fail gather.
        """
        try:
            key = "slfm_" + hashlib.sha1(f"{artist}|{date}".encode()).hexdigest()
            path = self.cache_dir / f"{key}.json"
            if path.exists():
                data = json.loads(path.read_text())
            else:
                data = self._search(artist, date)
                if data is None:
                    return None  # transient failure: try again next run
                if not data.get("setlist"):
                    cleaned = normalize_song(artist)
                    if cleaned and cleaned != artist.lower():
                        retried = self._search(cleaned, date)
                        if retried is not None:
                            data = retried
                tmp = path.with_suffix(".tmp")
                tmp.write_text(json.dumps(data))
                tmp.replace(path)
            return _pick(data.get("setlist", []), venue, city)
        except Exception as err:
            log.warning("setlist.fm lookup failed: %s", err)
            return None

    def _search(self, artist: str, date: str) -> dict | None:
        y, m, d = date.split("-")
        params = {"artistName": artist, "date": f"{d}-{m}-{y}"}
        for attempt in range(self.max_retries):
            self._throttle()
            try:
                resp = self.client.get(SEARCH_URL, params=params)
            except httpx.TransportError as err:
                log.warning("setlist.fm request failed: %s", err)
                if attempt < self.max_retries - 1:
                    time.sleep(self.backoff_s * (2**attempt))
                continue
            if resp.status_code == 404:
                return {"setlist": []}  # documented "no setlists found"
            if resp.status_code == 429 or resp.status_code >= 500:
                log.warning("setlist.fm returned %s", resp.status_code)
                if attempt < self.max_retries - 1:
                    time.sleep(self.backoff_s * (2**attempt))
                continue
            if resp.status_code >= 400:
                log.warning("setlist.fm returned %s for %s", resp.status_code, params)
                return None
            return resp.json()
        return None


def make_client(config: Config) -> SetlistFMClient | None:
    key = os.environ.get("SETLISTFM_API_KEY") or config.setlistfm.api_key
    if not key:
        return None
    return SetlistFMClient(config.root / "cache", key)
