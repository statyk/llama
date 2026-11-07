"""Applying a verdict in one unit (spec "Apply and re-check", and the coverage bullet
under "Recording pin"): the strict surface where an edit reaches what airs.

Inside one `show_unit` (snapshot/restore under the show lock): capture the before
state, write `overrides.json` through a filename-keyed path (never the track-number
writer in `cli`), one redo from the earliest stage any edit needs, re-read the show,
then check it. A switch is checked by coverage, anything else by the whole-show diff;
both then check for silenced flags. Any finding raises `_Restore` inside the unit, so
the snapshot comes back byte-identical, and the verdict becomes a proposal noting why.

This module never imports `llama.cli`: the redo arrives as a callable (the caller's
`_redo_show_locked` bound to the show), and it never takes the show lock itself
(`file_lock` is not re-entrant; `show_unit` holds it).

A restore also takes back the ledger row the redo added (`_LedgerUndo`): the snapshot
covers the show directory only, and a redo that clears the hold records `selected`."""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Literal, Sequence

from herder import HerderError, TaskFailed
from herder.limits import RateLimited
from llama.adjudicator.gate import (COVERAGE_ADDED_MAX_S, OPERATOR_EXCLUDED, STRUCTURE_KINDS,
                                    GateResult, is_resolved_song, flag_passes,
                                    has_track_list_edit, has_track_list_or_structure_edit)
from llama.adjudicator.verdict import (City, Exclude, Include, OverruleFlag, ProposeOnly,
                                       SetTitle, Structure, SwitchRecording, Venue, Verdict)
from llama.audio_reuse import StationUnpaired
from llama.errors import LlamaError
from llama.ia_client import IAError
from llama.ledger import Ledger
from llama.models import Overrides, Provenance, Show
from llama.overrules import flag_key, merge_rules, records_for
from llama.show_unit import ShowChanged, ShowView, show_unit
from llama.songs import normalize_song
from llama.stages.gather import _sets_from_breaks
from llama.station_mark import StationUnreadable
from llama.workspace import (SHOW_STAGE_ORDER, ShowWorkspace, read_model, read_overrides,
                             write_artifact)

log = logging.getLogger(__name__)

Redo = Callable[[str], "Path | None"]
Mode = Literal["auto", "accept"]


@dataclass(frozen=True)
class TrackRow:
    filename: str
    title: str
    title_source: str
    set: str
    segue: bool
    duration_s: float | None


@dataclass
class ApplyResult:
    status: Literal["applied", "restored", "transient", "refused"]
    held: bool
    diff: list[str]
    changes: list[str]
    error: str | None
    reheld: list[str] = field(default_factory=list)


class _Restore(Exception):
    """A check found something: raised inside the unit (so it restores), caught outside."""

    def __init__(self, failures: list[str]):
        super().__init__("; ".join(failures))
        self.failures = failures


class _TrialRestore(Exception):
    """A trial apply that passed every check: restored all the same, reported applied."""

    def __init__(self, result: ApplyResult):
        super().__init__("trial")
        self.result = result


# ---------------------------------------------------------------- edits

def _applicable(edits: Sequence) -> list:
    return [e for e in edits if not isinstance(e, ProposeOnly)]


_KIND_PROBE = Show(performance_id="", identifier="", artist="", date="")


def _overrule_stage(flag: str) -> str:
    # The kind never depends on the show (only the `titles` subject does).
    key = flag_key(flag, _KIND_PROBE)
    kind = key.kind if key is not None else ""
    if kind.startswith("research-"):
        return "vet"
    if kind.startswith("briefing-"):
        return "brief"
    return "gather"


def _stage_of(e) -> str:
    if isinstance(e, SwitchRecording):
        return "select"
    if isinstance(e, OverruleFlag):
        return _overrule_stage(e.flag)
    return "gather"      # include, exclude, set_title, structure, venue, city


