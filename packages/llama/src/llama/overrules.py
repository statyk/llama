"""Persisted overrules: flag kind + subject keys (bulk-apply spec "Overrules persist").

A flag that matches a recorded overrule becomes an operator note, not a hold.
Matching is by kind and subject, never by track number or count. Pure: no stage
and no `llama.replay` import (gather imports this module)."""
from __future__ import annotations

import re
from typing import NamedTuple, Sequence

from llama.models import Overrule, Show
from llama.structure import fold_curly_apostrophes

NOTE_PREFIX = "overruled: "


class FlagKey(NamedTuple):
    kind: str
    subject: tuple[str, ...] | None


def _norm(s: str) -> str:
    return " ".join(fold_curly_apostrophes(s).casefold().split())


_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # (regex, kind, subject mode): "norm" = normalised groups, "raw" = groups as written,
    # "none" = null subject
    (re.compile(r"^research asserts unknown song: (.*)$", re.S), "research-song", "norm"),
    (re.compile(r"^research asserts wrong date: (.*)$", re.S), "research-date", "raw"),
    (re.compile(r"^research asserts (.*?); item date .* looks like a year-only placeholder$",
                re.S), "research-date", "raw"),
    (re.compile(r"^research asserts .* sets but structure has "), "research-sets", "none"),
    (re.compile(r"^low-confidence structure alignment"), "alignment", "none"),
    (re.compile(r"^single-set structure for a long show"), "single-set", "none"),
    (re.compile(r"^setlist evidence shows multiple sets"), "sets-not-found", "none"),
    (re.compile(r"^structure has \d+ sets but jerrybase shows \d+"),
     "jerrybase-set-count", "none"),
    (re.compile(r"^jerrybase set closer '(.*)' is not at a set break", re.S),
     "jerrybase-closer", "norm"),
    (re.compile(r"^low-confidence setlist"), "low-confidence-setlist", "none"),
    (re.compile(r"^merged track(?:\(s\)|s)? .*span a set break"), "merged-tracks", "none"),
    (re.compile(r"^venue mismatch: archive '(.*)' vs jerrybase '(.*)'", re.S), "venue", "norm"),
    (re.compile(r"^recordings of this date disagree on city: '(.*)' \(selected\) vs '(.*)'",
                re.S), "city", "norm"),
    (re.compile(r"^tape spans"), "tape-spans", "none"),
    (re.compile(r"^unassigned multi-event recordings"), "events-unassigned", "none"),
    (re.compile(r"^multi-event date"), "multi-event", "none"),
    (re.compile(r"^no playable tracks"), "no-tracks", "none"),
    (re.compile(r"^briefing mentions unknown song: (.*)$", re.S), "briefing-song", "norm"),
    (re.compile(r"^briefing references nonexistent set: (.*)$", re.S), "briefing-set", "norm"),
]


def flag_key(flag: str, show: Show) -> FlagKey | None:
    """The (kind, subject) of a review flag; None when the flag is a package-family
    flag that cannot be overruled (`duration mismatch on ...`)."""
    if flag.startswith("duration mismatch on "):
        return None
    if flag.startswith("unresolved track titles"):
        names = sorted(t.filename for t in show.tracks if t.title_source == "unresolved")
        return FlagKey("titles", tuple(names))
    for rx, kind, mode in _PATTERNS:
        m = rx.match(flag)
        if not m:
            continue
        if mode == "none":
            return FlagKey(kind, None)
        if mode == "raw":
            return FlagKey(kind, tuple(g.strip() for g in m.groups()))
        return FlagKey(kind, tuple(_norm(g) for g in m.groups()))
    if flag.startswith("briefing"):
        return FlagKey("briefing-other", (re.sub(r"\d+", "N", _norm(flag)),))
    return FlagKey("other", (_norm(flag),))


def rule_matches(rule: Overrule, key: FlagKey, identifier: str) -> bool:
    if rule.identifier != identifier or rule.kind != key.kind:
        return False
    if key.kind == "titles":
        return set(key.subject or ()) <= set(rule.subject or ())
    if rule.subject is None or key.subject is None:
        return rule.subject is None and key.subject is None
    return tuple(rule.subject) == key.subject


def split_overruled(flags: list[str], rules: Sequence[Overrule],
                    show: Show) -> tuple[list[str], list[str]]:
    """(flags still holding, `overruled: <flag>` notes), flag order preserved."""
    held: list[str] = []
    notes: list[str] = []
    for f in flags:
        key = flag_key(f, show)
        if key is not None and any(rule_matches(r, key, show.identifier) for r in rules):
            notes.append(NOTE_PREFIX + f)
        else:
            held.append(f)
    return held, notes


def records_for(flags: list[str], show: Show, *, source: str, at: str) -> list[Overrule]:
    """One record per overrulable flag, scoped to the show's recording."""
    out: list[Overrule] = []
    for f in flags:
        key = flag_key(f, show)
        if key is None:
            continue
        out.append(Overrule(identifier=show.identifier, kind=key.kind,
                            subject=None if key.subject is None else list(key.subject),
                            flag=f, source=source, at=at))
    return out


def _ident(r: Overrule) -> tuple:
    return (r.identifier, r.kind, None if r.subject is None else tuple(r.subject))


def merge_rules(existing: Sequence[Overrule], new: Sequence[Overrule]) -> list[Overrule]:
    """Existing rules, then each new one not already present (same identifier, kind, subject)."""
    out = list(existing)
    seen = {_ident(r) for r in out}
    for r in new:
        if _ident(r) not in seen:
            seen.add(_ident(r))
            out.append(r)
    return out
