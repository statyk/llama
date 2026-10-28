#!/usr/bin/env python3
"""The bulk-apply campaign's operator script (plan Task 12 scaffold).

Subcommands: `pin` (pin the campaign to a release tag's commit), `arm` (the replay arm,
behind the version and pin gates), `snapshot` / `seal` / `restore` (thin wrappers over
`llama.batch_snapshot`) and `backfill` (plan Task 14: the overrule backfill from the
overnight verdicts, dry run unless `--apply`); plan Task 15: `freeze` (the frozen needs-LLM
list), `reselect-check` (the verified re-selection list, re-checked read-only), `mark` (the
marking batch, dry run unless `--apply`) and `unmark` (its reversal, by its record); plan
Tasks 16-17: `lists` (wave lists and `--counts`), `wave-check` (a list's read-only gate),
`spot-check` (a finished batch's sample), `revoice-list` (the ranked re-voice list for voiced
marked shows) and `trial-report` (the trial's cost projection). A
refused gate exits 2. Run with the pinned worktree's own interpreter:
`./.venv/bin/python scripts/bulk_apply.py ...`.
"""
import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

import replay_holds
from herder.usage import same_window

import llama
import llama.replay
from llama import batch_snapshot, campaign, reapply, station_mark
from llama.campaign_gate import (_VERSION, GateRefused, read_pin, require_pinned_code,
                                 require_tools, retire_rekey_restore, write_pin)
from llama.catalog import _performance_id, _sync_fd, derive_state
from llama.config import DEFAULT_ROOT, load_config
from llama.errors import LlamaError
from llama.ledger import Ledger, is_delivered
from llama.locks import file_lock
from llama.models import Overrule, Provenance, QualityAssessment, Show
from llama.override_keys import refusal as overrides_refusal
from llama.overrules import flag_key, merge_rules, records_for, split_overruled
from llama.replay import (CacheMiss, CacheOnlyIA, code_identity, config_fingerprint,
                          input_digests, row_label_only, row_visible_changes)
from llama.stages.select_recording import run_select_recording
from llama.station_mark import destination_voiced
from llama.show_unit import show_unit
from llama.workspace import ShowWorkspace, read_model, read_overrides, write_artifact

REPO = Path(__file__).resolve().parent.parent


def _echo(msg: str) -> None:
    print(msg)


def _config(args):
    path = args.config or DEFAULT_ROOT / "config.toml"
    if args.config is not None and not args.config.exists():
        raise GateRefused(f"no such config: {args.config}")
    return load_config(path)


def cmd_pin(args) -> int:
    root = _config(args).root
    done = subprocess.run(["git", "-C", str(REPO), "rev-parse", f"{args.tag}^{{commit}}"],
                          capture_output=True, text=True)
    if done.returncode != 0:
        raise GateRefused(f"cannot resolve tag {args.tag} in {REPO}: {done.stderr.strip()}")
    sha = done.stdout.strip()
    ident = code_identity()
    if ident != sha:
        raise GateRefused(f"the running code is {ident}, not {args.tag} ({sha}); pin from a "
                          f"clean checkout of the tag")
    version = args.tag[1:] if args.tag.startswith("v") else args.tag
    if not _VERSION.fullmatch(version):
        raise GateRefused(f"tag {args.tag} is not a release version tag (vX.Y.Z)")
    pin = write_pin(root, tag=args.tag, sha=sha, version=version,
                    worktree=str(REPO), replace=args.replace)
    print(f"pinned {pin['tag']} {sha} ({pin['version']}) at {root / 'campaign' / 'pin.json'}")
    return 0


def cmd_arm(args) -> int:
    config = _config(args)
    pin = require_pinned_code(config.root)
    require_tools(_echo, pin=pin)
    ns = argparse.Namespace(out=args.out, held=False, all=True, slugs=None,
                            strip_structure_overrides=False, strip_title_overrides=False,
                            rekey_overrides=False, disable_slices=None, config=args.config,
                            scratch=None)
    try:
        return replay_holds.run(ns)
    except replay_holds.Refusal as err:
        raise GateRefused(str(err)) from err


def _read_slugs(path: Path) -> list[str]:
    return [l.strip() for l in path.read_text().splitlines() if l.strip()]


def _station_root(config) -> Path | None:
    return config.delivery_path


def cmd_snapshot(args) -> int:
    config = _config(args)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = config.root / "campaign" / "snapshots" / stamp
    batch_snapshot.take(snap, config.root, _read_slugs(args.slugs),
                        station_root=_station_root(config))
    print(f"snapshot: {snap}")
    return 0


def cmd_seal(args) -> int:
    config = _config(args)
    batch_snapshot.seal(args.snap, config.root, station_root=_station_root(config))
    print(f"sealed: {args.snap}")
    return 0


def cmd_restore(args) -> int:
    config = _config(args)
    slugs = set(_read_slugs(args.slugs)) if args.slugs else None
    results = batch_snapshot.restore(args.snap, config.root, station_root=_station_root(config),
                                     apply=args.apply, slugs=slugs, echo=_echo)
    if not args.apply:
        print("dry run: nothing written (pass --apply)")
    return 0 if not any(a.startswith("refused") for _, a in results) else 1


# --- backfill (plan Task 14; spec "Overrules persist" (Backfill), "Undo", "Rollout") ---

NO_VERDICT = "no verdict"
NEVER_RULED = "verdict never ruled on this flag"
OTHER_ONLY = "only in other_flags (free text)"
NOT_OVERRULABLE = "not overrulable (package flag)"
NO_TITLES = "cannot derive the unresolved files"
NO_SHOW_JSON = "no show.json"
# Each layout's false-hold verdict value: `flags[].verdict` (layout A), `claims[].verdict`
# (layout B). A value is honoured only in its own layout.
_RECORDED = (("flags", "spurious"), ("claims", "flag-spurious"))
# Checkpoint A rulings (plan Task 14b). Rules (a) and (b) record only a flag still listed
# for one of these two reasons, never one of these rulings, and never their rule's kinds:
# a rehold overrule (b) covers unknown songs (T14c parent ruling: the adjudicator
# reviewed each re-hold whole), a fix verdict (a) does not.
_STILL_LISTED = (NEVER_RULED, OTHER_ONLY)
_NEVER_KINDS_A = frozenset({"titles", "research-song"})
_NEVER_KINDS_B = frozenset({"titles"})
_NEVER_RULINGS = frozenset({"research-wrong", "research-right-show-wrong"})
_STRUCTURE_KINDS = frozenset({"jerrybase-set-count", "jerrybase-closer", "research-sets",
                              "sets-not-found", "venue", "city"})
# Each basis's note prefix (the path follows) and its dry-run label, in precedence order.
_BASES = (("backfill verdict: ", "verdict"),
          ("backfill rule a (verdict action fix): ", "rule a"),
          ("backfill rule b (rehold overrule): ", "rule b"),
          ("backfill rule c (delivered, no verdict): ", "rule c"),
          ("backfill rule d (overrule_if_reheld_on, not raised by the base arm): ", "rule d"))


class BackfillShow(NamedTuple):
    slug: str
    record: list[Overrule]             # the overrules to record
    listed: list[tuple[str, str]]      # (base flag, why it is not recorded)
    show_reason: str | None            # show-level reason nothing is recorded, else None


def _base_rows(base: dict) -> list[dict]:
    rows = base.get("shows") if isinstance(base, dict) else None
    if isinstance(rows, dict):
        rows = list(rows.values())
    if not isinstance(rows, list) or not all(isinstance(r, dict) and isinstance(r.get("slug"), str)
                                             for r in rows):
        raise LlamaError("the base arm has no `shows` rows with a slug")
    return sorted(rows, key=lambda r: r["slug"])


def _considered(row: dict) -> bool:
    return row.get("outcome") == "newly-held" and row.get("state") != "held"


