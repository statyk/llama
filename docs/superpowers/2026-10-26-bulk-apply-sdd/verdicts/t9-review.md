# Task 9 review: `reapply` for packaged, briefed and delivered shows (6a8f7d81..a2e0f20b)

### Spec Compliance

- ✅ Spec compliant. Flow steps 1-7 match the brief's order and the spec ("Re-processing", "Known constraints" show_unit, "The library side"):
  - Step 1: writes inside `show_unit(ws, None)`, dry run `file_lock` only (reapply.py `reapply_show`, diff 405-416). No nested `file_lock`. The own undo, `discard_aside` and `put_back` calls are removed.
  - Step 2: `read_record` comes first, and `CampaignUnreadable` propagates. The `select` skip is at reapply.py:179. The non-held processed skip requires `not awaiting and processed`. The digest check follows.
  - Step 3: the held path is `classify` + `_PREDICTED`, unchanged.
  - Step 4: the label-only predicate is reapply.py:214-220. It is exactly: no flags, no `visible_changes`, `brief == "reuse"`, and NOT (awaiting and delivered and `destination_voiced is False`). Outcome `label-only` iff `any(diff.values())`, else `unchanged`.
  - Step 5: the structure gate covers both branches.
  - Step 6: `plan_reuse(strict=delivered and not allow_download)` + `check_pairs` + `destination_voiced` run before the fresh brief (reapply.py:247-250).
  - Step 7: `write_anchor_if_absent` is the first write (reapply.py:286). Then `show.json` is the commit marker. `mark_processed(held=bool(flags))` follows at reapply.py:330. Then the voiced-rider purge with echo (reapply.py:334), then `after_commit` inside the unit (reapply.py:336). The `audio reused r, downloaded d` echo is printed.
  - `ReapplyOutcome` gains `kind`, `audio` and `align_reproduced` with the specified defaults. The signature carries `with_gather_llm`, `allow_download` and `after_commit`.
  - CLI: `--allow-download` refuses with the fixed string on `--from-list` and on more than one name. The by-name strict refusal prints the fixed hint (cli.py:4116-4123).
- Spec "Apply lists skip processed shows ..., clear-accepted ones too" is satisfied. Checked: `clear-mark` requires `processed` and not awaiting (cli.py:2888), so a clear-accepted show always takes `skipped: processed`.
- Cross-task invariants, all hold:
  - The fresh brief passes `overrules=overrides.overrules` and calls `split_overruled` on the returned problems (diff 565-574).
  - `CampaignUnreadable` propagates. In the list form it hits the `LlamaError` arm, which records it retryable (cli.py `_reapply_list`), and the new test checks `retryable is True`.
  - `mark_processed` runs after the `show.json` write (reapply.py:289 and 326-330).
  - Task 8's identifier ruling is untouched: `plan_reuse` is unchanged, and reapply calls it before writing the anchor. On a first run it pairs through `show.json`; on later runs the existing anchor is filtered by identifier.
  - Task 13: `after_commit(ws)` runs inside the unit, and a raising hook restores (pinned by `test_after_commit_runs_inside_the_unit`). `StationUnpaired`/`StationUnreadable` are `LlamaError` subclasses, so the list form records them retryable.
- Untouched-name grep over the +/- lines: none of the following appear. `STOP_AFTER_LLM_FAILURES` and `load_list` appear only as context. `briefing_reusable`, `DURATION_TOLERANCE_S`, the junk constants, `_pair`, `AGREEMENT_FLOOR` and `MIN_ANCHORS` are absent. `purge_package_audio` is only called, never edited. `Manifest` is untouched.
- ⚠️ Cannot verify from diff: `CLAUDE.md` still describes `llama reapply` as "re-processes HELD shows ... --from-list ...". The brief's Files list does not include docs, so the controller should confirm a later task updates it.

### Strengths
- The rewrite is cleaner than the old code. Choosing `route` (`show`/`held`/`package`) first, before any writes, makes the flow order easy to read against the brief. The dry run and the apply share one decision, so predictions cannot drift from applies.
- Station reads happen before the brief. `test_station_check_runs_before_the_brief` pins this with zero provider calls, and the implementer showed M4 bites.
- Unifying `_is_delivered`/`_delivered` into `ledger.is_delivered` removes real duplication.
- The tests are real end-to-end fixtures, not mocks. `_delivered_env` packages for real over `ReuseIA`, copies to a station dir and purges, as deliver leaves it. Review Focus 4 is exercised through `deliver --fixed`, and the newly-held anchor through a real `fix --overrule` with zero downloads.
- The dry-run list is complete and each moved expectation cites its clause. Targeted run: `./.venv/bin/python -m pytest packages/llama/tests/test_reapply.py -q` gave 98 passed, no warnings (teed into t9-review.log). `llama.__file__` resolves inside the worktree.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **reapply.py:179: the re-selection skip is unconditional (brief-literal).**
   - Problem: the last mark starts at `select`, so the skip fires even after `redo --from select` has processed the show. It fires for held shows too. In both cases a named reapply prints `skipped: re-selection (llama redo <slug> --from select)`. That stale hint points the operator at a second full re-select, which re-downloads every track and spends a fresh brief. It also pre-empts step 3's "held shows keep today's behaviour" for a re-selected show that came out held.
   - Why it is Minor: the spec says "a redone re-selection drops off the verified list". Gating on `campaign.awaiting_fix(rec)` would match that intent.
   - Human call: the brief states it literally, so this is the operator's decision.
