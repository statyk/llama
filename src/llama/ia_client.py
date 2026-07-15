import hashlib
import json
import logging
import time
from pathlib import Path
from urllib.parse import quote

import httpx

log = logging.getLogger("llama")

SEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_URL = "https://archive.org/metadata/{identifier}"
DOWNLOAD_URL = "https://archive.org/download/{identifier}/{filename}"
SCRAPE_URL = "https://archive.org/services/search/v1/scrape"


class IAError(Exception):
    pass


class IAClient:
    def __init__(
        self,
        cache_dir: Path,
        client: httpx.Client | None = None,
        max_retries: int = 3,
        backoff_s: float = 1.0,
        rate_limit_s: float = 0.5,
    ):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.client = client or httpx.Client(
            timeout=60, follow_redirects=True, headers={"user-agent": "llama-radio/0.1"}
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

    def _get(self, url: str, params: dict | None = None, *,
             max_retries: int | None = None, backoff_s: float | None = None) -> httpx.Response:
        retries = max_retries if max_retries is not None else self.max_retries
        backoff = backoff_s if backoff_s is not None else self.backoff_s
        last: Exception | None = None
        for attempt in range(retries):
            self._throttle()
            try:
                resp = self.client.get(url, params=params)
            except httpx.TransportError as e:
                last = e
                if attempt < retries - 1:
                    time.sleep(backoff * (2**attempt))
                continue
            if 400 <= resp.status_code < 500:
                # Client errors are not transient: retrying won't help.
                raise IAError(f"archive.org returned {resp.status_code} for {url}")
            if resp.status_code >= 500:
                last = IAError(f"archive.org returned {resp.status_code}")
                if attempt < retries - 1:
                    time.sleep(backoff * (2**attempt))
                continue
            return resp
        raise IAError(f"GET {url} failed after {retries} attempts: {last}") from last

    def _cached(self, key: str, fetch) -> dict | list:
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text())
        data = fetch()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        tmp.replace(path)
        return data

    def search(self, query: str, fields: list[str], rows: int = 500) -> list[dict]:
        key = "search_" + hashlib.sha1(f"{query}|{fields}|{rows}".encode()).hexdigest()

        def fetch() -> list[dict]:
            params = {"q": query, "fl[]": fields, "rows": rows, "page": 1, "output": "json"}
            return self._get(SEARCH_URL, params).json()["response"]["docs"]

        return self._cached(key, fetch)

    def scrape(self, query: str, fields: list[str], count: int = 10000) -> list[dict]:
        """Cursor-paginated bulk listing via the scrape API. Not disk-cached:
        callers persist aggregates (e.g. the artist index), not raw pages.

        More patient than the default policy: a ~30-page bulk pull should ride
        out a multi-second archive.org 5xx burst rather than die mid-build.
        """
        out: list[dict] = []
        cursor: str | None = None
        while True:
            params: dict = {"q": query, "fields": ",".join(fields), "count": count}
            if cursor:
                params["cursor"] = cursor
            try:
                data = self._get(SCRAPE_URL, params,
                                 max_retries=max(5, self.max_retries),
                                 backoff_s=self.backoff_s * 2).json()
            except json.JSONDecodeError as e:
                raise IAError(f"scrape returned non-JSON for {query!r}") from e
            out.extend(data.get("items", []))
            log.info("scrape: %s/%s docs", f"{len(out):,}", f"{data.get('total', 0):,}")
            cursor = data.get("cursor")
            if not cursor:
                return out

    def metadata(self, identifier: str) -> dict:
        def fetch() -> dict:
            return self._get(METADATA_URL.format(identifier=identifier)).json()

        return self._cached(f"md_{identifier}", fetch)

    def download_file(self, identifier: str, filename: str, dest: Path, md5: str | None = None) -> Path:
        url = DOWNLOAD_URL.format(identifier=identifier, filename=quote(filename))
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        last: Exception | None = None
        for attempt in range(self.max_retries):
            self._throttle()
            try:
                h = hashlib.md5()
                with self.client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    with tmp.open("wb") as f:
                        for chunk in resp.iter_bytes():
                            f.write(chunk)
                            h.update(chunk)
                if md5 and h.hexdigest() != md5:
                    tmp.unlink()
                    raise IAError(f"md5 mismatch downloading {filename}")
                tmp.replace(dest)
                return dest
            except httpx.HTTPError as e:
                last = e
                tmp.unlink(missing_ok=True)
                if attempt < self.max_retries - 1:
                    time.sleep(self.backoff_s * (2**attempt))
        raise IAError(f"download of {filename} failed after {self.max_retries} attempts: {last}") from last