def earliest_stage(edits: Sequence) -> str:
    """The earliest stage (by `SHOW_STAGE_ORDER`) any applicable edit needs. Propose-only
    ops need none; a list of nothing else has no stage (ValueError)."""
    stages = [_stage_of(e) for e in _applicable(edits)]
    if not stages:
        raise ValueError("no applicable edit")
    return min(stages, key=SHOW_STAGE_ORDER.index)


def _structure_files_in_play_order(e: Structure, show: Show) -> list[str]:
    want = set(e.breaks_after)
    return [t.filename for t in show.tracks if t.filename in want]


def write_edits(show_ws: ShowWorkspace, edits: Sequence, *, show: Show, at: str,
                defer_subjectless_structure: bool) -> Overrides:
    """A raw filename-keyed update of `overrides.json` (never `cli._edit_overrides`, never
    a track number). Propose-only ops are ignored. Returns what was written."""
    ov = read_overrides(show_ws)
    exclude, include = list(ov.exclude), list(ov.include)
    titles = dict(ov.titles)
    update: dict = {}
    rules = list(ov.overrules)
    excluded_rows = {x.get("filename"): x for x in show.excluded_files}
    for e in _applicable(edits):
        if isinstance(e, Include):
            reasons = (excluded_rows.get(e.file) or {}).get("reasons") or []
            if OPERATOR_EXCLUDED in reasons or e.file in exclude:
                exclude = [f for f in exclude if f != e.file]
            elif e.file not in include:
                include.append(e.file)
        elif isinstance(e, Exclude):
            if e.file not in exclude:
                exclude.append(e.file)
            include = [f for f in include if f != e.file]
        elif isinstance(e, SetTitle):
            titles[e.file] = e.title
        elif isinstance(e, Structure):
            update["set_breaks"] = _structure_files_in_play_order(e, show)
            update["encore_after"] = e.encore_after
        elif isinstance(e, Venue):
            update["venue"] = e.venue
        elif isinstance(e, City):
            update["city"] = e.city
        elif isinstance(e, SwitchRecording):
            update["recording"] = e.identifier
        elif isinstance(e, OverruleFlag):
            key = flag_key(e.flag, show)
            if (defer_subjectless_structure and key is not None
                    and key.kind in STRUCTURE_KINDS and key.subject is None):
                continue
            rules = merge_rules(rules, records_for([e.flag], show, source="adjudicate", at=at))
    out = ov.model_copy(update={"exclude": exclude, "include": include, "titles": titles,
                                "overrules": rules, **update})
    write_artifact(show_ws.overrides, out)
    return out


# ---------------------------------------------------------------- whole-show check

def capture_before(show: Show) -> list[TrackRow]:
    return [TrackRow(t.filename, t.title, t.title_source, t.set, t.segue, t.duration_sec)
            for t in show.tracks]


