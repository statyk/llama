import datetime
import logging
import re
from collections.abc import Sequence
from typing import NamedTuple

from herder import HerderError, TaskFailed, run_json_task
from llama import jerrybase
from llama.config import StructureConfig
from llama.errors import LlamaError
from llama.junk import FORMAT_BY_AUDIO, LOSSLESS_TITLE_FORMATS, filter_files
from llama.ia_client import IAError
from llama.models import (AlignedStructure, Candidate, ParsedSetlist, Show,
                          SourcedParse, StructureInfo)
from llama.prompts import load_prompt
from llama.setlist import parse_setlist
from llama.siblings import DonorTape, cplus_filter, propose_rows, rate_alignment
from llama.songs import GD_SHORTHAND
from llama.structure import (TAUTOLOGICAL_TITLE_SOURCES, adopt_gap_titles, align,
                             apply_llm_alignment, blend_segues, from_setlistfm,
                             fuzzy_norm_title, norm_title, rank_parses,
                             structure_guard, venues_equivalent)
from llama.titles import (clean_tag_titles, resolve_titles, set_breaks,
                          sibling_format_titles, title_fraction)
from llama.util import length_seconds
from llama.workspace import ShowWorkspace, read_model, read_overrides, should_run, write_artifact

log = logging.getLogger("llama")


def _sets_from_breaks(n_tracks: int, breaks: list[int],
                      encore_after: int | None = None) -> list[str]:
    """Numbered set labels ("1","2",...) for each 1-based track, given the
    track numbers a break falls *after*. Break after track b closes a set.

    `encore_after` relabels every track past it "encore" -- the one label this
    function cannot otherwise emit. Without it, an operator forcing a break
    before a one-song encore gets set "3", which then contradicts jerrybase's
    numbered-set count (`expected_set_count` excludes encores) and trips
    `structure_guard`. That is a hold traded for a different hold, which is
    what this parameter exists to stop.
    """
    bset = set(breaks)
    labels, cur = [], 1
    for i in range(1, n_tracks + 1):
        labels.append(str(cur))
        if i in bset:
            cur += 1
    if encore_after is not None:
        for i in range(encore_after, n_tracks):
            labels[i] = "encore"
    return labels


def _validate_structure_override(n_tracks: int, breaks: list[int],
                                 encore_after: int | None) -> None:
    """Range- and order-check the structure overrides. Raises LlamaError."""
    bad = [n for n in breaks if not (1 <= n < n_tracks)]
    if bad:
        raise LlamaError(f"overrides.set_breaks: track number(s) out of range "
                         f"{bad} (show has {n_tracks} tracks)")
    if encore_after is None:
        return
    if not (1 <= encore_after < n_tracks):
        raise LlamaError(f"overrides.encore_after: track {encore_after} out of range "
                         f"(show has {n_tracks} tracks)")
    if breaks and encore_after <= max(breaks):
        raise LlamaError(f"overrides.encore_after ({encore_after}) must be greater "
                         f"than every set break {sorted(breaks)} -- if {encore_after} "
                         f"is already listed in set_breaks, drop it there instead: "
                         f"encore_after implies that break on its own")


def _breaks_of(sets: list[str]) -> list[int]:
    """Inverse of _sets_from_breaks: the 1-based track numbers a break falls
    after, given per-track set labels."""
    return [i + 1 for i in range(len(sets) - 1) if sets[i + 1] != sets[i]]


_EVENT_SUFFIX = re.compile(r"/e(\d+)$")


def _event_kind(pid: str) -> tuple[str | None, int | None]:
    """Read the per-event grouping suffix: ('event', N) | ('spans', None) |
    ('unassigned', None) | (None, None)."""
    m = _EVENT_SUFFIX.search(pid)
    if m:
        return "event", int(m.group(1))
    tail = pid.rsplit("/", 1)[-1]
    if tail in ("spans", "unassigned"):
        return tail, None
    return None, None



def _description(meta: dict) -> str:
    desc = meta.get("description") or ""
    if isinstance(desc, list):
        desc = "\n".join(str(d) for d in desc)
    return str(desc)


def _creator(meta: dict) -> str | None:
    creator = meta.get("creator")
    if isinstance(creator, list):
        creator = creator[0] if creator else None
    return creator


def _donor_key(agreement: float | None, cost: float, identifier: str) -> tuple:
    """Sort key for picking the winning donor: highest agreement, then lowest
    DP cost, then identifier (spec order). `agreement is None` (no anchors at
    all -- `rate_alignment`'s "no-anchors" band) ranks BELOW every real
    agreement value including 0.0: 0.0 is a real, if bad, measurement (the
    tape has anchors and none of them agree), while None means no measurement
    was possible at all."""
    rank = agreement if agreement is not None else -1.0
    return (-rank, cost, identifier)


def load_donor_tapes(ia, candidate: Candidate, identifier: str,
                     want: str | Sequence[str]) -> tuple[list[DonorTape], list[str]]:
    """Load every non-self recording in `candidate.recordings` as a
    `DonorTape` -- the ONE definition of "qualifying donor", shared by
    `_sibling_transfer` (gather's automatic pass) and `cli._propose_titles_for_show`
    / triage's `[t]` (the operator surface, Task 6). Extracted out of
    `_sibling_transfer` rather than reimplemented CLI-side: a second
    "which recordings count as donors" would be invisible when it drifted,
    exactly the class of duplication this module's docstrings keep warning
    about.

    A recording qualifies when: it is not `identifier` itself, its metadata
    fetches without error, `filter_files` leaves at least one kept file, and
    every kept file has a real (non-`None`) duration -- the same three
    conditions `_sibling_transfer` checked inline before this extraction.

    Returns `(donors, notes)`. `notes` carries one message per sibling whose
    metadata could not be fetched (`IAError`); a sibling that fetches fine
    but yields no kept files or an incomplete duration is silently skipped,
    matching prior behaviour -- neither case is a fetch failure worth a note.
    """
    donors: list[DonorTape] = []
    notes: list[str] = []
    for rec in candidate.recordings:
        if rec.identifier == identifier:
            continue
        try:
            files = ia.metadata(rec.identifier).get("files", [])
        except IAError as err:
            # Same three-line idiom as _collect_parses above, on the same
            # call, for the same identifiers -- one flaky sibling must not
            # abort the whole gather stage (the loosened fetch gate widened
            # how often this call fires; it does not change how a failure
            # should be handled).
            notes.append(f"could not fetch sibling {rec.identifier}: {err}")
            continue
        kept, _, _ = filter_files(files, want_format=want)
        if not kept:
            continue
        durations = [length_seconds(f.get("length")) for f in kept]
        if any(d is None for d in durations):    # skip donors with incomplete durations
            continue
        donors.append(DonorTape(identifier=rec.identifier,
                                names=[f["name"] for f in kept],
                                durations=durations,
                                titles=clean_tag_titles(kept)))
    return donors, notes


