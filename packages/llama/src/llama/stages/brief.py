import re
import string

from herder import run_json_task
from llama.models import Briefing, Show, VettingResult
from llama.prompts import load_prompt
from llama.songs import normalize_song
from llama.util import reviews_digest
from llama.workspace import (ShowWorkspace, read_model, read_overrides,
                             should_run, write_artifact)

_VAGUE_NOTE = (
    "IMPORTANT — uncertain setlist: this show's song list is incomplete and the "
    "available sources conflict. Do NOT name specific songs, do NOT assert a set "
    "count or set structure, and state nothing as fact that the show data does "
    "not confirm. Speak to the band, the era, the venue, the performance, and its "
    "reputation instead. Leave mentioned_songs empty."
)


def narration_note(narration: str) -> str:
    # Trailing blank line so the prompt's `{{narration_note}}Show data` slot
    # reads cleanly when set; empty string leaves the full-path prompt
    # byte-identical to the pre-narration template (one blank line before
    # "Show data"), rather than injecting an extra blank line.
    return _VAGUE_NOTE + "\n\n" if narration == "vague" else ""


# Set-count claims in briefing prose. "sets of ..." ("two sets of fiddle tunes")
# is a quantity of songs, not a set count, so it never counts as a claim. The
# lookahead stops at the field boundary (a newline), like _SCOPE_AFTER (final
# review I1 follow-up): a claim ending one field is not excused by "Of ..." opening the next.
_SET_COUNT_CLAIM = re.compile(
    r"\b(both|two|three|four|[234])\s+(?:\w+\s+)?sets\b(?![^\S\n]+of\b)", re.I
)
_ORDINAL_SET = re.compile(r"\b(second|third|fourth)\s+set\b", re.I)
_COUNT_WORDS = {"both": 2, "two": 2, "three": 3, "four": 4, "2": 2, "3": 3, "4": 4}
_ORDINALS = {"second": 2, "third": 3, "fourth": 4}

# --- slice 3 (spec "Slice 3 — Briefing guard"; constants per "New constants",
# fixed a priori, do not retune after the harness runs) ---

# 3c: today's count pattern with its single optional intervening word captured
# as group 2. The word stays `\w+`, never `[\w-]+`: widening it would make "two
# hard-hitting sets" a new claim. _SET_COUNT_CLAIM above is the
# vague branch's; both lookaheads stop at the field boundary (final review I1 follow-up).
_SET_COUNT_CLAIM_3C = re.compile(
    r"\b(both|two|three|four|[234])\s+(?:(\w+)\s+)?sets\b(?![^\S\n]+of\b)", re.I
)
# 3c qualifier denylist: an intervening word that makes the count not show-wide
# ("two electric sets"). `late-night` is unreachable under `\w+` (the hyphen
# ends the word) and is kept only because the spec lists it.
_NOT_SHOW_WIDE = frozenset({"electric", "acoustic", "night", "late-night", "afternoon",
                            "weekend", "more", "festival", "day"})
# 3c negation: one of these in the two words before a match ...
_NEGATION_2 = frozenset({"no", "not", "never"})
# ... or one of these within the four words before it (`instead of` as a bigram).
_NEGATION_4 = ("instead of", "expected", "without")
# 3c scope: a phrase after the match that scopes it below the show ("two sets
# a night"). `that`/`this` are deliberately absent: "two sets that night" is a
# claim about this show. The leading space stops at a newline: that is the
# briefing-field boundary (final review I1).
_SCOPE_AFTER = re.compile(r"^[^\S\n]*(?:each|every|a|per)\s+(?:night|day|weekend|tour)\b", re.I)
# 3c negation windows look back only within the match's own clause (Task 14
# fix round 1): a negation word in an earlier sentence, clause or briefing
# field qualifies nothing ("The band did not disappoint. Second set opened
# hot." is a claim). Clipping only ever removes suppressions. The comma is a
# break too: "As expected, the second set was a monster." is a claim.
# `\n` is _guard_prose's field boundary.
_CLAUSE_BREAK = re.compile(r"[.!?;:,\n]")

