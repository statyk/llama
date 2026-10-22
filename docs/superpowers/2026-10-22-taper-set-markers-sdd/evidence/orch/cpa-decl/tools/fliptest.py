"""Re-run decide_taper on a hand-corrected scratch copy of a row's taper text (in memory only)."""
import sys, re, json, contextlib
sys.path.insert(0, "scripts")
from pathlib import Path
import taper_probe as tp
from llama import taper
from llama.setlist import _TRACK_PREFIX, _NUM_PREFIX
root = Path("~/.llama").expanduser(); bundles = Path("~/.llama-harness/t3/bundles").expanduser()
ev = Path("docs/superpowers/2026-10-22-taper-set-markers-evidence")
s1 = {r["slug"]: r for r in json.loads((ev/"sort1.json").read_text())}

@contextlib.contextmanager
def single_strip():
    """Reader-local fix: strip the enumerated _NUM_PREFIX only when _TRACK_PREFIX stripped nothing."""
    orig = taper._song_titles
    def patched(rest, enumerated):
        r2 = _TRACK_PREFIX.sub("", rest)
        if r2 == rest and enumerated:
            r2 = _NUM_PREFIX.sub("", r2)
        return orig(r2, False)
    taper._song_titles = patched
    try: yield
    finally: taper._song_titles = orig

def run(slug, subs, field=None, patch=None, note=""):
    sj, tracks = tp.parse_bundle(bundles/f"{slug}.md")
    meta = dict(tp.load_meta(root, sj["identifier"]))
    before = tp.decide(tracks, meta, sj.get("artist"), [t.set for t in tracks])
    fld = field or ("notes" if before.source == "notes" else "description")
    text = taper._field_text(meta.get(fld))
    for old, new in subs:
        if old.startswith("re:"):
            text, n = re.subn(old[3:], new, text, flags=re.M)
        else:
            n = text.count(old); text = text.replace(old, new)
        assert n, (slug, old)
    meta[fld] = text
    with (single_strip() if patch == "single" else contextlib.nullcontext()):
        d = tp.decide(tracks, meta, sj.get("artist"), [t.set for t in tracks])
    match = ""
    if d.placement is not None:
        r = s1.get(slug, {}); tb, te = r.get("t_breaks"), r.get("t_enc")
        if tb is not None or te is not None:
            match = tp.compare(list(d.placement.sets), tp.target_labels(len(tracks), tb, te), tracks)
        else:
            match = "no-target"
        if r.get("renum"): match += "(renum)"
    print(json.dumps({"slug": slug, "fix": note, "before": before.reason, "after": d.reason or "OWNED",
                      "owned": d.placement is not None, "target": match,
                      "bounds": list(d.placement.boundaries) if d.placement else None}))