def best_donor(ia, candidate: Candidate, identifier: str, want: str | Sequence[str],
               tracks: list, metadata_norms: set[str]):
    """Load every qualifying donor (`load_donor_tapes`), align each against
    `tracks`' own durations, rate the pair, and return the single winner --
    highest anchor agreement, then lowest DP cost, then identifier
    (`_donor_key`'s tie-break). ONE definition of "who wins", shared by
    `_sibling_transfer` (gather's automatic pass) and
    `cli._sibling_proposal` (the operator surface) -- fix round 1 on Task 6:
    the two used to re-implement this four-step loop (propose_rows -> skip
    None -> rate_alignment -> `_donor_key` -> sort -> `[0]`) verbatim, and a
    reviewer mutation (sort the CLI's copy in reverse, i.e. pick the WORST
    donor) passed the whole suite -- the drift class this task exists to
    close, one level up. Extracting this also removes the need for `cli.py`
    to import `_donor_key` across the module boundary at all.

    Returns `(donor, rows, res, notes)`. `notes` is `load_donor_tapes`'s
    fetch-failure notes, always returned even when no donor qualifies.
    `(donor, rows, res)` are `(None, [], None)` when no candidate produced
    usable rows -- callers branch on `donor is None`, not on emptiness of
    `notes` (a donor can fail to fetch AND another can still qualify)."""
    target_durs = [t.duration_sec for t in tracks]
    donors, notes = load_donor_tapes(ia, candidate, identifier, want)
    candidates = []
    for donor in donors:
        rows, diag = propose_rows(target_durs, donor, metadata_norms=metadata_norms)
        if rows is None:
            continue
        res = rate_alignment(rows, tracks)
        candidates.append((_donor_key(res.agreement, diag["cost"], donor.identifier),
                           donor, rows, res))
    if not candidates:
        return None, [], None, notes
    candidates.sort(key=lambda c: c[0])
    _, donor, rows, res = candidates[0]
    return donor, rows, res, notes


def _sibling_transfer(ia, candidate: Candidate, identifier: str,
                      want: str | Sequence[str], tracks: list,
                      metadata_norms: set[str]) -> tuple[list, list[str]]:
    """The guarded duration-alignment title transfer. Loads every non-self
    sibling recording, aligns each against `tracks`' own durations
    (`siblings.propose_rows`), rates the pair (`siblings.rate_alignment`),
    picks the winning donor, and -- only in the `auto` band, and only after
    running `siblings.cplus_filter` -- fills `unresolved` tracks with the
    surviving `adopt` rows, stamped `title_source="sibling-align"`.

    Returns `(tracks, notes)`. `tracks` is always a NEW list -- inputs are
    never mutated in place, on every return path including "no candidate
    donor at all" -- and `notes` carries pair-level declines (why the
    winning donor's band was not `auto`, or why a donor could not be fetched
    at all), per-run declines (why an `auto`-band run still did not fill --
    concern #2 from Task 4's review: a C+ demotion reason is otherwise
    visible only on the internal, never-returned `SiblingRow` itself, so it
    must be surfaced here or it is simply lost).

    CONCERN #1 (data loss): `cplus_filter` says nothing about a track that
    already has a title -- an `adopt` row on an already-titled track survives
    C+ untouched (it gates FILL RUNS, not individual already-resolved
    tracks). This function is what must refuse to apply such a row: only a
    track whose OWN `title_source` is still `"unresolved"` at the moment of
    application is ever written, so a tape's own tag (or an operator's
    override) can never be clobbered by the sibling's guess, no matter what
    verdict the row carries.

    CONCERN #3: `cplus_filter` does not itself check the band -- it is called
    here ONLY when `rate_alignment` already routed the pair to `"auto"`;
    calling it on an `operator`/`declined`/`no-anchors` pair would gate
    nothing meaningful (there is no automatic adoption to gate).

    Fan-out cost (Task 5 fix round, measured): `propose_rows` per donor is
    0.015 / 0.067 / 0.23 / 1.88 SECONDS at 20 / 40 / 60 / 120 target tracks.
    Against 37,144 real candidates (~/.llama/runs): donors-per-performance is
    median 1, p90 9, max 38; 89 gathered shows put track count at median 22,
    p90 31, max 63. Typical show ~0.02-0.06s, p90 show ~0.3s, worst observed
    (38 donors x 63 tracks) ~9s once, at gather time -- acceptable inside a
    stage that already does per-recording network IO and audio downloads, no
    change made. The loosened fetch gate above does not add network cost:
    `IAClient.metadata` is disk-cached, and `_collect_parses` (above, in
    `build_canonical`) has already fetched every sibling's metadata for this
    same show before this function ever runs."""
    donor, rows, res, notes = best_donor(ia, candidate, identifier, want, tracks, metadata_norms)
    if donor is None:
        return list(tracks), notes
    new_tracks = list(tracks)

    if res.band != "auto":
        pct = f"{res.agreement:.0%}" if res.agreement is not None else None
        if res.band == "declined":
            notes.append(f"sibling alignment declined (anchor agreement {pct})")
        elif res.band == "operator":
            notes.append(f"sibling alignment needs operator review (anchor agreement {pct})")
        else:                                     # "no-anchors"
            notes.append(f"sibling alignment skipped ({donor.identifier}): "
                         "tape has no independent anchors")
        return new_tracks, notes

    filtered = cplus_filter(rows, tracks)          # C+ is auto-band only (concern #3)
    seen_reasons: set[str] = set()
    for row in filtered:
        pos = row.track - 1
        if tracks[pos].title_source != "unresolved":
            # concern #1: never overwrite a track that already has a title,
            # regardless of what verdict the row carries.
            continue
        if row.verdict == "adopt":
            new_tracks[pos] = new_tracks[pos].model_copy(
                update={"title": row.proposed, "title_source": "sibling-align"})
        elif row.reason and row.reason not in seen_reasons:
            seen_reasons.add(row.reason)
            notes.append(f"sibling alignment ({donor.identifier}): {row.reason}")
    return new_tracks, notes


# Recovery fires below this and requires the sibling to clear the second
# threshold. Both are the values the spec's 166-item measurement was taken
# at and were not independently swept - changing them invalidates it.
_RECOVER_BELOW = 0.5
_RECOVER_SIBLING_ABOVE = 0.9