def whole_show_diff(before: list[TrackRow], after: Show, edits: Sequence) -> list[str]:
    """Every difference the edits did not predict, one line each; [] when they match."""
    edits = _applicable(edits)
    includes = {e.file for e in edits if isinstance(e, Include)}
    excludes = {e.file for e in edits if isinstance(e, Exclude)}
    titled = {e.file: e.title for e in edits if isinstance(e, SetTitle)}
    struct = next((e for e in edits if isinstance(e, Structure)), None)
    pre = {r.filename: r for r in before}
    post_names = [t.filename for t in after.tracks]
    out: list[str] = []

    predicted = (set(pre) | includes) - excludes
    kept = set(post_names)
    # Every predicted file missing after, an include that did not land included.
    expected = [r.filename for r in before] + [e.file for e in edits if isinstance(e, Include)]
    out += [f"{f}: dropped (not predicted)" for f in dict.fromkeys(expected)
            if f in predicted - kept]
    out += [f"{f}: exclude did not land (not predicted)" for f in post_names if f in excludes]
    out += [f"{f}: added (not predicted)" for f in post_names
            if f in kept - predicted - excludes]

    unnamed = set(pre) - includes - excludes - set(titled)
    # Play order over every kept non-included file (set_title targets too).
    ordered = set(pre) - includes - excludes
    was = [r.filename for r in before if r.filename in ordered and r.filename in kept]
    now = [f for f in post_names if f in ordered]
    if was != now:
        out.append(f"order of kept tracks changed: {was} -> {now} (not predicted)")

    labels: dict[str, str] | None = None
    if struct is not None:
        pos = {f: i for i, f in enumerate(post_names, 1)}
        missing = [f for f in list(struct.breaks_after) + [struct.encore_after]
                   if f is not None and f not in pos]
        if missing:
            out += [f"{f}: structure file not in the track list" for f in missing]
        else:
            enc = pos[struct.encore_after] if struct.encore_after is not None else None
            sets = _sets_from_breaks(len(post_names), [pos[f] for f in struct.breaks_after], enc)
            labels = dict(zip(post_names, sets))

    for t in after.tracks:
        f = t.filename
        if f in includes or f not in pre:
            continue
        b = pre[f]
        if f in titled:
            if t.title != titled[f]:
                out.append(f"{f}: title {t.title!r} (predicted {titled[f]!r})")
            if t.title_source != "override":
                out.append(f"{f}: title_source {t.title_source!r} (predicted 'override')")
        elif f in unnamed:
            if t.title != b.title:
                out.append(f"{f}: title {b.title!r} -> {t.title!r} (not predicted)")
            if t.title_source != b.title_source:
                out.append(f"{f}: title_source {b.title_source!r} -> {t.title_source!r} "
                           f"(not predicted)")
            if struct is None and t.segue != b.segue:
                out.append(f"{f}: segue {b.segue} -> {t.segue} (not predicted)")
        if struct is None:
            if t.set != b.set:
                out.append(f"{f}: set {b.set!r} -> {t.set!r} (not predicted)")
        elif labels is not None and t.set != labels[f]:
            out.append(f"{f}: set {b.set!r} -> {t.set!r} (predicted {labels[f]!r})")
    return out


def _mss(sec: float | None) -> str:
    if sec is None:
        return "?"
    s = int(round(sec))
    return f"{s // 60}:{s % 60:02d}"


def track_changes(before: list[TrackRow], after: Show) -> list[str]:
    """For the run report, from before and after (not from the edits): changed and added
    tracks in the after order, then removed ones in the before order."""
    pre = {r.filename: r for r in before}
    names = {t.filename for t in after.tracks}
    out: list[str] = []
    for t in after.tracks:
        b = pre.get(t.filename)
        if b is None:
            out.append(f"+ {t.filename} ({_mss(t.duration_sec)}) {t.title}")
            continue
        if t.title != b.title:
            out.append(f"~ {t.filename}: {b.title!r} -> {t.title!r}")
        if t.set != b.set:
            out.append(f"~ {t.filename}: set {b.set} -> {t.set}")
    out += [f"- {r.filename} ({_mss(r.duration_s)}) {r.title}" for r in before
            if r.filename not in names]
    return out


# ---------------------------------------------------------------- flag checks

def _key(flag: str, show: Show):
    k = flag_key(flag, show)
    return k if k is not None else flag


def silenced_flags(pre: Show, post: Show, verdict: Verdict, gate: GateResult | None, *,
                   mode: Mode) -> list[str]:
    """Pre-apply flags whose key is gone after the apply and that the verdict does not
    account for: in `auto`, a judgement passing `flag_passes`; in `accept`, any judgement
    `spurious` or `real-fixed-by-action` (Shawn's acceptance replaces the bar)."""
    after = {_key(f, post) for f in post.review_flags}
    judged = {j.flag: j for j in verdict.flags}
    out: list[str] = []
    for f in pre.review_flags:
        if _key(f, pre) in after:
            continue
        j = judged.get(f)
        if j is not None:
            if mode == "accept" and j.verdict in ("spurious", "real-fixed-by-action"):
                continue
            if mode == "auto" and gate is not None and flag_passes(j, pre, verdict, gate):
                continue
        out.append(f)
    return out


