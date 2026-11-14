#!/usr/bin/env python3
"""Junk-title drop rollout tooling (spec
`docs/superpowers/specs/2026-11-13-junk-tag-drop-design.md`, "Rollout").

`list --arm A --emcee-status S --out DIR [--config P]` is the read-only membership list
(Rollout step 2). It reads the library, the station and the arm (a `replay_holds.py run
--all` arm written by THIS code under THIS config) and writes only under `DIR`:

- `members.json`: one row per member show (its drops, station state, the station tracks
  paired with a dropped source file, any other station-vs-library track difference);
- `reapply-replayable.json` / `reapply-needs-llm.json`: predicted lists for `llama reapply
  --from-list` (loadable by `reapply.load_list`), the second for the `--with-gather-llm`
  wave(s);
- `unpaired.json`: shows with drops whose station copy does not pair (left out, never
  guessed), and shows that could not be read.

A show's drops are the arm row's `junk_drops`, or, for a row the replay could not gather
LLM-free (`needs-llm`, `unreplayable`), `junk_titles.plan_drops` over the CURRENT
`show.json` (titles, set labels, `overrides.include`; breaker over show.json durations).
A show with a station copy is a member when a station track paired with `plan_reuse`
(show.json, else `reuse-anchor.json`) is a dropped source file; a show with no station
copy is a member when it has a drop.

`mark --list DIR/members.json [--config P] [--apply]` is the marking batch (Rollout step 3),
run BEFORE the release binaries are installed. It takes only the list (refused unless its
`sha` and `config_fingerprint` are the running code's and config's) and marks each member
with reason `junk-title drop` through `bulk_apply.mark_apply(skip_voiced=True,
no_copy_ok=True)`: under the station lock the station manifest is re-read; an unvoiced copy
(held or not) gets a station mark and a campaign mark, a voiced copy or none a campaign mark
only. No voiced station copy is ever marked. The batch is `<root>/campaign/marking/<id>/`
(`id` = the list's sha256, first 16), reversed by `bulk_apply.py unmark --batch`. The dry
run (no `--apply`) writes nothing and prints, per member, the station state it would act
on. `--apply` also requires the campaign pin and `llama`/`emcee` at least
JUNK_MARK_TOOLS_FLOOR.

`approval --list DIR/members.json --emcee-status S [--config P] [--backend B] [--out F]`
(Rollout step 6, read-only but for `--out`) is the operator's approval list of voiced copies,
from LIVE state: the station manifest decides voiced (a member voiced since the list appears;
one no longer voiced is listed under `no longer voiced (unvoiced route)`), the fresh status
file gives presenter and backend_now, the live `dj_audio` the clip count, the library
show.json the holds now (a held show is listed under `held (not approvable)`). `--out` gets
the approvable slugs, one per line. `recheck --list DIR/members.json [--config P] <slug>`
(read-only) is the check before `llama deliver <slug> --replace-voiced`: a member, a recorded
pair still on the station (file and title) whose source file the library show.json excludes
with reason `junk title`, not held, voiced. Exit 0 only when every check passes, else 1 and
`leave <slug> out of this batch`. Both take the list through the same identity gate as
`mark`.

Run it with the pinned worktree's own interpreter, by path. Refusals exit 2.
"""
import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bulk_apply   # noqa: E402
import replay_holds   # noqa: E402

import llama.replay   # noqa: E402
from llama import audio_reuse, junk_titles   # noqa: E402
from llama import station_mark   # noqa: E402
from llama.campaign_gate import (GateRefused, require_pinned_code,   # noqa: E402
                                 require_tools)
from llama.catalog import _performance_id   # noqa: E402
from llama.errors import LlamaError   # noqa: E402
from llama.models import Show   # noqa: E402
from llama.workspace import ShowWorkspace, read_model, read_overrides   # noqa: E402

SHOW_JSON_OUTCOMES = ("needs-llm", "unreplayable")
MEMBERS, REPLAYABLE, NEEDS_LLM, UNPAIRED = (
    "members.json", "reapply-replayable.json", "reapply-needs-llm.json", "unpaired.json")
