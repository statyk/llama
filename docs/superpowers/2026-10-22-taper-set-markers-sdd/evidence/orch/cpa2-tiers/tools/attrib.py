# Attribute each delta row's flip to the first Checkpoint A commit that changes its decision.
import json, sys, importlib.util
from pathlib import Path
sys.path.insert(0, "scripts")
import taper_probe as tp
from llama.models import Track
S = Path(sys.argv[1]); mode = sys.argv[2]  # lib | gate
VERS = ["5010a00", "b643513", "b503f24", "3d1c1e7", "025e713", "3758240", "2abad1e", "569b88c"]
NAME = {"b643513": "1 veto gap", "b503f24": "2 set+encore pre-split", "3d1c1e7": "3 encore none",
        "025e713": "4 R-ITEM", "3758240": "5 (b) annotation", "2abad1e": "6 (c) disc-set", "569b88c": "7 (d) keep encore"}
mods = {}
for v in VERS:
    spec = importlib.util.spec_from_file_location(f"taper_{v}", S / "versions" / f"taper_{v}.py")
    m = importlib.util.module_from_spec(spec); sys.modules[spec.name] = m; spec.loader.exec_module(m); mods[v] = m
root = Path("~/.llama").expanduser(); bundles = Path("~/.llama-harness/t3/bundles").expanduser()
def load(slug):
    if mode == "lib":
        sj = json.loads((root/"shows"/slug/"show.json").read_text())
        tracks = [Track.model_validate(t) for t in sj["tracks"]]
    else:
        sj, tracks = tp.parse_bundle(bundles/f"{slug}.md")
    meta = tp.load_meta(root, sj["identifier"])
    return sj, tracks, meta
out = []
for slug in sys.argv[3:]:
    sj, tracks, meta = load(slug)
    today = [t.set for t in tracks]
    seq = []
    for v in VERS:
        d = mods[v].decide_taper(tracks, meta, aliases=tp.aliases_for(sj.get("artist")), today_sets=today)
        seq.append((v, "OWNED" if d.placement is not None else d.reason, list(d.placement.sets) if d.placement else None))
    flips = [NAME[seq[i][0]] for i in range(1, len(seq)) if (seq[i][1] == "OWNED") != (seq[i-1][1] == "OWNED") or seq[i][2] != seq[i-1][2]]
    rec = {"slug": slug, "flips": flips, "first": seq[0][1], "final": seq[-1][1], "seq": [s[1] for s in seq]}
    out.append(rec)
    print(json.dumps(rec))
