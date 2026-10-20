# t1-rev: Task 1 review (spec compliance + code quality), f1744ad..dd0bf7c

### Spec Compliance

- ✅ Spec compliant. Every Interfaces item is present and matches the brief, with orchestrator rulings B1 and M6 applied:
  - `ShowNotes` at models.py (diff 112-119). It is a plain `BaseModel`, so it is permissive like the other persisted artifacts.
  - `ShowWorkspace.notes` is added at workspace.py (diff 412), and the gather artifact list now holds `[show, reviews, notes]` (diff 426).
  - `CanonicalBuild.needs_llm` is a trailing field defaulting to False (diff 174). It is set only when `best is None` and `longest.strip()` and `provider is None` (diff 209-224).
  - `GatherResult` has fields show/reviews/notes/needs_llm (diff 242-254).
  - `compute_gather` is keyword-only after `identifier`, as the brief specifies (diff 257-273). It contains no `write_artifact` call: the only writes in gather.py are lines 1298-1300, inside `run_gather`. It reads `show_ws` only through `read_overrides` (diff 296).
  - `run_gather` keeps its signature and its `Show` return value (diff 369-396).
  - `align_structure` is recorded in an `else:` of `if align_provider is not None:`, inside the weak-alignment `elif` (gather.py:1084-1112, read to confirm the `else` binds to the right `if`). The `low-confidence structure alignment` flag is still appended unchanged (diff 345).
  - `op_notes` is a separate list. The local `notes` still flows into `structure.conflicts` (diff 282-285, 312).
  - In the CLI, the text `notes:` block sits after needs-review and before `--tracks` (diff 60-64), and `--json` has a `"notes"` key with empty lists when the file is absent (diff 86).
- ✅ Byte-identical with providers.
  - In `build_canonical`, the provider path now computes `longest` whether or not a provider was passed. That is pure (`max` over a list already in hand), and the call and the `SourcedParse` are unchanged (diff 211-222).
  - The align path is unchanged when `align_provider` is set, since the new `else` cannot run then.
  - `run_gather` writes the same `show.json` and `reviews.json` content as before.
  - `compute_gather` has only one `return`, the `GatherResult` at gather.py:1270, so no early return was left over from the old body. Checked by grepping the function's `return` statements.
- ✅ Do-not-retune grep. I grepped the diff's `+`/`-` lines for: `is_real_title`, `title_fraction`, `_TRACK_NUM_PREFIX`, `normalize_song`, `DEFAULT_ALIASES`, `GD_SHORTHAND`, `is_family_artist`, `_RECOVER_BELOW`, `_RECOVER_SIBLING_ABOVE`, the three tail-guard names, the three junk-duration names, `align_coverage_threshold`, `_ENUMERATED_MIN_FILES`, `_ENUMERATED_MIN_COVERAGE`, `_STRUCTURE_PREFIX` and `_FOOTNOTE_TAIL`. Nothing matched (exit 1). `align_coverage_threshold` appears only in unchanged context lines.
- ✅ Ruling 6. Nothing new is appended to `review_flags`, `structure.conflicts` or `VettingResult`, and `notes.json` is read only in `cli._read_show_notes` (diff 32-36).
- ⚠️ Cannot verify from this diff: whether any other `run_gather`/`compute_gather` consumer drops `needs_llm`. Today the only consumer is `run_gather`, which discards it on purpose. Tasks 5 and 20 (`compute_legs`/`reapply`) consume it, and their reviews should check that they do.

### Deviations (judged on merit)

