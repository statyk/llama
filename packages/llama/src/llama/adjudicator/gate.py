"""The adjudicator's target validation and policy gate (spec "The policy gate", "Before
judging", and the auto-switch bar under "Recording pin"). Pure code, no IO: the strict
surface of the feature. A verdict auto-applies only when no veto holds and every edit
passes its bar; otherwise it is stored as a proposal. Every bar reads the constants
below, so a retune is one edit here (and the prompt, `prompts/adjudicate.md`, which
states these rules to the model, must change with it)."""
from __future__ import annotations

import html
import math
import re
from dataclasses import dataclass
from pathlib import Path

from llama.adjudicator.bundle import Bundle, Row, escape_braces
from llama.adjudicator.verdict import (City, Evidence, Exclude, FlagJudgement, Include,
                                       OverruleFlag, ProposeOnly, SetTitle, Structure,
                                       SwitchRecording, Venue, Verdict)
from llama.junk import DUPLICATE_DERIVATIVE_REASON, SPAM_REASON
from llama.models import Show, Track
from llama.override_keys import filename_keyed_entries
from llama.overrules import flag_key
from llama.placeholders import is_placeholder_title
from llama.structure import is_filler
from llama.titles import clean_tag_title, is_real_title

SHORT_EDIT_MAX_S = 60.0       # an include/exclude longer than this takes the long bar
VERDICT_SUM_MAX_S = 120.0     # ... and so does every one once the verdict's sum passes this
SIBLING_TOL_S = 2.0           # sibling match: within max(SIBLING_TOL_S, SIBLING_TOL_FRAC * d)
SIBLING_TOL_FRAC = 0.01
COVERAGE_ADDED_MAX_S = 60.0   # a switch's coverage check (Task 6), kept here with the bars
SIBLING_COVERAGE_TOL_S = 60.0  # a considered recording "keeps more" duration only past this

TITLE_BAR_SOURCES = {"unresolved", "tags", "desc-position", "sibling-format", "sibling-align",
                     "sibling", "setlist", "setlist-gap"}
LONG_BAR_KINDS = {"taper-description", "original-tag", "sibling-tracks"}
TITLE_WEAK_KINDS = {"setlistfm", "jerrybase", "review"}
TAPER_SIDE_KINDS = {"taper-description", "original-tag", "derivative-tag"}
# The setlist-only kinds: a structure edit from these alone is propose-only.
SETLIST_ONLY_KINDS = {"setlistfm", "jerrybase"}
TITLE_OVERRULE_KINDS = {"taper-description", "original-tag", "sibling-tracks"}
REFUSED_INCLUDE_REASONS = {"duplicate-listing", DUPLICATE_DERIVATIVE_REASON, SPAM_REASON}
OPERATOR_EXCLUDED = "operator-excluded"
MEDIUM_UP = {"medium", "high"}
HIGH = {"high"}

OVERRULE_BAR: dict[str, str] = {
    "research-song": "title", "research-date": "title",
    "research-sets": "structure", "alignment": "structure", "single-set": "structure",
    "sets-not-found": "structure", "jerrybase-set-count": "structure",
    "jerrybase-closer": "structure",
    "venue": "medium", "briefing-song": "medium", "briefing-set": "medium",
    "briefing-other": "medium",
    "titles": "never", "low-confidence-setlist": "never", "tape-spans": "never",
    "multi-event": "never", "events-unassigned": "never", "no-tracks": "never",
    "merged-tracks": "never", "city": "never", "other": "never",
    # taperssection: no evidence kind can establish lineage, so only an operator clears it.
    "lineage-unknown": "never", "misattribution": "medium",
}
STRUCTURE_KINDS = {k for k, b in OVERRULE_BAR.items() if b == "structure"}

EXISTING = "changes an existing overrides.json entry"
STRUCTURE_ON_INCLUDED = ("structure names a file this verdict includes; its position is not "
                         "predicted")
_TRACK_LIST_OPS = {"include", "exclude", "switch_recording"}
_SEGUE = re.compile(r"\s*(?:->|>)\s*")
_LETTER = re.compile(r"[^\W\d_]")


