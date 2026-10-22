import json, sys, difflib, re, collections
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
pat = collections.Counter(); ex = {}
for k in sorted(set(a) & set(b)):
    ta = [t for t, _ in a[k]['items']]; tb = [t for t, _ in b[k]['items']]
    if ta == tb: continue
    sm = difflib.SequenceMatcher(a=ta, b=tb, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op != 'replace' or i2-i1 != j2-j1: continue
        for o, n in zip(ta[i1:i2], tb[j1:j2]):
            if o == n: continue
            if re.match(r'^\s*(s\d+t\d+\s*[:.\-]?\s*-?\s*|\d{1,3}:\s+)', o, re.I) and o.endswith(n.strip()):
                c = 'prefix stripped (sNtN/NN:)'
            elif n.endswith(o) and re.match(r'^\d{1,3}\s', n):
                c = 'number kept: ' + n
            else:
                c = f'OTHER {o!r} -> {n!r}'
            pat[c] += 1; ex.setdefault(c, k)
for c, v in sorted(pat.items(), key=lambda kv: -kv[1]):
    print(v, c, ex[c] if c.startswith('OTHER') or c.startswith('number') else '')