1. **`notes.json` is written before `show.json` (diff 389-395): accept.**
   - `drop_stage_artifacts` deletes `show.json` before a forced gather (workspace.py:108 is `show_stage_artifacts`' only caller). After that, `show.json` is the `should_run` done-marker.
   - Writing notes first means a crash between the two writes re-runs gather instead of leaving a new `show.json` beside stale notes.
   - No checked call site depends on the order. `show_stage_artifacts` is used only by `drop_stage_artifacts`, and `_stage_ages` (cli.py:1708-1717) does not list `notes.json`. A show gathered before this change, with no `notes.json`, therefore does not look un-gathered anywhere.
2. **Extra test `test_json_carries_notes_and_empty_lists_without_notes_json` (diff 473-480): accept.**
   - It covers a requirement the brief stated but gave no test for (the `--json` key).
   - It checks both the file-absent case and the populated case.
   - It was written after the implementation, so it was never seen to fail. It depends directly on the new key, so it would fail if `diff 86` were reverted.

### Strengths

- The `else:` placement keeps the provider branch textually untouched. The comment there cites the spec and states that the degraded flag is unchanged.
- The `op_notes` comment (diff 282-285) records the ruling-6 separation where a later task would add notes, which guards against an implementer appending to the wrong `notes`.
- The `CanonicalBuild.needs_llm` comment states the empty-description exclusion, which matches the spec's citation of `gather.py:792-794`.
- `ShowNotes` uses `Field(default_factory=list)` and a docstring that names its readers. Leaving it permissive is right for a persisted artifact (per CLAUDE.md).
- The M6 edits are minimal and keep each test's meaning (diff 519-522, 544-547, 569-572).
- Checks I ran: the 12 new or touched tests pass with `-W default` and emit no warnings (`./.venv/bin/python -m pytest <3 files> -k "compute_gather or notes or run_gather_writes or run_gather_replaces" -q -W default` gives 12 passed). `llama.__file__` resolves inside the worktree.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)

1. **test_stage_gather.py, `extract_setlist` path: the "nothing recorded with a provider" side is not pinned.**
   - `test_compute_gather_with_a_provider_records_nothing_and_calls_it` (diff 640-647) uses `_low_coverage_candidate`, whose description parses (`best` is not None). So it pins only the align half.
   - A mutant that moves `needs_llm = True` above `if provider is not None:` (diff 218-224) survives every test, because `test_build_canonical_provider_none_never_reaches_the_llm_fallback` only checks that the provider is called.
   - It has no effect today, since `run_gather` discards the verdict. But the `GatherResult` docstring (diff 249-250) promises "Empty when providers were passed", and Task 5/20 consumers will rely on that.
   - Fix: a `build_canonical` test with a `FakeProvider` returning a valid `ParsedSetlist` on a non-parsing description, asserting `.needs_llm is False` (and, optionally, `compute_gather(...).needs_llm == ()`).
2. **The two-entry needs_llm path is unreachable in the current code. This is an observation, not a defect.**
   - `CanonicalBuild.needs_llm=True` implies `best is None`, so `canonical` is an empty `ParsedSetlist()` (diff 226). The align branch then needs `canonical.items` (gather.py:1084), so `("extract_setlist", "align_structure")` cannot occur.
   - The tuple-building code (diff 363-364) is still right for the contract. No test for both entries is possible without a mock, and none is needed.
3. **cli.py diff 36: `_read_show_notes` reads strictly.**
   - A malformed `notes.json` makes `llama show`, `--json` and triage (cli.py:1606) raise. This matches how `show.json` is read, and the implementer flagged it.
   - Consider leniency only if Task 5/20 can leave a partial file. `write_artifact` is atomic, so this is unlikely.
4. **Test noise.** The implementer's full-suite line reports 26 warnings. The new tests emit none (checked above), so these are presumably from before this change. The report gives no baseline warning count to confirm that; the controller can compare against the recorded baseline.

### Assessment

**Task quality:** Approved

**Reasoning:** The split is a faithful move of the old body. With providers, the old code paths are textually unchanged, and the new verdict is recorded only on the provider-absent branches. The tests cover align and extract without a provider, empty description, align with a provider, the `notes.json` write and replace, the artifact drop, and both CLI surfaces. The one gap worth closing is the extract-with-provider negative pin (Minor 1).