2. **reapply.py:330-336: the purge runs before `after_commit` (brief-ordered).**
   - Problem: if the hook raises after a voiced-rider purge has deleted audio that existed before the unit, `show_unit` cannot restore it. Its guarantee covers files outside `package/audio/`, and its audio restore only removes added files and puts back the aside.
   - Why there is no data loss: `purge_package_audio` verified that the station holds every track. The library is left with a restored manifest and missing audio, and the deliver gate routes that to `redo --from package`.
   - Suggested fix (brief-order change, human call): run `after_commit` before the purge, which makes the purge the last and only irreversible step. Or document it beside `show_unit` limitation 1. Task 13 should know about this either way.
3. **reapply.py:286 with route `show`: a `label-only`/`unchanged` commit leaves `reuse-anchor.json` behind.**
   - Spec "Held outcomes keep a reuse anchor" frames the anchor for held commits, and it "goes only when a package is built".
   - It is harmless: label-only means the files and titles are unchanged, so the anchor equals `show.json`, and `plan_reuse` reads it only when `show.json` pairs nothing.
   - It still lingers indefinitely. Skip the anchor when `route == "show"`, or note it.
4. **reapply.py:214-220: the `show` route does not require `packaged`.**
   - Problem: a briefed but unpackaged non-held show with no visible change commits `show.json` only and reports `unchanged`, so it stays unpackaged. The spec's outcome set for a non-label-only show is "cleared (re-packaged, ready to deliver) or held".
   - The population is rare: a crash between brief and package.
   - Fix: route it to `package` when `not packaged and not delivered`.
5. **reapply.py:114 `_purge_line` duplicates `cli._echo_purge` (cli.py:2703).** The three message texts are copied verbatim; only the "purged" line adds a slug prefix. One shared formatter would let both callers move together, for example in `catalog`.
6. **cli.py:4122: the by-name output doubles the slug**, as `FAILED <slug>: <slug>: station copy unreadable: ...`, because the exception text already carries the slug. The contract string is preserved inside the line, and the list form already prints `FAILED X: X: cannot read campaign.json` the same way. Cosmetic.
7. **cli.py:4269: the dry-run `downloads` count still uses `needs_audio_download(ws)`.** For a purged delivered show that strict reuse will copy from the station, this overcounts. Pre-existing approximation, conservative direction, flagged by the implementer.

### Implementer decisions (report "Concerns" 1-8)
1. Scope guard (`skipped: not held` for a non-held, unbriefed, unpackaged, undelivered show): **accept**. It matches the spec's "packaged, briefed and delivered" scope, and a mutant (M2) pins it.
2. Literal re-selection skip: **accept as brief-literal**. Minor 1 records the follow-up (gate on `awaiting_fix`).
3. Several names with `--allow-download` refuse: **accept**. It fits the contract's "takes one named show" and the hint's "re-run this one show".
4. With `--allow-download`, an unreadable station reads as unvoiced: **accept**. The operator has waived the station copy, and the failure direction is safe: a re-package with no purge, and deliver re-checks voiced later.
5. Anchor left after a show-only commit: **accept as brief-literal** (step 7). Benign; Minor 3.
6. Task 6's `already purged` warning kept on clear-mark's equal case: **accept**. It is outside this task, and the line is truthful.
7. Deliver's `different package version` warning printed verbatim by the voiced rider: **accept**. This is the spec's skip-and-warn.
8. Purge-then-hook limitation: **accept as brief-ordered**. Minor 2 gives a cheap reorder for the human to decide.
- Concerns 9 and 10: 9 is accepted as Minor 7. On 10, `unchanged` has `kind == "label-only"` and an unapplied needs-llm row has `kind == "needs-llm"`. Both fit the brief's kind set.

### Assessment

**Task quality:** Approved

**Reasoning:** The flow matches the brief's contract order step for step. Every write is inside `show_unit`, station reads and strict pairing precede the only LLM call, and `processed` follows the commit marker. The tests exercise real packaging, station copies and restore. The remaining items are brief-literal edge cases and polish for the human to rule on.