# ---------------------------------------------------------------- text checks

def normalize(s: str) -> str:
    s = html.unescape(s)
    s = s.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    return " ".join(s.casefold().split())


def _nq(quote: str) -> str:
    """A quote normalised the way the bundle text was: braces escaped first."""
    return normalize(escape_braces(quote))


def quote_ok(ev: Evidence, bundle: Bundle) -> bool:
    """The hallucination filter: the quote is in its CLAIMED kind's section. A quote
    that normalises to nothing is a substring of everything, so it fails."""
    q = _nq(ev.quote)
    if not q:
        return False
    return q in normalize("\n".join(r.text for r in bundle.sections.get(ev.kind, [])))


def quote_rows(ev: Evidence, bundle: Bundle) -> list[Row]:
    q = _nq(ev.quote)
    if not q:
        return []
    return [r for r in bundle.sections.get(ev.kind, []) if q in normalize(r.text)]


def stem_in(quote: str, filename: str) -> bool:
    """The file's stem occurs in the quote as a whole token, not preceded or followed by
    a letter or digit (Unicode-aware): `d1t1` is not in `d1t10` nor in `éd1t1`. A stem
    with no letter (`01.mp3`) never counts: a bare number in a quote is a track position,
    and a bare track number never names a file (operator ruling, 2026-11-07)."""
    stem = normalize(Path(filename).stem)
    if not _LETTER.search(stem):
        return False
    return re.search(r"(?<![^\W_])" + re.escape(stem) + r"(?![^\W_])",
                     normalize(quote)) is not None


def is_filler_title(title: str) -> bool:
    parts = [p for p in _SEGUE.split(title) if p.strip()]
    return bool(parts) and all(is_filler(p) for p in parts)


def sibling_match(ev: Evidence, bundle: Bundle, track: Track) -> bool:
    d = bundle.length_of(track.filename)
    if d is None:
        return False
    tol = max(SIBLING_TOL_S, SIBLING_TOL_FRAC * d)
    return any(r.length_s is not None and abs(r.length_s - d) <= tol
               for r in quote_rows(ev, bundle))


def overrule_bar(flag: str, show: Show) -> str:
    key = flag_key(flag, show)
    if key is None:
        return "never"
    return OVERRULE_BAR.get(key.kind, "never")


# ---------------------------------------------------------------- results

@dataclass(frozen=True)
class Facts:
    bundle: Bundle
    delivered: bool
    marked: bool
    lineage: dict[str, float]
    complaints: dict[str, int]


@dataclass(frozen=True)
class EditGate:
    index: int
    op: str
    bar: str      # short | long | title | structure | medium | switch | propose-only | never
    passed: bool
    reason: str


@dataclass(frozen=True)
class GateResult:
    edits: list[EditGate]
    vetoes: list[str]
    auto: bool


# ---------------------------------------------------------------- validation

def _track_names(show: Show) -> set[str]:
    return {t.filename for t in show.tracks}


def _structure_files(e: Structure) -> list[str]:
    return list(e.breaks_after) + ([e.encore_after] if e.encore_after is not None else [])


_NOT_PLACEABLE = "is not a current track or a file this verdict includes"
_INCLUDE_AND_TITLE = ["include", "set_title"]