def _verdict(verdicts: Path, slug: str, what: str = "verdict") -> dict | None:
    path = verdicts / f"{slug}.json"
    if not path.exists():
        return None
    try:
        v = json.loads(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise LlamaError(f"{path} unreadable ({exc}); nothing planned") from exc
    if not isinstance(v, dict):
        raise LlamaError(f"{path} is not a {what} object; nothing planned")
    return v


def _rulings(v: dict) -> tuple[dict[str, list[tuple[str, bool]]], list[str], set[str]]:
    """(flag -> [(verdict, is that layout's false-hold value)], flags named by
    `action.overrule_if_reheld_on` in their order, `other_flags` texts)."""
    ruled: dict[str, list[tuple[str, bool]]] = {}
    for key, value in _RECORDED:
        for e in v.get(key) or []:
            if isinstance(e, dict) and isinstance(e.get("flag"), str):
                ruled.setdefault(e["flag"], []).append(
                    (str(e.get("verdict")), e.get("verdict") == value))
    action = v.get("action")
    oir = action.get("overrule_if_reheld_on") if isinstance(action, dict) else None
    named = list(dict.fromkeys(f for f in oir or [] if isinstance(f, str)))
    other = {e["flag"] for e in v.get("other_flags") or []
             if isinstance(e, dict) and isinstance(e.get("flag"), str)}
    return ruled, named, other


def _titles_rule(flag: str, show: Show, row: dict, at: str,
                 note: str | None = None) -> Overrule | None:
    """The `titles` overrule built from the BASE row's `title_sources` (the files that
    were unresolved when the verdict was made), never from today's show.json. None when
    the base positions cannot be mapped onto today's track list."""
    sources = row.get("title_sources")
    if not isinstance(sources, list) or len(sources) != len(show.tracks):
        return None
    names = sorted(t.filename for t, src in zip(show.tracks, sources) if src == "unresolved")
    if not names:
        return None
    return Overrule(identifier=show.identifier, kind="titles", subject=names, flag=flag,
                    source="backfill", at=at, note=note)


def _record(flag: str, kind: str, show: Show, row: dict, at: str,
            note: str) -> Overrule | None:
    """One overrulable flag's record carrying its basis `note`; a `titles` flag through
    `_titles_rule` (None when it cannot derive the files)."""
    if kind == "titles":
        return _titles_rule(flag, show, row, at, note)
    [rule] = records_for([flag], show, source="backfill", at=at)
    return rule.model_copy(update={"note": note})


def _basis(rule: Overrule) -> str:
    """The dry-run label of the basis a backfill rule's note names."""
    return next(label for prefix, label in _BASES if (rule.note or "").startswith(prefix))


def _plan_one(root: Path, row: dict, verdicts: Path, delivered: set[str], at: str,
              rehold: Path | None = None, base_path: Path | None = None
              ) -> BackfillShow | None:
    """One base row's plan; None when it is not considered (the base outcome or state,
    or the show is held today). Today's rule first, then the Checkpoint A rulings (a),
    (b), (c); (d) adds `overrule_if_reheld_on` flags the base arm did not raise. A flag
    is recorded once, under the first basis that records it, its note naming that basis."""
    if not _considered(row):
        return None
    slug = row["slug"]
    ws = ShowWorkspace(root / "shows" / slug)
    if not ws.show.exists():
        return BackfillShow(slug, [], [], NO_SHOW_JSON)
    try:
        state = derive_state(ws, delivered)[0]
        if state == "held":
            return None
        show = read_model(ws.show, Show)
    except Exception as exc:
        return BackfillShow(slug, [], [], f"show.json unreadable: {' '.join(str(exc).split())}")
    v = _verdict(verdicts, slug)
    rv = _verdict(rehold, slug, "rehold verdict") if rehold is not None else None
    flags = (list(row.get("gather_flags") or []) + list(row.get("vet_flags") or [])
             + list(row.get("brief_flags") or []))
    record: list[Overrule] = []
    listed: list[tuple[str, str]] = []

    def take(f: str, kind: str, note: str) -> None:
        rule = _record(f, kind, show, row, at, note)
        if rule is None:
            listed.append((f, NO_TITLES))
        else:
            record.append(rule)

    if v is None:
        if state != "delivered":
            return BackfillShow(slug, [], [], NO_VERDICT)
        # (c): the operator delivered the show, i.e. accepted every flag; no exclusions.
        note_c = _BASES[3][0] + str(base_path if base_path is not None else "the base arm")
        for f in flags:
            key = flag_key(f, show)
            if key is None:
                listed.append((f, NOT_OVERRULABLE))
            else:
                take(f, key.kind, note_c)
        return BackfillShow(slug, record, listed, None)
    vpath = verdicts / f"{slug}.json"
    ruled, named, other = _rulings(v)
    action = v.get("action")
    fix = isinstance(action, dict) and action.get("kind") == "fix"
    reheld = rv is not None and rv.get("decision") == "overrule"
    for f in flags:
        key = flag_key(f, show)
        if key is None:
            listed.append((f, NOT_OVERRULABLE))
            continue
        rulings = ruled.get(f, [])
        if f in named or (rulings and all(ok for _, ok in rulings)):
            take(f, key.kind, _BASES[0][0] + str(vpath))
            continue
        if rulings:
            why = f"ruled {next(vd for vd, ok in rulings if not ok)}"
        elif f in other:
            why = OTHER_ONLY
        else:
            why = NEVER_RULED
        eligible = (why in _STILL_LISTED
                    and not any(vd in _NEVER_RULINGS for vd, _ in rulings))
        if (eligible and fix and key.kind in _STRUCTURE_KINDS
                and key.kind not in _NEVER_KINDS_A):
            take(f, key.kind, _BASES[1][0] + str(vpath))
        elif eligible and reheld and key.kind not in _NEVER_KINDS_B:
            take(f, key.kind, _BASES[2][0] + str(rehold / f"{slug}.json"))
        else:
            listed.append((f, why))
    # (d): flags the verdict says to overrule if re-held on, which the base arm did not
    # raise; one it cannot record is skipped, never listed.
    for f in named:
        if f in flags:
            continue
        key = flag_key(f, show)
        if key is None:
            continue
        rule = _record(f, key.kind, show, row, at, _BASES[4][0] + str(vpath))
        if rule is not None:
            record.append(rule)
    return BackfillShow(slug, record, listed, None)


def plan_backfill(root: Path, base: dict, verdicts: Path, delivered: set[str],
                  rehold: Path | None = None, *,
                  base_path: Path | None = None) -> list[BackfillShow]:
    """Every base row newly held under the pre-piece-4 code (outcome `newly-held`, state
    not `held`) whose show is not held today, with the overrules to record and the flags
    listed for the operator. `delivered` is the ledger's delivered performance ids (as
    `llama status` derives state); `rehold` the optional rehold-verdicts directory (rule
    b); `base_path` the base arm's path, named by rule (c)'s note. Reads only."""
    at = datetime.now(timezone.utc).isoformat()
    out = []
    for row in _base_rows(base):
        planned = _plan_one(root, row, verdicts, delivered, at, rehold, base_path)
        if planned is not None:
            out.append(planned)
    return out


def _print_plan(plan: list[BackfillShow], rows: dict[str, dict], verdicts: Path) -> None:
    for s in plan:
        if s.show_reason is not None:
            print(f"{s.slug}: {s.show_reason}")
            row = rows.get(s.slug, {})
            for f in (list(row.get("gather_flags") or []) + list(row.get("vet_flags") or [])
                      + list(row.get("brief_flags") or [])):
                print(f"  base flag: {f}")
            continue
        print(f"{s.slug}:")
        for r in s.record:
            basis = _basis(r)
            print(f"  record: {r.flag}" + ("" if basis == "verdict" else f" ({basis})"))
        for f, why in s.listed:
            print(f"  list: {f} ({why})")
    per_flag = [s for s in plan if s.show_reason is None]
    covered = sum(1 for s in per_flag if s.record and not s.listed)
    other = sum(1 for s in plan if s.show_reason not in (None, NO_VERDICT))
    # A rule-(c) show is planned per flag but still has no verdict file.
    no_verdict = sum(s.show_reason == NO_VERDICT
                     or (s.show_reason is None and not (verdicts / f"{s.slug}.json").exists())
                     for s in plan)
    line = (f"totals: shows considered {len(plan)}, "
            f"shows with no verdict {no_verdict}, "
            f"flags recorded {sum(len(s.record) for s in plan)}, "
            f"flags listed {sum(len(s.listed) for s in plan)}, "
            f"shows fully covered {covered} of {len(per_flag)}")
    if other:
        line += f", shows listed for another reason {other}"
    print(line)
    by = Counter(_basis(r) for s in plan for r in s.record)
    print("recorded by basis: " + ", ".join(f"{label} {by[label]}" for _, label in _BASES))


def _append_jsonl(path: Path, row: dict) -> None:
    line = (json.dumps(row) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        view = memoryview(line)
        while view:
            view = view[os.write(fd, view):]
        _sync_fd(fd)
    finally:
        os.close(fd)
    batch_snapshot._sync_dir(path.parent)


def _new_rules(ws: ShowWorkspace, rules: list[Overrule]) -> list[Overrule]:
    """The rules `merge_rules` would add to the show's stored overrules."""
    existing = read_overrides(ws).overrules
    return merge_rules(existing, rules)[len(existing):]


def _backfill_one(snap: Path, record: Path, root: Path, row: dict, verdicts: Path,
                  delivered: set[str], station_root: Path | None, at: str,
                  rehold: Path | None = None, base_path: Path | None = None) -> str:
    """One show's unit, inside `show_unit` (which takes the show lock): re-plan, re-read
    `overrides.json`, merge, write, then `record_after` (the show's final state; nothing
    tracked is written after it) and the batch record. Any failure, Ctrl-C included,
    restores every file outside `package/audio/`, so a write the batch could not record
    is undone and every recorded write stays restorable (spec "Undo")."""
    slug = row["slug"]
    ws = ShowWorkspace(root / "shows" / slug)
    with show_unit(ws, None):
        planned = _plan_one(root, row, verdicts, delivered, at, rehold, base_path)
        if planned is None or not planned.record:
            return "skipped: changed since the plan (held now, or nothing to record)"
        if ws.overrides.exists():
            data = json.loads(ws.overrides.read_text())
            refused = overrides_refusal(slug, data) if isinstance(data, dict) else None
            if refused is not None:
                raise LlamaError(refused)
        ov = read_overrides(ws)
        merged = merge_rules(ov.overrules, planned.record)
        added = merged[len(ov.overrules):]
        if not added:
            return "nothing new"
        write_artifact(ws.overrides, ov.model_copy(update={"overrules": merged}))
        batch_snapshot.record_after(snap, slug, root, station_root=station_root)
        _append_jsonl(record, {"slug": slug, "at": at,
                               "added": [r.model_dump() for r in added]})
    return f"recorded {len(added)}"


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def cmd_backfill(args) -> int:
    config = _config(args)
    root = config.root
    if args.apply:
        pin = require_pinned_code(root)
        require_tools(_echo, pin=pin)
    try:
        base = json.loads(args.base.read_bytes())
    except (OSError, ValueError) as exc:
        raise LlamaError(f"{args.base} unreadable ({exc})") from exc
    if not args.verdicts.is_dir():
        raise LlamaError(f"no verdicts directory {args.verdicts}")
    if args.rehold_verdicts is not None and not args.rehold_verdicts.is_dir():
        raise LlamaError(f"no rehold-verdicts directory {args.rehold_verdicts}")
    delivered = {e.performance_id for e in Ledger(root / "ledger.jsonl").entries()
                 if e.status == "delivered"}
    plan = plan_backfill(root, base, args.verdicts, delivered, args.rehold_verdicts,
                         base_path=args.base)
    rows = {r["slug"]: r for r in _base_rows(base)}
    _print_plan(plan, rows, args.verdicts)
    if not args.apply:
        print("dry run: nothing written (pass --apply)")
        return 0
    targets, failed = [], []
    for s in plan:
        if not s.record:
            continue
        try:
            if _new_rules(ShowWorkspace(root / "shows" / s.slug), s.record):
                targets.append(s.slug)
        except Exception as exc:
            print(f"{s.slug}: error: overrides.json unreadable: {' '.join(str(exc).split())}")
            failed.append(s.slug)
    if not targets:
        print("nothing to record: every planned overrule is already present"
              + (f"; {len(failed)} failed" if failed else ""))
        return 1 if failed else 0
    station_root = _station_root(config)
    stamp = _stamp()
    bdir = root / "campaign" / "backfill" / stamp
    if bdir.exists():
        raise LlamaError(f"refusing to back-fill: {bdir} exists")
    snap = bdir / "snapshot"
    batch_snapshot.take(snap, root, targets, station_root=station_root)
    print(f"snapshot: {snap}")
    at = datetime.now(timezone.utc).isoformat()
    retire_rekey_restore(root, by=f"bulk-apply overrule backfill {stamp}", at=at)
    record = bdir / "record.jsonl"
    written = 0
    for slug in targets:
        try:
            outcome = _backfill_one(snap, record, root, rows[slug], args.verdicts, delivered,
                                    station_root, at, args.rehold_verdicts, args.base)
        except Exception as exc:
            outcome = f"error: {' '.join(str(exc).split())}"
            failed.append(slug)
        else:
            written += outcome.startswith("recorded")
        print(f"{slug}: {outcome}")
    print(f"backfill {stamp}: {written} written, {len(failed)} failed; record: {record}")
    return 1 if failed else 0


# --- marking (plan Task 15; spec "The `awaiting_fix` contract" (Who gets marked, Writing a
# mark, The marking batch, No concurrent emcee), "The library side" (Marking skips),
# "Re-processing" (GD re-selections)) ---

FROZEN_NAME = "needs-llm-frozen.json"
RESELECTIONS_NAME = "reselections.json"
BACKUP_NAME = "station-backup"
RESELECTIONS_STALE = ("reselections.json predates the arm; re-run: "
                      "bulk_apply.py reselect-check --write")
REASON_CHANGED = "changed by the held-backlog fixes"
REASON_LLM = "replay needs an LLM call"
REASON_GUARD = "stored briefing fails today's guard"
REASON_RESELECTION = "recording re-selection"
REASON_NEWLY_HELD = "newly held by today's checks"
_REASON_KINDS = (REASON_CHANGED, REASON_LLM, REASON_GUARD, REASON_RESELECTION,
                 REASON_NEWLY_HELD)
# Rows whose diff comes from the provider-less fallback alignment (an artefact): they are
# marked only by a re-selection or by the frozen list, never by a visible change.
_NO_DIFF = ("needs-llm", "unreplayable")
_PLAN_COLUMNS = ("delivered unvoiced", "delivered voiced", "packaged", "briefed", "held")
# Exit 0 only when every delivered item's last record line is one of these (the brief's
# rule, literally: "no station copy" is listed too). "not delivered" lines never count.
_STATION_OK = ("marked", "already marked")
_NOT_DELIVERED = "not delivered"
# Task 15b (M1): the station copy carries this batch's mark, but its reversal evidence
# is not (yet) on record. Neither is `refused` (the station IS marked); both are listed
# and retried by a re-run, which records `marked` once the before copy is verified.
_UNSAVED = "marked, before copy not saved"
_UNVERIFIED = "marked by this batch, no verified before copy"
_RETRIED = ("refused", _UNSAVED, _UNVERIFIED)


class MarkItem(NamedTuple):
    slug: str
    reason: str
    start_stage: str                 # "gather" | "select"
    digests: dict | None             # the arm row's input digests; None: not checked
    state: str = ""                  # for the plan's table only; the apply re-reads it


def _one_line(exc: BaseException) -> str:
    return " ".join(str(exc).split()) or type(exc).__name__


def _campaign_dir(root: Path, campaign_dir: Path | None) -> Path:
    return campaign_dir if campaign_dir is not None else root / "campaign"


def _write_durable(path: Path, data: bytes) -> None:
    batch_snapshot._durable_replace(path, data)
    batch_snapshot._sync_dir(path.parent)


def _write_json(path: Path, obj) -> None:
    _write_durable(path, (json.dumps(obj, indent=2) + "\n").encode())


def _arm_rows(arm: dict) -> dict[str, dict]:
    rows = arm.get("shows") if isinstance(arm, dict) else None
    if not isinstance(rows, dict) or not all(isinstance(r, dict) for r in rows.values()):
        raise LlamaError("the arm has no `shows` rows")
    return rows


def freeze(root: Path, arm: dict, *, campaign_dir: Path | None = None) -> Path:
    """`<campaign>/needs-llm-frozen.json`: the arm's needs-LLM slugs (spec "Who gets
    marked": the frozen needs-LLM list). Written once; an existing file refuses."""
    path = _campaign_dir(root, campaign_dir) / FROZEN_NAME
    if path.exists():
        raise LlamaError(f"refusing to freeze: {path} exists (the list is frozen once)")
    slugs = sorted(s for s, r in _arm_rows(arm).items() if r.get("outcome") == "needs-llm")
    _write_json(path, {"arm_sha": arm.get("sha"), "arm_generated_at": arm.get("generated_at"),
                       "slugs": slugs})
    return path


def _source_slug(row) -> str:
    slug = row.get("slug") or row.get("show") if isinstance(row, dict) else None
    if not isinstance(slug, str) or not slug:
        raise LlamaError(f"a re-selection source row names no show: {row!r}"[:300])
    return slug


def reselect_rows(root: Path, config, source: list[dict]) -> list[dict]:
    """The verified re-selection list, re-checked: per source row, the stored recording
    (show.json) against the one selection picks now, run into a scratch ShowWorkspace under
    a temporary directory (never under the library) from the metadata cache only. Rows
    whose pick equals the stored recording (already re-selected) and voiced delivered
    shows (spec: voiced shows are not re-selected) are dropped. Writes nothing under
    `root`; a show it cannot check refuses the whole check."""
    ledger = Ledger(root / "ledger.jsonl")
    ia = CacheOnlyIA(root / "cache")
    out = []
    with tempfile.TemporaryDirectory(prefix="llama-reselect-") as tmp:
        for row in source:
            slug = _source_slug(row)
            ws = ShowWorkspace(root / "shows" / slug)
            try:
                prov = read_model(ws.provenance, Provenance)
                stored = read_model(ws.show, Show).identifier
            except (OSError, ValueError) as exc:
                raise LlamaError(f"{slug}: cannot read provenance.json/show.json "
                                 f"({_one_line(exc)})") from exc
            # The assessment exactly as `_redo_show_locked` builds it for `redo --from select`.
            assessment = (prov.assessment.model_copy(update={"rationale": prov.dossier})
                          if prov.assessment is not None
                          else QualityAssessment(performance_id=prov.performance_id,
                                                 quality_score=0.0, rationale=prov.dossier))
            try:
                pick = run_select_recording(ShowWorkspace(Path(tmp) / slug), ia, prov.candidate,
                                            assessment, config.audio_format, force=True,
                                            selection=config.selection)
            except CacheMiss as exc:
                raise LlamaError(f"{slug}: {exc}") from exc
            if pick == stored:
                continue
            if is_delivered(ledger, prov.performance_id):
                if config.delivery_path is None:
                    raise LlamaError(f"{slug}: delivered, but no delivery_path in config")
                if destination_voiced(config.delivery_path / slug):
                    continue
            out.append({"slug": slug, "stored": stored, "pick": pick})
    return out


def _processed(ws: ShowWorkspace) -> bool:
    """The campaign record says processed (not awaiting). An unreadable record is not."""
    try:
        rec = campaign.read_record(ws)
    except campaign.CampaignUnreadable:
        return False
    return rec is not None and rec.processed is not None and not campaign.awaiting_fix(rec)


class _Unplannable(Exception):
    """A row the plan cannot decide (Task 15b M2): listed, never dropped."""


def _stored_show(ws: ShowWorkspace) -> Show:
    try:
        return read_model(ws.show, Show)
    except (OSError, ValueError) as exc:
        raise _Unplannable(f"show.json unreadable ({_one_line(exc)})") from exc


def _guard_holds(ws: ShowWorkspace, row: dict, stored: Show) -> bool:
    """Pointer (a): the row's `stored_brief_guard` ignores overrules; only the problems
    that the show's recorded overrules do not cover count (as brief reuse does). An
    unreadable overrides.json honours no overrule."""
    problems = list(row.get("stored_brief_guard") or [])
    if not problems:
        return False
    try:
        rules = read_overrides(ws).overrules
    except Exception:
        rules = []
    held, _notes = split_overruled(problems, rules, stored)
    return bool(held)


def _llm_reason(row: dict | None) -> str:
    needs = ", ".join((row or {}).get("needs_llm") or [])
    return f"{REASON_LLM}: {needs or 'on the frozen needs-LLM list'}"


def _newly_held_reason(row: dict, stored: Show) -> str:
    """Task 15c (Checkpoint B ruling): the flag kinds of the row's new gather, vet and brief
    flags, first-seen order, no repeats; a flag `flag_key` cannot key is `package`."""
    kinds: list[str] = []
    for flag in [*(row.get("gather_flags") or []), *(row.get("vet_flags") or []),
                 *(row.get("brief_flags") or [])]:
        key = flag_key(flag, stored)
        kind = key.kind if key is not None else "package"
        if kind not in kinds:
            kinds.append(kind)
    return f"{REASON_NEWLY_HELD}: {', '.join(kinds)}" if kinds else REASON_NEWLY_HELD


def _plan_one_mark(ws: ShowWorkspace, row: dict | None, frozen: set[str],
                   resel: dict | None) -> tuple[str, str, dict | None] | None:
    """(reason, start stage, digests) or None, in the brief's priority order.
    `_Unplannable` when show.json, needed to decide the row, cannot be read."""
    slug = ws.dir.name
    if resel is not None:                      # whatever the arm says
        return f"{REASON_RESELECTION}: {resel['stored']} -> {resel['pick']}", "select", None
    if row is None:
        return None
    digests = row.get("digests") or None
    processed = _processed(ws)
    if row.get("outcome") in _NO_DIFF:         # checked BEFORE row_visible_changes (pointer d)
        if slug in frozen and not processed:
            return _llm_reason(row), "gather", digests
        return None
    stored = _stored_show(ws)
    if row_label_only(row, stored):
        return None
    visible = row_visible_changes(row, stored)
    if visible:
        return f"{REASON_CHANGED}: {', '.join(visible)}", "gather", digests
    if processed:
        return None
    if slug in frozen:
        return _llm_reason(row), "gather", digests
    if _guard_holds(ws, row, stored):
        return REASON_GUARD, "gather", digests
    if row.get("outcome") == NEWLY_HELD:       # Task 15c: last, after every other trigger
        return _newly_held_reason(row, stored), "gather", digests
    return None


def _plan_state(ws: ShowWorkspace, delivered: set[str]) -> str:
    """`delivered` (the ledger's) first, since it decides the station mark; else
    `derive_state`'s name."""
    try:
        pid = _performance_id(ws)
        if pid and pid in delivered:
            return "delivered"
        return derive_state(ws, delivered)[0]
    except Exception:
        return "unreadable"


def _could_mark(row: dict | None, slug: str, frozen: set[str], resel: dict | None) -> bool:
    """Whether `_plan_one_mark` might mark this row: a re-selection, a frozen slug, or an
    arm row with a diff. A no-diff row off the frozen list is never marked, so its
    missing directory is not a planning problem."""
    return (resel is not None or slug in frozen
            or (row is not None and row.get("outcome") not in _NO_DIFF))


def mark_plan(root: Path, arm: dict, frozen: set[str], reselections: list[dict],
              delivered: set[str]) -> tuple[list[MarkItem], list[tuple[str, str]]]:
    """(items, unplannable): every show the marking rule selects (spec "Who gets marked",
    "Marking skips"), in slug order, and every row it cannot decide as (slug, problem):
    `no show directory` for a row it might mark, `show.json unreadable (<detail>)` for a
    row whose decision needs show.json (Task 15b M2; a re-selection or a no-diff frozen
    row is planned without it). `delivered` is the ledger's delivered performance ids.
    Reads only."""
    rows = _arm_rows(arm)
    resel = {r["slug"]: r for r in reselections}
    items, unplannable = [], []
    for slug in sorted(set(rows) | set(resel)):
        ws = ShowWorkspace(root / "shows" / slug)
        if not ws.dir.is_dir():
            if _could_mark(rows.get(slug), slug, frozen, resel.get(slug)):
                unplannable.append((slug, "no show directory"))
            continue
        try:
            planned = _plan_one_mark(ws, rows.get(slug), frozen, resel.get(slug))
        except _Unplannable as exc:
            unplannable.append((slug, str(exc)))
            continue
        if planned is not None:
            items.append(MarkItem(slug, *planned, state=_plan_state(ws, delivered)))
    return items, unplannable


def take_station_backup(station_root: Path, dest: Path) -> dict:
    """Copy every top-level non-dot station dir's `manifest.json` into `dest/<slug>/`,
    each copy re-read and sha-verified, `index.json` written last (its presence means
    the backup is complete). A partial earlier attempt is discarded first."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    index = {"taken_at": datetime.now(timezone.utc).isoformat(),
             "station_root": str(station_root), "manifests": {}, "missing": [],
             "unreadable": {}}
    for d in sorted(station_root.iterdir()):
        if d.name.startswith(".") or not d.is_dir():
            continue
        try:
            data = (d / "manifest.json").read_bytes()
        except FileNotFoundError:
            index["missing"].append(d.name)
            continue
        except OSError as exc:
            index["unreadable"][d.name] = _one_line(exc)
            continue
        copy = dest / d.name / "manifest.json"
        batch_snapshot._write_copy(copy, data)
        sha = hashlib.sha256(data).hexdigest()
        if hashlib.sha256(copy.read_bytes()).hexdigest() != sha:
            raise LlamaError(f"station backup: {copy} does not verify; nothing marked")
        index["manifests"][d.name] = sha
    _write_json(dest / "index.json", index)
    return index


def _last_lines(record: Path) -> dict[str, dict]:
    """slug -> its last record line; an unparsable line (a crash mid-append) is skipped."""
    out: dict[str, dict] = {}
    if not record.exists():
        return out
    for line in record.read_text().splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and isinstance(row.get("slug"), str):
            out[row["slug"]] = row
    return out


def _batch_mark(ws: ShowWorkspace, batch_id: str) -> campaign.CampaignMark | None:
    """This batch's (last) library mark; None when there is none or the record is
    unreadable."""
    try:
        rec = campaign.read_record(ws)
    except campaign.CampaignUnreadable:
        return None
    return next((m for m in reversed(rec.marks) if m.batch == batch_id), None) if rec else None


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reversal(saved: Path, raw: bytes, data: dict, line: dict | None) -> bytes | None:
    """The verified pre-mark bytes of a station copy that holds `raw` (`data` parsed,
    carrying a mark), or None. Two kinds of evidence, each exact (never a judgement):
    (1) the saved before copy, when adding the station's mark to it the way
    `station_mark.write_mark` does gives exactly `raw`; (2) `raw` with the mark removed,
    when `raw` is the record line's `after_sha256` and the result is its
    `before_sha256` (an unsaved before copy, Task 15b M1)."""
    key = station_mark.MARK_KEY
    try:
        before = saved.read_bytes()
        bdata = json.loads(before)
    except (OSError, ValueError):
        bdata = None
    if (isinstance(bdata, dict) and station_mark.mark_of(bdata) is None
            and station_mark._encode({**bdata, key: data[key]},
                                     newline=before.endswith(b"\n")) == raw):
        return before
    line = line or {}
    if line.get("before_sha256") and line.get("after_sha256") == _sha(raw):
        rebuilt = station_mark._encode({k: v for k, v in data.items() if k != key},
                                       newline=raw.endswith(b"\n"))
        if _sha(rebuilt) == line["before_sha256"]:
            return rebuilt
    return None


def _mark_station(item: MarkItem, out: Path, batch: Path, at: str, batch_at: str | None,
                  line: dict | None) -> tuple[str, str | None, str | None]:
    """(station outcome, before sha, after sha) for a delivered show's station copy.
    The caller checked emcee just before. Never raises for a station problem (pointer c).
    A copy already carrying THIS batch's mark (`marked_at` is the batch's library mark
    `at`: a run stopped between the station write and its record line, or an unsaved
    before copy) is recorded `marked` once `_reversal` verifies its before bytes (saved
    as the before copy), else `_UNVERIFIED`; it is never re-written (Task 15b M1)."""
    saved = batch / "before" / f"{item.slug}.json"
    try:
        raw, data = station_mark.read_station_manifest(out)
        mark = station_mark.mark_of(data)
        if mark is not None:
            if batch_at is None or mark.get("marked_at") != batch_at:
                return "already marked", None, None
            before = _reversal(saved, raw, data, line)
            if before is None:
                return _UNVERIFIED, None, _sha(raw)
            try:
                if not saved.exists() or saved.read_bytes() != before:
                    _write_durable(saved, before)
            except (LlamaError, OSError) as exc:
                return f"{_UNSAVED} ({_one_line(exc)})", _sha(before), _sha(raw)
            return "marked", _sha(before), _sha(raw)
        _write_durable(saved, raw)                        # before any station write
        before, after = station_mark.write_mark(out, reason=item.reason, marked_at=at)
    except (LlamaError, OSError) as exc:
        return f"refused: {_one_line(exc)}", None, None
    if before != raw:                       # another writer between the two reads
        try:
            _write_durable(saved, before)
        except (LlamaError, OSError) as exc:  # the station IS marked: never `refused`
            return f"{_UNSAVED} ({_one_line(exc)})", _sha(before), _sha(after)
    return "marked", _sha(before), _sha(after)


class _DeliveredIds:
    """The ledger's delivered performance ids, re-read whenever the ledger file changed
    (size or mtime), so each item sees the ledger as it is under its show lock without
    parsing the whole ledger once per item."""

    def __init__(self, path: Path):
        self.path, self.key, self.ids = path, None, frozenset()

    def __contains__(self, pid: str) -> bool:
        try:
            st = self.path.stat()
            key = (st.st_mtime_ns, st.st_size)
        except FileNotFoundError:
            key = None
        if key != self.key:
            self.ids = frozenset(e.performance_id for e in Ledger(self.path).entries()
                                 if e.status == "delivered")
            self.key = key
        return pid in self.ids


def _station_root_problem(station_root: Path) -> str | None:
    """None when the station root is a readable directory holding at least one entry whose
    name does not start with `.`; "unreadable" when it is not a readable directory;
    "empty" otherwise. An unmounted network share can leave its mount point as an empty
    directory, which must not pass as a mounted station. Stops at the first entry."""
    if not station_root.is_dir() or not os.access(station_root, os.R_OK):
        return "unreadable"
    try:
        with os.scandir(station_root) as it:
            for entry in it:
                if not entry.name.startswith("."):
                    return None
    except OSError:
        return "unreadable"
    return "empty"


def _empty_station_message(station_root: Path) -> str:
    return f"station root {station_root} is empty (is the station mounted?)"


def _station_copy_problem(out: Path) -> str | None:
    """None when the station copy's directory is there; `no station copy` only when it is
    absent (ENOENT); any other stat error (EIO, ETIMEDOUT, ENOTCONN on a flaky mount) is a
    refusal, listed and retried, never mistaken for "no copy" (`Path.is_dir` would swallow
    it as False)."""
    try:
        st = os.stat(out)
    except FileNotFoundError:
        return "no station copy"
    except OSError as exc:
        return f"refused: station copy unreadable ({_one_line(exc)})"
    if not stat.S_ISDIR(st.st_mode):
        return f"refused: station copy unreadable ({out} is not a directory)"
    return None


def _mark_one(root: Path, item: MarkItem, station_root: Path, batch: Path,
              record: Path, delivered_ids: _DeliveredIds,
              line: dict | None = None) -> tuple[str, bool, list[str]]:
    """One item under the show lock: (what happened, whether it must be listed as not
    marked, the emcee lines that stop the batch). The library mark is written first and
    made durable; a station failure never rolls it back (the library side is the safe
    direction), so this takes the plain show lock, not `show_unit`."""
    ws = ShowWorkspace(root / "shows" / item.slug)
    if not ws.dir.is_dir():
        return "skipped: no show directory", True, []
    with file_lock(ws.lock):
        pid = _performance_id(ws)
        delivered = bool(pid) and pid in delivered_ids
        if item.digests is not None and input_digests(ws) != item.digests:
            return "skipped: inputs changed", delivered, []
        at = campaign._now()
        if not campaign.is_awaiting(ws):          # an unreadable record counts as awaiting
            campaign.add_mark(ws, reason=item.reason, start_stage=item.start_stage,
                              batch=batch.name, at=at)
        own = _batch_mark(ws, batch.name)
        mark_added = own is not None
        if own is not None:       # a re-run marks the station with the batch's own `at`
            at = own.at
        before_sha = after_sha = None
        running: list[str] = []
        out = station_root / item.slug
        copy_problem = None
        if not delivered:
            station = _NOT_DELIVERED
        elif (root_problem := _station_root_problem(station_root)) is not None:
            station = (f"refused: station root {station_root} is not readable"
                       if root_problem == "unreadable"
                       else f"refused: {_empty_station_message(station_root)}")
        elif (copy_problem := _station_copy_problem(out)) is not None:
            station = copy_problem
        else:
            running = station_mark.emcee_running()     # before EACH write (pointer b)
            if running:
                station = "refused: emcee is running"
            else:
                station, before_sha, after_sha = _mark_station(
                    item, out, batch, at, own.at if own else None, line)
        _append_jsonl(record, {"slug": item.slug, "reason": item.reason,
                               "start_stage": item.start_stage, "mark_added": mark_added,
                               "station": station, "before_sha256": before_sha,
                               "after_sha256": after_sha, "at": at})
    library = "library mark added" if mark_added else "library mark kept"
    return f"{station} ({library})", delivered and station not in _STATION_OK, running


def mark_apply(root: Path, items: list[MarkItem], *, station_root: Path, batch: Path,
               echo) -> int:
    """The marking batch (spec "The marking batch"). Per item, under the show lock: the
    digests re-checked, the campaign record marked (durable) unless already awaiting, then
    a delivered show's station copy marked, one `record.jsonl` line per item. Items already
    recorded with a station outcome other than `refused`, `_UNSAVED` or `_UNVERIFIED` are
    skipped (those three are retried: a station copy already carrying this batch's mark
    is recorded `marked` once its before bytes verify). A running emcee stops the
    batch. Exit 0 only when every delivered item is `marked` or `already marked`, judged
    over the batch's WHOLE record (each slug's last line, earlier runs included, so a
    re-run still reports a terminal `no station copy`) plus this run's items that wrote
    no line (inputs changed, errors, not reached); else 1, listing each."""
    (batch / "before").mkdir(parents=True, exist_ok=True)
    record = batch / "record.jsonl"
    last = _last_lines(record)
    done = {s: r for s, r in last.items()
            if not str(r.get("station", "refused")).startswith(_RETRIED)}
    listed: dict[str, str] = {}
    counts: Counter = Counter()
    stop: list[str] = []
    delivered_ids = _DeliveredIds(root / "ledger.jsonl")
    for item in items:
        if stop:
            listed[item.slug] = f"{item.slug}: not reached (emcee is running)"
            continue
        if item.slug in done:
            echo(f"{item.slug}: skipped: already recorded ({done[item.slug]['station']})")
            counts["already recorded"] += 1
            continue
        try:
            what, problem, stop = _mark_one(root, item, station_root, batch, record,
                                            delivered_ids, last.get(item.slug))
        except Exception as exc:
            what, problem = f"error: {_one_line(exc)}", True
        echo(f"{item.slug}: {what}")
        key = what.split(" (")[0]
        counts["refused" if key.startswith("refused") else
               "error" if key.startswith("error") else key] += 1
        if problem:
            listed[item.slug] = f"{item.slug}: {what}"
        if stop:
            echo("refusing to mark station copies: emcee is running; the batch stops")
            for line in stop:
                echo(f"  {line}")
    for slug, line in sorted(_last_lines(record).items()):
        station = str(line.get("station"))
        if slug not in listed and station not in _STATION_OK and station != _NOT_DELIVERED:
            listed[slug] = f"{slug}: {station} (recorded)"
    echo(f"marking {batch.name}: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
         + f"; record: {record}")
    if listed:
        echo(f"not marked ({len(listed)}); do not run emcee on their profiles until a "
             "re-run of this batch exits 0:")
        for line in listed.values():
            echo(f"  {line}")
        return 1
    return 0


def _after(later: str, earlier: str) -> bool:
    """`later` is at or after `earlier`; an unparseable time counts as after (the
    reversal's safe direction: it then lists the show instead of unmarking it)."""
    a, b = campaign._parse(later), campaign._parse(earlier)
    return a is None or b is None or a >= b


def _own_station_mark(out: Path, saved: Path, attributed: set[str],
                      line: dict) -> tuple[bytes | None, str | None, str | None]:
    """For a line whose station outcome is not `marked` (Task 15b M1): (bytes to put
    back, the sha the copy must hold, problem). A copy carrying a mark this batch wrote
    (`marked_at` in `attributed`) is put back when `_reversal` verifies its before bytes,
    else it is a problem; never skipped. A copy that cannot be read is a problem only
    when the batch saved a before copy for it (it attempted a station write); without
    one this batch never wrote it (`refused` before any write, `no station copy`)."""
    problem = _station_copy_problem(out)
    raw = data = None
    if problem is None:
        try:
            raw, data = station_mark.read_station_manifest(out)
        except LlamaError as exc:
            problem = _one_line(exc)
    if problem is not None:
        if not saved.exists():
            return None, None, None
        return None, None, (f"cannot check the station copy for this batch's mark "
                            f"({problem}); check it by hand")
    mark = station_mark.mark_of(data)
    if mark is None or mark.get("marked_at") not in attributed:
        return None, None, None
    restore = _reversal(saved, raw, data, line)
    if restore is None:
        return None, None, ("the station copy carries this batch's mark and there is no "
                            "verified before copy; check it by hand")
    return restore, _sha(raw), None


def _unmark_one(ws: ShowWorkspace, line: dict, batch: Path, station_root: Path,
                apply: bool) -> tuple[str, bool]:
    """(what happened, whether it is a problem). Under the show lock."""
    slug, bid = ws.dir.name, batch.name
    rec = campaign.read_record(ws)                        # CampaignUnreadable: an error
    mark = next((m for m in reversed(rec.marks) if m.batch == bid), None) if rec else None
    if mark is not None and rec.processed is not None and _after(rec.processed.at, mark.at):
        return "processed since marked: re-deliver instead", True
    restore = expect = None
    out = station_root / slug
    saved = batch / "before" / f"{slug}.json"
    if line.get("station") == "marked":
        current = hashlib.sha256(station_mark.read_station_manifest(out)[0]).hexdigest()
        if current == line.get("after_sha256"):
            restore, expect = saved.read_bytes(), current
            if hashlib.sha256(restore).hexdigest() != line.get("before_sha256"):
                return f"refused: before/{slug}.json does not match the record", True
        elif current != line.get("before_sha256"):       # equal: already put back
            return "station copy changed since marking", True
    elif line.get("station") != _NOT_DELIVERED:
        attributed = {a for a in (mark.at if mark else None, line.get("at")) if a}
        restore, expect, problem = _own_station_mark(out, saved, attributed, line)
        if problem is not None:
            return problem, True
    what = ("station copy put back; " if restore is not None else "") + "batch mark removed"
    if not apply:
        return f"would be: {what}", False
    if restore is not None:
        running = station_mark.emcee_running()
        if running:
            return "refused: emcee is running (" + "; ".join(running) + ")", True
        station_mark.put_back(out, expect_sha256=expect, data=restore)
    campaign.remove_marks(ws, bid)
    return what, False


def unmark(root: Path, batch: Path, *, station_root: Path, apply: bool, echo) -> int:
    """The marking batch's reversal (spec "A batch is reversible by its record"), by each
    slug's last record line with `mark_added`: a show processed since the batch's mark is
    listed and left alone; a `marked` station copy is put back only while it still holds
    the bytes marking wrote; then the batch's library mark is removed. A line with
    `mark_added: false` keeps the earlier batch's mark (and its station copy). Any other
    line's station copy still carrying this batch's mark is put back from verified
    evidence or listed, and a before copy with no record line at all (a run stopped
    between its station write and the line) is listed (Task 15b M1). Exit 1 when
    anything is listed."""
    record = batch / "record.jsonl"
    if not record.exists():
        raise LlamaError(f"no record.jsonl in {batch}")
    problems = 0
    lines = _last_lines(record)
    before_dir = batch / "before"
    for slug in sorted(p.stem for p in before_dir.glob("*.json")
                       if p.stem not in lines) if before_dir.is_dir() else []:
        problems += 1
        echo(f"{slug}: no record line (a marking run stopped part-way); re-run the batch, "
             "then unmark")
    for slug, line in sorted(lines.items()):
        if not line.get("mark_added"):
            echo(f"{slug}: kept (this batch added no library mark)")
            continue
        ws = ShowWorkspace(root / "shows" / slug)
        if not ws.dir.is_dir():
            what, problem = "no show directory; check it by hand", True
        else:
            try:
                with file_lock(ws.lock):
                    what, problem = _unmark_one(ws, line, batch, station_root, apply)
            except Exception as exc:
                what, problem = f"refused: {_one_line(exc)}", True
        problems += problem
        echo(f"{slug}: {what}")
    return 1 if problems else 0


def _read_json_file(path: Path, what: str) -> tuple[bytes, object]:
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise GateRefused(f"no {what}: {path}") from exc
    except OSError as exc:
        raise GateRefused(f"{path} unreadable ({_one_line(exc)})") from exc
    try:
        return data, json.loads(data)
    except ValueError as exc:
        raise GateRefused(f"{path} is not JSON ({_one_line(exc)})") from exc


def cmd_freeze(args) -> int:
    config = _config(args)
    _, arm = _read_json_file(args.arm, "arm")
    path = freeze(config.root, arm, campaign_dir=args.campaign_dir)
    n = len(json.loads(path.read_text())["slugs"])
    print(f"frozen {n} needs-LLM show(s): {path}")
    return 0


def cmd_reselect_check(args) -> int:
    config = _config(args)
    _, source = _read_json_file(args.source, "re-selection source")
    rows = source.get("rows") if isinstance(source, dict) else source
    if not isinstance(rows, list):
        raise GateRefused(f"{args.source} is not a list of shows")
    checked = reselect_rows(config.root, config, rows)
    for r in checked:
        print(f"{r['slug']}: {r['stored']} -> {r['pick']}")
    print(f"re-selections: {len(checked)} of {len(rows)} source row(s)")
    if not args.write:
        print("dry run: nothing written (pass --write)")
        return 0
    path = _campaign_dir(config.root, args.campaign_dir) / RESELECTIONS_NAME
    _write_json(path, {"written_at": datetime.now(timezone.utc).isoformat(), "rows": checked})
    print(f"written: {path}")
    return 0


def _parse_time(text) -> datetime | None:
    return campaign._parse(text) if isinstance(text, str) else None


def _station_state(item: MarkItem, station_root: Path) -> tuple[str, str | None]:
    """(table column, unreadable detail or None)."""
    if item.state != "delivered":
        return item.state, None
    out = station_root / item.slug
    problem = _station_copy_problem(out)
    if problem == "no station copy":
        return "delivered no station copy", None
    if problem is not None:
        return "delivered unreadable", problem
    try:
        voiced = destination_voiced(out)
    except LlamaError as exc:
        return "delivered unreadable", _one_line(exc)
    return ("delivered voiced" if voiced else "delivered unvoiced"), None


def _print_mark_plan(items: list[MarkItem], arm: dict, station_root: Path,
                     unplannable: list[tuple[str, str]]) -> None:
    rows = _arm_rows(arm)
    table: dict[str, Counter] = {k: Counter() for k in _REASON_KINDS}
    voiced, unreadable = [], []
    for it in items:
        column, detail = _station_state(it, station_root)
        kind = next((k for k in _REASON_KINDS if it.reason.startswith(k)), it.reason)
        table.setdefault(kind, Counter())[column] += 1
        if column == "delivered voiced":
            voiced.append(it.slug)
        if detail is not None:
            unreadable.append((it.slug, detail))
    extra = sorted({c for t in table.values() for c in t} - set(_PLAN_COLUMNS))
    columns = list(_PLAN_COLUMNS) + extra
    print(f"marking plan: {len(items)} show(s)")
    for kind, counts in table.items():
        print(f"  {kind}: " + ", ".join(f"{c} {counts[c]}" for c in columns))
    outcomes = Counter(rows[it.slug].get("outcome") for it in items if it.slug in rows)
    print("by arm outcome: " + ", ".join(f"{k} {v}" for k, v in sorted(outcomes.items())))
    print(f"voiced: {len(voiced)}" + (f": {', '.join(voiced)}" if voiced else ""))
    print(f"unreadable station manifests: {len(unreadable)}")
    for slug, detail in unreadable:
        print(f"  {slug}: {detail}")
    marked = {it.slug for it in items}
    unrep = sorted(s for s, r in rows.items()
                   if r.get("outcome") == "unreplayable" and s not in marked)
    print(f"unreplayable, not marked: {len(unrep)}" + (f": {', '.join(unrep)}" if unrep else ""))
    print(f"unplannable shows: {len(unplannable)}")
    for slug, problem in unplannable:
        print(f"  {slug}: {problem}")
    running = station_mark.emcee_running()
    print("emcee running: " + ("yes" if running else "no"))
    for line in running:
        print(f"  {line}")


def cmd_mark(args) -> int:
    config = _config(args)
    root, station_root = config.root, config.delivery_path
    if args.apply and args.campaign_dir is not None:      # Task 15b M3
        raise GateRefused(f"refusing --campaign-dir with --apply: campaign state must live "
                          f"in {root}/campaign (the dry run may use a scratch dir)")
    if station_root is None:
        raise GateRefused("no delivery_path in config")
    root_problem = _station_root_problem(station_root)
    if root_problem == "unreadable":
        raise GateRefused(f"station root {station_root} is not mounted or not a directory")
    if root_problem == "empty":
        raise GateRefused(_empty_station_message(station_root))
    if args.apply:
        pin = require_pinned_code(root)
        require_tools(_echo, pin=pin)
    arm_bytes, arm = _read_json_file(args.arm, "arm")
    if not isinstance(arm, dict):
        raise GateRefused(f"{args.arm} is not an arm")
    ident = llama.replay.code_identity()
    if (arm.get("sha") != ident or ident.endswith("-dirty")
            or str(arm.get("sha")).endswith("-dirty")):
        raise GateRefused(f"the arm was written by code {arm.get('sha')}; the running code is "
                          f"{ident} (an uncommitted tree has no code identity)")
    if arm.get("config_fingerprint") != config_fingerprint(config):
        raise GateRefused(f"the arm's config fingerprint {arm.get('config_fingerprint')} is not "
                          f"the running config's {config_fingerprint(config)}")
    camp = _campaign_dir(root, args.campaign_dir)
    frozen_bytes, frozen = _read_json_file(camp / FROZEN_NAME,
                                           "frozen needs-LLM list (run bulk_apply.py freeze)")
    resel_bytes, resel = _read_json_file(camp / RESELECTIONS_NAME,
                                         "re-selection list (run bulk_apply.py "
                                         "reselect-check --write)")
    if not (isinstance(frozen, dict) and isinstance(frozen.get("slugs"), list)):
        raise GateRefused(f"{camp / FROZEN_NAME} has no slugs")
    if not (isinstance(resel, dict) and isinstance(resel.get("rows"), list)
            and all(isinstance(r, dict) and isinstance(r.get("slug"), str)
                    for r in resel["rows"])):
        raise GateRefused(f"{camp / RESELECTIONS_NAME} has no rows")
    written, generated = _parse_time(resel.get("written_at")), _parse_time(arm.get("generated_at"))
    if written is None or generated is None or written < generated:
        raise GateRefused(RESELECTIONS_STALE)
    delivered = {e.performance_id for e in Ledger(root / "ledger.jsonl").entries()
                 if e.status == "delivered"}
    items, unplannable = mark_plan(root, arm, set(frozen["slugs"]), resel["rows"], delivered)
    _print_mark_plan(items, arm, station_root, unplannable)
    if not args.apply:
        print("dry run: nothing written (pass --apply)")
        return 1 if unplannable else 0
    if unplannable:
        raise GateRefused(f"refusing to mark: {len(unplannable)} unplannable show(s): "
                          + ", ".join(slug for slug, _ in unplannable))
    batch_id = hashlib.sha256(arm_bytes + frozen_bytes + resel_bytes).hexdigest()[:16]
    retire_rekey_restore(root, by=f"bulk-apply marking {batch_id}",
                         at=datetime.now(timezone.utc).isoformat())
    backup = camp / BACKUP_NAME
    if (backup / "index.json").exists():
        print(f"station backup: already taken ({backup})")
    else:
        index = take_station_backup(station_root, backup)
        print(f"station backup: {len(index['manifests'])} manifest(s) in {backup}")
    batch = camp / "marking" / batch_id
    if not (batch / "inputs.json").exists():
        _write_json(batch / "inputs.json", {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "arm": str(args.arm), "arm_sha256": hashlib.sha256(arm_bytes).hexdigest(),
            "arm_sha": arm.get("sha"), "arm_generated_at": arm.get("generated_at"),
            "frozen_sha256": hashlib.sha256(frozen_bytes).hexdigest(),
            "reselections_sha256": hashlib.sha256(resel_bytes).hexdigest(),
            "station_root": str(station_root)})
    return mark_apply(root, items, station_root=station_root, batch=batch, echo=_echo)


def cmd_unmark(args) -> int:
    config = _config(args)
    if config.delivery_path is None:
        raise GateRefused("no delivery_path in config")
    rc = unmark(config.root, args.batch, station_root=config.delivery_path, apply=args.apply,
                echo=_echo)
    if not args.apply:
        print("dry run: nothing written (pass --apply)")
    return rc


# --- wave lists, wave check, spot checks (plan Task 16; spec "Pacing, ordering and
# resumability" (selection), "Re-processing", "Pacing") ---

WAVE_DISK_MARGIN_BYTES = 20 * 10**9
LIST_KINDS = ("fresh", "reuse", "needs-llm", "label-only", "held")
NEWLY_HELD = "newly-held"


def _side(filenames, titles, sets, segues) -> list[dict]:
    n = max(len(filenames or []), len(titles or []), len(sets or []), len(segues or []))

    def at(seq, i):
        return seq[i] if seq and i < len(seq) else None
    return [{"filename": at(filenames, i), "title": at(titles, i), "set": at(sets, i),
             "segue": at(segues, i)} for i in range(n)]


def _stored_side(stored: Show) -> list[dict]:
    return [{"filename": t.filename, "title": t.title, "set": t.set, "segue": bool(t.segue)}
            for t in stored.tracks]


def _row_side(row: dict) -> list[dict]:
    return _side(row.get("filenames"), row.get("titles"), row.get("sets"), row.get("segues"))


def _arrow(b, a) -> str:
    return f"{'?' if b is None else b}->{'?' if a is None else a}"


def render_side_by_side(before: list[dict], after: list[dict]) -> list[str]:
    """One line per track index: set, title and segue mark (before->after); a line whose
    values differ starts with `*`. Tracks are paired by index; a side that is shorter
    shows `?` for the missing track."""
    lines = []
    for i in range(max(len(before), len(after))):
        b = before[i] if i < len(before) else {}
        a = after[i] if i < len(after) else {}
        differs = any(b.get(k) != a.get(k) for k in ("set", "title", "segue"))
        mark = {None: "?", True: ">", False: "-"}
        lines.append(f"{'*' if differs else ' '} {i + 1:>3}  set {_arrow(b.get('set'), a.get('set'))}"
                     f"  title {_arrow(b.get('title'), a.get('title'))}"
                     f"  segue {mark[b.get('segue')]}->{mark[a.get('segue')]}")
    return lines


def _famous_packet(root: Path, rows: dict[str, dict], slugs: list[str]) -> str:
    out = []
    for slug in slugs:
        out.append(f"== {slug}")
        row = rows.get(slug)
        if row is None:
            out.append("not in the arm")
            continue
        try:
            stored = _stored_show(ShowWorkspace(root / "shows" / slug))
        except _Unplannable as exc:
            out.append(str(exc))
            continue
        if row.get("outcome") in _NO_DIFF:
            out.append(f"no after side (outcome {row.get('outcome')})")
            continue
        out.extend(render_side_by_side(_stored_side(stored), _row_side(row)))
    return "\n".join(out) + "\n"


def _row_kind(row: dict, stored: Show | None) -> str:
    if row.get("outcome") == "needs-llm":
        return "needs-llm"
    if row.get("briefing") == "none":
        return "held"
    if stored is not None and row_label_only(row, stored):
        return "label-only"
    return str(row.get("briefing"))


def _voiced(station_root: Path | None, slug: str, problems: list[str]) -> bool | None:
    """True/False, or None (reported in `problems`) when the station copy cannot be read.
    No station copy is unvoiced."""
    if station_root is None:
        return False
    out = station_root / slug
    problem = _station_copy_problem(out)
    if problem == "no station copy":
        return False
    if problem is not None:
        problems.append(f"{slug}: {problem}")
        return None
    try:
        return destination_voiced(out)
    except LlamaError as exc:
        problems.append(f"{slug}: {_one_line(exc)}")
        return None


def select_wave(root: Path, station_root: Path | None, arm: dict, *, profiles, states, slugs,
                famous, reselections: set[str], problems: list[str]) -> list[dict]:
    """Every show a wave may take, as {slug, row, kind, voiced, profile}, in slug order
    (spec "Pacing, ordering and resumability"): awaiting fix with start `gather`, or
    label-only with no record, or `newly-held`; never processed, a re-selection, or
    famous. `voiced` is left to the caller to filter. Reads only; what it cannot decide
    goes to `problems`."""
    rows = _arm_rows(arm)
    delivered = {e.performance_id for e in Ledger(root / "ledger.jsonl").entries()
                 if e.status == "delivered"}
    picked = []
    for slug in sorted(rows):
        if slug in famous or slug in reselections or (slugs is not None and slug not in slugs):
            continue
        ws = ShowWorkspace(root / "shows" / slug)
        if not ws.dir.is_dir():
            continue
        row = rows[slug]
        try:
            rec = campaign.read_record(ws)
        except campaign.CampaignUnreadable as exc:
            problems.append(str(exc))
            continue
        if rec is not None and campaign.last_mark(rec) is not None:
            if not campaign.awaiting_fix(rec):
                continue                                    # processed
            if campaign.last_mark(rec).start_stage != "gather":
                continue                                    # a re-selection
            listed, stored = True, None
        else:
            listed = row.get("outcome") == NEWLY_HELD
            stored = None
        if row.get("outcome") not in _NO_DIFF:
            try:
                stored = _stored_show(ws)
            except _Unplannable as exc:
                problems.append(f"{slug}: {exc}")
                continue
            if not listed and rec is None and row_label_only(row, stored):
                listed = True
        if not listed:
            continue
        if states and _plan_state(ws, delivered) not in states:
            continue
        try:
            prov = read_model(ws.provenance, Provenance)
            profile = prov.profile
        except (OSError, ValueError):
            profile = None
        if profiles and profile not in profiles:
            continue
        picked.append({"slug": slug, "row": row, "profile": profile,
                       "kind": _row_kind(row, stored)})
    for item in picked:
        item["voiced"] = _voiced(station_root, item["slug"], problems)
    return picked


def cmd_lists(args) -> int:
    config = _config(args)
    root = config.root
    if config.delivery_path is None:
        raise GateRefused("no delivery_path in config")
    root_problem = _station_root_problem(config.delivery_path)
    if root_problem == "unreadable":
        raise GateRefused(f"station root {config.delivery_path} is not mounted or not a "
                          f"directory")
    if root_problem == "empty":
        raise GateRefused(_empty_station_message(config.delivery_path))
    pin = require_pinned_code(root)
    if not args.counts and args.out is None:
        raise GateRefused("lists needs --out (or --counts)")
    _, arm = _read_json_file(args.arm, "arm")
    if not isinstance(arm, dict):
        raise GateRefused(f"{args.arm} is not an arm")
    if arm.get("sha") != pin.get("sha"):
        raise GateRefused(f"the arm was written by code {arm.get('sha')}; the pin is "
                          f"{pin.get('sha')} ({pin.get('tag')})")
    if arm.get("config_fingerprint") != config_fingerprint(config):
        raise GateRefused(f"the arm's config fingerprint {arm.get('config_fingerprint')} is not "
                          f"the running config's {config_fingerprint(config)}")
    slugs = set(_read_slugs(args.slugs)) if args.slugs else None
    famous = _read_slugs(args.famous) if args.famous else []
    try:
        resel = {r["slug"] for r in json.loads(
            (root / "campaign" / RESELECTIONS_NAME).read_text())["rows"]}
    except FileNotFoundError:
        resel = set()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise GateRefused(f"{root / 'campaign' / RESELECTIONS_NAME} unreadable "
                          f"({_one_line(exc)})") from exc
    problems: list[str] = []
    picked = select_wave(root, config.delivery_path, arm, profiles=set(args.profile or []),
                         states=set(args.state or []), slugs=slugs, famous=set(famous),
                         reselections=resel, problems=problems)
    kinds = set(args.kind or [])
    picked = [p for p in picked if not kinds or p["kind"] in kinds]
    for line in problems:
        print(line, file=sys.stderr)
    picked = [p for p in picked if p["voiced"] is not None]    # unreadable: reported, not taken
    if args.counts:
        counts: dict = {}
        for p in picked:
            cell = counts.setdefault(p["profile"] or "(none)", {}).setdefault(
                p["kind"], {"unvoiced": 0, "voiced": 0})
            cell["voiced" if p["voiced"] else "unvoiced"] += 1
        print(json.dumps(counts, indent=2, sort_keys=True))
        return 0
    if not args.include_voiced:
        picked = [p for p in picked if not p["voiced"]]
    if args.limit is not None:
        picked = picked[:args.limit]
    doc = {"sha": arm["sha"], "config_fingerprint": arm["config_fingerprint"],
           "written_at": datetime.now(timezone.utc).isoformat(),
           "campaign": {"version": pin.get("version"), "pin_sha": pin.get("sha")},
           "rows": [{"slug": p["slug"], "outcome": p["row"].get("outcome"),
                     "briefing": p["row"].get("briefing"), "kind": p["kind"],
                     "digests": p["row"].get("digests") or {}} for p in picked]}
    _write_json(args.out, doc)
    print(f"listed {len(picked)} show(s): {args.out}")
    if famous:
        packet = Path(str(args.out) + ".famous.txt")
        _write_durable(packet, _famous_packet(root, _arm_rows(arm), famous).encode())
        print(f"famous-shows packet: {packet}")
    return 0


def cmd_wave_check(args) -> int:
    config = _config(args)
    root, station_root = config.root, config.delivery_path
    if station_root is None:
        raise GateRefused("no delivery_path in config")
    root_problem = _station_root_problem(station_root)
    if root_problem == "unreadable":
        raise GateRefused(f"station root {station_root} is not mounted or not a readable "
                          f"directory")
    if root_problem == "empty":
        raise GateRefused(_empty_station_message(station_root))
    _, doc = _read_json_file(args.list, "wave list")
    if not (isinstance(doc, dict) and isinstance(doc.get("rows"), list)):
        raise GateRefused(f"{args.list} is not a wave list")
    delivered = {e.performance_id for e in Ledger(root / "ledger.jsonl").entries()
                 if e.status == "delivered"}
    needed = 0
    for row in doc["rows"]:
        slug = row["slug"]
        ws = ShowWorkspace(root / "shows" / slug)
        if _plan_state(ws, delivered) != "delivered":
            continue
        out = station_root / slug
        station_mark.read_station_manifest(out)             # StationUnreadable -> exit 2
        audio = out / "audio"
        try:
            needed += sum(f.stat().st_size for f in audio.iterdir() if f.is_file())
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise GateRefused(f"{slug}: station audio unreadable ({_one_line(exc)})") from exc
    free = shutil.disk_usage(root).free
    print(f"needed: {needed} bytes\nfree: {free} bytes\nmargin: {WAVE_DISK_MARGIN_BYTES} bytes")
    if needed + WAVE_DISK_MARGIN_BYTES > free:
        raise GateRefused(f"not enough free disk under {root}: need {needed} + margin "
                          f"{WAVE_DISK_MARGIN_BYTES} > free {free}")
    print("wave-check: ok")
    return 0


def cmd_spot_check(args) -> int:
    import random
    config = _config(args)
    batch = args.batch
    progress = reapply.read_progress(batch)
    slugs = sorted(s for s, r in progress.items() if r.get("outcome") in ("cleared", "held"))
    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2**31)
    print(f"seed: {seed}")
    sample = random.Random(seed).sample(slugs, min(args.n, len(slugs)))
    for slug in sorted(sample):
        print(f"== {slug} ({progress[slug].get('outcome')})")
        before_path = batch / "snapshot" / "shows" / slug / "show.json"
        try:
            before = _stored_side(read_model(before_path, Show))
        except (OSError, ValueError) as exc:
            print(f"no before state ({_one_line(exc)})")
            continue
        try:
            after = _stored_side(_stored_show(ShowWorkspace(config.root / "shows" / slug)))
        except _Unplannable as exc:
            print(str(exc))
            continue
        for line in render_side_by_side(before, after):
            print(line)
    return 0


