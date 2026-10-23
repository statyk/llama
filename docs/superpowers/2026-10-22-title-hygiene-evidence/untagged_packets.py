#!/usr/bin/env python3
"""Piece 3: packets for every effectively-untagged show (< 2 independent
song-like titles, title overrides stripped) whose selected description gives
a count-matched list. Adds the tagged sibling recordings (selection.json
scores, title_fraction >= 0.9) with per-file titles and durations from the
cached metadata, so a checker can see where a positional fill shifts.
Read-only on ~/.llama. Run with the repo venv.
"""
import json
from pathlib import Path

__file__ = str(Path.home() / ".llama-harness/piece3/census/census.py")
_src = open(__file__).read().splitlines(keepends=True)
exec("".join(_src[:104] + _src[340:356] + _src[554:699]))

LIB = Path.home() / ".llama/shows"
CACHE = Path.home() / ".llama/cache"
OUT = Path.home() / ".llama-harness/piece3/untagged/packets"
OUT.mkdir(parents=True, exist_ok=True)
pop = json.load(open(Path.home() / ".llama-harness/piece3/untagged_cm.json"))
AUDIO = (".mp3", ".flac", ".shn")


def sib_files(ident):
    p = CACHE / f"md_{ident}.json"
    if not p.exists():
        return None
    files = json.load(open(p)).get("files", [])
    mp3 = [f for f in files if f.get("name", "").lower().endswith(".mp3")]
    pick = mp3 or [f for f in files if f.get("name", "").lower().endswith(AUDIO)]
    return sorted(pick, key=lambda f: f["name"])


def dur(f):
    v = f.get("length")
    try:
        if v and ":" in str(v):
            parts = [float(x) for x in str(v).split(":")]
            s = 0
            for x in parts:
                s = s * 60 + x
            return f"{s:.0f}s"
        return f"{float(v):.0f}s" if v else "?"
    except ValueError:
        return str(v)


summary = []
for slug in pop:
    r = by[slug]
    tr, src = basis(r)
    r["_basis"], r["_basis_src"] = tr, src
    n = len(tr)
    nl = numbered_lines(r.get("description") or "")
    op = r.get("own_parse") or []
    lst, used = (nl, "numbered_lines") if len(nl) == n else (op, "own_parse")
    sel = LIB / slug / "selection.json"
    sibs = []
    if sel.exists():
        sc = json.load(open(sel)).get("scores", {})
        for ident, s in sorted(sc.items(), key=lambda kv: -kv[1].get("score", 0)):
            if ident != r["identifier"] and (s.get("title_fraction") or 0) >= 0.9:
                sibs.append((ident, s))
    md = [head(r, "U", f"untagged, count-matched list ({used}), {len(sibs)} tagged siblings")]
    md.append(f"## Tracks (candidate = entry N of the selected description's `{used}` list, by position)\n")
    md.append(track_table(r, ["positional candidate", "raw tag"],
                          lambda k: [lst[k["n"] - 1] if k["n"] - 1 < len(lst) else "", _raw(r, k["file"])]))
    md.append("\n## Canonical setlist (as gather built it)\n")
    md.append(", ".join(f"[{c['set']}] {c['title']}" for c in (r.get("canonical") or [])) or "(empty)")
    md.append("\n## Tagged sibling recordings of the same performance (other tapers; titles and durations from archive.org metadata)\n")
    if not sibs:
        md.append("(none with title_fraction >= 0.9)")
    for ident, s in sibs[:3]:
        files = sib_files(ident)
        md.append(f"\n### {ident} (https://archive.org/details/{ident}; kept_tracks {s.get('kept_tracks')}, lineage {s.get('lineage')})\n")
        if files is None:
            md.append("(metadata not cached)")
            continue
        md.append("| # | file | dur | title |\n|---|---|---|---|")
        for i, f in enumerate(files, 1):
            md.append(f"| {i} | {f['name']} | {dur(f)} | {(f.get('title') or '').replace('|', '/')} |")
    md.append("\n## Selected item description (verbatim)\n")
    md.append(desc_block(r))
    md.append("\n## Overnight adjudication\n")
    md.append(verdict_block(slug))
    (OUT / f"{slug}.md").write_text("\n".join(md) + "\n")
    summary.append({"slug": slug, "list": used, "tagged_siblings": len(sibs),
                    "canonical_source": r.get("canonical_source"), "n_tracks": n})
json.dump(summary, open(OUT.parent / "index.json", "w"), indent=1)
print(len(summary), "packets;", sum(1 for s in summary if s["tagged_siblings"]), "with a tagged sibling")