def validate_targets(verdict: Verdict, bundle: Bundle) -> list[str]:
    """Every malformed target, one reason each; [] is valid. Filenames are matched
    exactly and case-sensitively: a near miss names no file. A set_title or structure edit
    may target a current track or an excluded file this same verdict includes (R4)."""
    show, ov = bundle.show, bundle.overrides
    tracks = _track_names(show)
    excluded = {x.get("filename") for x in show.excluded_files}
    included = {e.file for e in verdict.edits if isinstance(e, Include)} & excluded
    placeable = tracks | included
    considered = set((bundle.selection.get("scores") or {}))
    flags = set(show.review_flags)
    keyed = set(ov.titles) | {str(f) for f in ov.set_breaks or ()}
    if ov.encore_after is not None:
        keyed.add(str(ov.encore_after))
    out: list[str] = []
    named: dict[str, list[int]] = {}      # file -> include/exclude/set_title edit indexes
    excluded_by: dict[str, int] = {}
    structures, switches = [], []
    for i, e in enumerate(verdict.edits):
        if isinstance(e, Exclude) and e.file not in tracks:
            out.append(f"edit {i} exclude: {e.file} is not a current track")
        if isinstance(e, SetTitle) and e.file not in placeable:
            out.append(f"edit {i} set_title: {e.file} {_NOT_PLACEABLE}")
        if isinstance(e, Include) and e.file not in excluded:
            out.append(f"edit {i} include: {e.file} is not an excluded file")
        if isinstance(e, (Include, Exclude, SetTitle)):
            named.setdefault(e.file, []).append(i)
        if isinstance(e, Exclude):
            excluded_by.setdefault(e.file, i)
            if e.file in keyed:
                out.append(f"edit {i} exclude: {e.file} carries an overrides.json title, "
                           f"set break or encore key")
        if isinstance(e, Structure):
            structures.append(i)
            for f in _structure_files(e):
                if f not in placeable:
                    out.append(f"edit {i} structure: {f} {_NOT_PLACEABLE}")
        if isinstance(e, SwitchRecording):
            switches.append(i)
            if e.identifier == show.identifier:
                out.append(f"edit {i} switch_recording: {e.identifier} is the current recording")
            elif e.identifier not in considered:
                out.append(f"edit {i} switch_recording: {e.identifier} is not a considered "
                           f"recording")
        if isinstance(e, OverruleFlag) and e.flag not in flags:
            out.append(f"edit {i} overrule: {e.flag!r} is not a current flag")
    # Any file named by two include/exclude/set_title edits conflicts, the same op twice
    # included (two titles for one file cannot both apply), except one include plus one
    # set_title: re-admit the file and title it (R4).
    for f, idx in named.items():
        if len(idx) > 1 and sorted(verdict.edits[i].op for i in idx) != _INCLUDE_AND_TITLE:
            out.append(f"edits {', '.join(map(str, idx))}: conflict on {f}")
    for i in structures:
        for f in _structure_files(verdict.edits[i]):
            if f in excluded_by:
                out.append(f"edits {excluded_by[f]}, {i}: conflict on {f} "
                           f"(excluded and named by the structure edit)")
    if len(structures) > 1:
        out.append(f"edits {', '.join(map(str, structures))}: more than one structure edit")
    if len(switches) > 1:
        out.append(f"edits {', '.join(map(str, switches))}: more than one switch_recording edit")
    # Repeated judgements of one flag that agree on verdict and confidence are one
    # judgement, the first (review_flags may carry a string twice: pilot-review section 5,
    # discobiscuits; `why` is prose the gate never reads); disagreeing ones are malformed.
    seen: dict[str, FlagJudgement] = {}
    for j in verdict.flags:
        if j.flag not in flags:
            out.append(f"flag judgement {j.flag!r}: not a current flag")
        elif j.flag in seen:
            if not _agree(j, seen[j.flag]):
                out.append(f"flag judgement {j.flag!r}: judged twice with different verdicts "
                           f"or confidence")
            continue
        seen[j.flag] = j
    return out


def _agree(a: FlagJudgement, b: FlagJudgement) -> bool:
    return (a.verdict, a.confidence) == (b.verdict, b.confidence)


def first_judgements(verdict: Verdict) -> dict[str, FlagJudgement]:
    """Each judged flag's FIRST judgement: a valid verdict's repeats agree on verdict and
    confidence (`validate_targets`), so the first one's `why` is the one shown (R5)."""
    out: dict[str, FlagJudgement] = {}
    for j in verdict.flags:
        out.setdefault(j.flag, j)
    return out


# ---------------------------------------------------------------- bars

def _track(show: Show, filename: str) -> Track | None:
    return next((t for t in show.tracks if t.filename == filename), None)


def _excluded_row(show: Show, filename: str) -> dict | None:
    return next((x for x in show.excluded_files if x.get("filename") == filename), None)