# --- Task 17: the ranked re-voice list and the trial cost report (read-only) ---

MIN_BLOCK_POINTS = 5            # a trial block's 5-hour meter must move this many points
MATERIAL_DIFFERENCE = 0.25      # relative per-show cost gap that keeps two shapes apart
MEASURED_KINDS = ("fresh", "needs-llm")      # the kinds that make an LLM call
DISCARDED = "discarded: crossed a 5-hour reset; re-run"
_BACKEND_COST = {"voxtral": "1 Voxtral credit", "mlx_audio": "free (local)",
                 "elevenlabs": "ElevenLabs"}
UNKNOWN_UNTIL = "unknown until re-processed"


def _components(row: dict, stored: Show) -> dict:
    """How different the re-processed show is, per component, paired by filename."""
    old = {t.filename: t for t in stored.tracks}
    names = row.get("filenames") or []
    new = {}
    for i, name in enumerate(names):
        def at(key, i=i):
            seq = row.get(key)
            return seq[i] if seq and i < len(seq) else None
        new[name] = {"title": at("titles"), "set": at("sets"), "segue": bool(at("segues"))}
    added = [n for n in new if n not in old]
    removed = [n for n in old if n not in new]
    common = [n for n in new if n in old]
    return {"added": len(added), "removed": len(removed),
            "set_moves": sum(1 for n in common if new[n]["set"] != old[n].set),
            "titles": sum(1 for n in common if new[n]["title"] != old[n].title),
            "segues": sum(1 for n in common if new[n]["segue"] != bool(old[n].segue)),
            "metadata": sum(1 for k in ("venue", "city", "date") if row.get(k))}