OUTPUT_FILES = (MEMBERS, REPLAYABLE, NEEDS_LLM, UNPAIRED)
STATES = ("unvoiced", "voiced", "not on station")
# `mark --apply` runs before the release binaries are installed (spec Rollout step 3), so
# the installed tools are checked against this floor, not CAMPAIGN_MIN_VERSION.
JUNK_MARK_TOOLS_FLOOR = "2.23.0"
MARKING_DIR = Path("campaign") / "marking"


# --- gates ------------------------------------------------------------------------

def _station_gate(config) -> Path:
    """The configured station root, refused (GateRefused) when absent, unreadable or
    empty (an unmounted share). `list` and `mark` both pass through here."""
    station_root = config.delivery_path
    if station_root is None:
        raise GateRefused("no delivery_path in config: the station root is needed")
    problem = bulk_apply._station_root_problem(station_root)
    if problem == "empty":
        raise GateRefused(bulk_apply._empty_station_message(station_root))
    if problem is not None:
        raise GateRefused(f"station root {station_root} is {problem} (is the station mounted?)")
    return station_root


def _identity_gate(doc: dict, config, *, what: str, rerun: str) -> tuple[str, str]:
    """(running sha, config fingerprint) when `doc` (an arm or a list) was written by THIS
    code under THIS config; GateRefused otherwise, and always when either side is a
    `-dirty` tree. `what` names the document, `rerun` the command that rebuilds it.
    `list` and `mark` both pass through here."""
    sha = llama.replay.code_identity()
    fp = llama.replay.config_fingerprint(config)
    doc_sha = doc.get("sha")
    if str(doc_sha).endswith("-dirty") or sha.endswith("-dirty"):
        raise GateRefused(f"the {what} was written by code {doc_sha}; running code is {sha}: "
                          f"an uncommitted tree has no code identity, commit first and re-run "
                          f"{rerun}")
    if doc_sha != sha:
        raise GateRefused(f"the {what} was written by code {doc_sha}; running code is {sha}: "
                          f"re-run {rerun} from this tree")
    if doc.get("config_fingerprint") != fp:
        raise GateRefused(f"the {what} was written under config "
                          f"{doc.get('config_fingerprint')}; this config is {fp}")
    return sha, fp


def _out_gate(out: Path | None, config, station_root: Path) -> None:
    """GateRefused when `out` overlaps the library or the station root. `list` and
    `approval` both pass through here."""
    if out is None:
        return
    for what, p in (("library root", config.root), ("station root", station_root)):
        if replay_holds._overlaps(out, p):
            raise GateRefused(f"--out {out} overlaps the {what} {p}")


def _read_status(path: Path) -> dict[str, dict]:
    """slug -> row of an `emcee status --json` file."""
    _, doc = bulk_apply._read_json_file(path, "emcee status")
    if not isinstance(doc, list):
        raise GateRefused(f"{path} is not an `emcee status --json` list")
    return {s["slug"]: s for s in doc if isinstance(s, dict) and isinstance(s.get("slug"), str)}


def _gates(args):
    """(config, station_root, arm bytes, arm, running sha, fingerprint) or GateRefused."""
    config = bulk_apply._config(args)
    station_root = _station_gate(config)
    _out_gate(args.out, config, station_root)
    raw, arm = bulk_apply._read_json_file(args.arm, "arm")
    rows = bulk_apply._arm_rows(arm)
    sha, fp = _identity_gate(arm, config, what="arm", rerun="replay_holds.py run --all")
    return config, station_root, raw, rows, sha, fp


# --- per show ---------------------------------------------------------------------

def _arm_drops(row: dict) -> list[dict]:
    return [{"source_file": d.get("filename"), "title": d.get("title"),
             "duration_sec": d.get("duration_sec"), "set": d.get("set"),
             "after_track": d.get("after_track"), "rule": d.get("rule"),
             "held": bool(d.get("held"))}
            for d in (row.get("junk_drops") or []) if isinstance(d, dict)]


