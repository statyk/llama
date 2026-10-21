import hashlib
import itertools
import json
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import httpx

from llama.errors import LlamaError
from llama.status import detail
from llama.workspace import atomic_write_text

SEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_URL = "https://archive.org/metadata/{identifier}"
DOWNLOAD_URL = "https://archive.org/download/{identifier}/{filename}"
SCRAPE_URL = "https://archive.org/services/search/v1/scrape"

# Audio downloads (spec 2026-10-21 §1). A stall (read) timeout, not a total-time
# bound: healthy archive.org transfers run at ~50-100 KB/s and take minutes.
DOWNLOAD_CONNECT_TIMEOUT_S = 10.0
DOWNLOAD_STALL_TIMEOUT_S = 20.0
# Repeat attempts after the first pass stop starting once this much clock time
# (attempts + sleeps, less slot waits) has passed since the first pass ended.
DOWNLOAD_DEADLINE_S = 60.0
DOWNLOAD_SLEEP_MIN_S = 1.0
DOWNLOAD_SLEEP_MAX_S = 4.0
_DOWNLOAD_TIMEOUT = httpx.Timeout(DOWNLOAD_STALL_TIMEOUT_S, connect=DOWNLOAD_CONNECT_TIMEOUT_S)
# Not 5xx but transient: a retry may get a different answer.
_RETRYABLE_STATUS = frozenset({408, 429})


class IAError(LlamaError):
    pass


class IADownloadError(IAError):
    """A download that exhausted every candidate URL. The message starts
    `download of <filename> failed:` (failure records and operator greps match it)."""


@dataclass(frozen=True)
class _Attempt:
    """One download attempt's outcome. `ok` means the `.part` is complete and
    verified; otherwise `error` says why and `retryable` whether the schedule's
    repeat attempts may ask this URL again."""

    ok: bool
    error: str = ""
    retryable: bool = False
    slot_wait_s: float = 0.0  # time spent waiting for a download slot (not counted)


def _http_error_text(exc: httpx.HTTPError) -> str:
    return f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__


def _file_md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