def _backend_of(tts_now) -> str | None:
    return tts_now.get("backend") if isinstance(tts_now, dict) else None


def cmd_revoice_list(args) -> int:
    config = _config(args)
    root = config.root
    _, arm = _read_json_file(args.arm, "arm")
    if not isinstance(arm, dict):
        raise GateRefused(f"{args.arm} is not an arm")
    _, status = _read_json_file(args.emcee_status, "emcee status")
    if not isinstance(status, list):
        raise GateRefused(f"{args.emcee_status} is not an `emcee status --json` list")
    rows = _arm_rows(arm)
    known, unknown = [], []
    for st in status:
        if not isinstance(st, dict) or not st.get("voiced_by") or not isinstance(st.get("slug"), str):
            continue
        slug = st["slug"]
        backend = _backend_of(st.get("tts_now"))
        if args.backend and backend != args.backend:
            continue
        ws = ShowWorkspace(root / "shows" / slug)
        if not ws.dir.is_dir():
            continue
        try:
            rec = campaign.read_record(ws)
        except campaign.CampaignUnreadable as exc:
            print(str(exc), file=sys.stderr)
            continue
        if rec is None or campaign.last_mark(rec) is None or not campaign.awaiting_fix(rec):
            continue
        row = rows.get(slug)
        if row is None:
            print(f"{slug}: not in the arm", file=sys.stderr)
            continue
        item = {"slug": slug, "presenter": st["voiced_by"], "backend": backend or "unknown",
                "cost": _BACKEND_COST.get(backend, "unknown")}
        if row.get("outcome") in _NO_DIFF:
            unknown.append(item)
            continue
        try:
            item["c"] = _components(row, _stored_show(ws))
        except _Unplannable as exc:
            print(f"{slug}: {exc}", file=sys.stderr)
            continue
        known.append(item)

    def key(it):
        c = it["c"]
        return (-(c["added"] + c["removed"]), -c["set_moves"], -c["titles"], -c["segues"],
                -c["metadata"], it["slug"])
    known.sort(key=key)
    unknown.sort(key=lambda it: it["slug"])
    for rank, it in enumerate(known + unknown, 1):
        head = (f"{rank} {it['slug']} presenter {it['presenter']} backend {it['backend']} "
                f"cost {it['cost']}")
        if "c" in it:
            c = it["c"]
            print(f"{head} tracks +{c['added']}/-{c['removed']} set moves {c['set_moves']} "
                  f"titles {c['titles']} segues {c['segues']} metadata {c['metadata']}")
        else:
            print(f"{head} components {UNKNOWN_UNTIL}")
    return 0


