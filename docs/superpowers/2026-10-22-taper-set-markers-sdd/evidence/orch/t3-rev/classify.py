import sys, json
from pathlib import Path
from collections import Counter
sys.path.insert(0, "scripts")
import taper_probe as tp
from llama import taper
B = Path("~/.llama-harness/t3/bundles").expanduser(); R = Path("~/.llama").expanduser()
rows=[json.loads(l) for l in open(Path('~/.llama-harness/piece2/gate/gate_rows.jsonl').expanduser())]
cnt=Counter()
for r in rows:
    if not r['in_scope'] or not r['status'].startswith('unplaced'): continue
    sj, tracks = tp.parse_bundle(B/f"{r['slug']}.md")
    n=len(tracks); c=sum(1 for t in tracks if taper._counts(t))
    srcs=Counter(t.title_source for t in tracks)
    frac=c/n
    cls = "none-count" if c==0 else ("<50% count" if frac<0.5 else ">=50% count")
    cnt[cls]+=1
    print(f"{cls:12s} {c:3d}/{n:3d} {dict(srcs)} {r['slug']} :: {r['reason'][:80]}")
print(cnt)
