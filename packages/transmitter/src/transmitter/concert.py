"""Concert announcements: the finite inventory of phrase texts the transmitter
derives (and emcee voices later). Pure: no IO."""

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from transmitter.clock import ClockConfig, occurrences

if TYPE_CHECKING:
    from transmitter.pieces import Piece

Named = tuple[str, tuple[str, str]]  # (slug, occurrence key)
EASTERN = "America/New_York"
ASSEMBLED_TYPICAL_SECONDS = 18.0
PIECE_KINDS = ("id", "next", "next_end", "continues", "continues_end", "then",
               "with_comma", "with_period", "followed", "time")

_DAY_US = 86_400_000_000


def piece_id(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def clean(value: object) -> str | None:
    """An artist (or any name) as one clean line; None when empty or not a string."""
    if not isinstance(value, str):
        return None
    out = " ".join(value.split())
    return out or None


def title_of(block: object) -> str | None:
    """A block's spoken title: its `title` through `clean`; None means untitled.
    The inventory and the scheduler both use this, so the scheduler asks for
    exactly the block pieces the inventory lists."""
    return clean(getattr(block, "title", None))


def hour_word(h24: int) -> str:
    if h24 % 24 == 0:
        return "midnight"
    if h24 % 24 == 12:
        return "noon"
    return str(h24 % 12)


def _eastern(us: int) -> datetime:
    return datetime.fromtimestamp(us // 1_000_000, tz=timezone.utc).astimezone(ZoneInfo(EASTERN))


def time_phrase(us: int) -> str:
    local = _eastern(us)
    h, m = local.hour, local.minute
    nxt = (h + 1) % 24
    if m <= 2:
        words = f"at {hour_word(h)}"
    elif m <= 10:
        words = f"just after {hour_word(h)}"
    elif m <= 19:
        words = f"around quarter past {hour_word(h)}"
    elif m <= 40:
        words = f"around half past {hour_word(h)}"
    elif m <= 49:
        words = f"around quarter to {hour_word(nxt)}"
    elif m <= 57:
        words = f"a few minutes before {hour_word(nxt)}"
    else:
        words = f"at {hour_word(nxt)}"
    return f"{words} Eastern."


def then_time(us: int) -> str:
    local = _eastern(us)
    if local.minute == 0:
        return hour_word(local.hour)
    return f"{local.hour % 12 or 12}:{local.minute:02d}"


def next_text(title: str) -> str:
    return f"Coming up next, {title}"


def next_end_text(title: str) -> str:
    return f"Coming up next, {title}."


def continues_text(title: str) -> str:
    return f"{title} continues"


def continues_end_text(title: str) -> str:
    return f"{title} continues."


def then_text(title: str, nominal_us: int) -> str:
    return f"Then, at {then_time(nominal_us)} Eastern, {title}"


def with_comma(artist: str) -> str:
    return f"with {artist},"


def with_period(artist: str) -> str:
    return f"with {artist}" if artist.endswith(".") else f"with {artist}."


def followed_by(artist: str) -> str:
    return f"followed by {artist},"


_FORMS = ("at", "just after", "around quarter past", "around half past",
          "around quarter to", "a few minutes before")
_HOUR_WORDS = ("midnight", "noon", *(str(n) for n in range(1, 12)))
ALL_TIME_PHRASES: tuple[str, ...] = tuple(
    f"{form} {word} Eastern." for form in _FORMS for word in _HOUR_WORDS)


@dataclass(frozen=True)
class NeededPiece:
    id: str
    text: str
    kind: str


def needed_pieces(clock: ClockConfig, artists: Iterable[object], id_text: str,
                  from_us: int, days: float = 8.0) -> list[NeededPiece]:
    """Every piece text the feature may need, deduped by id, sorted by id."""
    found: dict[str, NeededPiece] = {}

    def add(text: str, kind: str) -> None:
        pid = piece_id(text)
        found.setdefault(pid, NeededPiece(pid, text, kind))

    add(id_text, "id")
    for block in clock.block:
        title = title_of(block)
        if title:
            add(next_text(title), "next")
            add(next_end_text(title), "next_end")
            add(continues_text(title), "continues")
            add(continues_end_text(title), "continues_end")
    until = from_us + round(days * _DAY_US)
    for occ in occurrences(clock, from_us, until):
        title = title_of(occ.block)
        if title:
            add(then_text(title, occ.nominal_us), "then")
    for artist in dict.fromkeys(a for a in map(clean, artists) if a):
        add(with_comma(artist), "with_comma")
        add(with_period(artist), "with_period")
        add(followed_by(artist), "followed")
    for text in ALL_TIME_PHRASES:
        add(text, "time")
    return sorted(found.values(), key=lambda p: p.id)


PHRASES = ("id", "next", "x", "followed", "then")


@dataclass(frozen=True)
class ConcertInput:
    """What the scheduler needs to propose concert breaks (`SchedulerInput.concert`).

    `present`: the piece ids whose MP3 is usable. `typical_frames`: the assumed
    assembled-clip length (pass 1, the boundary estimate, Y's predicted start).
    `first_break`: pass 2's assembled clip, used for the break at `start_frame`
    only. `no_assembly_at`: start frames planned at the last rung (today's logic)."""
    present: frozenset[str]
    id_text: str
    typical_frames: int
    first_break: "Piece | None" = None
    no_assembly_at: frozenset[int] = frozenset()


@dataclass(frozen=True)
class BreakContent:
    """One proposed concert break: the pieces in play order, the shows it names
    (X[, Y][, Z] with their occurrences), the occurrence announced with a time
    (Z's, when Then is spoken) and the phrases spoken (an ordered subset of
    `PHRASES`). `y_time_id` is the id of Y's time-phrase piece (Followed only)."""
    pieces: tuple[tuple[str, str], ...]
    entries: tuple[Named, ...]
    names: tuple[tuple[str, str], ...]
    phrases: tuple[str, ...]
    y_time_id: str | None

    @property
    def named(self) -> tuple[str, ...]:
        return tuple(slug for slug, _ in self.entries)

    def same_shape(self, other: "BreakContent") -> bool:
        """Same shows, same timed occurrence, same phrases: a different Y bucket
        alone (times are loose) does not count as a difference."""
        return (self.entries, self.names, self.phrases) == (other.entries, other.names, other.phrases)
