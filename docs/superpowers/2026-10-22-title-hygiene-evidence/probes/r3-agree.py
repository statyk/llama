"""Read-only probe: would D's agreement check (align of D titles vs a non-chosen canonical,
threshold 0.8) hold any of the 34 hand-checked-right class-U shows? Also check 2 (adjacent dup)."""
import json, re, html as H
from pathlib import Path
from llama.models import Track, ParsedSetlist, SetlistItem
from llama.structure import align, fuzzy_norm_title, fuzzy_title_eq, is_filler
from llama.songs import normalize_song

IDX = json.load(open("/Users/shawn/projects/llama/docs/superpowers/2026-10-22-title-hygiene-evidence/untagged-index.json"))
want = {x["slug"]: x for x in IDX}
RIGHT = set()
for d in "U0 U1 U2 U3".split():
    for l in open(f"/Users/shawn/projects/llama/docs/superpowers/2026-10-22-title-hygiene-evidence/handcheck/{d}/rows.jsonl"):
        if l.strip():
            r = json.loads(l)
            if r["show_verdict"] == "all-right":
                RIGHT.add(r["slug"])
NUMLINE = re.compile(r"^\s*(?:(?:d|cd|disc)\s*\d+\s*)?(?:t(?:rack)?\s*)?(\d{1,3})\s*[.):\-]?\s+(\S.*)$", re.I)
def numbered_lines(desc):
    text = re.sub(r"<br\s*/?>", "\n", desc or "", flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = H.unescape(text)
    out = []
    for ln in text.splitlines():
        m = NUMLINE.match(ln)
        if m and not re.match(r"^\s*\d{1,2}[:/]\d", ln):
            out.append(m.group(2).strip())
    return out
DUR = re.compile(r"\s*[\[(]?\b\d{1,2}:\d{2}(?::\d{2})?\.?\d*[\])]?\s*$|^\s*[\[(]?\d{1,2}:\d{2}(?::\d{2})?[\])]?\s*[-–]?\s*")
def clean(c):
    c = DUR.sub("", c)
    c = re.sub(r"\s*(?:->|>|\*|@|\$|\+)+\s*$", "", c)
    c = re.sub(r"\s*\(\s*\d+\s*\)\s*$", "", c)
    c = re.sub(r"^\s*(?:e|en|enc|encore|filler)\s*:\s*", "", c, flags=re.I)
    return c.strip().strip('"')
rows = {}
for line in open(Path.home()/".llama-harness/piece3/census/dump.jsonl"):
    r = json.loads(line)
    if r.get("slug") in want:
        rows[r["slug"]] = r
print("loaded", len(rows))
held_agree, held_dup = [], []
for slug, x in sorted(want.items()):
    r = rows[slug]
    tr = r["tracks"] if r.get("replayed") else r.get("stored_tracks")
    n = len(tr)
    lst = numbered_lines(r.get("description")) if x["list"] == "numbered_lines" else (r.get("own_parse") or [])
    if len(lst) != n:
        print(f"{slug}: list len {len(lst)} != {n} ??"); continue
    cands = [clean(c) for c in lst]
    tracks = [Track(index=i+1, set="1", title=c or t["file"], filename=t["file"], duration_sec=t.get("dur"),
                    segue=False, title_source="tags") for i, (c, t) in enumerate(zip(cands, tr))]
    canon = r.get("canonical") or []
    src = r.get("canonical_source")
    cov = None
    if canon and src != "chosen":
        ps = ParsedSetlist(items=[SetlistItem(title=c["title"], normalized=normalize_song(c["title"]), set=c.get("set") or "1") for c in canon], confidence="high")
        res = align(tracks, ps)
        cov = res.coverage
    # check 2
    dups = []
    for a, b in zip(tracks, tracks[1:]):
        if is_filler(a.title) or is_filler(b.title): continue
        na, nb = fuzzy_norm_title(a.title), fuzzy_norm_title(b.title)
        if na and (na == nb or fuzzy_title_eq(na, nb)):
            dups.append((a.index, a.title, b.title))
    tag = "RIGHT" if slug in RIGHT else "other"
    flag = ""
    if cov is not None and cov < 0.8:
        flag += " AGREE-DECLINE"; 
        if slug in RIGHT: held_agree.append(slug)
    if dups:
        flag += f" DUP{dups}"
        if slug in RIGHT: held_dup.append(slug)
    print(f"{slug:45s} {tag:5s} canon={src:12s} n={n:3d} cov={cov if cov is None else round(cov,2)}{flag}")
print("\nRIGHT shows with non-chosen canonical:", sum(1 for s in RIGHT if want[s]['canonical_source']!='chosen'), "of", len(RIGHT))
print("RIGHT shows the agreement check would hold:", len(held_agree), held_agree)
print("RIGHT shows check 2 would hold:", len(held_dup), held_dup)
