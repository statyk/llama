import json, sys, difflib, re, collections, random
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
only_asserting = len(sys.argv) > 3 and sys.argv[3] == 'asserting'
kinds = collections.Counter(); samples = collections.defaultdict(list)
for k in sorted(set(a) & set(b)):
    if only_asserting and not (a[k]['asserts'] or b[k]['asserts']):
        continue
    ta = [t for t, _ in a[k]['items']]; tb = [t for t, _ in b[k]['items']]
    if ta == tb: continue
    sm = difflib.SequenceMatcher(a=ta, b=tb, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal': continue
        o, n = ta[i1:i2], tb[j1:j2]
        if op == 'delete':
            kind = 'dropped'
        elif op == 'insert':
            kind = 'added'
        elif len(o) > len(n):
            kind = 'merged'
        elif len(o) < len(n):
            kind = 'split'
        else:
            kind = 'renamed'
        kinds[kind] += 1
        samples[kind].append((k, o, n))
print(kinds)
random.seed(1)
for kind, ss in samples.items():
    print('=====', kind, len(ss))
    for s in (ss if len(ss) <= int(sys.argv[4] if len(sys.argv)>4 else 40) else random.sample(ss, int(sys.argv[4] if len(sys.argv)>4 else 40))):
        print('  ', s)
