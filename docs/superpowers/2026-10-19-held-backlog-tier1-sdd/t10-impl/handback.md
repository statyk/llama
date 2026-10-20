# t10-impl handback: Task 10, slice 2a (corroborated short tags)

Status: DONE. Commit 84c8803 `feat(gather): 2a corroborated short tags` on held-backlog-tier1.
Full suite: `./.venv/bin/python -m pytest -q` -> 3421 passed, 1 skipped, 8 deselected (baseline 3401; +20 tests).

## Implemented
- `titles.tag_core(tag)`: the brief's regex verbatim (`_CORE_TAIL`), `.strip()`.
- `titles.strip_taper_markers(tag)`: the brief's two regexes verbatim (`_SHIPPED_TAIL`, `_SHIPPED_HASH`), applied **to a fixpoint** (see Deviations).
- `gather.accept_short_tags(tracks, tag_titles, tag_source, *, corroboration, metadata_norms) -> (list[Track], list[str])`: exactly the brief's rule: only `title_source == "unresolved"`, non-empty tag failing `is_real_title`; core has an alnum; `not is_junk_tag(core)`; every non-empty component of `re.split(r"\s*(?:->|>)\s*", core)` has `fuzzy_norm_title(c) in corroboration`; `fuzzy_norm_title(core) not in metadata_norms`. Ships `strip_taper_markers(tag)`, `title_source=tag_source`, `matched` untouched; note text per Contracts 2a with sorted union of component sources. Returns a new list (input untouched).
- Wired in `compute_gather` right after `adopt_gap_titles(...)` and before `flags = []`; `tag_layer`'s second return (previously discarded `_`) is now `tag_source`; `corroboration=cb.corroboration` (the dict); notes appended to `op_notes` (GatherResult.notes → notes.json only, ruling 6). Nothing goes to `structure.conflicts`/review_flags. `TAUTOLOGICAL_TITLE_SOURCES` untouched.
- M9: an `overrides.titles` position is `override` by the time 2a runs, so it is never judged or noted (pinned by a new test).
- Fixture `packages/llama/tests/fixtures/tnd2006-12-13.json`: `./.venv/bin/python scripts/capture_fixture.py --from-cache tnd2006-12-13.flac16` (offline), renamed from the script's default `tnd2006-12-13.flac16.json` to the brief's name.
- Imports added: `Track` (gather models import), `is_junk_tag`, `is_real_title`, `strip_taper_markers`, `tag_core`; test file got `from llama.models import Track` (orchestrator note).

## TDD evidence
- RED: both files errored at collection: `ImportError: cannot import name 'accept_short_tags' from 'llama.stages.gather'` (and `tag_core` in test_titles).
- GREEN on target files: 207 passed, then full suite 3419 → after added tests 3421.
- One of my own added tests was wrong first time (`"J > Nope"`, `"J > FF >"` pass `is_real_title`, so they never reach 2a); rewritten to `"J > X"` / `"J > F >"`.

