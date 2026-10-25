### Spec Compliance

- ✅ Spec compliant (Task 17 scope: checks, process check, dry run; spec 4.3 opening, "Checks", "Routes with no CLI form", "The process check", "Output"; 6(f) refusals).
  - Contract names and signatures match the brief: `REKEY_MIN_VERSION="2.18.0"`, `SNAPSHOT_PREFIX`, `APPLIED`, `LOCK` (scripts/rekey_overrides.py:45-48), `Refusal`/`Rekey` frozen dataclasses (:86-100), `check_show(ws, ia, want, *, overrides_bytes, show_bytes)` (:115), `check_library` (:286), `llama_processes(ps_lines, *, self_pid)` (:383).
  - Check order: `unreadable` (invalid JSON, non-object, or new `Overrides` raises) and `mixed` stop (:136-152); every other check runs and each failure is reported (:175-273). Pinned by `test_unreadable_and_mixed_stop_further_checks`, `test_every_other_failure_is_reported`.
  - `duplicate key` on equal `legacy_int` (:175-182), so "7"/"07" is caught (carried decision; `test_duplicate_key_seven_and_oh_seven`).
  - `structure out of range` uses gather's own `_validate_structure_override`, imported (:42, :232); structure checks gated on `set_breaks is not None or encore_after is not None` (:157, :228), `set_breaks: []` counts as present (`test_structure_checks_only_when_a_structure_key_is_present`).
  - `kept list differs` uses `final_kept(md["files"], ov, want, short_keep=False).kept` as a list (ordered) compare, plus `CacheMiss` (:253-266). Checked `final_kept` (gather.py:1046) and `title_inputs` (gather.py:1120-1170): show.json's tracks are `fk.kept`, the same object, so the comparison is the right one.
  - REASONS (:59-80) checked against the spec 4.3 table row by row: verbatim except "(below)" spelled out as `HAND_EDIT_ROUTE` — acceptable.
  - No-CLI-form routes: key <= -1 (:206-212), duplicate key, and a redo route without provenance.json (:161-166). Checked that `redo` really needs provenance.json (cli.py:2752-2755 raises without it). Checked v2.17.0's `--clear-title` (e37f670 cli.py:3057-3062, 1420-1421): `isdigit` then `pop(int)`, so `--clear-title 0` / `--clear-title 9` are real routes for in-CLI keys, and -1 really has no CLI form.
  - Dry run takes no lock and creates no file: the code path has no open-for-write, no mkdir, no lock (`load_config`, `CacheOnlyIA.metadata` replay.py:48-53, `ShowWorkspace.__init__` all read-only). Pinned by `test_dry_run_writes_nothing` (names, bytes, mtimes, dir mtimes, read-only tree, no `.lock`/`.rekey.lock`).
  - Output lines and summary match the contract (:442-475); exit 1 on any refusal or a failed ps (:476).
- ⚠️ Cannot verify from diff: `--snapshot`/`--apply`/`--restore`, `llama_versions`, `version_ok`, `find_snapshot`, `verify_snapshot` are Tasks 18-20 (none here, correctly). Their gate depends on `check_show`'s bytes-argument path, which is tested here (`test_check_show_judges_the_bytes_it_is_given`). The controller should confirm Task 19 passes both `overrides_bytes` and `show_bytes` re-read under the show lock.

**Live evidence (read-only, permitted by Global Constraints):** I ran `PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python scripts/rekey_overrides.py` against the operator's library. Result: rc 0, 1.3 s, `606 to rekey, 0 refused, 0 already migrated, 3377 without positional keys`, `llama processes running: none`. The per-line counts sum to **3203 titles / 427 breaks / 365 encore**, exactly the spec's "Measured today". `find ~/.llama -newer <log>` before and after found no file written. Output: /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-junk-filter/69caf142-5722-4b95-bb74-74745518bd97/scratchpad/dryrun.out

