# SDD ledger — plan: docs/superpowers/plans/2026-08-30-title-correspondence.md

Scope: Phase A only (Tasks 1-4). Tasks 5-9 (Phase B/C) explicitly out of scope.
Worktree: /Users/shawn/projects/llama/.worktrees/title-correspondence (branch `title-correspondence`)
Branch base: f785fe6. Test command: `./.venv/bin/pytest -q` (worktree venv, never bare pytest).
Baseline: 1479 passed, 7 deselected.
Spec read: docs/superpowers/specs/2026-08-30-title-correspondence-design.md (reachable).

## Pre-flight conflict scan (Tasks 1-4)

### Cross-task rows (every pair sharing a file or an interface)

| Pair | Produced | Consumed | Finding |
|---|---|---|---|
| T1 -> T2 | `structure.adopt_gap_titles(tracks, canonical, *, metadata_norms, aliases=None)` | T2 calls it with exactly those keywords + `aliases=GD_SHORTHAND if is_family_artist else {}` | AGREE. Verified `fuzzy_norm_title`/`title_components`/`_merge_run(norms,lo,hi,comps)` exist at structure.py:61/77/355 with the signatures the plan assumes. |
| T1 -> T1 | `setlist.is_junk_title` (promoted from `_is_junk_title`, setlist.py:353) | T1's `_hygienic` | AGREE. `MAX_TITLE_LEN=80` at setlist.py:362; `titles.is_real_title` at titles.py:24. Two in-file call sites of `_is_junk_title` (setlist.py:464) plus the back-compat alias. |
| T2 -> T3 | `title_source == "setlist-gap"`; `run_gather(..., jerrybase_enabled=True)` | T3's characterization test | AGREE. `jerrybase_enabled` is a real `run_gather` kwarg (gather.py:497). |
| T2 <-> T3 | both append to `packages/llama/tests/test_stage_gather.py` | sequential, T3 after T2 | NO CONFLICT. But T3's test repeats T2's fixture-blanking setup verbatim (blank mp3 idx 1,2). See Ruling 3. |
| T1/T2 -> T4 | `adopt_gap_titles`; gather's canonical builders | T4 harness spies on the real pipeline | AGREE. `_collect_parses` gather.py:143, `rank_parses` structure.py:296, `_strip_head_banner` gather.py:335, `_drop_artist_items` gather.py:469, `blend_segues` structure.py:339 all exist. |
| T4 -> T2/T3 | M1 ship gate | authorizes Phase A shipping unflagged | NOT A CODE DEPENDENCY. A failing gate is an escalation to the user, not a fix loop. |
| Global constraint | `structure.py` must not import `stages/gather.py` | T1 code | HELD. `grep stages packages/llama/src/llama/structure.py` = empty; `metadata_norms` is a parameter. |
| Global constraint | `parse_setlist` unmodified | T1-T4 | HELD. No task touches it. |

### Per-task self-consistency rows

| Task | Tests specified vs code specified | Files created vs files later touched | Finding |
|---|---|---|---|
| T1 | 11 tests call `adopt_gap_titles(tracks, canonical, metadata_norms=set())`; code makes `metadata_norms` keyword-only, `aliases` optional. `_tracks` builds `Track(index,set,title,filename,duration_sec,title_source)` — all real fields, `matched` defaults None. | setlist.py + structure.py + test_structure.py; none re-touched later in Phase A. | AGREE, one defect: Step 3's command `-k adopt or gap or anchor or hygiene` is unquoted, so the shell parses `or` as a command separator. See Ruling 1. |
| T2 | Fixture step shells out to `scripts/capture_fixture.py`, which does `httpx.get(https://archive.org/...)`. | Creates `ymsb2005_metadata.json`, consumed by T2's own third test. | CONFLICT with the run's no-network constraint. See Ruling 2. |
| T2 | `_hygienic` compares `fuzzy_norm_title(t)` against `metadata_norms`, which gather builds from `_place_norms`/`_date_norms` (gather.py:321), NOT from `fuzzy_norm_title`. | — | POSSIBLE NORMALIZATION MISMATCH. Unit test passes a hand-built `{"fillmore auditorium"}` so it cannot catch it. See Ruling 4. |
| T3 | Test asserts only `adopted` non-empty and no adopted title ends `.mp3`. | test file only. | Thin assertions by design (characterization pin). See Ruling 3. |
| T4 | Requires reading ~/.llama/cache (968 `md_*.json`) and three-way hand triage. | scripts/ + docs/. | NOT MECHANICAL — needs judgment. See Ruling 5. |

### Rulings (pre-flight)

Ruling 1: Task 1 Step 3's verification command is written as `-k adopt or gap or anchor or hygiene`; implementers must quote it as `-k "adopt or gap or anchor or hygiene"`. — The plan's intent is unambiguous (run the new tests) and the unquoted form is a shell-syntax slip, not a design choice. — If wrong: nothing; the assertion content of the tests is untouched and Step 5 runs the whole file anyway.

Ruling 2: Task 2 Step 1's fixture is built OFFLINE from the already-cached `~/.llama/cache/md_ymsb2005-12-31.flac16.wav.json`, slimmed with the exact same field projection `capture_fixture.capture_ia` applies (`metadata`, `files` projected to name/source/original/format/length/md5/title, `reviews`), instead of re-fetching from archive.org. — The run is barred from network calls; the cached response IS the archive.org response, and I verified it reproduces the plan's own acceptance assertion exactly: `24 tracks; 25 items; high`. — If wrong: the fixture could differ from a fresh fetch (archive.org re-derived the item since caching). Cost is a fixture that pins stale reality; detectable by re-running `capture_fixture.py` with network and diffing, and the 24/25/high assertion is the plan's own guard.

Ruling 3: Task 3's test stays as the plan writes it — thin assertions and setup duplicated from Task 2's test are both accepted. — The plan states its purpose explicitly ("pins the behaviour change so it is owned, not discovered"); a characterization pin that asserts the adopted titles are real song text is exactly the contract, and de-duplicating the two setups into a shared helper would couple two tests that pin different things. — If wrong: mild test-suite redundancy. Zero production-code risk.

Ruling 4: Task 2's implementer must EMPIRICALLY verify that `_show_metadata_norms`' output vocabulary is comparable with `fuzzy_norm_title` before declaring the wiring done, and report the finding. If they disagree, the fix is to normalize the comparison at the call site in gather (not to change `_show_metadata_norms`, which `_strip_head_banner` depends on, and not to move normalization into `structure.py`). — The plan asserts the comparison works but its only test hand-builds the norm set, so the assertion is untested at the integration boundary; `_strip_head_banner` is a live consumer that must not change behaviour. — If wrong (they actually agree): a few minutes of verification, no code change.

Ruling 5: Task 4's implementer runs on Opus, not Sonnet. — Its deliverable is a three-way hand triage of every wrong adoption plus an evidence doc held to the standard of an existing in-repo doc; the plan supplies a prose description of the harness, not its code, so it is not transcription. — If wrong: overspend on one dispatch.

Ruling 6: Phase A stops after Task 4's review regardless of the M1 verdict. If M1's `genuinely-wrong` rate exceeds the tag rung's typo baseline, the ship decision (flag vs abandon) is escalated to the user, not decided here. — The plan's ship gate names three outcomes, two of which change shipped behaviour; that is a scope decision above the orchestrator. — If wrong: one round-trip with the user.

## Task log

Task 1: dispatched 2026-08-31 00:40 EDT, implementer on Sonnet, agentId ab39ddba3e7ebd81d, BASE f785fe6. Child dir $D/task1.
Ruling 4 REFUTED by the coordinator 2026-08-31 00:45, with measurement. `_place_norms` (gather.py:267-289) and `_date_norms` (gather.py:290-320) BOTH build their sets with `fuzzy_norm_title` — the same function `_hygienic` uses. Measured: 'Fillmore Auditorium'/'Denver'/'Yonder Mountain String Band' all in_norms=True, 'Ride The Wild Turkey' False. The plan's hand-built test set is representative, not papering-over. Task 2's dispatch carries this as "checked and holds — do NOT add a conversion layer"; a conversion inserted to fix a non-bug turns a working guard inert, and an inert guard here is silent. The empirical check is kept as a CONFIRMATION; a False on a venue-named item would be a real finding to escalate, not patch.
Task 1: implementer DONE (Sonnet). Commit 2bdcc96. `./.venv/bin/pytest -q` -> 1489 passed, 7 deselected (+10 = the 10 new tests).
Task 1: implementer self-reported two defects it found and fixed pre-commit: (a) the brief's `_items`/`_tracks` helper names collide with pre-existing module-level helpers in test_structure.py, silently overwriting them and breaking 9 unrelated tests -> renamed to `_gap_items`/`_gap_tracks`, brief's test bodies kept verbatim; (b) its insertion point split an existing test, orphaning an assert -> restored.
Task 1: task review (Opus) — spec compliance PASS, task quality APPROVED. Report: .superpowers/sdd/2026-08-30-title-correspondence/task-1-review.md. Reviewer mutation-tested the new code on a scratch copy: count-forcing, `_merge_run` reuse, the metadata clause and override-anchoring are all load-bearing. Test file diff has ZERO deleted lines, so no pre-existing test was weakened by the helper rename.
Task 1: 2 Important findings, both properties of the brief's own verbatim code -> plan-mandated -> ruled on by me, not sent to the fix loop.

Ruling 7 (Important-1, merged-anchor exactness): the shipped code KEEPS `_merge_run` as the brief and spec both require; the DOCSTRING is amended to state the real invariant ("exact for single anchors, component-fuzzy for merged ones, because a merged track must consume all its items"). Additionally Task 4's M1 triage must break its error rate out BY ANCHOR KIND so the merged-subphrase path's rate is visible rather than pooled. — The reviewer is right that the two brief requirements are inconsistent: `_merge_run` matches components with `fuzzy_title_eq` (structure.py:355), which falls through to `_is_subphrase` (structure.py:184), so a merged anchor is not exact. But the SPEC is the binding authority and it explicitly mandates reusing `_merge_run` (and even `_window_match`, which the plan tightened away): "It reuses the existing matching-layer primitives — fuzzy_norm_title, title_components, _merge_run, _window_match, _window_hi — rather than reimplementing a walk." The spec's adoption conditions name count-forcing, anchoring and hygiene; exactness of the anchor match is the PLAN's own addition. `_merge_run` also requires ALL components to match CONSECUTIVELY, a far stronger joint constraint than one subphrase hit, and a wrong merged anchor almost always breaks count-forcing downstream, which is the spec's stated "whole safety argument". Tightening it now would make the shipped function differ from the one the spec's 2.4% pilot measured, and M1 is the instrument built to answer exactly this question against hidden tags with per-case triage. An overstated invariant in a shipped docstring is itself a real defect in a codebase that treats docstrings as load-bearing. — If wrong: Phase A ships (pending M1) with a merged-anchor path looser than the plan intended. Exposure is bounded to one measurement cycle because M1 now reports the merged-anchor rate separately; the fallback fix is a two-line tightening of `_merge_run`'s call site to exact per-component equality, which is strictly conservative (a declined merged anchor makes adjacent gaps decline, never mis-adopt).

Ruling 8 (Important-2, `_hygienic` aliasless normalization): NO code change; add a one-line comment recording that the aliasless call is deliberate and symmetric. — I verified the other side myself: `_place_norms` (gather.py:284) and `_date_norms` (gather.py:318) both build their sets with bare `fuzzy_norm_title(...)`, no aliases. So `_hygienic`'s bare `fuzzy_norm_title(t)` matches the vocabulary it is tested against exactly; threading aliases into ONE side is what would break it. This is the same conclusion the coordinator reached independently on Ruling 4. — If wrong: the metadata screen under-matches and a venue-named canonical item could be adopted as a title. Detectable in M1's triage (it would appear as a `genuinely-wrong` adoption of a venue/city/date string) and by the standing empirical check Task 2 must report.

