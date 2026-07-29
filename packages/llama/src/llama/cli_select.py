"""Shared, Typer-free selector layer over the catalog.

Plan A (foundations): the one selector implementation Plan B will wire into
every selector-capable command (`status`, `show`, `deliver`, `redo`, ...).
Pure functions over `CatalogEntry` objects — no Typer imports here; Plan B
owns translating CLI options into a `Selector` via `build_selector`. Nothing
in the existing CLI uses this module yet.
"""
from dataclasses import dataclass
from enum import Enum

from llama.catalog import CatalogEntry, select_shows
from llama.errors import LlamaError


class ShowState(str, Enum):
    """Derived-state names, matching `catalog.derive_state` verbatim."""

    held = "held"
    selected = "selected"
    gathered = "gathered"
    researched = "researched"
    vetted = "vetted"
    briefed = "briefed"
    scripted = "scripted"
    packaged = "packaged"
    delivered = "delivered"


@dataclass(frozen=True)
class Selector:
    """Pure data: the reconciled result of a command's selector options."""

    states: frozenset[str]        # empty = no state filter
    voiced: bool | None           # True/False/None (reconciled once here)
    artist: str | None
    run: str | None
    broadcast_ready: bool


def build_selector(*, held: bool = False, packaged: bool = False,
                   states=(), voiced: bool = False, unvoiced: bool = False,
                   artist: str | None = None, run: str | None = None,
                   broadcast_ready: bool = False) -> Selector:
    """Reconcile a command's raw selector options into a `Selector`.

    `--held`/`--packaged` are sugar: they add "held"/"packaged" to the
    states set. `states` is the repeatable `--state` values (`ShowState`
    members or plain strings). `voiced`/`unvoiced` reconcile to the single
    tri-state field; passing both raises `LlamaError` instead of silently
    picking one.
    """
    if voiced and unvoiced:
        raise LlamaError("give --voiced or --unvoiced, not both")
    state_set = {s.value if isinstance(s, ShowState) else str(s) for s in states}
    if held:
        state_set.add(ShowState.held.value)
    if packaged:
        state_set.add(ShowState.packaged.value)
    vf = True if voiced else (False if unvoiced else None)
    return Selector(states=frozenset(state_set), voiced=vf, artist=artist,
                    run=run, broadcast_ready=broadcast_ready)


def selector_active(sel: Selector) -> bool:
    """True iff any filter is set at all."""
    return bool(sel.states) or sel.voiced is not None or bool(sel.artist) \
        or bool(sel.run) or sel.broadcast_ready


def apply_selector(entries: list[CatalogEntry], sel: Selector) -> list[CatalogEntry]:
    """Thin wrapper over `catalog.select_shows` — no filtering logic here."""
    return select_shows(entries, states=sel.states or None, voiced=sel.voiced,
                        artist=sel.artist, run=sel.run,
                        broadcast_ready=sel.broadcast_ready)


HELD_NOTE = "note: {n} held show(s) excluded (add --held to include them)"


def split_held(entries: list[CatalogEntry],
               sel: Selector) -> tuple[list[CatalogEntry], list[CatalogEntry]]:
    """Partition off held entries unless the selector explicitly asked for
    them. ACTING commands only (spec §2 held opt-in) — the caller prints
    `HELD_NOTE` for the dropped list. When "held" IS in `sel.states`,
    nothing is dropped (both lists come back whole / empty)."""
    if ShowState.held.value in sel.states:
        return list(entries), []
    kept = [e for e in entries if e.state != ShowState.held.value]
    dropped = [e for e in entries if e.state == ShowState.held.value]
    return kept, dropped
