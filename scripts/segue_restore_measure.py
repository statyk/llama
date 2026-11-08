#!/usr/bin/env python3
"""Offline measurement for the segue restore pass (spec
2026-11-07-segue-restore-design, "Measurement").

One replay per show gives both arms at once: `llama.stages.gather.restore_segues`
is wrapped by a recorder that calls the REAL function twice (with the real donor,
and with `donor=None`) and records its input segues (arm A, restore off), its
output (arm B) and the second call's extra adds (the donor-said-no skips). No rule
logic is copied here.

    spot    --slugs S... --out DIR [--live]   shows stored with alignment `llm`
    library --out DIR [--limit N] [--seed N]  every show with no gather LLM touchpoint

`spot` answers the alignment LLM from each show's stored `show.json` (a stub), so
it replays what shipped; `--live` calls the real configured providers instead
(extract_setlist, align_structure). Read-only: nothing is written but
DIR and the replay scratch dirs (DIR/scratch). Run with this tree's own
interpreter: `./.venv/bin/python scripts/segue_restore_measure.py ...`.
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

import llama
from llama.config import DEFAULT_ROOT, load_config
from llama.ledger import Ledger
from llama.replay import CacheOnlyIA, compute_legs, setlistfm_client
from llama.songs import normalize_song
from llama.stages import gather
from llama.workspace import ShowWorkspace

SAMPLE_N = 20
DEFAULT_SEED = 20261107
FORMS = (">", "->", ") (>", "other")
_TRACK_LINE = re.compile(r"^(\d+) \| (.+?) \| (.*) \| (\S+)$")


class Refusal(Exception):
    """Exit 2 with this message."""


# --- the stub alignment provider ---------------------------------------------

class StubAligner:
    """`.complete(prompt) -> str` answering `align_structure` from the stored show:
    every index of the prompt's `index | filename | title | dur` lines gets the set and
    segue of the stored track with that filename and `matched_title` = the line's title.
    A filename missing from the stored show gets the previous track's set, no segue."""

    def __init__(self, stored_tracks):
        self.by_name = {t.filename: t for t in stored_tracks}

    def complete(self, prompt: str) -> str:
        out, prev_set = [], "1"
        for line in prompt.splitlines():
            mt = _TRACK_LINE.match(line.strip())
            if not mt:
                continue
            idx, fn, title = int(mt.group(1)), mt.group(2), mt.group(3)
            st = self.by_name.get(fn)
            set_, segue = (st.set, bool(st.segue)) if st is not None else (prev_set, False)
            prev_set = set_
            out.append({"index": idx, "set": set_, "segue": segue, "matched_title": title})
        return json.dumps({"tracks": out})


# --- info forms ----------------------------------------------------------------

def info_form(info: str | None) -> str:
    """`">"`, `"->"`, `") (>"` (a parenthesised note then `(>`) or `"other"`."""
    s = (info or "").strip()
    if s == ">":
        return ">"
    if s == "->":
        return "->"
    if re.search(r"\)\s*\(\s*>$", s):
        return ") (>"
    return "other"


def infos_for_tracks(titles: list[str], raw: dict | None) -> list[str | None]:
    """Each track's setlist.fm `info`: walk the cached raw songs in order and match on
    `normalize_song` title, first unused match. None = no raw or no match; "" = a match
    with no info."""
    if not raw:
        return [None] * len(titles)
    songs = []
    for s in (raw.get("sets") or {}).get("set") or []:
        for song in s.get("song", []):
            name = (song.get("name") or "").strip()
            if name and not song.get("tape"):
                songs.append((normalize_song(name), (song.get("info") or "").strip()))
    used = [False] * len(songs)
    out: list[str | None] = []
    for title in titles:
        want, found = normalize_song(title), None
        for i, (norm, info) in enumerate(songs):
            if not used[i] and norm == want:
                used[i], found = True, info
                break
        out.append(found)
    return out


# --- the recorder ----------------------------------------------------------------

