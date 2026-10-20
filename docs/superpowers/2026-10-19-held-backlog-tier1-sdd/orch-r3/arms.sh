#!/bin/bash
X=${1:?X}; W=/Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1
B=/Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1-base
P=/Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1-prev
H="$HOME/.llama-harness"; mkdir -p "$H"
echo "$(date +%T) start"
for T in "$B" "$P" "$W"; do (cd "$T" && ./.venv/bin/python -c "import llama; print('llama:', llama.__file__)"); done
(cd "$B" && ./.venv/bin/python scripts/replay_holds.py run --out "$H/$X-base-held.json" && ./.venv/bin/python scripts/replay_holds.py run --out "$H/$X-base-all.json" --all); echo "base rc=$?"
(cd "$P" && ./.venv/bin/python scripts/replay_holds.py run --out "$H/$X-prev-held.json" && ./.venv/bin/python scripts/replay_holds.py run --out "$H/$X-prev-all.json" --all); echo "prev rc=$?"
(cd "$W" && ./.venv/bin/python scripts/replay_holds.py run --out "$H/$X-cand-held.json" && ./.venv/bin/python scripts/replay_holds.py run --out "$H/$X-cand-all.json" --all); echo "cand rc=$?"
cd "$W"
./.venv/bin/python scripts/replay_holds.py compare "$H/$X-base-held.json" "$H/$X-cand-held.json" --out "$H/cmp-$X-held"; echo "cmp-held exit $?"
./.venv/bin/python scripts/replay_holds.py compare "$H/$X-prev-held.json" "$H/$X-cand-held.json" --no-repro-gate --out "$H/cmp-$X-slice-held"; echo "cmp-slice-held exit $?"
./.venv/bin/python scripts/replay_holds.py compare "$H/$X-base-all.json" "$H/$X-cand-all.json" --out "$H/cmp-$X-all"; echo "cmp-all exit $?"
./.venv/bin/python scripts/replay_holds.py compare "$H/$X-prev-all.json" "$H/$X-cand-all.json" --no-repro-gate --out "$H/cmp-$X-slice-all"; echo "cmp-slice-all exit $?"
echo "$(date +%T) end"
