"""Baseline measurement for the junk-tag drop design (2026-11-13).

Reads ~/.llama/shows/*/show.json FINAL titles (not a gather replay) and the
station manifests, and prints one TSV row per candidate drop. Read-only.
Usage: python3 measure.py [shows_dir] [station_dir] > drops.tsv
"""
import glob, json, os, re, statistics as st, sys

SHOWS = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.llama/shows")
STATION = sys.argv[2] if len(sys.argv) > 2 else "/Volumes/media/lma-radio/delivered"
W = r"(?:tuning(?:\s*up)?|tune\s*up|crowd(?:\s+noise)?|silence)"
SP = r"\s*(?:/|&|,|\band\b|\s-\s)\s*"
A = re.compile(rf"^{W}(?:{SP}{W})*$", re.I)
BS = re.compile(rf"^(?:{W}|intro(?:duction)?s?)(?:{SP}(?:{W}|intro(?:duction)?s?))*$", re.I)
BE = re.compile(rf"^(?:{W}|outros?)(?:{SP}(?:{W}|outros?))*$", re.I)

print("\t".join(["slug", "index", "filename", "title", "rule", "duration_sec", "pct_show",
                 "x_median", "held", "station", "voiced_backend"]))
for p in sorted(glob.glob(os.path.join(SHOWS, "*/show.json"))):
    slug = p.split("/")[-2]
    tr = json.load(open(p)).get("tracks", [])
    if not tr:
        continue
    ds = [t["duration_sec"] or 0 for t in tr]
    med, tot = st.median(ds), sum(ds)
    m = os.path.join(STATION, slug, "manifest.json")
    station = os.path.exists(m)
    dj = json.load(open(m)).get("dj_audio") if station else None
    backend = ((dj or {}).get("tts") or {}).get("backend", "unrecorded") if dj else ""
    for k, t in enumerate(tr):
        x = re.sub(r"\s+", " ", (t["title"] or "").strip().strip("-").strip())
        start = k == 0 or tr[k - 1]["set"] != t["set"]
        rule = ("A" if A.match(x) else "B" if BS.match(x) and start
                else "C" if BE.match(x) and k == len(tr) - 1 else None)
        if not rule:
            continue
        d = ds[k]
        held = sum([d > 360, 100 * d / tot > 5, d / med > 1]) >= 2
        print("\t".join(map(str, [slug, t["index"], t["filename"], x, rule, d,
                                  round(100 * d / tot, 2), round(d / med, 3), held,
                                  station, backend])))
