**Verdict: Needs fixes.** Two Important findings: I1 affects the confirmation surface and I2 is a spend loop. Both are small fixes. Nothing is Critical. After I1 and I2 are fixed: Ready to merge pending pilot.

Method: one pass by me, no subagents. I read the strict surfaces in full at e32b405f: gate.py, apply.py, runner.py, record.py, report.py, the cli.py hooks, adjudicate, triage [a], fix --recording, select_recording, override_keys, ledger, staleness, config, and scripts/adjudicate_pilot.py `run`. I read tests only where noted. The suite was not re-run. One scratch check ran from an empty scratchpad cwd (I1).

### Strengths
- gate.py:26-30: the constants are exact, and every bar reads them. gate.py:277 makes the boundary inclusive (`>` SHORT_EDIT_MAX_S / VERDICT_SUM_MAX_S). gate.py:240 treats an unknown duration as inf.
- gate.py:163-225: target validation matches filenames exactly and case-sensitively. It covers a conflict on one file, more than one structure or switch edit, a flag judged twice, and an unknown flag. evaluate() re-runs it fail-closed (gate.py:462).
- gate.py:93-102: stem_in is a whole token, Unicode-aware, and a stem with no letters never counts. This matches the operator ruling.
- apply.py:426-544: there is one unit. A switch alongside any non-venue edit is refused before any write (apply.py:441-449). Coverage, whole-show and silenced-flag checks all raise `_Restore` inside the unit. Re-hold is all-or-nothing (apply.py:337-361). RateLimited and ShowChanged propagate after the restore (apply.py:497).
- apply.py:366-408 and ledger.py remove_added/has_row: the ledger undo runs under the show lock, compared parsed and append-once. Lock order is show ⊃ ledger.
- record.py:98-107: the proposal write is under file_lock, after the unit, and compare-before-write. The digest excludes research, briefing and overrule `at` (record.py:48-67).
- runner.py:228-264: no-op checks come before any spend. RateLimited is re-raised at every arm (runner.py:256, 279, 307, 436). accept refuses a record other than the one shown (`expected_at`, runner.py:396).
- Invariants. llama/adjudicator/* imports no llama.cli, emcee, transmitter, deliver or station-write code (grep; it imports only the `StationUnreadable` exception class, apply.py:41). The apply's redo is `_redo_show_locked` (cli.py:3237): no delivery, no clear-mark, no voicing, and it reads the station only for strict reuse. The pipeline hook runs after the show lock is released in every caller (cli.py:699, 755, 4205-4216, 4327-4333; triage [a] cli.py:2276, outside the `show_unit` at cli.py:2307). There is no re-entered flock on the new paths. Run lock ⊃ show (`_execute` is under the run lock) ⊃ ledger.
- Propose-only ops: verdict.py:123 types them separately. `_applicable` drops them in apply (apply.py:89) and in runner (runner.py:154). accept never applies them.
- Pacing. `_adjudicate_after` gates every pipeline call (cli.py:4791-4795). The backlog loop gates per show (cli.py:4919-4924). Under --no-pacing, RateLimited becomes `unjudged` (cli.py:4799-4801). The pilot has its own fail-closed ceiling (adjudicate_pilot.py:248-258).
- Docs: packages/llama/CLAUDE.md `## Adjudicator`, the scripts/CLAUDE.md pilot section and the root CLAUDE.md row all match the code: hook points, flags, constants, the rollout caveat, `--stop-at-5h/--stop-at-7d` defaults of 85/80, and exit codes 2/3.

### Issues

#### Critical
None.

#### Important

**I1. Triage `[a]` and `adjudicate --accept` show a set_title without its title: the operator accepts a title he cannot see.**
- File: packages/llama/src/llama/adjudicator/report.py:33-42 (`_target`), used at report.py:72.
- What: `_target` returns the first attribute it finds among `file`, `identifier`, `flag`, `venue`, `city`. A `SetTitle` has `file`, so the line reads `edit 2: set_title gd73d1t04.mp3 [title: ...]` and `e.title` is never printed. I checked this in the scratch interpreter: `report._target(SetTitle(file='gd73d1t04.mp3', title='Bertha', ...))` returns `'gd73d1t04.mp3'`.
- Why: the spec ("Proposals in triage") says each edit is printed with its evidence. Titles are the near-strict surface. The orchestrator's "shown == accepted" ruling (orch-r1 ledger:62) assumes the operator saw the edit. Proposals on the title bar that fail the quote rule, and every propose-only title from setlist.fm, JerryBase or reviews, are exactly the ones where the quote may not contain the title.
- Fix: render `set_title <file> -> "<title>"`. Consider adding the length for include/exclude, which the bundle has, and the edit's `why`. Add a test in test_adjudicator_report.py that asserts the title text appears.

**I2. A failed or transient adjudication writes no record, so `run resume --all` re-pays the LLM call on every pass.**
- Files: runner.py:254-264 (FAILED / llm_failure, no record), runner.py:311-312 (apply exception), runner.py:325 (UNJUDGED transient). cli.py:699 and 755 adjudicate every held show `_process` returns, and `process_show` returns None for an already-held show on every resume (pipeline.py:158-175).
- What: the loop guard is `record.is_current` (cli.py:4789). Outcomes that make no record are never current. In an incomplete run that the operator's `while true; llama run resume --all; sleep 600` loop keeps resuming, each pass re-judges such a show with a fresh tier-high call. Two things keep a run incomplete: download failures, which the docs say can persist "until cleared by hand", and a `download`/`archive` failure in any other show of the run. Examples of failing shows: a bundle the provider rejects because it is oversized (ruled possible, orch ledger:72), a ProposeOnly with a bad evidence kind that fails schema validation every retry (deferred Task 4 minor), or an apply redo that fails the same download each time (UNJUDGED).
- Why: the spec's anti-goal is "Loops: an adjudicated show re-adjudicated ... by every later redo, with no new evidence". The spec lets a transient be re-judged "next run", but it does not foresee a 10-minute unattended sweep. The pacing gate limits how fast the window burns, not how much is spent.
- Fix (smallest): record the failure. After an LLM call that produced no record, write a minimal `failed` marker under the show lock (or a sidecar), keyed by the view digest. Have `_adjudicate_after` skip it for the pipeline hooks until the digest moves; `llama adjudicate` and `--force` would still retry. A cheaper alternative: skip adjudication inside `_sweep_runs` for shows that were already held when the pass started. Either one needs a test that resumes twice and counts provider calls.

#### Minor
- **M1.** cli.py:4930-4946: in `adjudicate --accept`, when `acceptable(stored)` is False, `accept_proposal(ctx, entry, expected_at=None)` still runs with nothing shown. Today it always returns stale or no-proposal, because the predicates agree. If a concurrent `llama adjudicate` writes a new acceptable record between the two reads, it is applied unseen, even without `--yes`. Fix: return the stale or no-proposal outcome directly when not acceptable, or pass a sentinel `expected_at` that never matches.
- **M2.** runner.py:442-446: `accept_proposal`'s ShowOutcome never sets `fixed_eligible`. An accepted marked, processed, delivered show is therefore listed under `llama deliver <slug>` rather than `deliver --fixed` (report.py:126-134). The command still works, but it is inconsistent with the auto path (runner.py:320).
- **M3.** bundle.py:172-174: `build_bundle` captures `view`, then re-reads `show.json` and `overrides.json` from disk instead of parsing the view's bytes. A change in between makes `bundle.show` newer than `expect`. This is the safe direction (the apply raises ShowChanged and the proposal write returns CHANGED), but parsing from `view` closes the gap.
- **M4.** report.py:59-61: a held_proposal's edit lines carry no confidence or why, while the proposal form shows the gate reason. This is cosmetic, with the same fix site as I1.

### Deferred minors triage ($W/deferred-minors.md)

| Item | Call | Why |
|---|---|---|
| T8 cli --accept reads the record without the sink | defer | the CLI never sets sink; only the pilot does, and it never accepts |
| T8 render_proposal `show` param unused | defer | cosmetic; touch it with I1 |
| T9 conftest raising=False | defer | covered by test_config_default_enables_hook |
| T9 cli.py:704 `ran` redundant / no boundary on a deferred-pass gate pause | defer | the boundary is deliberately not measured on the blocking pass |
| T10 acceptable_state re-reads disk | defer | expected_at plus the digest check in accept_proposal guard the apply |
| T10 `acceptable` closes over loop `entry` | defer | called in the same iteration; harmless (M1 touches the same lines) |
| T11b R2 double fault unpinned | defer | needs ShowChanged and a Ctrl-C in the same sub-ms window |
| T11b interrupted log.warning replaces original | defer | theoretical |
| T1 blank lines / substring template test / docstring test | defer | cosmetic; plan-mandated |
| T2 lineage_table `or` on an empty era dict | defer | falls back to the global table, which is the sensible default |
| T2 pin accepted with kept_tracks == 0 | defer | gather fails, the unit restores; operator-only path |
| T2 missing --clear-include combo tests; >100-col line; import order; truthiness guard; include-printed-once test | defer | coverage or style only |
| T3 setlistfm dumps every cached setlist | defer | weak, propose-only evidence |
| T3 SETLISTFM_CAP / NUL strip / length_of one-side-unknown untested / re-read per cap loop / vacuous assert / `_secs` exponent / long f-strings | defer | builder's call, perf or style; unreachable |
| T3 `_read_text` FileNotFoundError only | defer | fails at the bundle, before any spend, so it cannot feed I2 |
| T3 sibling ia.metadata writes the cache / network | defer | cache, outside show dirs; ruled |
| T4 ProposeOnly with an invalid evidence kind fails the whole verdict | defer, but fold into I2 | each retry costs an LLM call and leaves no record; I2's marker bounds it |
| T4 encore-not-in-breaks schema extra; adjudicate.md long line | defer | consistent with the gate |
| T5 structure edit from setlistfm at medium labelled `structure` | defer | the outcome is the same; accept is op-based |
| T5 inline literals; normalize without NFC; fail-closed test prefix only; veto-pass case covers include only | defer | each fails closed or is test breadth |
| T5 quote_ok `"\n".join` stitches two rows | defer | plan-mandated; it does not reach the long or title anchors (`quote_rows` is per row) |
| T5 F3 same-stem compare is case-sensitive (fail-open) | **fix before the full sweep (cheap)** | gate.py:255: a derivative with no recorded `original`, whose flac row differs only in case, lets the file's OWN tag row satisfy the long bar. That bar is strict (> 60 s track-list edits). `.casefold()` on both stems is a one-line change; it can ride with I1/I2, but it does not block the pilot |
| T6 !r quoting; n_res tuple; no switch+city / switch+overrule test | defer | apply.py:441-449 refuses any non-venue edit generically |
| T7 `_accept_pairs` keys vs pre | defer | affects only `applied[].index` bookkeeping, not what is applied |
| T7 M1 bare except; ApplyCalled naming | defer | no RateLimited can arise at steps 1-2 |

### Flagged rulings
I believe none of the rulings is wrong. Two need the operator's attention at the pilot:
- orch ledger:100 (partial-tape clearance needs an overrule per holding flag; never-bar flags hold). This follows the spec tables. The spec puts `low-confidence-setlist` and `tape-spans` on never, and partial tapes often carry the low-confidence flag. So the operator's "partial tape airs by default" ruling may clear few shows in practice. compare.md's partial-tape tally (orch-r1:72) is the place to check before the sweep.
- orch-r1:62 ("shown == accepted"). This is correct, but it is only as strong as what is shown; see I1 and M1.

### Declined to judge
- The prompt's wording quality beyond the constants (adjudicate.md:111-122 match gate.py). It is model-facing prose, and the pilot measures it.
- Pilot `select` stratification heuristics (ROOT_CAUSE_CLASS). The plan defers these to an eye check at pilot time.
- Per-test mutation adequacy. The implementers' mutation tables were not re-derived, and I ran no mutants.
- That the apply redo's own vet/brief LLM calls go through `make_providers(config)` (cli.py:3283) and are not separately gated. It is one gated unit, consistent with the "pacing gate before each adjudication" wording.

**Ready to merge?** With fixes. I1 and I2 (plus M1 and the T5 F3 casefold, which are cheap) and then a targeted re-review. After that: Ready to merge pending pilot.