def _dur_sum(tracks, *, unknown: float) -> float:
    return sum(unknown if t.duration_sec is None else t.duration_sec for t in tracks)


def coverage_failures(pre: Show, post: Show, *, mode: Mode) -> list[str]:
    """A switch's coverage check against the pre-switch track list; [] passes."""
    out: list[str] = []
    post_titles = {normalize_song(t.title) for t in post.tracks if is_resolved_song(t)}
    missing = [t.title for t in pre.tracks
               if is_resolved_song(t) and normalize_song(t.title) not in post_titles]
    if missing:
        out.append(f"missing title: {', '.join(missing)} not in the new recording")
    unknown = sum(t.duration_sec is None for t in list(pre.tracks) + list(post.tracks))
    pre_total, post_total = _dur_sum(pre.tracks, unknown=0.0), _dur_sum(post.tracks, unknown=0.0)
    if unknown:
        out.append(f"total duration: {unknown} track(s) of unknown length; cannot compare")
    elif post_total < pre_total:
        out.append(f"total duration: {post_total:.1f} s is below the current {pre_total:.1f} s")

    def weak(show, unknown):
        return _dur_sum([t for t in show.tracks if t.title_source == "unresolved" or t.short_kept],
                        unknown=unknown)
    added = weak(post, math.inf) - weak(pre, 0.0)
    if added > COVERAGE_ADDED_MAX_S:
        out.append(f"added duration: {added:.1f} s on untitled or short-kept tracks is over "
                   f"{COVERAGE_ADDED_MAX_S:.0f} s")
    if mode == "auto":
        n_res = sum(map(is_resolved_song, post.tracks)), sum(map(is_resolved_song, pre.tracks))
        if not (len(post.tracks) > len(pre.tracks) or n_res[0] > n_res[1]):
            out.append("gain: the new recording adds neither tracks nor resolved titles")
        if post.needs_review:
            out.append(f"held: the new recording is held ({'; '.join(post.review_flags)})")
    return out


def rehold_flags(pre: Show, post: Show, verdict: Verdict, gate: GateResult) -> list[str] | None:
    """The post flags to auto-overrule, all or nothing: each must carry the full key of a
    pre-apply flag judged spurious at a passing bar. Never `alignment`, never a duration
    mismatch (no key), never a subject-less structure kind after a track-list or
    structure edit. None when any post flag does not qualify, or there is none."""
    if not post.review_flags:
        return None
    no_subjectless = has_track_list_or_structure_edit(verdict)
    passing_keys = set()
    judged = {j.flag: j for j in verdict.flags}
    for f in pre.review_flags:
        j = judged.get(f)
        k = flag_key(f, pre)
        if (k is not None and j is not None and j.verdict == "spurious"
                and flag_passes(j, pre, verdict, gate)):
            passing_keys.add(k)
    for f in post.review_flags:
        k = flag_key(f, post)
        if k is None or k.kind == "alignment":
            return None
        if no_subjectless and k.kind in STRUCTURE_KINDS and k.subject is None:
            return None
        if k not in passing_keys:
            return None
    return list(post.review_flags)


# ---------------------------------------------------------------- the ledger