T = [
 # --- R-ITEM
 ("philleshandfriends-2007-10-07", [(r"re:s\dt\d+:\s*", "")], None, None, "R-ITEM strip sNtNN: prefix"),
 ("gratefuldead-1980-10-10", [("Set 1: (Acoustic)", "Set 1:"), ("Set 2: (Electric)", "Set 2:")], None, None, "R-ITEM drop parenthetical-only item after header"),
 ("infamousstringdusters-2008-12-06", [(r"re:^=+\s*$", "")], None, None, "R-ITEM drop decoration-only ===== lines"),
 ("railroadearth-2005-08-20", [(" Disc 1:", ""), (" Disc 2:", ""), (" Disc 3:", "")], None, None, "R-ITEM drop disc label in header rest"),
 ("robertwalters20thcongress-2004-01-02", [("Set 2:-Disk 2", "Set 2:")], None, None, "R-ITEM drop disc label in header rest"),
 ("derektrucksband-2003-12-26", [], None, "single", "R-ITEM single number strip (44 Blues)"),
 ("darkstarorchestra-2007-07-06", [(r"re:^\d\d: ", "")], None, None, "R-ITEM strip NN: prefix (non-enumerated)"),
 ("greyboyallstars-2012-04-20", [("Quantico, VA", "Quantico VA")], None, None, "R-ITEM comma split inside one numbered title"),
 ("railroadearth-2014-11-28", [("Lordy, Lordy", "Lordy Lordy")], None, None, "R-ITEM comma split inside one numbered title"),
 ("philleshandfriends-2005-12-29", [("Darkstar (v1)", "Darkstar"), ("Darkstar (v2)", "Darkstar")], None, None, "R-ITEM drop (v1) annotation"),
 ("clubdelf-2004-05-20", [("->?(@15:57) 24:48", ""), (r"re:^Tr-\d+ ", ""), (r"re:\s\d+:\d\d$", "")], None, None, "R-ITEM drop junk/Tr-/durations"),
 ("infamousstringdusters-2012-03-17", [("Set Break\n", "")], None, "single", "R-ITEM single strip + drop Set Break item"),
 ("philleshandfriends-2004-12-17", [(" (Chris vocals)", "")], None, None, "R-ITEM drop credit parenthetical"),
 ("perpetualgroove-2007-05-26", [("When You're In^*->", "When You're In->")], None, None, "R-ITEM drop ^ (tape lacks song)"),
 ("stantonmoore-2001-11-20", [(r"re:^\d+\. \?\s*\*?$", "")], None, None, "R-ITEM drop ? items"),
 ("philleshandfriends-2005-12-04", [("1) Warm Up", "1) Tuning")], None, None, "FILLER treat Warm Up as filler"),
 # --- R-FORM (annotated worded header)
 ("cowboyjunkies-2012-04-26", [("SET ONE (50:28)", "SET ONE"), ("SET TWO (1:15:03)", "SET TWO")], None, None, "R-FORM header + (duration)"),
 ("joerussosalmostdead-2017-03-11", [("Set One (9:30PM - 10:46PM):", "Set One:"), ("Set Two (11:18PM - 12:41AM):", "Set Two:")], None, None, "R-FORM header + (time range)"),
 ("joerussosalmostdead-2018-02-15", [("Set One (8:20PM - 9:45PM):", "Set One:"), ("Set Two (10:16PM - 11:53PM):", "Set Two:")], None, None, "R-FORM header + (time range)"),
 ("joerussosalmostdead-2019-03-03", [("Set One @ (8:16PM - 9:18PM):", "Set One:"), ("Set Two  (9:53PM - 11:37PM):", "Set Two:")], None, None, "R-FORM header + @ (time range)"),
 ("joerussosalmostdead-2019-11-25", [("Set One (8:02PM - 9:38PM)", "Set One:"), ("Set Two (10:06PM - 12:05AM):", "Set Two:")], None, None, "R-FORM header + (time range)"),
 ("joerussosalmostdead-2015-12-19", [("Set 1 (9:14PM - 10:30PM):", "Set 1:"), ("Set 2 (11:00PM - 12:45AM):", "Set 2:")], None, None, "R-FORM header + (time range)"),
 ("joerussosalmostdead-2018-02-18", [("Set One (8:38PM - 9:56PM):", "Set One:"), ("Set Two (10:26PM - 12:14AM?):", "Set Two:")], None, None, "R-FORM header + (time range)"),
 ("moe-2007-09-01", [("disc 1 (set 1 afternoon):", "disc 1 (set 1):"), ("-set 2 (night)", "-set 2-")], None, None, "R-FORM header + (word)"),
 ("tealeafgreen-2002-11-21", [(r"re:^(DISC \w+ - SET \w+) \(.*\)$", r"\1")], None, None, "R-FORM Disc-Set + (annotation)"),
 ("yondermountainstringband-2005-10-13", [(r"re:^(Disc \d - Set \d) \([\d:]+\):", r"\1:")], None, None, "R-FORM Disc-Set + (duration)"),
 ("umphreysmcgee-2006-12-31", [(r"re:^(Set I+) \([\d:]+\)$", r"\1")], None, None, "R-FORM header + (duration)"),
 ("belafleckandtheflecktones-2003-04-12", [("Disc 2 - Set II...", "Disc 2 - Set II")], None, None, "R-FORM Disc-Set + ..."),
 ("garciagrass-2010-10-23", [("disc 01 [Set I]", "disc 01 (Set I)"), ("disc 02 [Set II]", "disc 02 (Set II)")], None, None, "R-FORM disc + [Set]"),
 # --- N-FORM (would need a spec ruling; simulated by rewriting to a listed form)
 ("ratdog-2008-11-16", [("Set I Disc 1: 74:16", "Set I:"), ("Set II Disc 2: 69:34", "Set II:")], None, None, "N-FORM Set N Disc M"),
 ("johnkadlecik-2011-04-28", [(r"re:^Set (\d)( Continued)? Disc \d \(.*\)$", r"Set \1")], None, None, "N-FORM Set N Disc M"),
 ("papagrowsfunk-2004-01-23", [("Set 1 Disc 1", "Set 1"), ("Set 2 Disc 2", "Set 2"), (r"re:^Tr-\d+ ", "")], None, None, "N-FORM Set N Disc M (+Tr- prefix)"),
 ("thedead-2009-04-24", [("set 1 disc 1", "set 1"), ("set 2 disc 2", "set 2"), ("set 2 disc 3", "set 2")], None, None, "N-FORM Set N Disc M"),
 ("derektrucksband-2004-11-26", [("set 2 / disc 2", "set 2")], None, None, "N-FORM Set N / Disc M"),
 ("discobiscuits-2007-05-27", [("Set I (Disc 1) *", "Set I"), ("Set II (Disc 2)", "Set II"), ("Set II cont'd (Disc 3)", "Set II cont'd")], None, None, "N-FORM Set N (Disc M)"),
 ("greatamericantaxi-2009-11-03", [("Set I Disc I", "Set I"), ("Set II Disc II", "Set II")], None, None, "N-FORM Set N Disc M"),
 ("ryanadams-2009-02-21", [("Set One Disc One", "Set One"), ("Set One Disc Two", "Set One"), ("Set Two Disc Two", "Set Two")], None, None, "N-FORM Set N Disc M"),
 ("soulive-2001-12-15", [("Set 1 disc 1", "Set 1"), ("Set 2 disc 2", "Set 2")], None, None, "N-FORM Set N disc M"),
 ("soundtribesector9-2007-07-08", [("Set 1/Disc 1:", "Set 1:"), ("Set 2/Disc 2:", "Set 2:"), ("Set 2/Disc 3:", "Set 2:")], None, None, "N-FORM Set N/Disc M"),
 ("darkstarorchestra-2014-07-31", [("Set 1 Disc 1:", "Set 1:"), ("Set 2 Disc 2", "Set 2")], None, None, "N-FORM Set N Disc M"),
 ("philleshandfriends-2008-11-18", [("Disc I 1st Set", "1st Set"), ("Disc II 2nd Set Con't", "2nd Set cont."), ("Disc II 2nd Set", "2nd Set")], None, None, "N-FORM Disc N Mth Set"),
 ("philleshandfriends-2008-07-06", [("Disc I 1st Set", "1st Set"), ("Disc III 2nd Set Con't and Encore", "2nd Set cont."), ("Disc II 2nd Set", "2nd Set")], None, None, "N-FORM Disc N Mth Set"),
 ("tedeschitrucksband-2016-03-05", [("Disc I 1st Set", "1st Set"), ("Disc III 2nd Set Con't", "2nd Set cont."), ("Disc II 2nd Set", "2nd Set")], None, None, "N-FORM Disc N Mth Set"),
 ("thecodetalkers-2003-10-31", [("DISC 1 SET ONE", "SET ONE"), ("DISC 2 SET TWO", "SET TWO")], None, None, "N-FORM Disc N Set M (no sep)"),
 ("eotoband-2008-03-24", [("Disk 1: Set 1", "Set 1"), ("Disk 2: Set 2", "Set 2"), ("Disk 3: Encore", "Encore")], None, None, "N-FORM Disk N: Set M"),
 ("railroadearth-2006-02-18", [("DISC 01:SET I :", "SET I :"), ("DISC 02:SET II", "SET II"), ("DISC 03:SET II (cont'd)", "SET II cont'd"), (r"re:^0(\d): ", r"0\1. ")], None, None, "N-FORM DISC N:SET M (+NN: prefix)"),
 ("splinteredsunlight-2001-02-10", [("CD1 Set 1", "Set 1"), ("CD2 Set 2 Part1", "Set 2"), ("CD 3 Set 3 Part1", "Set 3"), ("CD4 Set 3 Part2", "Set 3 cont.")], None, None, "N-FORM CDn Set m"),
 ("corblund-2004-11-04", [("Disc/Set1", "Set 1"), ("Disc/Set2", "Set 2"), ("Disc/Set3", "Set 3")], None, None, "N-FORM Disc/SetN"),
 ("greenskybluegrass-2013-08-02", [("SET 1/2", "SET 1"), ("SET 2/2", "SET 2")], None, None, "N-FORM Set N/M"),
 ("jeffaustinandchriscastino-2004-03-18", [("(Start Set 1)", "(Set 1)"), ("(Start Set 2)", "(Set 2)")], None, None, "N-FORM (Start Set N)"),
]
for slug, subs, fld, patch, note in T:
    try:
        run(slug, subs, fld, patch, note)
    except AssertionError as e:
        print(json.dumps({"slug": slug, "fix": note, "error": f"sub not applied: {e}"}))