def _num(x: float) -> str:
    return f"{x:.4g}"


def _parse_block(spec: str) -> tuple[str, str, Path]:
    left, sep, path = spec.partition("=")
    if not sep or not path:
        raise GateRefused(f"--block {spec!r}: expected <shape>-<kind>=<batch dir>")
    for kind in MEASURED_KINDS:
        if left.endswith("-" + kind) and len(left) > len(kind) + 1:
            return left[:-len(kind) - 1], kind, Path(path)
    raise GateRefused(f"--block {spec!r}: the kind must be one of {', '.join(MEASURED_KINDS)}")


def _spending_rows(batch: Path) -> list[tuple[str | None, dict]]:
    """(list kind, last progress row) for every row that spent (llm_calls > 0), oldest first."""
    _, lst = _read_json_file(batch / "list.json", "batch list")
    if not (isinstance(lst, dict) and isinstance(lst.get("rows"), list)):
        raise GateRefused(f"{batch / 'list.json'} is not a wave list")
    kinds = {r.get("slug"): r.get("kind") for r in lst["rows"] if isinstance(r, dict)}
    out = [(kinds.get(s), r) for s, r in reapply.read_progress(batch).items()
           if isinstance(r.get("llm_calls"), (int, float)) and r["llm_calls"] > 0]
    return sorted(out, key=lambda kr: str(kr[1].get("at")))