def _arm_predicted(row: dict) -> list[dict]:
    side = bulk_apply._row_side(row)
    return [{"source_file": t["filename"], "title": t["title"], "set": t["set"],
             "segue": bool(t["segue"])} for t in side]


def _show_json_plan(ws: ShowWorkspace, show: Show) -> tuple[list[dict], list[dict]]:
    """(drops, predicted kept tracks) from the current show.json, gather's rule: a kept
    track whose next track dropped loses its segue unless its own title ends in an arrow."""
    include = frozenset(read_overrides(ws).include)
    tracks = show.tracks
    plan = junk_titles.plan_drops(
        [junk_titles.DropInput(filename=t.filename, title=t.title, set=t.set,
                               duration_sec=t.duration_sec) for t in tracks], include=include)
    rules = {d.position: d.rule for d in plan}
    total, median = junk_titles.show_stats([t.duration_sec for t in tracks])
    drops, kept = [], []
    for i, t in enumerate(tracks):
        if i in rules:
            drops.append({"source_file": t.filename, "title": t.title,
                          "duration_sec": t.duration_sec, "set": t.set, "after_track": len(kept),
                          "rule": rules[i],
                          "held": junk_titles.held(t.duration_sec, total=total, median=median)})
            continue
        segue = bool(t.segue) and not ((i + 1) in rules
                                       and not junk_titles.trailing_arrow(t.title))
        kept.append({"source_file": t.filename, "title": t.title, "set": t.set, "segue": segue})
    return drops, kept


def _b(v) -> str:
    return "true" if v else "false"


def _other_differences(paired: list[tuple[str, dict]], drop_srcs: set[str],
                       predicted: list[dict]) -> list[str]:
    """The paired station tracks other than the drop pairs against the predicted
    post-reprocess tracks, by source file, in station order; added tracks last."""
    pred = {p["source_file"]: p for p in predicted}
    seen: set[str] = set()
    out: list[str] = []
    for src, st in paired:
        if src in drop_srcs:
            continue
        seen.add(src)
        p = pred.get(src)
        if p is None:
            out.append(f"removed {src} '{st.get('title')}'")
            continue
        if st.get("title") != p["title"]:
            out.append(f"title {src}: '{st.get('title')}' -> '{p['title']}'")
        if st.get("set") != p["set"]:
            out.append(f"set {src}: {st.get('set')} -> {p['set']}")
        if bool(st.get("segue")) != p["segue"]:
            out.append(f"segue {src}: {_b(st.get('segue'))} -> {_b(p['segue'])}")
    for p in predicted:
        if p["source_file"] not in seen and p["source_file"] not in drop_srcs:
            out.append(f"added {p['source_file']} '{p['title']}'")
    return out


def _backend_now(tts_now) -> str | None:
    if not isinstance(tts_now, dict):
        return None
    if "unresolved" in tts_now:
        return "unresolved"
    return tts_now.get("backend")


def _clips(dj_audio) -> int:
    if not isinstance(dj_audio, dict):
        return 0
    intros = dj_audio.get("set_intros")
    return (len(intros) if isinstance(intros, dict) else 0) + (1 if dj_audio.get("outro") else 0)


def _voiced_station(dj_audio, status_row: dict | None) -> dict:
    """A voiced copy's station entry: presenter and backend_now from its `emcee status
    --json` row, clips from its live `dj_audio`."""
    st = status_row or {}
    return {"state": "voiced", "presenter": st.get("voiced_by"),
            "backend_now": _backend_now(st.get("tts_now")), "clips": _clips(dj_audio)}


def _station_tracks(manifest: Path) -> tuple[dict | None, dict[str, dict]]:
    """(raw manifest or None when unreadable, packaged filename -> track)."""
    try:
        data = json.loads(manifest.read_text())
    except (OSError, ValueError):
        return None, {}
    if not isinstance(data, dict):
        return None, {}
    tracks = data.get("tracks") if isinstance(data.get("tracks"), list) else []
    return data, {t["filename"]: t for t in tracks
                  if isinstance(t, dict) and isinstance(t.get("filename"), str)}