class _LedgerUndo:
    """The ledger row this unit's redo may add, and its removal on a restore.

    `process_show` records exactly one row kind: (candidate pid, `selected`, the
    provenance run), and `Ledger.record` is append-once on that key. Taken inside the unit
    (show lock held) before any redo: if a row of the key already exists, the redo can add
    nothing and the undo is a no-op; otherwise a restore removes every row of the key,
    compared parsed (a concurrent `remove`/`remove_status` rewrite re-serializes lines, so
    raw bytes are no identity). Only a holder of this show's lock runs `process_show` for
    it, so such a row is this unit's; a row of another run or status, or another show, is
    never touched. That argument assumes the show dir is `shows/<slugify(pid)>` (one lock
    per pid): a hand-renamed show dir is outside the guarantee, as for `show_unit`
    (limitation 4). An absent `ledger.jsonl` the redo created is left as a 0-byte file
    (readers treat it as empty). No readable provenance means the redo refuses before
    `process_show`, so there is nothing to undo."""

    def __init__(self, ledger: Ledger, show_ws: ShowWorkspace):
        self.ledger = ledger
        self.interrupt: BaseException | None = None   # a non-Exception raised by the removal
        try:
            prov = read_model(show_ws.provenance, Provenance)
        except Exception:      # noqa: BLE001 - missing or unreadable: no redo can record
            self.key = None
            return
        self.key = (prov.candidate.performance_id, "selected", prov.run)
        self.existed = ledger.has_row(*self.key)

    def undo(self) -> str | None:
        """Remove the added rows; never raises. A note when the removal failed; a
        KeyboardInterrupt (or other non-Exception) during it is kept in `interrupt` for
        the caller to re-raise once the original path has run."""
        if self.key is None or self.existed:
            return None
        try:
            self.ledger.remove_added(*self.key)
        except BaseException as exc:      # noqa: BLE001 - never mask the restore
            note = (f"ledger: could not remove the {self.key[1]} row this apply added for "
                    f"{self.key[0]} (run {self.key[2]}): {exc!r}")
            log.warning("%s", note)
            if not isinstance(exc, Exception):
                self.interrupt = exc
            return note
        return None


def _with_note(text: str | None, note: str | None) -> str | None:
    if note is None:
        return text
    return note if not text else f"{text}; {note}"


# ---------------------------------------------------------------- the unit

def _held_in(view: ShowView) -> bool:
    """Whether the show as the caller saw it (and as a restore leaves it) is held."""
    if view.show is None:
        return True
    return Show.model_validate_json(view.show).needs_review


def apply_verdict(show_ws: ShowWorkspace, verdict: Verdict, *, expect: ShowView, redo: Redo,
                  mode: Mode, gate: GateResult | None,
                  on_commit: Callable[[Show, ApplyResult], None], trial: bool = False,
                  at: str, ledger: Ledger) -> ApplyResult:
    """Apply `verdict` in one `show_unit`. `gate` is the verdict's GateResult in `auto` and
    None in `accept`. `on_commit` writes the applied record inside the unit. RateLimited,
    ShowChanged and KeyboardInterrupt propagate after the unit has restored the files.
    Every restore (a trial included) first removes the ledger row the redo added, under
    the show lock and before the files come back (`_LedgerUndo`); a failure to do so is
    added to the outcome's `error` (or to the propagating exception's notes), never in
    place of it. A KeyboardInterrupt during that removal is re-raised only after the
    restore and the outcome, with the outcome in its notes."""
    if mode == "auto" and gate is None:
        raise ValueError("auto mode needs the verdict's GateResult")
    edits = _applicable(verdict.edits)
    is_switch = any(isinstance(e, SwitchRecording) for e in edits)
    if is_switch:
        others = [e.op for e in edits if not isinstance(e, (SwitchRecording, Venue))]
        if others:
            # A switch is checked by coverage only, never by the whole-show diff, and
            # `accept` skips the gate that keeps a switch alone: refuse before writing.
            return ApplyResult("refused", _held_in(expect), [], [],
                               f"switch_recording cannot be applied with other edits "
                               f"({', '.join(others)}); only venue may accompany it", [])
    undos: list[_LedgerUndo] = []
    try:
        res = _run_unit(show_ws, verdict, edits, is_switch, expect=expect, redo=redo,
                        mode=mode, gate=gate, on_commit=on_commit, trial=trial, at=at,
                        ledger=ledger, undos=undos)
    except BaseException as exc:
        pending = undos[0].interrupt if undos else None
        if pending is not None and isinstance(exc, Exception):
            pending.add_note(f"after the apply was restored: {exc!r}")
            raise pending from exc
        raise
    pending = undos[0].interrupt if undos else None
    if pending is not None:
        # Ctrl-C during the ledger removal: the files are restored and the outcome
        # decided; stop now rather than let a batch carry on past the operator's interrupt.
        pending.add_note(f"after the apply was restored: {res.status}: "
                         + "; ".join(res.diff + ([res.error] if res.error else [])))
        raise pending
    return res