**The process-check widening (brief focus): correct, and necessary. Every brief must-not-match still does not match.**
- Measured on this Mac. A shebang'd script named `llama` whose shebang is the venv python appears in `ps -axo pid=,ppid=,command=` as `/opt/homebrew/Cellar/python@3.14/.../MacOS/Python /…/fakebin/llama get q`. `python -c … -m llama` appears as `.../MacOS/Python -c … -m llama`. The script flagged both.
- The brief's rule as written (case-sensitive `python` prefix, a `llama` first word, `.py` scripts only) misses both, so it would miss every venv `llama` and every `python -m llama` on this Mac.
- On Linux too, a shebang console script shows as `<python> <path>/llama`. So the "first non-option argument's basename is `llama`" clause (scripts/rekey_overrides.py:367-371) is what catches a venv `llama` anywhere, not a Mac quirk.
- Both widenings only add refusals. `test_process_check_matches` asserts the exact matched list (`got == match`), with every brief must-not-match present:
  - the script's own pid 500;
  - the same command under pid 701;
  - the wrapper zsh as parent (400) and as an unrelated pid (702);
  - an ancestor llama (300);
  - vim, `-zsh` and `python -m pytest`;
  - plus `MAC_PY scripts/rekey_overrides.py` (703) and `MAC_PY …/pytest` (707).
- Against the live process table (560 lines) the script found no match, and none was expected. The only line containing "llama" was an esbuild under `antenna/node_modules`, and it was correctly not matched. ps on macOS does not truncate when its output is not a terminal (longest line was 9221 characters).

### Strengths
- Errors only ever turn into refusals, never into a pass:
  - an unreadable `overrides.json` (any exception) becomes `unreadable` (:141-147);
  - an unreadable `show.json` becomes a `no show.json` refusal (:193-195);
  - any exception while computing the kept list becomes `kept list differs` (:261-263).
  On a strict surface that is the right direction.
- The redo-cannot-run route (no provenance.json) is a real spec clause that is easy to miss. It is implemented and tested (`test_a_redo_route_that_cannot_run_names_the_hand_edit`).
- Fixtures come from real gathers (`library_show`) with the overrides rewritten into the v2.17.0 form, so `title not applied` and `structure not applied` are judged against a real `show.json`, not hand-made data.
- The implementer's mutation evidence (M1-M7) covers the carried decisions (`short_keep=False`, duplicate key, the ancestor walk, structure gating).

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **The strict-surface ordering invariant of `kept list differs` is unpinned.** scripts/rekey_overrides.py:265 compares lists (`if kept != names`), which is correct. But mutant Mb, `set(kept) != set(names)`, survives the whole test file (28 passed; I predicted it would survive before running it, in a scratch copy with shadowing proven by `llama.__file__`).
   - Why it matters: `--apply` maps N to `show.json`'s `tracks[N-1].filename`. That mapping is correct only if `show.json`'s order is gather's play order.
   - For a titles-only show, the per-key `title not applied` check pins only the keyed positions. A swap elsewhere would pass a set comparison.
   - For breaks and the encore, nothing else pins the position.
   - Any future refactor to a set comparison (or a sorted one) would silently let `--apply` point a break or encore at the wrong file, and no test would fail.
   - Fix: in `test_kept_list_uses_todays_rule` or a sibling test, swap two `tracks[].filename` values in `show.json`, with the same multiset and a breaks/encore key present, and assert `kept list differs`.

