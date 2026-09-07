# `.pyc` staleness audit of the Tasks 1-3 mutation evidence

```
TOTAL MUTANTS AUDITED (Tasks 1-3): 49
SIZE-CHANGING (self-invalidating, safe): 34   [+3 more not exposed at all: scratch-script re-implementations, no repo file mutated]
SAME-LENGTH SWAPS (exposed class): 12   [3 provably same-length + 9 whose size the artifacts do not fix]
  of which RESOLVED from artifacts: 12
  of which UNRESOLVED: 0
RE-RUN PERFORMED: no (nothing unresolved)
RE-RUN RESULT: n/a
TREE CLEAN AT FINISH: yes
VERDICT: Tasks 1-3 mutation evidence is SOUND
```

Audited at HEAD `542d690`, branch `overrides-include`, main checkout. No file in the
repository was modified by this audit; `git status --porcelain` is empty and HEAD is
unchanged. Task 4 was out of scope.

---

## 1. The discriminator this audit actually used, and why it is not size

The dispatch brief's rule — "size-changing mutants are self-invalidating and safe" —
**is not sound inside a battery, and the incident that triggered this audit proves it.**
CPython validates a cached `.pyc` against `(source mtime in whole seconds, source size)`
recorded in the `.pyc` header. I confirmed the header layout on this machine by decoding
the live artefacts:

```
cli.cpython-314.pyc:    pyc_src_mtime=1788776589 (2026-09-07 06:23:09)  pyc_src_size=163593
junk.cpython-314.pyc:   pyc_src_mtime=1788771285 (2026-09-07 04:54:45)  pyc_src_size=13285
gather.cpython-314.pyc: pyc_src_mtime=1788772720 (2026-09-07 05:18:40)  pyc_src_size=61069
```

The comparison that matters is therefore between **mutant N and the immediately preceding
write to that same file**, not between mutant N and the pristine file. In Task 4's case
both colliding mutants were `fullmatch` -> `match`, i.e. **both were size-changing** with
respect to the original (4 bytes shorter) — and they collided with each other. A mutant
that shortens a file is not thereby safe; it is safe only if its size differs from the
previous mutant's, or if the previous write landed in an earlier second.

Because of that, I did not rest the verdict on size at all. I used a stronger test that
the artifacts *do* support:

> **Freshness rule.** The suite is offline and deterministic, and the test files are
> constant across a battery. A stale-`.pyc` run of mutant N executes mutant N-1's
> bytecode and therefore reproduces mutant N-1's exact set of failing tests. Only two
> bytecodes are available to mutant N's run: the cached one (which would yield N-1's
> observed behaviour) or a fresh compile of N's own source. **So if mutant N's logged
> failing-test set differs from mutant N-1's, mutant N's own bytecode ran.**

This is one-directional and I used it that way: a *differing* set proves freshness; an
*identical* set proves nothing either way and was escalated to independent replication.

Every mutation battery in Tasks 1-3 logged, per mutant, the exact list of failing tests.
That is what makes the rule applicable.

## 2. What the timing evidence does and does not say

The brief suggested consecutive mutants were separated by a full suite run (~7 s) plus a
`git checkout --`. **The artifacts refute that for Task 3 and do not support it for
Task 2's quality review**, so it must not be relied on:

- Task 3's three batteries were **scripted**: `t3-impl.log` shows ten mutants' results
  emitted between two `restored: True` lines with no interleaved suite run, and each
  mutant's scoped pytest run took **0.19-1.10 s**. The Task 3 harness script was not
  preserved anywhere on disk, so there is no per-mutant timestamp.
- Task 2's quality review states "I did not re-run the full suite"; its runs were scoped
  to `test_stage_gather.py` at 0.22-0.54 s each.
- `pytest-of-shawn/` retains only the three most recent numbered temp dirs, and two of the
  survivors (`pytest-2422`, `pytest-2423`) are **one second apart** — direct evidence that
  consecutive pytest sessions in these batteries do land inside a single wall-clock second.

