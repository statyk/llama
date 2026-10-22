# For each (d)-vetoed row: does the pre-(d) taper placement change today's NUMBERED boundaries
# (i.e., would it have fixed or changed a set break), apart from folding the encore?
import json, sys, importlib.util
from pathlib import Path
sys.path.insert(0, "scripts")
import taper_probe as tp
from llama.models import Track
from llama.structure import is_filler
S = Path(sys.argv[1]); mode = sys.argv[2]
spec = importlib.util.spec_from_file_location("taper_pre_d", S/"versions"/"taper_2abad1e.py")
m = importlib.util.module_from_spec(spec); sys.modules[spec.name] = m; spec.loader.exec_module(m)
root = Path("~/.llama").expanduser(); bundles = Path("~/.llama-harness/t3/bundles").expanduser()
def nb(labels, tracks):
    # numbered boundaries over non-filler, non-encore tracks: positions where the numbered label changes
    seq = [(i, l) for i, (l, t) in enumerate(zip(labels, tracks)) if l != "encore" and not is_filler(t.title)]
    return [seq[k][0] for k in range(1, len(seq)) if seq[k][1] != seq[k-1][1]]
for slug in sys.argv[3:]:
    if mode == "lib":
        sj = json.loads((root/"shows"/slug/"show.json").read_text()); tracks = [Track.model_validate(t) for t in sj["tracks"]]
    else:
        sj, tracks = tp.parse_bundle(bundles/f"{slug}.md")
    meta = tp.load_meta(root, sj["identifier"])
    today = [t.set for t in tracks]
    d = m.decide_taper(tracks, meta, aliases=tp.aliases_for(sj.get("artist")), today_sets=today)
    labs = list(d.placement.sets)
    tb = nb(today, tracks); pb = nb(labs, tracks)
    enc_today = sum(1 for l in today if l == "encore")
    # where does today's encore start relative to taper's last boundary
    print(f"{slug:42s} today_numbered_breaks={tb} taper_breaks={pb} {'SAME' if tb==pb else 'DIFFERENT'} today_enc_tracks={enc_today} today_sets={sorted(set(today))}")