def _dur(bundle: Bundle, filename: str) -> float:
    d = bundle.length_of(filename)
    return math.inf if d is None else d


def is_resolved_song(t: Track) -> bool:
    return (t.title_source != "unresolved" and not is_placeholder_title(t.title)
            and not is_filler_title(t.title))


def _long_anchor(ev: Evidence, bundle: Bundle, filename: str) -> bool:
    if ev.kind not in LONG_BAR_KINDS:
        return False
    own = bundle.own_row(ev.kind, filename)
    stem = Path(filename).stem.casefold()
    # A row naming a file of the same stem (ignoring case) counts as the file's own row
    # too: a derivative whose `original` is unrecorded has `own_row` None, and its flac
    # row is still its own.
    if not any(r != own and not (r.filename and Path(r.filename).stem.casefold() == stem)
               for r in quote_rows(ev, bundle)):
        return False
    return stem_in(ev.quote, filename)


def _track_edit(e, verdict: Verdict, bundle: Bundle,
                verdict_sum: float) -> tuple[str, bool, str]:
    show, ov = bundle.show, bundle.overrides
    if isinstance(e, Exclude):
        t = _track(show, e.file)
        if t is not None and is_resolved_song(t):
            return "propose-only", False, "exclude of a track with a resolved song title"
        if e.file in ov.include:
            return "propose-only", False, EXISTING
    else:
        row = _excluded_row(show, e.file) or {}
        reasons = set(row.get("reasons") or [])
        if reasons & REFUSED_INCLUDE_REASONS:
            return ("propose-only", False,
                    f"include of a file dropped as {', '.join(sorted(reasons & REFUSED_INCLUDE_REASONS))}")
        if OPERATOR_EXCLUDED in reasons or e.file in ov.exclude:
            return "propose-only", False, EXISTING
        shipped = _include_placeholder(e, verdict, bundle)
        if shipped is not None:
            return "propose-only", False, shipped
    if _dur(bundle, e.file) > SHORT_EDIT_MAX_S or verdict_sum > VERDICT_SUM_MAX_S:
        if e.confidence not in HIGH:
            return "long", False, "long bar needs high confidence"
        if not any(_long_anchor(ev, bundle, e.file) for ev in e.evidence):
            return ("long", False, "long bar needs a quote from the taper description, an "
                    "original tag or a sibling's tracks, outside the file's own tag row, "
                    "naming the file's stem")
        return "long", True, ""
    if e.confidence not in MEDIUM_UP:
        return "short", False, "short bar needs medium or high confidence"
    return "short", True, ""


def _title_anchor(ev: Evidence, e: SetTitle, bundle: Bundle, t: Track | None) -> bool:
    if normalize(e.title) not in normalize(ev.quote):
        return False
    if ev.kind == "sibling-tracks":
        return t is not None and sibling_match(ev, bundle, t)
    if ev.kind == "taper-description":
        return True
    if ev.kind == "original-tag":
        own = bundle.own_row("original-tag", e.file)
        return own is not None and _nq(ev.quote) in normalize(own.text)
    return False


def _title_edit(e: SetTitle, bundle: Bundle) -> tuple[str, bool, str]:
    t = _track(bundle.show, e.file)
    if (t is not None and t.title_source == "override") or e.file in bundle.overrides.titles:
        return "propose-only", False, EXISTING
    if t is not None and t.title_source not in TITLE_BAR_SOURCES \
            and not is_placeholder_title(t.title):
        return "never", False, f"title over a {t.title_source} title"
    if all(ev.kind in TITLE_WEAK_KINDS for ev in e.evidence):
        return "propose-only", False, "setlist.fm, JerryBase or reviews alone"
    if e.confidence not in HIGH:
        return "title", False, "title bar needs high confidence"
    if not any(_title_anchor(ev, e, bundle, t) for ev in e.evidence):
        return ("title", False, "title bar needs the title quoted from the taper description, "
                "this file's own original tag row, or a matching sibling file")
    return "title", True, ""


