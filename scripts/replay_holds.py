#!/usr/bin/env python3
"""Offline replay of the library's holds (held-backlog spec, slice 0).

`run` recomputes each show's flags from its stored artifacts and the
archive.org cache, under the code of THIS tree, with cache-only clients and
no LLM, and writes one "arm" JSON (plan "Contracts": Harness arm file).
`compare` diffs two arms: gates (exit 2 / 3), the report files and the
predicted / structure-changed / pilot lists `llama reapply` consumes.

IO discipline is the point: the library is only read. Each show replays into
`<scratch>/<slug>`, removed after the show; the arm JSON is the one file
written. A scratch or `--out` that overlaps the library root is refused, and
so is a run whose imported `llama` is not this tree's (the CLAUDE.md
worktree and copied-tree trap, enforced rather than remembered). Run it with
the tree's own interpreter: `./.venv/bin/python scripts/replay_holds.py run
--out <arm.json>`.
"""
import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import llama
from llama.catalog import derive_state
from llama.config import DEFAULT_ROOT, load_config
from llama.ledger import Ledger
from llama.replay import (CacheOnlyIA, ShowReplay, code_identity, config_fingerprint, flag_family,
                          replay_show, setlistfm_client, setlistfm_configured)
from llama.structure import _place_tokens
from llama.workspace import ShowWorkspace

PROGRESS_EVERY = 100


class Refusal(Exception):
    """Exit 2 with this message: nothing has been read or written yet."""


def _overlaps(a: Path, b: Path) -> bool:
    a, b = a.resolve(), b.resolve()
    return a == b or a in b.parents or b in a.parents


def _check_identity() -> None:
    """`llama.__file__` (read at call time) must resolve under this tree's
    `packages/llama/src` (ruling M2: worktrees nest inside the main repo, so
    the bare repo root would accept a worktree's llama)."""
    tree = Path(__file__).resolve().parents[1]
    src = tree / "packages" / "llama" / "src"
    print(f"llama: {llama.__file__}", file=sys.stderr)
    if not Path(llama.__file__).resolve().is_relative_to(src):
        raise Refusal(f"refusing to run: llama imports from {llama.__file__}, "
                      f"not from this tree {tree}")


def _read_slugs(path: Path) -> list[str]:
    slugs = sorted({line.strip() for line in path.read_text().splitlines() if line.strip()})
    for s in slugs:
        if s in (".", "..") or "/" in s or os.sep in s:
            raise Refusal(f"invalid slug in {path}: {s!r}")
    return slugs


def _targets(shows_dir: Path, scope: str, slugs: list[str],
             delivered: set[str]) -> list[Path]:
    """The show directories to replay. Enumerated by hand, not via
    `catalog.iter_shows` (ruling M3: that reads every show's overrides.json,
    so one malformed file would abort the run). Under `held`, a show whose
    state cannot be derived is kept: `replay_show` records why."""
    if scope == "slugs":
        return [shows_dir / s for s in slugs]
    dirs = sorted(d for d in shows_dir.iterdir() if d.is_dir()) if shows_dir.is_dir() else []
    if scope == "all":
        return dirs
    out = []
    for d in dirs:
        try:
            if derive_state(ShowWorkspace(d), delivered)[0] != "held":
                continue
        except Exception:
            pass
        out.append(d)
    return out


