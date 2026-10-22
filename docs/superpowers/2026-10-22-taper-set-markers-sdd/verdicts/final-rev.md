# final-rev: final whole-branch review, piece 2 (the taper's set/encore markers win)

Range a26c4d1..8ed8d0c (55 commits). The code at HEAD is the code at a9016b5, the acceptance run-3 sha: `git diff a9016b5 HEAD` touches only CLAUDE.md. Reviewer: Opus, read-only, single reviewer, no subagents. I did it in passes:
1. spec and plan;
2. the source diff in full (taper.py, gather.py, models.py, replay.py, replay_holds.py);
3. tests, by name against the plan and spec, with sampled reads;
4. my own reader and placement probes in a scratchpad;
5. six spot mutants of my own in scratch copies;
6. acceptance files, the record, and the deferred-minor triage.

## Verification I ran

- **Full suite:** `./.venv/bin/python -m pytest -q -p no:cacheprovider` from the worktree. Result: **4474 passed, 1 skipped, 8 deselected** (rc 0), the same as acceptance.md. `llama.__file__` resolves inside the worktree.
- **Global constraints:**
  - `git diff a26c4d1 HEAD -- packages/llama/src/llama/setlist.py` is empty.
  - Grepping the diff for the protected names and the do-not-retune constants finds imports and uses only, no definition edited.
  - No config, CLI, lock, emcee, transmitter, herder or antenna changes.
  - Nothing in emcee, transmitter or antenna reads `structure.alignment`.