def _recover_format_titles(
    files: list[dict], kept: list[dict], ordering: dict
) -> dict[str, str] | None:
    """Titles lifted from a lossless copy of the same item, when the delivered
    format's own tags are missing. archive.org sometimes builds the lossy
    derivative without carrying the tags across."""
    if title_fraction(clean_tag_titles(kept)) >= _RECOVER_BELOW:
        return None
    for fmt in LOSSLESS_TITLE_FORMATS:
        if fmt == ordering.get("format"):
            continue  # that is the set we already have
        other, _, _ = filter_files(files, want_format=fmt)
        recovered = sibling_format_titles(kept, other)
        if recovered and title_fraction(list(recovered.values())) >= _RECOVER_SIBLING_ABOVE:
            return recovered
    return None


def _collect_parses(ia, candidate: Candidate, identifier: str, chosen_meta: dict):
    """Parse every recording's description. Chosen recording first so it wins
    rank ties among copy-paste descriptions."""
    parses: list[SourcedParse] = []
    notes: list[str] = []
    descriptions: list[str] = []
    ordered = sorted(candidate.recordings, key=lambda r: r.identifier != identifier)
    for rec in ordered:
        if rec.identifier == identifier:
            meta = chosen_meta
        else:
            try:
                meta = ia.metadata(rec.identifier).get("metadata", {})
            except IAError as err:
                notes.append(f"could not fetch sibling {rec.identifier}: {err}")
                continue
        desc = _description(meta)
        descriptions.append(desc)
        source = "chosen" if rec.identifier == identifier else f"lma:{rec.identifier}"
        parses.append(SourcedParse(source=source, parsed=parse_setlist(desc)))
    return parses, notes, descriptions


def _format_tracks(tracks) -> str:
    return "\n".join(
        f"{t.index} | {t.filename} | {t.title} | {t.duration_sec or '?'}" for t in tracks
    )


def _format_setlist(canonical: ParsedSetlist) -> str:
    return "\n".join(
        f"[set {i.set}] {i.title}{' >' if i.segue else ''}" for i in canonical.items
    )


# --- Head-banner guard ------------------------------------------------------
#
# Task 1 stopped the parser discarding a setlist that sits above a marker which
# cannot open a show. That recovers real setlists, but the recovered block is
# sometimes a taper banner - band / venue / city / date / rig lines - and it
# lands at the HEAD of the canonical setlist, the one position where junk is
# unrecoverable: `align`'s two-pointer starts there and only advances on a
# match, so track 1 never reaches the real songs. Measured on the common
# population (baseline pair db02575 -> 98ba55d, clean_tracks construction):
# 54 shows worse, 53 of them to ZERO matched tracks.
#
# The fix point is gather, not the parser, because gather holds the one thing
# the parser never sees: THIS show's own metadata. That turns the open question
# "is this line a song?" into the closed one "is this literally this show's
# artist, venue, city, state or date?". There is no gazetteer anywhere here -
# the place vocabulary is this show's own metadata, and the only fixed lists
# are rig/lineage chatter and the closed postal-code list (50 states + DC).
#
# Three measured hazards are design constraints. Do not relearn them:
#   * `fades?` in the chatter lexicon matches the word *Fade*, and stripped the
#     heads of "Not Fade Away" and "West L.A. Fade Away". Excluded. Any token
#     proposed for this lexicon must be checked against real song titles first.
#   * Bare `@` / `~` / `#` match the trailing ANNOTATION markers Dead tapers
#     put on titles ("Peggy-O @", "Raise The Roof #"). Anchored positionally
#     below ("@ <digits>", leading `~`), never bare.
#   * Greedy strip + broad lexicon is the wrong combination: putting the
#     chatter lexicon inside stage 1's strip-to-last predicate cost -10/-9/-8
#     real songs per show (toad1996-09-18, joshritter2015-05-29,
#     damienrice2015-04-14). Broad vocabulary belongs ONLY in stage 2's
#     gap-bounded run.
_MONTHS = ("january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december")

# Rig/lineage line openers. Consulted in BOTH stages - a "Source: ..." line is
# as certainly not a song as the venue name is.
_RIG = re.compile(r"^(?:mic\s+)?location\b|^(?:source|transfer|lineage|recorded"
                  r"|taper|equipment|tagging)\b", re.I)

# Broad rig/gear/lineage vocabulary. This is deliberately wider than the
# parser's own `_NOISE` (widening that globally was declined in phase 3) and is
# safe only because nothing consults it except stage 2's run, which starts at
# the head and stops at the first stretch of more than `_HEAD_GAP`
# unrecognized items.
_HEAD_CHATTER = re.compile(
    r"^https?://|www\."
    r"|@\s*\d|^\s*~|~\s*\d"
    r"|\b\d+\s*['\"]|\brow\s+\d+\b|^right of\b"
    r"|\b\d+\s*(?:ft|feet|foot|cm|khz|hz|bit)\b"
    r"|\b(?:resampl\w*|dither\w*|wavelab|izotope|ozone|editing"
    r"|mastered|remaster\w*|transferr?ed|seeded|conversion|encode\w*"
    r"|mics?|preamp|xlrs?|soundboard|sbd|matrix|dfc|fob|foh|onstage|monitors?"
    r"|dsp|wav|cd.?audio"
    r"|nakamichi|schoeps|neumann|sennheiser|akg|sonosax|oade|lunatec"
    r"|audio.?technica|sound.?forge|rms|channels?|compression|normalized)\b"
    # Gear model numbers, in two branches, because a taper track prefix
    # ("t01)", "d101", "A01.", "B07.") and a gear model ("SKM140", "M62")
    # are the SAME lexical shape - letters then digits. What separates them
    # is POSITION: the prefix opens the item, the model is named inside one.
    # So a >=2-letter form matches anywhere, and a single-letter form only
    # when something precedes it, which keeps "Telefunken M62",
    # "Sony PCM-M10" and "mz-m200" while rejecting a leading "t01)".
    # Discriminating on letter count instead was measured and is a net loss
    # (-59 matched, 4 shows to zero): single-letter models are real and
    # common gear (M62, M10, R44, m200).
    r"|\b[a-z]{2,4}-?\d{2,4}[a-z]?s?\b"
    r"|(?<=.)\b[a-z]-?\d{2,4}[a-z]?s?\b",
    re.I,
)

# The closed US postal-code list: 50 states + DC, plus USA. Matched UPPERCASE
# and WHOLE-ITEM only - lower-cased or embedded, many of these are ordinary
# words ("in", "or", "me", "hi", "la", "ok", "de", "pa", "ma").
_STATE = re.compile(r"^(?:A[LKZR]|C[AOT]|D[EC]|FL|GA|HI|I[DLNA]|K[SY]"
                    r"|LA|M[EDAINSOT]|N[EVHJMYCD]|O[HKR]|PA|RI|S[CD]"
                    r"|T[NX]|UT|V[TA]|W[AVIY]|USA|U\.S\.A\.?)$")