# 3b: deterministic strips for tolerant song matching. Brief-local on purpose:
# structure._STRUCTURE_PREFIX does not match `E1:` and feeds align(), anchoring
# and jerrybase closer matching, so it is not touched.
_BRIEF_STRUCTURE_PREFIX = re.compile(r"^\s*(?:e\d*|encore)\s*:\s*", re.I)
_BRIEF_TRAILING = re.compile(r"[\s>\-*%#@^~+]+$")
_BRIEF_PAREN = re.compile(r"\s*\([^)]*\)\s*$")
_BRIEF_SEGUE = re.compile(r"\s*(?:->|>|→)\s*")


def _set_label(s: str) -> str:
    return "Encore" if s == "encore" else f"Set {s}"


def render_briefing_md(briefing: Briefing, show: Show) -> str:
    """Deterministic markdown render of the briefing model: briefing.md is a
    pure function of briefing.json, so the two artifacts can never disagree."""
    lines = [f"# Briefing: {show.artist} — {show.date}, {show.venue or 'venue unknown'}", ""]
    lines += ["## Context", briefing.context, ""]
    lines += ["## Why this show", briefing.significance, ""]
    for s in sorted(briefing.per_set, key=lambda x: (x == "encore", x)):
        lines += [f"## {_set_label(s)}", *[f"- {p}" for p in briefing.per_set[s]], ""]
    if briefing.notable_moments:
        lines += ["## Notable moments", *[f"- {m}" for m in briefing.notable_moments], ""]
    lines += ["## Reception", briefing.review_sentiment, ""]
    if briefing.cautions:
        lines += ["## Cautions for the scriptwriter", *[f"- {c}" for c in briefing.cautions], ""]
    return "\n".join(lines)


def normalize_briefing(b: Briefing) -> Briefing:
    """3a: a copy of `b` with every empty `per_set` entry removed; everything
    else identical. An empty `per_set` dict stays empty (no talking points at
    all is still a guard problem)."""
    return b.model_copy(deep=True,
                        update={"per_set": {k: list(v) for k, v in b.per_set.items() if v}})


def song_components(title: str) -> list[str]:
    """3b: a title's segue components, normalised. Strips a leading structure
    prefix (`E:`, `E1:`, `Encore:`), trailing segue/footnote markers and one
    trailing parenthetical (then trailing markers again), splits on segues,
    `normalize_song`s each part and drops empties."""
    t = _BRIEF_STRUCTURE_PREFIX.sub("", title)
    t = _BRIEF_TRAILING.sub("", t)
    t = _BRIEF_PAREN.sub("", t)
    t = _BRIEF_TRAILING.sub("", t)
    return [c for c in (normalize_song(p) for p in _BRIEF_SEGUE.split(t)) if c]


def song_comma_components(title: str) -> list[str]:
    """A merged-tease title (`A (tease), B (tease), C (tease)`) is one track
    carrying several songs: split on commas OUTSIDE parentheses and return the
    `song_components` of each part, in order. Fewer than two non-blank parts
    (no top-level comma) returns `[]`. This only ever ADDS known components to
    the guard's set; mentions are never split on commas."""
    parts, depth, cur = [], 0, []
    for ch in title:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    parts = [p for p in parts if p.strip()]
    if len(parts) < 2:
        return []
    return [c for p in parts for c in song_components(p)]


def known_song(song: str, exact: set[str], components: set[str]) -> bool:
    """3b: today's exact test first, so the matcher is a superset of today's;
    else known when the song has components and EVERY one is a known
    component. No fuzzy, loose or subphrase matching."""
    if normalize_song(song) in exact:
        return True
    cs = song_components(song)
    return bool(cs) and all(c in components for c in cs)


def _words_before(prose: str, start: int, n: int) -> list[str]:
    """The last `n` words before `start`, within its own clause and field."""
    clause = _CLAUSE_BREAK.split(prose[:start])[-1]
    toks = (t.strip(string.punctuation).lower() for t in clause.split())
    return [t for t in toks if t][-n:]


