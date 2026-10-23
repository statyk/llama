import json, re, html as H, sys
from pathlib import Path
sys.argv=['x']
exec(open('/private/tmp/claude-501/-Users-shawn-projects-llama/604acb36-5fd2-4077-9d87-a6f3a6fcfd42/scratchpad/r3/agree.py').read().split('held_agree, held_dup')[0])
from llama import jerrybase
from llama.songs import GD_SHORTHAND
for slug in ['darkstarorchestra-2005-05-30','gomez-2006-10-06','ratdog-1995-08-09','soundtribesector9-2004-06-24','darkstarorchestra-2004-08-31','ratdog-2007-08-12']:
    r = rows[slug]; x = want[slug]
    tr = r["tracks"] if r.get("replayed") else r.get("stored_tracks")
    lst = numbered_lines(r.get("description")) if x["list"] == "numbered_lines" else (r.get("own_parse") or [])
    cands = [clean(c) for c in lst]
    fam = jerrybase.is_family_artist(r.get("artist") or slug.split('-')[0])
    al = GD_SHORTHAND if fam else {}
    tracks = [Track(index=i+1, set="1", title=c or t["file"], filename=t["file"], duration_sec=t.get("dur"), segue=False, title_source="tags") for i,(c,t) in enumerate(zip(cands,tr))]
    canon = r["canonical"]
    ps = ParsedSetlist(items=[SetlistItem(title=c["title"], normalized=normalize_song(c["title"]), set=c.get("set") or "1") for c in canon], confidence="high")
    res = align(tracks, ps, aliases=al)
    print(f"\n== {slug} family={fam} cov={res.coverage:.2f} n={len(tracks)} canon={len(canon)}")
    print("  canonical:", " | ".join(c["title"] for c in canon))
    for t, m in zip(tracks, res.matched):
        print(f"  {'OK ' if m else 'MISS'} {t.index:2d} {t.title!r}")
