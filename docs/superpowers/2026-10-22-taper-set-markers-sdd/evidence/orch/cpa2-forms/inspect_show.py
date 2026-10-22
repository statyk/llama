"""For library slugs: today vs HEAD breaks, the lines a variant classifies differently, and
the boundary items. Usage: inspect_show.py <variant> slug..."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import variants as V
from llama import taper as T, jerrybase
from llama.models import Track
from llama.songs import GD_SHORTHAND
from llama.setlist import _TRACK_PREFIX, _NUM_PREFIX, _enumerated_prefix
ROOT = Path("~/.llama").expanduser()

def brk(sets):
    return [f"{i}:{sets[i-1]}>{sets[i]}" for i in range(1, len(sets)) if sets[i] != sets[i-1]]

def classify_lines(text, variant):
    V.patch("head")
    lines = T._preprocess(text)
    en = _enumerated_prefix(lines)
    res = []
    for i, ln in enumerate(lines):
        core = _TRACK_PREFIX.sub("", ln)
        if en:
            core = _NUM_PREFIX.sub("", core)
        V.patch("head"); h = T._classify(core)
        V.patch(variant); o = T._classify(core)
        V.patch("head")
        res.append((i, ln, h, o))
    return lines, res

def main():
    variant = sys.argv[1]
    for slug in [a for a in sys.argv[2:] if not a.startswith("-")]:
        sj = json.loads((ROOT/"shows"/slug/"show.json").read_text())
        md = json.loads((ROOT/"cache"/f"md_{sj['identifier']}.json").read_text()); meta = md.get("metadata", md)
        tracks = [Track.model_validate(t) for t in sj["tracks"]]
        al = GD_SHORTHAND if jerrybase.is_family_artist(sj.get("artist") or "") else {}
        today = [t.set for t in tracks]
        V.patch("head")
        d = T.decide_taper(tracks, meta, aliases=al, today_sets=today)
        V.patch(variant)
        dv = T.decide_taper(tracks, meta, aliases=al, today_sets=today)
        V.patch("head")
        print(f"##### {slug}  ident={sj['identifier']} src={d.source} ntracks={len(tracks)}")
        print("  today:", brk(today))
        print("  HEAD :", brk(d.placement.sets) if d.placement else f"NOT OWNED {d.reason}", d.placement.boundaries if d.placement else "")
        print(f"  {variant}:", brk(dv.placement.sets) if dv.placement else f"NOT OWNED {dv.reason}")
        text, src = T.taper_text_for(meta)
        lines, res = classify_lines(text, variant)
        for i, ln, h, o in res:
            if h[:4] != o[:4]:
                ctx0 = [l for l in lines[max(0, i-2):i]]
                ctx1 = [l for l in lines[i+1:i+3]]
                print(f"  L{i} DIFF head={h[0]}{h[1] or ''} var={o[0]}{o[1] or ''}: {ln!r}")
                print(f"       prev={ctx0!r}")
                print(f"       next={ctx1!r}")
        # boundary items
        items = d.taper.items
        for k in range(1, len(items)):
            if items[k].set != items[k-1].set:
                print(f"  boundary {items[k-1].set}|{items[k].set}: {items[k-1].title!r} | {items[k].title!r}")
        if d.placement:
            for b in d.placement.boundaries:
                a = tracks[b-1]; nb = tracks[b] if b < len(tracks) else None
                print(f"   placed after t{b}: {a.title!r} | {nb.title if nb else None!r}")
        if "-v" in sys.argv:
            for t in tracks:
                print("    ", t.index, t.set, (d.placement.sets[t.index-1] if d.placement else "-"), t.title, t.title_source)

if __name__ == "__main__":
    args = [a for a in sys.argv if a != "-v"]
    v = "-v" in sys.argv
    sys.argv = args + (["-v"] if v else [])
    main()
