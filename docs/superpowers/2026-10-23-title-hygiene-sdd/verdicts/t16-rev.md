### Spec Compliance
- ✅ Spec compliant. Every brief requirement and all six orchestrator rulings are present in 89fd787..f062b85. One ruled pin (ruling 4) is literally executed but does not check the ordering it was meant to pin (Important 1 below).
  - **One copy (Task 11 MUST):** yes. In the wired gather.py (f062b85), `resolve_titles`, `tag_layer`, `placeholder_positions`, `adopt_gap_titles`, `accept_short_tags` and `_recover_format_titles` are each called once, and only inside `title_inputs`/`title_cascade` (lines 1063, 1109, 1138, 1246, 1271, 1350, 1394, 1405). `compute_gather` keeps only `read_overrides` (1595), the jerrybase lookup (1603), and `build_canonical` through the `build` closure (1626). The deleted block is diff lines 317-376 and 405-562.
  - **No undefined names after the deletion:** I ran a symtable/AST check of the whole f062b85 gather.py for referenced-but-undefined globals. It found nothing, and it did catch a planted `kept` sentinel. `compute_gather` reads `inp.excluded`, `inp.ordering`, `inp.cb` and `inp.family_aliases`, plus `cascade.*` (diff 579-587).
  - **Notes order:** correct in the code. `op_notes = list(cascade.op_notes)` comes before every downstream `op_notes.append`/`+=`, and `notes = cb.notes + cascade.struct_notes` (diff 586-587). `title_cascade`'s `struct_notes` gets only sibling-align's notes. The new positional-decline, C, slice-4 and D notes all go to `op_notes`, so none reach `structure.conflicts`. No note of today's is dropped. The cascade's op_notes are exactly the old demoted, 2c/2d, format-sibling and 2a notes, plus the new ones.
  - **`cb.notes` aliasing:** `cb.notes` is no longer extended in place. Nothing reads `cb.notes` after line 1640 (grep: the only later `cb.` is `cb.needs_llm`), and `GatherResult` does not carry `cb`, so the output is identical.
  - **Moved jerrybase block:** `jerrybase.lookup(artist, candidate.date)` and `_event_kind(candidate.performance_id)` read no file list, track or canonical. Running them before `filter_files` changes only log order, or which exception surfaces first. It cannot change an outcome.
  - **GatherResult fields:** `self_filled`, `title_paths` and `title_record` are the last fields and defaulted (diff 258-260). Grep found no positional unpacking anywhere. The only other construction (test_replay.py:445) uses keywords. `test_title_paths_reported` asserts that `title_paths` is not in `show.model_dump_json()`. models.py and replay.py are unchanged in the range.
  - **`enabled_slices`:** keyword defaulting to `title_hygiene.ENABLED_SLICES` (diff 282), passed to `title_cascade` (diff 578). `run_gather` does not pass it (f062b85:2037-2041). No added line rebinds `ENABLED_SLICES`. Mutant M3 (ignore the kwarg) is caught by `test_compute_gather_enabled_slices_kwarg`, as I predicted.
  - **Protected names:** grepping the diff's +/- lines finds them only in deleted uses inside the removed duplicate block, and in comments. No definition is edited. `git diff main..f062b85 -- packages/llama/src/llama/setlist.py` is empty.
  - **The seven Step 1 tests:** all present (test_stage_gather.py new section; test_show_cmd.py pin). `desc-position` is in `TAUTOLOGICAL_TITLE_SOURCES` (structure.py:1154), which matches the moved setlist-gap comment.
  - **Rulings:**
    - (1) mccoury test: `setlist` → `desc-position`, with a clause comment; the low-confidence assert is left for Task 17.
    - (2) `declined=frozenset()` added to the stand-in.
    - (3) The patch now targets `_sibling_transfer_full`, with a 3-tuple stand-in.
    - (4) The test is renamed and pins the kwarg (it is non-vacuous: the 7 params that differed in the dry run now pass only at `frozenset()`). Its ordering half is weak; see Important 1.
    - (5) The gate0 asserts are removed with a comment, the docstring says `dump` measures a pre-wiring tree, and the gd74 non-vacuity assert reads arm `none`. The implementer flagged that last change as going beyond the ruling; it is within the ruling as relayed to me.
    - (6) regather_diff saves, patches and restores `_sibling_transfer_full`.
  - **Commit message:** lists every edited test with its clause and records the emcee/transmitter/antenna `title_source` grep as empty (I re-ran it: still empty).
- ⚠️ Cannot verify from the diff:
  - Full-suite count `4724 passed, 1 skipped, 8 deselected`. Not re-run, per the rubric. In my scratch copies (packages/llama/tests + scripts, `-x`), mutants M1 and M2 ran to 100% green, which is consistent with that count.
  - Library-level behaviour with slices off after the wiring. Gate 0 (3983/3983) was measured pre-wiring. After wiring, the evidence is the in-suite parametrized test over 12 fixture cases, plus reading the code.

