# usage: setflight.py STATE.md [task=agentId ...]   (no pairs = empty in-flight)
import sys,re,subprocess
p=sys.argv[1]; now=subprocess.check_output(['date','+%Y-%m-%dT%H:%M:%S%z']).decode().strip()
s=open(p).read()
s=re.sub(r'^updated:.*$', f'updated:  {now}', s, flags=re.M)
s=re.sub(r'^idle-ticks:.*$', 'idle-ticks: 0', s, flags=re.M)
pairs=[a.split('=',1) for a in sys.argv[2:]]
block='in-flight: []\n' if not pairs else 'in-flight:\n'+''.join(f'  - task: {t}\n    agentId: {a}\n    dispatched: {now}\n' for t,a in pairs)
s=re.sub(r'^in-flight:.*\n((  - |    ).*\n)*', block, s, flags=re.M)
open(p,'w').write(s); print(block, end='')
