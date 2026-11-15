"""The junk-drop audio check's labelled pre-release gate (spec
`docs/superpowers/specs/2026-11-14-junk-drop-audio-check-design.md`, "Packaging":
Reproduction and Pass bar; audio-check plan Task 11).

    python scripts/audio_check_labelled_gate.py --binary dist/llama [--share DIR] [--jobs N]

Runs a llama binary's hidden `_audio-check FILE` over the 145 labelled tracks of the spike
evidence (`docs/superpowers/2026-11-14-audio-check-evidence/`), read READ-ONLY from the
station share (`<share>/<slug>/audio/<file>`, default `/Volumes/media/lma-radio/delivered`).
The set is assembled from the three sample files (`sample.json`, `sample2.json`,
`sample3.json`; 142 distinct station files) plus the 3 `Silence` rows of `population2.tsv`
that no round sampled; the script refuses (exit 2) unless it assembles exactly 145.

Only the binary's STDOUT `verdict=<music|junk> run=<int> frac=<f>` line with exit 0 counts
as a result; anything else (exit 2 with `unchecked: <reason>` on stderr) is `unchecked`.

Groups and what blocks (exit 1):
- drops (rounds 1-3, 118 files): compared with `population2.tsv` by (slug, station_file),
  never by title. A caught labelled song (`music_chosen` True, `operator_label` song) that
  comes out `junk` or `unchecked` blocks, except the at-bar exemption
  (`audio_check_population.at_bar`: smashingpumpkins-2008-08-12,
  newridersofthepurplesage-1974-11-29, or a tsv `run_055` within one window of 120 s or
  `frac_055` within 0.05 of 0.60). `Silence` rows never block (no longer junk titles; the
  population gate skips them too). Every other flip is listed.
- control songs (12): must read `music`; `junk` or `unchecked` blocks unless the binary's
  own run is within one window of 120 s or its frac within 0.05 of 0.60 (listed).
- Space/Drums controls (12): listed, never blocking.
- the 3 extra Gomez `Silence` files: listed, never blocking.
A labelled file missing from the share blocks (the gate did not see all 145).
Exit 0 when nothing blocks. Reads only; writes nothing.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audio_check_population import (  # noqa: E402
    FRAC_BAR, FRAC_MARGIN, RUN_BAR_SEC, SKIP_TITLES, SONG_LABEL, WINDOW_SEC, at_bar)

EVIDENCE = (Path(__file__).resolve().parent.parent / "docs" / "superpowers"
            / "2026-11-14-audio-check-evidence")
DEFAULT_SHARE = Path("/Volumes/media/lma-radio/delivered")
EXPECTED_TRACKS = 145
SAMPLES = ("sample.json", "sample2.json", "sample3.json")
GROUP_DROPS = "drops"
GROUP_SONGS = "control songs"
GROUP_SPACE = "space/drums controls"
GROUP_GOMEZ = "extra gomez silence"
GROUPS = (GROUP_DROPS, GROUP_SONGS, GROUP_SPACE, GROUP_GOMEZ)
_SAMPLE_CONTROL_GROUPS = {"song": GROUP_SONGS, "space": GROUP_SPACE}
_VERDICT = re.compile(r"verdict=(music|junk) run=(\d+) frac=([0-9.]+)")


@dataclass
class Track:
    group: str
    slug: str
    station_file: str
    title: str
    pop: dict | None = None          # the population2.tsv row (drops and gomez)
    result: dict = field(default_factory=dict)  # verdict, run, frac, error

    @property
    def key(self) -> tuple[str, str]:
        return (self.slug, self.station_file)


def assemble(evidence: Path = EVIDENCE) -> list[Track]:
    with open(evidence / "population2.tsv", newline="") as f:
        pop = {(r["slug"], r["station_file"]): r for r in csv.DictReader(f, delimiter="\t")}
    tracks: dict[tuple[str, str], Track] = {}
    for name in SAMPLES:
        for item in json.loads((evidence / name).read_text()):
            key = (item["slug"], os.path.basename(item["path"]))
            if key in tracks:
                continue  # one file was labelled twice (round 2)
            group = _SAMPLE_CONTROL_GROUPS.get(item["group"], GROUP_DROPS)
            row = pop.get(key) if group == GROUP_DROPS else None
            if group == GROUP_DROPS and row is None:
                raise ValueError(f"sampled drop {key} has no population2.tsv row")
            tracks[key] = Track(group, key[0], key[1], item.get("title", ""), row)
    for key, row in pop.items():
        if row["title"] in SKIP_TITLES and key not in tracks:
            tracks[key] = Track(GROUP_GOMEZ, key[0], key[1], row["title"], row)
    return sorted(tracks.values(), key=lambda t: (GROUPS.index(t.group), t.key))


def parse(returncode: int, stdout: str, stderr: str) -> dict:
    m = _VERDICT.match(stdout) if returncode == 0 else None
    if m is None:
        err = (stderr.strip().splitlines() or [f"exit {returncode}"])[-1]
        return {"verdict": "unchecked", "run": None, "frac": None, "error": err}
    return {"verdict": m.group(1), "run": int(m.group(2)), "frac": float(m.group(3)),
            "error": None}


def run_one(binary: Path, path: Path) -> dict:
    res = subprocess.run([str(binary), "_audio-check", str(path)], capture_output=True,
                         text=True)
    return parse(res.returncode, res.stdout, res.stderr)


def _now_at_bar(result: dict) -> bool:
    run, frac = result.get("run"), result.get("frac")
    if run is None or frac is None:
        return False
    return abs(run - RUN_BAR_SEC) <= WINDOW_SEC or abs(frac - FRAC_BAR) <= FRAC_MARGIN + 1e-9


def _desc(t: Track) -> str:
    r = t.result
    now = (f"now {r['verdict']} run {r['run']} frac {r['frac']:.2f}" if r["verdict"] != "unchecked"
           else f"now unchecked ({r['error']})")
    if t.pop is not None:
        exp = "music" if t.pop["music_chosen"] == "True" else "junk"
        return (f"{t.slug} {t.station_file}: spike {exp} run {t.pop['run_055']} frac "
                f"{t.pop['frac_055']}; {now}; label {t.pop['operator_label'] or '-'}")
    return f"{t.slug} {t.station_file}: {now}"


def evaluate(tracks: list[Track]) -> dict:
    """Per group: counts, flips/listed lines; and the blockers."""
    out = {g: {"n": 0, "music": 0, "junk": 0, "unchecked": 0, "flips": [], "listed": []}
           for g in GROUPS}
    blockers: list[str] = []
    for t in tracks:
        g, r = out[t.group], t.result
        g["n"] += 1
        g[r["verdict"]] += 1
        if t.group == GROUP_DROPS:
            exp = "music" if t.pop["music_chosen"] == "True" else "junk"
            if r["verdict"] == exp:
                continue
            line = _desc(t)
            g["flips"].append(line)
            caught_song = exp == "music" and t.pop["operator_label"] == SONG_LABEL
            if caught_song and t.title not in SKIP_TITLES:
                if r["verdict"] == "junk" and at_bar(t.pop):
                    g["listed"].append(f"at-bar (not blocking): {line}")
                else:
                    blockers.append(f"caught labelled song not music: {line}")
        elif t.group == GROUP_SONGS:
            if r["verdict"] == "music":
                continue
            line = _desc(t)
            g["flips"].append(line)
            if r["verdict"] == "junk" and _now_at_bar(r):
                g["listed"].append(f"at-bar (not blocking): {line}")
            else:
                blockers.append(f"control song not music: {line}")
        else:
            g["listed"].append(_desc(t))
    return {"groups": out, "blockers": blockers}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--binary", type=Path, required=True)
    ap.add_argument("--share", type=Path, default=DEFAULT_SHARE)
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args(argv)
    try:
        tracks = assemble()
    except (OSError, ValueError, KeyError) as exc:
        print(f"audio_check_labelled_gate: cannot read the evidence: {exc}", file=sys.stderr)
        return 2
    if len(tracks) != EXPECTED_TRACKS:
        print(f"audio_check_labelled_gate: assembled {len(tracks)} labelled tracks, expected "
              f"{EXPECTED_TRACKS}", file=sys.stderr)
        return 2
    if not args.binary.is_file():
        print(f"audio_check_labelled_gate: no binary at {args.binary}", file=sys.stderr)
        return 2
    paths = {t.key: args.share / t.slug / "audio" / t.station_file for t in tracks}
    missing = [t for t in tracks if not paths[t.key].is_file()]
    present = [t for t in tracks if paths[t.key].is_file()]
    print(f"labelled tracks: {len(tracks)}; found on the share: {len(present)}; "
          f"missing: {len(missing)}")
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        for t, res in zip(present, pool.map(lambda t: run_one(args.binary, paths[t.key]),
                                            present)):
            t.result = res
    for t in missing:
        t.result = {"verdict": "unchecked", "run": None, "frac": None,
                    "error": "missing on the share"}
    for t in tracks:
        r = t.result
        print(f"  [{t.group}] {t.slug} {t.station_file}: {r['verdict']} "
              f"run={r['run']} frac={r['frac']}" + (f" ({r['error']})" if r["error"] else ""))
    res = evaluate(tracks)
    blockers = [f"missing on the share: {paths[t.key]}" for t in missing] + res["blockers"]
    for g in GROUPS:
        s = res["groups"][g]
        print(f"{g}: {s['n']} tracks; music {s['music']}, junk {s['junk']}, "
              f"unchecked {s['unchecked']}; flips {len(s['flips'])}")
        if g in (GROUP_DROPS, GROUP_SONGS):
            for line in s["flips"]:
                print(f"  flip: {line}")
        for line in s["listed"]:
            print(f"  {line}")
    if blockers:
        print("FAIL:")
        for line in blockers:
            print(f"  {line}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