Conclusion: **timing resolves nothing here, and the hazard was genuinely live.** The
resolution below rests entirely on logged behaviour, not on elapsed time.

## 3. Per-mutant table

Legend for "Size": **SC** = size-changing per the artifact's own wording; **SL** = provably
same-length swap; **IND** = the artifact describes the edit in prose only and does not fix
its byte size (treated as exposed); **N/A** = no repo file was mutated.
Legend for "Resolution": **FRESH** = failing-test set differs from the immediately
preceding write to that file (freshness rule); **REPL** = failing-test set matched its
predecessor's, resolved instead by an independent re-run elsewhere with a mutant-specific
failure signature; **N/A** = not exposed by construction.

### Task 1 — 5 mutants

| # | Where | File | Edit | Size | Resolution / evidence |
|---|-------|------|------|------|-----------------------|
| T1-1 | task-1-report, fix round 1 | `junk.py` | add `readmit` param to `_keep_and_exclude`, widen `clean_secs` filter, pass `readmit=readmit` | SC (insertion) | FRESH — sole mutant of `junk.py` in that session; predecessor write is the committed file; logged failure is mutant-specific: `assert set() == {'band1t20.mp3'}` |
| T1-2 | task-1-review, MUTANT A | none | `_keep_and_exclude` **re-implemented** in `t1-rev/mutant_check.py` with early re-admission | N/A | N/A — repo file never modified; the script only *imports* the unmutated `llama.junk`, and a `__main__` script is never `.pyc`-cached |
| T1-3 | task-1-review, MUTANT B | none | same scratch script, re-admission before dedupe | N/A | N/A — as above |
| T1-4 | task-1-review, MUTANT C | none | same scratch script, re-admission after ordering | N/A | N/A — as above |
| T1-5 | task-1-rereview, M1 | `junk.py` | `readmit` param + `[] if f["name"] in readmit else reasons` + pass-down (`git diff --stat`: 3 ins / 3 del) | SC (insertion) | FRESH — sole mutant of `junk.py`; **and** the rereviewer ran two *different* tests against the *same* mutated file and got opposite results (new test FAILED, old test PASSED), which is only possible if the mutant bytecode was live |

### Task 2 — 10 mutants (all `stages/gather.py`)

The Task 2 **spec** reviewer ran no mutants (its "mutation-sensitive by construction" line
is reasoning, not a run) and so contributes nothing to this count.

| # | Where | Edit | Size | Resolution / evidence |
|---|-------|------|------|-----------------------|
| T2-1 | task-2-report, fix round 1 | `t.included = t.filename in forced` -> `= True` | SC (-16) | FRESH — sole mutant in that session; logged red/green pair around it in `t2-impl.log` |
| T2-2 | task-2-quality-review, M1 | delete the whole stamp block | SC (deletion) | FRESH — `t2-qual.log` captures its mutant-specific failure `assert [] == ['FOLLOW-ME @BYPIKENO.mp3']`, the delete-block signature (a `-> True` mutant would fail with seven names on the left) |
| T2-3 | task-2-quality-review | disable `readmit` on the `filter_files` call | SC (deletion) | FRESH — reds the readmit **and** both-lists tests; distinct from either neighbour's set |
| T2-4 | task-2-quality-review | drop the `duration_sec` key | SC (deletion) | FRESH — reds the fifth test only; distinct set |
| T2-5 | task-2-quality-review | delete the warning loop | SC (deletion) | FRESH — reds the warning test only; distinct set |
| T2-6 | task-2-quality-review, M5 | `t.filename in forced` -> `True` | SC (-16) | **REPL** — its reported outcome ("only the readmit test went red") is *identical to M1's*, and the review does not record the execution order, so the freshness rule cannot separate them. Resolved instead by T2-7 below: the same mutant, re-run independently by the re-reviewer at a later commit, with its own distinct logged failure. The finding M5 supports therefore stands regardless of this run |
| T2-7 | task-2-rereview, MUT A | `t.included = True` unconditionally | SC (-16) | FRESH — `t2-rerev.log`: `FAILED ...test_gather_leaves_ordinary_tracks_unmarked`, `1 failed, 97 deselected`; predecessor is the green baseline run |
| T2-8 | task-2-rereview, MUT A2 | delete the `if overrides.include:` block | SC (deletion) | FRESH — `FAILED ...test_gather_readmits_an_operator_included_file` at `:2084`, `1 failed, 2 passed, 95 deselected` — differs from MUT A in failing test *and* counts |
| T2-9 | task-2-rereview, MUT B | recovery computed on a pre-re-admission `kept` (list comprehension inserted) | SC (insertion) | FRESH — `FAILED ...test_readmitting_a_lossless_orphan_suppresses_sibling_format_recovery`, `1 failed, 1 passed, 96 deselected`; differs from MUT A2 |
| T2-10 | task-2-rereview, MUT C | delete the three-line both-lists warning loop | SC (deletion) | FRESH — `FAILED ...test_exclude_wins_when_a_file_is_in_both_override_lists`, `1 failed, 97 deselected`; differs from MUT B |

