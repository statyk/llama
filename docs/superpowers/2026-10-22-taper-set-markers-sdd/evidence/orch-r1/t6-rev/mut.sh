#!/bin/bash
# usage: mut.sh NAME 'replacement'
S=/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-taper-markers/0443a042-e8ee-4093-a603-2fbd14e62179/scratchpad/t6-rev
PY=/Users/shawn/projects/llama/.claude/worktrees/taper-markers/.venv/bin/python
N=$1; R=$2
rm -rf $S/m_$N; cp -R $S/base $S/m_$N
$PY - "$S/m_$N/packages/llama/src/llama/replay.py" "$R" <<'PYEOF'
import sys
p, r = sys.argv[1], sys.argv[2]
s = open(p).read()
old = "\n            and not gathered.taper_owned):"
assert s.count(old) == 1
s = s.replace(old, r)
open(p, "w").write(s)
PYEOF
cd $S
export PYTHONPATH=$S/m_$N/packages/llama/src:$S/m_$N/packages/herder/src:$S/m_$N/packages/llama/tests
export PYTHONPYCACHEPREFIX=$S/pyc_$N
$PY -c "import llama.replay as r, inspect; src=inspect.getsource(r.compute_legs); print('FILE', r.__file__); print([l for l in src.splitlines() if 'stored alignment llm' in l or 'alignment == \"llm\"' in l or 'gathered.' in l and 'and' in l])"
$PY -m pytest -q -p no:cacheprovider --rootdir=$S/m_$N $S/m_$N/packages/llama/tests/test_replay.py $S/m_$N/packages/llama/tests/test_reapply.py 2>&1 | grep -E "FAILED|passed|failed|error" | sed 's/ - .*//'