#### Minor (Nice to Have)
1. **`title_source == "override"` clause unpinned.** Mutant Ma, which drops `t.title_source != "override" or` at :222, survives. Every `title not applied` fixture also has a mismatched title. Fix: add a case where the track's title equals the forced title but `title_source` is `tags`.
2. **Unpinned: a key of -1 or below on a show with no `show.json`.** Mutant Mc, which sets `negative = []` at :199, survives. Add `{"titles": {"-1": "X"}}` with show.json removed, and assert both `no show.json` and the hand-edit `title out of range`.
3. **The `title out of range` detail shows only raw keys** (:208-212). For `"7_0"` (reads as 70) or `"+9"`, the operator copies the key into v2.17.0's `--clear-title`, which rejects it (`isdigit`, e37f670 cli.py:3059). Fix: add the parsed number, as `duplicate key` already does ("all read as N").
4. **Routes keep the `<show>` placeholder** (:57, :66-78): `repair: \`llama redo <show> --from gather\``. Substituting the slug when printing (`_print_refusal`, :442) would keep `route == REASONS[reason]` in the dataclass and give the operator a pasteable command. The implementer asked about this (Concern 3); the controller's call.
5. **Spec-level gap, flagged by the implementer (Concern 2), confirmed by reading the code.** The documented operator loop (CLAUDE.md: `while true; do llama run resume --all; sleep 600; done`) typed at an interactive prompt runs inside `-zsh`, with no `-c` and no llama child during `sleep 600`. The check is blind to it most of the time. Wrappers inside a `-c` string are also unmatched (`caffeinate -i llama`, `nohup`, `env`, `time`, `sudo`, `exec`), as are `&` as a separator, `if`/`while` heads and `python -W x scripts/…`. All of these follow the brief's drop set, not a deviation.
   - Effect: a loop that wakes mid-`--apply` runs the new binary. Its resolver refuses legacy files, and the show lock serializes against apply, so this is noise and needs-attention runs, not wrong audio.
   - Recommend: one line in the runbook/dry-run output that the check cannot see an interactive loop, so step 1 stays a manual confirmation.
6. **Duplicated code.**
   - `_check_identity` (:415-425) is a verbatim copy of `replay_holds._check_identity` (scripts/replay_holds.py:58-67). Acceptable for a standalone one-off, but name the source in its docstring (it does) and keep the two in step.
   - The `first = str(exc)...` one-liner appears twice (:146, :194). A tiny helper would do.
7. **An unreadable `show.json` is reported as `no show.json`** (:193-195), detail `show.json unreadable: …`. Reasonable (the table has no row for it, and the route is the right repair). Noting it for the controller's ack (Concern 4).

### Checks I ran
- One named risk per item:
  - kept-list inputs vs gather (gather.py:1046-1083, 1120-1170);
  - redo's provenance prerequisite (cli.py:2752);
  - v2.17.0's `--clear-title` parsing (e37f670 cli.py:3057-3062);
  - dry-run write paths (config.py, replay.py:41-62, workspace.py:71-74);
  - `short_keep=False` reproducing the pre-piece-4 filter (junk.py:284-286, 419-426).
- Live read-only dry run (above): 606/0/0/3377, totals 3203/427/365, nothing written.
- Live ps probe with a shebang'd `llama` and `python … -m llama` (above): both matched, nothing false.
- Mutants Ma, Mb and Mc in a `git archive 368ccda` scratch copy (/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-junk-filter/69caf142-5722-4b95-bb74-74745518bd97/scratchpad/mut/), run with `.venv/bin/python -m pytest -p no:cacheprovider`, `PYTHONPATH` shadowing, `PYTHONDONTWRITEBYTECODE=1`, and each copy's `llama.__file__` asserted inside it. All three survived, as predicted.
- Test noise: the full suite's `26 warnings` matches every earlier task's baseline in this run (4844 through 5275 passed, all with 26 warnings), so nothing new. The new file reported `28 passed` with no warnings.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The checks, the routes and the read-only dry run are correct. On the live library they reproduce the spec's 606/0 measurement and its 3203/427/365 totals exactly, and the process-check widening is necessary and safe. The one Important item is a missing test that pins the ordered kept-list comparison: mapping N to `tracks[N-1].filename` depends on that order, and a set comparison would pass every current test. Adding it is one small test; the Minor items are optional.