def _structure_evidence(e, bar: str) -> tuple[str, bool, str]:
    if e.confidence not in HIGH:
        return bar, False, f"{bar} bar needs high confidence"
    if not any(ev.kind in TAPER_SIDE_KINDS for ev in e.evidence):
        if bar == "structure" and all(ev.kind in SETLIST_ONLY_KINDS for ev in e.evidence):
            return "propose-only", False, "setlist.fm or JerryBase alone"
        return bar, False, f"{bar} bar needs a taper-side quote"
    return bar, True, ""


def _structure_edit(e: Structure, verdict: Verdict, bundle: Bundle) -> tuple[str, bool, str]:
    ov = bundle.overrides
    if ov.set_breaks is not None or ov.encore_after is not None:
        return "propose-only", False, EXISTING
    # Fail closed (R4 fix round 1): an included file's play position is not predicted, and
    # apply's re-check derives the set labels from where the structure files actually land,
    # so a break or encore anchored on an included file would split the show unchecked.
    included = {x.file for x in verdict.edits if isinstance(x, Include)}
    if included & set(_structure_files(e)):
        return "propose-only", False, STRUCTURE_ON_INCLUDED
    return _structure_evidence(e, "structure")


def is_placeholder_track(t: Track) -> bool:
    """The placeholder veto's test, fail closed: a blank or missing title, an unresolved
    source, or `is_placeholder_title` (which judges a blank title False on its own)."""
    title = t.title if isinstance(t.title, str) else ""
    return (not title.strip() or t.title_source == "unresolved"
            or is_placeholder_title(title))


def _is_placeholder_text(title) -> bool:
    return not isinstance(title, str) or not title.strip() or is_placeholder_title(title)


def _included_title(bundle: Bundle, filename: str) -> str | None:
    """The title gather's `tags` rung would give a re-admitted file: its own cleaned
    metadata tag, when that is a real title. None (undeterminable) otherwise: no metadata
    row, or a tag gather would not take as a real title."""
    meta = bundle.files.get(filename)
    tag = clean_tag_title(meta.title) if meta is not None else ""
    return tag if tag and is_real_title(tag) else None


def _predicted_placeholders(verdict: Verdict, bundle: Bundle) -> list[tuple[str, str | None]]:
    """(file, title) for each placeholder title in the predicted post-verdict kept set:
    current tracks minus excludes plus includes, set_title edits applied; an included file
    without a set_title takes `_included_title`, None (undeterminable) counting too."""
    excludes = {e.file for e in verdict.edits if isinstance(e, Exclude)}
    titled = {e.file: e.title for e in verdict.edits if isinstance(e, SetTitle)}
    out: list[tuple[str, str | None]] = []
    for t in bundle.show.tracks:
        if t.filename in excludes:
            continue
        if t.filename in titled:
            if _is_placeholder_text(titled[t.filename]):
                out.append((t.filename, titled[t.filename]))
        elif is_placeholder_track(t):
            out.append((t.filename, t.title))
    for e in verdict.edits:
        if not isinstance(e, Include) or e.file in excludes:
            continue
        title = titled[e.file] if e.file in titled else _included_title(bundle, e.file)
        if _is_placeholder_text(title):
            out.append((e.file, title))
    return out


def _include_placeholder(e: Include, verdict: Verdict, bundle: Bundle) -> str | None:
    """An include is propose-only when its predicted title (`_predicted_placeholders`:
    the verdict's set_title for the file, else its cleaned real tag) is a placeholder or
    undeterminable: gather may ship that tag (operator ruling 2026-11-07). It runs on every
    include, a verdict with a research-song overrule included (clause (b) of
    `_placeholder_veto` holds that overrule too); apply's whole-show check is the backstop."""
    if _track(bundle.show, e.file):
        return None          # (an include of a current track is malformed: validate_targets)
    bad = [(fn, t) for fn, t in _predicted_placeholders(verdict, bundle) if fn == e.file]
    if not bad:
        return None
    fn, title = bad[0]
    shown = "no determinable title" if title is None else repr(title)
    return f"include ships a placeholder title ({fn}: {shown})"