def _one_show(root: Path, station_root: Path, slug: str, row: dict,
              status: dict[str, dict]) -> tuple[str, dict | None]:
    """("member" | "unpaired" | "none", row)."""
    ws = ShowWorkspace(root / "shows" / slug)
    if not ws.dir.is_dir():
        return "unpaired", {"slug": slug, "detail": "no library show directory", "drops": []}
    needs_llm = row.get("outcome") in SHOW_JSON_OUTCOMES
    try:
        if needs_llm:
            drops, predicted = _show_json_plan(ws, read_model(ws.show, Show))
        else:
            drops, predicted = _arm_drops(row), _arm_predicted(row)
    except (OSError, ValueError, LlamaError) as exc:
        return "unpaired", {"slug": slug, "detail": f"cannot read the show: "
                            f"{bulk_apply._one_line(exc)}", "drops": []}
    drop_srcs = {d["source_file"] for d in drops}
    st_dir = station_root / slug
    manifest = st_dir / "manifest.json"
    station = {"state": "not on station", "presenter": None, "backend_now": None, "clips": 0}
    pairs: list[dict] = []
    other: list[str] = []
    if manifest.exists():
        data, by_name = _station_tracks(manifest)
        plan = audio_reuse.plan_reuse(ws, st_dir)
        names = {src: path.name for src, path in plan.station.items()}
        if not names:
            if drops:
                return "unpaired", {"slug": slug, "detail": "station copy does not pair",
                                    "drops": drops}
            return "none", None
        order = list(by_name)
        paired = sorted(((src, by_name.get(n, {"filename": n})) for src, n in names.items()),
                        key=lambda p: order.index(p[1]["filename"])
                        if p[1]["filename"] in by_name else len(order))
        pairs = [{"station_file": st["filename"], "station_title": st.get("title"),
                  "source_file": src} for src, st in paired if src in drop_srcs]
        if not pairs:
            return "none", None
        other = _other_differences(paired, drop_srcs, predicted)
        dj = data.get("dj_audio") if data is not None else None
        if dj is not None:
            station = _voiced_station(dj, status.get(slug))
        else:
            station = {**station, "state": "unvoiced"}
    elif not drops:
        return "none", None
    return "member", {
        "slug": slug, "outcome": "member", "briefing": row.get("briefing"),
        "digests": row.get("digests") if isinstance(row.get("digests"), dict) else {},
        "needs_llm": needs_llm, "drop_source": "show.json" if needs_llm else "replay",
        "station": station, "drops": drops, "held": any(d["held"] for d in drops),
        "pairs": pairs, "other_differences": other,
        "arm_outcome": row.get("outcome")}


# --- list -------------------------------------------------------------------------

def _write(path: Path, doc: dict) -> None:
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")


def cmd_list(args) -> int:
    config, station_root, raw, rows, sha, fp = _gates(args)
    status = _read_status(args.emcee_status)
    members, unpaired = [], []
    for slug in sorted(rows):
        kind, item = _one_show(config.root, station_root, slug, rows[slug], status)
        if kind == "member":
            members.append(item)
        elif kind == "unpaired":
            unpaired.append(item)
    at = datetime.now(timezone.utc).isoformat()
    head = {"sha": sha, "config_fingerprint": fp, "written_at": at}
    member_rows = [{k: v for k, v in m.items() if k != "arm_outcome"} for m in members]
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    _write(out / MEMBERS, {**head, "arm_sha256": hashlib.sha256(raw).hexdigest(),
                           "rows": member_rows})

    def predicted(ms):
        return [{"slug": m["slug"], "outcome": m["arm_outcome"], "briefing": m["briefing"],
                 "digests": m["digests"]} for m in ms]
    llm = [m for m in members if m["needs_llm"]]
    _write(out / REPLAYABLE, {**head, "rows": predicted([m for m in members
                                                          if not m["needs_llm"]])})
    _write(out / NEEDS_LLM, {**head, "rows": predicted(llm)})
    _write(out / UNPAIRED, {**head, "rows": unpaired})

    states = Counter(m["station"]["state"] for m in members)
    backends = Counter(m["station"]["backend_now"] or "none" for m in members
                       if m["station"]["state"] == "voiced")
    print(f"members: {len(members)}")
    for s in STATES:
        print(f"  {s}: {states.get(s, 0)}")
    print("voiced by backend_now: " + (", ".join(f"{b} {n}" for b, n in sorted(backends.items()))
                                       or "none"))
    print(f"held: {sum(1 for m in members if m['held'])}")
    print(f"with-gather-llm wave: {len(llm)}")
    print(f"unpaired: {len(unpaired)}")
    for u in unpaired:
        print(f"  {u['slug']}: {u['detail']}")
    print(f"wrote {', '.join(OUTPUT_FILES)} to {out}")
    return 0