def run(args: argparse.Namespace) -> int:
    _check_identity()
    config_path = args.config or DEFAULT_ROOT / "config.toml"   # as `llama` does
    if args.config is not None and not args.config.exists():
        raise Refusal(f"no such config: {args.config}")
    config = load_config(config_path)
    root = config.root
    if _overlaps(args.out, root):
        raise Refusal(f"refusing --out {args.out}: it overlaps the library root {root}")
    if args.scratch is not None and _overlaps(args.scratch, root):
        raise Refusal(f"refusing scratch {args.scratch}: it overlaps the library root {root}")
    scope = "slugs" if args.slugs else ("all" if args.all else "held")
    slugs = _read_slugs(args.slugs) if args.slugs else []

    delivered = {e.performance_id for e in Ledger(root / "ledger.jsonl").entries()
                 if e.status == "delivered"}
    targets = _targets(root / "shows", scope, slugs, delivered)
    ia = CacheOnlyIA(root / "cache")
    slfm = setlistfm_client(config)

    own_scratch = args.scratch is None
    scratch = Path(tempfile.mkdtemp(prefix="replay-")) if own_scratch else args.scratch
    scratch.mkdir(parents=True, exist_ok=True)
    rows: dict[str, dict] = {}
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        for i, d in enumerate(targets, 1):
            if not d.is_dir():
                rows[d.name] = ShowReplay(slug=d.name, state="missing", outcome="unreplayable",
                                          unreplayable="show directory missing").to_dict()
            else:
                show_scratch = scratch / d.name
                try:
                    rows[d.name] = replay_show(ShowWorkspace(d), config=config, ia=ia,
                                               slfm=slfm, scratch=show_scratch,
                                               delivered=delivered).to_dict()
                finally:
                    shutil.rmtree(show_scratch, ignore_errors=True)
            if i % PROGRESS_EVERY == 0:
                print(f"replayed {i}/{len(targets)}", file=sys.stderr)
    finally:
        logging.disable(previous)
        if own_scratch:
            shutil.rmtree(scratch, ignore_errors=True)

    arm = {
        "sha": code_identity(),
        "config_fingerprint": config_fingerprint(config),
        "setlistfm_configured": setlistfm_configured(config),
        "scope": scope,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "llama_file": llama.__file__,
        "root": str(root),
        "shows": {slug: rows[slug] for slug in sorted(rows)},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_name(f".{args.out.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(arm, indent=1) + "\n")
    os.replace(tmp, args.out)
    counts = Counter(r["outcome"] for r in rows.values())
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    print(f"replayed {len(rows)} show(s): {summary}", file=sys.stderr)
    return 0


# --- compare ---

NON_HELD = ("packaged", "delivered")
CLEARING = ("clears", "needs-brief")
SHIPPED = ("title_changes", "venue", "city", "date", "set_changes", "segue_changes",
           "set_breaks", "alignment")
NOTE_GROUPS = (   # (Contracts id, fixed leading words)
    ("swap", "venue taken from the selected recording:"),
    ("1c", "venue differs from jerrybase:"),
    ("2a", "accepted short tag title:"),
    ("2b", "placeholder tag title:"),
    ("2c", "stripped glued track number:"),
    ("5c.1", "jerrybase set closer "),
    ("5c.2", "set breaks anchored from jerrybase numbered sets"),
    ("4a", "unknown-song flags suppressed by the right-show gate:"),
    ("format sibling tagged", "format sibling tagged"),
)
NONE = "  (none)"
OUTPUT_FILES = ("summary.txt", "drift.txt", "flags.txt", "outcomes.txt", "packaged_exposure.txt",
                "title_sources.txt", "structure_changed.txt", "hand_check_sample.txt",
                "closest_calls.txt", "needs_llm.txt", "notes.txt", "briefings.txt",
                "narration_candidates.html", "predicted_list.json",
                "structure_changed_list.json", "pilot_list.json")


def _load_arm(path: Path) -> dict:
    try:
        arm = json.loads(path.read_text())
        if not isinstance(arm.get("shows"), dict):
            raise ValueError("no shows")
        return arm
    except (OSError, ValueError, AttributeError) as err:
        raise Refusal(f"cannot read arm {path}: {err}")


def _flags(r: dict) -> list[str]:
    return list(r.get("gather_flags") or []) + list(r.get("vet_flags") or [])


def _all_flags(r: dict) -> list[str]:
    return _flags(r) + list(r.get("brief_flags") or [])


def _families(r: dict) -> set[str]:
    return {flag_family(f) for f in _all_flags(r)}


def _skey(slug: str) -> str:
    return hashlib.sha1(slug.encode()).hexdigest()


def _j(v) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def _in_denominator(r: dict) -> bool:
    if r.get("state") == "held":
        return r.get("outcome") != "needs-llm"
    return r.get("state") == "unknown" and r.get("outcome") == "unreplayable"


def _gates(base: dict, cand: dict) -> None:
    problems = []
    if base.get("setlistfm_configured") != cand.get("setlistfm_configured"):
        problems.append("setlistfm_configured differs")
    if base.get("config_fingerprint") != cand.get("config_fingerprint"):
        problems.append("config_fingerprint differs")
    b, c = base["shows"], cand["shows"]
    for slug in sorted(set(b) - set(c)):
        problems.append(f"{slug} is in the base arm only")
    for slug in sorted(set(c) - set(b)):
        problems.append(f"{slug} is in the candidate arm only")
    for slug in sorted(set(b) & set(c)):
        if (b[slug].get("digests") or {}) != (c[slug].get("digests") or {}):
            problems.append(f"{slug}: digests differ")
    if problems:
        raise Refusal("arms differ: " + "; ".join(problems))


def _lines(title: str, rows: list[str]) -> list[str]:
    return [title, *(rows or [NONE]), ""]


def _drift(base: dict) -> list[str]:
    out = []
    for slug, r in sorted(base["shows"].items()):
        if r.get("reproduces") is not True and r.get("outcome") != "needs-llm":
            out.append(f"{slug}  [{r.get('state')}]  stored: {_j(r.get('stored_core_flags'))}"
                       f"  replayed: {_j(_flags(r))}")
    return out


def _briefings(base: dict, cand: dict) -> tuple[list[str], int]:
    b, c = base["shows"], cand["shows"]
    ok, total, bad = 0, 0, []
    for slug, r in sorted(b.items()):
        stored = sorted(f for f in (r.get("stored_flags") or []) if flag_family(f) == "briefing")
        if not stored:
            continue
        total += 1
        if stored == sorted(r.get("stored_brief_guard") or []):
            ok += 1
        else:
            bad.append(slug)
    def firing(arm):
        return [s for s, r in sorted(arm.items())
                if r.get("state") in NON_HELD and r.get("stored_brief_guard")]
    fb, fc = firing(b), firing(c)
    differ = [f"  {s}  [{c[s].get('state')}]  {_j(b[s].get('stored_brief_guard'))} -> "
              f"{_j(c[s].get('stored_brief_guard'))}"
              for s in sorted(b) if s in c and b[s].get("stored_brief_guard") != c[s].get("stored_brief_guard")]
    out = [f"briefing guard reproduces {ok}/{total}", *[f"  not reproduced: {s}" for s in bad], "",
           f"clean briefings firing: base {len(fb)}, cand {len(fc)}",
           *[f"  {s}" for s in fc], "",
           *_lines("stored_brief_guard differs between the arms:", differ)]
    return out, len(differ)


def _flag_counts(base: dict, cand: dict) -> list[str]:
    removed, added = Counter(), Counter()
    for slug, cr in cand["shows"].items():
        br = base["shows"][slug]
        if br.get("state") != "held":
            continue
        bf, cf = _families(br), _families(cr)
        removed.update(bf - cf)
        added.update(cf - bf)
    return [f"{fam}: removed {removed[fam]}, added {added[fam]}"
            for fam in sorted(set(removed) | set(added))]


def _newly_cleared(base: dict, cand: dict) -> list[str]:
    return [s for s, c in sorted(cand["shows"].items())
            if c.get("outcome") in CLEARING and base["shows"][s].get("outcome") not in CLEARING]


def _outcomes(base: dict, cand: dict) -> list[str]:
    held, other = Counter(), Counter()
    for r in cand["shows"].values():
        (held if r.get("state") == "held" else other)[r.get("outcome")] += 1
    nc = _newly_cleared(base, cand)
    return ["held (cand):", *[f"  {k}: {v}" for k, v in sorted(held.items())], "",
            "non-held (cand):", *[f"  {k}: {v}" for k, v in sorted(other.items())], "",
            f"newly cleared: {len(nc)}", *[f"  {s}" for s in nc]]


def _exposure(base: dict, cand: dict) -> tuple[list[str], int]:
    out, n = ["shipped fields that would change (base -> cand):"], 0
    for slug, c in sorted(cand["shows"].items()):
        b = base["shows"][slug]
        if c.get("state") not in NON_HELD:
            continue
        diffs = [f for f in SHIPPED if b.get(f) != c.get(f)]
        if diffs:
            n += 1
            out.append(f"{slug}  [{c.get('state')}]")
            out += [f"  {f}: {_j(b.get(f))} -> {_j(c.get(f))}" for f in diffs]
    if n == 0:
        out.append(NONE)
    out += ["", "newly held (cand raises a flag the base did not):"]
    m = 0
    for slug, c in sorted(cand["shows"].items()):
        b = base["shows"][slug]
        if c.get("state") in NON_HELD and c.get("outcome") == "newly-held" and b.get("outcome") != "newly-held":
            m += 1
            added = [f for f in _all_flags(c) if f not in _all_flags(b)]
            out.append(f"{slug}  [{c.get('state')}]  added: {'; '.join(added)}")
    if m == 0:
        out.append(NONE)
    return out, n + m


def _would_clear(r: dict) -> bool:
    return r.get("outcome") in CLEARING + ("structure-changed",)


def _title_sources(cand: dict) -> list[str]:
    out = []
    for slug, r in sorted(cand["shows"].items()):
        if _would_clear(r):
            for t in r.get("title_changes") or []:
                out.append(f"{slug}  #{t.get('index')}: {t.get('old')!r} ({t.get('old_source')}) -> "
                           f"{t.get('new')!r} ({t.get('new_source')})")
    return out


def _read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _show_json(root: Path, slug: str) -> dict:
    d = _read_json(root / "shows" / slug / "show.json")
    return d if isinstance(d, dict) else {}


def _description(root: Path, slug: str) -> str | None:
    ident = _show_json(root, slug).get("identifier")
    if not ident:
        return None
    d = _read_json(root / "cache" / f"md_{ident}.json")
    try:
        text = d["metadata"]["description"]
    except (TypeError, KeyError):
        return None
    if isinstance(text, list):
        text = " ".join(map(str, text))
    return text if isinstance(text, str) else None


def _excerpt(root: Path, slug: str) -> str:
    d = _description(root, slug)
    return d[:300].replace("\n", " ") if d else "(description unavailable)"


def _structure_changed(cand: dict, root: Path) -> list[str]:
    out = []
    for slug, r in sorted(cand["shows"].items()):
        if r.get("outcome") != "structure-changed":
            continue
        out.append(f"{slug}  would be: {r.get('would_be')}")
        for f in ("set_changes", "segue_changes", "set_breaks", "alignment"):
            out.append(f"  {f}: {_j(r.get(f))}")
        out.append(f"  description: {_excerpt(root, slug)}")
    return out


def _hand_check(base: dict, cand: dict) -> list[str]:
    rows = sorted(_newly_cleared(base, cand), key=_skey)[:20]
    out = []
    for slug in rows:
        b, c = base["shows"][slug], cand["shows"][slug]
        removed = [f for f in _all_flags(b) if f not in _all_flags(c)]
        out.append(f"{slug}  removed: {'; '.join(removed) or '(none)'}")
        out += [f"  note: {n}" for n in c.get("notes") or []]
    return out


def _notes_by_group(cand: dict) -> dict[str, list[tuple[str, str]]]:
    groups: dict[str, list[tuple[str, str]]] = {g: [] for g, _ in NOTE_GROUPS}
    groups["other"] = []
    for slug, r in sorted(cand["shows"].items()):
        for n in r.get("notes") or []:
            for g, prefix in NOTE_GROUPS:
                if n.startswith(prefix):
                    groups[g].append((slug, n))
                    break
            else:
                groups["other"].append((slug, n))
    return groups


def _notes_txt(cand: dict) -> list[str]:
    out = []
    for g, rows in _notes_by_group(cand).items():
        out += _lines(f"== {g} ({len(rows)})", [f"  {s}: {n}" for s, n in rows])
    return out


def _jaccard(x: str, y: str) -> float:
    a, b = set(_place_tokens(x)), set(_place_tokens(y))
    return len(a & b) / len(a | b) if a | b else 1.0


def _closest(base: dict, cand: dict, root: Path) -> tuple[list[str], int]:
    notes = _notes_by_group(cand)
    out, n = [], 0
    def section(title, rows):
        nonlocal out, n
        n += len(rows)
        out += _lines(title, rows)
    rows = []
    for slug, note in notes["1c"]:
        m = re.search(r"archive '(.*)' vs '(.*)' \(same city\)", note)
        if m:
            rows.append((_jaccard(m.group(1), m.group(2)), slug, m.group(1), m.group(2)))
    rows.sort(key=lambda t: (t[0], t[1]))
    section("slice 1 (1c): lowest venue-token overlap (bottom 10)",
            [f"  {s}: overlap {j:.2f}: '{x}' vs '{y}'" for j, s, x, y in rows[:10]])
    rows = []
    for slug, note in notes["2a"]:
        m = re.fullmatch(r"accepted short tag title: track (\d+) '(.*)' corroborated by (.*)", note)
        if not m:
            continue
        srcs = [x for x in m.group(3).split(", ") if x]
        why = []
        if len(srcs) == 1:
            why.append("single source")
        if re.fullmatch(r"'?\d+", m.group(2)):
            why.append("numeric-only title")
        if why:
            rows.append(f"  {slug}: track {m.group(1)} '{m.group(2)}' by {m.group(3)} ({', '.join(why)})")
    section("slice 2a: single-source or numeric-only short titles", rows)
    rows = []
    for slug, note in notes["4a"]:
        m = re.search(r"(\d+)/(\d+) tape tracks asserted \(ratio ([\d.]+)\), (\d+) unclaimed", note)
        if m:
            rows.append((float(m.group(3)), int(m.group(1)), slug, m.group(1), m.group(2), m.group(4)))
    rows.sort(key=lambda t: (t[0], t[1], t[2]))
    section("slice 4a: right-show gate suppressions (ratio asc, asserted asc)",
            [f"  {s}: ratio {r:.2f}, asserted {a}/{t}, unclaimed {u}" for r, _, s, a, t, u in rows])
    rows = []
    for slug, c in sorted(cand["shows"].items()):
        b = base["shows"][slug]
        if "research-date" in _families(b) - _families(c):
            v = _read_json(root / "shows" / slug / "vetting.json")
            dates = v.get("asserted_dates") if isinstance(v, dict) else None
            rows.append(f"  {slug}: asserted_dates {_j(dates) if dates is not None else '(vetting.json unavailable)'}")
    section("slice 4b: lost a research-date flag", rows)
    rows = []
    lost_flag = "setlist evidence shows multiple sets but alignment found none"
    for slug, c in sorted(cand["shows"].items()):
        b = base["shows"][slug]
        if any(f.startswith(lost_flag) for f in _all_flags(b)) and \
                not any(f.startswith(lost_flag) for f in _all_flags(c)):
            tracks = _show_json(root, slug).get("tracks")
            try:
                minutes = f"{sum(float(t.get('duration_sec') or 0) for t in tracks) / 60:.0f} min"
            except (TypeError, ValueError, AttributeError):
                minutes = "? min"
            rows.append(f"  {slug}: {minutes}; {_excerpt(root, slug)}")
    section("slice 5a: lost 'multiple sets but alignment found none'", rows)
    rows = []
    for slug, c in sorted(cand["shows"].items()):
        parts = [f"{f}: {_j(c[f])}" for f in ("alignment", "set_breaks") if c.get(f)]
        if parts:
            rows.append(f"  {slug}: " + "; ".join(parts))
    section("slice 5c: alignment or set_breaks changed", rows)
    return out, n


def _needs_llm(base: dict, cand: dict) -> tuple[list[str], int, int]:
    def rows(arm, with_repro):
        return [f"  {s}  [{r.get('state')}]  {_j(r.get('needs_llm'))}"
                + (f"  reproduces: {r.get('reproduces')}" if with_repro else "")
                for s, r in sorted(arm["shows"].items()) if r.get("needs_llm")]
    b, c = rows(base, True), rows(cand, False)
    return [*_lines("base:", b), *_lines("cand:", c)], len(b), len(c)


def _list_doc(cand: dict, rows: list[dict]) -> dict:
    return {"sha": cand.get("sha"), "config_fingerprint": cand.get("config_fingerprint"),
            "written_at": datetime.now(timezone.utc).isoformat(), "rows": rows}


def _list_row(slug: str, r: dict, outcome: str) -> dict:
    return {"slug": slug, "outcome": outcome, "briefing": r.get("briefing"),
            "digests": r.get("digests")}


def _pilot(rows: list[dict]) -> list[dict]:
    chosen = rows[:10]
    spare = [r for r in rows[10:] if r["briefing"] == "reuse"]
    while sum(r["briefing"] == "reuse" for r in chosen) < 2 and spare:
        idx = max((i for i, r in enumerate(chosen) if r["briefing"] != "reuse"), default=None)
        if idx is None:
            break
        chosen[idx] = spare.pop(0)
    return sorted(chosen, key=lambda r: _skey(r["slug"]))


def _write(out: Path, name: str, lines: list[str]) -> None:
    (out / name).write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")


def compare(args: argparse.Namespace) -> int:
    base, cand = _load_arm(args.base), _load_arm(args.cand)
    _gates(base, cand)
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    for name in OUTPUT_FILES:     # stale outputs of an earlier compare must not outlive this one
        (out / name).unlink(missing_ok=True)
    root = Path(base.get("root") or cand.get("root") or ".")
    drift = _drift(base)
    _write(out, "drift.txt", _lines("base shows whose stored core flags are not reproduced:", drift))
    denom = [r for r in base["shows"].values() if _in_denominator(r)]
    ok = sum(r.get("reproduces") is True for r in denom)
    if denom and ok * 100 < 99 * len(denom):
        print(f"baseline reproduces {ok}/{len(denom)} held shows that are not needs-LLM (< 99%)",
              file=sys.stderr)
        return 3

    brief_lines, n_brief = _briefings(base, cand)
    _write(out, "briefings.txt", brief_lines)
    flag_lines = _flag_counts(base, cand)
    _write(out, "flags.txt", flag_lines)
    _write(out, "outcomes.txt", _outcomes(base, cand))
    exp, n_exp = _exposure(base, cand)
    _write(out, "packaged_exposure.txt", exp)
    ts = _title_sources(cand)
    _write(out, "title_sources.txt", _lines("title changes of would-clear shows:", ts))
    sc = _structure_changed(cand, root)
    _write(out, "structure_changed.txt", _lines("structure-changed shows:", sc))
    hc = _hand_check(base, cand)
    _write(out, "hand_check_sample.txt", _lines("hand-check sample (newly cleared, sha1 order):", hc))
    cc, n_cc = _closest(base, cand, root)
    _write(out, "closest_calls.txt", cc)
    nl, nb, nc_ = _needs_llm(base, cand)
    _write(out, "needs_llm.txt", nl)
    _write(out, "notes.txt", _notes_txt(cand))

    ordered = sorted(cand["shows"].items(), key=lambda kv: _skey(kv[0]))
    predicted = [_list_row(s, r, r["outcome"]) for s, r in ordered if r.get("outcome") in CLEARING]
    sclist = [_list_row(s, r, r.get("would_be")) for s, r in ordered
              if r.get("outcome") == "structure-changed"]
    pilot = _pilot(predicted)
    for name, rows in (("predicted_list.json", predicted), ("structure_changed_list.json", sclist),
                       ("pilot_list.json", pilot)):
        (out / name).write_text(json.dumps(_list_doc(cand, rows), indent=1) + "\n")

    n_notes = sum(len(v) for v in _notes_by_group(cand).values())
    held_nl = lambda arm: sum(1 for r in arm["shows"].values()
                              if r.get("state") == "held" and r.get("outcome") == "needs-llm")
    bl_ok = brief_lines[0]
    _write(out, "summary.txt", [
        f"base reproduces {ok}/{len(denom)} (held, not needs-LLM)",
        f"needs-LLM held: base {held_nl(base)}, cand {held_nl(cand)}",
        bl_ok,
        f"drift.txt: {len(drift)} show(s)",
        f"briefings.txt: {n_brief} stored_brief_guard difference(s)",
        f"flags.txt: {len(flag_lines)} famil(ies)",
        f"newly cleared: {len(_newly_cleared(base, cand))}",
        f"packaged_exposure.txt: {n_exp} entr(ies)",
        f"title_sources.txt: {len(ts)} row(s)",
        f"structure_changed.txt: {len(sclist)} show(s)",
        f"hand_check_sample.txt: {len(hc_rows(base, cand))} show(s)",
        f"closest_calls.txt: {n_cc} row(s)",
        f"needs_llm.txt: base {nb}, cand {nc_}",
        f"notes.txt: {n_notes} note(s)",
        f"predicted_list.json: {len(predicted)} row(s)",
        f"structure_changed_list.json: {len(sclist)} row(s)",
        f"pilot_list.json: {len(pilot)} row(s)",
    ])
    print(f"compare: wrote {out}", file=sys.stderr)
    return 0


def hc_rows(base: dict, cand: dict) -> list[str]:
    return sorted(_newly_cleared(base, cand), key=_skey)[:20]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="replay shows into an arm JSON")
    r.add_argument("--out", type=Path, required=True, help="the arm JSON to write")
    scope = r.add_mutually_exclusive_group()
    scope.add_argument("--held", action="store_true", help="held shows only (the default)")
    scope.add_argument("--all", action="store_true", help="every show in the library")
    scope.add_argument("--slugs", type=Path, help="a file of slugs, one per line")
    r.add_argument("--config", type=Path, default=None,
                   help="config file (default ~/.llama/config.toml, as llama)")
    r.add_argument("--scratch", type=Path, default=None,
                   help="scratch directory (default: a temp dir removed at exit)")
    c = sub.add_parser("compare", help="diff two arms into reports and predicted lists")
    c.add_argument("base", type=Path)
    c.add_argument("cand", type=Path)
    c.add_argument("--out", type=Path, required=True, help="directory for the reports")
    args = ap.parse_args(argv)
    try:
        return compare(args) if args.cmd == "compare" else run(args)
    except Refusal as err:
        print(str(err), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
