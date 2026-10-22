import json, sys
def match(pat, f):
    return f.startswith(pat[:-3] + "[") if pat.endswith("[*]") else f == pat
for l in open(sys.argv[1]):
    r = json.loads(l)
    core = r["predicted"]
    hit = {p: [f for f in r["fails"] if match(p, f)] for p in core}
    extras = [f for f in r["fails"] if not any(match(p, f) for p in core)]
    missing = [p for p, fs in hit.items() if not fs]
    if r["hang"]: v = "HANG"
    elif not r["fails"]: v = "SURVIVED"
    elif not missing and not extras: v = "CAUGHT-AS-PREDICTED"
    elif not missing: v = "CAUGHT+EXTRAS(check vs declared possible)"
    else: v = "SURPRISE?(core missing)"
    print(f"{r['id']:4} {v:42} line={r['line']} {r['summary']}")
    print("      diff:", r["diff"])
    for p in missing: print("      CORE-GREEN:", p)
    for f in extras: print("      EXTRA:", f)
