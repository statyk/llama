# usage: python3 setflight.py <STATE.md> [task agentId]...   (replaces the in-flight list; no args = empty)
import re,subprocess,sys
p=sys.argv[1]; s=open(p).read(); a=sys.argv[2:]
d=subprocess.check_output(['date','+%Y-%m-%dT%H:%M:%S%z']).decode().strip()
s=re.sub(r'^updated:.*$',f'updated:  {d}',s,flags=re.M)
s=re.sub(r'^idle-ticks:.*$','idle-ticks: 0',s,flags=re.M)
body=''.join(f'\n  - task: {a[i]}\n    agentId: {a[i+1]}\n    dispatched: {d}' for i in range(0,len(a),2))
s=re.sub(r'^in-flight:.*?(?=\n\n)', 'in-flight:'+(body or ' []'), s, flags=re.M|re.S)
open(p,'w').write(s)
