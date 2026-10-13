### Spec Compliance
- ✅ Spec compliant. The diff matches the brief word for word:
  - `_presenter_file` is at cli.py:279-291 and `_dry_run_marker` at cli.py:294-315. All four marker texts are as specified, and the catch list `(PresenterError, OSError, ValueError)` is at cli.py:304. `ValueError` also covers `UnicodeDecodeError`, and `TOMLDecodeError` and pydantic `ValidationError` are subclasses of it.
  - The dry-run branch is at cli.py:395-396 and the docstring sentence at cli.py:358-361.
  - The `BILLYG.toml` fix is at test_run_cmd.py:552-553, and the three new tests (four cases) are at test_run_cmd.py:666-766.
  - The import is at cli.py:28.
  - No extras.
- ⚠️ Cannot verify from diff:
  - Spec section 1/6 wording beyond the brief. I took the brief as the spec proxy.
  - On a case-sensitive filesystem, dry-run and a real run can disagree. Details are under Minor 2.

### Strengths
- `_dry_run_marker` keeps file lookup, loading and resolution as three separate steps, each with its own try block. A bad presenter cannot abort the listing. Named risk: does `resolve_tts` do I/O that could raise outside `TTSResolutionError`, for example hashing a missing voice-clone clip? I read emcee/tts/resolve.py:43-76. It is pure (no I/O) and raises only `TTSResolutionError`, so the "never raises" docstring holds for resolution.
- RED evidence I captured myself, since the implementer recorded none. I ran the new test file against base 7159866 in a scratch `git archive` copy, using `python -m pytest` with PYTHONPATH shadowing (checked: `emcee.__file__` and `tests.__file__` both resolved inside the scratch copy). I predicted the 4 new cases would fail and the old dry-run tests would pass. Result: exactly that, 4 failed / 4 passed. So the new tests do pin the new behaviour. Log: t6-review.log.
- The unloadable-file cases are real. The `unreadable` case puts a directory at `phil.toml`: `exact.exists()` is True and `read_text()` raises `IsADirectoryError`, so the OSError branch is exercised. The `binary` case exercises the UnicodeDecodeError/ValueError branch. The `kurt` case uses the strict-model typo `tts_modle`, so the strict `Presenter` model is exercised end to end.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **Gap in the brief's tests: no test checks the "pinned presenters only" rule (the brief's test shape, verbatim).** test_run_cmd.py:695-708 and :549-566.
   - Every test station uses a `fake` house backend (`_write_config`, test_run_cmd.py:31). An unpinned presenter (`roy`, `billyg`) therefore resolves to `model=None`.
   - Mutation, run in scratch: I replaced `if resolution.pinned:` (cli.py:309) with `if resolution.model:`. I predicted it would survive, and it did: all 8 dry-run tests passed.
   - Why it matters: in production the house backend is voxtral. There an unpinned presenter resolves to a concrete model, and the pinned check is the only thing keeping that row unchanged.
   - Fix: add one assertion with a hosted house backend (`[tts] backend = "voxtral"`) and an unpinned presenter, checking that the row has no `[voxtral ...]` suffix.
2. **Pre-existing behaviour, and the brief prescribes it: dry-run loads by `path.stem`, but a real run loads by the configured id.** cli.py:303, compared with process.py:75 `load_presenter(config.root, view.presenter)`.
   - On a case-sensitive filesystem, config `BillyG` with file `billyg.toml` shows as fine (and now as resolved) in dry-run, but `emcee voice`/`run` fails with "no presenter".
   - The old `_presenter_file_exists` had the same case-insensitive "not missing" behaviour, and on macOS (APFS, case-insensitive by default) both paths agree. This task makes dry-run claim more, though: it now says the presenter loads and resolves.
   - Not this task's fix. Flag it for the final review, or make process.py use the same lookup.
3. **The "never raises" claim has one gap: `_presenter_file` itself.** `pdir.iterdir()` (cli.py:288) sits outside any try block. An unreadable `presenters/` directory (PermissionError) would abort the whole listing. This edge case predates the task (the old helper had the same call).
4. **The `speech_for` guard in `test_dry_run_marks_invalid_and_unresolved_presenters_and_completes` would pass on base too** (test_run_cmd.py:741-742). It guards against a regression, which is fine, but it is not evidence for this task.

No test-output noise to report: the handback's results line (2695 passed, 1 skipped, 7 deselected) shows no warnings beyond the baseline.

### Assessment
**Task quality:** Approved
**Reasoning:** The implementation is the brief's code verbatim and correct. The resolver is pure, so the "never raises" guarantee holds apart from a pre-existing directory-listing edge case. The new tests fail against base, so they pin the new behaviour. One gap is worth closing cheaply: the pinned-only rule is never tested under a hosted house backend, where it actually matters, and a mutant demonstrates this.