# --- mark -------------------------------------------------------------------------

def _read_list(path: Path, config) -> tuple[bytes, list[dict], str]:
    """(list bytes, member rows, running sha) of a `list` members.json written by THIS
    code and config."""
    raw, doc = bulk_apply._read_json_file(path, "membership list")
    if not isinstance(doc, dict) or not isinstance(doc.get("rows"), list):
        raise GateRefused(f"{path} is not a `junk_drop_rollout.py list` members.json")
    sha, _ = _identity_gate(doc, config, what="list", rerun="junk_drop_rollout.py list")
    rows, seen = [], set()
    for r in doc["rows"]:
        if not (isinstance(r, dict) and isinstance(r.get("slug"), str)
                and isinstance(r.get("digests"), dict)):
            raise GateRefused(f"{path}: a row without a slug or digests: {r!r}"[:300])
        if r["slug"] in seen:
            raise GateRefused(f"{path}: {r['slug']} is listed twice")
        seen.add(r["slug"])
        rows.append(r)
    return raw, rows, sha


def _dry_state(root: Path, station_root: Path, slug: str,
               delivered: "bulk_apply._DeliveredIds") -> tuple[str, bool]:
    """(the station state the apply would act on, whether it would station-mark), read now
    with no lock; the apply re-reads it under the station lock."""
    ws = ShowWorkspace(root / "shows" / slug)
    if not ws.dir.is_dir():
        return "no show directory", False
    try:
        pid = _performance_id(ws)
    except (OSError, ValueError, LlamaError) as exc:
        return f"unreadable show ({bulk_apply._one_line(exc)})", False
    if not (pid and pid in delivered):
        return "not delivered", False
    out = station_root / slug
    problem = bulk_apply._station_copy_problem(out)
    if problem is not None:
        return problem, False
    try:
        _, data = station_mark.read_station_manifest(out)
    except LlamaError as exc:
        return f"unreadable ({bulk_apply._one_line(exc)})", False
    if data.get("dj_audio") is not None:
        return "voiced", False
    if station_mark.mark_of(data) is not None:
        return "unvoiced, already marked", False
    return "unvoiced", True


def cmd_mark(args) -> int:
    config = bulk_apply._config(args)
    root = config.root
    station_root = _station_gate(config)
    raw, rows, sha = _read_list(args.list, config)
    if not args.apply:
        delivered = bulk_apply._DeliveredIds(root / "ledger.jsonl")
        counts: Counter = Counter()
        for r in rows:
            state, would = _dry_state(root, station_root, r["slug"], delivered)
            held = " (held)" if r.get("held") else ""
            act = "would station-mark" if would else "campaign mark only"
            counts[act] += 1
            print(f"{r['slug']}: {state}{held}: {act}")
        print(f"members: {len(rows)}; would station-mark {counts['would station-mark']}, "
              f"campaign mark only {counts['campaign mark only']}")
        running = station_mark.emcee_running()
        print("emcee running: " + ("yes" if running else "no"))
        for line in running:
            print(f"  {line}")
        print("dry run: nothing written (pass --apply)")
        return 0
    pin = require_pinned_code(root)
    require_tools(bulk_apply._echo, pin=pin, minimum=JUNK_MARK_TOOLS_FLOOR)
    items = [bulk_apply.MarkItem(r["slug"], bulk_apply.REASON_JUNK, "gather", r["digests"])
             for r in rows]
    batch = root / MARKING_DIR / hashlib.sha256(raw).hexdigest()[:16]
    if not (batch / "inputs.json").exists():
        bulk_apply._write_json(batch / "inputs.json", {
            "list": str(args.list), "list_sha256": hashlib.sha256(raw).hexdigest(),
            "sha": sha, "station_root": str(station_root),
            "created_at": datetime.now(timezone.utc).isoformat()})
    return bulk_apply.mark_apply(root, items, station_root=station_root, batch=batch,
                                 echo=bulk_apply._echo, skip_voiced=True, no_copy_ok=True)