def _placeholder_veto(e: OverruleFlag, verdict: Verdict, bundle: Bundle) -> str | None:
    """A research-song overrule is propose-only while (a) any shipped title of the current
    (pre-verdict) show is a placeholder, or (b) any title of the predicted post-verdict
    kept set is: an unknown-song flag on such a show may be the only thing holding a
    `Track N` title off the air. Strict: set_title edits do not lift (a) (operator ruling
    2026-11-07); (b) keeps an include of a placeholder-titled file from clearing the
    hold (the include check and apply's whole-show backstop hold the include itself)."""
    show = bundle.show
    key = flag_key(e.flag, show)
    if key is None or key.kind != "research-song":
        return None
    bad = [t for t in show.tracks if is_placeholder_track(t)]
    if bad:
        return (f"research-song overrule while {len(bad)} shipped title(s) are placeholders "
                f"(e.g. {bad[0].filename}: {bad[0].title!r})")
    post = _predicted_placeholders(verdict, bundle)
    if post:
        fn, title = post[0]
        shown = "no determinable title" if title is None else repr(title)
        return (f"research-song overrule while {len(post)} predicted post-verdict title(s) "
                f"are placeholders (e.g. {fn}: {shown})")
    return None


def _overrule_edit(e: OverruleFlag, verdict: Verdict, bundle: Bundle) -> tuple[str, bool, str]:
    bar = overrule_bar(e.flag, bundle.show)
    if bar == "never":
        return "never", False, "this flag kind is never overruled automatically"
    veto = _placeholder_veto(e, verdict, bundle)
    if veto is not None:
        return "propose-only", False, veto
    judged = next((j for j in verdict.flags if j.flag == e.flag), None)
    if judged is None or judged.verdict != "spurious":
        return bar, False, "overrule of a flag not judged spurious"
    if bar == "medium":
        if e.confidence not in MEDIUM_UP:
            return bar, False, "medium bar needs medium or high confidence"
        return bar, True, ""
    if bar == "structure":
        return _structure_evidence(e, "structure")
    # title: the title bar's evidence kinds; these flags name a song or date, not a
    # file, so the per-file anchors (sibling match, own tag row) do not apply.
    if e.confidence not in HIGH:
        return bar, False, "title bar needs high confidence"
    if all(ev.kind in TITLE_WEAK_KINDS for ev in e.evidence):
        return bar, False, "setlist.fm, JerryBase or reviews alone"
    if not any(ev.kind in TITLE_OVERRULE_KINDS for ev in e.evidence):
        return bar, False, ("title bar needs a quote from the taper description, an original "
                            "tag or a sibling's tracks")
    return bar, True, ""


def _switch_edit(e: SwitchRecording, verdict: Verdict, facts: Facts) -> tuple[str, bool, str]:
    b = facts.bundle
    scores = b.selection.get("scores") or {}
    sib = scores.get(e.identifier) or {}
    cur = scores.get(b.show.identifier) or {}
    propose: list[str] = []
    fail: list[str] = []
    if not (sib.get("kept_tracks") or 0) > 0:
        fail.append("sibling has no file in the wanted format")
    # Facts.complaints holds select's complaint count per identifier; a sibling missing
    # from it is one select found no complaints against (0).
    if facts.complaints.get(e.identifier, 0) != 0:
        fail.append("select found recording complaints against the sibling")
    s_rank, c_rank = facts.lineage.get(sib.get("lineage")), facts.lineage.get(cur.get("lineage"))
    if s_rank is None or c_rank is None:
        propose.append("lineage class not in the lineage table")
    elif s_rank < c_rank:
        fail.append("sibling's lineage class ranks worse than the current recording's")
    if e.confidence not in HIGH:
        fail.append("switch needs high confidence")
    if not e.evidence:   # each quote is also substring-checked in `_gate_edit`
        fail.append("switch needs at least one checked quote")
    if facts.delivered:
        fail.append("show is delivered")
    if facts.marked:
        fail.append("show is station-marked")
    if filename_keyed_entries(b.overrides):
        fail.append("overrides.json has filename-keyed entries")
    if b.overrides.recording is not None:
        propose.append(EXISTING)
    for other in verdict.edits:
        if other is not e and other.op != "venue":
            fail.append(f"switch with a {other.op} edit")
    reasons = propose + fail
    if not reasons:
        return "switch", True, ""
    return ("propose-only" if propose else "switch"), False, "; ".join(reasons)


