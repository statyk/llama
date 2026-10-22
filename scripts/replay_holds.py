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
import html
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
from llama import jerrybase
from llama.catalog import derive_state
from llama.config import DEFAULT_ROOT, load_config
from llama.ledger import Ledger
from llama.replay import (CacheOnlyIA, ShowReplay, code_identity, config_fingerprint, flag_family,
                          input_digests, replay_show, setlistfm_client, setlistfm_configured)
from llama.models import Briefing, Track
from llama.stages.brief import _ORDINAL_SET, _SET_COUNT_CLAIM, _claim_matches, _guard_prose
from llama.structure import _place_tokens
from llama.workspace import read_model
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


STRIPPED_KEYS = ("set_breaks", "encore_after")
# Copied into a shadow show dir: everything `compute_legs` reads from the show directory
# besides `overrides.json` (rewritten) and the stored side `replay_show` reads.
SHADOW_FILES = ("provenance.json", "show.json", "vetting.json", "briefing.json", "briefing.md")


def _shadow(d: Path, shadow_root: Path) -> tuple[ShowWorkspace, dict]:
    """A scratch copy of show dir `d` whose `overrides.json` has `set_breaks` and
    `encore_after` removed (excludes, includes, titles, narration and the rest kept:
    the adjudicator's targets are in post-exclusion numbering). Built under the run's
    scratch root; `d` is only read. An unparsable overrides file is copied unchanged,
    so the replay records it unreplayable as it would unstripped. Also returns what was
    removed (`{key: value}` for each stripped key that was present; empty if nothing)."""
    stripped: dict = {}
    sd = shadow_root / d.name
    shutil.rmtree(sd, ignore_errors=True)
    sd.mkdir(parents=True)
    for name in SHADOW_FILES:
        if (d / name).is_file():
            shutil.copyfile(d / name, sd / name)
    ov = d / "overrides.json"
    if ov.is_file():
        try:
            data = json.loads(ov.read_text())
        except ValueError:
            shutil.copyfile(ov, sd / "overrides.json")
        else:
            if isinstance(data, dict):
                for k in STRIPPED_KEYS:
                    if k in data:
                        stripped[k] = data.pop(k)
            (sd / "overrides.json").write_text(json.dumps(data, indent=1) + "\n")
    return ShowWorkspace(sd), stripped