Task 1: minor (deferred): `test_hygiene_rejects_a_junk_item` never exercises `is_junk_title` — `is_junk_title("Set List:")` is False and the `endswith(":")` clause does the rejecting, so Step 1's promoted predicate has ZERO new coverage; `is_real_title` and `MAX_TITLE_LEN` clauses likewise unpinned.
Task 1: minor (deferred): redundant mid-file imports at test_structure.py:1642-1643.
Task 1: minor (deferred): `test_empty_canonical_is_a_no_op` still passes with its guard removed (smoke test, not a guard test); the "never overwritten" half of the override test is tautological.
Task 1: minor (deferred): `_is_junk_title` back-compat alias has zero consumers; prose comment at structure.py:758 names the private alias.
Task 1: minor (deferred): anchor scan unbounded to end of item list (reviewer probed adversarial shapes; count-forcing absorbed all — informational).
Task 1: minor (deferred): merged-anchor test comment misdescribes the failure mode; empty path returns caller's list not a copy; continuation indentation off by four; `_hygienic`'s function-local imports not needed for circularity.
Task 1: complete (commits f785fe6..2bdcc96, review clean; 2 Important ruled, 6 minor deferred)

Task 2: dispatched 00:53 EDT, implementer on Sonnet, agentId ab0c7f02dbad00cf5, BASE 2bdcc96. DONE at 01:01 -> commit 8e03daa, `./.venv/bin/pytest -q` 1492 passed 7 deselected (+3).
Task 2: implementer found a REAL defect in the brief's test body: `test_gap_fill_resolves_a_mixed_show` as literally specified can never pass regardless of implementation. The gd73 fixture's kept-file count exactly equals its canonical item count (6==6), so the pre-existing WHOLE-TAPE setlist rung in `titles.resolve_titles` resolves the blanked tracks to `title_source="setlist"` before `adopt_gap_titles` ever sees an unresolved run. Fixed with a one-line addition using the existing `overrides.exclude` mechanism to drop the trailing untagged file (gd73-06-10d3t01.mp3, "Johnny B. Goode"), breaking the coincidental whole-tape count match without touching either anchor (Morning Dew / Dark Star) or the two-item gap under test (China Cat Sunflower / I Know You Rider). Red before the wiring, green after; both states verified. No production code, fixture JSON, or other test touched.
Task 2: NOTE FOR THE FINAL REVIEW — this sits in tension with the annotation Task 2 adds at titles.py:129 calling that rung "MEASURED DEAD: 0 of 2,015 tracks across the 89-show library". Both can be true (the canonical test fixture is not a library show), but the annotation's "close to a measure-zero event" reads oddly next to a repo fixture that triggers it on the first try.

Coordinator hardening received 01:01, applied:
Ruling 7 (amended): the docstring must state the CONSEQUENCE, not just the mechanism — a merged anchor bound by subphrase can land ONE ITEM OFF, and count-forcing does NOT catch that, because a same-size shift preserves the gap's item count. Same failure shape that killed the LLM approach and the unanchored DP in the spec's own measurements: a shift satisfies every consistency check because a shift is consistent. — A reader given only "matches fuzzily" cannot derive the reachable silent failure. — If wrong: none; documentation-only.
Ruling 9: M1's by-anchor-kind breakout is a GATE, not a report line. Phase A ships unflagged only if BOTH the pooled genuinely-wrong rate AND the merged-anchor-path rate independently clear the gate. If the merged path is materially worse, the two-line conservative tightening of `_merge_run`'s call site is applied BEFORE shipping, not after. Carried into Task 4's dispatch in those terms. — An evidence doc that merely records a worse merged-path number while the pooled number passes ships the defect it measured. — If wrong: Phase A is held on a gate stricter than the plan wrote, costing one measurement cycle; the pooled number is still recorded so nothing is lost.
Ruling 10: the "junk-title test has zero coverage" minor is PROMOTED out of deferred and fixed in Task 2. A promoted predicate with no test through the new path means nothing would fail if the promotion were reverted or the call site dropped; this project's own recorded lesson is that a green suite is not evidence a constraint is load-bearing — mutation is. Fix requires a case where hygiene rejects BECAUSE `is_junk_title` says so and for no other reason, verified by mutation. — If wrong: one extra small test.
Task 2: resumed implementer (Sonnet, same agent) at 01:03 with both additions; new sentinel $D/task2/done2.
Task 2: task review (Opus) — spec compliance PASS, task quality APPROVED. Report: task-2-review.md. Reviewer independently reproduced the fixture projection from the cached source (byte-identical), re-derived the red-before-wiring state by monkeypatching `adopt_gap_titles` to identity, and mutation-tested the guard tests. Worktree clean before and after.
Task 2: reviewer CONFIRMED the implementer's whole-tape-rung finding from first principles, and confirmed the `overrides.exclude` fix does not weaken what the test pins.
Task 2: 1 Important (I1), 4 Minor, 1 Cannot-verify.

Ruling 11 (I1 — adoption inflates coverage and flips `Track.matched`): the PLACEMENT stands; the SILENCE does not. Task 3 additionally lands the reviewer's minimum remediation — a comment at gather.py:604 recording that adoption feeds `align()` and therefore raises coverage and flips `matched` BY CONSTRUCTION, plus a test pinning the exact wired-vs-unwired outcome. I am NOT deciding here whether `matched` should stay honest; that goes up to the user.
  Evidence (reviewer-measured on the mixed-show case, wired vs wiring monkeypatched out, all else identical):
    WIRED   : coverage=1.0  matched=[T,T,T,T,T]  needs_review=False  flags=[]
    UNWIRED : coverage=0.6  matched=[T,F,F,T,T]  needs_review=True   flags=['low-confidence structure alignment','unresolved track titles']
  Why placement stands: both the spec and the plan put the rung before `align()`, and that is what gives gap-filled tracks correct set labels; Task 3's whole premise is that adopted titles make downstream checks live. Why the silence does not: `models.py:158-160` documents `matched` as a three-state marker existing specifically so the UI never "assert[s] something never checked", and adoption makes `matched=True` assert exactly that. Worse, `coverage` gates `align_coverage_threshold` (gather.py:646), which controls the LLM realignment fallback AND the `low-confidence structure alignment` flag — so the flag is suppressed precisely on the shows where the riskiest thing was done. Composed with Ruling 7's admitted weak point (a merged anchor can bind one item off, and count-forcing provably cannot catch a same-size shift), the reachable failure is: mis-adopt a shifted run -> coverage rises to 1.0 -> the flag that would have caught it is suppressed -> the show ships wrong, silently. That is this project's own recorded dangerous class (the tail-guard run's "a gate defined over things that changed state was structurally blind to it").
  — If wrong: documenting and pinning a behaviour that later turns out to want changing costs one test rewrite. The alternative error — leaving it undocumented and unpinned — is the silent one, and Phase A's only remaining backstop would be M1.

Ruling 12: Minors M1-M4 from the Task 2 review are folded into Task 3 rather than deferred, because all four live in the files Task 3 already touches and three are one-liners. M1: the integration test asserts gap-fill FIRED but never that it filled CORRECTLY — add the adopted-title assertion. M2: the titles.py:129 annotation reads "this code never runs", which is true of the production corpus and false of the test suite, where it fires on the canonical gd73 fixture and was the exact trap the plan author fell into — add the fixture clause. M3: `test_a_wholly_untagged_tape_gets_no_gap_fill`'s docstring claims it pins anchoring, but the ymsb fixture is 24 files vs 25 items so count-forcing rejects independently (reviewer verified by mutation: the test still passes with the unanchored branch defeated) — fix the docstring to say what it actually pins. M4: hoist the twice-computed `_show_metadata_norms(...)` and the twice-written `GD_SHORTHAND if ... else {}` into locals. — If wrong: cosmetic churn in one test file.

Task 2: DEFERRED to the final review / the user — the `titles.py:129` annotation's "0 of 2,015 tracks across the 89-show library (2026-08-30)" is an unsourced number with no script, log, or in-repo evidence doc, unlike every other measured constant in this codebase (tail-guard, junk-duration, `_RECOVER_BELOW`) which each cite a doc or record their sample. I cannot manufacture provenance; only the plan author has the command.
Task 2: complete (commits 2bdcc96..83c2a62, review clean; 1 Important ruled into Task 3, 4 minors folded into Task 3, 1 unsourced-number item deferred)

Task 3: dispatched 01:14 EDT, implementer on Sonnet, agentId a69774e3d6c9008d7, BASE 83c2a62. Scope = plan's Task 3 + Items A-E (Rulings 11/12).
Task 3: liveness probe 01:25 — task3 dir age-min=0, commit 6d1be0e at 01:24, log tail shows 1495 passed. Healthy; sentinel timeout was "not yet", not death.

Ruling 11 SUPERSEDED by the plan owner 01:25. I1 is not merely pinned, it is CORRECTED, and both changes are in scope for Phase A:
  (1) a track adopted by `adopt_gap_titles` reports `matched=None`, never True — no model change needed, since models.py:158-160 already defines None as "not measured" and the CLI renders it `-` under that legend. An adopted track's match is TAUTOLOGICAL: align() matched the canonical item's own text against that same canonical item, so it is not a measurement.
  (2) adopted tracks are EXCLUDED from `_songish_coverage`; coverage is computed only over tracks whose titles came from independent evidence.
  Owner's scope argument: as wired, Phase A makes the documented invariant at models.py:158-160 FALSE, and a feature that falsifies a documented invariant is not finished — this is doing Piece 1 correctly, not a separate behaviour change. Rejected alternatives: moving adoption after align() buys honesty by surrendering the downstream value Task 3 exists to pin (correct sets/segues on gap tracks; closer tripwire and spans check seeing real titles); leaving it as-is is circular in the way that matters, because the adoption manufactures the very evidence that says the adoption was fine. With coverage honest, a shifted adoption cannot raise coverage, so it cannot suppress its own alarm.
  Edge case specified, not assumed: if every songish track were adopted, coverage is computed over an empty set and `_songish_coverage` returns 0.0, tripping the low-confidence flag — the safe direction. Unreachable in Phase A (adoption requires anchors; anchors are matched tracks) but must be asserted, not reasoned about.
  The Item-A pinning test committed in 6d1be0e encoded the OLD table and must be rewritten to the corrected semantics; it is now the regression guard for this entire finding.
  — If wrong: coverage under-reports on gap-filled shows, making the low-confidence flag fire more often than needed — visible, conservative, and the opposite of a silent failure.