def _qualified(prose: str, m: re.Match) -> bool:
    """3c: a count or ordinal match that is negated or scoped below the show."""
    if any(w in _NEGATION_2 for w in _words_before(prose, m.start(), 2)):
        return True
    four = _words_before(prose, m.start(), 4)
    for phrase in _NEGATION_4:
        k = len(phrase.split())
        if any(" ".join(four[i:i + k]) == phrase for i in range(len(four) - k + 1)):
            return True
    return bool(_SCOPE_AFTER.match(prose[m.end():]))


def _claim_matches(prose: str) -> tuple[list[re.Match], list[re.Match]]:
    """3c: the (count, ordinal) matches that still count as claims under full
    narration. A count whose intervening word is a non-show-wide qualifier is
    skipped, and any match that is negated or followed by a scope phrase is
    skipped. Spans equal today's regexes' (the 3c count pattern only adds a
    capture group), which is how scripts/replay_holds.py lists the matches
    3c suppresses."""
    counts = [m for m in _SET_COUNT_CLAIM_3C.finditer(prose)
              if (m.group(2) or "").lower() not in _NOT_SHOW_WIDE and not _qualified(prose, m)]
    ordinals = [m for m in _ORDINAL_SET.finditer(prose) if not _qualified(prose, m)]
    return counts, ordinals


def _claim_counts(prose: str) -> tuple[set[int], dict[int, str]]:
    """3c: (claimed set counts, implied ordinals) under full narration."""
    counts, ordinals = _claim_matches(prose)
    return ({_COUNT_WORDS[m.group(1).lower()] for m in counts},
            {_ORDINALS[m.group(1).lower()]: m.group(1).lower() for m in ordinals})


def _guard_prose(b: Briefing) -> str:
    r"""The prose `briefing_guard`'s set-count checks scan (also read by
    scripts/replay_holds.py's suppressed-claims report, so the two can never
    scan different text).

    briefing.cautions is deliberately excluded: cautions exist to flag exactly
    the kind of uncertain/conflicting-source phrasing (e.g. "sources disagree
    on whether there were three sets") that the set-count checks would misread
    as an assertion and false-positive on.

    Fields are joined by a newline, the field boundary 3c's negation windows
    stop at. Today's regexes' `\s+` spans it exactly as it spanned the single
    space it replaced (same length), so their matches and spans, and with
    them the vague branch, are unchanged."""
    return "\n".join([b.context, b.significance, b.review_sentiment, *b.notable_moments,
                      *(p for pts in b.per_set.values() for p in pts)])


def briefing_guard(briefing: Briefing, show: Show) -> list[str]:
    """A briefing that misnames songs or sets — or breaks the vague-narration
    contract — must never ship; cross-check against show.json."""
    problems: list[str] = []
    exact = {normalize_song(t.title) for t in show.tracks}
    components = (exact | {c for t in show.tracks for c in song_components(t.title)}
                  | {" ".join(song_components(t.title)) for t in show.tracks}
                  | {c for t in show.tracks for c in song_comma_components(t.title)})
    for song in briefing.mentioned_songs:
        if not known_song(song, exact, components):
            problems.append(f"briefing mentions unknown song: {song}")
    sets = {t.set for t in show.tracks}
    for s in briefing.per_set:
        if s not in sets:
            problems.append(f"briefing references nonexistent set: {s}")
    prose = _guard_prose(briefing)
    n_sets = len({t.set for t in show.tracks if t.set != "encore"})
    if briefing.narration == "vague":
        # Vague means: assert nothing about set structure, name no songs.
        # Unchanged by slice 3: today's regexes, no qualifier/negation/scope skip.
        claimed = {_COUNT_WORDS[m.group(1).lower()] for m in _SET_COUNT_CLAIM.finditer(prose)}
        implied = {_ORDINALS[m.group(1).lower()]: m.group(1).lower()
                   for m in _ORDINAL_SET.finditer(prose)}
        if briefing.per_set:
            problems.append("briefing has per-set talking points under vague narration")
        if briefing.mentioned_songs:
            problems.append("briefing names songs under vague narration")
        if claimed or implied:
            problems.append("briefing asserts set structure under vague narration")
    else:
        claimed, implied = _claim_counts(prose)    # 3c
        if not briefing.per_set:
            problems.append("briefing has no per-set talking points")
        for n in sorted(claimed):
            if n != n_sets:
                problems.append(f"briefing claims {n} sets but structure has {n_sets}")
        for n, word in sorted(implied.items()):
            if n > n_sets:
                problems.append(
                    f"briefing mentions the {word} set but structure has {n_sets} sets")
    return problems