### Strengths
- The deletion is clean and complete. The rationale comments were moved, comment-only, to the matching lines in `title_inputs`/`title_cascade` rather than lost, and stale "until the wiring task" wording was updated (diff 13-15, 60-61).
- No longer mutating `inp.cb` is a strict improvement, and the comment says so (diff 583-585).
- The new tests are behavioural and contrastive. `test_gather_s_withdrawn_when_list_count_matched` runs the same input at `frozenset()` and asserts setlist.fm's wording ships there. `test_gather_q1_…` checks both that the decline note is in `notes` and that it is NOT in `conflicts`. `test_gather_c1_fills_tmp_tape` asserts that no 2b or format-sibling note appears.
- The Step 4 dry run was thorough: every failure was tied to a clause or named as routing, and the regather_diff inertness was found unprompted.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **The ruled notes-order pin does not discriminate (ruling 4 / brief Step 3).**
   - Where: packages/llama/tests/test_title_cascade.py `_today` (`assert res.notes[:len(notes)] == notes`), and the absence of any conflicts-order test.
   - What's wrong: I ran mutants in scratch copies of f062b85, with shadowing proven by a planted sentinel and predictions logged first. M2 builds `op_notes` empty and appends the cascade's op_notes at the END. M1 builds `notes = cascade.struct_notes + cb.notes`. Both SURVIVE the whole llama suite plus the scripts tests. The reason: none of the 12 parity cases produces a downstream op_note (jerrybase is off, and no taper note fires there), so "begins with" collapses to "equals". No test has both canonical notes and sibling notes in `conflicts`.
   - Why it matters: the code is correct today (verified by reading), but the order the brief names in Step 3 is unprotected on the default, all-slices path. Gate 0 no longer guards it now that the copy is gone. Order is observable in notes.json, and in the `conflicts` text sent to the briefing LLM.
   - Fix: one small test. Use a fixture where a cascade op_note fires (e.g. the furthur `lossless titles declined: …` note, or a 2b note) AND a downstream op_note fires (taper marker note, or jerrybase on). Assert that the cascade notes are a strict prefix and that a downstream note follows them. Add an assert that a canonical note precedes a sibling-align note in `structure.conflicts`. Re-check that M1 and M2 go red.

#### Minor (Nice to Have)
1. **Stale docstring.** packages/llama/tests/test_stage_gather.py:1440-1468 (`test_gather_artist_item_does_not_block_title_resolution`) still says "the setlist is the only title source" and "every track here is 'setlist'-sourced", while the assertion now says `desc-position`.
   - It also no longer guards what its name says at default slices. D fills from reader (ii), which drops the artist line with its own cleaner, so a regression in `build_canonical`'s artist drop before `resolve_titles` would no longer fail this test. (`test_gather_drops_setlist_items_that_are_the_artist_name` still covers the canonical drop for align.)
   - Fix: update the docstring, and add a `compute_gather(..., enabled_slices=frozenset())` arm asserting six `setlist` titles, which keeps the original guard.
2. **Red WIP commit on the branch.** 30bb7e0 has 11 failures by design: the orchestrator waived the green rule for the dry-run commit, and the plan says one commit per task. This leaves a red commit for `git bisect`. Consider squashing 30bb7e0 into f062b85 at merge time.
3. **Dead 2-tuple wrapper.** `_sibling_transfer` (gather.py:303) is now off the production path; only its pin test and the probe use it. The implementer kept it deliberately. A one-line comment at its definition saying so would stop a later reader assuming gather calls it.
4. **Rename docstring cites the plan, not the spec.** The renamed test's docstring (test_title_cascade.py:151-157) cites "Task 16" and Step 3 rather than a spec clause. The constraint asks for a spec clause; a reference to the spec's notes-order and Placement rules would satisfy it.
5. **Test noise (not introduced by this diff).** The scratch runs showed `DeprecationWarning: This process … is multi-threaded, use of fork()` from test_concurrency/test_ledger_concurrency/test_locks/test_sessions (Python 3.14).

### Assessment
**Task quality:** Needs fixes
**Reasoning:** The wiring is correct, there is exactly one copy, the moved jerrybase block is outcome-neutral, the fields and kwarg match the contract, and all six rulings are executed. The one gap is that the notes ordering the brief names (op_notes first; struct notes after `cb.notes`) has no discriminating test: mutants M1 and M2 survive the full llama and scripts suites, so one small fixture test is needed before the order can be called pinned.

Evidence: log `$D/t16-rev/t16-rev.log`. Scratch copies are in ~/.llama-harness/piece3/scratch/t16-rev/{base,m1,m2,m3}, and the mutant outputs are in `m1.out`, `m2.out` and `m3.out` there.
