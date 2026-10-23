import datetime
import logging
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import NamedTuple

from herder import HerderError, TaskFailed, run_json_task
from herder.limits import RateLimited
from llama import desc_list, jerrybase, taper, title_hygiene
from llama.config import StructureConfig
from llama.errors import LlamaError
from llama.junk import FORMAT_BY_AUDIO, LOSSLESS_TITLE_FORMATS, filter_files
from llama.ia_client import IAError
from llama.desc_list import DescRead, drop_leading_artist_items, read_desc_list
from llama.lossless_titles import (SHIFTED_DELIVERED_NOTE, LosslessResult, apply_lossless,
                                   demoted_note)
from llama.title_cosmetics import cosmetic_strip
from llama.title_hygiene import DDecision, SetlistPlan
from llama.models import (AlignedStructure, JerrybaseEvent, Candidate, Overrides, ParsedSetlist,
                          SetlistItem, Show, ShowNotes, SourcedParse, StructureInfo, Track)
from llama.prompts import load_prompt
from llama.setlist import parse_setlist
from llama.siblings import DonorTape, SiblingRow, cplus_filter, propose_rows, rate_alignment
from llama.songs import GD_SHORTHAND, normalize_song
from llama.structure import (TAUTOLOGICAL_TITLE_SOURCES, adopt_gap_titles, align,
                             apply_llm_alignment, blend_segues, cities_compatible, encore_lost,
                             from_setlistfm,
                             fuzzy_norm_title, fuzzy_title_eq, is_filler, norm_title, rank_parses,
                             structure_guard, venues_equivalent,
                             _venues_equivalent_pre1b)
from llama.placeholders import is_junk_tag
from llama.taper import TaperDecision
from llama.titles import (_GLUED_NUM_PREFIX, _JOINED_NUM_PREFIX, clean_tag_title, clean_tag_titles,
                          is_real_title, placeholder_positions, resolve_titles, set_breaks, sibling_format_titles, shipped_short_tag, tag_core,
                          tag_layer, title_fraction, TagLayer)
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


_CLOSER_FLAG = re.compile(r"^jerrybase set closer '(.*)' is not at a set break$")


def demote_jerrybase_flags(hard: list[str], count_flag: str | None,
                           event: JerrybaseEvent, taper: "taper.TaperText",
                           aliases: dict[str, str] | None = None
                           ) -> tuple[list[str], str | None, list[str]]:
    """(kept hard flags, kept count flag, op notes). On a taper-owned show a
    jerrybase disagreement with the taper's OWN text is an operator note, not a
    hold (spec 2026-10-22-taper-set-markers section 5). Jerrybase numbered set k
    maps to the taper's set k and its `encore` to the taper's encore; a closer
    flag is demoted when the taper has no such set or its last song there
    differs from jerrybase's closer, and otherwise stays hard (it then catches
    llama's placement, not the taper's text). The set-count flag is demoted
    when the taper's numbered set count differs from jerrybase's."""
    notes: list[str] = []
    kept_count = count_flag
    if count_flag is not None:
        taper_n = len({i.set for i in taper.items if i.set != "encore"})
        jb_n = len({s.name for s in event.sets if s.name != "encore"})
        if taper_n != jb_n:
            notes.append(f"{count_flag} (taper's markers)")
            kept_count = None
    kept: list[str] = []
    used: set[int] = set()
    for flag in hard:
        m = _CLOSER_FLAG.match(flag)
        k = next((n for n, st in enumerate(event.sets)
                  if n not in used and m is not None and st.closer == m.group(1)), None)
        if k is None:
            kept.append(flag)
            continue
        used.add(k)
        st = event.sets[k]
        songs = [i.title for i in taper.items if i.set == st.name]
        agrees = bool(songs) and fuzzy_title_eq(fuzzy_norm_title(songs[-1], aliases),
                                                fuzzy_norm_title(st.closer, aliases))
        if agrees:
            kept.append(flag)
        else:
            notes.append(f"jerrybase set closer '{st.closer}' is not at a set break "
                         f"(taper's markers)")
    return kept, kept_count, notes


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


