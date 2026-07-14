import hashlib
import json
import time
from pathlib import Path
from urllib.parse import quote

import httpx

SEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_URL = "https://archive.org/metadata/{identifier}"
DOWNLOAD_URL = "https://archive.org/download/{identifier}/{filename}"


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

    def _get(self, url: str, params: dict | None = None) -> httpx.Response:
        last: Exception | None = None
        for attempt in range(self.max_retries):
            self._throttle()
            try:
                resp = self.client.get(url, params=params)
            except httpx.TransportError as e:
                last = e
                if attempt < self.max_retries - 1:
                    time.sleep(self.backoff_s * (2**attempt))
                continue
            if 400 <= resp.status_code < 500:
                # Client errors are not transient: retrying won't help.
                raise IAError(f"archive.org returned {resp.status_code} for {url}")
            if resp.status_code >= 500:
                last = IAError(f"archive.org returned {resp.status_code}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.backoff_s * (2**attempt))
                continue
            return resp
        raise IAError(f"GET {url} failed after {self.max_retries} attempts: {last}") from last

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
