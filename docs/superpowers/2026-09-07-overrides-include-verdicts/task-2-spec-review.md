SPEC COMPLIANCE: PASS

# Task 2 spec-compliance review — `run_gather` honours `overrides.include`

Diff reviewed: `a431de1..10d3202` (single commit, 2 files, +81/-3). Working tree clean; no files modified by this review.

## Requirement-by-requirement

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 1 | `read_overrides` hoisted above `filter_files`; `readmit=frozenset(overrides.include)` passed; old duplicate line gone | **Met** | `gather.py:838-841`; `grep -n read_overrides gather.py` → exactly one call site in `run_gather` (line 838); the diff's `-    overrides = read_overrides(show_ws)` above the exclude block confirms the deletion |
| 2 | Unmatched `overrides.include` entry logs a warning naming it | **Met** | `gather.py:842-843`, `log.warning("overrides.include entry %r matched no file", missing)`, computed over post-`filter_files` `kept`; pinned by `test_stage_gather.py:2083` |
| 3 | `Track.included` stamped immediately before `Show(...)`, `True` on exactly the re-admitted tracks | **Met** | `gather.py:1134-1138`, immediately above `show = Show(` at `:1140`; nothing rebuilds `tracks` in between. `test_stage_gather.py:2051` asserts list-equality (`[t.filename for t in show.tracks if t.included] == ["FOLLOW-ME @BYPIKENO.mp3"]`), so both the True and the False halves are pinned |
| 4 | Precedence: `exclude` block still runs after re-admission; a file in both lists ends up `operator-excluded`; pinned by test | **Met** | exclude block untouched at `gather.py:850-858`, after the readmit at `:839`; `test_exclude_wins_when_a_file_is_in_both_override_lists` (`:2069`) asserts absence from `tracks` **and** `reasons == ["operator-excluded"]` |
| 5 | `operator-excluded` entries carry `duration_sec`, homogeneous with `filter_files` output; tested | **Met** | `gather.py:855-857` uses the already-imported `length_seconds` (`gather.py:26`); matches the shape `junk.py:139,174,178` emits. Pinned by `test_operator_excluded_entry_carries_duration_sec` (`:2096`), which deliberately uses `gd73-06-10d1t01.mp3` — a file the junk filter keeps — so it exercises the `operator-excluded` branch, not junk filtering |
| 6 | Spec §5: re-admitted track runs the ordinary title cascade, no NEW review flag | **Met** | The diff adds nothing to `flags`/`needs_review`; `.included` has exactly one reader in `src/` (the stamp itself at `gather.py:1138`), so it cannot feed a flag. `_recover_format_titles` still runs on the post-`filter_files` `kept` (`gather.py:848`), so a re-admitted file participates in the cascade per spec §2 |

## Global constraints (checked in the code, not just the diff)

- `junk.py:66,69,70` — `SHORT_FRACTION_OF_MEDIAN = 0.25`, `MIN_MEDIAN_SAMPLE = 5`, `MIN_PLAUSIBLE_SEC = 90.0`. Unchanged; `junk.py` is not in the diff at all.
- `models.py:250-256` — `ManifestTrack` has no new field. `models.py:167-170` — provenance lives on `Track.included` in `show.json`, as the spec requires.
- `models.py:197` — `class Overrides(BaseModel)`, no `model_config`, no `extra="forbid"`. A pre-feature `overrides.json` with no `include` key still loads (field defaults to `[]`).
- No network reachable from the new tests: all five drive `run_gather(sws, StubIA(), FakeProvider(), …)`.

## Extra / scope

Nothing built beyond the brief plus the orchestrator's sanctioned `duration_sec` requirement. No CLI resolver or display work leaked in from Tasks 3-4 (verified: `cli.py` is not in the diff).

## Strengths

- The stamp is placed exactly where spec §1 says and carries the comment explaining *why* late (`gather.py:1134-1135`), so a future refactor that moves it has a reason not to.
- The hoist comment (`gather.py:834-837`) records the precedence rule at the site where it is easy to break — someone moving the exclude block up now has to read the reason first.
- Every new test is mutation-sensitive by construction: delete the stamp and `:2051`'s list-equality goes `[] != [...]`; reorder exclude before readmit and `:2069`'s first assertion fails; drop the `duration_sec` key and `:2096` raises `KeyError`; drop the warning loop and `:2083` sees no matching record.
- The deviation on the brief's caplog assertion is real and correctly diagnosed: pytest's `LogCaptureHandler.emit` formats each record, so `record.message` is already `%`-substituted and `r.message % r.args` raises `TypeError` for **any** record carrying args — the brief's ternary would have failed against a fully compliant implementation. The replacement keeps the only correct branch of the original and weakens nothing.

## Findings

### Critical
None.

### Important
None.

### Minor

1. **Spec §2/§6's "and warns" for the both-lists case is not implemented** — `gather.py:842-843` and `:853-854`. Spec §2 says a file in both lists is "**excluded** — a defined answer, **with a warning logged**", and §6's gather test list says "a file in both lists is excluded **and warns**". In the implementation neither warning fires: the include warning is computed over `kept`, which at line 842 still contains the re-admitted file, and the exclude warning fires only for entries matching *no* file in `kept`. So the contradiction is resolved silently. The brief's Step 3 code prescribes exactly this, so the implementer followed instructions; flagging it for the controller to rule on rather than as an implementer defect. Remedy, if wanted: after the exclude block, `for both in sorted(set(overrides.include) & drop): log.warning("%r is in both overrides.include and overrides.exclude; excluding", both)`, plus one assertion in `test_exclude_wins_when_a_file_is_in_both_override_lists`. Low urgency — spec §3 says the CLI makes the state unreachable by construction.

2. **`test_gather_leaves_ordinary_tracks_unmarked` (`:2063`) passes for the wrong reason on its own** — `Track.included` defaults to `False`, so this test stays green even if the whole stamp block is deleted. It is not a coverage gap in practice, because `:2051`'s list-equality assertion is what actually pins the False half, but the test as written asserts a model default rather than gather behaviour. It is verbatim from the brief; no change needed unless the controller wants it strengthened (e.g. by asserting `included` is False on a run where `overrides.include` names a file that *is* present, so the `if overrides.include:` branch is live).

## Verification performed

- Read the full review package once; read `gather.py:830-860` and `:1120-1165`, `junk.py:60-70,180-260`, `models.py:150-260`, spec §§1-6.
- Named risk checked outside the diff: *does anything else consume `Track.included` in a way this stamp could break, or feed a review flag?* — `grep -rn "\.included" packages/llama/src/llama/` returns exactly one hit, the stamp itself. No.
- Named risk checked outside the diff: *is the `operator-excluded` entry shape now genuinely homogeneous with `filter_files`?* — `junk.py:139,174,178` all emit `duration_sec`; `gather.py:856` matches.
- Ran the five task-2 tests only (not the suite): `./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py -q -k "readmit or ordinary_tracks_unmarked or both_override or include_entry or duration_sec"` → `5 passed, 92 deselected in 0.26s`. The implementer's whole-suite figure (1934 passed, 7 deselected) was not re-run. Their reported 26 warnings are pre-existing `os.fork()` DeprecationWarnings in concurrency tests, not introduced here.

## Assessment

**Task quality:** Approved.

**Reasoning:** All six requirements and all four global constraints are met at the exact sites the spec names, with tests that would fail if the corresponding behaviour were removed; the only spec-text gap is the unlogged both-lists warning, which the brief itself omitted and which the CLI (Task 3) makes unreachable.
