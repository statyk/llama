#!/bin/bash
SP=/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-held-backlog-tier1/14455d61-96ec-47d7-bf0b-86cfb6e7a6b5/scratchpad; H=$HOME/.llama-harness; W=/Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1; O=/Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1/orch-r4
for X in base cand; do T=$SP/fw6-$X
  (cd $T && PYTHONPATH=$T/packages/llama/src:$T/packages/herder/src PYTHONPYCACHEPREFIX=$SP/pyc-$X $W/.venv/bin/python -c "import llama; print('llama:', llama.__file__)" &&    PYTHONPATH=$T/packages/llama/src:$T/packages/herder/src PYTHONPYCACHEPREFIX=$SP/pyc-$X $W/.venv/bin/python scripts/replay_holds.py run --slugs $O/fw6-allslugs.txt --out $H/fw6-$X-all.json --scratch $SP/scratch-$X); echo "$X rc=$?"
done
cd $SP/fw6-cand && PYTHONPATH=$SP/fw6-cand/packages/llama/src:$SP/fw6-cand/packages/herder/src PYTHONPYCACHEPREFIX=$SP/pyc-cand $W/.venv/bin/python scripts/replay_holds.py compare $H/fw6-base-all.json $H/fw6-cand-all.json --no-repro-gate --out $H/cmp-fw6-all; echo "compare rc=$?"
