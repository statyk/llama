#!/bin/bash
# usage: run.sh MUTANT
S=/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-taper-markers/0443a042-e8ee-4093-a603-2fbd14e62179/scratchpad/cpa3-rr1
PY=/Users/shawn/projects/llama/.claude/worktrees/taper-markers/.venv/bin/python
F=$S/copy/packages/llama/src/llama/taper.py
cp $F $S/taper.orig
$PY $S/mut.py $F $1
cd $S/copy
PYTHONPATH=$S/copy/packages/llama/src PYTHONPYCACHEPREFIX=$S/pyc-$1 PYTHONDONTWRITEBYTECODE=1 $PY -c "import llama, llama.taper; print('import:', llama.taper.__file__)"
PYTHONPATH=$S/copy/packages/llama/src PYTHONPYCACHEPREFIX=$S/pyc-$1 $PY -m pytest -q -p no:cacheprovider packages/llama/tests/test_taper.py 2>&1 | grep -E "FAILED|passed|failed|error" | sed 's/ - .*//' | tail -15
cp $S/taper.orig $F
