# usage: setflight.py STATE.md [task agentId]...   (no pairs => in-flight: [])
import sys,re,subprocess
p=sys.argv[1]; pairs=sys.argv[2:]
s=open(p).read()
now=subprocess.check_output(['date','+%Y-%m-%dT%H:%M:%S%z']).decode().strip()
s=re.sub(r'^updated:.*$', 'updated:  '+now, s, flags=re.M)
s=re.sub(r'^idle-ticks:.*$', 'idle-ticks: 0', s, flags=re.M)
if pairs:
    blk='in-flight:\n'+''.join(f'  - task: {pairs[i]}\n    agentId: {pairs[i+1]}\n    dispatched: {now}\n' for i in range(0,len(pairs),2))
else:
    blk='in-flight: []\n'
s=re.sub(r'in-flight:( \[\])?\n(  .*\n)*', blk, s)
open(p,'w').write(s)