# A metadata match beyond the first K items never triggers a strip: K bounds the
# blast radius of any false positive, and a song legitimately named after the
# venue or city survives everywhere below it.
_HEAD_K = 10
# Banner tails carry arbitrary unrecognizable fragments ("din", "110") between
# recognizable chatter lines, so the stage-2 run tolerates a gap. The bound is
# PER GAP, not cumulative: a run that alternates chatter and songs every <=2
# items chains hops and keeps going. What keeps a real setlist safe is
# therefore the lexicon staying off real song titles (the hazard notes above),
# not this number.
_HEAD_GAP = 2


def _place_norms(value: str | None) -> set[str]:
    """Normalized forms of one venue/city string, plus its natural variants.

    Split on `,`/`@` because item metadata packs several places into one field
    ("Nashville, TN @ City Hall") while the banner puts each on its own line.
    The leading-article and leading-digit variants exist because the parser has
    already mangled the banner line before gather sees it: its enumerated gate
    strips the "40" off "40 Watt Club".
    """
    out: set[str] = set()
    for part in re.split(r"[,@]", value or ""):
        part = part.strip()
        if not part:
            continue
        for variant in (part,
                        re.sub(r"^(?:the|a)\s+", "", part, flags=re.I),
                        re.sub(r"^\d+\s+", "", part)):
            norm = fuzzy_norm_title(variant)
            if norm:
                out.add(norm)
    return out


def _date_norms(date: str) -> set[str]:
    """Normalized renderings of the show date as a banner line might write it.

    Enumerated rather than pattern-matched: an "is this a date?" pattern would
    also match song titles, while this list can only ever match THIS show's own
    date."""
    try:
        day = datetime.date.fromisoformat((date or "")[:10])
    except ValueError:
        return set()
    mon, weekday = _MONTHS[day.month - 1], day.strftime("%A")
    y, m, d = day.year, day.month, day.day
    renderings = (
        f"{mon} {d}", f"{mon[:3]} {d}",
        f"{mon} {d} {y}", f"{mon[:3]} {d} {y}",
        f"{d} {mon} {y}", f"{d} {mon}", f"{d} {mon[:3]} {y}",
        f"{y}", f"{y} {weekday}", f"{y} {weekday[:3]}",
        f"{m}/{d}/{y}", f"{m:02d}/{d:02d}/{y}",
        f"{m}/{d}/{str(y)[2:]}", f"{m:02d}/{d:02d}/{str(y)[2:]}",
        f"{y}/{m:02d}/{d:02d}", f"{y}-{m:02d}-{d:02d}",
        f"{weekday} {mon} {d} {y}", f"{weekday[:3]} {mon[:3]} {d} {y}",
        f"{mon} {d}th {y}", f"{mon} {d}st {y}",
        f"{mon} {d}nd {y}", f"{mon} {d}rd {y}",
        f"{d}th {mon} {y}", f"{d}st {mon} {y}",
        f"{d}nd {mon} {y}", f"{d}rd {mon} {y}",
        f"{d:02d} {mon[:3]} {y}", f"{d:02d} {mon[:4]} {y}",
        f"{d} {mon[:4]} {y}",
    )
    return {n for n in (fuzzy_norm_title(r) for r in renderings) if n}


def show_metadata_norms(artist: str, candidate: Candidate, meta: dict,
                        events: list) -> set[str]:
    """The closed vocabulary the head-banner guard matches against: everything
    this show's own metadata says about who/where/when it is.

    PUBLIC (fix round 1 on Task 6) because the operator surface shares it:
    `cli._sibling_proposal` needs the identical `metadata_norms` gather uses,
    so the sibling arm's hygiene check (`siblings.hygienic_title` via
    `propose_rows`) can never silently diverge from the pipeline's. A leading
    underscore imported across a module boundary is a false promise that the
    symbol is free to rename/re-signature -- the same reasoning
    `structure.hygienic_title`'s own docstring already gives for the
    identical choice, one task earlier in this feature."""
    norms = _date_norms(candidate.date)
    for value in (artist, candidate.venue, candidate.city,
                  meta.get("venue"), meta.get("coverage")):
        norms |= _place_norms(value if isinstance(value, str) else None)
    for event in events:
        norms |= _place_norms(event.venue)
        norms |= _place_norms(event.city)
    return norms


