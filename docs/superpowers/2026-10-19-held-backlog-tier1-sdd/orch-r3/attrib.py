import json,sys
L=lambda p:(lambda x:x if isinstance(x,dict) else {s['slug']:s for s in x})(json.load(open(p))['shows'])
X=sys.argv[1]
E,F,G=L(f'{X}/E2-cand-{sys.argv[2]}.json'),L(f'{X}/F-cand-{sys.argv[2]}.json'),L(f'{X}/F2-cand-{sys.argv[2]}.json')
diff=lambda a,b:[f for f in sorted(set(a)|set(b)) if a.get(f)!=b.get(f)]
FG=[k for k in G if diff(F[k],G[k])]; EG=[k for k in G if diff(E[k],G[k])]; EF=[k for k in G if diff(E[k],F[k])]
print('F!=F2',len(FG),' E2!=F2',len(EG),' E2!=F',len(EF))
print('-- F!=F2 and F2!=E2 (not a pure revert to E2):')
for k in FG:
    d=diff(E[k],G[k])
    if d: print(' ',k,'E2:',E[k]['outcome'],'F:',F[k]['outcome'],'F2:',G[k]['outcome'],'| F2 vs E2 fields',d)
print('-- E2!=F2 but not in E2!=F (new in F2):',[k for k in EG if k not in EF])
print('-- E2!=F2 and F==F2 (kept slice-5 effect):',len([k for k in EG if k not in FG]))
