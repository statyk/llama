#!/usr/bin/env python3
"""The bulk-apply campaign's operator script (plan Task 12 scaffold).

Subcommands: `pin` (pin the campaign to a release tag's commit), `arm` (the replay arm,
behind the version and pin gates), `snapshot` / `seal` / `restore` (thin wrappers over
`llama.batch_snapshot`) and `backfill` (plan Task 14: the overrule backfill from the
overnight verdicts, dry run unless `--apply`); plan Task 15: `freeze` (the frozen needs-LLM
list), `reselect-check` (the verified re-selection list, re-checked read-only), `mark` (the
marking batch, dry run unless `--apply`) and `unmark` (its reversal, by its record). A
refused gate exits 2. Run with the pinned worktree's own interpreter:
`./.venv/bin/python scripts/bulk_apply.py ...`.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

import replay_holds

import llama
import llama.replay
from llama import batch_snapshot, campaign, station_mark
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


def _verdict(verdicts: Path, slug: str) -> dict | None:
    path = verdicts / f"{slug}.json"
    if not path.exists():
        return None
    try:
        v = json.loads(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise LlamaError(f"{path} unreadable ({exc}); nothing planned") from exc
    if not isinstance(v, dict):
        raise LlamaError(f"{path} is not a verdict object; nothing planned")
    return v


def _rulings(v: dict) -> tuple[dict[str, list[tuple[str, bool]]], set[str], set[str]]:
    """(flag -> [(verdict, is that layout's false-hold value)], flags named by
    `action.overrule_if_reheld_on`, `other_flags` texts)."""
    ruled: dict[str, list[tuple[str, bool]]] = {}
    for key, value in _RECORDED:
        for e in v.get(key) or []:
            if isinstance(e, dict) and isinstance(e.get("flag"), str):
                ruled.setdefault(e["flag"], []).append(
                    (str(e.get("verdict")), e.get("verdict") == value))
    action = v.get("action")
    oir = action.get("overrule_if_reheld_on") if isinstance(action, dict) else None
    named = {f for f in oir or [] if isinstance(f, str)}
    other = {e["flag"] for e in v.get("other_flags") or []
             if isinstance(e, dict) and isinstance(e.get("flag"), str)}
    return ruled, named, other


def _titles_rule(flag: str, show: Show, row: dict, at: str) -> Overrule | None:
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
                    source="backfill", at=at)


def _plan_one(root: Path, row: dict, verdicts: Path, delivered: set[str],
              at: str) -> BackfillShow | None:
    """One base row's plan; None when it is not considered (the base outcome or state,
    or the show is held today)."""
    if not _considered(row):
        return None
    slug = row["slug"]
    ws = ShowWorkspace(root / "shows" / slug)
    if not ws.show.exists():
        return BackfillShow(slug, [], [], NO_SHOW_JSON)
    try:
        if derive_state(ws, delivered)[0] == "held":
            return None
        show = read_model(ws.show, Show)
    except Exception as exc:
        return BackfillShow(slug, [], [], f"show.json unreadable: {' '.join(str(exc).split())}")
    v = _verdict(verdicts, slug)
    if v is None:
        return BackfillShow(slug, [], [], NO_VERDICT)
    ruled, named, other = _rulings(v)
    flags = (list(row.get("gather_flags") or []) + list(row.get("vet_flags") or [])
             + list(row.get("brief_flags") or []))
    record: list[Overrule] = []
    listed: list[tuple[str, str]] = []
    for f in flags:
        key = flag_key(f, show)
        if key is None:
            listed.append((f, NOT_OVERRULABLE))
            continue
        rulings = ruled.get(f, [])
        if f in named or (rulings and all(ok for _, ok in rulings)):
            if key.kind == "titles":
                rule = _titles_rule(f, show, row, at)
                if rule is None:
                    listed.append((f, NO_TITLES))
                else:
                    record.append(rule)
            else:
                record.extend(records_for([f], show, source="backfill", at=at))
        elif rulings:
            listed.append((f, f"ruled {next(vd for vd, ok in rulings if not ok)}"))
        elif f in other:
            listed.append((f, OTHER_ONLY))
        else:
            listed.append((f, NEVER_RULED))
    return BackfillShow(slug, record, listed, None)


def plan_backfill(root: Path, base: dict, verdicts: Path,
                  delivered: set[str]) -> list[BackfillShow]:
    """Every base row newly held under the pre-piece-4 code (outcome `newly-held`, state
    not `held`) whose show is not held today, with the overrules to record and the flags
    listed for the operator. `delivered` is the ledger's delivered performance ids (as
    `llama status` derives state). Reads only."""
    at = datetime.now(timezone.utc).isoformat()
    out = []
    for row in _base_rows(base):
        planned = _plan_one(root, row, verdicts, delivered, at)
        if planned is not None:
            out.append(planned)
    return out


def _print_plan(plan: list[BackfillShow], rows: dict[str, dict]) -> None:
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
            print(f"  record: {r.flag}")
        for f, why in s.listed:
            print(f"  list: {f} ({why})")
    with_verdict = [s for s in plan if s.show_reason is None]
    covered = sum(1 for s in with_verdict if s.record and not s.listed)
    other = sum(1 for s in plan if s.show_reason not in (None, NO_VERDICT))
    line = (f"totals: shows considered {len(plan)}, "
            f"shows with no verdict {sum(s.show_reason == NO_VERDICT for s in plan)}, "
            f"flags recorded {sum(len(s.record) for s in plan)}, "
            f"flags listed {sum(len(s.listed) for s in plan)}, "
            f"shows fully covered {covered} of {len(with_verdict)}")
    if other:
        line += f", shows listed for another reason {other}"
    print(line)


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
                  delivered: set[str], station_root: Path | None, at: str) -> str:
    """One show's unit, inside `show_unit` (which takes the show lock): re-plan, re-read
    `overrides.json`, merge, write, then `record_after` (the show's final state; nothing
    tracked is written after it) and the batch record. Any failure, Ctrl-C included,
    restores every file outside `package/audio/`, so a write the batch could not record
    is undone and every recorded write stays restorable (spec "Undo")."""
    slug = row["slug"]
    ws = ShowWorkspace(root / "shows" / slug)
    with show_unit(ws, None):
        planned = _plan_one(root, row, verdicts, delivered, at)
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
    delivered = {e.performance_id for e in Ledger(root / "ledger.jsonl").entries()
                 if e.status == "delivered"}
    plan = plan_backfill(root, base, args.verdicts, delivered)
    rows = {r["slug"]: r for r in _base_rows(base)}
    _print_plan(plan, rows)
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
                                    station_root, at)
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
_REASON_KINDS = (REASON_CHANGED, REASON_LLM, REASON_GUARD, REASON_RESELECTION)
# Rows whose diff comes from the provider-less fallback alignment (an artefact): they are
# marked only by a re-selection or by the frozen list, never by a visible change.
_NO_DIFF = ("needs-llm", "unreplayable")
_PLAN_COLUMNS = ("delivered unvoiced", "delivered voiced", "packaged", "briefed", "held")
_STATION_OK = ("marked", "already marked", "no station copy")


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


def _stored_show(ws: ShowWorkspace) -> Show | None:
    try:
        return read_model(ws.show, Show)
    except (OSError, ValueError):
        return None


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


def _plan_one_mark(ws: ShowWorkspace, row: dict | None, frozen: set[str],
                   resel: dict | None) -> tuple[str, str, dict | None] | None:
    """(reason, start stage, digests) or None, in the brief's priority order."""
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
    if stored is not None:
        if row_label_only(row, stored):
            return None
        visible = row_visible_changes(row, stored)
        if visible:
            return f"{REASON_CHANGED}: {', '.join(visible)}", "gather", digests
    if processed:
        return None
    if slug in frozen:
        return _llm_reason(row), "gather", digests
    if stored is not None and _guard_holds(ws, row, stored):
        return REASON_GUARD, "gather", digests
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


