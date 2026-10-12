#!/usr/bin/env python3
# usage: state.py STATE.md add <task> <agentId> | rm <task> | touch
import sys, re, subprocess

p, op = sys.argv[1], sys.argv[2]
D = p.rsplit('/', 1)[0]
s = open(p).read()
now = subprocess.check_output(["date", "+%Y-%m-%dT%H:%M:%S%z"]).decode().strip()
s = re.sub(r'^updated:.*$', 'updated:  ' + now, s, flags=re.M)
if op != 'touch':
    task = sys.argv[3]
    m = re.search(r'^probe-dirs: \[(.*)\]$', s, flags=re.M)
    dirs = [x.strip() for x in m.group(1).split(',') if x.strip()]
    blk = re.search(r'^in-flight:\n((?:  .*\n)*)', s, flags=re.M)
    entries = re.findall(r'  - task: (\S+)\n    agentId: (\S+)\n    dispatched: (\S+)\n', blk.group(1))
    if op == 'add':
        entries.append((task, sys.argv[4], now))
        dirs.append(f"{D}/{task}")
    else:
        entries = [e for e in entries if e[0] != task]
        dirs = [d for d in dirs if d != f"{D}/{task}"]
    body = ''.join(f"  - task: {t}\n    agentId: {a}\n    dispatched: {d}\n" for t, a, d in entries)
    # replace in-flight body first (later in file), then probe-dirs
    s = s[:blk.start(1)] + body + s[blk.end(1):]
    m = re.search(r'^probe-dirs: \[(.*)\]$', s, flags=re.M)
    s = s[:m.start(1)] + ' ' + ', '.join(dirs) + ' ' + s[m.end(1):]
    print("in-flight:", [e[0] for e in entries])
open(p, 'w').write(s)
