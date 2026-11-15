"""Decoder parity gate (Task 4, step 6). Run: ./.venv/bin/python <this> > table.md
Reads the station share read-only. Compares classify_file against population2 run_055/frac_055/music_chosen."""
import csv, json, os, sys
from pathlib import Path
from llama.audio_check import classify

E = Path(__file__).parent
SHARE = "/Volumes/media/lma-radio/delivered"
rows = list(csv.DictReader(open(E / "population2.tsv"), delimiter="\t"))
by = {(r["slug"], r["station_file"]): r for r in rows}
sel = {}
for r in rows:
    if r["music_chosen"] == "True" and r["title"] != "Silence":
        sel[(r["slug"], r["station_file"])] = (r, "chosen")
for s in json.load(open(E / "sample3.json")):
    if s["group"] == "near":
        k = (s["slug"], os.path.basename(s["path"]))
        r = by.get(k)
        if r is None:
            print(f"UNPAIRED {k}", file=sys.stderr); continue
        sel.setdefault(k, (r, "near"))
AT_BAR = {"smashingpumpkins-2008-08-12", "newridersofthepurplesage-1974-11-29"}
out, flips, blockers, missing = [], 0, 0, []
print("| slug | file | label | grp | pop run/frac | now run/frac | pop verdict | now verdict | flip | blocker |")
print("|---|---|---|---|---|---|---|---|---|---|")
for (slug, f), (r, grp) in sorted(sel.items()):
    p = Path(SHARE) / slug / "audio" / f
    if not p.exists():
        missing.append(str(p)); continue
    try:
        res = classify.classify_file(p)
    except Exception as e:
        print(f"| {slug} | {f} | ERROR {e} |"); continue
    run0, frac0 = int(r["run_055"]), float(r["frac_055"])
    v0 = "music" if r["music_chosen"] == "True" else "junk"
    flip = v0 != res.verdict
    block = (flip and r["operator_label"] == "song" and v0 == "music" and res.verdict == "junk"
             and slug not in AT_BAR and abs(run0 - 120) > 10 and abs(frac0 - 0.60) > 0.05)
    flips += flip; blockers += block
    print(f"| {slug} | {f} | {r['operator_label']} | {grp} | {run0}/{frac0:.2f} | {res.run_sec}/{res.frac:.2f} | {v0} | {res.verdict} | {'FLIP' if flip else ''} | {'BLOCKER' if block else ''} |")
print(f"\nTracks run: {len(sel)-len(missing)} of {len(sel)}; flips: {flips}; blocking flips: {blockers}; missing on share: {len(missing)}")
for m in missing: print(f"- missing: {m}")
