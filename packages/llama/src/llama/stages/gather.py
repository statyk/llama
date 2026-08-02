import datetime
import logging
import re

from herder import HerderError, TaskFailed, run_json_task
from llama import jerrybase
from llama.config import StructureConfig
from llama.errors import LlamaError
from llama.junk import FORMAT_BY_AUDIO, filter_files
from llama.ia_client import IAError
from llama.models import (AlignedStructure, Candidate, ParsedSetlist, Show,
                          SourcedParse, StructureInfo)
from llama.prompts import load_prompt
from llama.setlist import parse_setlist
from llama.songs import GD_SHORTHAND
from llama.structure import (align, apply_llm_alignment, blend_segues,
                             from_setlistfm, fuzzy_norm_title, norm_title,
                             rank_parses, structure_guard, venues_equivalent)
from llama.titles import clean_tag_title, is_real_title, resolve_titles, set_breaks
from llama.workspace import ShowWorkspace, read_model, read_overrides, should_run, write_artifact

log = logging.getLogger("llama")


def _sets_from_breaks(n_tracks: int, breaks: list[int]) -> list[str]:
    """Numbered set labels ("1","2",...) for each 1-based track, given the
    track numbers a break falls *after*. Break after track b closes a set."""
    bset = set(breaks)
    labels, cur = [], 1
    for i in range(1, n_tracks + 1):
        labels.append(str(cur))
        if i in bset:
            cur += 1
    return labels


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


def _sibling_titles(ia, candidate: Candidate, identifier: str, want: str, n: int) -> list[str] | None:
    for rec in candidate.recordings:
        if rec.identifier == identifier:
            continue
        kept, _, _ = filter_files(ia.metadata(rec.identifier).get("files", []), want_format=want)
        titles = [clean_tag_title(f.get("title")) for f in kept]
        if len(kept) == n and all(is_real_title(t) for t in titles):
            return titles
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
    r"|\b[a-z]{1,4}-?\d{2,4}[a-z]?s?\b",
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