Ruling 13 (Item F): the unsourced "0 of 2,015 tracks" annotation gets provenance rather than deletion. Task 3 adds `scripts/title_source_census.py` (read-only walk of ~/.llama/shows/*/show.json) and the annotation cites it by name plus date, matching how `refresh_jerrybase.py` and `capture_fixture.py` are cited. Owner re-ran the census live: shows=89 tracks=2015; tags 1917 | unresolved 75 | sibling 21 | override 2 | setlist 0. — Every other measured constant in this codebase cites a doc or records its sample; a bare number in a comment is treated as settled fact by the next reader. — If wrong: a small script nobody runs again.
Task 3: sent the I1 ruling + Item F to the live implementer at 01:26 (queued for its next tool round). No takeover, no second writer — the agent is alive and remains the sole writer.
Task 3: implementer DONE across two passes (Sonnet, same agent resumed once). Commits b380e5c, cd43a7e, 6d1be0e, f4e8889, 3d2dcf6. `./.venv/bin/pytest -q` -> 1497 passed, 7 deselected; tree clean. Verified by me.
Task 3: I1 correction landed as ruled — `structure._songish_coverage` now excludes `title_source=="setlist-gap"` tracks; `gather.py`'s final track assembly forces `matched=None` for adopted tracks instead of align()'s tautological True. Empty-set edge case (all songish tracks adopted -> 0.0) pinned by test, not assumed. Both corrections verified by mutation.
Task 3: Item F census run against the live library matched the plan owner's numbers EXACTLY — shows=89 tracks=2015, tags=1917 unresolved=75 sibling=21 override=2, and 0 with title_source=="setlist". No discrepancy.
Task 3: THIRD defect found in the plan's own verbatim test code — the base Task 3 brief's test snippet also fails as written, for the same reason Task 2's did (gd73's 6 files == 6 items, so the whole-tape rung pre-empts adopt_gap_titles). Fixed the same way, and documented in the test docstring. That is three separate never-could-pass tests in the plan's Phase A text.
Task 3: implementer flagged honestly that the mixed-show FIXTURE cannot numerically distinguish the coverage fix (its coverage is 1.0 before and after, since its anchors already fully cover it), and added a synthetic unit test that does discriminate rather than fabricating a fixture change. Routed to the Task 3 reviewer for independent judgement.
Task 3: task review dispatched (Opus), range 83c2a62..3d2dcf6.
Task 3: task review (Opus) — spec compliance PASS, task quality CHANGES REQUESTED. 3 Important, 4 Minor, 2 Cannot-verify. Report: task-3-review.md. Reviewer verified by execution: five mutations, two probes, the census run, a pytest collection check; worktree clean after every restore.
  Important 1: Item A4's coverage half is NOT guarded at integration level — the existing pinning test stays green when the coverage exclusion is mutated away. A discriminating case exists and the implementer wrongly concluded none did: a show whose independent evidence is WEAK keeps its flag with the exclusion, and without it two tautological Trues buy it a clean bill of health. Reviewer ran both.
  Important 2: the identical tautology exists for `title_source == "setlist"` (titles.py's whole-tape rung assigns the canonical item's own text by position) and the new filter does not cover it. Measured on the fixture: 3 of 6 tracks "matched" against text they were handed, coverage 1.0, flags []. The new `_songish_coverage` docstring's claim ("only tracks whose titles came from independent evidence") is one the implementation does not keep.
  Important 3: excluding adopted tracks makes coverage a ratio over the independent tracks only, so a mostly gap-filled show's flag turns on a handful of measurements. Measured: 1 matched anchor + 9 adopted -> 1.0; 1 missed anchor + 9 adopted -> 0.0; 0 anchors + 10 adopted -> 0.0. 1.0 from a single measurement is the dangerous direction and is fully reachable; the docstring documents only the fully-empty case. Docstring sentence, no code change.
  Reviewer's note worth keeping: the fix does NOT eliminate adoption's ability to raise coverage relative to no adoption (previously-unresolved tracks leave the denominator when adopted). What it buys is that when an independent anchor MISSES, the miss is no longer diluted by tautological matches — which is Important 1's untested case.

Ruling 14 (Important 2): EXTEND the filter to exclude `setlist` as well as `setlist-gap`, with a comment saying why `tags`, `sibling`, `sibling-format` and `override` are independent and stay; and introduce the module-level constant Minor 7 asks for so "which sources are tautological?" is answerable in one place. Rejected the alternative (narrow the docstring and record `setlist` as a measured-dead exception). — The whole-tape rung assigns the canonical item's own text by position, which is the identical tautology the fix was written for, and Item C deliberately KEEPS that rung, so its tautology is a standing property rather than a transient. Production impact is nil today (census: 0 of 2015), so extending is behaviourally free in production while removing a path that fires throughout the test suite and masks exactly this class of bug. The docstring states a principle; the filter should implement the principle, not an enumeration that happens to be true this month. — If wrong: on a show where the whole-tape rung does fire, coverage drops toward 0.0 and the low-confidence flag fires, holding the show for review. That is the conservative direction and is visible, not silent.
Ruling 15: Minors 4-7 are folded into the same fix round rather than deferred — all four are one-liners or directly serve Ruling 14, and they live in the files already being edited. Minor 4: the test name asserts the exclusion half it cannot demonstrate; rename or make it true. Minor 5: models.py:158-160 explains `matched=None` solely via the override path and now has a second, more common producer. Minor 6: function-body imports against file convention, plus ~10 duplicated setup lines. Minor 7: the constant, per Ruling 14. — If wrong: cosmetic churn.
Task 3: fix round 1/5 dispatched — resumed original implementer (Sonnet), findings sent verbatim, sentinel $D/task3/done3.
Task 3: fix round 1/5 — commit b07d51a. Scoped re-review (Opus) verdicts: Important 1 ADDRESSED, Important 2 ADDRESSED (`structure.TAUTOLOGICAL_TITLE_SOURCES` introduced), Important 3 ADDRESSED, Minors 4-7 ADDRESSED. No new Critical/Important breakage. Suite 1499 passed, 7 deselected; verified by me.
Task 3: re-reviewer confirmed the one pre-existing test whose expectations moved (`test_gather_artist_item_does_not_block_title_resolution`) is the only one affected — it ran the full suite under the `{"setlist-gap"}` mutation to prove nothing else shifted silently — and judged the rewrite honest.

Ruling 16 (plan owner, 02:03): the re-reviewer explicitly reasoned that `gather.py:702` "must stay setlist-gap-only because setlist-sourced tracks are deliberately not forced to matched=None". That reasoning is REJECTED. `_songish_coverage` (structure.py:946) excludes both members of TAUTOLOGICAL_TITLE_SOURCES, but gather.py:702 forces `matched=None` only for `setlist-gap` — so a `setlist`-sourced track is excluded from the coverage denominator as tautological while still reporting `matched=True`, asserting an independent match that never happened. That is the same models.py:158-160 violation the I1 ruling exists to prevent, on the other rung: a reader of `llama show --tracks` sees a checkmark on a track whose match was circular. Fix: gather.py:702 tests membership in `structure.TAUTOLOGICAL_TITLE_SOURCES` rather than naming one source — one constant, both signals, no way to drift, which is the actual value of having introduced the constant. Pinned by test, verified by mutation. — If wrong: nil in production (0 of 2,015 library tracks are `setlist`-sourced); test-visible only, same class as the coverage change already accepted.
Ruling 17: the user-visible behaviour change — a show whose every title came from the setlist flips `needs_review` False -> True — is recorded in the M1 evidence doc (Task 4), not only in a test docstring. Same for the gd73 fixture caveat. — Behaviour changes documented only inside a test docstring are invisible to anyone looking for behaviour changes; the M1 doc is what Phase B's author will read. It is the safe direction and honest (such a show has zero independent evidence its alignment is right), and it must carry the measured "0 of 2,015 production tracks affected" so a future reader sees it was scoped, not overlooked. — If wrong: a caveat in a doc nobody needed.
Task 3: fix round 2/5 dispatched — resumed implementer (Sonnet), sentinel $D/task3/done4.
Task 3: fix round 2/5 — commit a37bb83, `gather.py:710` now tests `t.title_source in TAUTOLOGICAL_TITLE_SOURCES`. Round-2 scoped re-review (Sonnet): ADDRESSED. Suite 1499 passed, 7 deselected; tree clean; verified by me.
Task 3: the pin was added as a new ASSERTION inside an existing test, not a new test function — which is why the suite count stayed 1499 before and after. I refused the report's prose on that number and required the mutation; two independent parties then reproduced the same result. Re-reviewer: mutating the matched= line fails `test_stage_gather.py::test_gather_artist_item_does_not_block_title_resolution` on `assert all(t.matched is None for t in show.tracks)`. Plan owner ran the same mutation separately (73 passed baseline -> 1 failed / 72 passed) and got the identical test and assertion.
  Method note worth keeping: patching `structure.TAUTOLOGICAL_TITLE_SOURCES` would change BOTH signals at once and could not attribute a failure to the matched= line. Because gather does `from llama.structure import TAUTOLOGICAL_TITLE_SOURCES` it holds its own module-level binding, so rebinding `llama.stages.gather.TAUTOLOGICAL_TITLE_SOURCES` isolates the matched= line alone. Done via an out-of-tree pytest plugin (`-p` + PYTHONPATH), editing nothing in the worktree — no second writer.
  And the failure that nearly hid it: the plan owner's first attempt produced NO output because the plugin was not on PYTHONPATH — a silent no-op indistinguishable from a clean run. Carried into Task 4 as a hard requirement.
Task 3: complete (commits 83c2a62..a37bb83, review clean after 2 fix rounds; 3 Important + 4 Minor all addressed, 0 parked)

Task 4: dispatched 02:14 EDT, implementer on OPUS (Ruling 5 — prose harness spec + three-way hand triage + evidence doc is design work, not transcription), agentId a96db764e99bed532, BASE a37bb83. Child dir $D/task4; bulk output to an unprobed sibling work dir. Carries Rulings 6, 9 and 17, requirement C (prove the harness can return non-empty before believing any clean result), and the do-not-tune-toward-a-passing-number instruction.
Task 4: implementer DONE_WITH_CONCERNS (Opus). Commits 8ac7d77 (harness scripts/blind_tag_gapfill.py), 7e179a6 (doc docs/superpowers/2026-08-31-gap-fill-blind-test.md). Suite 1499 passed, 7 deselected at both commits; verified by me.
Task 4 measured: 968 cached items, 960 usable, 57,098 blinding trials, 15,118 firings, 6,864 distinct adoptions. Raw pre-triage wrong rate 9.13% (627 distinct). Hand triage of all 627: scorer-artifact 422, genuinely-wrong 108, genuinely-wrong/filler-segment 56, tag-typo-adoption-superior 41.
  Pooled genuinely-wrong 1.57% (108/6864); 2.39% including filler-segment — which lands on the spec pilot's own 2.4% interior / 1.5% edge, from a different instrument on a differently-built canonical.
  BY ANCHOR KIND: single n=6607 genuinely-wrong=107 (1.62%); merged n=257 genuinely-wrong=1 (0.39%). Interior 1.49%, edge 1.99%.

Ruling 7 / Ruling 9 OUTCOME — my R7 expectation was REFUTED BY MEASUREMENT, in the safe direction. The merged-anchor path is four times BETTER than the single-anchor path, not worse, and its single failure is not a merged-anchor failure at all: on `billystrings2021-08-14.Neumann` track 3 the canonical carries an extra item (`There Is a Time`) the tape does not, and the identical error reproduces at the same track with a SINGLE anchor when the blinded window starts one track later. The merged bind is incidental. Consequence: the reserved conservative tightening of `_merge_run`'s call site should NOT be applied — it would decline 257 adoptions to prevent one error a single anchor produces anyway. Keeping `_merge_run` (R7) was correct; the by-anchor-kind gate (R9, plan owner's hardening) is what turned an assumption into a measurement, and is the reason this is known rather than believed.

Task 4: NEW DEFECT found by the gate — the `--natural` run (blinding nothing, i.e. real shipping behaviour) makes exactly 2 adoptions across 960 items: one perfect (`Robot Jam`), one adopting a taper's thank-you sentence as a track title. Both are TRAILING-EDGE gaps, where `_hygienic` demonstrably fails because `_strip_head_banner` has no tail counterpart. Implementer's recommended fix is ~3 lines and strictly conservative: decline edge gaps whose span reaches the last canonical item. NOT dispatched — it changes shipped behaviour and sits inside the ship decision.
Task 4: the POOLED gate cannot be settled as written. The plan gates on "at or below the tag rung's own typo baseline", which has never been measured here and which this instrument cannot measure without circularity, because the tags ARE its ground truth. Bounds recorded: >=0.60% floor on the tag rung's own error rate; 6.5% of scored disagreements are the tag's fault. The implementer recorded the unresolvability rather than adjusting the measurement, and states it made no post-hoc threshold or class-boundary changes.
Task 4: escalated to the plan owner per Ruling 6 — ship unflagged / ship flagged / fix the trailing edge first is not mine to decide.
Task 4: task review dispatched (Opus), range a37bb83..7e179a6, briefed to attack the merged-anchor result hardest (n=257, one event, and it licenses NOT applying a reserved safety tightening).
Task 4: task review (Opus) — spec compliance PASS, task quality CHANGES REQUESTED (1 Critical, 4 Important, 6 Minor; all doc-level, instrument sound). Reviewer re-derived everything rather than reading: full 968-item sweep re-run, triage tables parsed and joined back onto a regenerated TSV, anchor pass independently re-derived and agreeing with the spy replay on 30,544/30,544 trials WITH a live negative control, requirement C mutation-tested both ways, trailing-edge fix actually applied and re-swept. It also applied non-empty discipline to its OWN negative results.
  CRITICAL C1 — the merged breakout labels a gap `merged` only via its IMMEDIATELY ADJACENT anchor, but the risk R7 identified is that a mis-bound merged anchor shifts every gap that FOLLOWS. Re-attributed on that mechanism the sign reverses: adjacent-merged 1/257 (0.39%), upstream-merged-only 7/304 (2.30%), no-merged 100/6303 (1.59%). Partition reconciles exactly to the doc's own 6,864/108. The 0.39% answered a different question than the gate was asking.
  IMPORTANT I2 — 1/257 vs 107/6607 is Fisher one-sided p=0.083, Wilson CI 0.07-2.17% overlapping single's 1.34-1.95%. "Passes decisively"/"four times better" overclaim from one event.
  IMPORTANT I3 — the trailing-edge fix measured: costs 318 distinct adoptions (4.6%), NOT the doc's implied 1,156/17% edge population; trades 265 correct titles for 11 genuinely-wrong (24:1); headline 1.57% -> 1.48%.
  IMPORTANT I4 — `edge` is a TRIAL property and 2,306 of 6,864 distinct adoptions carry both values; the 1,156/5,708 split is first-wins and the rule is unstated. Edge population ranges 672-1,594 under other rules.
  IMPORTANT I5 — judgement calls 1 and 2 are mutually inconsistent (bidirectionality proves "a shift" for reprises, but Drums<->Space, also bidirectional, is excused into the excluded subclass). Defensible headline is the RANGE 1.57-2.39%, both of which the doc does print.
  Minors m6-m11: an unrunnable `triage.py` command; Rulings 6/7/9 cited but findable nowhere (see below); ~5 merged-direction adoptions classed artifact under a rule covering only the opposite direction; the blind test bypasses the sibling rung; the extract_setlist LLM-canonical population is silently excluded; the 135 "unverifiable" adoptions are INDUCED by blinding.
  Reviewer's read on the three recommendations: (1) don't tighten _merge_run — NOT carried as stated; deferring is defensible since the one adjacent failure does reproduce under a single anchor, but declaring the question retired is not. (2) fix the trailing edge — CARRIED AND STRENGTHENED; all five bad adoptions sit at track == n_tracks, the fix kills all five and spares the good interior one. (3) pooled gate unresolvable — CARRIED; the most credible move in the doc. No evidence of post-hoc tuning; both available levers were taken conservatively.
Task 4: C1 escalated to the plan owner 02:53 — their ship ruling 1 (no _merge_run tightening) was made on the 0.39% figure and must be re-made on 2.30%. Fix dispatch HELD so it goes out as one dispatch covering the trailing edge plus every doc correction.
Note on Minor m7: "Rulings 6/7/9 findable nowhere in repo or SDD dir" is explained by this ledger living in gitignored `.superpowers/`. Copying it to docs/superpowers/2026-08-31-phase-a-sdd-ledger.md is a standing deliverable of this run and resolves m7.

Ruling 18 (unblocking C1): the fix round proceeds WITHOUT applying the `_merge_run` tightening, and the doc is corrected to record C1's re-attribution honestly and to stop declaring the merged question retired. — The plan owner ruled "do not tighten" and the reviewer independently concluded that deferring is defensible (the one adjacent failure does reproduce under a single anchor) while "declaring the question retired is not". So both authorities agree on the ACTION and differ only on what the doc may claim — which is a doc fix, not a code fix. Dispatching now on that basis avoids parking the run on a question whose answer does not change what gets built; if the owner later wants the tightening, it is a further round taken against a doc that finally tells the truth. — If wrong: the tightening lands one round later than it could have, on a corpus where its cost is now measured (318 distinct adoptions, 265 correct titles traded for 11 wrong) rather than assumed.
Task 4: fix round 1/5 dispatched — resumed original implementer (Opus), all findings verbatim, sentinel $D/task4/done2.
Ruling 18 SUPERSEDED by the plan owner's re-ruling on C1 (02:56). Outcome unchanged — no `_merge_run` tightening — but the REASON is the opposite of the one first given, and the doc must say so. The owner accepted C1 as their own error: they had accepted an answer to the wrong question, and the re-attributed partition SUPPORTS R7's mechanism rather than exonerating it. "Four times better" and "the gate exonerated it" are struck from the record. The doc must name the failure class in its own right — a gate answering a question nobody asked is subtler than not gating at all, and a gate must be defined over the mechanism it means to bound, not over what is easiest to label.
  Three reasons the outcome nonetheless stands: (1) BOTH directions are underpowered — 7/304 vs 100/6303 is ~7 observed against ~4.8 expected, so a 2.30%-vs-1.59% difference resting on seven events licenses a code change no more than one event licensed calling it safe; symmetric skepticism or none. (2) This project does not ship unmeasured knobs — the tail-guard constants carry their measurements in comments precisely so a constant nobody can re-validate does not become folklore, and a tightening justified by seven events would be exactly that. (3) DECISIVE: after the trailing-edge fix the rung makes ZERO natural adoptions, so a tightening would be a guard on a path that does not execute — dead code protecting dead code. The correct artifact is the measurement, not the mitigation.
  REPLACEMENT ARTIFACT: the doc carries a REACTIVATION CONDITION as a requirement — the merged-anchor question is OPEN, not settled; the partition is underpowered in both directions; and if the rung ever begins making natural adoptions on a future corpus, the merged-anchor error rate MUST be re-measured with adequate power BEFORE any adoption is trusted. The reserved two-line tightening is recorded in the doc as the prepared response so whoever re-measures need not re-derive it.
Ruling 19 (cost asymmetry, plan owner): the trailing-edge fix's 24:1 trade — 265 correct titles sacrificed against 11 genuinely-wrong prevented — is worth taking, and the doc must say WHY rather than reporting the ratio. A DECLINED title costs the operator one `--set-title` call. A WRONG title reaches the manifest, the ID3 tag and the air, with `briefing_guard` and emcee's `script_guard` both STRUCTURALLY BLIND to it, because each defines truth from the tracklist itself. Asymmetric costs justify a lopsided ratio. All five bad adoptions sit at `track == n_tracks` and the fix spares the good interior one, so it is targeted, not blunt.
Ruling 20 (ship, plan owner): Phase A ships UNFLAGGED and MEASURED INERT. After the trailing-edge fix the `--natural` run makes ZERO adoptions across all 960 cached items — not a low rate, zero; there are no natural interior count-forced gaps in this corpus at all. That settles flagged-vs-unflagged by removing the population: a review flag on a rung that never fires is noise infrastructure with no subjects. The rung is annotated with command, date and number the way `titles.py:129`'s dead rung is, so the next reader does not re-diagnose it as a bug. NOTE: no push and no merge — whether Phase A merges at all is the user's decision, not this run's.
Task 4: supplement sent to the live implementer 02:57 with the reactivation condition and the cost-asymmetry reasoning.
Task 4: fix round 1/5 — commits b1ca393 (trailing-edge fix in structure.py), 5f05dac (harness: upstream merged attribution, triage shipped as data), 967a5c1 (doc: withdraw two overclaims, measure what replaced them). Suite 1500 passed, 7 deselected; tree clean; verified by me.

Ruling 21 (resource-driven, mine): the Task 4 fix-wave scoped re-review and the final whole-branch review are COMBINED into a single Opus dispatch, rather than run as two. — The 5h meter is at 73% against an 80% band; two full Opus reviews would breach it and get the run killed mid-review, which is strictly worse than one review that completes. The final review's range (f785fe6..HEAD) already CONTAINS the fix wave, so the combined reviewer sees every line the scoped re-review would have seen; what is lost is only the separation of concerns, not coverage. — The cost if wrong is real and I am recording it rather than glossing it: the final reviewer is handed the Task 4 fix-round findings so it can verdict them, which means it is NOT independent of the prior reviewer's conclusions on that range. Per the delegation skill's own warning about compromised reviewer independence, its agreement on those specific points must NOT be counted as independent confirmation. Its whole-branch findings on everything else remain independent, since no prior verdicts on Tasks 1-3 are being handed to it.

Ruling 20 CORRECTED (plan owner, 03:12): Phase A does NOT ship "measured inert". After the trailing-edge fix the rung makes EXACTLY ONE natural adoption across the 960-item cache — `ymsb2010-07-17` t19 -> `Robot Jam` — which is CORRECT, INTERIOR (track 19 of 23), and untouched by the fix. A very small population, not an empty one, and that adoption recovers a title nothing else in llama could have produced. The "zero" originated in the first Task 4 report, was inherited without re-derivation, and was propagated by the plan owner into a ruling and into their report to the user before the implementer's re-sweep refused it.
  The C1 outcome SURVIVES on the corrected premise, with the implementer supplying replacement reasoning rather than leaving the broken one standing: the sole surviving adoption has `merged_attr = none` — that tape's only merged anchor sits at track 22, AFTER the gap — so a `_merge_run` tightening still would not touch anything that executes. Same conclusion, measured basis instead of a false one. The doc must carry the corrected version, NOT the "dead code guarding a dead path" phrasing.
  Ship framing everywhere must read "exactly one adoption across 960 cached items", never "inert" or "zero".
Task 4: FOR THE RECORD — an implementer refused a controller instruction because it had measured the opposite, and was right. That is the behaviour this protocol wants, not an exception to it. Two further signs the measurement was run honestly: it reclassified finding m8 in the direction that moved its OWN headline UP (1.57% -> 1.65%), and it held 922 against the review's 2,306 dual-valued edge figure on the grounds that 922 reconciles arithmetically.
Note: my final-review dispatch contained the false "measured inert" premise; corrected to the live reviewer at 03:13 and asked to verify the natural sweep itself rather than take either number on trust.

Task 4: complete (commits a37bb83..967a5c1, review clean after 1 fix round; C1 + I2-I5 + m6/m8-m11 + m7 + the trailing-edge fix + the reactivation condition ALL verdicted ADDRESSED, 0 parked)

FINAL WHOLE-BRANCH REVIEW (Opus, combined with the Task 4 fix-wave re-review per Ruling 21). Range f785fe6..967a5c1, 16 commits. Report: .superpowers/sdd/2026-08-30-title-correspondence/final-review.md
  JOB 1 VERDICT: APPROVE. NOTHING BLOCKS MERGE. Critical: none. All seven global constraints verified. Suite re-run by the reviewer: 1500 passed, 7 deselected.
  Test quality: SIX OF SEVEN source mutations the reviewer applied were caught by exactly the tests that name the property (trailing-edge branch, TAUTOLOGICAL_TITLE_SOURCES coverage exclusion, `is_junk_title` in `_hygienic`, the `_merge_run` anchor branch, gather's `matched` override, a one-item span shift). The seventh — removing the `if not items or not tracks` guard — failed nothing, confirming the deferred minor. The reviewer notes this is the project's own standard and "is not the usual outcome".
  Coherence: `matched` has exactly three consumers (cli.py 663/665/667, all already three-state); `coverage` has exactly one behavioural consumer (`align_coverage_threshold`) plus the show.json audit record. Nothing breaks or misleads.
  Deferred Task-1 minors: NONE must be fixed before merge. Two were already fixed in later tasks (junk-title coverage, merged-anchor comment), both mutation-verified.
  Three Important findings, none blocking: I-A CLAUDE.md:325 and docs/workflow.md:186 both enumerate the title cascade and neither mentions the new `setlist-gap` rung or the TAUTOLOGICAL_TITLE_SOURCES semantics, and no plan task schedules it — doc debt that should accompany merge. I-B the shipped code declines EVERY trailing-edge run while the approved spec authorizes edge adoption on either end; evidence-backed and conservative, but a spec narrowing the owner should ratify explicitly rather than absorb. I-C M2 (the full-library re-gather no-op gate) is Task 9 and is unrun; substantively mitigated — adoption touches only unresolved tracks, the natural sweep changes 1 track in 960 cached items and that item is not a library show, and the census shows 0 setlist-sourced tracks so no live show flips.
  New evidence the reviewer generated that the doc lacks, supporting I-B's asymmetry: the SURVIVING leading-edge population (n=837) is 1.43% strict / 1.55% incl-filler genuinely-wrong, versus 1.56% / 2.50% for everything else — the retained head branch is measurably not the weak side.
  Honesty check on the inertness claim: the reviewer re-ran `--natural` at HEAD and got exactly 1 adoption (`ymsb2010-07-17` t19 -> `Robot Jam`, interior, correct). The false "zero" was in MY dispatch; the branch itself never claims it, and the doc says "very nearly inert... one adoption" with a dated re-run command.
  Both of my verification asks came back CONFIRMED: reverting m8 in a copy of the triage file reproduces the prior review's figures exactly (108/1.57%, upstream 7/304=2.30%, none 100/6303=1.59%), so the doc's higher headline is the same data plus a reclassification that moved its own number UP; and 922 is correct while the prior review's 2,306 is not reproducible under the harness's stated distinct key (1,594 - 672 = 922 reconciles definitionally).
  Per Ruling 21, only two Job-2 verdicts rest on judgement shared with the prior reviewer (whether `upstream` is the right mechanism proxy for C1, and choosing "state the tension, publish the range" for I5). Everything else was re-derived. Job 1 findings on Tasks 1-3 are fully independent.
PHASE A COMPLETE. Tasks 5-9 (Phases B and C) deliberately not started.

## Phase B pre-flight scan (orchestrator, 2026-08-31)

Baseline measured: `./.venv/bin/pytest -q` -> **1500 passed, 7 deselected** @ 33b4eaf.
(Plan's recorded 1479 was pre-merge; +21 from Phase A.)

| # | Rows checked | Finding |
|---|---|---|
| P1 | T5 produces `correspondence.propose_titles`/models; T6 consumes+extends same module | agree. `correspondence.py` absent, `models.py` has no TitleProposal — clean create. |
| P2 | T6 produces `gather.build_canonical`; T7 consumes it | agree. |
| P3 | T6 produces `sibling_item_durations`; T7 consumes it | agree. |
| P4 | T7 produces `--suggest-titles` render+write path; T8 consumes it as a shared helper | agree, but T8's text says "reuse ... from Task 6" — the code it describes is in **Task 7**. |
| P5 | T7 self-consistency: test helpers vs existing test file | **CONFLICT.** `test_cli.py` imports only `Path`, `CliRunner`, `llama.cli.app`. `FIXTURES`, `StubIA`, `FakeProvider`, `run_gather`, `ShowWorkspace`, `_ymsb_candidate`, `read_overrides` do NOT exist there. |
| P6 | T6 self-consistency: `test_build_canonical_makes_no_llm_call_without_a_provider` | **CONFLICT.** Constructs `FakeProvider()`, never passes it, asserts `not fake.calls`. Vacuously true — asserts nothing. |
| P7 | T7 self-consistency: asserted proposal values vs fixture | Unverifiable pre-flight: `len(ov.titles)==22`, `ov.titles[1]=="Granny Woncha Smoke Some > Ride The Wild Turkey"`, fillers at 11/22 are empirical claims about the ymsb fixture crossed with the DP. |
| P8 | T9 Step 1 (M2) vs repo state | **ALREADY DONE.** `scripts/regather_diff.py` exists; evidence doc carries "## M2: full-library no-op check (2026-08-31)" at line 1128, landed in 1f02dcb. |
| P9 | T5/T6 vs Global Constraints | agree. No new deps; `parse_setlist` untouched; DP is proposal-only; no scoring gates an automatic adoption. |
| P10 | gd73 fixture trap (6 files vs 6 items) | Not triggered by T5-T9 tests — none needs an unresolved run on gd73. |

Ruling: P4 — read Task 8's "Task 6" as **Task 7**. Task 7 is the task that produces the render+write path; Task 6 produces `build_canonical`/`sibling_item_durations` and has no rendering. Cost if wrong: Task 8 extracts the wrong helper, caught immediately by its own test.

Ruling: P5 — Task 7's implementer **builds the missing helpers in `test_cli.py`**, importing them from where they already live (`herder.FakeProvider`, `llama.workspace.ShowWorkspace`, `llama.stages.gather.run_gather`, `llama.overrides` reader) and copying `StubIA` from `test_stage_gather.py` rather than inventing a second one. Cost if wrong: duplicated stub drifts from the gather one; bounded, and the reviewer sees both.

Ruling: P6 — the vacuous assertion is **replaced, not transcribed**. The constraint (`provider=None` can never reach an LLM) is pinned by monkeypatching `llama.stages.gather.run_json_task` to a raiser and calling `build_canonical(..., provider=None)` on input where the fallback *would* otherwise fire, **plus a positive control** proving that same input DOES reach the raiser when a provider is passed. A check that cannot return non-empty is not a check. Cost if wrong: more test code than the plan asked for; the constraint is the hard one from the dispatch brief, so over-pinning is the safe direction.

Ruling: P7 — if the DP's real output disagrees with the plan's asserted numbers, the implementer **reports the measured values with the fixture evidence and does not tune the DP to fit the assertions**. Adjusting the test to measured truth is allowed only when the proposal is verifiable as correct against the fixture's own description text; otherwise it is a finding. Cost if wrong: a wrong expectation is pinned; mitigated because Task 9/M3 re-reviews this exact show by hand.

Ruling: P8 — Task 9 is **re-scoped to Step 2 (M3) + Step 3 (record M3 only)**. M2 is not re-run; the orchestrator verifies the recorded M2 section and reports the delta. Cost if wrong: an M2 result goes stale relative to Phase B code — but Phase B adds no automatic adoption, so re-gather output cannot move. Re-checked at final review.

Task 5: BLOCKED on round 0 — implementer transcribed the brief byte-for-byte and
`test_margins_are_reported_per_row` fails against the brief's OWN implementation.
Traced: forbidding either row's span makes the whole assignment infeasible (no
segue means nothing can absorb the orphaned item), so `alt == inf` and both rows
get `margin_sec = None`. Not a transcription error — a gap in the plan's algorithm.

Task 5: Ruling: `margin_sec` conflates three distinct states behind one `None`.
Decided — `float("inf")` when no alternative assignment exists (the row is
FORCED), `None` only for filler rows (margin is not applicable to a track that
consumes no item), a number otherwise. Rationale: the spec (lines 250-255) makes
margin a DISPLAY column of the proposal table and nothing else — "No margins and
no scoring" binds Piece 1's automatic adoption, not Piece 2's rendering — so this
cannot affect any adoption decision. A forced row is the *most* certain outcome
available (it is the same count-forced condition Phase A treats as its strongest
evidence class); reporting it as `None` renders it in Task 7's table as `-`,
identical to no-information, which is exactly backwards. Neither the test
assertion nor the DP's cost model is touched: this changes only how the
already-computed `alt == _INF` case is reported.
Carried into Task 7: the renderer must print `forced` for an infinite margin, not
`f"{inf:5.0f}s"`.
Cost if wrong: the table reads `forced` where an operator expected a number —
display-only, trivially reversible, and M3 hand-reviews all six held shows, which
is the gate that would surface it.

Task 5: Ruling REVISED by the root, and the revision is correct. My `float("inf")`
carrier is defeated by pydantic's default `ser_json_inf_nan="null"`. Verified
independently in the worktree venv (pydantic 2.13.5): a forced row and a filler
row dump to BYTE-IDENTICAL JSON (`"margin_sec":null` in both), and
`model_validate_json` round-trips the forced row's margin back to `None`. So `inf`
silently collapses the two states I had just separated, at the first
serialization boundary.
Revised: `ProposalRow` gains an explicit `forced: bool = False`; `margin_sec`
stays numeric-or-absent. Task 7's renderer reads `forced` off the flag, never off
an `inf` comparison — which would also degrade to a `None` check past any
serialization boundary.
Consequence I must own: the brief's `test_margins_are_reported_per_row` asserts
`all(r.margin_sec is not None ...)`, and under the revision a forced row's
`margin_sec` IS `None`, so that assertion now contradicts the representation.
Ruling: the assertion is amended to `r.margin_sec is not None or r.forced` —
which is what "margins are reported per row" always meant, now that the reporting
has two carriers. This is the one place a plan test assertion is edited in Phase B,
and it is edited because the representation changed under it, not to make a red
test green. Plus a NEW test pinning the thing the root measured: a forced row and
a filler row must remain distinguishable across a JSON round-trip.
Cost if wrong: a bool on a proposal model, display-only; the round-trip test is
the regression pin that would catch any future collapse.

Task 5: review 1 (Opus) — spec ✅ compliant; task quality NEEDS FIXES. 0 Critical,
5 Important, 1 Minor. Reviewer mutation-tested rather than reasoned, and two
findings land on MY OWN ruling's regression pin:
  I1 the JSON round-trip test hand-builds rows and never calls propose_titles, so
     reverting the producer to the inf sentinel passes all 7 tests (mutation-run).
  I2 the margin computation is entirely untested — replacing it with an
     unconditional (None, True) also passes all 7 (mutation-run).
  I3 the amended assertion is true for its fixture but FALSE in general (a filler
     row has margin_sec=None and forced=False); assert the trichotomy instead.
  I4 my "most certain outcome the DP can produce" comment on `forced` is an
     overclaim the spec's own measurement contradicts — forced means structurally
     rigid, not correct, and the plain 2x2 no-segue case marks every row forced
     while being exactly the 45-52%-wrong unanchored regime.
  I5 `item_durations` length is never validated against len(items); a short list
     silently truncates into a wrong-but-plausible table, which is the one failure
     an operator cannot audit in a human-confirmation flow.
Ruling: all five enter the fix loop. I4 is the one I most want fixed — I wrote the
overclaim, it sits one task upstream of the operator-facing table, and Piece 2's
entire safety argument is that a human reads that table. Adopt the reviewer's
replacement wording.
Minor M1 (deferred): `fuzzy_norm_title` imported unused in correspondence.py.
DEFERRED not fixed — Task 6 adds `sibling_item_durations`, which genuinely uses it;
removing it now just means Task 6 re-adds it. Re-check at final review that Task 6
did make it live.

Task 5: fix round 3/5 (5 addressed, 1 new open — trichotomy pin is filler-blind;
commits 3fa074c..c9612d6). Re-review (Opus) independently re-ran both cited
mutations and confirmed each now fails, then ran a THIRD mutation of its own:
a producer setting forced=True on filler rows passes all 9 tests. The
forced/filler collapse this whole three-round chain exists to prevent is still
unpinned at the producer, because the trichotomy landed in the one fixture with
no filler row. One-line remedy, verified green by the reviewer.

Task 5: Ruling: fix round 4 stays on the SAME Sonnet implementer rather than
escalating to a fresh Opus one. The skill escalates at round 4 because "a loop
that survives three resumes usually means the implementer cannot see its own
problem" — that rationale does not hold here. Every round addressed everything
asked of it (confirmed by an independent re-review that re-ran the mutations
rather than trusting the report); each new finding came from a NEW check I
ordered, not from the implementer failing to see a standing one. Escalating a
verified one-line test move to a more capable model buys nothing.
Cost if wrong: one line of test code written by the cheaper model, and it goes
straight back through a scoped re-review that has already demonstrated it will
catch exactly this class of gap.
Minor (deferred): `correspondence.py:25`'s "1 entries" grammar, pinned by a
`pytest.raises(match=...)` so the wording is load-bearing — cosmetic, deferred to
final review.
Carry into Task 7: the re-review notes `forced` will be the COMMON case in
production (a no-segue setlist makes every row forced), so the proposal table's
margin column will mostly read `forced` rather than a number. The renderer must
not let that read as high confidence.

Task 5: fix round 4/5 (2 addressed, 0 open; commits c9612d6..e5669c7). Re-review
APPROVED: trichotomy pinned at two sites (added, not moved), citation now by
section name, the filler-forced mutation caught with a pre-fix control proving the
gap was real, and harness shadowing proved by a planted sentinel rather than
inferred from a green count.
Task 5: complete (commits 33b4eaf..e5669c7, review clean). Suite 1509 passed,
7 deselected via `./.venv/bin/pytest -q`, verified by the orchestrator.
Carry into Task 6/7: `propose_titles` has NO production caller yet, so
test_correspondence.py is the sole exerciser of the forced/filler trichotomy —
re-check the invariant holds once a real caller lands.

Task 6: implementer DONE (commit 39e0339). Suite 1512 passed, 7 deselected
(1509 + 3 new, zero regressions), verified by the orchestrator.
Two concerns raised by the implementer, both routed to review rather than
accepted on report:
  C1 the brief's signature was underspecified — `run_gather` also needs the
     winning parse's `source` for `StructureInfo.source` (pinned by 4 existing
     assertions), unreconstructable from (canonical, notes). Solved with an
     additive optional `source_out: dict | None` OUT-PARAMETER that the function
     mutates. A mutable out-param is a smell; reviewer asked to judge it against
     a 3-tuple / NamedTuple / carrying source on the returned object, and told
     explicitly that the brief's 2-tuple test is amendable and is NOT a reason to
     accept a worse interface.
  C2 the jerrybase `events` computation was REORDERED to run before the
     build_canonical call. Reviewer asked to verify the no-dependency claim
     against the code rather than accept it — a green suite cannot prove a
     behaviour change the tests do not cover.

Task 6: review 1 (Opus) — spec ✅ compliant; task quality NOT APPROVED.
0 Critical, 3 Important, 4 Minor.
  C2 ANSWERED: the events reorder IS behaviour-preserving, verified by static
     data flow and shown to be FORCED (build_canonical takes events as an
     argument), not incidental. No finding.
  C1 ANSWERED: the reviewer would NOT ship `source_out`. A caller that forgets
     it silently loses provenance.
  I1 `sibling_item_durations` is entirely unpinned — replacing the whole body
     with `return None` leaves the suite fully green. The one new test passes
     `ia=None` and returns on the first line, never reaching the donor loop, the
     uniqueness refusal, or the length invariant, despite its name. This is the
     project's own recorded "green suite != pinned" failure mode, in a function
     Task 7 depends on.
  I2 CORRECTNESS: the docstring's uniqueness invariant is not enforced in the
     direction that matters. The donor is refused when the DONOR repeats a title,
     but when the CANONICAL repeats a song and the donor names it once, the donor
     is ACCEPTED and one duration is handed to both items. Measured. That is a
     positional guess — precisely what the function's stated safety story says it
     refuses to make — and it silently corrupts the DP's cost model.
  I3 `source_out` → NamedTuple return.
Ruling: all three Important enter the fix loop, and I additionally pull Minors
M1, M3 and M4 into the same round rather than deferring them. M1 is normally a
deferred minor, but the reviewer MEASURED that deleting the entire cleaning pass
leaves `test_build_canonical_matches_what_gather_uses` green while failing four
pre-existing gather tests — so the one test written to protect a
behaviour-preserving extraction does not protect it, and the task's whole claim
rests on tests that predate it. M3/M4 are one-liners in files already open.
Acceptance criterion for M1 is stated as a mutation, not a mechanism: the test
must FAIL when the cleaning pass is deleted.
Minor M2 (deferred): `except Exception: continue` around the donor fetch swallows
bugs in `filter_files`, where `_collect_parses` next door catches `IAError`
specifically. Brief-specified and inherited; deferred to final review.
Cannot-verify carried to Task 7: the production yield of `sibling_item_durations`
is unmeasured, and this project has a history of rungs alive on the gd73 fixture
and near-dead in production. Task 7 must not assume the sibling path fires.

Task 6: fix round 1/5 (6 addressed per implementer, re-review pending; commits
39e0339..08f0e33). Suite 1519 passed, 7 deselected, verified by the orchestrator.
Implementer proved shadow-copy shadowing with a planted `RuntimeError:
SENTINEL-SHADOW-PROOF` before trusting either mutation, and reports both caught.
Note: it also recorded that the FIRST version of its M1 test passed 3/3 against
the cleaning-pass mutation before a description-construction fix — i.e. it caught
its own vacuous pin. Re-review asked to confirm which tests go red under the
cleaning-pass mutation, since M1's whole point is that the NEW test must fail,
not merely the four pre-existing ones.
Minor process deviation (noted, not escalated): the implementer put its mutation
shadow copy under `$D/task6-work/` rather than the unprobed `$W`. Outside the
probed per-child dir, so the write-age signal stayed clean (files=4 throughout);
no monitoring harm.

Task 6: re-review APPROVED. All six findings ADDRESSED with independent mutation
evidence, each naming the test that catches it; the reviewer proved shadowing on
BOTH mutated files before trusting any result, and reported that none of the
implementer's verification claims were overstated. Key confirmations: (b) the
cleaning-pass mutation fails `test_build_canonical_applies_the_cleaning_pass`
specifically, not merely the 4 pre-existing gather tests — M1's whole point; and
forcing `CanonicalBuild.source = None` fails 12 tests, so provenance is genuinely
threaded rather than renamed.
Task 6: complete (commits e5669c7..08f0e33, 1 minor parked). Suite 1519 passed,
7 deselected via `./.venv/bin/pytest -q`, verified by the orchestrator.

Task 6: parked — N1 (Minor): `test_sibling_item_durations_refuses_a_zero_length_
donor_track`'s docstring claims to pin the `> 0` arm, but mutating `> 0` -> `>= 0`
is a no-op because `junk.filter_files` drops zero/missing-length files upstream,
so the test is a behavioural duplicate of the partial-donor case.
Ruling: REAL but deferred, not fixed in-loop. The shipped CODE is correct — the
`> 0` half is unreachable defensive code — so nothing downstream builds on the
gap; what is wrong is a docstring asserting a pin that does not exist. That is the
same class this repo's own `green-suite-does-not-mean-pinned` memory warns about,
so it goes to the final review's fix wave with the rename/fold options recorded,
rather than being silently discarded. Cost if wrong: a misleading test name
survives to merge.
Task 6: deferred minor — O1: deleting ONLY `_drop_artist_items` leaves the whole
suite green (even `test_gather_drops_setlist_items_that_are_the_artist_name`),
because `_strip_head_banner` masks it. PRE-EXISTING, not introduced by Phase B.
Flagged to the final review.
Task 6: deferred minor — M2: `except Exception: continue` around the donor fetch
swallows `filter_files` bugs where `_collect_parses` catches `IAError`. Inherited
from the brief.

Orchestrator action: the re-review's O3 caught a defect in the TASK 7 BRIEF before
it could be dispatched — `task-7-brief.md:93` still read `canonical, _ =
build_canonical(...)`, which now raises `ValueError: too many values to unpack`
against Task 6's NamedTuple return. Brief patched in place to
`build_canonical(...).setlist`, with an appended amendment note recording why.

Task 7: implementer DONE (commit 9bbdc0a). Suite 1522 passed, 7 deselected
(1519 + 3 new), verified by the orchestrator.
The brief's empirical assertions HELD: 22 titles (24 tracks - 2 filler), track 1
== "Granny Woncha Smoke Some > Ride The Wild Turkey", fillers at 11 and 22. The
P7 ruling's escape hatch was not needed.
Two brief-spec bugs found and fixed, both reported as verified-against-real-code
rather than guessed, and routed to review rather than accepted on report:
  B1 the "unusable canonical" staging helper crashed as literally written --
     `FakeProvider()` with no queued response, hit by build_canonical's LLM
     rescue. Fixed by staging with provider=None, which is what the CLI path
     itself always uses.
  B2 the asserted infeasibility message ("no consistent correspondence - parse
     quality too low") is UNREACHABLE for an empty canonical setlist; the real
     message is "no usable canonical setlist". Assertion corrected,
     correspondence.py left untouched. Reviewer asked to confirm this is genuine
     unreachability and not an assertion relaxed to match observed output, and to
     check whether the OTHER infeasibility message is reachable and tested at all.
Self-disclosed gap routed to review: the `forced` rendering branch is not
exercised by any assertion, because the ymsb fixture never produces a forced row.
Given that `forced` is expected to be the COMMON case in production and this task
chain has repeatedly found branches that looked pinned and were not, the reviewer
is asked to rule on whether that is acceptable.

Task 7: review 1 (Opus) — spec ✅ compliant; task quality APPROVED with 3
Important + 8 Minor. Proposal-only + human-gate constraint verified by branch
trace: no path writes a title without typer.confirm returning true, and
build_canonical is called with provider=None.
Q1 answered: the `forced` render branch is UNPINNED (mutation-verified) — the
ymsb fixture never produces a forced row. Q2: BOTH brief-spec corrections
independently verified; the unreachability claim is genuine, not an assertion
relaxed to fit. Q3: the adopted titles are correct against the DESCRIPTION TEXT,
not merely self-consistent — so a uniform shift is ruled out. Q4: the Task 8 seam
is reusable.
  I1 the three early exits silently discard co-specified edit flags at exit 0.
     `fix X --suggest-titles --set-venue Fillmore` on a DECLINED proposal exits 0
     with overrides.venue still None — demonstrated empirically. Worst case is
     `--suggest-titles --overrule`, where exit 0 reads as "hold cleared" when it
     was not. Brief-prescribed, but `fix`'s own docstring advertises combos.
  I2 `--suggest-titles` + `--exclude`/`--unexclude` can SILENTLY MISLABEL: the
     proposal is computed over the current track list, but a same-invocation
     exclusion renumbers tracks while overrides.titles is applied by 1-based
     position. Out-of-range keys raise, but any key below the new count lands on
     the wrong track with no flag — the exact silent-wrong-title failure this
     whole design exists to prevent.
  I3 adopted titles carry the description's FOOTNOTE MARKERS verbatim
     (`Polly Put The Kettle On * ^`, `Get Me Outta This City # %`, ...), and
     inconsistently — a bare trailing `*` is stripped elsewhere. These flow into
     overrides.titles -> manifest v3 -> ID3 TIT2 -> packaged_filename -> briefing
     -> emcee's script.
Ruling: I1, I2 and the Minors enter the fix loop. M10 is ELEVATED out of Minor —
`parsed_titles.update(picks)` runs after --set-title parsing, so a proposal
overrides an operator's EXPLICIT `--set-title 3="Real Song"`. Explicit operator
input must beat a generated proposal; that is the same human-authority principle
the confirmation gate exists to protect, so it is not cosmetic.
Ruling: I3 is NOT fixed in this task and is NOT silently parked — ESCALATED to the
root as a scope question. It is real and it degrades the M3 gate (the spec expects
ymsb2005-12-31 to render "the exactly-correct 24 rows"). But the reviewer is right
that the cleaning belongs upstream in build_canonical's cleaning pass, and that is
the fork: fixing it there changes the canonical for EVERY gather run, which can
move existing shows' titles and so puts M2's full-library re-gather no-op result
at risk; fixing it only in the proposal path leaves Phase A's already-shipped
setlist-gap rung emitting the same markers. Neither branch is mine to choose
unilaterally — one risks a ratified gate, the other ships a known inconsistency.
Cost if wrong to defer: M3 renders nine titles with footnote residue and the
operator sees it at the gate, which is the cheap place to see it.

Task 7: fix round 1/5 (9 addressed per implementer, re-review in flight; commits
9bbdc0a..5261f8b). Suite 1529 passed, 7 deselected, verified by the orchestrator.

I3 ESCALATION RESOLVED by the root: fix UPSTREAM in build_canonical's cleaning
pass, gated on a differential measurement, NOT defer-to-M3. Reasoning recorded:
the markers are description apparatus, never part of a song's name, and a `#` in
an ID3 TIT2 frame is wrong at every sink; proposal-path-only would knowingly ship
a second copy of a defect the already-shipped setlist-gap rung emits; and
defer-to-M3 fixes nothing, since the operator still hand-edits 7 of 22 rows after
confirming, which is most of the "24 calls become one" value.
Root's CORRECTION, which changes the plan: **re-running M2 as-is does not measure
this change.** `scripts/regather_diff.py` is a differential over `adopt_gap_titles`
wired vs monkeypatched-to-no-op; a cleaning-pass change moves BOTH ARMS
IDENTICALLY, so the harness would report a clean no-op while the canonical shifted
underneath it. Structurally blind — the metrics-are-blind-at-their-own-boundary
trap this project has hit before. A second differential arm (strip-on vs
strip-off) is required.

PREDICTION PRE-REGISTERED with a third-party registrar (a different agent, which
did not author it), against commit 5261f8b, per the "an agent must not hold its own
sealed envelope" rule: stripping trailing footnote markers will change ONLY track
`title` text, and will NOT move `matched`, `set`, `title_source`, set breaks,
coverage, or alignment output on any show. Mechanism, measured by the orchestrator
before registering: `fuzzy_norm_title` ALREADY discards these characters — all six
marked/unmarked pairs normalize identically (`'Get Me Outta This City # %'` and
`'Get Me Outta This City'` both -> `'get me outta this city'`), so matching cannot
observe the strip. Abort condition registered IN ADVANCE of seeing any number: any
movement in the abort set stops the run and escalates rather than being ruled on
locally.

Task 7: Ruling on M9 (root-suggested, adopted): pin the THREADING, not the
behaviour. The real regression risk is someone dropping the `setlistfm=` argument
and silently reverting the proposal path to an LMA-only canonical — invisible
offline, since this suite's autouse fixture keeps SETLISTFM_API_KEY unset so
`make_client` returns None everywhere and no test reaches the non-None path. A
call-argument assertion (monkeypatch `build_canonical`, assert it receives what
`make_client` returned plus the jerrybase events, sentinel object standing in for
the client) catches exactly that with no setlist.fm fixture, no network, no new
stub. Building a full setlist.fm stub to test behaviour no other test exercises is
a larger scope expansion than this phase should absorb.
Deferred to fix round 2 rather than committed now: the Task 7 re-review is in
flight against 9bbdc0a..5261f8b, and committing under an in-flight reviewer is the
shared-surface hazard the delegation skill warns about.
Standing caveat to carry into the evidence doc: setlistfm=None throughout means
the strip-on/strip-off differential is a BOUND, not a replica of production.

Task 7: re-review — ALL findings ADDRESSED (I1, I2, M4, M6, M7, M8, M9, M10, M11),
no new Critical/Important breakage. Human gate re-verified intact: the if/elif/else
cannot reach the adopt branch without typer.confirm returning True, `adopted` is
set only in the confirmed branch, and provider=None is still unconditional.
Reviewer proved shadowing before mutating, reproduced the M4 mutation exactly, and
confirmed the I1 fall-through picks the RIGHT redo stage by observation
(`--suggest-titles --overrule` on a decline emits `--from package`, not the
`gather` a leaked parsed_titles would have produced). I2 confirmed not over-broad.
M9 was addressed BEYOND the ruling — the implementer threaded the real
`make_client(config)` and real jerrybase events rather than merely documenting the
divergence, and the reviewer cross-checked that the artist/date lookup keys match
run_gather's rather than merely looking similar.
New Minor: `_propose_titles_for_show`'s new docstring claims the proposal canonical
"matches what the gather redo will use", but `kept` is still not exclusion-filtered,
so on a show with prior exclusions it can rank a different winning parse via
`rank_parses(target_count=len(kept))`. Ranking difference, not a wrong-title
mechanism — but I2's OWN remediation message ("run the exclusion first, then
--suggest-titles") routes operators into exactly that state, which is what makes it
worth fixing rather than deferring.
Still open: the M9 THREADING is unpinned — `grep` finds no make_client/setlistfm
reference in test_cli.py, and the autouse fixture keeps SETLISTFM_API_KEY unset so
no test reaches the non-None path.

Ruling: BATCH Task 7's two residuals with Task 8 into ONE dispatch, reviewed as one
unit, rather than running a fix round and then a Task 8 round over the same lines.
Task 8's mandated `_format_proposal_row` extraction refactors exactly the region
the `kept` Minor lives in, and Task 8 also owns the deferred M5 pin (the `forced`
render branch). Splitting them means two edits to the same code with a review
sandwiched between, and the second edit would rewrite the first.
Cost if wrong: one larger review surface instead of two small ones; mitigated
because the findings are enumerated individually and the re-review verdicts each
one separately.

Meter: root overrode the 70% stop band for the 17:53-20:09 window specifically,
on reset timing (5h at 60%, burn ~26%/hr, window resets 20:09 — the reset arrives
before any wall). Band applies again on its own terms in the new window. 7d at 31%
with ~58h runway, not binding.

I3 CONTROL REQUIREMENT (root, and it is the decisive one): because the mechanism
check came back CONFIRMED, an empty abort set is now the PREDICTED result — which
makes it weak evidence on its own. An empty differential is what you would see
BOTH if the strip is genuinely inert to matching AND if the harness never
exercised the changed code at all. So: before believing the empty answer, PROVE
THE HARNESS CAN RETURN NON-EMPTY — plant a deliberate canonical mutation the diff
must catch (rename a canonical item outright), confirm the differential goes red,
revert, then run the real strip-on/strip-off arms. This is the same
sentinel-shadowing discipline the implementers have been using on mutation checks,
applied one level up at the corpus harness. Without that control, "clean no-op"
and "measured nothing" are the same output — which is exactly the
metrics-are-blind-at-their-own-boundary trap that made re-running M2 useless here
in the first place.

Task 8 (batched with Task 7 residuals): implementer DONE. Commits b5b9f05 (A1/A2/A3)
and cf35b08 (triage resolution). Suite 1536 passed, 7 deselected (1529 + 7 new),
verified by the orchestrator.
Task 8: Ruling on the triage keystroke: UPHOLD the implementer's `t`, against the
brief's literal `s`. Verified the premise myself rather than accepting it —
`cli.py:697` `RESOLVE_PROMPT = "... / [s]kip / [q]uit"` and `cli.py:780`
`typer.prompt(RESOLVE_PROMPT, default="s")`, so bare Enter IS skip. Binding `s` to
suggest-titles would make a blank Enter silently fire title suggestion on every
held unresolved show — a destructive default on exactly the population this
feature targets. The brief's step-1 snippet (`prompts = iter(["s","y","q"])`) was
written without noticing the existing binding; that is a plan defect and `t` is
its correct resolution.
Cost if wrong: the docs and the plan's snippet name a different key than the code;
cheap to change, and the alternative is a footgun on the default keystroke.
Task 8: implementer self-flagged that A1 (exclusion-filtering `kept`) has NO
dedicated regression test — every existing fixture has an empty overrides.exclude,
so it is only indirectly exercised. Routed to review rather than accepted.

Task 8: review 1 (Opus) — spec ✅; task quality NEEDS FIXES. 0 Critical, 1
Important, 4 Minor. Confirmation invariant re-verified across BOTH entry points by
mutation (bypassing the confirm fails tests on each surface); the helper is
genuinely shared, not duplicated-and-currently-identical; provider=None holds at
the single shared call site; A3's trichotomy pin binds (sole catcher named).
The `t` keystroke ruling was independently re-verified by the reviewer and upheld.
  I1 A1 is COMPLETELY UNPINNED — deleting the three-line exclude filter leaves
     1099 tests passing. Ruling: I OVERRULE the implementer's "heavier
     fixture-construction than the severity warrants" judgment, on both halves.
     Severity: an unfiltered `kept` makes the proposal's canonical differ from the
     redo's, and overrides.titles applies by 1-based POSITION, so a different
     winning parse means confirmed titles landing on the WRONG TRACKS — the same
     silent-wrong-title class the feature exists to prevent, and the identical
     hazard its own I2 guard refuses to risk. Cost: the A2 spy pattern built in
     the same commit makes it ~20 lines, and the reviewer wrote AND validated the
     test (green on shipped code, red with the filter removed).
Ruling: I am placing the PHASE-LEVEL DOCS GAP in this round rather than leaving it
to the final review. No Phase B commit touches docs/, the plan has no docs task,
and `docs/workflow.md:535-550` enumerates the triage prompt exhaustively — so it
is now factually stale, not merely incomplete. Folded in with it: Phase A's
still-unfixed I-A finding (neither CLAUDE.md's cascade paragraph nor workflow.md
mentions the `setlist-gap` rung or TAUTOLOGICAL_TITLE_SOURCES). Same files, same
pass, one review.
Task 8: parked — the rendered table omits the per-row `evidence` column though the
spec's table lists it; only `prop.evidence_source` prints, in the header. Task 7
scope, surfaced late by the A3 extraction. Ruling: real but deferred — it is a
display omission, the header already names the evidence source for the whole
proposal, and no adoption decision reads it. Cost if wrong: an operator sees one
evidence label instead of per-row ones at M3.

Task 8: fix round 1/5 (5 addressed, re-review NOT yet run; commits cf35b08..fa62e47).
Suite 1537 passed, 7 deselected, verified by the orchestrator.
  I1 A1 pin landed and MUT4-verified by the implementer: fresh scratch copy,
     shadowing proved with a planted RuntimeError FIRST, sentinel reverted, then
     the reviewer's exact three-line deletion applied — failure output matches the
     reviewer's predicted `AssertionError: 'ymsb2005-12-31d01t01.mp3' not in [...]`
     exactly.
  M1 solved better than asked: rather than appending `[t]` to a one-off pre-loop
     echo, the implementer added RESOLVE_PROMPT_WITH_TITLES selected per show and
     passed into typer.prompt on EVERY iteration, so it survives any `continue`.
  M2/M3/M4 landed; docs split into its own commit (fa62e47) covering
     --suggest-titles, the [t] resolution, and Phase A's inherited setlist-gap /
     TAUTOLOGICAL_TITLE_SOURCES doc debt.

RUN PAUSED at fa62e47 on the 5h usage band. The root's earlier override was VOIDED:
it rested on "the reset arrives first / sixteen minutes from now", but 20:09 was
2h16m out at 17:53, and measured burn (60% -> 74% in 22 min ~= 38%/hr) put
exhaustion ~70 minutes BEFORE the reset. Root confirmed the error and directed
option (a): stop here. Branch is green, committed, clean — a cheap place to pause.
REMAINING WORK, in the root's required order for the resumed run:
  1. I3 footnote strip in build_canonical + the strip-on/strip-off differential,
     WITH the non-empty control (plant a canonical mutation the diff must catch,
     confirm red, revert, then run the real arms). Correctness-gating; must not
     land unmeasured.
  2. Task 8 scoped re-review (Opus) of cf35b08..fa62e47.
  3. Task 9 = M3 only (M2 already ratified in 1f02dcb; re-running it as-is would
     be blind to the strip anyway).
  4. Final whole-branch review (Opus, most capable).
Rationale for that order: a merge can wait on a review, but the strip cannot land
unmeasured.

=== I3: ABORT-SET-MOVED. ESCALATED, NOT RULED ON. ===
Commits 90f8f9f (strip + 5 unit tests) and 2706af2 (scripts/footnote_strip_diff.py).
Suite 1542 passed, 7 deselected — run by the orchestrator, not carried forward.
Evidence doc deliberately NOT written, per the stop instruction.

CONTROL (ran FIRST, went red as required): `--selftest` renames every canonical
item outright. 89/89 shows, 2742 abort-set moves, hitting EVERY registered member
— matched 1700, segue 442, set 236, conflicts[N] 112, coverage 85, conflicts
length 85, review_flags 34, needs_review 25, set_breaks 23. Mutation flag-scoped,
restored in a `finally`, confirmed reverted before the real arms. So the harness
demonstrably CAN see a canonical mutation; an empty result from it would have
meant something.
REAL ARMS (reproduced by the orchestrator, not taken on report): `0 track titles
stripped; 11 structure.conflicts entries stripped; 0 other abort-set moves`.

WHAT MOVED: 11 entries of `structure.conflicts` on 3 of 89 shows, every one a pure
marker strip of an UNMATCHED canonical item's text — 'Thick Smoke #@%' ->
'Thick Smoke', 'High Lonesome Sound * # $' -> 'High Lonesome Sound'. List length
and ordering unchanged; coverage byte-identical on all three; ZERO movement in
matched / set / title_source / segue / set_breaks / review_flags / needs_review
anywhere in the corpus.

Therefore: the prediction's MECHANISM is confirmed (fuzzy_norm_title makes matching
blind to the markers — no matching DECISION moved anywhere), while the
prediction's LETTER is falsified (`conflicts` is produced by align(), and I
registered "alignment output" in the abort set).
ATTRIBUTION, per the registered-claim-falls rule: the registrar reproduced my
wording faithfully; the imprecision is MINE as author. "Alignment output" did not
distinguish a matching decision from a diagnostic that quotes canonical text. Do
not charge this to the registrar.
The implementer was RIGHT to stop. Its own suggestion that the ruling might go the
other way is exactly the ruling it correctly refused to make for itself.
`.conflicts` has one consumer in-tree: gather.py:803, assigning into StructureInfo.
CAVEAT: all arms ran setlistfm=None -> upper bound on blast radius, not a
production measurement.
CONCERN carried up: the differential shows ZERO improved track titles. It
demonstrates absence of harm, not presence of benefit — the 3 marked shows align
at coverage 0.0 offline so nothing adopts. The strip's actual value is at the
canonical layer reaching overrides.titles via --suggest-titles (9 of 25 items on
the ymsb2005 fixture).

Task 8: re-review APPROVED, no further round. I1/M1/M2/M3/M4 all ADDRESSED;
shadowing proven (a planted raise turned 6 tests red) and the snapshot baseline
1537/7 matched the orchestrator's worktree run exactly. Reviewer corrected my
credit: the Phase A doc sub-item was ALREADY satisfied at cf35b08 (came in with
1f02dcb) — this diff does not deserve credit for it.
Four new Minors, none blocking: N1 the M1 prompt fix is unpinned (reverting it
passes 1135 tests); N2 RESOLVE_PROMPT_WITH_TITLES is a hand-copied literal whose
comment falsely claims RESOLVE_PROMPT is the single source of truth; N3 both doc
files say build_canonical(provider=None) is "the same canonical gather itself
would" build — FACTUALLY WRONG, run_gather passes the real provider, and it is
wrong in CLAUDE.md; N4 "propose a title per track" overstates (filler rows get
none, already-titled tracks are never adopted over).
Ruling: N1-N4 dispatched now as an independent round — they touch cli.py, tests and
docs, disjoint from gather.py, so they cannot collide with either outcome of the
I3 ruling.

I3 RULING (root): PROCEED with the strip. The abort set fired on WORDING, not
substance — zero matching decisions moved in 89 shows; the 11 deltas are quoted
text of unmatched canonical items inside a diagnostic, length and ordering
unchanged. Recorded as a FALSIFICATION with a scoped waiver by the author of the
wording, NOT waved through as a pass: pre-registration is worth nothing if the
author narrows the claim after seeing the numbers.
Corrected wording, to be inherited: abort on movement in matching DECISIONS
(matched/set/segue/set_breaks/coverage/title_source/review_flags/needs_review),
NOT on diagnostics that quote canonical text.
Attribution confirmed by the root as author: the imprecision is the root's/mine as
author of the abort wording — not the registrar's (which reproduced it faithfully)
and not the instrument's (which measured correctly).

CONFLICTS DOWNSTREAM REACH — root asked me to verify, not assert. VERIFIED, and the
answer is stronger than "neutral":
  - `structure.conflicts` has ONE in-tree consumer (gather.py:803 -> StructureInfo).
  - BUT StructureInfo is a field of Show, and stages/brief.py:138 passes
    `show_json=show.model_dump_json(indent=2)` into the BRIEFING PROMPT.
  - So conflicts text DOES reach a prompt-facing surface. Confirmed on real data:
    ~/.llama/shows/greenskybluegrass-2008-02-29/show.json currently carries
    'Thick Smoke #@%' in structure.conflicts, and that whole dump goes to the
    briefing LLM today.
  => cleaning it is STRICTLY BETTER, not merely neutral: the LLM stops seeing
     description apparatus glued to song names. This also touches the known parked
     defect that `structure.conflicts` reaches the briefing LLM unlabeled.

Task 8 N1-N4: DONE. Commits 331221d (N1/N2 code+tests) and a76bf36 (N3/N4 docs).
Suite 1543 passed, 7 deselected. Both reverts shown RED on an outside-worktree copy
with shadowing proven first.
Scope deviation, and the implementer was RIGHT: the triage-decline test N1 needed to
pin lives in tests/test_triage.py, NOT test_cli.py as MY dispatch's file list said —
test_cli.py's decline tests cover the non-looping `fix` path, which cannot exhibit
the N1 bug at all. My file list was wrong; it edited the correct file and said so.

=== M3: GATE FAILED. ESCALATED. ===
Commit b4bd0f8 (docs only, +396, no code). Suite 1543 passed, 7 deselected.
Four of six shows rendered feasible; THREE of those four would have written wrong
titles, and nothing in the rendering distinguished them from the one correct case.
  ymsb2005-12-31: shape matches the spec EXACTLY (24 rows, 22 titled, fillers at 11
    and 22 — the fillers are even correct) while 13 of 22 titles are WRONG via a
    textbook uniform off-by-one across rows 12-21. Canonical has 23 items vs 25
    songs: both reprises missing.
  ymsb2002-12-31: rendered 38 rows / 36 confident titles — precisely the
    "confident-looking wrong one" the spec said must not appear.
  infamousstringdusters-2014-03-15: only 3 picks, ALL THREE WRONG. On a `y` it
    writes a title onto track 8 that track 7 already carries from its own tags, and
    drops `Machines` entirely. The small pick count makes it read low-risk; it is
    the most dangerous of the six.
  delmccourybandred / greenskybluegrass-2007-08-05: DECLINED, safe, correct.
  trampledbyturtles-2007-07-20: the one correct adoption (track 21 = `1922`,
    confirmed by description AND the filename D2T08).

GATE-DESIGN FINDING, and it is the important one: the spec's M3 acceptance
criterion for ymsb2005 was "renders the exactly-correct 24 rows" — a SHAPE test.
The shape passed while the content failed. A criterion defined over shape is
structurally blind to the uniform-shift failure the whole feature is built around.
Same class as the earlier "metrics are blind at their own boundary" traps.

setlist.fm ACTIVE IS WORSE THAN OFFLINE, measured on ymsb2005: n=23 items with both
reprises dropped, vs n=25 correct offline. This INVERTS this repo's standing
"every offline flip measurement is an upper bound" assumption, which is recorded
project-wide. The proposal path threads setlistfm deliberately (to match the redo's
canonical) and that consistency is producing the worse canonical here.

`forced` NEVER APPEARED in any of the six tables — every titled row carried a
numeric margin, i.e. the confident presentation, including on the three wrong
tables. My earlier worry that `forced` would read as over-confident was inverted:
the real problem is it never fires.

`sibling_item_durations` returned None on ALL FOUR feasible shows -> every proposal
fell back to duration-model. On ymsb2005 a fully-tagged sibling WITH per-track
durations is in cache — it is what the reviewer used to establish ground truth by
hand. The anchors were available and unused. This is the same function the Task 6
reviewer flagged as having unmeasured production yield; it is now measured at 0/4.

Root cause across every failure: a CANONICAL/TRACK COUNT MISMATCH, not a duration
error — missing reprises, missing intro tracks plus a truncated tape, a segue
sandwich held at different granularity. Nothing checks that the canonical and the
track list cover the same material before rendering. This is the filed-not-fixed
CLAUDE.md coverage gap surfacing at the proposal layer.

The never-clobber clause was demonstrated LOAD-BEARING on TBT: three wrong rows
landed on already-tagged tracks and were therefore not picks and not written.

MY ERROR, owned: I passed "the three marked shows align at coverage 0.0 offline"
into the M3 dispatch as fact. It came from the i3strip report and I did not verify
it. It is FALSE for greenskybluegrass-2008-02-29, which aligns at coverage 1.0
(28/30 matched). The zero-improved-titles conclusion survives on a stronger
mechanism — all 11 deltas are on UNMATCHED items and only matched items supply
titles — but I relayed an unverified claim into a dispatch brief. Same class as my
"alignment output" wording imprecision earlier in this run.