def mark_plan(root: Path, arm: dict, frozen: set[str], reselections: list[dict],
              delivered: set[str]) -> list[MarkItem]:
    """Every show the marking rule selects (spec "Who gets marked", "Marking skips"), in
    slug order. `delivered` is the ledger's delivered performance ids. Reads only."""
    rows = _arm_rows(arm)
    resel = {r["slug"]: r for r in reselections}
    items = []
    for slug in sorted(set(rows) | set(resel)):
        ws = ShowWorkspace(root / "shows" / slug)
        if not ws.dir.is_dir():
            continue
        planned = _plan_one_mark(ws, rows.get(slug), frozen, resel.get(slug))
        if planned is not None:
            items.append(MarkItem(slug, *planned, state=_plan_state(ws, delivered)))
    return items


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


def _has_batch_mark(ws: ShowWorkspace, batch_id: str) -> bool:
    try:
        rec = campaign.read_record(ws)
    except campaign.CampaignUnreadable:
        return False
    return rec is not None and any(m.batch == batch_id for m in rec.marks)


def _mark_station(item: MarkItem, out: Path, batch: Path,
                  at: str) -> tuple[str, str | None, str | None]:
    """(station outcome, before sha, after sha) for a delivered show's station copy.
    The caller checked emcee just before. Never raises for a station problem (pointer c)."""
    try:
        raw, data = station_mark.read_station_manifest(out)
        if station_mark.mark_of(data) is not None:
            return "already marked", None, None
        saved = batch / "before" / f"{item.slug}.json"
        _write_durable(saved, raw)                        # before any station write
        before, after = station_mark.write_mark(out, reason=item.reason, marked_at=at)
        if before != raw:
            _write_durable(saved, before)
    except (LlamaError, OSError) as exc:
        return f"refused: {_one_line(exc)}", None, None
    return "marked", hashlib.sha256(before).hexdigest(), hashlib.sha256(after).hexdigest()


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