- **Spot mutants**, in scratch copies (`git archive HEAD` under `~/.llama-harness/piece2/accept/work/final-rev/<m>`), run with `PYTHONPATH` shadowing plus a per-mutant `PYTHONPYCACHEPREFIX`. The runner asserted that `llama` and `llama.stages.gather` imported from each copy. The S0 control was green. Predictions are in the log, written before the first mutant result. Every mutant was caught by its predicted test:
  - MA, ruling (d)'s keep-today's-encore veto off: 3 predicted tests red.
  - MB, the closer tripwire skipped on owned plus jerrybase: `test_tripwire_runs_on_owned_show_agreeing_with_anchoring`.
  - MC, `merge_conflicts` kept on owned shows: `test_owned_show_drops_merge_conflicts_not_owned_keeps_them`.
  - MD, `StructureInfo` not created without a canonical: the predicted test, plus 2 notes-only coverage tests (the rule's own effect).
  - ME, an owned show records step-1 coverage: the 4 predicted tests.
  - MF, set-count demotion off: the predicted test, plus `test_set_count_note_excludes_the_taper_encore`.

  None of these six is in mutation.md's 32-plus-12 table, so this widens the pinned set.
- **Acceptance numbers sampled against `~/.llama-harness/piece2/accept3/`:**
  - `step3.txt`: title diffs 0, not-owned diffs 0, owned 627, newly held 8.
  - `cmp/summary.txt`: taper_cleared 8; taper_changes tiers 78/0/7/30/498, needs-llm-not-owned 459, stored-llm moved 45; base reproduces 133/146.
  - The per-state tally of `taper_changes.txt` (songs moved 5/69/4; provenance 56/399/43; segues 4/26; filler 1/6; stored-llm 6/36/3 held) matches acceptance.md's table exactly.

## Strengths

- **The decision is narrow and inspectable.**
  - One pure decision function, `decide_taper`, decides ownership, and gather consumes one boolean.
  - The relaxation in `replay.compute_legs` is exactly `and not gathered.taper_owned`, keyed on ownership alone, as section 7 requires. Mutants i, j1 and j2 pin it in both directions.
  - On the not-owned path, gather really is today's path. The new `today_llm` is the old `canonical.items and coverage < threshold` condition in the only branch where it is read (`anchored is None` there), and the anchoring note is appended at the same point in `notes`. The oracle tests (`_oracle` with `decide_taper` patched) plus step3's "not-owned diffs 0" over the whole library are strong evidence.
- **Placement is a genuine exact structural test.** It requires unique hits, only filler between, no merged track across the boundary, no repeated title, order, and a non-tautological source. Comma-kept items are checked so that they never guess. It has no thresholds.
- **Every veto makes the taper own less.** I found no rule that can make it own more than placement allows.
- **Backward compatibility:**
  - `StructureInfo.taper_owned` is defaulted on a permissive model, and a test pins that old dirs read False.
  - `GatherResult`'s new fields are trailing, defaulted NamedTuple fields, and no caller unpacks it positionally.
  - Harness readers use `.get` for base-arm rows.
- **Strict-surface hygiene in the harness:** a stripped arm is stamped, `compare` refuses mixed arms, and a stripped arm writes no apply lists.
- **Docs and record:**
  - The spec records every ruling with its attribution.
  - The mutation record is unusually rigorous: predictions first, sentinels, one-line diffs.
  - Every spec-named real-case negative and positive test exists, and so does every plan-named test (I checked all 75 names).

## Issues

### Critical
None.

### Important

**I1. About 7.8 MB of the 10.8 MB SDD record is copies of source trees, including deliberately mutated code, committed under `docs/`.**
- **Where:** `docs/superpowers/2026-10-22-taper-set-markers-sdd/evidence/`:
  - `orch/t12-rev/{mut,c_025e713,c_3d1c1e7,c_67291bd}/packages/...` (about 5.4 MB, 348 files; `mut` alone is 3.0 MB);
  - `orch-r1/{mut,red,red2}/` and `orch-r1/t6-rev/m_{A,B,base0,C,D,F,G,I,J}/` (12 dirs, about 198 KB each).
- **What they contain:** 393 `.py` files, among them full copies of `cli.py` (210 KB each), `test_stage_gather.py` and `test_taper.py`, mutated `taper.py`/`gather.py`, and copies of `.github/workflows/release.yml`, `packaging/*.spec`, `llama.entitlements`, `pytest.ini`, `LICENSE` and `CLAUDE.md`.
- **Secrets:** none found. I grepped for API-key, token and private-key shapes; the only personal data is the email already present in the copied LICENSE and CLAUDE.md.
- **Why it matters:**
  - The brief's test was "nothing in them is code", and this is code, some of it deliberately broken.
  - Once merged to `main` and pushed, it is permanent in history and in every clone.
  - It shows up in every repo-wide grep and IDE symbol search as duplicate, and partly wrong, definitions of `decide_taper`, `compute_gather` and so on. A future reader of "where is X defined" will hit mutants.
  - The stray `pytest.ini` files make those dirs pytest roots if anyone points pytest at `docs/`. `testpaths` keeps the default run safe today.
- **Fix, before merge (a follow-up delete commit does not remove the bytes from history):** rewrite the branch so that b95a099, and any other commit that added these dirs, carries no tree copies. Replace them with what the evidence needs: the one-line mutant diffs (mutation.md already has them), the runner scripts, and logs. Use `git rebase` with a commit-edit, or rebuild the docs commits. Rewriting history is the operator's call. The alternative is to accept the size explicitly and say so in the record's README.

### Minor

**M1. `1st Encore:` / `First Encore:` with a colon never owns.**
- **Where:** taper.py `_preprocess` and `_ENCORE_HEADER` (around lines 215-218 and 355).
- **What is wrong:** spec section 1 lists `1st Encore:` as a recognised encore line. `setlist._INLINE_MARKER` splits the joined text before `Encore:`, so the ordinal survives as a song item of the previous set (`('1st','2')`, `('2nd','encore')`). The 2|encore boundary's last song is then `1st` and never places. Verified:
  - `Set 1: Bertha / Set 2: Sugaree / 1st Encore: Ripple / 2nd Encore: Brokedown Palace` over the tracks [Bertha, Sugaree, Ripple, Brokedown Palace] gives `unplaced: 2|encore last song '1st' matches 0 tracks`;
  - the same with `First Encore:` fails the same way;
  - `Encore 1:` / `Encore 2:` and the own-line `1st Encore` both own.
- **Effect:** it fails closed (computed as today), so it costs yield, not correctness. The probe counted 35 "ordinal encore" lines in 32 cached texts. `test_numbered_encore_lines_continue` asserts only `runs()` and one label, so it misses the stray item.
- **Fix later:** hold an ordinal-encore header whole before the inline split, as `_split_set_and_encore` does. Strengthen the test to assert the full item list.

**M2. acceptance.md line 32 says the 1-vs-4 miss counts "could not be reconciled".** They reconcile from `score_rows.jsonl`. The in-scope line uses the gate's definition (`yes` rows only), and its 1 miss is `darkstarorchestra-2007-05-17`. The other 3 misses (`furthur-2012-07-08`, `greenskybluegrass-2014-02-28`, `thenewdeal-2005-04-29`) are `taper_explicit: partial`, so they fall outside that set but inside "counts by primary (in scope)", where "in scope" means "not filename/track-tag". `score_summary.txt` uses "in scope" in two senses. Fix: one sentence in acceptance.md, and later a distinct label in the scorer.

**M3. The production `assert` (gather.py:1377) checks that step-1 labels are parallel to tracks.** `align` and `anchor_breaks` produce per-track lists, so it is effectively unreachable. If it ever fires it is a per-show `other` failure (cli's last-resort catch), and under `-O` it vanishes, so `decide_taper` would silently read a short list. Fix later: `LlamaError`, or a decline in `decide_taper` on a length mismatch.

**M4. Two decline branches in `place_taper_structure`/`_place_boundary` are untested:**
- "boundaries out of order";
- "today's structure splits the filler run more than once".

The first looks unreachable through the between-filler rule. It is still the only guard that keeps `labels` correct if bounds stop increasing, so a one-line test would pin it. The "fewer than two sets" message is also untested. Fix later.

**M5. The CLAUDE.md bullet goes slightly beyond the spec.** It names the G1 cost shows (`greenskybluegrass-2013-05-04`, `soulive-2001-12-15`), which come from acceptance.md, not the spec's Documented limitations. Everything else in the bullet matches the spec, including the B4 "LATEST hit" wording and the "never `conflicts`" routing. Fix later, or accept: the facts are true and cited to the acceptance record, which the bullet links.

**M6. `test_taper_structure_beats_unlabelled_setlistfm`'s no-flag assertion is vacuous.** Its last assertion (no "setlist evidence shows multiple sets" or "single-set" flag) cannot fail: the oracle raises neither, since the evidence is `{"1"}` and the 35-minute tape is under `guard_min_minutes`. This is the orch-r1 L29 minor, still open. Fix later: make the tape long enough that the oracle does flag.

## Deferred-minor triage

| Ledger line | Verdict | Reason |
|---|---|---|
| orch L45: `_classify` 5-tuple → NamedTuple | NO ACTION | Private and local; readability only. |
| orch L45: extra void rules not in the module docstring | FIXED | Module docstring lines 94-101 list all three. |
| orch L45: `_has_marker`/`read_taper_structure` double scan could drift | NO ACTION | Both call the same `_scan`, so they cannot drift; the cost is negligible. |
| orch L51: R4 rules also apply to marker-line rests | NO ACTION | Own-less, and 0 library texts changed. |
| orch L58: short `today_sets` silently ignored | FIX LATER (see M3) | Partly fixed: gather asserts the lists are parallel. A decline-on-mismatch inside `decide_taper` would close it for every caller, the probe included. |
| orch L59: untested edge branches | FIX LATER (see M4) | "Veto order with both" is now pinned (`test_encore_like_veto_reason_wins_over_set_like`). Out-of-order, two-split and "<2 sets" remain. |
| orch L59: brief's `Set Break` swapped for `Space`; literals slightly off; noqa E402 imports; 'fewer than two sets' lacks <A>\|<B> | NO ACTION | Cosmetic or test-only. |
| orch L67: in-scope-before-reader test proves nothing; `--out` guard; `breaks_of` test-only; forms O(n·m); handback claim wrong | FIX LATER (low) | Read-only measurement tooling. No library write is possible; the guard covers `--root` and `--bundles`. |
| orch L72: probe test comment; `same_enc` unpinned; summary untested; split-inside-encore tier | NO ACTION | Probe reporting only; the acceptance used replay_holds' report 3, not these tiers. |
| orch L106: rulings R1-R8 | NO ACTION | Pointer only. |
| orch-r1 L14 F1: ordinal header split into `Third`/`Set` | FIXED | R10, 6cf03ea; mutant r pins it. |
| orch-r1 L14 F2: M1 first match only, M2 `_CONT_AFTER` .search, M6 set-3 items skipped | FIXED | Every token is checked (6cf03ea). `_CONT_AFTER` has no `^`, so .search is not an equivalent mutant (comment at taper.py:302-305). `test_set_like_token_in_a_set_three_item` pins M6. |
| orch-r1 L14 F3/F4/F5: attribution, "notes" wording, counts | FIXED / NO ACTION | Docstrings now attribute R9 and describe encore items accurately; the counts were record-only. |
| orch-r1 L17 F6: `_CONT_AFTER` 'cont' prefix broad | NO ACTION | 0 false exemptions in the cache. |
| orch-r1 L22: an item before the first header is labelled "1" | NO ACTION | In an asserting text the only surviving pre-header items are the relabelled leading block before `Set 2`, which spec section 2 makes set 1. Set-like firing there only makes the taper own less. |
| orch-r1 L29: production assert | FIX LATER | M3. |
| orch-r1 L29: filler exclusion untested (M4) | FIXED | Mutant x is caught by `test_filler_only_label_difference_keeps_step_one_alignment`. |
| orch-r1 L29: no-flag assertion at test_stage_gather.py:3281 vacuous | FIX LATER | M6, still vacuous. |
| orch-r1 L29: interim HEAD hard flags before Task 5 | NO ACTION | Moot; Task 5 landed. |
| orch-r1 L29: umphreys identical-to-today only with setlist.fm | NO ACTION | The test passes setlist.fm explicitly and asserts ownership. |
| orch-r1 L35: test (b) preconditions not asserted | NO ACTION | `needs_no_anchoring` asserts `step1_alignment == "jerrybase"`. Mutants y1-y3 and my ME show the conditions are load-bearing. |
| orch-r1 L51: t6 handback mutant-sense misreport; function-local import | NO ACTION | Record/cosmetic. |
| orch-r1 L59: replay_holds docstring rationale; `_shadow` outside never-raises; filler/strip-state not pinned | FIX LATER (low) | Harness only. The run-3 strip arm completed. An OSError aborts a run rather than corrupting it. |
| orch-r1 L65: taper_probe 'ships' branch untested | NO ACTION | Probe only. |
| orch-r1 L73/L78: harness voiced check for unreplayable rows, unused args, `_delivery_path` duplication, comment wording | FIX LATER (low) | Report cosmetics; the unreplayable section is empty in run 3. |
| orch-r1 L86: `test_not_owned_is_exactly_today` crashes rather than asserting under a mutant | NO ACTION | It is still red under the mutant; swapping the two asserts is cosmetic. |
| orch-r1 L89: t8-rev I1/I2 (header-side boundary unpinned; o2/o3 survive) | FIXED | Fix round 1: o, o2 and o3 are caught, and the header-side glued-token tests were added. |
| orch-r1 L97: mutation.md o2/o3 "first run" wording; generous 'declared' labels; glued-token pin | FIXED / NO ACTION | Line 104 now says "SURVIVED, found by t8-rev". The labels are record style. The glued-token pin is deliberate. |
| orch-r2 L34: t9-rev I1 (R1's needs-LLM-base branch untested) | FIXED | 4aa9f8c; M1 is caught. |
| orch-r2 L34: probe docstring "errs toward owning LESS" | FIXED | The docstring now files G1's proxy under "direction mixed". |
| orch-r2 L34: B4 earliest hit leans own-more | FIXED (superseded) | The narrowed ruling uses the LATEST hit (77e5322, 95c735a; L1-L3 caught). |
| orch-r2 L34: `today_reaches_llm` default False | FIXED | Now a required argument; mutant K1 is caught. |
| orch-r2 L34: spec :408 low-confidence paragraph, :596 furthur example | FIXED | Spec lines 417-422 and 607-610. |
| orch-r2 L44: umphreys gather test no longer pins the owned path | FIXED | The test now asserts `res.taper_owned is True` and labels equal to the oracle's. |
| orch-r2 L45: "measured declines" are fixtures | FIXED | Spec line 356 says "Illustrations ... not a population measurement". |
| orch-r2 L45: `B4_BREAK`/`B4_AMBIGUOUS` unused by tests | NO ACTION | `B4_AMBIGUOUS` is gone with the narrowing; tests use the literal string, which is fine. |
| orch-r2 L52: spec §2 "sufficient not exact" sentence | FIXED | Now "with no numbered step-1 break before that hit, the taper still owns". |
| orch-r2 L52: t9-fix4's per-show reasons inferred | NO ACTION | Record caveat. Run 3's step3 shows the only flip is joerussosalmostdead-2019-09-28. |

No deferred item is MUST FIX BEFORE MERGE.

## Declined to judge

- **Whether the D1 segue loss, G1's two lost correct structures, and the 3 owned low-confidence holds are acceptable.** Each is an operator or llama-db ruling recorded in the spec; I checked only that the code implements it.
- **The rule's acceptance trade-offs**, for example the unmarked-encore folding on `furthur-2012-07-08`, `greenskybluegrass-2014-02-28` and `thenewdeal-2005-04-29`. These are operator rulings, not code defects.
- **The correctness of individual adjudicator targets and of the pre-screen verdicts.** I did not re-run any pre-screen. I sampled their counts against the files only.
- **The apply-time decisions** (derektrucksband-2004-04-15, corblund-2004-11-04, mymorningjacket-2018-03-05, the voiced rows). These are operator-gated after merge, by the spec.
- **The deep internals of `scripts/taper_probe.py`** (959 lines). It is read-only one-off measurement tooling. I checked that it writes only under `--out` and refuses an overlapping `--out`, not each tier's logic.
- **Line-by-line review of all 4459 lines of test_taper.py.** I checked every plan- and spec-named test exists, read the gather pins and the umphreys test, and used mutation (the record plus my six) to judge the tests' strength.
- **Regex performance on pathological input.** The header regexes are anchored and linear per line, as far as I could see; I did not fuzz them.
- **Whether the `E <Title>` encore-like rule's collateral (`E Street Shuffle` and similar) costs real yield.** It is own-less, and accepted in the module docstring.

## Recommendations

1. Before merge, resolve I1: rewrite the record commits without the source-tree copies, or have the operator explicitly accept about 7.8 MB of duplicated and mutated code in permanent history.
2. Fix M2's sentence in acceptance.md (one line) at the same time.
3. File M1 (the `1st Encore:` split), M3, M4 and M6 as follow-ups. All four fail closed or affect tests only.

## Assessment

**Ready to merge? With fixes.** The code is correct, matches the spec (the one listed form that does not work, M1, fails closed), is narrowly wired, well pinned, and backward compatible, and the suite is green at 4474. The fix is to keep about 7.8 MB of copied and mutated source trees out of `main`'s permanent history (I1). If the operator accepts that cost, the code is ready as is.
