"""Offline replay of gather/vet over the on-disk cache: no network, no LLM.

Slice 0 of the held-backlog Tier 1 work. This module holds the cache-only
clients and the input/config/code identities the harness stamps on each arm.
"""
import hashlib
import json
import os
import subprocess
from pathlib import Path

import llama
from llama.config import Config
from llama.errors import LlamaError
from llama.models import VettingResult
from llama.setlistfm import _pick, cache_key
from llama.workspace import ShowWorkspace, read_model

_REFUSED = "network refused by the cache-only client"


class CacheMiss(LlamaError):
    pass


class CacheOnlyIA:
    """An archive.org client that only ever reads `md_<id>.json` from the cache."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.misses: list[str] = []

    def metadata(self, identifier: str) -> dict:
        path = self.cache_dir / f"md_{identifier}.json"
        if not path.exists():
            self.misses.append(identifier)
            raise CacheMiss(f"cache miss: md_{identifier}.json")
        return json.loads(path.read_text())

    def search(self, *args, **kwargs):
        raise CacheMiss(_REFUSED)

    def scrape(self, *args, **kwargs):
        raise CacheMiss(_REFUSED)

    def download_file(self, *args, **kwargs):
        raise CacheMiss(_REFUSED)


class CacheOnlySetlistFM:
    """A setlist.fm client that only reads the client's own cache files."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.misses: list[tuple[str, str]] = []

    def setlist(self, artist: str, date: str,
                venue: str | None = None, city: str | None = None) -> dict | None:
        path = self.cache_dir / (cache_key(artist, date) + ".json")
        if not path.exists():
            self.misses.append((artist, date))
            return None
        data = json.loads(path.read_text())
        return _pick(data.get("setlist", []), venue, city)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def input_digests(ws: ShowWorkspace) -> dict[str, str | None]:
    """sha256 of each file the replay reads; None when absent.

    `vetting.extraction` hashes only the extraction, never the flags (which
    are derived by the arm under test).
    """
    def of(path: Path) -> str | None:
        return _sha256(path.read_bytes()) if path.exists() else None

    extraction = None
    if ws.vetting.exists():
        result = read_model(ws.vetting, VettingResult)
        extraction = _sha256(result.vetting.model_dump_json().encode())
    return {
        "show.json": of(ws.show),
        "overrides.json": of(ws.overrides),
        "provenance.json": of(ws.provenance),
        "research.md": of(ws.research),
        "vetting.extraction": extraction,
    }


def setlistfm_configured(config: Config) -> bool:
    return bool(os.environ.get("SETLISTFM_API_KEY") or config.setlistfm.api_key)


def setlistfm_client(config: Config) -> CacheOnlySetlistFM | None:
    """The one place the replay's setlist.fm client is chosen."""
    if setlistfm_configured(config):
        return CacheOnlySetlistFM(config.root / "cache")
    return None


def config_fingerprint(config: Config) -> str:
    payload = {
        "audio_format": config.audio_format,
        "structure": config.structure.model_dump(),
        "jerrybase": config.jerrybase.model_dump(),
        "setlistfm_configured": setlistfm_configured(config),
    }
    return _sha256(json.dumps(payload, sort_keys=True).encode())


def code_identity() -> str:
    """The git HEAD of the running llama (`-dirty` if uncommitted), else its version."""
    here = str(Path(llama.__file__).resolve().parent)
    try:
        sha = subprocess.run(["git", "-C", here, "rev-parse", "HEAD"], capture_output=True,
                             text=True, check=True).stdout.strip()
        status = subprocess.run(["git", "-C", here, "status", "--porcelain"], capture_output=True,
                                text=True, check=True).stdout.strip()
        if sha:
            return sha + ("-dirty" if status else "")
    except (OSError, subprocess.CalledProcessError):
        pass
    return f"version:{llama.__version__}"