### Task 3 — 34 mutants (all `cli.py`)

**Round 0, scripted batch 1** (ten mutants between the pre-battery green suite and the
first `restored: True`). Table numbers in brackets are the report's own numbering.

| # | Edit | Size | Logged failing set | Resolution |
|---|------|------|--------------------|------------|
| T3-01 [1] | `dropped` clause emitted unconditionally (drop ` if s.excluded_files else ""`) | SC | `[no_dropped_clause_when_nothing_was_dropped]` | FRESH (vs green baseline) |
| T3-02 [2] | `+` marker never emitted, **width preserved** — i.e. `'+'` -> `' '` in `{'+' if t.included else ' '}` | **SL** | `[tracks_listing_marks_a_re_admitted_track]` | FRESH (differs from T3-01) |
| T3-03 [3] | `+` marker on every row | IND | `[tracks_listing_marks_a_re_admitted_track]` | **REPL** — identical to T3-02's set, so unresolved here; see T3-32 |
| T3-04 [4] | `+` legend emitted unconditionally | IND | `[no_re_admitted_legend_when_no_track_was_re_admitted]` | FRESH |
| T3-05 [5] | `e['duration_sec']` for `e.get(...)` | SC (-4) | `[excluded_section_survives_a_show_json_written_before_duration_sec]` | FRESH |
| T3-06 [6] | `enumerate(show.excluded_files, start=1)` -> `start=0` | **SL** | 3 tests | FRESH |
| T3-07 [14] | `if handles:` -> `if True:`, the crashing variant (`max()` over empty) | SC (-3) | 11 tests | FRESH |
| T3-08 [8] | `data["excluded"]` hoisted out of `if show_tracks:` | SC (dedent) | `[json_omits_excluded_without_the_tracks_flag]` | FRESH |
| T3-09 [9] | `include=` line dropped from `overrides:` | SC (deletion) | `[overrides_line_and_json_carry_include]` | FRESH |
| T3-10 [10] | `"include": ov.include` dropped from `--json` | SC (deletion) | 2 tests | FRESH |

**Round 0, scripted batch 2** (four mutants after the first `restored: True`).

| # | Edit | Size | Logged failing set | Resolution |
|---|------|------|--------------------|------------|
| T3-11 [7] | `excluded (N):` header emitted even when empty, crash-free variant | IND | `[no_excluded_section_when_nothing_was_filtered]` | FRESH (differs from T3-10) |
| T3-12 [11] | re-admit hint line dropped | SC (deletion) | `[tracks_listing_shows_the_excluded_section]` | FRESH |
| T3-13 [12] | `+` column reverted to the pre-feature layout | IND | 4 tests | FRESH |
| T3-14 [13] | excluded filename column unpadded | SC | `[tracks_listing_shows_the_excluded_section]` | FRESH |

