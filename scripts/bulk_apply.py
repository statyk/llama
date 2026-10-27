#!/usr/bin/env python3
"""The bulk-apply campaign's operator script (plan Task 12 scaffold).

Subcommands: `pin` (pin the campaign to a release tag's commit), `arm` (the replay arm,
behind the version and pin gates), `snapshot` / `seal` / `restore` (thin wrappers over
`llama.batch_snapshot`) and `backfill` (plan Task 14: the overrule backfill from the
overnight verdicts, dry run unless `--apply`). Later tasks add the writing subcommands
here. A refused gate exits 2. Run with the pinned worktree's own interpreter:
`./.venv/bin/python scripts/bulk_apply.py ...`.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

import replay_holds

import llama
from llama import batch_snapshot
from llama.campaign_gate import (_VERSION, GateRefused, read_pin, require_pinned_code,
                                 require_tools, retire_rekey_restore, write_pin)
from llama.catalog import _sync_fd, derive_state
from llama.config import DEFAULT_ROOT, load_config
from llama.errors import LlamaError
from llama.ledger import Ledger
from llama.models import Overrule, Show
from llama.override_keys import refusal as overrides_refusal
from llama.overrules import flag_key, merge_rules, records_for
from llama.replay import code_identity
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
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except (GateRefused, LlamaError) as err:
        print(str(err), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
