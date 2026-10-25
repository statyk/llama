# Task 4 review (t4-rev): final_kept + fix's writer rules, 853239a..904eeb5

### Spec Compliance

- ✅ Spec compliant (4.1 "Writers refuse legacy", 4.2 writers/staleness/behaviour change/no show.json/exclusion refusal/dangling-key clears). Every brief test line is present (test_fix.py:1220-1420, test_stage_gather.py:4544-4620). The one deviation is Decision 1: two `final_kept` calls on the `--suggest-titles` path where the brief says one. The orchestrator ruled that the spec's one-helper rule requires it, and I agree on the merits: both calls go through the same helper over the same stored overrides (pinned at test_fix.py:1412).
- ⚠️ Cannot verify from diff: triage's legacy skip, `[t]`/`[u]`/`[m]` staleness and `[e]` keyed exclusion. These are Task 5's, per the ruling. The `_refuse_legacy` docstring (cli.py diff l.50) already says "and triage's", so Task 5 must make that true or reword it.

Named-risk checks (one each):
- **`final_kept` is a verbatim move, and `title_inputs`' outputs are unchanged.** gather.py diff l.522-545 vs removed l.569-572 and 596-610 match line for line. The only behavioural difference is that the exclusion's log warnings now fire before format recovery instead of after. `filter_files`' own default is `short_keep=True` (junk.py:379), so passing it explicitly changes nothing. `title_inputs` still feeds `recovery_basis` from `fk.unexcluded` and `positions` from `fk.kept`. I checked that `compute_gather` derives `want` as `FORMAT_BY_AUDIO[audio_format]` (gather.py:1649), the same expression `_stale` uses (cli.py:1437). The pin test_stage_gather.py:4544 holds literal values captured on the base commit.
- **`_refuse_legacy` runs first on every `fix` path.** It is cli.py diff l.241, immediately after `_resolve_show` and before `capture_view`, the `--untitled` branch, every parse, the combination guards, the show.json, stale and exclusion refusals, and the unit. I checked that `_resolve_show`/`catalog` read the file through `Overrides` (`titles: dict[str,str]`, `set_breaks: list[int|str]`, `encore_after: int|str`, models.py:223-225), so a legacy or mixed file parses and cannot raise before the refusal.
- **Every new refusal happens before `show_unit` and writes nothing, with or without `--no-run`.** The stale check (l.279, l.373-375), the no-show.json check (l.371) and the exclusion check (l.377-410) all sit above the `did_files`/`did_meta` block and the unit. The tests assert `tree_bytes` is byte-identical and `calls == []` in both modes (test_fix.py:1305-1316).
- **`_stale` uses the overrides as stored before this invocation's edits.** It calls `read_overrides(sws)` before any `_edit_overrides`. test_fix.py:1270-1281 pins the spec's `--exclude 3 --set-title 7=X` behaviour change.
- **The exclusion check's `extra`/`cleared` semantics cannot orphan a key.** I traced it against `_edit_overrides` (cli.py:1525-1553). A clear is applied before a set, and `--clear-set-breaks` / `--clear-encore` beat `--set-*`. Every mismatch between the check's model and the writer goes toward over-refusal: `--clear-set-breaks --set-breaks 2 --exclude 2` refuses although the stored result is None. None goes toward under-refusal. Out-of-range numbers are dropped from `extra`, but the writer's `to_file` then raises inside the unit, which rolls back. `--suggest-titles` picks are merged after the check, but `--suggest-titles` cannot be combined with `--exclude` (that guard exits first). `--untitled` cannot be combined with `--exclude` either.
- **`_stale` never treats an `IAError` as "not stale".** `ia.metadata` is not wrapped in any handler (cli.py:1435), so the error propagates. An item with no files gives `kept == []`, which differs from show.json, so `_stale` refuses.

Fixed strings checked character for character against global-constraints: the staleness string is at cli.py diff l.76-77 and the exclusion string at l.107-110, with the flag map `--clear-title <file>` / `--clear-set-breaks` / `--clear-encore`. The tests assert both in full (test_fix.py:1252, 1292, 1314).

Protected-name grep over the diff: only reads of `FORMAT_BY_AUDIO` (diff l.73, 163-164, and the tests). `junk.py`, `structure.py` and `titles.py` are not in the diff.

### Strengths
- `final_kept` really is the single copy. `title_inputs`, `_stale` and `_propose_titles_for_show` all go through it, which removes the hand-rolled `filter_files` + exclude recomputation in `_propose_titles_for_show`, a past source of review findings.
- Ordering is tested, not just claimed:
  - the legacy matrix (test_fix.py:1217-1234) patches the proposal to `pytest.fail` and passes `input=""`;
  - the `--untitled` stale case proves the stale check runs before the resolved-count refusal (the windsor tracks are titled);
  - the stale test then shows that `--clear-set-breaks` succeeds on the same show.
- The dry run moved the existing positional tests onto real gathers, without loosening the check. It also found and fixed two tests that were passing only because an un-stubbed `IAClient` reached archive.org (`test_untitled_is_refused_on_a_zero_track_show`, `test_clear_title`).
- The C1 decline is kept as a second line of defence and still pinned, by calling `_propose_titles_for_show` directly (test_cli.py diff l.691-701, 748-752).

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **cli.py diff l.1435 (`_stale`): an archive.org failure shows as a traceback.** `ia.metadata` failing (an uncached item, or an archive.org error) escapes `fix` as an uncaught `IAError` instead of the usual `error: …` exit 1. It is safe (nothing is written and it is never read as "not stale"), but it differs from how other refusals look. Wrap `refuse_if_stale`'s call in `except LlamaError` → echo + `Exit(1)`.
2. **cli.py diff l.391-392 (`file_of`): a third copy of the number-to-filename translation.** It indexes `names[n-1]`, as `_edit_overrides.to_file` does, while `_resolve_exclude_tokens` (cli.py:1611) maps by `t.index`. They agree only because gather writes contiguous indexes. A shared helper (or reusing `to_file`'s rule) would keep the three from drifting.
3. **cli.py diff l.80: `extra: Mapping[str, str] = {}` is a mutable default.** It is never mutated, so it is harmless, but `extra: Mapping[str, str] | None = None` is the idiom.
4. **test_fix.py:1411: the first half of `test_suggest_titles_kept_list_comes_from_final_kept` never asserts the CLI's exit code.** A crash after the two spy calls would still pass. Add `.exit_code == 0` (the declined proposal exits 0).
5. **Exclusion over-refusal.** `--clear-set-breaks`/`--clear-encore` combined with `--set-breaks`/`--set-encore` and `--exclude` of the new value's file refuses even though the clear wins in `_edit_overrides`. It is conservative and unpinned. Either refuse the clear+set combination outright or leave it, but write the choice down.
6. **cli.py diff l.355-364: the `--suggest-titles` combination message is stale.** Its wording ("renumbers tracks before the proposal's numbering would apply") predates filename keys, as the implementer noted. It is cosmetic.

### Assessment

**Task quality:** Approved

**Reasoning:** Every new refusal runs before any prompt and before the unit, and the legacy refusal is first on every `fix` path. The exclusion check can only over-refuse, never orphan a key. `final_kept` is a verbatim, pinned move with `title_inputs`' outputs unchanged. What remains is error-surface polish and minor duplication.
