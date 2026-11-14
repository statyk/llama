#!/usr/bin/env python3
"""Measure the junk-title drop (spec 2026-11-13-junk-tag-drop-design) against the
2026-11-13 baseline (`docs/superpowers/2026-11-13-junk-tag-drop-evidence/drops.tsv`).

    python scripts/junk_drop_measure.py compare --base B --cand C --baseline TSV \
        --shows DIR --out OUT

B and C are arm JSONs from `replay_holds.py run` (rows under `shows`, keyed by slug); C is
the candidate arm and carries `junk_drops` per row, B (base code) does not: a missing key
means none. DIR is the library's `shows/` directory, read only (`show.json`,
`overrides.json`). Hold changes are `replay_holds.py compare`'s job, not this script's.

Writes OUT/summary.md, differences.tsv, vocabulary.txt, kept_track_deltas.tsv and
override_keys.tsv. Exit 2: unreadable input, or an `--out` that is, contains or lies inside
the library root (the parent of DIR). Exit 3: a candidate drop outside the operator's
vocabulary (vocabulary.txt non-empty).

Calls made where the brief left room:
- Rows join on slug; a slug in only one arm contributes to no per-file comparison (its drops
  still count in the candidate totals). A baseline row has the show's full pre-drop list, a
  candidate row only its kept tracks, so "kept in both arms" is: the filename is in both
  rows' `filenames` (the candidate list is post-drop, hence a dropped file is never "kept").
- A candidate drop's identity is (slug, filename). Titles are compared after `measure.py`'s
  normalisation (whitespace collapsed, stripped, outer hyphens stripped), not raw.
- `adjacent_to_drop`: the candidate's pre-drop order is rebuilt from its kept list plus its
  `junk_drops` (each inserted after `after_track` kept tracks, drop order within a
  position); True when the track right after this one in that order was dropped.
- A baseline-only drop whose slug is not in the candidate arm is `not-in-arm` (checked first:
  the replay never looked at that show). summary.md ends with a Coverage block (arm sizes,
  intersection, baseline slugs absent from each arm, empty-`filenames` rows per arm, each arm's
  `scope`); kept-track deltas cover only slugs in both arms with non-empty `filenames`.
- A baseline-only drop's candidate "final title" is the candidate row's title for that file
  (it was kept); `arrowed` uses `junk_titles.trailing_arrow` on it.
- `override_keys.tsv` takes only filename (string) entries of `set_breaks` and `encore_after`;
  the kept tracks on each side are the candidate's tracks at `after_track - 1` and `after_track`
  of the drop's own record (empty when none).
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

from llama import junk, junk_titles
from llama.titles import clean_tag_title

# Copied verbatim from docs/superpowers/2026-11-13-junk-tag-drop-evidence/measure.py.
W = r"(?:tuning(?:\s*up)?|tune\s*up|crowd(?:\s+noise)?|silence)"
SP = r"\s*(?:/|&|,|\band\b|\s-\s)\s*"
A = re.compile(rf"^{W}(?:{SP}{W})*$", re.I)
BS = re.compile(rf"^(?:{W}|intro(?:duction)?s?)(?:{SP}(?:{W}|intro(?:duction)?s?))*$", re.I)
BE = re.compile(rf"^(?:{W}|outros?)(?:{SP}(?:{W}|outros?))*$", re.I)

# The operator's vocabulary (Global Constraints), matched per part with re.fullmatch(.., re.I).
VOCAB = (r"tuning(?:\s*up)?|tune\s*up|crowd(?:\s+noise)?|silence",
         r"intro(?:duction)?s?",
         r"outros?")

BASE_ONLY = ("not-in-arm", "operator-include", "arrowed", "needs-llm-row", "title-differs", "not-kept", "other")
CAND_ONLY = ("title-differs", "not-in-show.json", "parts-split", "edge-run", "other")
DIFF_COLS = ["side", "slug", "filename", "title_baseline", "title_cand", "rule", "category"]
DELTA_COLS = ["slug", "filename", "set_base", "set_cand", "title_base", "title_cand",
              "segue_base", "segue_cand", "adjacent_to_drop"]
OVERRIDE_COLS = ["slug", "key", "filename", "set_before", "set_after"]


class Refusal(Exception):
    """Exit 2 with this message."""


def _norm(t) -> str:
    return re.sub(r"\s+", " ", (t or "").strip().strip("-").strip())


def _read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _load_arm(path: Path) -> dict:
    """The arm's rows by slug; `_arm_scope` reads the arm's own `scope` echo."""
    data = _read_json(path)
    if not isinstance(data, dict) or not isinstance(data.get("shows"), dict):
        raise Refusal(f"cannot read arm {path}")
    return data["shows"]


def _arm_scope(path: Path):
    data = _read_json(path)
    return data.get("scope") if isinstance(data, dict) else None


def _load_baseline(path: Path) -> list[dict]:
    try:
        with open(path, newline="") as f:
            rows = list(csv.DictReader(f, delimiter="\t"))
    except OSError as err:
        raise Refusal(f"cannot read baseline {path}: {err}")
    if not rows and not path.read_text().strip():
        raise Refusal(f"empty baseline {path}")
    for need in ("slug", "filename", "title", "rule", "held"):
        if rows and need not in rows[0]:
            raise Refusal(f"baseline {path} has no {need} column")
    return rows


def _inside(out: Path, root: Path) -> bool:
    out, root = out.resolve(), root.resolve()
    return out == root or root in out.parents or out in root.parents


def _is_vocab(part: str) -> bool:
    return any(re.fullmatch(v, part, re.I) for v in VOCAB)


def _drops(row: dict) -> list[dict]:
    d = row.get("junk_drops")
    return [x for x in d if isinstance(x, dict)] if isinstance(d, list) else []


def _title_map(row: dict) -> dict[str, str]:
    return dict(zip(row.get("filenames") or [], row.get("titles") or []))


def _tsv(path: Path, cols: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(cols)
        w.writerows(rows)


def _cand_category(slug: str, d: dict, show_titles: dict[str, str] | None) -> str:
    fn, title = d["filename"], d.get("title") or ""
    if show_titles is not None and fn in show_titles and _norm(show_titles[fn]) != _norm(title):
        return "title-differs"
    if show_titles is None or fn not in show_titles:
        return "not-in-show.json"
    x = _norm(clean_tag_title(title))
    if not (A.match(x) or BS.match(x) or BE.match(x)):
        return "parts-split"
    if d.get("rule") in ("B", "C"):
        return "edge-run"
    return "other"


def _predrop_order(row: dict) -> list[str]:
    kept = list(row.get("filenames") or [])
    drops = _drops(row)
    out: list[str] = []
    for a in range(len(kept) + 1):
        out += [d["filename"] for d in drops if d.get("after_track") == a]
        if a < len(kept):
            out.append(kept[a])
    out += [d["filename"] for d in drops
            if not isinstance(d.get("after_track"), int) or d["after_track"] > len(kept)]
    return out


def compare(args: argparse.Namespace) -> int:
    shows_dir: Path = args.shows
    if not shows_dir.is_dir():
        raise Refusal(f"no such shows directory: {shows_dir}")
    library_root = shows_dir.resolve().parent
    if _inside(args.out, library_root):
        raise Refusal(f"refusing --out {args.out}: it overlaps the library root {library_root}")
    base, cand = _load_arm(args.base), _load_arm(args.cand)
    baseline = _load_baseline(args.baseline)

    base_drops = {(r["slug"], r["filename"]): r for r in baseline}
    cand_drops = {(s, d["filename"]): d for s, row in cand.items() for d in _drops(row)
                  if isinstance(d.get("filename"), str)}

    def show_titles(slug: str) -> dict[str, str] | None:
        sj = _read_json(shows_dir / slug / "show.json")
        if not isinstance(sj, dict) or not isinstance(sj.get("tracks"), list):
            return None
        return {t.get("filename"): t.get("title") for t in sj["tracks"] if isinstance(t, dict)}

    def overrides(slug: str) -> dict:
        ov = _read_json(shows_dir / slug / "overrides.json")
        return ov if isinstance(ov, dict) else {}

    diffs: list[list] = []
    cand_cats: Counter = Counter()
    base_cats: Counter = Counter()
    title_cache: dict[str, dict | None] = {}
    for (slug, fn), d in sorted(cand_drops.items()):
        if (slug, fn) in base_drops:
            continue
        if slug not in title_cache:
            title_cache[slug] = show_titles(slug)
        cat = _cand_category(slug, d, title_cache[slug])
        cand_cats[cat] += 1
        diffs.append(["cand", slug, fn, (title_cache[slug] or {}).get(fn, ""), d.get("title", ""),
                      d.get("rule", ""), cat])
    for (slug, fn), r in sorted(base_drops.items()):
        if (slug, fn) in cand_drops:
            continue
        row = cand.get(slug) or {}
        ctitle = _title_map(row).get(fn)
        btitle = r["title"]
        if slug not in cand:
            cat = "not-in-arm"
        elif fn in (overrides(slug).get("include") or []):
            cat = "operator-include"
        elif ctitle is not None and junk_titles.trailing_arrow(ctitle):
            cat = "arrowed"
        elif row.get("outcome") in ("needs-llm", "unreplayable"):
            cat = "needs-llm-row"
        elif ctitle is not None and _norm(ctitle) != _norm(btitle):
            cat = "title-differs"
        elif ctitle is None:
            cat = "not-kept"
        else:
            cat = "other"
        base_cats[cat] += 1
        diffs.append(["baseline", slug, fn, btitle, ctitle or "", r["rule"], cat])
    args.out.mkdir(parents=True, exist_ok=True)
    _tsv(args.out / "differences.tsv", DIFF_COLS, diffs)

    vocab = []
    for (slug, fn), d in sorted(cand_drops.items()):
        ps = junk.parts(clean_tag_title(d.get("title")))
        bad = [p for p in ps if not _is_vocab(p)]
        if bad:
            vocab.append(f"{slug}\t{fn}\t{d.get('rule')}\t{d.get('title')!r}\tnot in vocabulary: "
                         + ", ".join(repr(p) for p in bad))
    (args.out / "vocabulary.txt").write_text("".join(v + "\n" for v in vocab))

    deltas = []
    empty = {"base": 0, "cand": 0}
    for name, arm in (("base", base), ("cand", cand)):
        empty[name] = sum(1 for r in arm.values() if not r.get("filenames"))
    for slug in sorted(set(base) & set(cand)):
        b, c = base[slug], cand[slug]
        if not b.get("filenames") or not c.get("filenames"):
            continue
        bi = {f: i for i, f in enumerate(b["filenames"])}
        order = _predrop_order(c)
        dropped = {d["filename"] for d in _drops(c)}
        for ci, fn in enumerate(c["filenames"]):
            if fn not in bi:
                continue

            def at(row, key, i):
                v = row.get(key) or []
                return v[i] if i < len(v) else None
            i = bi[fn]
            sb, sc = at(b, "sets", i), at(c, "sets", ci)
            tb, tc = at(b, "titles", i), at(c, "titles", ci)
            gb, gc = at(b, "segues", i), at(c, "segues", ci)
            if (sb, tb, gb) == (sc, tc, gc):
                continue
            p = order.index(fn)
            nxt = order[p + 1] if p + 1 < len(order) else None
            deltas.append([slug, fn, sb, sc, tb, tc, gb, gc, nxt in dropped])
    _tsv(args.out / "kept_track_deltas.tsv", DELTA_COLS, deltas)

    okeys = []
    for slug in sorted({s for s, _ in cand_drops}):
        ov = overrides(slug)
        named = [("set_breaks", f) for f in (ov.get("set_breaks") or []) if isinstance(f, str)]
        if isinstance(ov.get("encore_after"), str):
            named.append(("encore_after", ov["encore_after"]))
        sets = cand[slug].get("sets") or []
        for key, f in named:
            d = cand_drops.get((slug, f))
            if d is None:
                continue
            a = d.get("after_track")
            before = sets[a - 1] if isinstance(a, int) and 1 <= a <= len(sets) else ""
            after = sets[a] if isinstance(a, int) and 0 <= a < len(sets) else ""
            okeys.append([slug, key, f, before, after])
    _tsv(args.out / "override_keys.tsv", OVERRIDE_COLS, okeys)

    (args.out / "summary.md").write_text(_summary(base_drops, cand_drops, cand_cats, base_cats,
                                                  len(deltas), len(okeys), len(vocab),
                                                  _coverage(base, cand, base_drops, empty, args)))
    print(f"wrote {args.out}: {len(diffs)} difference(s), {len(deltas)} kept-track delta(s), "
          f"{len(okeys)} override key(s), {len(vocab)} vocabulary violation(s)", file=sys.stderr)
    return 3 if vocab else 0


def _coverage(base, cand, base_drops, empty, args) -> list[str]:
    both = set(base) & set(cand)
    bslugs = {s for s, _ in base_drops}
    out = ["## Coverage", "",
           f"- base arm shows: {len(base)}" + (f" (scope {_arm_scope(args.base)})" if _arm_scope(args.base) else ""),
           f"- candidate arm shows: {len(cand)}" + (f" (scope {_arm_scope(args.cand)})" if _arm_scope(args.cand) else ""),
           f"- in both arms: {len(both)}",
           f"- baseline slugs absent from the candidate arm: {len(bslugs - set(cand))}",
           f"- baseline slugs absent from the base arm: {len(bslugs - set(base))}",
           f"- rows with empty filenames (skipped by kept-track deltas), base: {empty['base']}",
           f"- rows with empty filenames (skipped by kept-track deltas), candidate: {empty['cand']}", ""]
    return out


def _summary(base_drops, cand_drops, cand_cats, base_cats, n_deltas, n_okeys, n_vocab,
             coverage) -> str:
    b_rows = [(s, r["rule"]) for (s, _), r in base_drops.items()]
    c_rows = [(s, d.get("rule")) for (s, _), d in cand_drops.items()]
    b_held = [s for (s, _), r in base_drops.items() if str(r["held"]).lower() == "true"]
    c_held = [s for (s, _), d in cand_drops.items() if d.get("held")]
    out = ["# Junk-title drop: candidate vs 2026-11-13 baseline", "",
           "| | baseline | candidate |", "|---|---|---|",
           f"| drop rows | {len(b_rows)} | {len(c_rows)} |",
           f"| shows with a drop | {len({s for s, _ in b_rows})} | {len({s for s, _ in c_rows})} |"]
    for rule in ("A", "B", "C"):
        out.append(f"| rule {rule} rows | {sum(1 for _, r in b_rows if r == rule)} | "
                   f"{sum(1 for _, r in c_rows if r == rule)} |")
        out.append(f"| rule {rule} shows | {len({s for s, r in b_rows if r == rule})} | "
                   f"{len({s for s, r in c_rows if r == rule})} |")
    out += [f"| held rows | {len(b_held)} | {len(c_held)} |",
            f"| held shows | {len(set(b_held))} | {len(set(c_held))} |", "",
            "## Expected-delta reconciliation", "",
            f"Candidate-only drops (in the candidate, not the baseline): {sum(cand_cats.values())}", ""]
    out += [f"- {c}: {cand_cats.get(c, 0)}" for c in CAND_ONLY]
    out += ["", f"Baseline-only drops (in the baseline, not the candidate): {sum(base_cats.values())}", ""]
    out += [f"- {c}: {base_cats.get(c, 0)}" for c in BASE_ONLY]
    out += ["", f"Kept-track deltas: {n_deltas} (kept_track_deltas.tsv)",
            f"Override keys naming a dropped file: {n_okeys} (override_keys.tsv)",
            f"Vocabulary violations: {n_vocab} (vocabulary.txt; exit 3 when non-zero)", "",
            *coverage]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="junk_drop_measure.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compare", help="compare a candidate replay arm to the baseline")
    c.add_argument("--base", type=Path, required=True)
    c.add_argument("--cand", type=Path, required=True)
    c.add_argument("--baseline", type=Path, required=True)
    c.add_argument("--shows", type=Path, required=True)
    c.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        return compare(args)
    except Refusal as err:
        print(f"refused: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
