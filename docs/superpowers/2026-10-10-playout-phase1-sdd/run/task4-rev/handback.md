### Spec Compliance
Compliant. `layout.py`, `test_layout.py` and the `helpers.py` additions match the Task 4 brief verbatim: the same signatures, logic and 10 tests. The orchestrator rulings are honoured. `from transmitter import adts` is at module top (helpers.py:20), there is no duplicate `Path` import, and I found no unused imports in layout.py. `test_layout.py` binds `F` and never uses it, but the brief's own test file does the same, so this is plan-carried. Nothing is missing and nothing extra was added. The grid is implemented as specified: `segment_pieces(n)` = `pieces(441n, 441n+441)` (layout.py:92-93) with frame 0 at the epoch. The implementer's report is accurate.

### Strengths
- `pieces()` has the boundaries right. Rows are half-open. A row with `end_frame <= pos` is skipped and a row with `start_frame >= stop` stops the loop. A gap piece is emitted only when `start_frame > pos`. `take = min(stop, end_frame)` is always greater than `pos`, so no zero-count piece can be emitted. I hand-checked the show/gap/show test: 159 + 87 + 195 = 441, with `a:441..599`, `silence:0` ×87 and `b:0..194`.
- `end_frame` takes a cut into account and `pieces` uses it, so the frames of a cut show after the cut become silence. The encode-matches-plan check, however, compares against the full `frames`, which is correct because the encode is the full show.
- "Never list a segment that does not exist": `build_segment` refuses any segment whose last frame is past `rows[-1].end_frame` (layout.py:142-143). It also refuses an empty plan.
- An encode whose frame count differs from the plan is refused before any bytes are assembled (layout.py:144-148), so a re-encode cannot silently shift the grid.
- `segment.assemble` enforces the 441-frame count as a second guard (segment.py:11-12).
- The build test checks payload identity, not just counts. It parses the real assembled segment and checks its PRIV timestamp.
- `validate_rows` also catches rows that are out of order: a descending start fails the overlap test.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **There is no test that `validate_rows` accepts a valid plan** (test_layout.py:33-37 only asserts raises). A mutant that changes `r.start_frame < prev.end_frame` to `<=` would reject abutting rows (`start == prev.end`, a legitimate zero-gap join), and so would a `validate_rows` that always raises. Both would pass the suite. The `frames <= 0` and "cut outside the show" branches (layout.py:56-59) are untested too. Task 6's planner depends on this function, so a positive case (abutting rows, a cut row followed by an aligned run_start) plus one test per branch is cheap.
2. **The past-the-plan boundary is not pinned.** The only test is far past the end (n=1 against 500 frames). Changing `>` to `>=` at layout.py:142 would refuse the last fully covered segment, and no test would fail. Add a case where `end_frame == (n+1)*441` builds and `end_frame == (n+1)*441 - 1` refuses.
3. **`build_segment` trusts its inputs.** It neither calls `validate_rows` nor checks `n >= 0`. With overlapping or unsorted rows, `pieces()` silently trims or reorders rather than raising. A negative `n` builds a segment of leading silence with a wrapped timestamp. This is plan-mandated, and the risk is low if Task 6/9 always validate and pass `n >= first`. A single `validate_rows(rows)` and an `n < 0` check at the top of `build_segment` would make this the self-defending choke point the module docstring describes. Task 9 should be confirmed to validate.
4. **`silent_frame` is not checked to be exactly one ADTS frame.** `assemble` counts list entries, not frames. A multi-frame or empty `silent_frame` would produce a segment that passes the 441-entry check but holds more or fewer than 441 frames, which drifts timing. One line in `__init__` closes this: `len(adts.frame_offsets(silent_frame)) == 2`. The value comes from a later task, which is why this is only a note.
5. **Error-type mapping in `_load` is narrow.** Only `FileNotFoundError` becomes `LayoutError`. A `PermissionError` or `IsADirectoryError` escapes as a raw `OSError`, and a corrupt or truncated encode escapes as `AdtsError`. `AdtsError` is still a `TransmitterError`, so it is acceptable. The raw `OSError` is inconsistent with the earlier `require_root maps OSError` fix, so callers that catch `TransmitterError` would miss it.
6. **Memory use.** Each cached encode holds the whole file's bytes plus a Python list of offsets. A 3 h show is about 465k frames, so roughly 17 MB of int objects on top of the ~170 MB of bytes, times `keep=2`. That is acceptable on hugo. `mmap` plus an `array('q')` of offsets would be lighter if memory becomes a concern.
7. There is no test for LRU eviction or the cache hit path (`keep`), and none for `has()`, `path()`, or a `cut_frame` row going through `build_segment` itself (the cut is only tested via `segment_pieces`).

### Assessment
**Task quality:** Approved
**Reasoning:** The implementation matches the brief exactly, and the frame arithmetic is correct at every row and segment boundary I checked: show/gap/show, a cut row, a segment past the plan, and an encode/plan mismatch. The findings are test-coverage gaps (no positive `validate_rows` case, the unpinned past-the-plan boundary) and input hardening that is plan-mandated or depends on later tasks; none of them makes the code untrustworthy now.
