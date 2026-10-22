"""For every inline-split marker over the cache: does neutralising THAT split change the reader's outcome?"""
import json, re, html, sys
from pathlib import Path
from llama import taper
from llama.setlist import _INLINE_MARKER, _TRACK_PREFIX, _NUM_PREFIX, _enumerated_prefix
ROOT=Path("~/.llama").expanduser()
sel={}
for sjp in (ROOT/"shows").glob("*/show.json"):
    try: sj=json.loads(sjp.read_text()); sel[sj["identifier"]]=sjp.parent.name
    except Exception: pass
PROSE=re.compile(r"\b(of|from|end|missing|part|including|differs|source|sources|patch|patched|to|the|in|during|for|with|is|was|and|on|at|by|between|throughout|thru|through|than|show|complete)\s*$|"
                 r"(recorded|transfer|lineage|source|taper|sbd|dat|flac|shn|cassette|master|eac|wav|cdr|>|mic|aud)",re.I)
def sig(r): return (r.asserts, r.reason, tuple((i.title,i.set) for i in r.items), r.has_encore)
out=[]
for p in sorted((ROOT/"cache").glob("md_*.json")):
    try: md=json.loads(p.read_text())
    except Exception: continue
    meta=md.get("metadata",md) if isinstance(md,dict) else {}
    if not isinstance(meta,dict): continue
    chosen,src=taper.taper_text_for(meta)
    for fld in ("description","notes"):
        text=taper._field_text(meta.get(fld))
        if not text: continue
        t=re.sub(r"<br\s*/?>","\n",text,flags=re.I); t=re.sub(r"<[^>]+>","\n",t); t=html.unescape(t)
        raw=[ln.strip() for ln in t.splitlines()]
        if not any(_INLINE_MARKER.search(ln) for ln in raw): continue
        base=taper.read_taper_structure(text)
        for li,ln in enumerate(raw):
            for m in _INLINE_MARKER.finditer(ln):
                before=ln[:m.start()]
                # neutralise this one split: join with a token that blocks the split (" " is \s in re? use '~~')
                variant=ln[:m.start()]+" ~"+ln[m.end():]   # '~' after space: lookahead fails
                # verify the split is blocked
                t2="\n".join(raw[:li]+[variant]+raw[li+1:])
                r2=taper.read_taper_structure(t2)
                changed = sig(r2)!=sig(base)
                prose=bool(PROSE.search(before))
                out.append(dict(ident=p.stem[3:],fld=fld,read=(src==fld),lib=sel.get(p.stem[3:]),
                    before=before[-60:],after=ln[m.end():m.end()+60],base_asserts=base.asserts,base_reason=base.reason,
                    new_asserts=r2.asserts,new_reason=r2.reason,changed=changed,prose=prose,
                    labels_changed=(base.asserts and r2.asserts and sig(r2)[2]!=sig(base)[2])))
json.dump(out,open(sys.argv[1],"w"))
print(len(out))