def _block_rows(batch: Path, kind: str) -> list[dict]:
    """The batch's applied rows of `kind` that spent (llm_calls > 0), oldest first."""
    return [r for k, r in _spending_rows(batch) if k == kind]


def _all_progress_rows(batch: Path) -> list[dict]:
    """Every parseable object line of the batch's progress.jsonl, in file order (not just
    each slug's last row; an unparseable line is skipped, as `reapply.read_progress` does)."""
    path = batch / "progress.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and isinstance(row.get("slug"), str):
            out.append(row)
    return out


def _foreign_inside(batch: Path, kind: str) -> int:
    """Spending progress lines of another kind whose time falls inside the block's own
    window. Every line counts: an other-kind show that spent inside the window and was
    re-run outside it leaves only its later row as the slug's last row."""
    mine = [str(r.get("at")) for k, r in _spending_rows(batch) if k == kind]
    if not mine:
        return 0
    lo, hi = mine[0], mine[-1]
    _, lst = _read_json_file(batch / "list.json", "batch list")
    kinds = {r.get("slug"): r.get("kind") for r in lst["rows"] if isinstance(r, dict)}
    return sum(1 for r in _all_progress_rows(batch)
               if kinds.get(r["slug"]) != kind
               and isinstance(r.get("llm_calls"), (int, float)) and r["llm_calls"] > 0
               and lo <= str(r.get("at")) <= hi)


