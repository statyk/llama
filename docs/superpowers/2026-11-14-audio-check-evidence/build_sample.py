import csv, json, random, sys, os
random.seed(7)
ST = "/Volumes/media/lma-radio/delivered"
D = "/Users/shawn/projects/llama/docs/superpowers/2026-11-13-junk-tag-drop-evidence/drops.tsv"
rows = list(csv.DictReader(open(D), delimiter="\t"))
def resolve(slug, dur, title):
    p = f"{ST}/{slug}/manifest.json"
    if not os.path.exists(p): return None
    m = json.load(open(p))
    best = None
    for t in m["tracks"]:
        if abs(t["duration_sec"] - dur) < 3 and t["title"].strip().lower() == title.strip().lower():
            best = t; break
    if not best: return None
    f = f"{ST}/{slug}/audio/{best['filename']}"
    return f if os.path.exists(f) else None
out = []
def add(group, slug, title, dur, f, rule=""):
    out.append(dict(group=group, slug=slug, title=title, dur=round(float(dur)), rule=rule, path=f))
rows_sorted = sorted(rows, key=lambda r: -float(r["duration_sec"]))
for r in rows_sorted[:15]:
    f = resolve(r["slug"], float(r["duration_sec"]), r["title"])
    if f: add("longest15", r["slug"], r["title"], r["duration_sec"], f, r["rule"])
    else: print("MISS", r["slug"], r["title"], file=sys.stderr)
used = {o["path"] for o in out}
def pick(group, cands, n):
    random.shuffle(cands); k = 0
    for r in cands:
        if k >= n: break
        f = resolve(r["slug"], float(r["duration_sec"]), r["title"])
        if f and f not in used:
            used.add(f); add(group, r["slug"], r["title"], r["duration_sec"], f, r["rule"]); k += 1
pick("shortjunk", [r for r in rows if r["rule"]=="A" and float(r["duration_sec"])<120], 12)
pick("midjunk", [r for r in rows if r["rule"]=="A" and 120<=float(r["duration_sec"])<390], 12)
pick("longintro", [r for r in rows if r["rule"]=="B" and float(r["duration_sec"])>180], 12)
# controls and space/drums from station manifests
slugs = sorted(os.listdir(ST)); random.shuffle(slugs)
junk = {"tuning","crowd","crowd noise","intro","outro","silence","banter","applause"}
songs, space = [], []
for s in slugs:
    p = f"{ST}/{s}/manifest.json"
    if not os.path.exists(p): continue
    try: m = json.load(open(p))
    except Exception: continue
    for t in m["tracks"]:
        ti = t["title"].strip().lower(); f = f"{ST}/{s}/audio/{t['filename']}"
        if s.startswith("gratefuldead-") and ti in ("space","drums","drums > space","space >","drums >") and len(space) < 12 and os.path.exists(f):
            space.append((s, t, f))
        elif ti not in junk and not any(j in ti for j in junk) and 150 < t["duration_sec"] < 900 and len(songs) < 12 and random.random() < 0.05 and os.path.exists(f):
            songs.append((s, t, f))
    if len(space) >= 12 and len(songs) >= 12: break
for s,t,f in songs: add("song", s, t["title"], t["duration_sec"], f)
for s,t,f in space: add("space", s, t["title"], t["duration_sec"], f)
json.dump(out, open(sys.argv[1], "w"), indent=1)
from collections import Counter; print(Counter(o["group"] for o in out))