**Fix round 1** (seven scripted mutants at sha `18073023966e`, plus one separately-invoked
re-verification).

| # | Edit | Size | Logged failing set | Resolution |
|---|------|------|--------------------|------------|
| T3-15 | legend reverted to the false parenthetical | IND | `[tracks_listing_marks_a_re_admitted_track]` | FRESH (vs green baseline) |
| T3-16 | hint put back inside the shared `_format_tracks` | IND (a move) | `[exclude_picker_lists_the_dropped_files_but_not_the_re_admit_hint]` | FRESH |
| T3-17 | hint dropped from `_print_show_entry` | SC (deletion) | `[tracks_listing_shows_the_excluded_section]` | FRESH |
| T3-18 | hint emitted even when nothing was dropped | IND | `[no_excluded_section_when_nothing_was_filtered]` | FRESH |
| T3-19 | hint prints a literal `<show>` instead of `entry.slug` | SC | `[tracks_listing_shows_the_excluded_section]` | FRESH |
| T3-20 | `.rstrip()` dropped from the excluded row | SC (deletion) | `[excluded_row_with_no_reasons_has_no_trailing_whitespace]` | FRESH |
| T3-21 | picker stops rendering the excluded listing | SC (deletion) | `[exclude_picker_lists_the_dropped_files_but_not_the_re_admit_hint]` | FRESH |
| T3-22 | re-verification of T3-18 against the rewritten line-scoped assertion | IND | `[no_excluded_section_when_nothing_was_filtered]` | FRESH — separate invocation after a `RESTORED` sha check and a full green suite; predecessor write is the restore |

**Fix round 2** (six scripted mutants at sha `ffc9dfec8470`, plus one separately-invoked
re-run of the one that missed).