def _strip_head_banner(parsed: ParsedSetlist, norms: set[str]) -> ParsedSetlist:
    """Drop a taper banner sitting at the head of the parsed setlist.

    Stage 1 (metadata span): within the first `_HEAD_K` items find the LAST one
    that IS this show's metadata, and strip everything up to and including it -
    but only when metadata items are a MAJORITY of that span. Strip-to-last
    rather than a strict leading run because banners do not interleave songs,
    and the strict run measured 29 residual zero-alignment shows: it stops at
    the first unrecognized fragment, and zero-padded date formats and composite
    venue strings supply those constantly. The majority rule is what keeps a
    lone coincidental match - a song titled like the city - from eating the
    real songs above it. THE MAJORITY RULE BOUNDS STAGE 1 ONLY, and so does
    `_HEAD_K`; see the stage-2 note below for why that is not the protection it
    reads as.

    Stage 2 (chatter run): from the new head, trim this show's own metadata,
    rig/lineage chatter and bare state codes, tolerating a gap of up to
    `_HEAD_GAP` unrecognized items when chatter resumes immediately after.

    The metadata half of that list is easy to miss and is load-bearing:
    `is_chatter` is `is_meta OR _HEAD_CHATTER OR _STATE`, so THE METADATA
    VOCABULARY IS ITSELF A STAGE-2 HOP TARGET - and stage 2 has neither
    `_HEAD_K` nor the majority rule. A lone coincidental metadata match that
    stage 1 EXPLICITLY DECLINED still eats the songs above it whenever it lands
    within `_HEAD_GAP` of the head. Measured with `norms={"nashville"}`:

        ("Bertha", "Nashville", "Sugaree", "Ripple")   -> 2 songs lost
        ("Bertha", "Jack Straw", "Nashville", ...)     -> 3 songs lost
        ("Bertha", "Jack Straw", "Deal", "Nashville")  -> unchanged (gap 3 > 2)

    So stage 1 declining a match is not a decision stage 2 honours; it only
    moves the cost from "everything above it" to "at most `_HEAD_GAP` above
    it". Dropping `is_meta` from `is_chatter` is the behavioural fix and needs
    corpus re-measurement - filed for 4b, not attempted here.

    KNOWN DEFECT, measured, still open: the run is UNCAPPED. Neither `_HEAD_K`
    nor the majority rule applies to stage 2, so with `c` chatter-matching items
    it can consume up to `2 * c` real ones - verified by execution, linear in
    `c` with no ceiling. The only thing limiting it is the lexicon failing to
    match real song titles, which is necessary and measurably nowhere near
    sufficient: on an enumerated tracklist where every line matched, 7 corpus
    shows were stripped to zero items. The position-aware gear-model branches
    above cut that to 4 by removing the driver (taper track prefixes), but they
    fix the CAUSE, not the shape - a different open vocabulary would do it
    again.

    SECOND DEFECT, accepted knowingly, NOT a side effect: the gap hop consumes
    the item it steps over. Neither "Liar" (bts2008-10-21) nor "buckingham
    green" (ween2001-07-28) matches any chatter alternative; each sits at index
    0 and is eaten to reach an in-line stage note at index 1 whose word
    "monitor(s)" does match. Both stay lost. This is SILENT - neither show
    reaches zero, so a per-show zero gate cannot see it - and nothing measured
    reaches it without re-breaking the wipes above.

    Four shapes were measured and rejected; do not re-propose one without
    re-measuring both corpora (baseline `da4393f`, common population, aligned
    song-like tracks, wipes counted as to-zero events):
      require a stage-1 metadata hit before stage 2 runs
          -56, THREE shows to zero. Rig-only banners ("SKM140"/"V2"/"Mini-Me")
          legitimately need stage 2 with no metadata evidence at all.
      let stage 2 only BEGIN on a chatter item
          -886, TEN shows to zero, and it is the prototype's v4. The premise
          "a banner always starts with a banner line" is true of the raw
          description and false here: stage 1 has already eaten the
          recognizable banner lines, so what sits at the new head is the
          unrecognizable fragment the gap rule exists to bridge ("din", "110",
          "Friday"). A precondition holding at the guard's entry need not hold
          at the entry of its second phase.
      cap the run at `_HEAD_K`
          only -5 on top of the branches above, and it takes a real show
          (delmccouryband2011-05-27) to do it. Measured as NOT load-bearing
          once the cause is fixed; deliberately not shipped. Note it would be a
          CAP and not a bound - inside those 10 items `2 * c` still runs free.
      discriminate the gear shape on letter count
          -59, four shows to zero (see the branch comment above).
    """
    items = parsed.items

    def is_meta(item) -> bool:
        return fuzzy_norm_title(item.title) in norms or bool(_RIG.match(item.title))

    def is_chatter(item) -> bool:
        # NOTE the `is_meta` term: this show's own metadata counts as chatter
        # too, so stage 2 can hop to a metadata coincidence that stage 1's
        # majority rule declined. See the docstring - this is not "rig/lineage
        # chatter and bare state codes" alone.
        return (is_meta(item) or bool(_HEAD_CHATTER.search(item.title))
                or bool(_STATE.match(item.title.strip())))

    last = -1
    for k in range(min(_HEAD_K, len(items))):
        if is_meta(items[k]):
            last = k
    if last >= 0:
        hits = sum(1 for k in range(last + 1) if is_meta(items[k]))
        if hits * 2 <= last + 1:
            last = -1
    kept = items[last + 1:]

    pos = 0
    while pos < len(kept):
        if is_chatter(kept[pos]):
            pos += 1
            continue
        gap = next((g for g in range(1, _HEAD_GAP + 1)
                    if pos + g < len(kept) and is_chatter(kept[pos + g])), None)
        if gap is None:
            break
        pos += gap + 1
    kept = kept[pos:]

    if len(kept) == len(items):
        return parsed
    if not kept:
        # A wipe must not ship silently. `run_gather`'s low-coverage branch is
        # guarded by `elif canonical.items and ...`, so an EMPTY canonical
        # short-circuits it: the show gets coverage 0.0, no
        # "low-confidence structure alignment" flag, and needs_review False -
        # strictly quieter than the same show with a bad-but-non-empty setlist,
        # which is flagged. The short-circuit predates this guard, but the
        # guard is what made it reachable, by turning a non-empty canonical
        # that would have been flagged into an empty one that is not.
        #
        # Downgrading confidence routes the wipe into the EXISTING
        # "low-confidence setlist" flag rather than inventing new vocabulary,
        # and the semantics are honest rather than convenient: a setlist with
        # no items in it genuinely is low confidence. The other two downstream
        # readers are provably inert on an empty parse - `resolve_titles`
        # already refuses a setlist whose length differs from the track count,
        # and gather's sibling-lookup gate is already true for the same reason.
        return parsed.model_copy(update={"items": kept, "confidence": "low"})
    return parsed.model_copy(update={"items": kept})


def _drop_artist_items(parsed: ParsedSetlist, artist: str) -> ParsedSetlist:
    """Remove setlist items that are just the performing artist's name.

    LMA descriptions routinely put the band name on its own line above the
    songs; the parser has no artist to compare against, so it emits it as a
    song. It can never match a track, and every such item pushes the alignment
    pointer one step further from where the next real song sits.
    """
    key = jerrybase.artist_key(artist)
    if not key:
        return parsed
    kept = [i for i in parsed.items if jerrybase.artist_key(i.title) != key]
    if len(kept) == len(parsed.items):
        return parsed
    return parsed.model_copy(update={"items": kept})


# A run of footnote markers at the very END of a canonical item's title, with
# the whitespace that separates them: "Polly Put The Kettle On * ^",
# "High Lonesome Sound * # $". These are apparatus of the DESCRIPTION (they
# key a "* with Sam Bush" note further down the page), not part of any song's
# name, and they survive into adopted titles -> overrides.titles -> manifest
# v3 -> ID3 TIT2 -> the briefing -> emcee's script, where a "#" is wrong at
# every sink.
#
# THE LEADING \s+ IS LOAD-BEARING and must not be relaxed to \s*: it is the
# only thing that puts a real title ENDING in one of these characters -
# "100%", a title ending in "$" - out of this rule's reach. A marker is
# written as a separate token in every description convention; a title
# character is not. This is the same class of bound as `titles._TRACK_NUM_PREFIX`'s
# `\d{1,3}` (which keeps "1952 Vincent Black Lightning" and a bare "2001"
# out of the track-number strip's reach) - widen it and the rule starts
# eating real titles instead of apparatus.
#
# Trailing only, by construction: `$` anchors the match, so a marker
# character INSIDE a title ("Rock $ Roll") is untouched.
_FOOTNOTE_TAIL = re.compile(r"(?:\s+[*#%^$@]+)+\s*$")