def _meter_of(row: dict, which: str) -> dict:
    m = (row.get("meter") or {}).get(which)
    return m if isinstance(m, dict) else {}


def _one_window(resets: set) -> bool:
    """The readings' 5-hour resets all name one window, allowing /usage's
    one-minute jitter (herder.usage.same_window)."""
    try:
        when = [None if r is None else datetime.fromisoformat(r) for r in resets]
    except (TypeError, ValueError):
        return len(resets) == 1
    return all(same_window(a, b) for a in when for b in when)


def _measure_block(rows: list[dict]) -> dict | None:
    """{n, d5, d7} for one block, or None when the readings are unusable or the block
    crossed a 5-hour reset."""
    if not rows:
        return None
    first, last = _meter_of(rows[0], "before"), _meter_of(rows[-1], "after")
    resets = {m.get("five_hour_resets") for r in rows for m in (_meter_of(r, "before"),
                                                                 _meter_of(r, "after"))}
    if not _one_window(resets):
        return {"discarded": True}
    vals = (first.get("five_hour"), last.get("five_hour"),
            first.get("seven_day"), last.get("seven_day"))
    if any(not isinstance(v, (int, float)) for v in vals):
        return None
    return {"n": len(rows), "d5": vals[1] - vals[0], "d7": vals[3] - vals[2]}


