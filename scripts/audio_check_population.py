"""The junk-drop audio check's population gate (spec
`docs/superpowers/specs/2026-11-14-junk-drop-audio-check-design.md`, "Replay and the
rollout" and "Packaging" Pass bar).

    python scripts/audio_check_population.py --summary DIR/summary.json [--tsv population2.tsv]

Compares a `llama audio-prepass` summary with the spike's `population2.tsv` on the tsv's
(slug, source_file) rows only (never the rest of the pre-pass superset). Rows titled
`Silence` are skipped (no longer junk titles). Prints rows absent from the summary
separately, every flip, every failed row and the held-show count (shows with a `music`
outcome among the compared rows).

Exit 1 (the rollout stops before the arm) when:
- a caught labelled song (`music_chosen` True, `operator_label` `song`) came out `junk`,
  outside the at-bar exemption (smashingpumpkins-2008-08-12,
  newridersofthepurplesage-1974-11-29, or a track whose tsv `run_055` is within one
  window (10 s) of 120 s or `frac_055` within 0.05 of 0.60);
- a caught labelled song is missing from the summary or `failed`;
- the held count is outside 28 +/- 3.
Exit 2 for an unreadable input. Read-only; stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

DEFAULT_TSV = (Path(__file__).resolve().parent.parent / "docs" / "superpowers"
               / "2026-11-14-audio-check-evidence" / "population2.tsv")
AT_BAR_SLUGS = frozenset({"smashingpumpkins-2008-08-12", "newridersofthepurplesage-1974-11-29"})
RUN_BAR_SEC = 120
WINDOW_SEC = 10
FRAC_BAR = 0.60
FRAC_MARGIN = 0.05
HELD_EXPECTED = 28
HELD_TOLERANCE = 3
SONG_LABEL = "song"
SKIP_TITLES = frozenset({"Silence"})


def _truthy(v: str) -> bool:
    return str(v).strip().lower() == "true"


def at_bar(row: dict) -> bool:
    if row["slug"] in AT_BAR_SLUGS:
        return True
    try:
        run = float(row["run_055"])
        frac = float(row["frac_055"])
    except (KeyError, ValueError):
        return False
    return abs(run - RUN_BAR_SEC) <= WINDOW_SEC or abs(frac - FRAC_BAR) <= FRAC_MARGIN + 1e-9


def read_tsv(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def read_summary(path: Path) -> dict[tuple[str, str], dict]:
    doc = json.loads(Path(path).read_text())
    files = doc.get("files") if isinstance(doc, dict) else None
    if not isinstance(files, list):
        raise ValueError(f"{path} has no `files` list")
    return {(r["slug"], r["source_file"]): r for r in files
            if isinstance(r, dict) and isinstance(r.get("slug"), str)
            and isinstance(r.get("source_file"), str)}


def compare(rows: list[dict], summary: dict[tuple[str, str], dict]) -> dict:
    absent, flips, failed, blockers, listed = [], [], [], [], []
    held: set[str] = set()
    compared = 0
    for row in rows:
        if row.get("title") in SKIP_TITLES:
            continue
        key = (row["slug"], row["source_file"])
        expected = "music" if _truthy(row.get("music_chosen", "")) else "junk"
        caught_song = expected == "music" and row.get("operator_label") == SONG_LABEL
        got = summary.get(key)
        desc = f"{key[0]} {key[1]} '{row.get('title')}'"
        if got is None:
            absent.append(desc)
            if caught_song:
                blockers.append(f"caught song missing from the summary: {desc}")
            continue
        compared += 1
        outcome = got.get("outcome")
        if outcome == "music":
            held.add(row["slug"])
        if outcome == "failed":
            failed.append(f"{desc}: {got.get('error')}")
            if caught_song:
                blockers.append(f"caught song failed: {desc}: {got.get('error')}")
            continue
        if outcome != expected:
            line = (f"{desc}: {expected} -> {outcome} (spike run {row.get('run_055')} frac "
                    f"{row.get('frac_055')}; now run {got.get('run_sec')} frac {got.get('frac')}"
                    f"; label {row.get('operator_label') or '-'})")
            flips.append(line)
            if caught_song and outcome == "junk":
                (listed if at_bar(row) else blockers).append(line)
    n_held = len(held)
    if abs(n_held - HELD_EXPECTED) > HELD_TOLERANCE:
        blockers.append(f"held count {n_held} is outside {HELD_EXPECTED} +/- {HELD_TOLERANCE}")
    return {"compared": compared, "absent": absent, "flips": flips, "failed": failed,
            "at_bar": listed, "blockers": blockers, "held": n_held}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--summary", type=Path, required=True)
    ap.add_argument("--tsv", type=Path, default=DEFAULT_TSV)
    args = ap.parse_args(argv)
    try:
        rows = read_tsv(args.tsv)
        summary = read_summary(args.summary)
    except (OSError, ValueError, KeyError) as exc:
        print(f"audio_check_population: cannot read input: {exc}", file=sys.stderr)
        return 2
    r = compare(rows, summary)
    print(f"compared {r['compared']} population row(s); absent from the summary "
          f"{len(r['absent'])}; failed {len(r['failed'])}; flips {len(r['flips'])}")
    for title, items in (("absent from the summary", r["absent"]), ("failed", r["failed"]),
                         ("flips", r["flips"]),
                         ("at-bar song flips (listed, not blocking)", r["at_bar"])):
        if items:
            print(f"{title}:")
            for line in items:
                print(f"  {line}")
    print(f"held shows: {r['held']} (bar {HELD_EXPECTED} +/- {HELD_TOLERANCE})")
    if r["blockers"]:
        print("FAIL:")
        for line in r["blockers"]:
            print(f"  {line}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
