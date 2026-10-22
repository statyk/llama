import json, re, sys
from pathlib import Path
from llama import taper
from llama.setlist import _split_songs
root = Path("~/.llama").expanduser()
rows = [json.loads(l) for l in open(Path("~/.llama-harness/piece2/gate/library_rows.jsonl").expanduser())]
NEW = {
 "encor typo": re.compile(r"\bencor\b", re.I),
 "glued NE.": re.compile(r"^\s*\d{1,3}E[.):]", re.I | re.M),
 "E<space>Song line": re.compile(r"^\s*(?:\d{1,3}[.)]?\s+)?E\s+[A-Z]", re.M),
 "E~ / -e- item": re.compile(r"(?:^|[,>]\s*)[-~]*e[~-]+\s*\w", re.I | re.M),
}
hits = {k: [] for k in NEW}
for r in rows:
    if r["status"] != "owned": continue
    sj = json.loads((root/"shows"/r["slug"]/"show.json").read_text())
    md = json.loads((root/"cache"/f"md_{sj['identifier']}.json").read_text()); meta = md.get("metadata", md)
    text, src = taper.taper_text_for(meta)
    t = taper.read_taper_structure(text)
    if t.has_encore: continue   # the veto only applies without a recognised encore
    pre = "\n".join(taper._preprocess(text))
    for k, rx in NEW.items():
        m = rx.search(pre)
        if m: hits[k].append((r["slug"], r.get("tier"), pre[max(0,m.start()-5):m.end()+25].replace("\n"," / ")))
for k, v in hits.items():
    print(f"## {k}: {len(v)}")
    for x in v: print("  ", x)