class Recorder:
    """Wraps `restore_segues`: records arm A (input), arm B (output) and the donor-said-no
    skips (adds of a second call with `donor=None` that the real call did not make)."""

    def __init__(self, real):
        self.real = real
        self.calls: list[dict] = []

    def __call__(self, tracks, segues, **kw):
        result = self.real(tracks, segues, **kw)
        nodonor = self.real(tracks, segues, **{**kw, "donor": None})
        added = {k for k, _ in result[1]}
        self.calls.append({
            "a": list(segues), "b": list(result[0]), "adds": list(result[1]),
            "skips": [(k, ev) for k, ev in nodonor[1] if k not in added],
            "titles": [t.title for t in tracks], "filenames": [t.filename for t in tracks]})
        return result


class RecordingSlfm:
    """Passes a `CacheOnlySetlistFM` through, keeping the last raw setlist it returned."""

    def __init__(self, inner):
        self.inner, self.last = inner, None

    def setlist(self, *args, **kwargs):
        self.last = self.inner.setlist(*args, **kwargs)
        return self.last

    def __getattr__(self, name):
        return getattr(self.inner, name)


# --- sampling ---------------------------------------------------------------------

def stratified_sample(rows: list[dict], n: int, *, seed: int, key) -> list[dict]:
    """`n` rows round-robin across the strata of `key`, each stratum shuffled by a
    seeded RNG over rows sorted by (slug, track): deterministic in the input set."""
    groups: dict = defaultdict(list)
    for r in sorted(rows, key=lambda r: (r["slug"], r["track"])):
        groups[key(r)].append(r)
    rng = random.Random(seed)
    queues = []
    for k in sorted(groups, key=str):
        q = list(groups[k])
        rng.shuffle(q)
        queues.append(q)
    out: list[dict] = []
    while len(out) < n and any(queues):
        for q in queues:
            if q and len(out) < n:
                out.append(q.pop())
    return out


def description_line(cache_dir: Path, identifier: str, title: str) -> str:
    """The selected recording's description line containing `title` (cached metadata)."""
    try:
        meta = json.loads((cache_dir / f"md_{identifier}.json").read_text())
    except Exception:
        return ""
    desc = (meta.get("metadata") or meta).get("description") or ""
    if isinstance(desc, list):
        desc = "\n".join(str(d) for d in desc)
    want = title.lower()
    for line in re.split(r"<br\s*/?>|\n", str(desc)):
        if want and want in line.lower():
            return line.strip()
    return ""


# --- one show ---------------------------------------------------------------------

def replay_one(ws: ShowWorkspace, *, config, ia, slfm, scratch: Path, rec: Recorder,
               providers=None) -> tuple[object, dict]:
    """Replay `ws`; returns (legs, row). The row is the recorder's last call, with each
    add/skip given its setlist.fm `info` and form."""
    rec.calls.clear()
    proxy = RecordingSlfm(slfm) if slfm is not None else None
    try:
        legs = compute_legs(ws, config=config, ia=ia, slfm=proxy, scratch=scratch,
                            gather_providers=providers, llm_failures_raise=providers is not None)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    row: dict = {"slug": ws.dir.name, "identifier": legs.stored.identifier,
                 "alignment": (legs.gather.show.structure.alignment
                               if legs.gather.show.structure else None),
                 "adds": [], "skips": [], "called": bool(rec.calls)}
    if rec.calls:
        call = rec.calls[-1]
        infos = infos_for_tracks(call["titles"], proxy.last if proxy else None)

        def item(k, ev):
            e3 = ev == "setlist.fm"
            info = infos[k] if e3 else None
            return {"slug": ws.dir.name, "track": k + 1, "title": call["titles"][k],
                    "evidence": ev, "info": info,
                    "form": info_form(info) if e3 else "deterministic"}

        row["adds"] = [item(k, ev) for k, ev in call["adds"]]
        row["skips"] = [item(k, ev) for k, ev in call["skips"]]
        stored = {t.filename: t.segue for t in legs.stored.tracks}
        row["a_diffs"] = [{"track": i + 1, "stored": stored[fn], "arm_a": a}
                          for i, (fn, a) in enumerate(zip(call["filenames"], call["a"]))
                          if fn in stored and stored[fn] != a]
    return legs, row


