### Finding Verdicts
- **F1 (per-show LLM-call baseline)**: ADDRESSED. `test_pace_loop.py` `test_a_mixed_run_records_only_the_show_that_called_the_llm[("a","b")]` catches M1 (`llm_calls() > 0`), because b would record a second boundary off a's calls. It also catches a baseline hoisted above the loop. The vacuous `pacing-state.json` asserts are removed, and `recorded == []` plus the read-count assert are kept. The implementer's M1 run (`2 == 1` on pids0 only) is consistent with the code at cli.py:632/646. One cosmetic nit: the docstring says a once-before-the-loop baseline "records nothing extra either way but is pinned by the reverse order". That is wrong: such a baseline records b too in (a,b), and the reverse order pins neither variant. pids0 is the one that matters.
- **F2(a) `auto` not true, any state**: ADDRESSED. sessions.py `sweep_verdict` reads the request once via `read_request` and checks `"auto" in req and req["auto"] is not True` regardless of marker. Cases paused-past-auto-false and incomplete-auto-false are tested.
- **F2(b) recording**: ADDRESSED. cli.py:865 `_get_query` writes `"human_gate": False` and cli.py:905 `_get_profile` writes `profile.human_gate`. Both are driven by the real-CLI tests in test_sessions.py. `_resume_locked` still passes `human_gate=False` (cli.py:1280), so there is no resume-behaviour change.
- **F2(b) recorded key / fallback / unloadable**: ADDRESSED for every run that has a request.json:
  - A recorded value is gated unless it is `False`.
  - For `mode: "profile"` without the key, `load_profile(run_dir.parent.parent, name)` is tried. The root is `config.root`, since `_sweep_runs` passes `config.root/"runs"/id`.
  - These all read as gated: missing file, bad TOML, schema failure (`ProfileError`), `OSError`/`ValueError` (UnicodeDecodeError included), and no or empty name.
  - Each case is tested in the incomplete and paused states.
  - Not covered: the no-request.json legacy run in concern (2) below, an Important gap against the ruling's intent.
- **F3 (malformed `updated_at`)**: ADDRESSED.
  - `sweep_verdict` returns `needs attention` when `fromisoformat` raises, after the running/awaiting checks. Every eligible run has therefore parsed, and `_instant` (cli.py:1327, which normalizes naive to UTC) cannot raise at the sort (cli.py:1298).
  - `_updated_at` now always returns a str, which also fixes `iter_sessions`' mixed-type sort crash.
  - The skip line is `skip <id>: needs attention`, and the sweep continues. Both are pinned by `test_a_malformed_updated_at_does_not_stop_the_sweep` for a str and an int.
- **F4 (spec/docs)**: ADDRESSED. Spec §6 has three dated operator-ruling bullets that match the code. The CLAUDE.md Commands bullet and README:151-158 state the new skips. Wording is accurate apart from the concern (2) gap, which the docs also do not mention.

### Implementer concerns (1)-(4): verdict each
1. **Any recorded `human_gate` other than `false` counts as gated, and the recorded value beats a since-edited profile**: ACCEPTABLE. This is the safe direction and mirrors the `auto is not True` rule. The writers only ever write a pydantic bool. Recorded-wins is the right reading: the request records what the run was started under.
2. **criteria.json but no request.json counts as not gated**: GAP AGAINST THE RULING'S INTENT (Important, strict surface: human decisions and LLM spend).
   - Such runs are identifiable. `_get_profile` has stamped `criteria.profile = name` since the 2026-07-27 UX redesign (plan-a-foundations:567/583). That predates profile request.json (2026-09-07), and `iter_sessions` already exposes it as `info.profile`.
   - Probe in a scratch root (worktree code, `llama.__file__` inside the worktree), with profile `weekly` saved with `human_gate=True` and runs holding `criteria.json{profile:"weekly"}` and no request.json:
     - no session.json: `sweep_verdict` → `None` (ELIGIBLE);
     - incomplete with a legacy `download of …` failure: `None` (ELIGIBLE).
   - The no-marker case is a live unattended-human-decision path. A gated `--auto` profile run killed before its gate has no approvals. The sweep resumes it with `auto=True, human_gate=False`, so `choose_entries(..., human_gate=False)` (pipeline.py:85-96) auto-picks the shortlist the profile required a human to approve, then spends on processing it.
   - The population is narrow: runs left in `runs/` since before 2026-09-07. The ruling says "any human-gated run", though, and the data to honour it is on disk.
   - Fix (one place): in `_human_gated`, when there is no `human_gate` key, take the profile name from the request when `mode == "profile"`, else from `info.profile` (criteria.profile; `None` for query runs). Then apply the same load-or-gated fallback. Add an eligibility case with criteria.profile and no request.json, gated, both with no marker and incomplete.
3. **`run list`'s `_humanize_age` still crashes on a malformed `updated_at`**: ACCEPTABLE as-is (outside the ruling, and not a regression). Before the fix, an int crashed `iter_sessions`' sort and a bad string crashed `_humanize_age`. Both are now one ValueError in `_humanize_age`, and the sweep never calls it. Worth a follow-up.
4. **CLAUDE.md "Five readers"**: ACCEPTABLE. The list is accurate: `run_resume`, `_interpret_with_pause`, `iter_sessions`, `_by_run_rollup`, `sweep_verdict`, and the three SWEEP readers do go through `read_request`. "Five readers, not three" reads oddly but is true. If concern (2) is fixed, the note should add that `sweep_verdict` also reads `criteria.profile`.

### New Breakage in the Fix Diff
- **Important**: sessions.py `_human_gated` / `sweep_verdict`. The legacy profile run without request.json is still swept despite a gated profile. Same as concern (2), confirmed by probe.
- **Minor**: test_pace_loop.py, the new test's docstring misdescribes which mutant the reverse order pins (see F1).
- Otherwise clean:
  - No reader breaks on an old run dir. `read_request` stays permissive, and a missing `human_gate` or `mode` is tolerated.
  - The `sessions → profiles` import adds no cycle (profiles imports only errors/models/workspace).
  - The profile loader uses the run's own root: tests use `tmp_path`, never `~/.llama`.
  - The skip line is correct.
  - The sort is unreachable by a bad timestamp.

### Out-of-Scope Observations
- Behaviour the ruling chose, flagged so the operator knows: a gated profile run that a human has ALREADY approved, and that then lost shows to download/archive failures, is now never swept. `choose_entries` would just return the approved picks, so no new decision would be made, yet the sweep skips it. Such runs need a manual `run resume <id>`. This is the "any human-gated run" rule as given, not a defect.
- A gated or interactive paused run whose reset is still in the future now prints `needs attention` instead of `paused until HH:MM`. That is consistent with the ruling, and only the display changes.
- Concern (3) (`_humanize_age`) is worth fixing alongside, as the final reviewer suggested.

### Verdict
**Fix round:** Findings remain open. F2(b) is incomplete against the ruling's intent: a pre-2026-09-07 profile run with no request.json whose criteria names a human-gated profile is still eligible, and with no marker the sweep auto-picks its shortlist. The fix is to fall back to `criteria.profile` (concern 2). F1, F2(a), F3 and F4 are addressed. There is no other Critical/Important breakage.
