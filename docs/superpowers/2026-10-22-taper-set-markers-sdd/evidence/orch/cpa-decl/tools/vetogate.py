import json, re, sys
sys.path.insert(0, "scripts")
from pathlib import Path
import taper_probe as tp
from llama import taper
exec(open(sys.argv[1]).read().split("hits = {")[0].split("NEW = ")[1].join(["NEW = ",""]) if False else "")
NEW = {
 "encor typo": re.compile(r"\bencor\b", re.I),
 "glued NE.": re.compile(r"^\s*\d{1,3}E[.):]", re.I | re.M),
 "E<space>Song line": re.compile(r"^\s*(?:\d{1,3}[.)]?\s+)?E\s+[A-Z]", re.M),
 "E~ / -e- item": re.compile(r"(?:^|[,>]|\s\s)\s*[-~]*e[~-]+\s*\w", re.I | re.M),
}
root = Path("~/.llama").expanduser(); bundles = Path("~/.llama-harness/t3/bundles").expanduser()
rows = [json.loads(l) for l in open(Path("~/.llama-harness/piece2/gate/gate_rows.jsonl").expanduser())]
for r in rows:
    if r["status"] != "owned": continue
    sj, tracks = tp.parse_bundle(bundles/f"{r['slug']}.md"); meta = tp.load_meta(root, sj["identifier"])
    text, src = taper.taper_text_for(meta); t = taper.read_taper_structure(text)
    if t.has_encore: continue
    pre = "\n".join(taper._preprocess(text))
    for k, rx in NEW.items():
        m = rx.search(pre)
        if m: print(r["slug"], r["in_scope"], k, repr(pre[max(0,m.start()-5):m.end()+20]))
print("done")
