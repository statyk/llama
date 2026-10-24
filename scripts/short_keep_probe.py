#!/usr/bin/env python3
"""Read-only arm reports for the junk short-keep piece (spec
`docs/superpowers/specs/2026-10-23-junk-short-keep-design.md`, 4.3, 6(a)-(e), 8 premise 1).

  arms   --base BASE.json --cand CAND.json --ref-dir R1 --out DIR
         base consistency (the replay base arm against the reference `arm_base.jsonl`),
         reference reproduction (the candidate arm against `arm_r1.jsonl`), the m3 tallies
         with the candidate in place of `arm_r1.jsonl`, the 6(b) added-hold classes with the
         25% rule, 6(d) override checks and 6(e) positional fills. Writes `arms.md` and
         `arms.json`; exit 1 when anything BLOCKS MERGE, 2 on a refusal.
  repro  --pre PRE.json --post POST.json --out DIR
         the post-migration self-check (spec 4.3 steps 7 and 9). Writes `repro.md`; exit 1
         on any difference, a show in one arm only, or a replayable row lacking the fields.

`--ref-dir` holds the reference JSONL arms (one row per show, keyed `slug`; tracks are
`file`/`title`/`src`/`set`/`segue`). Run with the tree's own interpreter. Nothing but
`--out` is written; an `--out` overlapping the library root or the reference dir is refused.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import llama
from llama.config import DEFAULT_ROOT, load_config
from llama.replay import flag_family

EXPECTED_ADDED = {"new unresolved track": 18, "long single-set show": 6, "positional rung lost": 4,
                  "low confidence remains": 3, "jerrybase closer not at a break": 2, "other": 1}
MARGIN = 1.25
POS = {"desc-position", "setlist"}
FIELDS = ("filenames", "titles", "title_sources", "sets", "segues", "breaks")
LOW_CONF = "low-confidence structure alignment"
LONG_SINGLE = "single-set structure for a long show"
CLOSER = "jerrybase set closer"


class Refusal(Exception):
    """Exit 2 with this message: nothing has been written."""


def _overlaps(a: Path, b: Path) -> bool:
    a, b = a.resolve(), b.resolve()
    return a == b or a in b.parents or b in a.parents


def _load_arm(path: Path) -> dict:
    try:
        arm = json.loads(Path(path).expanduser().read_text())
        if not isinstance(arm.get("shows"), dict):
            raise ValueError("no shows")
        return arm["shows"]
    except (OSError, ValueError, AttributeError) as err:
        raise Refusal(f"cannot read arm {path}: {err}")


def _load_ref(path: Path) -> dict:
    try:
        rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
    except (OSError, ValueError) as err:
        raise Refusal(f"cannot read reference arm {path}: {err}")
    out = {r["slug"]: r for r in rows if isinstance(r, dict) and "slug" in r}
    if not out:
        raise Refusal(f"reference arm {path} holds no shows")
    return out


def _unreplayable(r: dict) -> bool:
    return r.get("outcome") == "unreplayable"


def _missing_fields(r: dict) -> list[str]:
    """Fields a replayable row of the new code must carry; empty list when it does."""
    missing = [k for k in FIELDS + ("flags", "outcome") if k not in r]
    if missing:
        return missing
    n = len(r["filenames"])
    return [k for k in ("titles", "title_sources", "sets", "segues") if len(r[k]) != n]


def _bucket(r: dict) -> str:
    s = r.get("state")
    return ("voiced" if r.get("voiced") else "delivered") if s == "delivered" else str(s)


def encore_file(filenames: list[str], sets: list) -> str | None:
    """The filename of the track the encore falls after (None: no encore, or it opens the tape)."""
    for i, label in enumerate(sets):
        if str(label).lower() in ("encore", "e"):
            return filenames[i - 1] if i > 0 else None
    return None


def _base_flags(r: dict) -> list[str]:
    """`replay.Legs.flags` order: gather + vet + carried package flags + brief."""
    carried = [f for f in r.get("stored_flags") or [] if flag_family(f) == "package"]
    return (list(r.get("gather_flags") or []) + list(r.get("vet_flags") or []) + carried
            + list(r.get("brief_flags") or []))


def base_consistency(base: dict, ref: dict) -> list[str]:
    out = []
    for slug in sorted(ref):
        b, a = ref[slug], base.get(slug)
        if a is None:
            out.append(f"{slug}: not in the replay base arm")
            continue
        if _unreplayable(a):
            if b.get("replayed"):
                out.append(f"{slug}: unreplayable in the replay base ({a.get('unreplayable')})")
            continue
        titles = [t["title"] for t in b.get("tracks") or []]
        if a.get("titles") != titles:
            out.append(f"{slug}: titles differ")
        if _base_flags(a) != list(b.get("flags") or []):
            out.append(f"{slug}: flags differ: replay {_base_flags(a)} vs reference {b.get('flags')}")
    out += [f"{s}: in the replay base arm only" for s in sorted(set(base) - set(ref))]
    return out


def reference_reproduction(cand: dict, r1: dict) -> list[str]:
    out = []
    for slug in sorted(r1):
        r, c = r1[slug], cand.get(slug)
        if c is None:
            out.append(f"{slug}: not in the candidate arm")
            continue
        if _unreplayable(c):
            if r.get("replayed"):
                out.append(f"{slug}: unreplayable in the candidate ({c.get('unreplayable')})")
            continue
        tr = r.get("tracks") or []
        for name, mine, theirs in (
                ("filenames", c["filenames"], [t["file"] for t in tr]),
                ("titles", c["titles"], [t["title"] for t in tr]),
                ("title_sources", c["title_sources"], [t["src"] for t in tr]),
                ("sets", c["sets"], [t["set"] for t in tr]),
                ("segues", c["segues"], [t["segue"] for t in tr]),
                ("flags", c["flags"], list(r.get("flags") or []))):
            if list(mine) != list(theirs):
                out.append(f"{slug}: {name} differ")
    out += [f"{s}: in the candidate arm only" for s in sorted(set(cand) - set(r1))]
    return out


def _cand_tracks(c: dict) -> list[dict]:
    return [{"file": f, "title": t, "src": s, "set": st, "segue": g}
            for f, t, s, st, g in zip(c["filenames"], c["titles"], c["title_sources"],
                                      c["sets"], c["segues"])]


def _ov(b: dict) -> dict:
    return b.get("ov") or {}


def _has_ov(b: dict) -> bool:
    o = _ov(b)
    return bool(o.get("titles")) or o.get("set_breaks") is not None or o.get("encore_after") is not None


def override_structure_moved(b: dict, c: dict) -> list[str]:
    """6(d): each base break, and the encore, read as the filename it falls after, must fall after
    the same filename in the candidate."""
    o = _ov(b)
    files = [t["file"] for t in b["tracks"]]
    cf = c["filenames"]
    moved = []
    for k in o.get("set_breaks") or []:
        f = files[k - 1] if 0 < k <= len(files) else None
        if f is None or f not in cf or (cf.index(f) + 1) not in c["breaks"]:
            moved.append(f"break after {f}")
    if o.get("encore_after") is not None:
        k = o["encore_after"]
        f = files[k - 1] if 0 < k <= len(files) else None
        if f is None or encore_file(cf, c["sets"]) != f:
            moved.append(f"encore after {f}")
    return moved


def compare(base: dict, cand: dict) -> dict:
    """m3_cmp.cmp ported: `base` is the reference `arm_base.jsonl`, `cand` the candidate arm."""
    out = Counter(); st = defaultdict(Counter); cls = Counter()
    unrep, ov_title, ov_struct, lost, gained, added, cleared, cleared_rows = [], [], [], [], [], [], [], []
    for s, b in sorted(base.items()):
        a = cand.get(s)
        if a is None or _unreplayable(a):
            if b.get("replayed"):
                unrep.append([s, (a or {}).get("unreplayable")])
            continue
        if not b.get("replayed"):
            continue
        bt = b["tracks"]
        at = _cand_tracks(a)
        bf, af = [t["file"] for t in bt], a["filenames"]
        bo = {t["file"]: t["title"] for t in bt if t["src"] == "override"}
        ao = {t["file"]: t["title"] for t in at if t["src"] == "override"}
        if bo != ao:
            ov_title.append(s)
        if _has_ov(b):
            mv = override_structure_moved(b, a)
            if mv:
                ov_struct.append([s, mv])
        bflags, aflags = list(b.get("flags") or []), list(a["flags"])
        if bf == af and [t["title"] for t in bt] == a["titles"] and bflags == aflags:
            out["unchanged"] += 1
            continue
        out["changed"] += 1
        baseset = set(bf)
        new = [f for f in af if f not in baseset]
        out["files added"] += len(new)
        by_file = {t["file"]: t for t in bt}
        aset = {t["file"]: t for t in at}
        lp = [t for t in bt if t["src"] in POS and t["file"] in aset
              and aset[t["file"]]["src"] not in POS and aset[t["file"]]["title"] != t["title"]]
        if lp:
            lost.append([s, len(lp)])
        gp = [t for t in at if t["src"] in POS and by_file.get(t["file"], {}).get("title") != t["title"]]
        if gp:
            gained.append([s, len(gp)])
        k = ("cleared" if bflags and not aflags else "added" if aflags and not bflags
             else "flags-changed" if bflags != aflags else "same")
        out[k] += 1
        st[k][_bucket(b)] += 1
        if k == "added":
            nf = [f for f in aflags if f not in bflags]
            unres = any(t["src"] == "unresolved" and t["file"] in set(new) for t in at)
            if s in {x for x in base if _has_ov(base[x])} and bo != ao:
                c = "override shift"
            elif lp:
                c = "positional rung lost"
            elif unres:
                c = "new unresolved track"
            elif nf and all(f.startswith(LOW_CONF) for f in nf):
                c = "low confidence remains"
            elif any(f.startswith(LONG_SINGLE) for f in nf):
                c = "long single-set show"
            elif any(f.startswith(CLOSER) for f in nf):
                c = "jerrybase closer not at a break"
            else:
                c = "other"
            cls[c] += 1
            added.append([s, _bucket(b), c, aflags[:4]])
        if k == "cleared":
            cleared.append([s, _bucket(b), bflags[:3]])
    blocks = []
    for c, n in sorted(cls.items()):
        exp = EXPECTED_ADDED.get(c, 0)
        if c not in EXPECTED_ADDED or n > MARGIN * exp:
            blocks.append(f"BLOCKS MERGE: {c} {n} (expected {exp})")
    return {"counts": dict(out), "cleared_by_state": dict(st["cleared"]),
            "added_by_state": dict(st["added"]), "added_classes": dict(cls),
            "unreplayable": unrep, "override_title_moved": ov_title,
            "override_structure_moved": ov_struct, "positional_lost": lost,
            "positional_gained": gained, "added": sorted(added), "cleared": sorted(cleared),
            "blocks": blocks}


def _guard_out(out: Path, config: Path | None, *others: tuple[str, Path]) -> Path:
    """Refuse an `--out` overlapping the library root (read as `replay_holds.run` does: the
    given config, else the default `config.toml`) or any other read-only input."""
    out = out.expanduser()
    if config is not None and not config.exists():
        raise Refusal(f"no such config: {config}")
    root = load_config(config or DEFAULT_ROOT / "config.toml").root.expanduser()
    for what, p in (("library root", root), *others):
        if _overlaps(out, p.expanduser()):
            raise Refusal(f"refusing --out {out}: it overlaps the {what} {p}")
    return out


def _lines(title: str, rows: list[str]) -> list[str]:
    return [f"## {title} ({len(rows)})"] + (["  " + r for r in rows] or ["  (none)"]) + [""]


def arms(args) -> int:
    ref_dir = args.ref_dir.expanduser()
    out = _guard_out(args.out, args.config, ("reference dir", ref_dir))
    ref_base, ref_r1 = _load_ref(ref_dir / "arm_base.jsonl"), _load_ref(ref_dir / "arm_r1.jsonl")
    base, cand = _load_arm(args.base), _load_arm(args.cand)
    for name, arm in (("base", base), ("candidate", cand)):
        if not set(arm) & set(ref_base):
            raise Refusal(f"the {name} arm shares no show with the reference")
    bad = [f"{s}: {', '.join(m)}" for s, r in sorted(cand.items())
           if not _unreplayable(r) and (m := _missing_fields(r))]
    if bad:
        raise Refusal("candidate rows lack the piece-4 fields (an arm from older code?): "
                      + "; ".join(bad[:5]))
    consistency = base_consistency(base, ref_base)
    repro = reference_reproduction(cand, ref_r1)
    tally = compare(ref_base, cand)
    result = {"base_consistency": consistency, "reference_reproduction": repro, **tally}
    out.mkdir(parents=True, exist_ok=True)
    (out / "arms.json").write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    md = [f"# short-keep arm report", "", f"llama: {llama.__file__}", ""]
    md += _lines("BLOCKS MERGE", tally["blocks"])
    md += _lines("base consistency (the library moved since the reference ran)", consistency)
    md += _lines("reference reproduction differences", repro)
    md += ["## tallies", f"  {tally['counts']}",
           f"  cleared by state {tally['cleared_by_state']} | added by state {tally['added_by_state']}",
           f"  added classes {tally['added_classes']} (expected {EXPECTED_ADDED})", ""]
    md += _lines("unreplayable", [f"{s}: {w}" for s, w in tally["unreplayable"]])
    md += _lines("override tracks on a different file (6(d), expected 0)", tally["override_title_moved"])
    md += _lines("override-path structures moved (6(d), expected 0)",
                 [f"{s}: {m}" for s, m in tally["override_structure_moved"]])
    md += _lines("positional fills lost (6(e))", [f"{s}: {n}" for s, n in tally["positional_lost"]])
    md += _lines("positional fills gained (6(e))", [f"{s}: {n}" for s, n in tally["positional_gained"]])
    md += _lines("added holds", [f"{s} [{b}] {c}: {f}" for s, b, c, f in tally["added"]])
    md += _lines("cleared holds (for the operator)", [f"{s} [{b}] {f}" for s, b, f in tally["cleared"]])
    (out / "arms.md").write_text("\n".join(md) + "\n")
    print("\n".join(md[:3] + tally["blocks"]) if tally["blocks"] else f"arms: {tally['counts']}")
    return 1 if tally["blocks"] else 0


def _row_key(r: dict) -> dict:
    return {"tracks": list(zip(r["filenames"], r["titles"], r["title_sources"], r["sets"],
                               r["segues"])),
            "outcome": r["outcome"], "breaks": list(r["breaks"]),
            "encore": encore_file(r["filenames"], r["sets"])}


def repro(args) -> int:
    out = _guard_out(args.out, args.config, ("pre arm", args.pre), ("post arm", args.post))
    pre, post = _load_arm(args.pre), _load_arm(args.post)
    diffs, equal_unrep, total_equal = [], [], 0
    for slug in sorted(set(pre) | set(post)):
        a, b = pre.get(slug), post.get(slug)
        if a is None or b is None:
            diffs.append(f"{slug}: present in the {'post' if a is None else 'pre'} arm only")
            continue
        ua, ub = _unreplayable(a), _unreplayable(b)
        if ua or ub:
            if ua and ub and a.get("unreplayable") == b.get("unreplayable"):
                equal_unrep.append(f"{slug}: {a.get('unreplayable')}")
            else:
                diffs.append(f"{slug}: unreplayable pre={a.get('unreplayable')!r} "
                             f"post={b.get('unreplayable')!r} (outcome {a.get('outcome')} -> "
                             f"{b.get('outcome')})")
            continue
        lacking = [f"{side} lacks {m}" for side, r in (("pre", a), ("post", b))
                   if (m := _missing_fields(r))]
        if lacking:
            diffs.append(f"{slug}: " + "; ".join(lacking))
            continue
        ka, kb = _row_key(a), _row_key(b)
        if ka == kb:
            total_equal += 1
            continue
        for k in ("outcome", "breaks", "encore"):
            if ka[k] != kb[k]:
                diffs.append(f"{slug}: {k} {ka[k]!r} -> {kb[k]!r}")
        if ka["tracks"] != kb["tracks"]:
            ta, tb = ka["tracks"], kb["tracks"]
            if len(ta) != len(tb):
                diffs.append(f"{slug}: track count {len(ta)} -> {len(tb)}")
            for i, (x, y) in enumerate(zip(ta, tb), 1):
                if x != y:
                    diffs.append(f"{slug}: track {i} {x!r} -> {y!r}")
    out.mkdir(parents=True, exist_ok=True)
    md = ["# short-keep post-migration self-check", "", f"llama: {llama.__file__}",
          f"equal replayable shows: {total_equal}", ""]
    md += _lines("differences", diffs)
    md += _lines("unreplayable in both arms with an equal reason (counted equal)", equal_unrep)
    (out / "repro.md").write_text("\n".join(md) + "\n")
    print(f"repro: {total_equal} equal, {len(equal_unrep)} equal-unreplayable, {len(diffs)} difference(s)")
    return 1 if diffs else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("arms")
    a.add_argument("--base", type=Path, required=True)
    a.add_argument("--cand", type=Path, required=True)
    a.add_argument("--ref-dir", type=Path, required=True)
    a.add_argument("--config", type=Path)
    a.add_argument("--out", type=Path, required=True)
    r = sub.add_parser("repro")
    r.add_argument("--pre", type=Path, required=True)
    r.add_argument("--post", type=Path, required=True)
    r.add_argument("--config", type=Path)
    r.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        return arms(args) if args.cmd == "arms" else repro(args)
    except Refusal as err:
        print(f"refusing: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