| # | Edit | Size | Logged failing set | Resolution |
|---|------|------|--------------------|------------|
| T3-23 | duration loses its `>6` right-alignment | SC (deletion) | 2 tests | FRESH (vs green baseline) |
| T3-24 | fields reordered back to filename-before-duration | **SL** (a reorder) | 5 tests | FRESH |
| T3-25 | filename padding reinstated — the run that **MISSED** | SC (insertion) | `NONE` | FRESH (empty set differs from T3-24's five) |
| T3-26 | filename truncated to 20 | SC (insertion) | `[excluded_rows_align_regardless_of_filename_length]` | FRESH |
| T3-27 | handle loses its `>3` | SC (deletion) | 2 tests | FRESH |
| T3-28 | `.rstrip()` dropped in the new position | SC (deletion) | `[excluded_row_with_no_reasons_has_no_trailing_whitespace]` | FRESH |
| T3-29 | filename padding reinstated, re-run against the strengthened test | SC (insertion) | `[excluded_rows_align_regardless_of_filename_length]` | FRESH — separate invocation after a `RESTORED` sha check |

**Task 3 quality review** (four independent re-runs at orig sha `d0a26a6d`, applied one at
a time by exact-anchor replace + `git checkout --`).

| # | Edit | Size | Logged failure | Resolution |
|---|------|------|----------------|------------|
| T3-30 | M13, excluded filename column unpadded | SC | `tracks_listing_shows_the_excluded_section`, `assert 19 == 21` | FRESH |
| T3-31 | M1, `dropped` clause unconditional | SC | `no_dropped_clause...`, output `recording: gd73  (1 tracks, 0 dropped)` | FRESH |
| T3-32 | M5, `e['duration_sec']` | SC (-4) | `excluded_section_survives...`, `KeyError('duration_sec')`, exit 1 | FRESH |
| T3-33 | M3, `+` on every row | IND | `tracks_listing_marks_a_re_admitted_track`, `'   2.+ set ...'.startswith('   2.  set ')` False | FRESH — **and this is the replication that resolves T3-03**: the captured output shows a `+` on track 2, the marker-on-every-row signature, which is *not* what a marker-never-emitted mutant produces |

**Task 3 re-review** (one mutant).

| # | Edit | Size | Logged failure | Resolution |
|---|------|------|----------------|------------|
| T3-34 | filename padding reinstated | SC (insertion) | `excluded_rows_align_regardless_of_filename_length`, `assert 68 == 26`, with the padded row printed verbatim | FRESH — sole mutant; predecessor is the pristine file after a logged `102 passed` |

## 4. The two mutants that needed replication rather than the freshness rule

Exactly two runs in Tasks 1-3 produced a failing-test set identical to their predecessor's,
which is the observable signature a stale-`.pyc` false CAUGHT would leave:

1. **T3-03** (`+` marker on every row) followed **T3-02** (`+` marker never emitted) in the
   same scripted batch, and both logged the single failure
   `test_tracks_listing_marks_a_re_admitted_track`. T3-02 is itself proven fresh (its set
   differs from T3-01). T3-03 is resolved by **T3-33**, the quality reviewer's independent
   re-run of the same mutant at a different commit, in a different session, which captured
   the assertion text `'   2.+ set ...'.startswith('   2.  set ')` — a mutant-specific
   output that a marker-never-emitted mutant cannot produce. The claim (`_format_tracks`'s
   marker is pinned in both directions) is therefore established.

2. **T2-6** (Task 2 quality review's M5, `t.included = True`) reported the same outcome as
   its M1 (delete the stamp block) — "only the readmit test went red" — and that review
   does not record the mutants' execution order, so the freshness rule cannot separate them.
   Resolved by **T2-7**, the re-reviewer's MUT A: the identical mutant, re-run at commit
   `2b6ccef`, with its own distinct logged failure
   (`test_gather_leaves_ordinary_tracks_unmarked`, `1 failed, 97 deselected`).

Note that even in the worst case these two are not evidence *for* a defect: a false CAUGHT
here would have meant re-running the previous mutant, which was itself caught by the same
predicted test. Neither would have licensed a wrong conclusion; both are independently
re-established anyway.

## 5. What I could not determine, and what it would take

- **Exact byte sizes for 9 of the 34 Task 3 mutants and for the `IND` rows generally.** The
  reports describe those edits in prose; no per-mutant diff, patch or size was recorded, and
  the Task 3 harness script was not preserved (only Task 4's `mutate*.py` survive, under
  `sdd/t4-impl/`). To fix this for future runs, have the harness log the mutated file's
  sha1 **and** byte size per mutant, which is what Task 4's rebuilt battery already does.
- **The execution order of the Task 2 quality review's five `gather.py` mutants.** The
  review names them M1-M5 but does not state that this is run order, and `t2-qual.log`
  captured only M1's output. This is why T2-6 needed replication rather than the ordering
  rule. Logging every mutant's output, not just the first, would have closed it.
- **Per-mutant wall-clock timestamps anywhere in Tasks 1-3.** Only two coarse markers exist
  (`fix round 1 start 2026-09-07T09:37:53Z`, `fix round 2 start 2026-09-07T09:42:45Z`).
  `pytest-of-shawn/` has since garbage-collected all but its three most recent temp dirs, so
  that route is closed too. The verdict does not depend on this, but it means the brief's
  "consecutive writes were seconds apart" premise could not be confirmed — and the evidence
  that does survive points the other way.

## 6. Standing correction for future batteries

The rule "a size-changing mutant is self-invalidating" should not be carried forward. The
correct invariant is: **mutant N is safe iff its size differs from the previous write to
that file, or its mtime lands in a later whole second.** The soundest fix remains the one
Task 4 adopted — a unique `PYTHONPYCACHEPREFIX` per mutant, which removes the shared cache
entirely and makes both size and timing irrelevant. Failing that, logging each mutant's
failing-test set (which all three tasks did) preserves enough signal to audit the run
after the fact, as this audit did.

## 7. Tree state

`git status --porcelain` is empty, HEAD is `542d690982a1c92892307a8fe02ebb8e0116381a` on
branch `overrides-include`. This audit applied no mutations and required none: every
exposed mutant resolved from the artifacts.
