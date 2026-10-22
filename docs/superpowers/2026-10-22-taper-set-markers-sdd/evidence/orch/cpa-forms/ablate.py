"""Line ablation over library shows: which marker lines are load-bearing for ownership/placement."""
import json, sys, re
from pathlib import Path
from llama import taper, jerrybase
from llama.models import Track
from llama.songs import GD_SHORTHAND
from llama.setlist import _TRACK_PREFIX, _NUM_PREFIX, _enumerated_prefix

ROOT = Path("~/.llama").expanduser()
OUT = Path(sys.argv[1])

def aliases(artist):
    return GD_SHORTHAND if artist and jerrybase.is_family_artist(artist) else {}

def override(show, sj):
    if (sj.get("structure") or {}).get("source") == "override":
        return True
    p = show / "overrides.json"
    if p.exists():
        try:
            o = json.loads(p.read_text())
        except Exception:
            return True
        return o.get("set_breaks") is not None or o.get("encore_after") is not None
    return False

def sig(d):
    return (tuple(d.placement.sets) if d.placement else None, d.reason)

rows = []
nshow = 0
for show in sorted((ROOT / "shows").glob("*/")):
    sjp = show / "show.json"
    if not sjp.exists():
        continue
    try:
        sj = json.loads(sjp.read_text())
        if override(show, sj):
            continue
        tracks = [Track.model_validate(t) for t in sj["tracks"]]
        if not tracks:
            continue
        md = json.loads((ROOT / "cache" / f"md_{sj['identifier']}.json").read_text())
    except Exception as e:
        continue
    meta = md.get("metadata", md)
    al = aliases(sj.get("artist"))
    today = [t.set for t in tracks]
    base = taper.decide_taper(tracks, meta, aliases=al, today_sets=today)
    text, source = taper.taper_text_for(meta)
    if source == "none":
        continue
    nshow += 1
    lines = taper._preprocess(text)
    m2 = dict(meta); m2[source] = "\n".join(lines)
    if source == "notes":
        m2["description"] = meta.get("description")
    rebase = taper.decide_taper(tracks, m2, aliases=al, today_sets=today)
    if sig(rebase) != sig(base):
        rows.append({"slug": show.name, "kind": "REJOIN-MISMATCH", "base": sig(base)[1], "rebase": sig(rebase)[1]})
        continue
    enumerated = _enumerated_prefix(lines)
    for i, line in enumerate(lines):
        if not line:
            continue
        core = _TRACK_PREFIX.sub("", line)
        if enumerated:
            core = _NUM_PREFIX.sub("", core)
        kind, num, cont, ae, rest = taper._classify(core)
        isfour = bool(taper._SET_FOUR_PLUS.search(line))
        enclike = kind == "song" and (taper._ENCORE_WORDS.search(line) or taper._encore_like(core))
        if kind == "song" and not isfour and not enclike:
            continue
        variants = {"delete": lines[:i] + lines[i+1:]}
        if kind != "song":
            variants["keep-rest"] = lines[:i] + ([rest] if rest.strip() else []) + lines[i+1:]
        for vn, vl in variants.items():
            m3 = dict(meta); m3[source] = "\n".join(vl)
            d = taper.decide_taper(tracks, m3, aliases=al, today_sets=today)
            if sig(d) != sig(base):
                rows.append({"slug": show.name, "artist": sj.get("artist"), "ident": sj["identifier"],
                             "source": source, "i": i, "line": line, "kind": kind, "num": num,
                             "four": isfour, "enclike": bool(enclike), "variant": vn,
                             "base_owned": base.placement is not None, "base_reason": base.reason,
                             "new_owned": d.placement is not None, "new_reason": d.reason,
                             "base_sets": list(base.placement.sets) if base.placement else None,
                             "new_sets": list(d.placement.sets) if d.placement else None,
                             "today": today,
                             "ctx": lines[max(0, i-2):i+3]})
OUT.write_text("".join(json.dumps(r) + "\n" for r in rows))
print("shows with taper text:", nshow, "rows:", len(rows))