def _run_unit(show_ws: ShowWorkspace, verdict: Verdict, edits: list, is_switch: bool, *,
              expect: ShowView, redo: Redo, mode: Mode, gate: GateResult | None,
              on_commit: Callable[[Show, ApplyResult], None], trial: bool, at: str,
              ledger: Ledger, undos: list) -> ApplyResult:
    """The unit and its outcome; `undos` receives the unit's `_LedgerUndo`."""
    note: str | None = None      # a failed ledger removal, reported with the outcome
    try:
        with show_unit(show_ws, expect):
            undo = _LedgerUndo(ledger, show_ws)
            undos.append(undo)
            try:
                return _apply_in_unit(show_ws, verdict, edits, is_switch, redo=redo, mode=mode,
                                      gate=gate, on_commit=on_commit, trial=trial, at=at)
            except BaseException as exc:
                # Under the show lock, before show_unit restores the files: no other
                # unit of this show can have recorded meanwhile.
                note = undo.undo()
                if note is not None:
                    exc.add_note(note)
                raise
    except _TrialRestore as t:
        return replace(t.result, status="applied",
                       error=_with_note(t.result.error, note))
    except _Restore as r:
        return ApplyResult("restored", _held_in(expect), r.failures, [],
                           note, [])
    except (RateLimited, ShowChanged):
        raise
    except (IAError, TaskFailed, HerderError) as exc:
        return ApplyResult("transient", _held_in(expect), [], [],
                           _with_note(str(exc), note), [])
    except (StationUnpaired, StationUnreadable, LlamaError) as exc:
        return ApplyResult("refused", _held_in(expect), [], [],
                           _with_note(str(exc), note), [])


def _apply_in_unit(show_ws: ShowWorkspace, verdict: Verdict, edits: list, is_switch: bool, *,
                   redo: Redo, mode: Mode, gate: GateResult | None,
                   on_commit: Callable[[Show, ApplyResult], None], trial: bool,
                   at: str) -> ApplyResult:
    """The unit's body; raises `_Restore`/`_TrialRestore` to restore."""
    pre = read_model(show_ws.show, Show)
    before = capture_before(pre)
    write_edits(show_ws, edits, show=pre, at=at,
                defer_subjectless_structure=has_track_list_edit(verdict))
    redo(earliest_stage(edits))
    post = read_model(show_ws.show, Show)
    if is_switch:
        failures = coverage_failures(pre, post, mode=mode)
    else:
        failures = whole_show_diff(before, post, edits)
    failures += [f"flag silenced without a passing judgement: {f}"
                 for f in silenced_flags(pre, post, verdict, gate, mode=mode)]
    if failures:
        raise _Restore(failures)
    reheld: list[str] = []
    if mode == "auto" and post.needs_review:
        flags = rehold_flags(pre, post, verdict, gate)
        if flags is not None:
            ov = read_overrides(show_ws)
            write_artifact(show_ws.overrides, ov.model_copy(update={
                "overrules": merge_rules(ov.overrules, records_for(
                    flags, post, source="adjudicate", at=at))}))
            write_artifact(show_ws.show, post.model_copy(
                update={"needs_review": False, "review_flags": []}))
            redo("package")
            post = read_model(show_ws.show, Show)
            reheld = flags
    result = ApplyResult("applied", post.needs_review, [], track_changes(before, post),
                         None, reheld)
    on_commit(post, result)
    if trial:
        raise _TrialRestore(result)
    return result