# --- approval and recheck ---------------------------------------------------------

BACKENDS = ("voxtral", "mlx_audio", "elevenlabs")


def _library_show(root: Path, slug: str) -> tuple[Show | None, str | None]:
    """(the library show.json now, or None and why)."""
    ws = ShowWorkspace(root / "shows" / slug)
    if not ws.show.exists():
        return None, "no library show.json"
    try:
        return read_model(ws.show, Show), None
    except (OSError, ValueError, LlamaError) as exc:
        return None, f"cannot read show.json: {bulk_apply._one_line(exc)}"


def _mmss(d) -> str:
    s = int(round(float(d or 0)))
    return f"{s // 60}:{s % 60:02d}"


def _null(v) -> str:
    return "null" if v is None else str(v)


def cmd_approval(args) -> int:
    """The operator's approval list for the voiced batch (Rollout step 6), from LIVE
    state: the station manifest decides voiced, the fresh status file the presenter and
    backend_now, the library show.json the holds. Writes only `--out`."""
    config = bulk_apply._config(args)
    station_root = _station_gate(config)
    _out_gate(args.out, config, station_root)
    _, rows, _ = _read_list(args.list, config)
    status = _read_status(args.emcee_status)
    approvable, held, gone, cannot = [], [], [], []
    unvoiced = other_backend = 0
    for r in rows:
        slug = r["slug"]
        was_voiced = (r.get("station") or {}).get("state") == "voiced"
        manifest = station_root / slug / "manifest.json"
        data, _ = _station_tracks(manifest)
        if data is None:
            if manifest.exists():
                cannot.append(f"{slug}: station manifest unreadable")
            elif was_voiced:
                cannot.append(f"{slug}: no station copy")
            else:
                unvoiced += 1
            continue
        dj = data.get("dj_audio")
        if dj is None:
            if was_voiced:
                gone.append(slug)
            else:
                unvoiced += 1
            continue
        station = _voiced_station(dj, status.get(slug))
        if args.backend and station["backend_now"] != args.backend:
            other_backend += 1
            continue
        show, problem = _library_show(config.root, slug)
        if show is None:
            cannot.append(f"{slug}: {problem}")
            continue
        (held if show.needs_review else approvable).append((r, station, show.review_flags))

    def block(r, station, flags):
        print(f"  {r['slug']}: presenter {_null(station['presenter'])}, backend_now "
              f"{_null(station['backend_now'])}, clips {station['clips']}")
        for d in r.get("drops") or []:
            print(f"    drop '{d.get('title')}' {_mmss(d.get('duration_sec'))} held "
                  f"{'yes' if d.get('held') else 'no'}")
        for o in r.get("other_differences") or []:
            print(f"    other {o}")
        print("    library hold flags: " + ("; ".join(flags) or "none"))

    print(f"approvable: {len(approvable)}")
    for e in approvable:
        block(*e)
    print(f"held (not approvable): {len(held)}")
    for e in held:
        block(*e)
    print(f"no longer voiced (unvoiced route): {len(gone)}")
    for slug in gone:
        print(f"  {slug}")
    print(f"cannot check (not approvable): {len(cannot)}")
    for line in cannot:
        print(f"  {line}")
    print(f"unvoiced members (not in this list): {unvoiced}")
    if args.backend:
        print(f"voiced members on another backend_now (not shown): {other_backend}")
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("".join(f"{r['slug']}\n" for r, _, _ in approvable))
        print(f"wrote {len(approvable)} approvable slugs to {args.out}")
    return 0


