"""The three positional overrides, keyed by filename (piece 4 spec 4.1).

`overrides.json`'s `titles`, `set_breaks` and `encore_after` name FILES, not track
numbers: an inserted track (the short-keep rule) would otherwise re-point every key
after it silently. The key names stay; the values are filenames:

    titles        {"<filename>": "<title>"}   forced title per file
    set_breaks    ["<filename>", ...]         a break falls after each listed file
    encore_after  "<filename>"                encore starts after this file

A **legacy** value is the track-number form: any titles key, set_breaks item or
encore_after that v2.17.0's model (`dict[int, str]`, `list[int]`, `int`) accepts as an
int. The test is that model's own rule, pydantic's lax JSON-mode `int`, not Python's
`int()`: `"7"`, `" 7"`, `"7.0"`, `"07"`, `"+7"`, `"7_0"` (70), `true`, `7` and `2.0`
are all legacy. Every real filename has an extension, so none is. The migration
(`scripts/rekey_overrides.py`) and this resolver use the same test.

The model parses every form (`models.Overrides`); only `resolve_positions` (gather's
one reader) and the writers (`cli._edit_overrides`) judge legacy or mixed values.
Nothing here does IO.
"""
from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic import TypeAdapter, ValidationError

from llama.errors import LlamaError

if TYPE_CHECKING:
    from llama.models import Overrides

POSITIONAL_KEYS = ("titles", "set_breaks", "encore_after")

_INT = TypeAdapter(int)


def legacy_int(v: object) -> int | None:
    """The track number v2.17.0's model reads `v` as, else None. Lax, JSON mode, as
    `read_model` reads: the value is re-serialised and parsed as an int. A titles key
    is judged as the JSON string it is."""
    try:
        return _INT.validate_json(json.dumps(v))
    except (ValidationError, TypeError, ValueError):
        return None


def _entries(data: Mapping[str, object]) -> list[tuple[str, object]]:
    """(key, value) for every positional value, in order: titles keys, set_breaks
    items, encore_after. `set_breaks: []`/None and a missing or None encore add
    nothing."""
    out: list[tuple[str, object]] = []
    titles = data.get("titles")
    if isinstance(titles, Mapping):
        out += [("titles", k) for k in titles]
    breaks = data.get("set_breaks")
    if isinstance(breaks, list):
        out += [("set_breaks", v) for v in breaks]
    encore = data.get("encore_after")
    if encore is not None:
        out.append(("encore_after", encore))
    return out


def classify(data: Mapping[str, object]) -> str:
    """`"none"` (no positional value), `"legacy"` (every one a track number),
    `"filename"` (none a track number) or `"mixed"`. Takes `json.loads` output or
    `Overrides.model_dump()`."""
    kinds = {legacy_int(v) is not None for _, v in _entries(data)}
    if not kinds:
        return "none"
    if kinds == {True}:
        return "legacy"
    if kinds == {False}:
        return "filename"
    return "mixed"


def filename_values(data: Mapping[str, object]) -> list[tuple[str, str]]:
    """(key, filename) for every positional value that is not a track number, in
    `_entries` order."""
    return [(k, str(v)) for k, v in _entries(data) if legacy_int(v) is None]


def rekey_raw(raw: dict, filenames: Sequence[str]) -> dict:
    """The migration's mapping: a copy of `raw` with each legacy value N replaced by
    `filenames[N - 1]`. Only the three positional keys change; key order (top level
    and within `titles`) and every other key are kept, and a filename value already
    present is left as it is. Raises IndexError on an N outside 1..len(filenames)
    (callers check first)."""
    def name(v: object) -> object:
        n = legacy_int(v)
        if n is None:
            return v
        if not 1 <= n <= len(filenames):
            raise IndexError(f"track {n} outside 1..{len(filenames)}")
        return filenames[n - 1]

    out = copy.deepcopy(raw)
    if isinstance(out.get("titles"), dict):
        out["titles"] = {name(k): t for k, t in out["titles"].items()}
    if isinstance(out.get("set_breaks"), list):
        out["set_breaks"] = [name(v) for v in out["set_breaks"]]
    if out.get("encore_after") is not None:
        out["encore_after"] = name(out["encore_after"])
    return out


def legacy_message(slug: str) -> str:
    return f"{slug}: overrides.json uses track-number keys; run the migration"


def mixed_message(slug: str, data: Mapping[str, object]) -> str:
    named = ", ".join(f"{k} {f}" for k, f in filename_values(data))
    return (f"{slug}: overrides.json mixes track-number and filename keys "
            f"(filename-valued: {named}); undo the hand edit")


def dangling_message(slug: str, dangling: Sequence[tuple[str, str]]) -> str:
    named = ", ".join(f"{k} {f}" for k, f in dangling)
    return (f"{slug}: overrides name files not in the track list: {named}; clear them "
            f"with llama fix {slug} --clear-title <file> / --clear-set-breaks / "
            f"--clear-encore")


def refusal(slug: str, data: Mapping[str, object]) -> str | None:
    """The writers' and the resolver's form check: the mixed message, the legacy
    message, or None. Mixed first: a mixed file holds a legacy value too, and the
    migration cannot repair it (spec 4.1)."""
    kind = classify(data)
    if kind == "mixed":
        return mixed_message(slug, data)
    if kind == "legacy":
        return legacy_message(slug)
    return None


@dataclass(frozen=True)
class Positions:
    """The positional values the cascade and the structure override consume,
    1-based over gather's final kept list. `set_breaks` None is no structure
    override; `[]` is forced no breaks."""
    titles: dict[int, str] = field(default_factory=dict)
    set_breaks: list[int] | None = None
    encore_after: int | None = None


def resolve_positions(ov: Overrides, kept_names: Sequence[str], *, slug: str) -> Positions:
    """Map `ov`'s filename values onto `kept_names` (gather's final kept list, in play
    order) once. Raises LlamaError naming `slug`: a mixed file (first), a legacy file,
    then every filename value whose file is not in the list, in one message."""
    data = ov.model_dump()
    why = refusal(slug, data)
    if why is not None:
        raise LlamaError(why)
    index: dict[str, int] = {}
    for i, n in enumerate(kept_names):
        index.setdefault(n, i + 1)
    dangling = list(dict.fromkeys((k, f) for k, f in filename_values(data) if f not in index))
    if dangling:
        raise LlamaError(dangling_message(slug, dangling))
    return Positions(
        titles={index[str(k)]: t for k, t in ov.titles.items()},
        set_breaks=(None if ov.set_breaks is None
                    else [index[str(v)] for v in ov.set_breaks]),
        encore_after=None if ov.encore_after is None else index[str(ov.encore_after)])