def _show_metadata_norms(artist: str, candidate: Candidate, meta: dict,
                         events: list) -> set[str]:
    """The closed vocabulary the head-banner guard matches against: everything
    this show's own metadata says about who/where/when it is."""
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
    real songs above it.

    Stage 2 (chatter run): from the new head, trim rig/lineage chatter and bare
    state codes, tolerating a gap of up to `_HEAD_GAP` unrecognized items when
    chatter resumes immediately after.
    """
    items = parsed.items

    def is_meta(item) -> bool:
        return fuzzy_norm_title(item.title) in norms or bool(_RIG.match(item.title))

    def is_chatter(item) -> bool:
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

    overrides = read_overrides(show_ws)
    if overrides.exclude:
        drop = set(overrides.exclude)
        matched = {f["name"] for f in kept if f["name"] in drop}
        for missing in sorted(drop - matched):
            log.warning("overrides.exclude entry %r matched no file", missing)
        excluded += [{"filename": f["name"], "reasons": ["operator-excluded"]}
                     for f in kept if f["name"] in drop]
        kept = [f for f in kept if f["name"] not in drop]

    # Canonical performance setlist: every recording's description, plus
    # setlist.fm when configured, ranked pick-best.
    parses, notes, descriptions = _collect_parses(ia, candidate, identifier, meta)
    if setlistfm is not None:
        raw = setlistfm.setlist(artist, candidate.date,
                                venue=candidate.venue, city=candidate.city)
        converted = from_setlistfm(raw) if raw else None
        if converted is not None:
            parses.insert(0, SourcedParse(source="setlist.fm", parsed=converted))

    best = rank_parses(parses, target_count=len(kept))
    if best is None:
        longest = max(descriptions, key=len, default="")
        if longest.strip():
            parsed = run_json_task(provider, "extract_setlist", ParsedSetlist,
                                   template=load_prompt("extract_setlist"),
                                   description=longest)
            best = SourcedParse(source="llm", parsed=parsed)
    canonical = best.parsed if best else ParsedSetlist()
    if best is not None and best.source == "setlist.fm":
        best_lma = rank_parses([p for p in parses if p.source != "setlist.fm"],
                               target_count=len(kept))
        canonical = blend_segues(canonical, best_lma.parsed if best_lma else None)

    # Jerrybase structure evidence (no-op for artists absent from the dataset).
    # A per-event candidate (/eN) selects events[N-1] for every evidence check.
    # Resolved HERE, above the setlist cleaning below, because the head-banner
    # guard reads the event venues as part of this show's own metadata; nothing
    # in this block depends on tracks or on the canonical setlist.
    events = jerrybase.lookup(artist, candidate.date) if jerrybase_enabled else []
    kind, n = _event_kind(candidate.performance_id)
    if kind == "event" and events and 1 <= n <= len(events):
        event = events[n - 1]
    elif kind == "event":
        event = None
    elif len(events) == 1:
        event = events[0]
    else:
        event = None

    # Clean the canonical setlist at the point it enters the stage, before
    # anything consumes it. Neither a taper banner nor an artist header line is
    # a song, so neither has any business in title resolution either — not just
    # in alignment. Placing this immediately before `align` would treat a
    # data-cleaning step as an alignment concern, and `resolve_titles` below is
    # upstream of that: it only trusts the setlist when
    # `len(items) == len(tracks)`, so on an untagged tape one header item costs
    # every title on the show.
    #
    # Order matters: the banner strip runs on the head span first, then the
    # artist drop globally. Every event on the date contributes its venue, not
    # just the resolved one — a multi-event date leaves `event` None, and the
    # banner still names the building.
    canonical = _strip_head_banner(
        canonical, _show_metadata_norms(artist, candidate, meta, events))
    canonical = _drop_artist_items(canonical, artist)

    siblings = None
    if any(not is_real_title(clean_tag_title(f.get("title"))) for f in kept) and (
        canonical.confidence == "low" or len(canonical.items) != len(kept)
    ):
        siblings = _sibling_titles(ia, candidate, identifier, want, len(kept))
    tracks = resolve_titles(kept, canonical, sibling_titles=siblings)
    for n, forced in overrides.titles.items():
        if not (1 <= n <= len(tracks)):
            raise LlamaError(f"overrides.titles: no track {n} "
                             f"(show has {len(tracks)} tracks)")
        tracks[n - 1] = tracks[n - 1].model_copy(
            update={"title": forced, "title_source": "override"})

    flags = []
    if overrides.set_breaks is not None:
        bad = [n for n in overrides.set_breaks if not (1 <= n < len(tracks))]
        if bad:
            raise LlamaError(f"overrides.set_breaks: track number(s) out of range "
                             f"{bad} (show has {len(tracks)} tracks)")
        labels = _sets_from_breaks(len(tracks), overrides.set_breaks)
        tracks = [t.model_copy(update={"set": s}) for t, s in zip(tracks, labels)]
        breaks = sorted(overrides.set_breaks)
        alignment = "override"
        coverage, conflicts = 1.0, []
    else:
        # Single-word Dead shorthand ("Scarlet", "Dew", "Help") is only safe
        # inside the Garcia universe — they are ordinary English words
        # elsewhere. Non-family shows get an empty table, which makes the
        # vocabulary a provable no-op on the non-Dead corpus.
        aliases = GD_SHORTHAND if jerrybase.is_family_artist(artist) else {}
        result = align(tracks, canonical, aliases=aliases)
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

        tracks = [t.model_copy(update={"set": s, "segue": g})
                  for t, s, g in zip(tracks, result.sets, result.segues)]
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
    if overrides.set_breaks is not None:
        structure_info = StructureInfo(source="override", alignment="override",
                                       coverage=1.0, conflicts=[])
    elif best is not None or notes:
        source = best.source if best is not None else "none"
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