def _strip_footnote_markers(parsed: ParsedSetlist) -> ParsedSetlist:
    """Drop trailing footnote markers from canonical item titles.

    Removes only apparatus: the title is otherwise byte-identical, and an item
    whose title is NOTHING but markers is left alone rather than reduced to
    residue. The residue guard tests for a surviving ALPHANUMERIC, not merely
    for a non-empty string: "* ^" strips to "*", which is non-empty and still
    not a title. Nothing is lost by the stronger test -- a canonical item with
    no alphanumeric character in it was never a song name.

    `SetlistItem.normalized` is deliberately NOT recomputed, and does not need
    to be: `songs.normalize_song` strips every non-alphanumeric character, so
    every marker this removes is already absent from `normalized`. Recomputing
    would produce the same string; leaving it alone makes that a guarantee
    rather than an assumption, and keeps `blend_segues` (which pools on
    `normalized`) provably untouched.
    """
    items = []
    changed = False
    for it in parsed.items:
        stripped = _FOOTNOTE_TAIL.sub("", it.title)
        if stripped != it.title and any(ch.isalnum() for ch in stripped):
            items.append(it.model_copy(update={"title": stripped}))
            changed = True
        else:
            items.append(it)
    return parsed.model_copy(update={"items": items}) if changed else parsed


class CanonicalBuild(NamedTuple):
    """`build_canonical`'s result. A NamedTuple rather than a bare 3-tuple so
    call sites read `result.source` instead of a positional index, and rather
    than an output-parameter (an earlier draft's `source_out: dict | None`)
    because that shape lets a caller silently forget to pass it and lose
    provenance with no signal -- exactly the kind of guess-by-omission this
    module elsewhere refuses to make."""
    setlist: ParsedSetlist
    notes: list[str]
    source: str | None


def build_canonical(ia, candidate: Candidate, identifier: str, meta: dict,
                    kept: list[dict], artist: str, events, *,
                    setlistfm=None, provider=None) -> CanonicalBuild:
    """The cleaned canonical performance setlist: every recording's
    description, plus setlist.fm when configured, ranked pick-best, then
    head-banner-stripped, artist-item-dropped and footnote-marker-stripped.

    `provider=None` skips the `extract_setlist` LLM fallback entirely, so
    callers outside the pipeline (`llama fix --suggest-titles`) never trigger
    an LLM call.

    Order matters for the cleaning pass: the banner strip runs on the head
    span first, then the artist drop globally. `events` covers every
    jerrybase event on the date, not just a resolved one -- a multi-event
    date leaves the caller's `event` None, and the banner guard still needs
    to recognize every candidate venue's name.

    `.source` names the winning parse's provenance (a `SourcedParse.source`
    value, or None if nothing ranked) -- `run_gather` reports it as
    `StructureInfo.source`.
    """
    parses, notes, descriptions = _collect_parses(ia, candidate, identifier, meta)
    if setlistfm is not None:
        raw = setlistfm.setlist(artist, candidate.date,
                                venue=candidate.venue, city=candidate.city)
        converted = from_setlistfm(raw) if raw else None
        if converted is not None:
            parses.insert(0, SourcedParse(source="setlist.fm", parsed=converted))

    best = rank_parses(parses, target_count=len(kept))
    if best is None and provider is not None:
        longest = max(descriptions, key=len, default="")
        if longest.strip():
            parsed = run_json_task(provider, "extract_setlist", ParsedSetlist,
                                   template=load_prompt("extract_setlist"),
                                   description=longest)
            best = SourcedParse(source="llm", parsed=parsed)
    source = best.source if best is not None else None
    canonical = best.parsed if best else ParsedSetlist()
    if best is not None and best.source == "setlist.fm":
        best_lma = rank_parses([p for p in parses if p.source != "setlist.fm"],
                               target_count=len(kept))
        canonical = blend_segues(canonical, best_lma.parsed if best_lma else None)

    metadata_norms = show_metadata_norms(artist, candidate, meta, events)
    canonical = _strip_head_banner(canonical, metadata_norms)
    canonical = _drop_artist_items(canonical, artist)
    canonical = _strip_footnote_markers(canonical)
    return CanonicalBuild(setlist=canonical, notes=notes, source=source)