def _bar(e, verdict: Verdict, facts: Facts, verdict_sum: float) -> tuple[str, bool, str]:
    b = facts.bundle
    if isinstance(e, ProposeOnly):
        return "propose-only", False, f"{e.op} is propose-only"
    if isinstance(e, (Include, Exclude)):
        return _track_edit(e, verdict, b, verdict_sum)
    if isinstance(e, SetTitle):
        return _title_edit(e, b)
    if isinstance(e, Structure):
        return _structure_edit(e, verdict, b)
    if isinstance(e, Venue):
        if b.overrides.venue is not None:
            return "propose-only", False, EXISTING
        if e.confidence not in MEDIUM_UP:
            return "medium", False, "venue needs medium or high confidence"
        return "medium", True, ""
    if isinstance(e, City):
        return "propose-only", False, "city is propose-only"
    if isinstance(e, SwitchRecording):
        return _switch_edit(e, verdict, facts)
    if isinstance(e, OverruleFlag):
        return _overrule_edit(e, verdict, b)
    return "never", False, f"unknown edit {e.op}"


def _gate_edit(i: int, e, verdict: Verdict, facts: Facts, verdict_sum: float) -> EditGate:
    bar, passed, reason = _bar(e, verdict, facts, verdict_sum)
    if not isinstance(e, ProposeOnly) and bar not in ("propose-only", "never"):
        bad = next((ev for ev in e.evidence if not quote_ok(ev, facts.bundle)), None)
        if bad is not None:
            passed, reason = False, f"quote not found in {bad.kind}"
    return EditGate(index=i, op=e.op, bar=bar, passed=passed, reason=reason)


def _vetoes(verdict: Verdict, show: Show) -> list[str]:
    out: list[str] = []
    if verdict.kind not in ("fix", "overrule"):
        out.append(f"kind is {verdict.kind}")
    if verdict.show_correct_after != "yes":
        out.append(f"show not judged correct after the action ({verdict.show_correct_after})")
    for j in verdict.flags:
        if j.verdict in ("real-not-fixable", "undecidable"):
            out.append(f"flag judged {j.verdict}: {j.flag}")
    judged = {j.flag for j in verdict.flags}
    for f in show.review_flags:
        if f not in judged:
            out.append(f"flag not judged: {f}")
    if verdict.better_sibling is not None and not any(
            isinstance(e, SwitchRecording) and e.identifier == verdict.better_sibling
            for e in verdict.edits):
        out.append(f"better_sibling {verdict.better_sibling} has no switch_recording edit to it")
    if not verdict.edits:
        out.append("no edits")
    return out


def _secs_text(s: float | None) -> str:
    return "?" if s is None else f"{s:.0f}"


def _kept_count(entry) -> int | None:
    """A selection.json scores entry's `kept_tracks`, or None when it is not usable."""
    n = entry.get("kept_tracks") if isinstance(entry, dict) else None
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        return None
    return n


def _operator_pinned(bundle: Bundle) -> bool:
    """Whether overrides.json pins the CURRENT recording by the operator's choice (Shawn's
    ruling, 2026-11-07: his choice of recording is the decision): `recording_source`
    "operator", or absent (a pin from before the field; every one came from `fix`). A
    pin the adjudicator wrote on an auto switch ("adjudicate"), or any other value, is not."""
    ov = bundle.overrides
    return (ov.recording is not None and ov.recording == bundle.show.identifier
            and ov.recording_source in (None, "operator"))


