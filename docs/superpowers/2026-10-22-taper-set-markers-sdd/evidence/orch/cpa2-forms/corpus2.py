"""Every corpus line whose classification HEAD vs noB / noC differs, plus text-level reader
outcomes under HEAD and each variant. Read-only over ~/.llama/cache."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import variants as V
from llama import taper as T, jerrybase
from llama.setlist import _TRACK_PREFIX, _NUM_PREFIX, _enumerated_prefix

ROOT = Path("~/.llama").expanduser()
OUT = Path(sys.argv[1])
sel = {}
for sjp in (ROOT / "shows").glob("*/show.json"):
    try:
        sj = json.loads(sjp.read_text()); sel[sj["identifier"]] = sjp.parent.name
    except Exception:
        pass

def rd(text):
    r = T.read_taper_structure(text)
    return [r.asserts, r.reason, r.has_encore, r.encore_like, [(i.title, i.set) for i in r.items]]

out = open(OUT, "w")
for p in sorted((ROOT / "cache").glob("md_*.json")):
    try:
        md = json.loads(p.read_text())
    except Exception:
        continue
    meta = md.get("metadata", md) if isinstance(md, dict) else {}
    if not isinstance(meta, dict):
        continue
    ident = p.stem[3:]
    c = meta.get("creator"); c = (c[0] if isinstance(c, list) and c else c) or ""
    fam = jerrybase.is_family_artist(str(c))
    V.patch("head")
    _, hsrc = T.taper_text_for(meta)
    srcs = {}
    for v in ("noB", "noC", "noItem", "noPre"):
        V.patch(v); srcs[v] = T.taper_text_for(meta)[1]
    V.patch("head")
    for fld in ("description", "notes"):
        text = T._field_text(meta.get(fld))
        if not text:
            continue
        V.patch("head")
        lines = T._preprocess(text)
        en = _enumerated_prefix(lines)
        hits = []
        for i, ln in enumerate(lines):
            if not ln:
                continue
            core = _TRACK_PREFIX.sub("", ln)
            if en:
                core = _NUM_PREFIX.sub("", core)
            V.patch("head"); h = T._classify(core)
            if h[0] != "set":
                continue
            diff = {}
            for v in ("noB", "noC"):
                V.patch(v); o = T._classify(core)
                if o[:4] != h[:4]:
                    diff[v] = [o[0], o[1]]
            V.patch("head")
            if diff:
                hits.append({"i": i, "line": ln, "core": core, "num": h[1], "cont": h[2], "ae": h[3],
                             "rest": h[4], "diff": diff,
                             "prev": lines[max(0, i-3):i], "next": lines[i+1:i+4]})
        V.patch("head"); rh = rd(text)
        rv = {}
        for v in ("noB", "noC", "noItem", "noPre"):
            V.patch(v); rv[v] = rd(text)
        V.patch("head")
        changed = {v: rv[v][:2] for v in rv if rv[v][:2] != rh[:2]}
        items_changed = {v: True for v in rv if rv[v][4] != rh[4]}
        if hits or changed or items_changed:
            out.write(json.dumps({"ident": ident, "creator": str(c), "fam": fam, "fld": fld,
                                  "read": hsrc == fld, "srcs": srcs, "hsrc": hsrc, "lib": sel.get(ident),
                                  "head": rh[:4], "changed": changed, "items_changed": items_changed,
                                  "hits": hits}) + "\n")
out.close()
