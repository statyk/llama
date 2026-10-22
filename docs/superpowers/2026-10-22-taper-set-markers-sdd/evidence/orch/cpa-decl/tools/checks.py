import sys, json
sys.path.insert(0, "scripts")
from pathlib import Path
import taper_probe as tp
from llama.setlist import parse_setlist, is_junk_title
from llama.structure import is_filler, fuzzy_title_eq, fuzzy_norm_title
root = Path("~/.llama").expanduser(); bundles = Path("~/.llama-harness/t3/bundles").expanduser()
def desc(slug, fld="description"):
    sj, tracks = tp.parse_bundle(bundles/f"{slug}.md"); meta = tp.load_meta(root, sj["identifier"])
    from llama import taper
    return taper._field_text(meta.get(fld))
want = {
 "philleshandfriends-2005-12-29": ["Darkstar"],
 "philleshandfriends-2007-10-07": ["Ripple", "Casey"],
 "gratefuldead-1980-10-10": ["Electric", "Acoustic", "Mississippi"],
 "infamousstringdusters-2008-12-06": ["====", "West", "Truth"],
 "railroadearth-2005-08-20": ["Disc 2", "Long Way"],
 "robertwalters20thcongress-2004-01-02": ["Disk", "Cuervo"],
 "derektrucksband-2003-12-26": ["Blues"],
 "darkstarorchestra-2007-07-06": ["Ripple", "Jack Straw"],
 "greyboyallstars-2012-04-20": ["VA", "Quantico"],
 "railroadearth-2014-11-28": ["Lordy"],
 "umphreysmcgee-2005-04-16": ["Immigrant"],
 "perpetualgroove-2007-05-26": ["When You"],
 "clubdelf-2004-05-20": ["Scorp", "@15"],
 "deepbananablackout-2006-03-18": ["????", "Tr-0"],
 "moe-2004-10-31": ["Six Days"],
 "philleshandfriends-2004-12-17": ["Sugaree"],
 "kellerwilliams-2007-02-23": [")"],
 "stantonmoore-2001-11-20": ["?"],
 "samkiningerband-2008-06-26": ["Track 5"],
 "infamousstringdusters-2012-03-17": ["Cents", "Set Break"],
}
for slug, keys in want.items():
    items = parse_setlist(desc(slug)).items
    hits = [(i.set, i.title) for i in items if any(k in i.title for k in keys)]
    print(slug, "->", hits[:8])
print()
for t in ["Warm Up","Set Break","Encore Break","encore break","Callback / Banter","crowd/donor rap/intros","Donor Rap","Phil's Donor Rap","E: Donor Rap/Intros","Intro / Tuning","Crowd","(Electric)","=====","-Disk 2","Disc 2:","?","Tr-07 ????",")","Track 5","Band Introductions","Thanks/Donor Rap","Encore Banter","Intros / Crowd","(crowd)"]:
    print(repr(t), "filler", is_filler(t), "junk", is_junk_title(t))
print()
pairs=[("08: Ripple","Ripple"),("08: Jack Straw","Jack Straw"),("Darkstar (v1)","Darkstar >"),("When You're In^","When You're In"),("Immigrant Song^","Immigrant Song"),("Sugaree (Chris vocals)","Sugaree"),("Pedro","Pedro In D Major"),("Freshman 10","Freshman 10 (Pete McNeil on Drums)"),("El Cuervo","El Cuervo (Live Debut)"),("Big Wind","E: Big Wind"),("Harder They Come","E1: Harder They Come ->"),("- Open e","Open e"),("- Lo Swaga","Lo Swaga"),("//Long Way To Go","Long Way To Go"),("Tr-01 Like A Silence","Like A Silence"),("When The World Comes Tumbling Down","When The World Comes Tumbling Down (11:40)"),("Diggin' Up Bones","ENCORE: Diggin' Up Bones (6:54)"),("hurry up... and wait","Hurry Up... and Wait"),("uncle jr.","uncle jr"),("The Garden (Part I)","The Garden (Part II) >"),("In Memory Of Elizabeth Reed ^","Dark Star & -> In Memory of Elizabeth Reed Jam ->"),("02: Years With Rose","Years With Rose"),("2- Total Evaporation","Total Evaporation >"),("Six Days on the Road","6 Days"),("Lordy","Lordy, Lordy"),("Lordy, Lordy","Lordy, Lordy"),("Quantico, VA","Quantico, VA"),("Blues","44 Blues"),("44 Blues","44 Blues")]
for a,b in pairs:
    print(f"{a!r:45} {b!r:45} eq={fuzzy_title_eq(fuzzy_norm_title(a,{}), fuzzy_norm_title(b,{}))}  na={fuzzy_norm_title(a,{})!r}")
