import sys, pathlib
src = pathlib.Path(sys.argv[1]); name = sys.argv[2]
t = src.read_text(); orig = t
def rep(a, b, count=1):
    global t
    assert t.count(a) == count, (name, a, t.count(a)); t = t.replace(a, b)
if name == "M1":
    rep("_CONT_AFTER.match(item.title[m.end():]):\n                continue", "_CONT_AFTER.match(item.title[m.end():]):\n                break")
elif name == "M2":
    rep("_CONT_AFTER.match(", "_CONT_AFTER.search(")
elif name == "M2b":  # old ^ restored + search: should be equivalent (survive)
    rep('_CONT_AFTER = re.compile(r"\\s*', '_CONT_AFTER = re.compile(r"^\\s*'); rep("_CONT_AFTER.match(", "_CONT_AFTER.search(")
elif name == "M2c":  # old ^ restored, .match kept: no behaviour change
    rep('_CONT_AFTER = re.compile(r"\\s*', '_CONT_AFTER = re.compile(r"^\\s*')
elif name == "M6":
    rep('        if item.set == "encore":\n            continue\n        if item.title.strip', '        if item.set in ("encore", "3"):\n            continue\n        if item.title.strip')
elif name == "F1":
    rep('        if item.title.strip(_ITEM_DECOR).lower() == "set":\n            return True\n', '')
elif name == "SENT":
    rep("def _set_like(items: tuple[TaperItem, ...]) -> bool:\n", "def _set_like(items: tuple[TaperItem, ...]) -> bool:\n    raise RuntimeError('SENTINEL-COPY')\n")
elif name == "U":
    pass
src.write_text(t)
print(name, "applied", t != orig)