# --- harness ----------------------------------------------------------------------

def _overlaps(a: Path, b: Path) -> bool:
    a, b = a.resolve(), b.resolve()
    return a == b or a in b.parents or b in a.parents


def _setup(args):
    tree = Path(__file__).resolve().parents[1]
    src = tree / "packages" / "llama" / "src"
    print(f"llama: {llama.__file__}", file=sys.stderr)
    if not Path(llama.__file__).resolve().is_relative_to(src):
        raise Refusal(f"refusing to run: llama imports from {llama.__file__}, not from this tree {tree}")
    config_path = args.config or DEFAULT_ROOT / "config.toml"
    if args.config is not None and not args.config.exists():
        raise Refusal(f"no such config: {args.config}")
    config = load_config(config_path)
    for guarded in (config.root, config.delivery_path):
        if guarded is not None and _overlaps(args.out, guarded):
            raise Refusal(f"refusing --out {args.out}: it overlaps {guarded}")
    args.out.mkdir(parents=True, exist_ok=True)
    rec = Recorder(gather.restore_segues)
    gather.restore_segues = rec      # compute_gather calls it by module-global name
    return config, rec


def _error(slug, err) -> dict:
    return {"slug": slug, "error": f"{type(err).__name__}: {err}"[:300]}


def cmd_spot(args) -> int:
    config, rec = _setup(args)
    providers = None
    if args.live:
        from llama.pipeline import make_providers
        p = make_providers(config)
        providers = (p["extract_setlist"], p["align_structure"])
    ia, slfm = CacheOnlyIA(config.root / "cache"), setlistfm_client(config)
    rows, previous = [], logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        for slug in args.slugs:
            if slug in (".", "..") or "/" in slug:
                rows.append(_error(slug, ValueError("invalid slug")))
                continue
            ws = ShowWorkspace(config.root / "shows" / slug)
            try:
                stored = json.loads(ws.show.read_text())
                stored_align = (stored.get("structure") or {}).get("alignment")
                if stored_align != "llm":
                    rows.append(_error(slug, f"stored alignment is {stored_align!r}, not llm"))
                    continue
                from llama.models import Show
                stub = StubAligner(Show.model_validate(stored).tracks)
                legs, row = replay_one(ws, config=config, ia=ia, slfm=slfm,
                                       scratch=args.out / "scratch" / slug, rec=rec,
                                       providers=providers or (None, stub))
                if row["alignment"] != "llm":
                    row["error"] = f"replay alignment is {row['alignment']!r}, not llm"
                if row.get("a_diffs"):
                    row["error"] = (row.get("error", "") + " arm A differs from stored segues").strip()
                rows.append(row)
            except Exception as err:
                rows.append(_error(slug, err))
    finally:
        logging.disable(previous)
        shutil.rmtree(args.out / "scratch", ignore_errors=True)
    (args.out / "spot.json").write_text(json.dumps(rows, indent=2) + "\n")
    lines = []
    for r in rows:
        lines.append(f"{r['slug']}: " + (f"ERROR {r['error']}" if "error" in r and not r.get("called")
                     else f"{len(r['adds'])} adds, {len(r['skips'])} donor-said-no skips"))
        if r.get("error") and r.get("called"):
            lines.append(f"  ERROR {r['error']}")
        for a in r.get("adds", []):
            lines.append(f"  ADD  {a['track']:>3} {a['title']!r} ({a['evidence']}) info={a['info']!r}")
        for a in r.get("skips", []):
            lines.append(f"  SKIP {a['track']:>3} {a['title']!r} info={a['info']!r}")
        for d in r.get("a_diffs", []):
            lines.append(f"  A-vs-stored differs: track {d['track']} stored={d['stored']} A={d['arm_a']}")
    (args.out / "spot.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


def cmd_library(args) -> int:
    from llama import station_mark
    config, rec = _setup(args)
    root = config.root
    delivered = {e.performance_id for e in Ledger(root / "ledger.jsonl").entries()
                 if e.status == "delivered"}
    ia, slfm = CacheOnlyIA(root / "cache"), setlistfm_client(config)
    dirs = sorted(d for d in (root / "shows").iterdir() if d.is_dir())
    rows, errors, scanned, skipped = [], [], 0, 0
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        for d in dirs:
            if args.limit is not None and scanned >= args.limit:
                break
            ws = ShowWorkspace(d)
            try:
                legs, row = replay_one(ws, config=config, ia=ia, slfm=slfm,
                                       scratch=args.out / "scratch" / d.name, rec=rec)
                st = legs.stored.structure
                if legs.gather.needs_llm or (st is not None and st.alignment == "llm"):
                    skipped += 1
                    continue
                scanned += 1
                if legs.stored.performance_id not in delivered:
                    row["state"] = "library-only"
                else:
                    dest = config.delivery_path / d.name if config.delivery_path else None
                    try:
                        row["state"] = ("delivered voiced" if station_mark.destination_voiced(dest)
                                        else "delivered unvoiced")
                    except Exception:
                        row["state"] = "delivered (station unreadable)"
                rows.append(row)
            except Exception as err:
                errors.append(_error(d.name, err))
    finally:
        logging.disable(previous)
        shutil.rmtree(args.out / "scratch", ignore_errors=True)
    adds = [a for r in rows for a in r["adds"]]
    skips = [a for r in rows for a in r["skips"]]
    changed = [r for r in rows if r["adds"]]
    sample_adds = stratified_sample(adds, SAMPLE_N, seed=args.seed, key=lambda r: r["form"])
    sample_skips = stratified_sample(skips, SAMPLE_N, seed=args.seed, key=lambda r: r["form"])
    for s in sample_adds + sample_skips:
        s["description_line"] = description_line(root / "cache", next(
            r["identifier"] for r in rows if r["slug"] == s["slug"]), s["title"])
    out = {"seed": args.seed, "scanned": scanned, "skipped_llm": skipped, "errors": errors,
           "rows": rows, "sample_adds": sample_adds, "sample_skips": sample_skips}
    (args.out / "library.json").write_text(json.dumps(out, indent=2) + "\n")

    def forms(items):
        c = Counter(i["form"] for i in items)
        return ", ".join(f"{f} {c.get(f, 0)}" for f in (*FORMS, "deterministic"))

    print(f"scanned {scanned} shows ({skipped} skipped for an LLM touchpoint, {len(errors)} errors)")
    print(f"shows changed {len(changed)}; segues added {len(adds)}")
    by_state = Counter(r["state"] for r in changed)
    print("changed by state: " + ", ".join(f"{k} {v}" for k, v in sorted(by_state.items())))
    print(f"adds by info form: {forms(adds)}")
    print(f"donor-said-no skips {len(skips)} by info form: {forms(skips)}")
    for title, items in (("ADDS", sample_adds), ("SKIPS", sample_skips)):
        print(f"\nsample {title} ({len(items)}):")
        for s in items:
            print(f"  {s['slug']} track {s['track']} {s['title']!r} info={s['info']!r} "
                  f"| {s['description_line']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--config", type=Path, default=None)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("spot")
    s.add_argument("--slugs", nargs="+", required=True)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--live", action="store_true")
    s.set_defaults(fn=cmd_spot)
    li = sub.add_parser("library")
    li.add_argument("--out", type=Path, required=True)
    li.add_argument("--limit", type=int, default=None)
    li.add_argument("--seed", type=int, default=DEFAULT_SEED)
    li.set_defaults(fn=cmd_library)
    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except Refusal as err:
        print(err, file=sys.stderr)
        return 2
    finally:
        if isinstance(gather.restore_segues, Recorder):    # uninstall the recorder
            gather.restore_segues = gather.restore_segues.real


if __name__ == "__main__":
    sys.exit(main())