class IAClient:
    def __init__(
        self,
        cache_dir: Path,
        client: httpx.Client | None = None,
        max_retries: int = 3,
        backoff_s: float = 1.0,
        rate_limit_s: float = 0.5,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
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
        self.clock = clock
        self.sleep = sleep
        self.rng = rng or random.Random()

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
        atomic_write_text(path, json.dumps(data))
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
            detail(f"scrape: {len(out):,}/{data.get('total', 0):,} docs")
            cursor = data.get("cursor")
            if not cursor:
                return out

    def metadata(self, identifier: str) -> dict:
        def fetch() -> dict:
            return self._get(METADATA_URL.format(identifier=identifier)).json()

        return self._cached(f"md_{identifier}", fetch)

    def _download_candidates(self, identifier: str, filename: str) -> tuple[list[str], int | None]:
        """Candidate URLs for one file, in order, and its metadata `size` (None when
        absent or non-numeric). The redirect URL first, then each listed server; with
        unusable metadata, the redirect URL alone."""
        quoted = quote(filename)  # keeps "/" as a path separator
        urls = [DOWNLOAD_URL.format(identifier=identifier, filename=quoted)]
        try:
            md = self.metadata(identifier)
        except (IAError, ValueError):
            return urls, None
        if not isinstance(md, dict):
            return urls, None

        size: int | None = None
        files = md.get("files")
        for entry in files if isinstance(files, list) else []:
            if isinstance(entry, dict) and entry.get("name") == filename:
                try:
                    size = int(entry.get("size"))
                except (TypeError, ValueError):
                    size = None
                break

        workable = md.get("workable_servers")
        # A d1/d2 absent from a non-empty workable_servers is one archive.org has
        # marked not workable, so d1/d2 are a fallback for a missing or empty list only.
        servers = workable if isinstance(workable, list) and workable else [md.get("d1"), md.get("d2")]
        item_dir = md.get("dir")
        if isinstance(item_dir, str) and item_dir:
            for server in servers:
                if isinstance(server, str) and server:
                    url = f"https://{server}{item_dir}/{quoted}"
                    if url not in urls:
                        urls.append(url)
        return urls, size

    def _pause(self) -> None:
        self.sleep(self.rng.uniform(DOWNLOAD_SLEEP_MIN_S, DOWNLOAD_SLEEP_MAX_S))

    def _attempt(self, url: str, tmp: Path, *, md5: str | None, size: int | None) -> _Attempt:
        """One GET of `url` into `tmp`, then the integrity check. A failed attempt
        leaves no `.part`; a successful one leaves the verified `.part` for the caller
        to rename into place."""
        self._throttle()
        try:
            with self.client.stream("GET", url, timeout=_DOWNLOAD_TIMEOUT) as resp:
                status = resp.status_code
                if not 200 <= status < 300:
                    tmp.unlink(missing_ok=True)
                    retryable = status >= 500 or status in _RETRYABLE_STATUS
                    return _Attempt(False, f"HTTP {status}", retryable=retryable)
                with tmp.open("wb") as f:
                    for chunk in resp.iter_bytes():
                        f.write(chunk)
        except httpx.HTTPError as e:
            # Transport errors (connect/stall timeouts, resets, a body dying
            # mid-transfer) and every other httpx error (TooManyRedirects,
            # DecodingError) fail this attempt only, retryably.
            tmp.unlink(missing_ok=True)
            return _Attempt(False, _http_error_text(e), retryable=True)

        # Verify the file on disk, whole: a bad copy is not asked again.
        if md5:
            got = _file_md5(tmp)
            if got != md5:
                tmp.unlink()
                return _Attempt(False, f"md5 mismatch (got {got}, expected {md5})")
        elif size is not None:
            got_size = tmp.stat().st_size
            if got_size != size:
                tmp.unlink()
                return _Attempt(False, f"size mismatch (got {got_size} bytes, expected {size})")
        return _Attempt(True)

    def download_file(self, identifier: str, filename: str, dest: Path, md5: str | None = None) -> Path:
        """Fetch `filename` into `dest`, verified, trying the item's listed servers
        when the redirect URL fails (spec 2026-10-21 §1).

        First pass: one attempt per candidate, in order, never cut short. Then
        repeat attempts cycle the candidates whose last error was retryable until
        DOWNLOAD_DEADLINE_S has passed since the first pass ended (checked before
        each attempt). A short random sleep separates attempts; Retry-After is
        ignored, since switching servers is the response to a struggling one."""
        candidates, size = self._download_candidates(identifier, filename)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        last_error: dict[str, str] = {}
        retryable: dict[str, bool] = {}
        attempts = 0

        def attempt(url: str) -> _Attempt:
            nonlocal attempts
            attempts += 1
            outcome = self._attempt(url, tmp, md5=md5, size=size)
            if not outcome.ok:
                last_error[url] = outcome.error
                retryable[url] = outcome.retryable
            return outcome

        try:
            for i, url in enumerate(candidates):
                if i:
                    self._pause()
                if attempt(url).ok:
                    tmp.replace(dest)
                    return dest

            first_pass_end = self.clock()
            slot_wait = 0.0

            def expired() -> bool:
                return self.clock() - first_pass_end - slot_wait >= DOWNLOAD_DEADLINE_S

            ring = itertools.cycle(candidates)
            while any(retryable.values()) and not expired():
                self._pause()
                if expired():
                    break
                url = next(u for u in ring if retryable[u])
                outcome = attempt(url)
                slot_wait += outcome.slot_wait_s
                if outcome.ok:
                    tmp.replace(dest)
                    return dest
        finally:
            tmp.unlink(missing_ok=True)  # gone after a rename; any other exit leaves no .part

        tried = "; ".join(f"{url} -> {last_error[url]}" for url in candidates)
        raise IADownloadError(f"download of {filename} failed: {tried} ({attempts} attempts)")