def vetting_summary_text(vr: VettingResult | None) -> str:
    """Compact rendering of a vetting result for the prompt's {{vetting}} slot,
    so `cautions` are grounded in the vet stage's findings rather than invented."""
    if vr is None:
        return "(no vetting data)"
    lines = ["Vetting flags: " + "; ".join(vr.flags) if vr.flags
             else "Research passed vetting with no flags."]
    if vr.adopted_date:
        lines.append(f"The show date was corrected to {vr.adopted_date} "
                     "based on research (archive metadata had a placeholder).")
    if vr.vetting.context:
        lines.append("Context: " + vr.vetting.context)
    return "\n".join(lines)


def vetting_summary(show_ws: ShowWorkspace) -> str:
    """`vetting_summary_text` over the show's stored vetting.json."""
    if not show_ws.vetting.exists():
        return vetting_summary_text(None)
    return vetting_summary_text(read_model(show_ws.vetting, VettingResult))


def generate_briefing(provider, show: Show, research_md: str, reviews: list[dict], *,
                      narration: str, vetting: VettingResult | None) -> tuple[Briefing, list[str]]:
    """The brief LLM task (two attempts, the guard's problems fed back once):
    the normalised, narration-stamped briefing and the guard problems still
    standing (`[]` on success). Writes nothing; `run_brief` and `llama
    reapply` (spec slice 6) do their own writes."""
    inputs = dict(
        show_json=show.model_dump_json(indent=2),
        research=research_md or "(no research available)",
        vetting=vetting_summary_text(vetting),
        reviews_digest=reviews_digest(reviews),
        narration_note=narration_note(narration),
    )
    feedback = ""
    for _attempt in range(2):
        briefing = run_json_task(provider, "brief", Briefing,
                                 template=load_prompt("brief"), feedback=feedback, **inputs)
        briefing.narration = narration  # stamped; the LLM's value is never trusted
        briefing = normalize_briefing(briefing)   # 3a: before the guard and the writes
        problems = briefing_guard(briefing, show)
        if not problems:
            break
        feedback = (
            "IMPORTANT: your previous briefing failed fact-checking: "
            + "; ".join(problems)
            + ". Fix every problem; stay strictly grounded in the inputs."
        )
    return briefing, problems


def run_brief(
    show_ws: ShowWorkspace,
    provider,
    show: Show,
    research_md: str,
    reviews: list[dict],
    force: bool = False,
) -> Briefing:
    if not should_run(show_ws.briefing_json, force):
        briefing = read_model(show_ws.briefing_json, Briefing)
        if not show_ws.briefing_md.exists():
            # briefing.md is a pure function of briefing.json (see
            # render_briefing_md); if only the .md is missing, self-heal by
            # re-rendering it instead of leaving package's hard requirement
            # for both artifacts unresolvable short of a full re-brief.
            write_artifact(show_ws.briefing_md, render_briefing_md(briefing, show))
        return briefing

    narration = read_overrides(show_ws).narration
    vetting = (read_model(show_ws.vetting, VettingResult)
               if show_ws.vetting.exists() else None)
    briefing, problems = generate_briefing(provider, show, research_md, reviews,
                                           narration=narration, vetting=vetting)
    if problems:
        current = read_model(show_ws.show, Show)
        current.review_flags = current.review_flags + problems
        current.needs_review = True
        write_artifact(show_ws.show, current)
    write_artifact(show_ws.briefing_json, briefing)
    write_artifact(show_ws.briefing_md, render_briefing_md(briefing, show))
    return briefing
