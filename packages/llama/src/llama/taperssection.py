"""Taper's Section allowlist: model wrapper, synthetic collection key, exact matching.

Imports the entry models from `config`; `config` never imports this module.
"""
import hashlib
import json
import re
import unicodedata

from llama.config import TaperssectionArtist, TaperssectionConfig
from llama.errors import LlamaError
from llama.util import slugify

KEY_PREFIX = "ts-"


def norm_creator(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return re.sub(r"^the ", "", s).strip()


def artist_key(name: str) -> str:
    return KEY_PREFIX + slugify(name)


def display_label(allowlist: "Allowlist | None", key: str) -> str:
    """The human-facing label for a collection/artist key: a resolvable `ts-` key
    shows its entry's name; anything else (an LMA collection, an unknown or
    unloadable ts key) shows as-is. Display only: never raises, never gates."""
    if not is_synthetic(key) or not allowlist:
        return key
    entry = allowlist.by_key(key)
    return entry.name if entry is not None else key


def is_synthetic(key: str) -> bool:
    return key.startswith(KEY_PREFIX)


class Allowlist:
    def __init__(self, entries: list[TaperssectionArtist]):
        self.entries = list(entries)

    @classmethod
    def empty(cls) -> "Allowlist":
        return cls([])

    @classmethod
    def from_config(cls, cfg: TaperssectionConfig) -> "Allowlist":
        keys: dict[str, str] = {}
        creators: dict[str, str] = {}
        for e in cfg.artists:
            k = artist_key(e.name)
            if k in keys:
                raise LlamaError(
                    f"taperssection artists {keys[k]!r} and {e.name!r} both give key {k!r}; "
                    "rename one in [[taperssection.artists]]"
                )
            keys[k] = e.name
            for c in {norm_creator(n) for n in (e.name, *e.creators)}:
                if c in creators and creators[c] != e.name:
                    raise LlamaError(
                        f"taperssection spelling {c!r} appears in both {creators[c]!r} "
                        f"and {e.name!r}; a name or creator may belong to one entry"
                    )
                creators[c] = e.name
        return cls(list(cfg.artists))

    @staticmethod
    def for_candidate(allowlist: "Allowlist | None", collection: str) -> TaperssectionArtist | None:
        if not is_synthetic(collection):
            return None
        if not allowlist:
            raise LlamaError(
                f"taperssection key {collection!r} needs an allowlist but "
                "[[taperssection.artists]] is empty or not loaded"
            )
        return allowlist.require(collection)

    def __bool__(self) -> bool:
        return bool(self.entries)

    def key(self, entry: TaperssectionArtist) -> str:
        return artist_key(entry.name)

    def by_key(self, key: str) -> TaperssectionArtist | None:
        for e in self.entries:
            if self.key(e) == key:
                return e
        return None

    def require(self, key: str) -> TaperssectionArtist:
        e = self.by_key(key)
        if e is None:
            raise LlamaError(
                f"unknown taperssection artist key {key!r}; "
                "is it still in [[taperssection.artists]]?"
            )
        return e

    def matching_names(self, entry: TaperssectionArtist) -> tuple[str, ...]:
        return (entry.name, *entry.creators)

    def match_creator(self, creator: str | list | None, entry: TaperssectionArtist) -> bool:
        if creator is None:
            return False
        vals = creator if isinstance(creator, list) else [creator]
        mine = {norm_creator(n) for n in entry.creators}
        return any(isinstance(v, str) and norm_creator(v) in mine for v in vals)

    def resolve_name(self, name: str | None) -> TaperssectionArtist | None:
        if not name:
            return None
        guess = norm_creator(name)
        if not guess:
            return None
        for e in self.entries:
            for n in self.matching_names(e):
                spelled = norm_creator(n)
                if guess == spelled or guess == spelled.replace(" ", ""):
                    return e
        return None

    def fingerprint(self) -> str | None:
        if not self.entries:
            return None
        payload = []
        for e in sorted(self.entries, key=self.key):
            d = e.model_dump(exclude={"note"})
            for f in ("creators", "lineages", "exclude"):
                d[f] = sorted(d[f])
            payload.append(d)
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()
