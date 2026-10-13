set -x
cd /Users/shawn/projects/llama/.claude/worktrees/playout-phase2 || exit 9
python3 -m venv .venv
./.venv/bin/python -m pip install -q -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]" || { echo STEP-FAIL pip; exit 1; }
uv venv -q --python 3.11 .venv311 || { echo STEP-FAIL uvvenv; exit 1; }
uv pip install -q --python .venv311/bin/python -e "packages/transmitter[dev]" || { echo STEP-FAIL uvpip; exit 1; }
(cd antenna && npm ci) || { echo STEP-FAIL npmci; exit 1; }
grep -qx '.venv311/' "$(git rev-parse --git-common-dir)/info/exclude" || echo '.venv311/' >> "$(git rev-parse --git-common-dir)/info/exclude"
./.venv/bin/python -c "import transmitter, llama; print('PATH', transmitter.__file__, llama.__file__)"
./.venv311/bin/python -c "import transmitter, sys; print('PATH311', transmitter.__file__, sys.version)"
echo BEGIN-PYTEST; ./.venv/bin/python -m pytest -q 2>&1 | tail -5; echo "RC-PYTEST ${PIPESTATUS[0]}"
echo BEGIN-PY311; ./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q 2>&1 | tail -5; echo "RC-PY311 ${PIPESTATUS[0]}"
echo BEGIN-NPM; (cd antenna && npm test 2>&1 | tail -15; echo "RC-NPM ${PIPESTATUS[0]}"; npx tsc --noEmit 2>&1 | tail -5; echo "RC-TSC ${PIPESTATUS[0]}")
echo BEGIN-DEB12; bash packages/transmitter/scripts/test-in-debian12.sh 2>&1 | tail -6; echo "RC-DEB12 ${PIPESTATUS[0]}"
echo TASK0-END
