"""Every marker line over the cache, with context and the item's reader outcome."""
import json, sys
from pathlib import Path
from llama import taper, jerrybase
from llama.setlist import _TRACK_PREFIX, _NUM_PREFIX, _enumerated_prefix, _INLINE_MARKER
import html, re

ROOT = Path("~/.llama").expanduser()
OUT = Path(sys.argv[1])
# selected identifiers of library shows
sel = {}
for sjp in (ROOT / "shows").glob("*/show.json"):
    try:
        sj = json.loads(sjp.read_text()); sel[sj["identifier"]] = sjp.parent.name
    except Exception:
        pass
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
    chosen, csrc = taper.taper_text_for(meta)
    for fld in ("description", "notes"):
        text = taper._field_text(meta.get(fld))
        if not text:
            continue
        r = taper.read_taper_structure(text)
        lines = taper._preprocess(text)
        # which preprocessed lines came from an inline split: mark lines whose raw line contained an inline split
        enumerated = _enumerated_prefix(lines)
        for i, line in enumerate(lines):
            if not line:
                continue
            core = _TRACK_PREFIX.sub("", line)
            if enumerated:
                core = _NUM_PREFIX.sub("", core)
            kind, num, cont, ae, rest = taper._classify(core)
            if kind == "song":
                continue
            out.write(json.dumps({"ident": ident, "creator": str(c), "fam": fam, "fld": fld,
                "read": csrc == fld, "asserts": r.asserts, "reason": r.reason, "has_encore": r.has_encore,
                "lib": sel.get(ident), "i": i, "line": line, "core": core, "kind": kind, "num": num,
                "cont": cont, "ae": ae, "rest": rest,
                "prev": lines[max(0,i-3):i], "next": lines[i+1:i+4]}) + "\n")
out.close()