def run_gather(
    show_ws: ShowWorkspace,
    ia,
    provider,
    candidate: Candidate,
    identifier: str,
    audio_format: str = "mp3",
    force: bool = False,
    align_provider=None,
    setlistfm=None,
    structure_cfg: StructureConfig | None = None,
    jerrybase_enabled: bool = False,
) -> Show:
    if not should_run(show_ws.show, force):
        return read_model(show_ws.show, Show)
    structure_cfg = structure_cfg or StructureConfig()

    md = ia.metadata(identifier)
    meta = md.get("metadata", {})
    artist = str(_creator(meta) or candidate.collection)
    want = FORMAT_BY_AUDIO[audio_format]
    kept, excluded, ordering = filter_files(md.get("files", []), want_format=want)
    # Computed on the unexcluded set, deliberately: it is a filename-keyed map
    # and resolve_titles only looks up names still in `kept`, so covering files
    # the operator later drops is harmless, while moving it below the exclusion
    # would let one dropped file change whether recovery fires at all.
    format_titles = _recover_format_titles(md.get("files", []), kept, ordering)

    overrides = read_overrides(show_ws)
    if overrides.exclude:
        drop = set(overrides.exclude)
        matched = {f["name"] for f in kept if f["name"] in drop}
        for missing in sorted(drop - matched):
            log.warning("overrides.exclude entry %r matched no file", missing)
        excluded += [{"filename": f["name"], "reasons": ["operator-excluded"]}
                     for f in kept if f["name"] in drop]
        kept = [f for f in kept if f["name"] not in drop]

    # Jerrybase structure evidence (no-op for artists absent from the dataset).
    # A per-event candidate (/eN) selects events[N-1] for every evidence check.
    # Resolved HERE, above the canonical-setlist build below, because
    # `build_canonical`'s head-banner guard reads the event venues as part of
    # this show's own metadata; nothing in this block depends on tracks or on
    # the canonical setlist.
    events = jerrybase.lookup(artist, candidate.date) if jerrybase_enabled else []
    # `ev_n`, not `n`: hoisting this block above the overrides loop below put
    # it in scope of that loop's `for n, forced in ...`, which rebinds `n`.
    # Harmless today because `ev_n` is consumed immediately, but the hoist
    # silently removed a guarantee and the distinct name puts it back.
    kind, ev_n = _event_kind(candidate.performance_id)
    if kind == "event" and events and 1 <= ev_n <= len(events):
        event = events[ev_n - 1]
    elif kind == "event":
        event = None
    elif len(events) == 1:
        event = events[0]
    else:
        event = None

    # Canonical performance setlist: every recording's description, plus
    # setlist.fm when configured, ranked pick-best, then cleaned (head-banner
    # stripped, artist-only items dropped) at the point it enters the stage,
    # before anything consumes it -- `resolve_titles` below only trusts the
    # setlist when `len(items) == len(tracks)`, so on an untagged tape one
    # header item costs every title on the show. `.source` (the winning
    # parse's provenance) is used below for `StructureInfo.source`.
    canonical, notes, canonical_source = build_canonical(
        ia, candidate, identifier, meta, kept, artist, events,
        setlistfm=setlistfm, provider=provider)
    # Recomputed (not re-fetched) rather than threaded out of build_canonical:
    # it's a pure function of already-in-scope values, and adopt_gap_titles
    # below needs it independently of the canonical-setlist build.
    metadata_norms = show_metadata_norms(artist, candidate, meta, events)

    # `kept and` is load-bearing: title_fraction is 0.0 on an empty list, so an
    # exclude-everything tape would otherwise fetch every sibling recording's
    # metadata to resolve zero titles. The output was never wrong, only the
    # fetches wasted. Loosened (Task 5): the old count-mismatch/confidence
    # condition is gone -- the new sibling-align pass below is guarded on its
    # own evidence (anchor agreement), not on how the canonical setlist lined
    # up, so gating the FETCH on that condition too was never doing anything
    # but adding false negatives.
    fetch_siblings = bool(kept and title_fraction(clean_tag_titles(kept)) < 1.0)
    tracks = resolve_titles(kept, canonical, format_titles=format_titles)
    for n, forced in overrides.titles.items():
        if not (1 <= n <= len(tracks)):
            raise LlamaError(f"overrides.titles: no track {n} "
                             f"(show has {len(tracks)} tracks)")
        tracks[n - 1] = tracks[n - 1].model_copy(
            update={"title": forced, "title_source": "override"})

    # Guarded duration-alignment sibling transfer. After the overrides loop
    # (an operator-forced title can anchor the guard) and before
    # adopt_gap_titles (see that call's own comment for why ordering there
    # matters to `Track.matched`). `siblings.py` stays pure; all IO is here.
    if fetch_siblings:
        tracks, sib_notes = _sibling_transfer(ia, candidate, identifier, want,
                                              tracks, metadata_norms)
        notes += sib_notes

    # Single-word Dead shorthand ("Scarlet", "Dew", "Help") is only safe
    # inside the Garcia universe — they are ordinary English words
    # elsewhere. Non-family shows get an empty table, which makes the
    # vocabulary a provable no-op on the non-Dead corpus. Shared with the
    # `align()` call below.
    family_aliases = GD_SHORTHAND if jerrybase.is_family_artist(artist) else {}

    # Fill count-forced runs of unresolved tracks between tag-verified anchors.
    # Runs here, after the overrides loop, so an operator-forced title can
    # ANCHOR a gap as well as survive it. metadata_norms is passed down
    # because structure.py must not import a stage.
    #
    # An adopted title *is* the canonical item's own text, so align() below
    # WOULD be guaranteed to match it -- tautologically raising `coverage` and
    # flipping `Track.matched` to True for tracks that were never
    # independently matched, which could suppress the "low-confidence
    # structure alignment" flag (gated on `align_coverage_threshold` below) on
    # exactly the shows where adoption took the riskiest action. RULED and
    # DELIBERATELY CORRECTED FOR, not merely accepted: `structure._songish_coverage`
    # excludes every source in `structure.TAUTOLOGICAL_TITLE_SOURCES`
    # (`setlist-gap` AND the whole-tape `setlist` rung -- the same tautology,
    # ruled to be excluded the same way) from the coverage denominator, and
    # the final track assembly below forces a `setlist-gap` track's `matched`
    # to None (= "not measured", per models.py:158-160 -- an adopted match is
    # tautological, never an independent measurement). See
    # test_adopted_tracks_report_matched_none and
    # test_missed_anchor_flags_low_confidence_once_adopted_tracks_are_excluded
    # in test_stage_gather.py for the pinned corrected behaviour.
    tracks = adopt_gap_titles(
        tracks, canonical,
        metadata_norms=metadata_norms,
        aliases=family_aliases)

    flags = []
    if overrides.set_breaks is not None or overrides.encore_after is not None:
        breaks_in = list(overrides.set_breaks or [])
        _validate_structure_override(len(tracks), breaks_in, overrides.encore_after)
        labels = _sets_from_breaks(len(tracks), breaks_in, overrides.encore_after)
        tracks = [t.model_copy(update={"set": s}) for t, s in zip(tracks, labels)]
        breaks = sorted(set(breaks_in) | ({overrides.encore_after}
                                          if overrides.encore_after is not None else set()))
        alignment = "override"
        coverage, conflicts = 1.0, []
    else:
        # family_aliases (Single-word Dead shorthand — "Scarlet", "Dew",
        # "Help" — safe only inside the Garcia universe) was computed above,
        # before the adopt_gap_titles call, and is reused here unchanged.
        result = align(tracks, canonical, aliases=family_aliases)
        alignment = "deterministic"
        # Jerrybase closers are ground truth for where breaks fall, so anchoring
        # is tried on its own evidence and wins whenever it succeeds — it is not
        # gated on the alignment looking bad. The old `coverage < threshold`
        # gate was a trap: gd1973-08-01 aligned to 0.8182 against a 0.8 gate, so
        # a show whose breaks were plainly wrong was "too good" for every repair
        # path. Measured over the 756 corpus shows carrying evidence: +148 newly
        # anchor and not one show that already anchored changes.
        anchored = (jerrybase.anchor_breaks(tracks, event, aligned_sets=result.sets)
                    if event is not None else None)
        if anchored is not None:
            # Record what anchoring overrode. Anchoring now wins on
            # high-coverage shows AND suppresses the closer tripwire when it
            # does, so without this a mis-anchor would leave no trace anywhere.
            was = _breaks_of(result.sets)
            result = result.model_copy(update={"sets": anchored})
            alignment = "jerrybase"
            note = "set breaks anchored from jerrybase"
            if was != _breaks_of(anchored):
                note += f" (was {was})"
            notes.append(note)
        elif canonical.items and result.coverage < structure_cfg.align_coverage_threshold:
            # No usable jerrybase evidence and the alignment is weak: fall back
            # to LLM realignment, then to a review flag.
            llm_result = None
            if align_provider is not None:
                try:
                    resp = run_json_task(align_provider, "align_structure", AlignedStructure,
                                         template=load_prompt("align_structure"),
                                         tracks=_format_tracks(tracks),
                                         setlist=_format_setlist(canonical))
                    llm_result = apply_llm_alignment(tracks, resp)
                except (TaskFailed, HerderError) as err:
                    log.warning("align_structure failed: %s", err)
            if llm_result is not None and llm_result.coverage >= structure_cfg.align_coverage_threshold:
                # Deliberate trade-off: apply_llm_alignment never populates
                # conflicts, so any deterministic-alignment conflicts are
                # dropped when the LLM realignment wins.
                result, alignment = llm_result, "llm"
            else:
                flags.append("low-confidence structure alignment")

        # A track whose title_source is in TAUTOLOGICAL_TITLE_SOURCES
        # ("setlist-gap" AND the whole-tape "setlist" rung) carries the
        # canonical item's own text, so align()'s match on it is tautological
        # (see _songish_coverage's docstring) -- honesty requires overriding
        # `m` to None here rather than recording align()'s True.
        # `matched=None` already means "not measured" per models.py:158-160,
        # and this IS an unmeasured track: nothing independent was ever
        # checked against it. Round 2 (review): this must test membership in
        # the SAME constant _songish_coverage filters on, not name one
        # source -- the two signals describe the same fact, and a literal
        # here let them drift apart (a "setlist"-sourced track was excluded
        # from coverage as tautological while still reporting matched=True,
        # the same models.py:158-160 violation the whole ruling exists to
        # prevent, just on the other rung).
        tracks = [t.model_copy(update={
            "set": s, "segue": g,
            "matched": None if t.title_source in TAUTOLOGICAL_TITLE_SOURCES else m})
                  for t, s, g, m in zip(tracks, result.sets, result.segues, result.matched)]
        breaks = set_breaks(tracks)
        coverage, conflicts = result.coverage, result.conflicts
        # merge_conflicts has three different lifecycles, same exposure as
        # the `conflicts` trade-off noted above: it SURVIVES jerrybase
        # anchoring via the `model_copy` above (anchoring only replaces
        # `sets`) - but anchoring can then replace the very breaks a flagged
        # track was said to span, so the flag can end up naming a track whose
        # final labels are actually consistent; it is SILENTLY DROPPED when
        # LLM realignment wins, because `apply_llm_alignment` never
        # populates it; and it is never computed at all on the override
        # branch. Left as-is - whether an anchoring-overridden flag should
        # still fire is a later call, not this one's.
        if result.merge_conflicts:
            nums = ", ".join(str(n) for n in result.merge_conflicts)
            flags.append(f"merged track(s) {nums} span a set break")

    # Multi-event handling. Held grouping catch-alls flag directly; an
    # unpartitioned multi-event date keeps the blanket flag (defensive); a
    # per-event candidate whose aligned tracks span >1 event was mislabeled.
    if kind == "spans":
        flags.append(f"tape spans {len(events)} events")
    elif kind == "unassigned":
        flags.append("unassigned multi-event recordings")
    elif kind is None and len(events) > 1:
        venue_list = ", ".join(sorted({e.venue for e in events}))
        flags.append(f"multi-event date: {len(events)} jerrybase events at {venue_list}")
    elif kind == "event" and len(events) > 1:
        spanned = sum(
            1 for ev in events
            if any(norm_title(t.title) == norm_title(s.closer)
                   for s in ev.sets for t in tracks)
        )
        if spanned > 1:
            flags.append(f"tape spans {len(events)} events")

    # Venue enrichment + cross-check (single-event only; never overwrite a venue).
    venue, city, venue_source = candidate.venue, candidate.city, "item"
    if event is not None:
        if not (venue and venue.strip()):
            venue, city, venue_source = event.venue, event.city, "jerrybase"
        elif not venues_equivalent(venue, event.venue):
            flags.append(f"venue mismatch: archive '{venue}' vs jerrybase '{event.venue}'")

    if overrides.venue is not None:
        venue, venue_source = overrides.venue, "override"
        flags = [f for f in flags if not f.startswith("venue mismatch")]
    if overrides.city is not None:
        city = overrides.city

    # Closer tripwire (single-event, non-anchored alignments; anchoring places
    # breaks at closers by construction, so it cannot contradict itself).
    if event is not None and alignment != "jerrybase":
        hard, soft = jerrybase.closer_contradictions(tracks, event)
        flags += hard
        notes += soft

    # Count numbered sets only — an encore is a coda, not a set, and jerrybase
    # often records only the numbered sets, so counting it would spuriously
    # disagree with a tape that labels a trailing encore (or vice-versa).
    expected_sets = (len({s.name for s in event.sets if s.name != "encore"})
                     if event is not None else None)
    guard = structure_guard(tracks, breaks,
                            evidence_sets={i.set for i in canonical.items},
                            min_minutes=structure_cfg.guard_min_minutes,
                            expected_set_count=expected_sets)
    if guard:
        flags.append(guard)

    if any(t.title_source == "unresolved" for t in tracks):
        flags.append("unresolved track titles")
    if canonical.confidence == "low":
        flags.append("low-confidence setlist")
    if not tracks:
        flags.append("no playable tracks")

    structure_info = None
    if overrides.set_breaks is not None or overrides.encore_after is not None:
        structure_info = StructureInfo(source="override", alignment="override",
                                       coverage=1.0, conflicts=[])
    elif canonical_source is not None or notes:
        source = canonical_source if canonical_source is not None else "none"
        structure_info = StructureInfo(source=source, alignment=alignment,
                                       coverage=coverage,
                                       conflicts=conflicts + notes)

    date, date_source, item_date = candidate.date, "item", None
    if overrides.date is not None:
        date, date_source, item_date = overrides.date, "override", candidate.date

    show = Show(
        performance_id=candidate.performance_id,
        identifier=identifier,
        artist=artist,
        date=date,
        date_source=date_source,
        item_date=item_date,
        venue=venue,
        city=city,
        venue_source=venue_source,
        tracks=tracks,
        set_breaks=breaks,
        excluded_files=excluded,
        order_source=ordering["order_source"],
        reordered=ordering["reordered"],
        lineage=meta.get("lineage") or meta.get("source"),
        source_url=f"https://archive.org/details/{identifier}",
        needs_review=bool(flags),
        review_flags=flags,
        structure=structure_info,
    )
    write_artifact(show_ws.show, show)
    write_artifact(show_ws.reviews, md.get("reviews", []))
    return show