def _dedupe_ordered(items: list[str]) -> list[str]:
    """Drop repeated entries, keeping the FIRST occurrence's position.

    `StructureInfo.conflicts` is read straight into the briefing LLM prompt
    (`show.model_dump_json()`, `stages/brief.py:138`) and its sequence
    carries meaning, so a plain `set()` (or `sorted(set(...))`) is wrong here
    -- it would scramble the order the rest of `run_gather` builds `flags`/
    `notes` in. This exists because `_collect_parses` (via `build_canonical`,
    always run first) and `load_donor_tapes` (via `_sibling_transfer_full`, run
    only when the sibling-align gate fires) each independently retry and
    independently catch/note the exact same `IAError` for the exact same
    donor identifier -- `IAClient` never caches a failed fetch, so nothing
    stops either from trying again and noting again. Deduping here, at the
    join, rather than by threading "already failed" state between the two
    fetchers, keeps that retry real: a transient failure that recovers on
    the second attempt still gets its chance (see the two functions' own
    docstrings for why a permanent failure note should appear only once
    regardless of which of them happens to emit it first)."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _donor_key(agreement: float | None, cost: float, identifier: str) -> tuple:
    """Sort key for picking the winning donor: highest agreement, then lowest
    DP cost, then identifier (spec order). `agreement is None` (no anchors at
    all -- `rate_alignment`'s "no-anchors" band) ranks BELOW every real
    agreement value including 0.0: 0.0 is a real, if bad, measurement (the
    tape has anchors and none of them agree), while None means no measurement
    was possible at all.

    EMERGENT SAFETY ROLE, NOT A DESIGNED ONE -- worth knowing before this
    ordering is "simplified": picking the highest-agreement donor is also
    what keeps 135 of 136 measured slide-shaped donor pairs out of the
    automatic band, since a displaced pairing scores lower agreement than a
    clean donor of the same performance and so never wins the tie-break.
    Two tests pin the ordering (a reversed sort fails in both gather and
    cli) without naming this; see
    `docs/superpowers/2026-09-02-sibling-transfer-evidence.md`, Step 9, for
    the measurement this ordering happens to protect."""
    rank = agreement if agreement is not None else -1.0
    return (-rank, cost, identifier)


def load_donor_tapes(ia, candidate: Candidate, identifier: str,
                     want: str | Sequence[str]) -> tuple[list[DonorTape], list[str]]:
    """Load every non-self recording in `candidate.recordings` as a
    `DonorTape` -- the ONE definition of "qualifying donor", shared by
    `_sibling_transfer_full` (gather's automatic pass, reached through `title_inputs`'
    `sibling_step`) and `cli._propose_titles_for_show` / triage's `[t]` (the operator
    surface, Task 6). Extracted out of the transfer pass (then `_sibling_transfer`)
    rather than reimplemented CLI-side: a second
    "which recordings count as donors" would be invisible when it drifted,
    exactly the class of duplication this module's docstrings keep warning
    about.

    A recording qualifies when: it is not `identifier` itself, its metadata
    fetches without error, `filter_files` leaves at least one kept file, and
    every kept file has a real (non-`None`) duration -- the same three
    conditions the transfer pass checked inline before this extraction.

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
    `_sibling_transfer_full` (gather's automatic pass) and
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


DonorRows = tuple[DonorTape, list[SiblingRow]]


# Off the production path since Task 16 (gather calls `_sibling_transfer_full` through
# `title_inputs`); kept for its pin test and the title-hygiene gate probe.
def _sibling_transfer(ia, candidate: Candidate, identifier: str,
                      want: str | Sequence[str], tracks: list,
                      metadata_norms: set[str]) -> tuple[list, list[str]]:
    """`_sibling_transfer_full`'s first two elements, byte-identical to before the
    split (title hygiene, Task 11). See `_sibling_transfer_full`."""
    new_tracks, notes, _ = _sibling_transfer_full(ia, candidate, identifier, want,
                                                  tracks, metadata_norms)
    return new_tracks, notes


def _sibling_transfer_full(ia, candidate: Candidate, identifier: str,
                           want: str | Sequence[str], tracks: list,
                           metadata_norms: set[str]
                           ) -> tuple[list, list[str], DonorRows | None]:
    """The guarded duration-alignment title transfer. Loads every non-self
    sibling recording, aligns each against `tracks`' own durations
    (`siblings.propose_rows`), rates the pair (`siblings.rate_alignment`),
    picks the winning donor, and -- only in the `auto` band, and only after
    running `siblings.cplus_filter` -- fills `unresolved` tracks with the
    surviving `adopt` rows, stamped `title_source="sibling-align"`.

    Returns `(tracks, notes, donor_rows)`. `donor_rows` is the winning donor's
    `(donor, rows)` from `best_donor` whatever the band, None when no donor
    qualified: title hygiene's D rung reads it for its sibling-duration check
    rather than re-running `best_donor` (Task 11). `tracks` is always a NEW list -- inputs are
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
        return list(tracks), notes, None
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
        return new_tracks, notes, (donor, rows)

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
    return new_tracks, notes, (donor, rows)


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
    # True when the `extract_setlist` LLM fallback was reached and NOT taken:
    # nothing ranked, the longest description is non-blank, and no provider
    # was passed. An empty description makes no call even with a provider,
    # so it is never needs-LLM (held-backlog spec "Slice 0").
    needs_llm: bool = False
    # The cross-source item vocabulary (held-backlog spec ruling 3; slices 2a
    # and 2b): `fuzzy_norm_title(item.title)` -> sorted sources listing it,
    # over setlist.fm and every sibling `lma:` parse, never the selected
    # recording's own description (`"chosen"`) nor a sibling whose
    # whitespace-normalised description copies it (same author), nor `"llm"`.
    # Built from the raw parses, before the cleaning pass: an item
    # vocabulary, not the canonical. Built here and nowhere else.
    corroboration: dict[str, tuple[str, ...]] = {}


def _corroboration(parses: list[SourcedParse], descriptions: list[str], chosen_desc: str,
                   setlistfm_parse: SourcedParse | None) -> dict[str, tuple[str, ...]]:
    """`CanonicalBuild.corroboration` (ruling 3). `parses`/`descriptions` are
    `_collect_parses`' parallel lists; `chosen_desc` is the selected
    recording's own description, compared whitespace-normalised so a pasted
    copy (the bobbyleerodgers-2010-01-13 shape) is recognised as the same
    author even with different spacing."""
    def ws(text: str) -> str:
        return " ".join(text.split())

    chosen_ws = ws(chosen_desc)
    eligible = [p for p, desc in zip(parses, descriptions, strict=True)
                if p.source.startswith("lma:") and ws(desc) != chosen_ws]
    if setlistfm_parse is not None:
        eligible.append(setlistfm_parse)
    vocab: dict[str, set[str]] = {}
    for p in eligible:
        for item in p.parsed.items:
            norm = fuzzy_norm_title(item.title)
            if norm:
                vocab.setdefault(norm, set()).add(p.source)
    return {norm: tuple(sorted(sources)) for norm, sources in vocab.items()}


def build_canonical(ia, candidate: Candidate, identifier: str, meta: dict,
                    kept: list[dict], artist: str, events, *,
                    setlistfm=None, provider=None) -> CanonicalBuild:
    """The cleaned canonical performance setlist: every recording's
    description, plus setlist.fm when configured, ranked pick-best, then
    head-banner-stripped, artist-item-dropped and footnote-marker-stripped.

    `provider=None` skips the `extract_setlist` LLM fallback entirely, so
    callers outside the pipeline (`llama fix --suggest-titles`) never trigger
    an LLM call. When that skip is what decided the result (the fallback
    would otherwise have run), `.needs_llm` is True.

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
    slfm_parse = None
    if setlistfm is not None:
        raw = setlistfm.setlist(artist, candidate.date,
                                venue=candidate.venue, city=candidate.city)
        converted = from_setlistfm(raw) if raw else None
        if converted is not None:
            slfm_parse = SourcedParse(source="setlist.fm", parsed=converted)
    # Before the setlist.fm insert, while `parses` is still parallel to
    # `descriptions`. The chosen description is read from `meta` directly, so
    # a selected recording missing from `candidate.recordings` still has its
    # copies recognised.
    corroboration = _corroboration(parses, descriptions, _description(meta), slfm_parse)
    if slfm_parse is not None:
        parses.insert(0, slfm_parse)

    best = rank_parses(parses, target_count=len(kept))
    needs_llm = False
    if best is None:
        longest = max(descriptions, key=len, default="")
        if longest.strip():
            if provider is not None:
                parsed = run_json_task(provider, "extract_setlist", ParsedSetlist,
                                       template=load_prompt("extract_setlist"),
                                       description=longest)
                best = SourcedParse(source="llm", parsed=parsed)
            else:
                needs_llm = True
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
    return CanonicalBuild(setlist=canonical, notes=notes, source=source,
                          needs_llm=needs_llm, corroboration=corroboration)


# Slice 2a's segue split: a core like `Ravine > J` is judged component by
# component, every one of which must be corroborated.
_SEGUE_SPLIT = re.compile(r"\s*(?:->|>)\s*")


def accept_short_tags(tracks: list[Track], tag_titles: list[str], tag_source: str, *,
                      corroboration: dict[str, tuple[str, ...]],
                      metadata_norms: set[str],
                      demoted: frozenset[int],
                      tag_sources: Sequence[str] | None = None) -> tuple[list[Track], list[str]]:
    """Held-backlog slice 2a (spec "2a. Corroborated short tags"; ruling 2:
    a NEW predicate beside `is_real_title`, which is untouched).

    Fills only tracks still `unresolved`, so it never pre-empts an earlier
    rung (a `setlist-gap` title stays) and never touches an `override`. A
    track's tag-layer text (`tag_titles[i]`, the layer `resolve_titles` used)
    is judged only when it is non-empty and FAILS `is_real_title` -- a
    2b-demoted `tmp` passes it and is never re-accepted here. Nor is ANY
    position in `demoted` (0-based, 2b's `placeholder_positions` minus
    overrides): 2b judges the whole tag and 2a its segue components, so a
    `J > J` x 3 tape is recording-level junk to 2b (`j j` is no item) yet
    corroborated per component; spec 2b leaves such a track to setlist-gap and
    sibling-align only. Required, not defaulted, so no caller can forget it.
    Its core
    (`titles.tag_core`) is accepted when all hold:

    - it contains an alphanumeric character (a `?`-only core never qualifies);
    - it passes 2a's junk veto (`placeholders.is_junk_tag`), no exemption;
    - every segue component equals, by `fuzzy_norm_title`, an item of a
      cross-source parse (`corroboration`: setlist.fm or a sibling
      description, never the selected recording's own -- ruling 3);
    - the whole core is not in `metadata_norms`.

    An accepted track ships `titles.shipped_short_tag(tag)` (taper markers
    off, plus Task 11b's cosmetics: `M80,`, `E: 2x2`, `42(1)`) with
    `title_source=tag_source` (`tags`, or `sibling-format` when format
    recovery fired); `matched` is untouched. Returns a NEW list and one
    operator note per accepted track (Contracts id 2a; notes.json only).

    `tag_sources` (title hygiene, slice 3: the tag layer may mix sources per track)
    stamps each accepted track with its own source; None, the default, stamps
    `tag_source` on every track, exactly as before."""
    out = list(tracks)
    notes: list[str] = []
    for i, t in enumerate(tracks):
        if t.title_source != "unresolved" or i in demoted or i >= len(tag_titles):
            continue
        tag = tag_titles[i]
        if not tag.strip() or is_real_title(tag):
            continue
        core = tag_core(tag)
        if not any(ch.isalnum() for ch in core) or is_junk_tag(core):
            continue
        parts = [c for c in _SEGUE_SPLIT.split(core) if c]
        keys = [fuzzy_norm_title(c) for c in parts]
        if not parts or not all(k in corroboration for k in keys):
            continue
        if fuzzy_norm_title(core) in metadata_norms:
            continue
        title = shipped_short_tag(tag)
        source = tag_source if tag_sources is None else tag_sources[i]
        out[i] = t.model_copy(update={"title": title, "title_source": source})
        sources = sorted({src for k in keys for src in corroboration[k]})
        notes.append(f"accepted short tag title: track {t.index} '{title}' "
                     f"corroborated by {', '.join(sources)}")
    return out, notes


# ---- Title hygiene (piece 3): the unwired builder and orchestrator -----------------------
#
# Spec `docs/superpowers/specs/2026-10-22-title-hygiene-design.md`; plan Task 11.
# `title_inputs` is `compute_gather`'s title prelude (filter, include/exclude handling,
# recovery, the canonical, metadata norms, the tag-gate basis, corroboration) plus the
# description lists and the two sibling closures; `title_cascade` is its title block (tag
# layer through 2a) with the new slices placed where the spec puts them, each behind
# `enabled`. With `enabled=frozenset()` the cascade reproduces the pre-piece-3 title block
# exactly (gate 0, measured on the whole library before wiring). `compute_gather` calls
# both (Task 16); they are the only copy of the prelude and the title block.


def gather_cleaner(metadata_norms: set[str], artist: str) -> desc_list.Cleaner:
    """Reader (ii)'s cleaner (spec slice 2 (ii)): `build_canonical`'s cleaning with one
    difference. `_strip_head_banner`, then `drop_leading_artist_items` (artist items in the
    leading run only, never mid-list: a self-titled song stays), then
    `_strip_footnote_markers`. Returns `(cleaned, removed_indices)`: the indices (into the
    INPUT items) the first two removed. Both remove a leading run, so the indices are a
    prefix. The footnote strip rewrites titles and removes nothing, so it reports nothing."""
    def clean(parsed: ParsedSetlist) -> tuple[ParsedSetlist, frozenset[int]]:
        banner = _strip_head_banner(parsed, metadata_norms)
        dropped = drop_leading_artist_items(banner, artist)
        removed = len(parsed.items) - len(dropped.items)
        return _strip_footnote_markers(dropped), frozenset(range(removed))
    return clean


@dataclass(frozen=True)
class TitleInputs:
    """Everything the title cascade reads, computed once by `title_inputs`."""
    kept: list[dict]
    excluded: list[dict]
    files: list[dict]                    # the item's whole file list (slice 3's lossless lookup)
    ordering: dict
    recovery_basis: list[dict]
    tag_gate_basis: list[dict]
    format_titles: dict[str, str] | None
    overrides: Overrides
    cb: CanonicalBuild
    corroboration: frozenset[str]
    item_title: str | None
    metadata_norms: set[str]
    family_aliases: dict[str, str]
    desc: DescRead
    sibling_step: Callable[[list[Track]], tuple[list[Track], list[str], DonorRows | None]]
    donor_check: Callable[[list[Track]], DonorRows | None]


def title_inputs(md: dict, overrides: Overrides, *, ia, candidate: Candidate, identifier: str,
                 artist: str, want: Sequence[str], events: list,
                 build: Callable[[list[dict]], CanonicalBuild]) -> TitleInputs:
    """`compute_gather`'s title prelude, as one builder (its only copy). It does
    no IO of its own: the canonical comes through `build` (the caller binds
    `build_canonical`), called once on the post-exclusion `kept`, and the two closures
    fetch only when the cascade calls them. `sibling_step` is `_sibling_transfer_full`
    bound to the show; `donor_check` is `best_donor` bound to the show, returning
    `(donor, rows)` or None (never raising: a target without durations has no donor)."""
    meta = md.get("metadata", {})
    files = md.get("files", [])
    kept, excluded, ordering = filter_files(
        files, want_format=want, readmit=frozenset(overrides.include))
    for missing in sorted(set(overrides.include) - {f["name"] for f in kept}):
        log.warning("overrides.include entry %r matched no file", missing)
    # Computed on the unexcluded set, deliberately: it is a filename-keyed map
    # and resolve_titles only looks up names still in `kept`, so covering files
    # the operator later drops is harmless, while moving it below the exclusion
    # would let one dropped file change whether recovery fires at all.
    #
    # The guarantee is now SYMMETRIC, and `recovery_basis` is what makes it so.
    # `kept` is post-re-admission, but `_recover_format_titles` and
    # `sibling_format_titles` judge the whole RECORDING rather than the
    # individual file -- the mp3-side title_fraction gate, and the exact-count
    # bijection against the lossless sibling's own kept set. Left on `kept`,
    # one re-admitted file flipped title recovery for every track on the tape:
    # a file with no lossless counterpart breaks the bijection and turns OFF
    # recovery the other tracks would have had, and an untagged one pushes the
    # mp3-side fraction below the gate and turns it ON. Measured on the gd73
    # fixture, both directions (7-vs-6 bijection; 0.43 against a 0.50 gate).
    #
    # An operator saying "keep this one track" must not change where a
    # DIFFERENT track's title came from, so recording-level decisions vote on
    # the tape minus re-admissions. Note what that costs the re-admitted file
    # HERE: `sibling_format_titles` keys its map off the basis, so the file is
    # absent from it and falls through to the ordinary cascade -- no vote AND
    # no recovered title. (The other gate differs: the enumerated-tape strip
    # applies to every kept file, so there the re-admitted file loses only the
    # vote.) This is the same rule as the exclusion guard above, in the other
    # direction.
    #
    # TWO recording-level consumers are deliberately NOT carved out, both
    # because the re-admission genuinely changes the question they ask:
    # `fetch_siblings` in `title_cascade` (a re-admitted untagged file really
    # does mean the tape is no longer fully tagged, and its only adoption
    # target is that file), and `build_canonical`'s `target_count=len(kept)`
    # (the tape really does have one more track, though a +/-1 shift there can
    # change which description wins `rank_parses` and so the whole tape's set
    # labels).
    # Filter on what filter_files ACTUALLY re-admitted, never on the raw
    # `overrides.include` request. An entry naming a file that was never
    # dropped re-admits nothing, but filtering on the request would still
    # strip that already-kept file of its vote -- re-entering this very bug
    # through the front door, and silently, since the "matched no file"
    # warning above cannot fire for a name that IS in `kept`.
    readmitted = set(ordering.get("readmitted", ()))
    recovery_basis = [f for f in kept if f["name"] not in readmitted]
    format_titles = _recover_format_titles(files, recovery_basis, ordering)

    # Re-admission was applied inside the filter above (where play order is
    # derived); the exclusion runs AFTER it, so a file named in both lists
    # ends up excluded.
    if overrides.exclude:
        drop = set(overrides.exclude)
        matched = {f["name"] for f in kept if f["name"] in drop}
        for missing in sorted(drop - matched):
            log.warning("overrides.exclude entry %r matched no file", missing)
        for both in sorted(set(overrides.include) & drop):
            log.warning("overrides: %r is in both include and exclude; "
                        "exclude wins", both)
        excluded += [{"filename": f["name"], "reasons": ["operator-excluded"],
                      "duration_sec": length_seconds(f.get("length"))}
                     for f in kept if f["name"] in drop]
        kept = [f for f in kept if f["name"] not in drop]

    # Canonical performance setlist (`build` is `build_canonical` in gather):
    # every recording's description, plus setlist.fm when configured, ranked
    # pick-best, then cleaned (head-banner stripped, artist-only items dropped)
    # at the point it enters the stage, before anything consumes it --
    # `resolve_titles` only trusts the setlist when `len(items) == len(tracks)`,
    # so on an untagged tape one header item costs every title on the show.
    # `.source` (the winning parse's provenance) is `StructureInfo.source`.
    cb = build(kept)
    # Recomputed (not re-fetched) rather than threaded out of build_canonical:
    # it's a pure function of already-in-scope values, and adopt_gap_titles
    # needs it independently of the canonical-setlist build.
    metadata_norms = show_metadata_norms(artist, candidate, meta, events)
    # The same one-file-must-not-decide-for-the-recording rule as
    # `recovery_basis` above, applied to the OTHER recording-level gate:
    # clean_tag_titles' enumerated-tape test, which decides whether a leading
    # track number is stripped from EVERY title. Computed here rather than
    # reusing `recovery_basis` -- that one is deliberately PRE-exclusion (see
    # the guard above it), while this gate must vote over the tracks that
    # actually ship. Reusing it let operator-excluded files vote, which is the
    # defect test_readmission_does_not_stop_the_track_number_strip caught.
    tag_gate_basis = [f for f in kept if f["name"] not in readmitted]
    # Single-word Dead shorthand ("Scarlet", "Dew", "Help") is only safe
    # inside the Garcia universe — they are ordinary English words
    # elsewhere. Non-family shows get an empty table, which makes the
    # vocabulary a provable no-op on the non-Dead corpus. Shared with
    # gather's `align()` call.
    family_aliases = GD_SHORTHAND if jerrybase.is_family_artist(artist) else {}
    desc = read_desc_list(_description(meta), len(kept), artist=artist,
                          clean=gather_cleaner(metadata_norms, artist))

    def sibling_step(tracks: list[Track]) -> tuple[list[Track], list[str], DonorRows | None]:
        return _sibling_transfer_full(ia, candidate, identifier, want, tracks, metadata_norms)

    def donor_check(tracks: list[Track]) -> DonorRows | None:
        donor, rows, _, _ = best_donor(ia, candidate, identifier, want, tracks, metadata_norms)
        return None if donor is None else (donor, rows)

    return TitleInputs(
        kept=kept, excluded=excluded, files=files, ordering=ordering,
        recovery_basis=recovery_basis, tag_gate_basis=tag_gate_basis,
        format_titles=format_titles, overrides=overrides, cb=cb,
        corroboration=frozenset(cb.corroboration), item_title=meta.get("title"),
        metadata_norms=metadata_norms, family_aliases=family_aliases, desc=desc,
        sibling_step=sibling_step, donor_check=donor_check)


@dataclass(frozen=True)
class CascadeRecord:
    """What the cascade decided, for the gate probe and the replay record. Positions are
    0-based. `lossless` is slice 3's result with any `overrides.titles` position filtered
    out (never changed, never noted); `d` is None when D did not run or returned None."""
    wholly_untagged: bool
    fetch_siblings: bool
    s_positions: tuple[int, ...]
    lossless: LosslessResult | None
    s_plan: SetlistPlan
    d: DDecision | None
    short4: tuple[int, ...]
    short4_declined: dict[int, str]
    gap_filled: tuple[int, ...]
    deferred_applied: tuple[int, ...]


@dataclass(frozen=True)
class TitleCascade:
    """`title_cascade`'s result. `tracks` are the titles before alignment; `op_notes` go to
    notes.json (never `structure.conflicts`); `struct_notes` are sibling-align's notes, which
    join `cb.notes` on today's `structure.conflicts` path; `paths` is per track `""`, `C1`,
    `C2`, `S`, `S-deferred`, `D` or `4` (fills only)."""
    tracks: list[Track]
    op_notes: list[str]
    struct_notes: list[str]
    self_filled: bool
    paths: tuple[str, ...]
    record: CascadeRecord


def _filled(before: list[Track], after: list[Track], source: str) -> tuple[int, ...]:
    return tuple(i for i, (b, a) in enumerate(zip(before, after))
                 if b.title_source != source and a.title_source == source)


def _without_override_positions(res: LosslessResult, overridden: set[int],
                                delivered: list[str], delivered_source: str) -> LosslessResult:
    """Slice 3 never touches an override (Constraints, "Ordering"): at an `overrides.titles`
    position its change, or its shifted-set demotion (C-1), is undone, uncounted and
    unnoted (the override replaces the title anyway, so a note there would be false)."""
    hit = {i for i in res.changed if i in overridden}
    hit_demoted = {i for i in res.demoted if i in overridden}
    if not hit and not hit_demoted:
        return res
    titles, sources = list(res.titles), list(res.sources)
    for i in hit | hit_demoted:
        titles[i], sources[i] = delivered[i], delivered_source
    demoted = tuple(i for i in res.demoted if i not in hit_demoted)
    prefixes = tuple(f"lossless title: track {i + 1} '" for i in hit)
    notes = [n for n in res.notes
             if not (prefixes and n.startswith(prefixes))
             and not n.startswith(SHIFTED_DELIVERED_NOTE)]
    if demoted:
        notes.append(demoted_note(demoted))
    return replace(res, titles=titles, sources=sources,
                   changed={i: c for i, c in res.changed.items() if i not in hit},
                   notes=tuple(notes), demoted=demoted)


def title_cascade(inp: TitleInputs, *,
                  enabled: frozenset[str] = title_hygiene.ENABLED_SLICES) -> TitleCascade:
    """Today's title block (tag layer through 2a), with the new slices at their places
    (spec: slice 1 placement, slice 2 "When it fires", slice 3 "Placement" and "Per-track
    source", slice 4 placement, Constraints "Ordering"). Order: tag layer -> C (slice 3)
    -> 2b on the delivered layer minus C-changed (notes minus overrides) -> 2c/2d notes
    skipping C-changed -> `fetch_siblings` -> the format-sibling note (not when C acted)
    -> wholly untagged -> the S plan (slice 1) -> `resolve_titles` -> overrides ->
    sibling-align -> setlist-gap (S-declined positions bind it) -> 2a -> slice 4 -> D
    (slice 2) -> the deferred S fill. No rung overwrites a resolved track or an override.
    With `enabled=frozenset()` the result is exactly today's."""
    s1, s2, s3, s4 = (f"slice{k}" in enabled for k in (1, 2, 3, 4))
    kept, overrides, cb = inp.kept, inp.overrides, inp.cb
    canonical = cb.setlist
    n = len(kept)
    overridden = {k - 1 for k in overrides.titles}
    op_notes: list[str] = []
    struct_notes: list[str] = []

    # The delivered tag layer, then slice 3 (C) per track on top of it.
    delivered, delivered_source = tag_layer(kept, inp.format_titles, inp.tag_gate_basis)
    titles, sources = list(delivered), [delivered_source] * n
    lossless = None
    if s3:
        in_scope = (inp.format_titles is None
                    and title_fraction(clean_tag_titles(inp.recovery_basis)) >= _RECOVER_BELOW)
        lossless = _without_override_positions(
            apply_lossless(kept, delivered, delivered_source, in_scope=in_scope,
                           files=inp.files, ordering=inp.ordering,
                           recovery_basis=inp.recovery_basis, desc=inp.desc.used,
                           canonical=canonical, metadata_norms=inp.metadata_norms),
            overridden, delivered, delivered_source)
        titles, sources = list(lossless.titles), list(lossless.sources)
        op_notes += lossless.notes
    c_changed = set(lossless.changed) if lossless is not None else set()
    c_demoted = set(lossless.demoted) if lossless is not None else set()

    # 2b on the delivered layer, minus the stems C changed. `layer_demoted` is what
    # resolve_titles demotes (overrides included, as today: they are overwritten anyway);
    # `demoted` drops override positions, as today's notes and 2a do.
    # Slice 2b (held-backlog spec "2b. Junk-title detector"): placeholder tags
    # demote to `unresolved` inside resolve_titles. The same positions are
    # computed here, over the same tag layer, for the notes. An override is
    # never judged (spec 2b: only `tags`/`sibling-format` titles are), so a
    # position the overrides loop below replaces gets no note and does not
    # count as demoted; resolve_titles' demotion there is overwritten anyway.
    layer_demoted = [i for i in placeholder_positions(delivered, corroboration=inp.corroboration,
                                                      item_title=inp.item_title)
                     if i not in c_changed]
    demoted = [i for i in layer_demoted if (i + 1) not in overrides.titles]
    for i in demoted:
        op_notes.append(f"placeholder tag title: track {i + 1} '{delivered[i]}' "
                        f"demoted to unresolved")
    # Slice 2c/2d: one note per title the glued/joined-prefix strip changed. Only
    # on the `tags` layer: under format recovery the tag titles are the lossless
    # sibling's, and comparing them with this mp3's own tags would note strips
    # that never happened. An overridden position is never judged (as for 2b).
    if delivered_source == "tags":
        for i, f in enumerate(kept):
            if i in c_changed or i in c_demoted:
                continue
            raw = clean_tag_title(f.get("title"))
            if (delivered[i] != raw and _GLUED_NUM_PREFIX.match(raw)
                    and (i + 1) not in overrides.titles):
                op_notes.append(f"stripped glued track number: track {i + 1} "
                                f"'{raw}' -> '{delivered[i]}'")
            if (delivered[i] != raw and _JOINED_NUM_PREFIX.match(raw)
                    and (i + 1) not in overrides.titles):
                op_notes.append(f"stripped joined track number: track {i + 1} "
                                f"'{raw}' -> '{delivered[i]}'")
    # `kept and` is load-bearing: title_fraction is 0.0 on an empty list, so an
    # exclude-everything tape would otherwise fetch every sibling recording's
    # metadata to resolve zero titles. The output was never wrong, only the
    # fetches wasted. Loosened (Task 5): the old count-mismatch/confidence
    # condition is gone -- the sibling-align pass below is guarded on its
    # own evidence (anchor agreement), not on how the canonical setlist lined
    # up, so gating the FETCH on that condition too was never doing anything
    # but adding false negatives.
    # Deliberately NO gate_basis, unlike the resolve_titles call below: this is
    # the fetch_siblings carve-out, and a re-admitted untagged file genuinely
    # does mean the tape is no longer fully tagged. Same function, same tape,
    # two different votes -- which is intended, not an oversight (whole-branch
    # review M4). The flip is only ever 1.0 -> <1.0, and at 1.0 the only
    # unresolved tracks are slice 2b's demotions (the `or demoted` arm below),
    # so otherwise the fetch's only adoption target is the re-admitted file.
    #
    # Slice 2b: `fetch_siblings` is a fetch gate, not a measured one ("never
    # wrong, only wasted"), so it is recomputed over post-detector titles: a
    # `tmp` x 19 tape has title_fraction 1.0 but nothing usable, and
    # sibling-align gets its guarded chance at the demoted tracks.
    fetch_siblings = bool(kept and (title_fraction(clean_tag_titles(kept)) < 1.0 or demoted))
    # Spec 2b: recording-level gates keep `is_real_title`, so `_RECOVER_BELOW`
    # does not move and a `tmp`-tagged mp3 does not trigger format recovery.
    # A fully-tagged lossless sibling is filed as a note, not acted on. Only
    # when recovery did NOT fire (otherwise the tag layer IS that sibling and
    # "recovery not triggered" would be false), and not when C acted.
    if demoted and inp.format_titles is None and not c_changed:
        for fmt in LOSSLESS_TITLE_FORMATS:
            if fmt == inp.ordering.get("format"):
                continue
            other, _, _ = filter_files(inp.files, want_format=fmt)
            recovered = sibling_format_titles(inp.recovery_basis, other)
            if recovered is None:
                continue
            frac = title_fraction(list(recovered.values()))
            if frac >= _RECOVER_SIBLING_ABOVE:
                op_notes.append(f"format sibling tagged: {fmt} title fraction {frac:.2f} "
                                f"(recovery not triggered; filed, not acted on)")
                break

    # Wholly untagged: once, from the tag layer after C, before resolve_titles.
    layer_demoted_set = frozenset(layer_demoted)
    untagged = title_hygiene.wholly_untagged(titles, layer_demoted_set)

    # Slice 1: where the S rung fires. `s_positions` reach today's S branch.
    tag_real = [i not in layer_demoted_set and is_real_title(titles[i]) for i in range(n)]
    s_positions = [i for i in range(n)
                   if i not in layer_demoted_set and not tag_real[i] and i not in overridden]
    plan = title_hygiene.plan_setlist_rung(
        canonical=canonical, canonical_source=cb.source, s_positions=s_positions,
        tag_titles=titles, tag_real=tag_real, filenames=[f["name"] for f in kept],
        metadata_norms=inp.metadata_norms, desc_used=inp.desc.used is not None,
        wholly_untagged=untagged, slice1=s1, slice2=s2)
    op_notes += plan.notes

    tracks = resolve_titles(kept, canonical, format_titles=inp.format_titles,
                            gate_basis=inp.tag_gate_basis, corroboration=inp.corroboration,
                            item_title=inp.item_title,
                            layer=TagLayer(titles, sources, layer_demoted_set),
                            setlist_fills=plan.fills)
    for k, forced in overrides.titles.items():
        if not (1 <= k <= len(tracks)):
            raise LlamaError(f"overrides.titles: no track {k} "
                             f"(show has {len(tracks)} tracks)")
        tracks[k - 1] = tracks[k - 1].model_copy(
            update={"title": forced, "title_source": "override"})

    # Guarded duration-alignment sibling transfer. After the overrides loop
    # (an operator-forced title can anchor the guard) and before
    # adopt_gap_titles (see that call's own comment for why ordering there
    # matters to `Track.matched`). `siblings.py` stays pure; all IO is in
    # `inp.sibling_step`.
    sibling_ran, kept_donor = False, None
    if fetch_siblings:
        tracks, sib_notes, kept_donor = inp.sibling_step(tracks)
        struct_notes += sib_notes
        sibling_ran = True

    # Fill count-forced runs of unresolved tracks between tag-verified anchors.
    # Runs here, after the overrides loop, so an operator-forced title can
    # ANCHOR a gap as well as survive it. metadata_norms is passed down
    # because structure.py must not import a stage. S's declined positions
    # bind it (slice 1, "Declines bind setlist-gap").
    #
    # An adopted title *is* the canonical item's own text, so gather's align()
    # WOULD be guaranteed to match it -- tautologically raising `coverage` and
    # flipping `Track.matched` to True for tracks that were never
    # independently matched, which could suppress the "low-confidence
    # structure alignment" flag on exactly the shows where adoption took the
    # riskiest action. RULED and DELIBERATELY CORRECTED FOR, not merely
    # accepted: `structure._songish_coverage` excludes every source in
    # `structure.TAUTOLOGICAL_TITLE_SOURCES` (`setlist-gap`, the whole-tape
    # `setlist` rung and `desc-position`) from the coverage denominator, and
    # gather's final track assembly forces such a track's `matched` to None
    # (= "not measured", per models.py). See
    # test_adopted_tracks_report_matched_none and
    # test_missed_anchor_flags_low_confidence_once_adopted_tracks_are_excluded
    # in test_stage_gather.py for the pinned corrected behaviour.
    before = tracks
    tracks = adopt_gap_titles(tracks, canonical, metadata_norms=inp.metadata_norms,
                              aliases=inp.family_aliases, declined=plan.declined)
    gap_filled = _filled(before, tracks, "setlist-gap")

    # Slice 2a (held-backlog spec "2a. Corroborated short tags"): after
    # sibling-align and setlist-gap, before alignment, so it fills only what
    # every earlier rung left `unresolved` (`Ramone & Emiglio` from
    # setlist-gap is never displaced by the tag `R&E`) and never an override
    # (M9: an `overrides.titles` position is `override` by now, so it is never
    # judged or noted). Over the same tag layer `resolve_titles` used. Its
    # notes go to notes.json only (ruling 6), never `structure.conflicts`.
    tracks, short_notes = accept_short_tags(tracks, titles, delivered_source,
                                            corroboration=cb.corroboration,
                                            metadata_norms=inp.metadata_norms,
                                            demoted=frozenset(demoted), tag_sources=sources)
    op_notes += short_notes

    short4: tuple[int, ...] = ()
    short4_declined: dict[int, str] = {}
    if s4:
        tracks, notes4, accepted, short4_declined = title_hygiene.confirm_short_tags(
            tracks, titles, sources, desc=inp.desc.used, demoted=frozenset(demoted),
            metadata_norms=inp.metadata_norms)
        short4 = tuple(accepted)
        op_notes += notes4

    d = None
    if s2 and inp.desc.used is not None:
        pre_d = tracks
        if sibling_ran:
            def donor() -> DonorRows | None:
                return kept_donor          # sibling_step's choice; never re-run best_donor
        else:
            def donor() -> DonorRows | None:
                return inp.donor_check(pre_d)
        d = title_hygiene.decide_d(tracks, inp.desc.used, tag_titles=titles,
                                   canonical=canonical, metadata_norms=inp.metadata_norms,
                                   aliases=inp.family_aliases, wholly_untagged=untagged,
                                   donor=donor)
        if d is not None:
            tracks = title_hygiene.apply_d(tracks, d)
            op_notes += title_hygiene.d_notes(d, inp.desc.used)

    before = tracks
    tracks, deferred_notes = title_hygiene.apply_deferred_setlist(
        tracks, plan, d, tag_titles=titles, metadata_norms=inp.metadata_norms)
    deferred_applied = _filled(before, tracks, "setlist")
    op_notes += deferred_notes

    record = CascadeRecord(
        wholly_untagged=untagged, fetch_siblings=fetch_siblings,
        s_positions=tuple(s_positions), lossless=lossless, s_plan=plan, d=d,
        short4=short4, short4_declined=dict(short4_declined), gap_filled=gap_filled,
        deferred_applied=deferred_applied)
    return TitleCascade(tracks=tracks, op_notes=op_notes, struct_notes=struct_notes,
                        self_filled=title_hygiene.is_self_filled(tracks, d),
                        paths=_paths(record, n), record=record)


def _paths(record: CascadeRecord, n: int) -> tuple[str, ...]:
    """Per track, which new path filled it: `C1`/`C2` (slice 3), `S` (the S rung inside
    resolve_titles), `4` (slice 4), `D` (slice 2), `S-deferred`; `""` otherwise. Each
    position is filled by at most one of them (no rung overwrites a resolved track)."""
    paths = [""] * n
    if record.lossless is not None:
        for i, c in record.lossless.changed.items():
            paths[i] = c
    for i in record.s_plan.fills:
        paths[i] = "S"
    for i in record.short4:
        paths[i] = "4"
    if record.d is not None:
        for i in record.d.fills:
            paths[i] = "D"
    for i in record.deferred_applied:
        paths[i] = "S-deferred"
    return tuple(paths)


class GatherResult(NamedTuple):
    """`compute_gather`'s result: everything gather derives, nothing written.

    `notes` are operator-facing notes bound for `notes.json` (spec ruling 6:
    never `show.json`, never `structure.conflicts`, so never an LLM's input).
    `needs_llm` names each LLM touchpoint gather reached but could not take
    for want of a provider -- `"extract_setlist"`, `"align_structure"`, each
    at most once, in that order. Empty when providers were passed: with
    providers gather behaves exactly as it always has.

    The last three fields are in-process only, never persisted (held-backlog
    piece 2, spec 2026-10-22-taper-set-markers sections 4 and 7):
    `taper_owned` is True when the taper's own markers own the shipped
    structure (the one predicate `replay` may key on); `taper` is the
    `decide_taper` result, None on the structure-override path; and
    `step1_alignment` is today's mechanism before the taper step
    (`deterministic`/`jerrybase`), None on the override path.

    Title hygiene (piece 3), also in-process only: `self_filled` is
    `title_cascade`'s self-filled predicate (spec slice 2, "Self-filled
    tapes"); `title_paths` is per track which new path filled it (`""`, `C1`,
    `C2`, `S`, `S-deferred`, `D`, `4`); `title_record` is the cascade's
    `CascadeRecord` (fills and declines)."""
    show: Show
    reviews: list[dict]
    notes: list[str]
    needs_llm: tuple[str, ...]
    taper_owned: bool = False
    taper: TaperDecision | None = None
    step1_alignment: str | None = None
    self_filled: bool = False
    title_paths: tuple[str, ...] = ()
    title_record: CascadeRecord | None = None


# Slice 1 1d's hold (Contracts "Exact note and flag strings"); an operator
# venue or city override removes it.
_CITY_CONFLICT_FLAG = "recordings of this date disagree on city"


def _stripped(s: str | None) -> str | None:
    return (s or "").strip() or None


def venue_tie_break(candidate: Candidate, sel) -> tuple[str, str | None] | None:
    """Slice B: on a tied grouping vote the selected recording's own stripped
    venue ships. Raw strings are counted as `grouping._make_candidate` counts
    them. It applies only when the two strings are `venues_equivalent` (one name,
    spelled or phrased two ways); different names ship the vote (measured
    2026-10-21: the selected string was no better). Returns `(venue, city)`,
    or None when the tie-break does not apply."""
    if sel is None or not _stripped(sel.venue):
        return None
    counts = Counter(r.venue for r in candidate.recordings if r.venue)
    n = counts.get(sel.venue, 0)
    if n == 0 or n != counts.get(candidate.venue, 0) or sel.venue == candidate.venue:
        return None
    if not venues_equivalent(_stripped(sel.venue), candidate.venue):
        return None
    sel_city = _stripped(sel.coverage)
    if sel_city is not None and not cities_compatible(sel_city, candidate.city):
        return None
    return _stripped(sel.venue), sel_city or candidate.city


def jerrybase_city(event) -> str:
    """A jerrybase event's place as one "City, State" string, the shape
    `cities_compatible` compares (spec Slice 1, "City compatibility")."""
    return f"{event.city}, {event.state}" if event.state else event.city


def two_venue_signature(candidate: Candidate) -> bool:
    """True when two of the candidate's recordings name venues that are not
    equivalent in one (compatible) city: the same-city two-performance shape
    of `gratefuldead-1978-11-17` (spec Slice 1, step 2). It also fires on two
    spellings of one hall, which keeps that show held -- the safe error. A
    recording without a city of its own takes the candidate's."""
    recs = [(v, _stripped(r.coverage) or candidate.city)
            for r in candidate.recordings if (v := _stripped(r.venue))]
    return any(not venues_equivalent(va, vb) and cities_compatible(ca, cb)
               for i, (va, ca) in enumerate(recs) for vb, cb in recs[i + 1:])


def compute_gather(
    show_ws: ShowWorkspace,
    ia,
    provider,
    candidate: Candidate,
    identifier: str,
    *,
    audio_format: str = "mp3",
    align_provider=None,
    setlistfm=None,
    structure_cfg: StructureConfig | None = None,
    jerrybase_enabled: bool = False,
    enabled_slices: frozenset[str] = title_hygiene.ENABLED_SLICES,
) -> GatherResult:
    """Gather without the writes: `run_gather` minus `should_run` and the
    three artifacts. Reads `overrides.json` from `show_ws` and nothing else
    from it, so an offline replay can point it at a scratch workspace holding
    only a copy of the overrides. With `provider`/`align_provider` None, the
    LLM touchpoints are recorded in `.needs_llm` instead of called; the
    degraded result (e.g. the `low-confidence structure alignment` flag) is
    exactly what `run_gather` would have written with no provider.

    `enabled_slices` is the set of title-hygiene slices `title_cascade` runs
    (default `title_hygiene.ENABLED_SLICES`); `frozenset()` is the title block
    as it stood before piece 3. `run_gather` never passes it; harnesses do."""
    structure_cfg = structure_cfg or StructureConfig()
    # Operator-facing notes for notes.json are `op_notes` below, deliberately a
    # SEPARATE list from the local `notes`, which keeps flowing into
    # `structure.conflicts` (and so to the briefing LLM) exactly as before
    # (spec ruling 6).
    needs_align = False

    md = ia.metadata(identifier)
    meta = md.get("metadata", {})
    artist = str(_creator(meta) or candidate.collection)
    want = FORMAT_BY_AUDIO[audio_format]
    # read_overrides is hoisted above filter_files (it only reads the show dir)
    # so operator re-admission can be applied inside the filter, where play
    # order is derived (`title_inputs`).
    overrides = read_overrides(show_ws)

    # Jerrybase structure evidence (no-op for artists absent from the dataset).
    # A per-event candidate (/eN) selects events[N-1] for every evidence check.
    # Resolved HERE, above the title prelude below, because `build_canonical`'s
    # head-banner guard and `show_metadata_norms` read the event venues as part
    # of this show's own metadata; nothing in this block reads a track or the
    # canonical setlist.
    events = jerrybase.lookup(artist, candidate.date) if jerrybase_enabled else []
    # `ev_n`, not `n`: a bare `n` here was once rebound by a later loop's
    # `for n, forced in ...`; the distinct name keeps the guarantee explicit.
    kind, ev_n = _event_kind(candidate.performance_id)
    if kind == "event" and events and 1 <= ev_n <= len(events):
        event = events[ev_n - 1]
    elif kind == "event":
        event = None
    elif len(events) == 1:
        event = events[0]
    else:
        event = None

    # Titles (title hygiene, piece 3; spec 2026-10-22-title-hygiene-design).
    # `title_inputs` is the prelude: filter, include/exclude, format recovery,
    # the canonical setlist, metadata norms, the tag-gate basis and the
    # selected description's list. Its one IO is the canonical, built here
    # through `build_canonical` with this call's providers (every recording's
    # description, plus setlist.fm when configured, ranked pick-best, then
    # cleaned). `title_cascade` is the title block, tag layer through 2a with
    # the new slices at their places; `enabled_slices` picks which run.
    # The comments at each step live in those two functions.
    def build(kept: list[dict]) -> CanonicalBuild:
        return build_canonical(ia, candidate, identifier, meta, kept, artist, events,
                               setlistfm=setlistfm, provider=provider)

    inp = title_inputs(md, overrides, ia=ia, candidate=candidate, identifier=identifier,
                       artist=artist, want=want, events=events, build=build)
    cascade = title_cascade(inp, enabled=enabled_slices)
    excluded, ordering, cb = inp.excluded, inp.ordering, inp.cb
    canonical, canonical_source = cb.setlist, cb.source
    family_aliases = inp.family_aliases
    tracks = cascade.tracks
    # The cascade's operator notes are the first entries of `op_notes`; its
    # sibling-align notes follow the canonical's notes in `notes`, today's
    # order. A new list: `cb.notes` itself is never extended.
    op_notes: list[str] = list(cascade.op_notes)
    notes = cb.notes + cascade.struct_notes

    flags = []
    # The taper step's outputs; the structure-override path never runs it.
    taper_owned, decision, step1_alignment = False, None, None
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
        anchor_note = None
        if anchored is not None:
            # Record what anchoring overrode. Anchoring now wins on
            # high-coverage shows AND suppresses the closer tripwire when it
            # does, so without this a mis-anchor would leave no trace anywhere.
            was = _breaks_of(result.sets)
            result = result.model_copy(update={"sets": anchored})
            alignment = "jerrybase"
            anchor_note = "set breaks anchored from jerrybase"
            if was != _breaks_of(anchored):
                anchor_note += f" (was {was})"

        # Held-backlog piece 2 (spec 2026-10-22-taper-set-markers section 4):
        # the alignment and anchoring above are STEP 1, today's structure and
        # the reference for every "was" note. Step 2 reads the taper's own
        # set/encore markers and places them exactly; when every boundary
        # places, the taper owns the structure and exactly its labels ship
        # (no merge with step 1). Called through the module so tests can
        # patch `llama.taper.decide_taper`. `today_sets` must be parallel to
        # `tracks`: `decide_taper` silently ignores a short list, and the
        # keep-today's-encore veto reads it.
        step1_alignment = alignment
        step1_sets = list(result.sets)
        assert len(step1_sets) == len(tracks), "step-1 labels must be parallel to tracks"
        threshold = structure_cfg.align_coverage_threshold
        # THE "today's path would reach the LLM branch" predicate, computed once:
        # canonical items, no jerrybase anchoring, step-1 coverage under the
        # threshold. It decides the not-owned LLM branch below, the owned show's
        # low-confidence flag, and ruling (d)'s no-encore veto inside
        # `decide_taper` (llama-db reading of operator ruling (d), 2026-10-22:
        # with no taper encore marker on that path, the taper owns nothing).
        today_llm = bool(canonical.items) and anchored is None and result.coverage < threshold
        decision = taper.decide_taper(tracks, meta, aliases=family_aliases,
                                      today_sets=step1_sets, today_reaches_llm=today_llm)
        taper_owned = decision.placement is not None
        shipped_sets = None
        if taper_owned:
            # Step 3. No `align_structure` call, as successful anchoring skips
            # it today. The anchoring note is dropped (it would reach the
            # briefing contradicting the shipped labels). Coverage is the
            # reader's items aligned against the tape, and it is what
            # `StructureInfo.coverage` records. The low-confidence flag is
            # raised only where today's path would have reached the LLM branch
            # (canonical items, no anchoring, step-1 coverage under the
            # threshold) AND the reader's coverage is under it too.
            reader = ParsedSetlist(items=[
                SetlistItem(title=i.title, normalized=normalize_song(i.title), set=i.set)
                for i in decision.taper.items])
            reader_coverage = align(tracks, reader, aliases=family_aliases).coverage
            if today_llm and reader_coverage < threshold:
                flags.append("low-confidence structure alignment")
            shipped_sets = list(decision.placement.sets)
            # `alignment` becomes "taper" only when the taper's labels differ
            # from step 1's at song level (filler excluded); a label rename at
            # the same positions counts, so the note cites labels too.
            if any(new != old for t, new, old in zip(tracks, shipped_sets, step1_sets)
                   if not is_filler(t.title)):
                alignment = "taper"
                op_notes.append(f"set breaks from the taper's markers (was "
                                f"{_breaks_of(step1_sets)} {list(dict.fromkeys(step1_sets))})")
        elif anchor_note is not None:
            # Not owned (step 4): exactly today's path from here on -- the
            # anchoring note, else the LLM branch below, then every flag.
            notes.append(anchor_note)
        elif today_llm and not cascade.self_filled:
            # (A self-filled tape -- every song-like track `desc-position` and D passed
            # all its checks -- never gets here: spec Q2, operator ruling "let them
            # ship". No align_structure call, no needs_align verdict, no low-confidence
            # flag; labels come from jerrybase anchoring when it resolved, else from
            # the deterministic align() above. `today_llm` itself, as passed to
            # `decide_taper`, is unchanged.)
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
                except RateLimited:
                    # A usage window ran out. Degrading to a review flag here
                    # would write a `low-confidence structure alignment` the
                    # recording did not earn, and `should_run` means the
                    # resume never recomputes it - so the wrong flag would be
                    # permanent. Re-raise so `_execute` can pause the run on
                    # it instead of degrading: `cli.py`'s per-show
                    # `except RateLimited` (checked before the broader
                    # `except (TaskFailed, HerderError, IAError)`, which it
                    # would otherwise also match) catches this, marks the
                    # session paused with a resume time, and leaves this
                    # show's finished stages on disk for `run resume` to
                    # pick up - not recorded as a per-show failure.
                    raise
                except (TaskFailed, HerderError) as err:
                    log.warning("align_structure failed: %s", err)
            else:
                # Reached and not taken: the flag below is still appended
                # exactly as before, and the verdict says an LLM would have
                # had a say (spec "Slice 0").
                needs_align = True
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
        # On a taper-owned show only the labels are the taper's: segues and
        # `matched` stay step 1's, unchanged.
        tracks = [t.model_copy(update={
            "set": s, "segue": g,
            "matched": None if t.title_source in TAUTOLOGICAL_TITLE_SOURCES else m})
                  for t, s, g, m in zip(tracks,
                                        result.sets if shipped_sets is None else shipped_sets,
                                        result.segues, result.matched)]
        breaks = set_breaks(tracks)
        coverage, conflicts = result.coverage, result.conflicts
        if taper_owned:
            coverage = reader_coverage
        # merge_conflicts has three different lifecycles, same exposure as
        # the `conflicts` trade-off noted above: it SURVIVES jerrybase
        # anchoring via the `model_copy` above (anchoring only replaces
        # `sets`) - but anchoring can then replace the very breaks a flagged
        # track was said to span, so the flag can end up naming a track whose
        # final labels are actually consistent; it is SILENTLY DROPPED when
        # LLM realignment wins, because `apply_llm_alignment` never
        # populates it; and it is never computed at all on the override
        # branch. Left as-is - whether an anchoring-overridden flag should
        # still fire is a later call, not this one's. Dropped on a
        # taper-owned show: placement already excludes a merged track at a
        # taper boundary (spec section 5).
        if result.merge_conflicts and not taper_owned:
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

    # Venue enrichment + the jerrybase venue tripwire (spec Slice 1). The arms
    # are ONE chain, in this order: enrichment, 1a, step 1 (the vote agrees),
    # step 2 (the swap), the two-venue signature, 1c, else today's flag. `sel`
    # is the selected recording's own entry in the candidate (absent after a
    # hand-edit or an older grouping: then no swap, no 1c, no 1d).
    sel = next((r for r in candidate.recordings if r.identifier == identifier), None)
    sel_venue = _stripped(sel.venue) if sel is not None else None
    sel_city = _stripped(sel.coverage) if sel is not None else None
    vote_venue, vote_city = candidate.venue, candidate.city
    venue, city, venue_source = vote_venue, vote_city, "item"
    # slice B: a tied vote ships the selected string; an operator venue override
    # chooses the venue itself, so it takes no tie-break (and no tie-break city)
    tie = venue_tie_break(candidate, sel) if overrides.venue is None else None
    if event is not None:
        if not (venue and venue.strip()):
            # Enrichment, byte-identical to before except 1a: a blank
            # jerrybase venue neither enriches nor flags.
            if event.venue.strip():
                venue, city, venue_source = event.venue, event.city, "jerrybase"
        else:
            jb_city = jerrybase_city(event)
            archive_city = sel_city or vote_city
            mismatch = f"venue mismatch: archive '{venue}' vs jerrybase '{event.venue}'"
            if not event.venue.strip():
                # 1a: a blank jerrybase venue is no evidence, unless the
                # cities say this is not the place.
                if not cities_compatible(archive_city, jb_city):
                    flags.append(mismatch)
                elif tie is not None:
                    venue, city = tie
            elif venues_equivalent(venue, event.venue) and (
                    _venues_equivalent_pre1b(venue, event.venue)
                    or cities_compatible(archive_city, jb_city)):
                # Step 1: the vote ships. Narrowing S (Checkpoint C operator
                # decision, 2026-10-19): a pair equivalent before slice 1
                # passes on equivalence alone; only a pair 1b NEWLY made
                # equivalent must also have compatible cities.
                if (tie is not None and venues_equivalent(tie[0], event.venue)
                        and (_venues_equivalent_pre1b(tie[0], event.venue)
                             or cities_compatible(archive_city, jb_city))):
                    venue, city = tie           # slice B, on step 1's full test
            elif (sel_venue and venues_equivalent(sel_venue, event.venue)
                  and cities_compatible(sel_city or vote_city, jb_city)
                  and not two_venue_signature(candidate)):
                # Step 2, the swap: the selected recording and jerrybase agree.
                op_notes.append(f"venue taken from the selected recording: '{sel_venue}' agrees "
                                f"with jerrybase '{event.venue}' (vote was '{vote_venue}')")
                venue, city = sel_venue, sel_city or vote_city
            elif two_venue_signature(candidate):
                flags.append(mismatch)                  # a same-city double keeps the hold
            elif (len(events) == 1 and sel_venue
                  and cities_compatible(sel_city or vote_city, jb_city)):
                # 1c: same place, different name, on a single-event date.
                op_notes.append(f"venue differs from jerrybase: archive '{sel_venue}' "
                                f"vs '{event.venue}' (same city)")
                venue, city = sel_venue, sel_city or vote_city
            else:
                flags.append(mismatch)
    elif tie is not None:
        venue, city = tie                       # slice B: no event

    # 1d, every show, jerrybase or not, after the swap: a selected recording
    # whose city is known to conflict with the vote's ships its own venue and
    # city, held (the other recordings may be a different performance). An
    # unknown city on either side is no conflict, so a blank vote city is None.
    # Narrowing V (Checkpoint C operator decision, 2026-10-19): it fires only on
    # a genuine second venue -- the selected recording's venue not equivalent
    # to the vote's (the venue the chain started from, never the swapped one or
    # jerrybase's). Two recordings naming one hall in "different" cities is
    # locality noise. A blank vote venue is no evidence of the same hall, so it
    # counts as not equivalent and the city conflict still holds.
    if (sel_venue and sel_city and _stripped(vote_city)
            and not (_stripped(vote_venue) and venues_equivalent(sel_venue, vote_venue))
            and not cities_compatible(sel_city, vote_city)):
        venue, city = sel_venue, sel_city
        flags.append(f"{_CITY_CONFLICT_FLAG}: '{sel_city}' (selected) vs '{vote_city}'")

    if overrides.venue is not None:
        venue, venue_source = overrides.venue, "override"
        flags = [f for f in flags if not f.startswith("venue mismatch")]
    if overrides.city is not None:
        city = overrides.city
    if overrides.venue is not None or overrides.city is not None:
        flags = [f for f in flags if not f.startswith(_CITY_CONFLICT_FLAG)]

    # Closer tripwire (single-event, non-anchored alignments; anchoring places
    # breaks at closers by construction, so it cannot contradict itself).
    # The skip keys on ownership plus mechanism: only when the taper does not
    # own the structure AND the shipped breaks came from jerrybase anchoring.
    if event is not None and (taper_owned or alignment != "jerrybase"):
        hard, soft = jerrybase.closer_contradictions(tracks, event)
        if taper_owned:
            hard, _, closer_notes = demote_jerrybase_flags(
                hard, None, event, decision.taper, family_aliases)
            op_notes += closer_notes
        flags += hard
        notes += soft
        # 5c.1: closers excused because only filler follows them; operator
        # notes only (notes.json), never `notes`, which reach the briefing LLM.
        op_notes += jerrybase.filler_tail_closers(tracks, event)

    # Count numbered sets only — an encore is a coda, not a set, and jerrybase
    # often records only the numbered sets, so counting it would spuriously
    # disagree with a tape that labels a trailing encore (or vice-versa).
    expected_sets = (len({s.name for s in event.sets if s.name != "encore"})
                     if event is not None else None)
    # 5a: numbered sets only, unless the canonical's encore was lost from the tape.
    evidence = {i.set for i in canonical.items}
    if not encore_lost(tracks, canonical, family_aliases):
        evidence.discard("encore")
    guard = structure_guard(tracks, breaks,
                            evidence_sets=evidence,
                            min_minutes=structure_cfg.guard_min_minutes,
                            expected_set_count=expected_sets)
    if guard and guard.startswith("structure has ") and taper_owned and event is not None:
        _, guard, count_notes = demote_jerrybase_flags(
            [], guard, event, decision.taper, family_aliases)
        op_notes += count_notes
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
    elif canonical_source is not None or notes or taper_owned:
        # A taper-owned structure is recorded even with no canonical source.
        source = canonical_source if canonical_source is not None else "none"
        structure_info = StructureInfo(source=source, alignment=alignment,
                                       coverage=coverage,
                                       conflicts=_dedupe_ordered(conflicts + notes),
                                       taper_owned=taper_owned)

    date, date_source, item_date = candidate.date, "item", None
    if overrides.date is not None:
        date, date_source, item_date = overrides.date, "override", candidate.date

    # Stamped here rather than in titles.resolve_titles so no intermediate
    # rebuild of `tracks` between there and here can drop it.
    #
    # This reads the REQUEST (`overrides.include`) where the recording-level
    # bases in `title_inputs` deliberately read `ordering["readmitted"]` instead, and the
    # difference is intended (whole-branch review M7). The bases answer "which
    # files must lose their vote", where naming an already-kept file would
    # wrongly disenfranchise it; this answers "which files did the operator
    # ask for", which is exactly the request. A name that re-admitted nothing
    # marks nothing, because it is not in `tracks` under either reading.
    if overrides.include:
        forced = set(overrides.include)
        for t in tracks:
            t.included = t.filename in forced

    # Slice 5: cosmetic strip of the FINAL titles, after every flag, set label and
    # structure above was computed from the pre-strip titles (spec "Slice 5").
    title_paths = cascade.paths
    if "slice5" in enabled_slices:
        tracks, strip_notes, changed = cosmetic_strip(tracks, artist=artist)
        op_notes += strip_notes
        if changed:
            paths = list(title_paths)
            for pos in changed:
                paths[pos] += "+5"
            title_paths = tuple(paths)

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
    needs_llm = tuple(name for name, hit in (("extract_setlist", cb.needs_llm),
                                             ("align_structure", needs_align)) if hit)
    return GatherResult(show=show, reviews=md.get("reviews", []), notes=op_notes,
                        needs_llm=needs_llm, taper_owned=taper_owned, taper=decision,
                        step1_alignment=step1_alignment, self_filled=cascade.self_filled,
                        title_paths=title_paths, title_record=cascade.record)


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
    res = compute_gather(
        show_ws, ia, provider, candidate, identifier,
        audio_format=audio_format, align_provider=align_provider,
        setlistfm=setlistfm, structure_cfg=structure_cfg,
        jerrybase_enabled=jerrybase_enabled)
    # notes.json is REPLACED on every gather (`vet` reset: a vet note belongs
    # to the gather it was raised against), and written BEFORE show.json:
    # show.json is `should_run`'s done-marker, so a crash between the two
    # leaves gather to re-run rather than a new show.json beside stale notes.
    write_artifact(show_ws.notes, ShowNotes(gather=res.notes, vet=[]))
    write_artifact(show_ws.show, res.show)
    write_artifact(show_ws.reviews, res.reviews)
    return res.show
