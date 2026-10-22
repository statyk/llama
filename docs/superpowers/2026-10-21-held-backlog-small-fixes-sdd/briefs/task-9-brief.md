### Task 9: Acceptance measurement with the replay harness (reports only; nothing applied)

**Files:** none in the repo. Outputs go to `~/.llama-harness/small-fixes/`.

**Preconditions:** Tasks 1-8 are committed. `git -C "$W" status --porcelain` prints nothing (a `-dirty` identity makes the predicted lists unusable). The full suite is green. Ask the owner to hold off `llama get`/`fix`/`triage`/`run resume --all` on the library while both arms run, because a changed show makes `compare` exit 2.

- [ ] **Step 1: Base tree at the branch's fork point, with its own venv**

```bash
BASE_SHA=$(git -C "$W" merge-base HEAD main)
B=/Users/shawn/projects/llama/.claude/worktrees/held-backlog-small-fixes-base
git -C /Users/shawn/projects/llama worktree add --detach "$B" "$BASE_SHA"
cd "$B" && python3 -m venv .venv && ./.venv/bin/pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"
./.venv/bin/python -c "import llama; print(llama.__file__)"     # must be under $B
```

- [ ] **Step 2: Both arms, each with its own tree's interpreter (read-only on `~/.llama`; run in the background)**

```bash
H="$HOME/.llama-harness/small-fixes"; mkdir -p "$H"
(cd "$B" && ./.venv/bin/python scripts/replay_holds.py run --all --out "$H/base.json")
(cd "$W" && ./.venv/bin/python scripts/replay_holds.py run --all --out "$H/cand.json")
```
Expected: each prints `replayed N show(s): ...` with the same N.

- [ ] **Step 3: Compare with the candidate tree (it has `venue_changes.txt`)**

Run: `cd "$W" && ./.venv/bin/python scripts/replay_holds.py compare "$H/base.json" "$H/cand.json" --out "$H/cmp"; echo "exit $?"`
Expected: `exit 0`. On `exit 2` (the library changed between arms), re-run both arms in one sitting. On `exit 3` (the base does not reproduce), stop and report: that is harness drift, not this branch.

- [ ] **Step 4: Check against the spec's acceptance and record the numbers**

- B: `venue_changes.txt`. Record the count of shows. The order of magnitude is the spec's ~270 ties, fewer after the city gate and step 1's test. For every row marked `flags CHANGED`, read the flags added and removed. A venue or city flag is one starting `venue mismatch:` (emitted by 1a, the `two_venue_signature` arm and the chain's final `else`) or `recordings of this date disagree on city` (1d, `gather._CITY_CONFLICT_FLAG`). **Any added or removed venue or city flag is a defect: stop and report it.** Any other flag change on a venue-changed row is attributed (to slice D, or to none) and listed in the report, not a stop.
- D: `flags.txt` shows `added 0` for every family. `packaged_exposure.txt`'s "newly held" section is `(none)`. Record any title changes from D in `packaged_exposure.txt`/`title_sources.txt`. Few or none are expected.
- C: no harness effect is expected.
- `predicted_list.json`: record its row count. Near zero is expected, because B and D clear no holds by design.

- [ ] **Step 5: Report to the orchestrator (no library writes)**

Report the paths (`$H/base.json`, `$H/cand.json`, `$H/cmp/`), the text of `summary.txt`, and the numbers from Step 4. Then list what the owner should hand-check:
- every `venue_changes.txt` row whose two venue strings are not plain spelling variants of one place;
- every row marked `DELIVERED` (informational: delivered shows keep their spelling until something re-gathers them);
- every non-venue flag change on a venue-changed row, with its attribution;
- every D-driven title change.

State plainly that nothing was applied, and that the base worktree at `$B` is left for the owner to remove. Also state that **`predicted_list.json` is tied to this branch's sha**: `llama reapply --from-list` refuses a list whose `sha` differs from the installed code, so after merging the owner re-runs both arms from the merged tree before applying (spec "Apply" is the owner's call).