def _coverage_vetoes(verdict: Verdict, bundle: Bundle) -> list[str]:
    """A verdict with no switch_recording edit is propose-only while a considered recording
    keeps more than the current one, like with like: more selection.json `kept_tracks`, or,
    as a tie-break only on EQUAL `kept_tracks` (Shawn's ruling, 2026-11-07), a select-filtered
    metadata duration more than SIBLING_COVERAGE_TOL_S longer; a sibling with fewer tracks
    never vetoes on duration. Fail closed: no `scores`, show.json and selection.json naming
    different current recordings, or an entry (the current one's included) without a usable
    `kept_tracks` vetoes too; an unknown duration skips only the duration clause. An
    operator pin on the current recording exempts the show (`_operator_pinned`)."""
    if any(isinstance(e, SwitchRecording) for e in verdict.edits):
        return []
    if _operator_pinned(bundle):
        return []
    tail = "no switch_recording edit"
    sel = bundle.selection
    scores = sel.get("scores") if isinstance(sel, dict) else None
    if not isinstance(scores, dict):
        return [f"considered recordings unknown (no selection.json scores); {tail}"]
    cur = bundle.show.identifier
    if sel.get("identifier") != cur:
        return [f"current recording unknown (show.json {cur} vs selection.json "
                f"{sel.get('identifier')}); {tail}"]
    n_cur = _kept_count(scores.get(cur))
    if n_cur is None:
        return [f"coverage of the current recording {cur} unknown (no usable kept_tracks); "
                f"{tail}"]
    s_cur = bundle.current_kept_s
    out: list[str] = []
    for ident, entry in scores.items():
        if ident == cur:
            continue
        n = _kept_count(entry)
        if n is None:
            out.append(f"coverage of considered recording {ident} unknown (no usable "
                       f"kept_tracks); {tail}")
            continue
        s = bundle.sibling_kept_s.get(ident)
        longer = s is not None and s_cur is not None and s > s_cur + SIBLING_COVERAGE_TOL_S
        if n > n_cur:
            out.append(f"considered recording {ident} keeps more ({n} tracks, {_secs_text(s)} s) "
                       f"than the current ({n_cur} tracks, {_secs_text(s_cur)} s); {tail}")
        if n == n_cur and longer:      # the tie-break: duration counts on equal tracks only
            out.append(f"considered recording {ident} keeps more duration on equal tracks "
                       f"({n} tracks, {_secs_text(s)} s) than the current ({n_cur} tracks, "
                       f"{_secs_text(s_cur)} s); {tail}")
    return out


def evaluate(verdict: Verdict, facts: Facts) -> GateResult:
    b = facts.bundle
    verdict_sum = sum(_dur(b, e.file) for e in verdict.edits if isinstance(e, (Include, Exclude)))
    edits = [_gate_edit(i, e, verdict, facts, verdict_sum) for i, e in enumerate(verdict.edits)]
    # Fail closed: the runner validates first, and this is the second layer.
    vetoes = ([f"malformed: {r}" for r in validate_targets(verdict, b)]
              + _vetoes(verdict, b.show) + _coverage_vetoes(verdict, b))
    auto = not vetoes and bool(edits) and all(g.passed for g in edits)
    return GateResult(edits=edits, vetoes=vetoes, auto=auto)


def flag_passes(j: FlagJudgement, show: Show, verdict: Verdict, gate: GateResult) -> bool:
    """Whether a flag judgement clears its flag at a passing bar."""
    if j.verdict == "real-fixed-by-action":
        return j.confidence in MEDIUM_UP
    if j.verdict != "spurious":
        return False
    bar = overrule_bar(j.flag, show)
    if bar == "medium":
        return j.confidence in MEDIUM_UP
    if bar in ("title", "structure"):
        passed = {g.index for g in gate.edits if g.passed}
        return any(isinstance(e, OverruleFlag) and e.flag == j.flag and i in passed
                   for i, e in enumerate(verdict.edits))
    return False


def has_track_list_edit(verdict: Verdict) -> bool:
    return any(e.op in _TRACK_LIST_OPS for e in verdict.edits)


def has_track_list_or_structure_edit(verdict: Verdict) -> bool:
    return has_track_list_edit(verdict) or any(isinstance(e, Structure) for e in verdict.edits)
