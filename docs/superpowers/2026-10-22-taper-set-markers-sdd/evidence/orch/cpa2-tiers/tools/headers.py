# Print the recognised marker lines (and the encore-like flag) for each slug: lib or gate.
import json, sys
from pathlib import Path
sys.path.insert(0, "scripts")
import taper_probe as tp
from llama import taper
from llama.models import Track
from llama.setlist import _TRACK_PREFIX, _NUM_PREFIX, _enumerated_prefix
root = Path("~/.llama").expanduser(); bundles = Path("~/.llama-harness/t3/bundles").expanduser()
mode = sys.argv[1]
for slug in sys.argv[2:]:
    if mode == "lib":
        sj = json.loads((root/"shows"/slug/"show.json").read_text()); tracks = [Track.model_validate(t) for t in sj["tracks"]]
    else:
        sj, tracks = tp.parse_bundle(bundles/f"{slug}.md")
    meta = tp.load_meta(root, sj["identifier"])
    today = [t.set for t in tracks]
    d = tp.decide(tracks, meta, sj.get("artist"), today)
    text, src = taper.taper_text_for(meta)
    lines = taper._preprocess(text); en = _enumerated_prefix(lines)
    hdrs = []
    for ln in lines:
        if not ln: continue
        core = _TRACK_PREFIX.sub("", ln)
        if en: core = _NUM_PREFIX.sub("", core)
        k = taper._classify(core)
        if k[0] != "song":
            hdrs.append(f"{'S'+str(k[1]) if k[0]=='set' else 'E'}{'c' if k[2] else ''}:{ln[:60]!r}")
    labs = list(d.placement.sets) if d.placement else None
    same = labs == today
    bnd = d.placement.boundaries if d.placement else None
    print(f"{slug} src={src} same_as_today={same} bounds={bnd} n={len(tracks)} enc={d.taper.has_encore}")
    print("    ", " ; ".join(hdrs))