def cmd_recheck(args) -> int:
    """The pre-`--replace-voiced` re-check of one approved show (Rollout step 6). Writes
    nothing; exit 0 only when every check passes, 1 otherwise."""
    config = bulk_apply._config(args)
    station_root = _station_gate(config)
    _, rows, _ = _read_list(args.list, config)
    slug = args.slug
    row = next((r for r in rows if r["slug"] == slug), None)
    checks = [("member of the list", row is not None, None)]
    if row is not None:
        manifest = station_root / slug / "manifest.json"
        data, by_name = _station_tracks(manifest)
        show, problem = _library_show(config.root, slug)
        junk = {e.get("filename") for e in (show.excluded_files if show else [])
                if isinstance(e, dict) and junk_titles.REASON in (e.get("reasons") or [])}
        pairs = [p for p in row.get("pairs") or [] if isinstance(p, dict)]
        live, why = [], []
        for p in pairs:
            st = by_name.get(p.get("station_file"))
            if st is None or st.get("title") != p.get("station_title"):
                why.append(f"'{p.get('station_file')}' '{p.get('station_title')}' "
                           f"not in the station manifest")
            elif p.get("source_file") not in junk:
                why.append(f"{p.get('source_file')} not excluded with reason "
                           f"'{junk_titles.REASON}' in the library show.json")
            else:
                live.append(f"{p['station_file']} -> {p['source_file']}")
        if data is None:
            why.insert(0, "station manifest missing or unreadable")
        if show is None:
            why.insert(0, problem)
        if not pairs:
            why.append("the list records no pair")
        checks.append(("a recorded pair is on the station and dropped in the library",
                       bool(live), "; ".join(live) if live else "; ".join(why)))
        checks.append(("library show not held", show is not None and not show.needs_review,
                       problem if show is None
                       else ("; ".join(show.review_flags) or None) if show.needs_review
                       else None))
        checks.append(("station copy voiced",
                       data is not None and data.get("dj_audio") is not None,
                       None if data is not None else "station manifest missing or unreadable"))
    for name, ok, detail in checks:
        print(f"{slug}: {name}: {'ok' if ok else 'FAIL'}" + (f" ({detail})" if detail else ""))
    if all(ok for _, ok, _ in checks):
        print(f"{slug}: recheck passed")
        return 0
    print(f"leave {slug} out of this batch")
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", type=Path, default=None,
                        help="config.toml (the library root, station root and fingerprint)")
    p = sub.add_parser("list", parents=[common],
                       help="the read-only membership list (writes only under --out)")
    p.add_argument("--arm", type=Path, required=True,
                   help="a `replay_holds.py run --all` arm from this code and config")
    p.add_argument("--emcee-status", type=Path, required=True,
                   help="the file `emcee status --json` wrote")
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(fn=cmd_list)
    p = sub.add_parser("mark", parents=[common],
                       help="the junk-title drop marking batch (dry run unless --apply)")
    p.add_argument("--list", type=Path, required=True,
                   help="the members.json `list` wrote, from this code and config")
    p.add_argument("--apply", action="store_true",
                   help="write the campaign and station marks (never a voiced copy's)")
    p.set_defaults(fn=cmd_mark)
    p = sub.add_parser("approval", parents=[common],
                       help="the voiced approval list from live state (writes only --out)")
    p.add_argument("--list", type=Path, required=True,
                   help="the members.json `list` wrote, from this code and config")
    p.add_argument("--emcee-status", type=Path, required=True,
                   help="a FRESH `emcee status --json` file")
    p.add_argument("--backend", choices=BACKENDS, default=None,
                   help="only voiced members whose backend_now is this")
    p.add_argument("--out", type=Path, default=None,
                   help="write the approvable slugs here, one per line")
    p.set_defaults(fn=cmd_approval)
    p = sub.add_parser("recheck", parents=[common],
                       help="the read-only re-check before `deliver --replace-voiced`")
    p.add_argument("--list", type=Path, required=True,
                   help="the members.json `list` wrote, from this code and config")
    p.add_argument("slug")
    p.set_defaults(fn=cmd_recheck)
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except (GateRefused, LlamaError) as err:
        print(str(err), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
