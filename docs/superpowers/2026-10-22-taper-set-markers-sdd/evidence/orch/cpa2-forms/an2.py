import json, re, collections, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
B, C = [], []
for r in rows:
    for h in r["hits"]:
        rec = dict(h, ident=r["ident"], fld=r["fld"], read=r["read"], asserts=r["head"][0],
                   reason=r["head"][1], lib=r["lib"], fam=r["fam"], creator=r["creator"])
        if "noB" in h["diff"]:
            B.append(rec)
        if "noC" in h["diff"]:
            C.append(rec)
print("B hit lines", len(B), "items", len({(x['ident'], x['fld']) for x in B}))
print("C hit lines", len(C), "items", len({(x['ident'], x['fld']) for x in C}))
# B: annotation shape
def annot(core):
    m = re.search(r"\(([^()]*)\)|(\.{2,}|…)", core)
    return m.group(0) if m else ""
print("\n== B: distinct cores by shape (digits->9)")
cnt = collections.Counter(re.sub(r"\d", "9", x["core"].strip()) for x in B)
for k, n in cnt.most_common():
    print(f"{n:5d} {k[:110]}")
print("\n== C: distinct cores by shape (digits->9)")
cnt = collections.Counter(re.sub(r"\d", "9", x["core"].strip()) for x in C)
for k, n in cnt.most_common():
    print(f"{n:5d} {k[:110]}")