def _mark_one(root: Path, item: MarkItem, station_root: Path, batch: Path,
              record: Path, delivered_ids: _DeliveredIds) -> tuple[str, bool, list[str]]:
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
        mark_added = _has_batch_mark(ws, batch.name)
        before_sha = after_sha = None
        running: list[str] = []
        out = station_root / item.slug
        if not delivered:
            station = "not delivered"
        elif not station_root.is_dir():
            station = f"refused: station root {station_root} is not readable"
        elif not out.is_dir():
            station = "no station copy"
        else:
            running = station_mark.emcee_running()     # before EACH write (pointer b)
            if running:
                station = "refused: emcee is running"
            else:
                station, before_sha, after_sha = _mark_station(item, out, batch, at)
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
    recorded with a non-refused station outcome are skipped. A running emcee stops the
    batch. Exit 0 only when every delivered item's station copy is marked (or already
    marked, or there is none); else 1, listing each that is not."""
    (batch / "before").mkdir(parents=True, exist_ok=True)
    record = batch / "record.jsonl"
    done = {s: r for s, r in _last_lines(record).items()
            if not str(r.get("station", "refused")).startswith("refused")}
    listed: list[str] = []
    counts: Counter = Counter()
    stop: list[str] = []
    delivered_ids = _DeliveredIds(root / "ledger.jsonl")
    for item in items:
        if stop:
            listed.append(f"{item.slug}: not reached (emcee is running)")
            continue
        if item.slug in done:
            echo(f"{item.slug}: skipped: already recorded ({done[item.slug]['station']})")
            counts["already recorded"] += 1
            continue
        try:
            what, problem, stop = _mark_one(root, item, station_root, batch, record,
                                            delivered_ids)
        except Exception as exc:
            what, problem = f"error: {_one_line(exc)}", True
        echo(f"{item.slug}: {what}")
        key = what.split(" (")[0]
        counts["refused" if key.startswith("refused") else
               "error" if key.startswith("error") else key] += 1
        if problem:
            listed.append(f"{item.slug}: {what}")
        if stop:
            echo("refusing to mark station copies: emcee is running; the batch stops")
            for line in stop:
                echo(f"  {line}")
    echo(f"marking {batch.name}: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
         + f"; record: {record}")
    if listed:
        echo(f"not marked ({len(listed)}); do not run emcee on their profiles until a "
             "re-run of this batch exits 0:")
        for line in listed:
            echo(f"  {line}")
        return 1
    return 0


def _after(later: str, earlier: str) -> bool:
    """`later` is at or after `earlier`; an unparseable time counts as after (the
    reversal's safe direction: it then lists the show instead of unmarking it)."""
    a, b = campaign._parse(later), campaign._parse(earlier)
    return a is None or b is None or a >= b


def _unmark_one(ws: ShowWorkspace, line: dict, batch: Path, station_root: Path,
                apply: bool) -> tuple[str, bool]:
    """(what happened, whether it is a problem). Under the show lock."""
    slug, bid = ws.dir.name, batch.name
    rec = campaign.read_record(ws)                        # CampaignUnreadable: an error
    mark = next((m for m in reversed(rec.marks) if m.batch == bid), None) if rec else None
    if mark is not None and rec.processed is not None and _after(rec.processed.at, mark.at):
        return "processed since marked: re-deliver instead", True
    restore = None
    out = station_root / slug
    if line.get("station") == "marked":
        current = hashlib.sha256(station_mark.read_station_manifest(out)[0]).hexdigest()
        if current == line.get("after_sha256"):
            restore = (batch / "before" / f"{slug}.json").read_bytes()
            if hashlib.sha256(restore).hexdigest() != line.get("before_sha256"):
                return f"refused: before/{slug}.json does not match the record", True
        elif current != line.get("before_sha256"):       # equal: already put back
            return "station copy changed since marking", True
    what = ("station copy put back; " if restore is not None else "") + "batch mark removed"
    if not apply:
        return f"would be: {what}", False
    if restore is not None:
        running = station_mark.emcee_running()
        if running:
            return "refused: emcee is running (" + "; ".join(running) + ")", True
        station_mark.put_back(out, expect_sha256=line["after_sha256"], data=restore)
    campaign.remove_marks(ws, bid)
    return what, False


def unmark(root: Path, batch: Path, *, station_root: Path, apply: bool, echo) -> int:
    """The marking batch's reversal (spec "A batch is reversible by its record"), by each
    slug's last record line with `mark_added`: a show processed since the batch's mark is
    listed and left alone; a `marked` station copy is put back only while it still holds
    the bytes marking wrote; then the batch's library mark is removed. A line with
    `mark_added: false` keeps the earlier batch's mark (and its station copy). Exit 1 when
    anything is listed."""
    record = batch / "record.jsonl"
    if not record.exists():
        raise LlamaError(f"no record.jsonl in {batch}")
    problems = 0
    for slug, line in sorted(_last_lines(record).items()):
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
    if not out.is_dir():
        return "delivered no station copy", None
    try:
        voiced = destination_voiced(out)
    except LlamaError as exc:
        return "delivered unreadable", _one_line(exc)
    return ("delivered voiced" if voiced else "delivered unvoiced"), None


def _print_mark_plan(items: list[MarkItem], arm: dict, station_root: Path) -> None:
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
    running = station_mark.emcee_running()
    print("emcee running: " + ("yes" if running else "no"))
    for line in running:
        print(f"  {line}")


def cmd_mark(args) -> int:
    config = _config(args)
    root, station_root = config.root, config.delivery_path
    if station_root is None:
        raise GateRefused("no delivery_path in config")
    if not station_root.is_dir():
        raise GateRefused(f"station root {station_root} is not mounted or not a directory")
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
    items = mark_plan(root, arm, set(frozen["slugs"]), resel["rows"], delivered)
    _print_mark_plan(items, arm, station_root)
    if not args.apply:
        print("dry run: nothing written (pass --apply)")
        return 0
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
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except (GateRefused, LlamaError) as err:
        print(str(err), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