def _replay_stripped(d: Path, *, shadow_root: Path, **kw) -> dict:
    """`replay_show` over the shadow of `d`; the row then carries the REAL show's
    state and input digests, so arms stay comparable with an unstripped base."""
    shadow, stripped = _shadow(d, shadow_root)
    r = replay_show(shadow, **kw)
    real = ShowWorkspace(d)
    try:
        r.state = derive_state(real, kw["delivered"])[0]
    except Exception:
        pass
    try:
        r.digests = input_digests(real)
    except Exception:
        pass
    row = r.to_dict()
    row["stripped"] = stripped     # what strip mode removed; absent/empty = nothing
    return row


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
                    kw = dict(config=config, ia=ia, slfm=slfm, scratch=show_scratch,
                              delivered=delivered)
                    rows[d.name] = (_replay_stripped(d, shadow_root=scratch / ".shadow", **kw)
                                    if args.strip_structure_overrides
                                    else replay_show(ShowWorkspace(d), **kw).to_dict())
                finally:
                    shutil.rmtree(show_scratch, ignore_errors=True)
                    shutil.rmtree(scratch / ".shadow" / d.name, ignore_errors=True)
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
        "structure_overrides_stripped": bool(args.strip_structure_overrides),
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
    ("2d", "stripped joined track number:"),
    ("5c.1", "jerrybase set closer "),
    ("4a", "unknown-song flags suppressed by the right-show gate:"),
    ("format sibling tagged", "format sibling tagged"),
)
NONE = "  (none)"
OUTPUT_FILES = ("summary.txt", "drift.txt", "flags.txt", "outcomes.txt", "packaged_exposure.txt",
                "venue_changes.txt", "title_sources.txt", "structure_changed.txt", "hand_check_sample.txt",
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
    if bool(base.get("structure_overrides_stripped")) != bool(cand.get("structure_overrides_stripped")):
        problems.append("structure_overrides_stripped differs")
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


SUPPRESSED_CONTEXT = 60     # characters of context either side of a suppressed match


def _suppressed_claims(root: Path | None) -> tuple[list[str], int]:
    """briefings.txt section (4), Task 14: over every stored briefing in the
    library at `root` (read-only) that has its show.json, under full
    narration, each match of today's set-count/ordinal regexes over the
    guard's own prose (`brief._guard_prose`) that slice 3c no longer counts
    (its span is not among `brief._claim_matches`'). This is the detection
    3c gives up, which "zero newly firing" cannot see (spec slice 3
    acceptance). With no `root` (neither arm records one) it reads nothing
    and reports 0, never the caller's cwd."""
    rows = []
    shows = root / "shows" if root is not None else None
    for bj in sorted(shows.glob("*/briefing.json")) if shows is not None and shows.is_dir() else []:
        if not (bj.parent / "show.json").exists():
            continue
        try:
            b = read_model(bj, Briefing)
        except (OSError, ValueError):
            continue
        if b.narration == "vague":
            continue
        prose = _guard_prose(b)
        kept = {m.span() for ms in _claim_matches(prose) for m in ms}
        for rx in (_SET_COUNT_CLAIM, _ORDINAL_SET):
            for m in rx.finditer(prose):
                if m.span() in kept:
                    continue
                s, e = m.span()
                ctx = prose[max(0, s - SUPPRESSED_CONTEXT):e + SUPPRESSED_CONTEXT]
                rows.append(f"  {bj.parent.name}  {m.group(0)!r}  ...{' '.join(ctx.split())}...")
    return [f"suppressed set-count/ordinal matches: {len(rows)}", *(rows or [NONE]), ""], len(rows)


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


def _shipped(field: str, own: dict, other: dict):
    """An arm's shipped value of venue/city: the diff's `new`, else the stored
    value (null means the replay equals it), which is `old` of whichever arm has a diff."""
    d = own.get(field)
    if d:
        return d.get("new")
    o = other.get(field)
    return o.get("old") if o else None


def _venue_changes(base: dict, cand: dict) -> tuple[list[str], int, int]:
    rows, n, m, skipped = [], 0, 0, 0
    for slug, c in sorted(cand["shows"].items()):
        b = base["shows"][slug]
        if b.get("outcome") == "unreplayable" or c.get("outcome") == "unreplayable":
            skipped += 1
            continue
        bv, cv = _shipped("venue", b, c), _shipped("venue", c, b)
        bc, cc = _shipped("city", b, c), _shipped("city", c, b)
        if bv == cv and bc == cc:
            continue
        n += 1
        rows.append(f"{slug}  [{c.get('state')}]" + ("  DELIVERED" if c.get("state") == "delivered" else ""))
        rows.append(f"  venue: {_j(bv)} -> {_j(cv)}")
        rows.append(f"  city: {_j(bc)} -> {_j(cc)}")
        bf, cf = set(_all_flags(b)), set(_all_flags(c))
        if bf == cf:
            rows.append("  flags: unchanged")
        else:
            m += 1
            rows.append(f"  flags CHANGED: added {_j(sorted(cf - bf))}; removed {_j(sorted(bf - cf))}")
    head = ["shows whose shipped venue or city differs (base -> cand):",
            f"skipped {skipped} unreplayable show(s) (fields absent)"]
    return head + (rows or [NONE]), n, m


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
            inner = v.get("vetting") if isinstance(v, dict) else None
            dates = inner.get("asserted_dates") if isinstance(inner, dict) else None
            if not isinstance(dates, list):
                dates = None
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
    croot = Path(cand["root"]) if cand.get("root") else root
    section("5c.3 second closer candidates", _second_closer_candidates(cand, croot))
    short = _short_track_arm(cand, croot)
    n_short = len({row.split(":", 1)[0] for row in short})
    section(f"5c.1 short-track arm (not adopted): {n_short} show(s)", short)
    return out, n


# The survey's "< 7 min" short-track arm (spec "Slice 5 — 5c" (1)), reported,
# never adopted.
SHORT_TRACK_SEC = 420
_CLOSER_FLAG = re.compile(r"jerrybase set closer '(.*)' is not at a set break")


def _stored_tracks(show: dict) -> list[Track] | None:
    try:
        return [Track.model_validate(t) for t in show.get("tracks") or []]
    except (ValueError, TypeError):
        return None


def _second_closer_candidates(cand: dict, root: Path) -> list[str]:
    """Every show whose stored tracks give some jerrybase closer on its date two
    or more candidates, the closer or a candidate starting with a parenthetical:
    a superset of the shows where 5c.3's fold created the second candidate."""
    rows = []
    for slug in sorted(cand["shows"]):
        show = _show_json(root, slug)
        tracks = _stored_tracks(show)
        if not tracks:
            continue
        for event in jerrybase.lookup(show.get("artist") or "", show.get("date") or ""):
            for st in event.sets:
                hits = jerrybase._closer_candidates(tracks, st.closer)
                if len(hits) < 2:
                    continue
                titles = [tracks[i].title for i in hits]
                if jerrybase._LEADING_PAREN.match(st.closer) or \
                        any(jerrybase._LEADING_PAREN.match(t) for t in titles):
                    rows.append(f"  {slug}: closer '{st.closer}': candidates {_j(titles)}")
    return rows


def _short_track_arm(cand: dict, root: Path) -> list[str]:
    """Shows whose cand arm still carries a closer-not-at-a-break flag where the
    closer has one candidate in the stored tracks and every track after it, up
    to the next set change, is under SHORT_TRACK_SEC."""
    rows = []
    for slug, r in sorted(cand["shows"].items()):
        closers = [m.group(1) for f in _all_flags(r) if (m := _CLOSER_FLAG.fullmatch(f))]
        if not closers:
            continue
        tracks = _stored_tracks(_show_json(root, slug))
        if not tracks:
            continue
        for c in closers:
            hits = jerrybase._closer_candidates(tracks, c)
            if len(hits) != 1:
                continue
            tail = []
            for t in tracks[hits[0] + 1:]:
                if t.set != tracks[hits[0]].set:
                    break
                tail.append(t)
            if tail and all(t.duration_sec is not None and t.duration_sec < SHORT_TRACK_SEC
                            for t in tail):
                rows.append(f"  {slug}: closer '{c}': followed by "
                            + ", ".join(f"'{t.title}' {t.duration_sec:.0f}s" for t in tail))
    return rows


def _needs_llm(base: dict, cand: dict) -> tuple[list[str], int, int]:
    def rows(arm, with_repro):
        return [f"  {s}  [{r.get('state')}]  {_j(r.get('needs_llm'))}"
                + (f"  reproduces: {r.get('reproduces')}" if with_repro else "")
                for s, r in sorted(arm["shows"].items()) if r.get("needs_llm")]
    b, c = rows(base, True), rows(cand, False)
    return [*_lines("base:", b), *_lines("cand:", c)], len(b), len(c)


NARRATION_FLAGS = ("single-set structure for a long show", "low-confidence setlist")


def _is_candidate(r: dict, show: dict) -> bool:
    if r.get("state") != "held":
        return False
    flags = _all_flags(r)
    if not flags:
        return False
    st = show.get("structure") if isinstance(show.get("structure"), dict) else {}
    for f in flags:
        if f.startswith("low-confidence setlist"):
            if not (st.get("source") == "none" or st.get("coverage") == 0.0):
                return False
        elif not f.startswith(NARRATION_FLAGS[0]):
            return False
    return True


def _tracks(show: dict) -> list[dict]:
    t = show.get("tracks")
    return [x for x in t if isinstance(x, dict)] if isinstance(t, list) else []


def _narration_row(slug: str, r: dict, root: Path) -> list[str]:
    show = _show_json(root, slug)
    tracks = _tracks(show)
    try:
        minutes = f"{sum(float(t.get('duration_sec') or 0) for t in tracks) / 60:.0f}" if tracks else "?"
    except (TypeError, ValueError):
        minutes = "?"
    srcs = Counter(str(t.get("title_source")) for t in tracks)
    untitled = "yes" if tracks and all(t.get("title_source") == "unresolved" for t in tracks) else "no"
    return [slug, str(show.get("artist") or "?"), str(show.get("date") or "?"),
            str(show.get("venue") or "?"), minutes, "; ".join(_all_flags(r)),
            ", ".join(f"{k}: {v}" for k, v in sorted(srcs.items())) or "?", untitled,
            _excerpt(root, slug)]


NARRATION_HEAD = ("slug", "artist", "date", "venue", "minutes", "flags", "title sources",
                  "untitled", "description")
NARRATION_JS = """
document.querySelectorAll('th').forEach(function (th, i) {
  th.style.cursor = 'pointer';
  th.addEventListener('click', function () {
    var tb = document.querySelector('tbody'), asc = th.dataset.asc !== '1';
    th.dataset.asc = asc ? '1' : '0';
    var rows = Array.prototype.slice.call(tb.rows);
    rows.sort(function (a, b) {
      var x = a.cells[i].textContent, y = b.cells[i].textContent;
      var isNum = function (v) { return /^-?\\d+(\\.\\d+)?$/.test(v.trim()); };
      var ax = isNum(x), ay = isNum(y), c;
      if (ax && ay) c = +x - +y;
      else if (ax !== ay) c = ax ? -1 : 1;
      else c = x.localeCompare(y);
      return asc ? c : -c;
    });
    rows.forEach(function (r) { tb.appendChild(r); });
  });
});
"""


def _narration_page(cand: dict, root: Path) -> str:
    rows = [_narration_row(s, r, root) for s, r in sorted(cand["shows"].items())
            if _is_candidate(r, _show_json(root, s))]
    e = html.escape
    head = "".join(f"<th>{e(h)}</th>" for h in NARRATION_HEAD)
    body = "\n".join("<tr>" + "".join(f"<td>{e(c)}</td>" for c in row) + "</tr>" for row in rows)
    return (f"<!doctype html>\n<html><head><meta charset=\"utf-8\"><title>Narration candidates</title>"
            f"</head><body>\n<h1>Narration candidates ({len(rows)})</h1>\n"
            f"<table border=\"1\" cellpadding=\"4\">\n<thead><tr>{head}</tr></thead>\n"
            f"<tbody>\n{body}\n</tbody></table>\n<script>{NARRATION_JS}</script>\n</body></html>\n")


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
    skipped = bool(getattr(args, "no_repro_gate", False))
    if skipped:
        print(f"baseline reproduces {ok}/{len(denom)} held shows that are not needs-LLM "
              "(gate skipped: --no-repro-gate)", file=sys.stderr)
    elif denom and ok * 100 < 99 * len(denom):
        print(f"baseline reproduces {ok}/{len(denom)} held shows that are not needs-LLM (< 99%)",
              file=sys.stderr)
        return 3

    brief_lines, n_brief = _briefings(base, cand)
    arm_root = cand.get("root") or base.get("root")
    supp_lines, n_supp = _suppressed_claims(Path(arm_root) if arm_root else None)
    _write(out, "briefings.txt", brief_lines + supp_lines)
    flag_lines = _flag_counts(base, cand)
    _write(out, "flags.txt", flag_lines)
    _write(out, "outcomes.txt", _outcomes(base, cand))
    exp, n_exp = _exposure(base, cand)
    _write(out, "packaged_exposure.txt", exp)
    vc, n_vc, m_vc = _venue_changes(base, cand)
    _write(out, "venue_changes.txt", vc)
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
    (out / "narration_candidates.html").write_text(_narration_page(cand, root), encoding="utf-8")

    ordered = sorted(cand["shows"].items(), key=lambda kv: _skey(kv[0]))
    predicted = [_list_row(s, r, r["outcome"]) for s, r in ordered if r.get("outcome") in CLEARING]
    sclist = [_list_row(s, r, r.get("would_be")) for s, r in ordered
              if r.get("outcome") == "structure-changed"]
    pilot = _pilot(predicted)
    stripped = bool(cand.get("structure_overrides_stripped"))
    if not stripped:   # a stripped arm can never feed `reapply --from-list`
        for name, rows in (("predicted_list.json", predicted),
                           ("structure_changed_list.json", sclist), ("pilot_list.json", pilot)):
            (out / name).write_text(json.dumps(_list_doc(cand, rows), indent=1) + "\n")

    n_notes = sum(len(v) for v in _notes_by_group(cand).values())
    held_nl = lambda arm: sum(1 for r in arm["shows"].values()
                              if r.get("state") == "held" and r.get("outcome") == "needs-llm")
    bl_ok = brief_lines[0]
    _write(out, "summary.txt", [
        f"base reproduces {ok}/{len(denom)} (held, not needs-LLM"
        + ("; gate skipped: --no-repro-gate)" if skipped else ")"),
        f"needs-LLM held: base {held_nl(base)}, cand {held_nl(cand)}",
        bl_ok,
        f"drift.txt: {len(drift)} show(s)",
        f"briefings.txt: {n_brief} stored_brief_guard difference(s), "
        f"{n_supp} suppressed set-count/ordinal match(es)",
        f"flags.txt: {len(flag_lines)} famil(ies)",
        f"newly cleared: {len(_newly_cleared(base, cand))}",
        f"packaged_exposure.txt: {n_exp} entr(ies)",
        f"venue_changes.txt: {n_vc} show(s), {m_vc} with a flag change",
        f"title_sources.txt: {len(ts)} row(s)",
        f"structure_changed.txt: {len(sclist)} show(s)",
        f"hand_check_sample.txt: {len(hc_rows(base, cand))} show(s)",
        f"closest_calls.txt: {n_cc} row(s)",
        f"needs_llm.txt: base {nb}, cand {nc_}",
        f"notes.txt: {n_notes} note(s)",
    ] + ([f"apply lists: not written (arms replayed with --strip-structure-overrides)"] if stripped else [
        f"predicted_list.json: {len(predicted)} row(s)",
        f"structure_changed_list.json: {len(sclist)} row(s)",
        f"pilot_list.json: {len(pilot)} row(s)",
    ]))
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
    r.add_argument("--strip-structure-overrides", action="store_true",
                   help="replay each show with overrides.set_breaks/encore_after removed "
                        "(a scratch copy; the arm is stamped and yields no apply lists)")
    r.add_argument("--config", type=Path, default=None,
                   help="config file (default ~/.llama/config.toml, as llama)")
    r.add_argument("--scratch", type=Path, default=None,
                   help="scratch directory (default: a temp dir removed at exit)")
    c = sub.add_parser("compare", help="diff two arms into reports and predicted lists")
    c.add_argument("base", type=Path)
    c.add_argument("cand", type=Path)
    c.add_argument("--out", type=Path, required=True, help="directory for the reports")
    c.add_argument("--no-repro-gate", action="store_true",
                   help="skip the base-reproduction gate (for a -prev arm, which carries earlier slices)")
    args = ap.parse_args(argv)
    try:
        return compare(args) if args.cmd == "compare" else run(args)
    except Refusal as err:
        print(str(err), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