def cmd_trial_report(args) -> int:
    if not args.weekly_share > 0:
        raise GateRefused("--weekly-share must be above 0")
    shape_of: dict[str, str] = {}
    for spec in args.shape or []:
        name, sep, profiles = spec.partition("=")
        if not sep or not name:
            raise GateRefused(f"--shape {spec!r}: expected <shape>=<profile>,<profile>")
        for p in profiles.split(","):
            shape_of[p.strip()] = name
    _, queue = _read_json_file(args.queue, "queue")
    if not isinstance(queue, dict):
        raise GateRefused(f"{args.queue} is not a `lists --counts` document")
    kept: list[tuple[str, str, dict]] = []
    for spec in args.block:
        shape, kind, batch = _parse_block(spec)
        label = f"{shape}-{kind}"
        rows = _block_rows(batch, kind)
        foreign = _foreign_inside(batch, kind)
        if foreign:
            print(f"{label}: not contiguous: {foreign} spending row(s) of another kind "
                  f"inside it; re-run as one block per kind")
            continue
        m = _measure_block(rows)
        if m is None:
            print(f"block {label}: no usable measurement ({len(rows)} spending row(s))")
            continue
        if m.get("discarded"):
            print(f"block {label}: {DISCARDED}")
            continue
        line = f"block {label}: shows={m['n']} delta5={_num(m['d5'])} delta7={_num(m['d7'])}"
        if m["d5"] < MIN_BLOCK_POINTS:
            line += (f" -- delta5 {_num(m['d5'])} < {MIN_BLOCK_POINTS} points; error bound "
                     f"±1/{m['n']} = ±{_num(1 / m['n'])} points per show")
        print(line)
        print(f"block {label}: per-show 5h: {_num(m['d5'] / m['n'])}")
        kept.append((shape, kind, m))
    sum5, sum7 = sum(m["d5"] for _, _, m in kept), sum(m["d7"] for _, _, m in kept)
    if not kept or sum5 <= 0:
        print("no usable block: no projection")
        return 0
    ratio = sum7 / sum5
    print(f"7d/5h ratio: {_num(ratio)}")
    cost: dict[str, dict] = {}            # kind -> {"pooled": c, "shapes": {shape: c}, "apart": b}
    for kind in MEASURED_KINDS:
        mine = [(s, m) for s, k, m in kept if k == kind]
        if not mine:
            continue
        shapes: dict[str, list[float]] = {}
        for s, m in mine:
            acc = shapes.setdefault(s, [0.0, 0])
            acc[0] += m["d5"]
            acc[1] += m["n"]
        per = {s: a[0] / a[1] * ratio for s, a in shapes.items()}
        pooled = sum(m["d5"] for _, m in mine) / sum(m["n"] for _, m in mine) * ratio
        hi, lo = max(per.values()), min(per.values())
        apart = len(per) > 1 and hi > 0 and (hi - lo) / hi > MATERIAL_DIFFERENCE
        cost[kind] = {"pooled": pooled, "shapes": per, "apart": apart, "max": hi}
        for s, c in sorted(per.items()):
            print(f"block {s}-{kind}: per-show 7d: {_num(c)}")
        print(f"{kind}: shapes kept apart" if apart else f"{kind}: pooled {_num(pooled)} per show 7d")

    def per_show(profile: str, kind: str) -> float | None:
        c = cost.get(kind)
        if c is None:
            return None
        if not c["apart"]:
            return c["pooled"]
        shape = shape_of.get(profile, profile)
        return c["shapes"].get(shape, c["max"])

    total = 0.0
    unmeasured: set[str] = set()
    for profile in sorted(queue):
        pts = 0.0
        for kind, cell in (queue[profile] or {}).items():
            if kind not in MEASURED_KINDS:
                continue                    # reuse, label-only and held make no LLM call
            n = int(cell.get("unvoiced", 0)) + int(cell.get("voiced", 0))
            c = per_show(profile, kind)
            if c is None:
                if n:
                    unmeasured.add(kind)
                continue
            pts += n * c
        total += pts
        print(f"projection {profile}: {_num(pts)} points = {_num(pts / args.weekly_share)} weeks")
    print(f"projection total: {_num(total)} points = {_num(total / args.weekly_share)} weeks "
          f"at {_num(args.weekly_share)} points of the weekly meter per week")
    for kind in sorted(unmeasured):
        print(f"note: no usable block for kind {kind}; its shows are left out of the projection")
    reproduced = []
    for spec in args.block:
        shape, kind, batch = _parse_block(spec)
        if kind == "needs-llm":
            reproduced += [r.get("align_reproduced") for r in _block_rows(batch, kind)
                           if isinstance(r.get("align_reproduced"), bool)]
    if reproduced:
        print(f"align_reproduced: {sum(reproduced)}/{len(reproduced)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=None,
                    help="config file (default ~/.llama/config.toml, as llama)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help):
        p = sub.add_parser(name, help=help)
        p.add_argument("--config", type=Path, default=argparse.SUPPRESS)
        p.set_defaults(fn=fn)
        return p

    p = add("pin", cmd_pin, "pin the campaign to a release tag (must be the running code)")
    p.add_argument("--tag", required=True)
    p.add_argument("--replace", action="store_true", help="overwrite an existing pin")
    p = add("arm", cmd_arm, "replay every show into an arm JSON (version and pin gated)")
    p.add_argument("--out", type=Path, required=True)
    p = add("snapshot", cmd_snapshot, "snapshot the listed shows into campaign/snapshots/")
    p.add_argument("--slugs", type=Path, required=True, help="a file of slugs, one per line")
    p = add("seal", cmd_seal, "seal a snapshot (record every show's after state)")
    p.add_argument("snap", type=Path)
    p = add("restore", cmd_restore, "rewind a snapshot's shows (dry run unless --apply)")
    p.add_argument("snap", type=Path)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--slugs", type=Path, default=None)
    p = add("backfill", cmd_backfill, "record the overnight verdicts' false holds as "
            "overrules (dry run unless --apply)")
    p.add_argument("--base", type=Path, required=True, help="the base arm (migration-base.json)")
    p.add_argument("--verdicts", type=Path, required=True, help="the verdicts directory")
    p.add_argument("--rehold-verdicts", type=Path, default=None,
                   help="the rehold-verdicts directory (rule b: decision overrule)")
    p.add_argument("--apply", action="store_true")
    p = add("freeze", cmd_freeze, "write the frozen needs-LLM list from an arm (once)")
    p.add_argument("--arm", type=Path, required=True)
    p.add_argument("--campaign-dir", type=Path, default=None,
                   help="default <root>/campaign")
    p = add("reselect-check", cmd_reselect_check, "re-check the verified re-selection list "
            "(read-only; --write records it)")
    p.add_argument("--source", type=Path, required=True,
                   help="the re-selection source list (m3_changed-r1.json)")
    p.add_argument("--write", action="store_true")
    p.add_argument("--campaign-dir", type=Path, default=None,
                   help="default <root>/campaign")
    p = add("mark", cmd_mark, "mark every show the fixes would change awaiting fix "
            "(dry run unless --apply)")
    p.add_argument("--arm", type=Path, required=True)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--campaign-dir", type=Path, default=None,
                   help="default <root>/campaign")
    p = add("unmark", cmd_unmark, "reverse one marking batch by its record "
            "(dry run unless --apply)")
    p.add_argument("--batch", type=Path, required=True, help="campaign/marking/<id>")
    p.add_argument("--apply", action="store_true")
    p = add("lists", cmd_lists, "write a wave list from an arm (read-only; selection rules in "
            "the spec)")
    p.add_argument("--arm", type=Path, required=True)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--profile", action="append", default=None)
    p.add_argument("--state", action="append", default=None)
    p.add_argument("--slugs", type=Path, default=None)
    p.add_argument("--kind", action="append", default=None, choices=LIST_KINDS)
    p.add_argument("--include-voiced", action="store_true")
    p.add_argument("--famous", type=Path, default=None,
                   help="slugs left out of the list and written to <out>.famous.txt")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--counts", action="store_true",
                   help="print per profile/kind counts instead of a list")
    p = add("wave-check", cmd_wave_check, "refuse a wave the station or the disk cannot take")
    p.add_argument("--list", type=Path, required=True)
    p = add("spot-check", cmd_spot_check, "seeded before/after sample of a reapply batch")
    p.add_argument("--batch", type=Path, required=True)
    p.add_argument("--n", type=int, default=5)
    p.add_argument("--seed", type=int, default=None)
    p = add("revoice-list", cmd_revoice_list, "rank the voiced shows awaiting fix by how "
            "wrong they are (read-only)")
    p.add_argument("--arm", type=Path, required=True)
    p.add_argument("--emcee-status", type=Path, required=True,
                   help="the file `emcee status --json` wrote")
    p.add_argument("--backend", choices=("voxtral", "mlx_audio", "elevenlabs"), default=None)
    p = add("trial-report", cmd_trial_report, "per-kind trial cost and the queue projection "
            "(read-only)")
    p.add_argument("--block", action="append", required=True,
                   help="<shape>-<kind>=<reapply batch dir>; kind fresh or needs-llm")
    p.add_argument("--queue", type=Path, required=True, help="`lists --counts` output")
    p.add_argument("--weekly-share", type=float, required=True,
                   help="points of the weekly all-models meter this work may use per week")
    p.add_argument("--shape", action="append", default=None,
                   help="<shape>=<profile>,<profile> (a profile alone is its own shape)")
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except (GateRefused, LlamaError) as err:
        print(str(err), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