## Tests added (beyond the brief's verbatim ones)
- `test_accept_short_tags_needs_every_segue_component_corroborated` — mutant (c) row as the orchestrator asked: `"J > X"` (only J corroborated) NOT accepted; `"J > F >"` accepted as `J > F`, note sources union `lma:x, setlist.fm`.
- `test_accept_short_tags_never_judges_a_real_title_tag` — survivor (f) fix: `"Jam > Jam"` with `jam` corroborated stays unresolved (2b's recording-level class judges the whole tag `jam jam`, 2a would judge per component; only the is_real_title gate stops the re-accept).
- `test_accept_short_tags_carries_the_tag_layer_source` — `sibling-format` stamped, `matched` None.
- `test_2a_never_judges_an_overridden_position` — M9 on the tnd fixture.
- `test_tag_core_and_shipped_title` row `("Dew > #", "Dew", "Dew")` — fixpoint.

## Mutation table (recipe: fresh rsync copy per mutant under $TMPDIR, PYTHONPATH shadow proven by printing llama.__file__ under the copy, private PYTHONPYCACHEPREFIX, worktree interpreter `-m pytest`, over test_titles.py + test_stage_gather.py; predictions written before flipping)
| mutant | predicted test | result |
|---|---|---|
| (a) drop alnum check | test_stage_gather::test_accept_short_tags_rules | caught by predicted |
| (b) drop metadata_norms veto | test_accept_short_tags_rules | caught by predicted |
| (c) any() instead of all() over components | test_accept_short_tags_needs_every_segue_component_corroborated | caught by predicted |
| (d) drop is_junk_tag | test_accept_short_tags_rules | caught by predicted |
| (e) `_SHIPPED_HASH` `\s+` → `\s*` (attached `#` removed) | test_titles::test_tag_core_and_shipped_title[F#-F-F#] | caught by predicted (run before and after the fixpoint change) |
| (f, extra) drop is_real_title gate | test_accept_short_tags_ignores_tags_that_pass_is_real_title | **SURVIVED** (tmp also caught by the junk veto) → new test_accept_short_tags_never_judges_a_real_title_tag; re-run: caught by it |
| (g, extra) hardcode `"tags"` source | test_accept_short_tags_carries_the_tag_layer_source | caught by predicted |
| (h, extra) drop the notes wiring (`op_notes += []`) | test_2a_accepts_j_when_a_sibling_description_corroborates_it | caught by predicted (+ test_2a_never_judges_an_overridden_position) |
| (i, extra) fixpoint → single pass | test_tag_core_and_shipped_title[Dew > #-Dew-Dew] | caught by predicted |

Note on (a): in the real pipeline `?` is also stopped by corroboration (empty normals are skipped in `_corroboration`), so only the unit row (which injects a `""` key) catches it; that is the intended layering.

## Self-review
- No do-not-retune constant touched (grep of the diff for is_real_title body, `_YEAR_LIKE`, title_fraction, `_TRACK_NUM_PREFIX`, `_FOOTNOTE_TAIL`, `_RECOVER_*`, `TAUTOLOGICAL_TITLE_SOURCES`: no hits).
- Shipped title is never empty: shipped stripping removes a subset of what core stripping removes, and an accepted core has an alnum.
- `i >= len(tag_titles)` guard is defensive only (gather's tracks and tag layer are both over `kept`).

## Deviations
- `strip_taper_markers` loops the brief's two substitutions to a fixpoint. The brief's single composition leaves `Dew > #` as `Dew >` (the free-standing `#` hides the `>`), which breaks the spec's acceptance "No shipped title keeps a trailing taper marker". Regexes are verbatim; all 11 brief rows unchanged. Revert = one line if the orchestrator prefers the literal composition.
- Fixture file renamed to the brief's `tnd2006-12-13.json` (script default name includes `.flac16`).

## Concerns / observations (not acted on)
- On the tnd in-memory run, accepting the `J` tracks moved set labels (e.g. track 8 set 1 → 2) relative to the no-sibling arm — the spec's expected "structure-changed" effect, which slice 0's list covers; not a 2a defect.
- Tags that PASS is_real_title keep their trailing markers as today (`Glide >`, `G-nome > J >`): pre-existing behaviour, out of 2a's scope; the spec's "no trailing marker" acceptance is about accepted short tags.

## Files changed
- packages/llama/src/llama/titles.py
- packages/llama/src/llama/stages/gather.py
- packages/llama/tests/test_titles.py
- packages/llama/tests/test_stage_gather.py
- packages/llama/tests/fixtures/tnd2006-12-13.json (new)

---

# Fix round 1 (Important 1: 2a re-accepted a 2b recording-level demotion)

Commit: `fix(gather): 2a never re-accepts a 2b-demoted position` (see `git log -1` on held-backlog-tier1).

## What changed
- `gather.accept_short_tags` gains a **required** keyword `demoted: frozenset[int]` (0-based positions; required rather than defaulted so no caller can silently omit it) and skips `i in demoted`. Docstring explains the whole-tag vs per-component mismatch.
- `compute_gather` passes `demoted=frozenset(demoted)` — the 2b list already computed (placeholder_positions minus override positions).
- Existing unit calls updated to pass `demoted=frozenset()`.
- Optional item taken: reachable fixpoint rows `("F > #", "F", "F")` and `("1922 $ #", "1922", "1922")` beside `Dew > #`.

## Covering tests
- `test_accept_short_tags_skips_positions_2b_demoted`: `["J > J"]*4`, `j` corroborated, demoted {0,1,2} -> tracks 1-3 stay unresolved, track 4 (control, not demoted) accepted; one note for track 4 only.
- `test_2a_does_not_reaccept_a_recording_level_2b_demotion`: tnd fixture with every tag `J > J`, sibling corroborates `J` -> 2b placeholder notes present, no `accepted short tag title` note, all tracks unresolved.
- RED on HEAD before the fix: the pipeline test failed on the behaviour (`assert not any(... 'accepted short tag title' ...)` -> True), not on a signature error.

## Commands / output
- Target files: `./.venv/bin/python -m pytest packages/llama/tests/test_titles.py packages/llama/tests/test_stage_gather.py -q` -> 213 passed.
- Full suite: `./.venv/bin/python -m pytest -q` -> 3425 passed, 1 skipped, 8 deselected.

## Mutants (same recipe: fresh rsync copy, PYTHONPATH shadow proven, private PYTHONPYCACHEPREFIX, predicted first)
| mutant | predicted test | result |
|---|---|---|
| (j) drop `i in demoted` skip | test_accept_short_tags_skips_positions_2b_demoted | caught by predicted (+ test_2a_does_not_reaccept_a_recording_level_2b_demotion) |
| (k) call site passes `frozenset()` | test_2a_does_not_reaccept_a_recording_level_2b_demotion | caught by predicted |
