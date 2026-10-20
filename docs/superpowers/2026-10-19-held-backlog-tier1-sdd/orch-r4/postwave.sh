#!/bin/bash
# usage: postwave.sh N — scoped harness re-check + per-show check for wave N (read-only)
N=${1:?N}; W=/Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1; O=$W/.superpowers/sdd/tier1/orch-r4; H=$HOME/.llama-harness
echo "$(date +%T) postwave $N start"
cd "$W" && ./.venv/bin/python -c "import llama; print('llama:', llama.__file__)"
./.venv/bin/python scripts/replay_holds.py run --slugs "$O/w$N-slugs.txt" --out "$H/wave$N-after.json"; echo "replay rc=$?"
python3 "$O/wavecheck.py" "$H/cmp-G2-held/wave$N.json" "$O/wave$N.log" "$H/wave$N-after.json" "$O/w$N-marker" "$O/w$N-llmfail-before.txt" "$O/w$N-shows-before.txt" > "$O/wave$N-table.txt" 2>&1; echo "check rc=$?"
tail -6 "$O/wave$N-table.txt"
echo "$(date +%T) postwave $N end"
