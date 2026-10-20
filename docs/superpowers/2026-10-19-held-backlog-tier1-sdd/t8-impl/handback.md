# t8-impl handback — Task 8: cross-source parse vocabulary + placeholders.py

Status: DONE. Commit e416018 on held-backlog-tier1.

## Implemented
- `packages/llama/src/llama/placeholders.py` (new, pure; imports only `re` and `llama.structure.fuzzy_norm_title`):
  NUMBER_WORDS, is_placeholder, is_timestamp, starts_with_timestamp, is_date_like, looks_like_filename,
  RESIDUE_TOKENS (one re.I regex, prefix start-anchored), letters_after_residue, is_residue,
  is_placeholder_title, is_junk_tag, recording_level_junk. Regexes exactly as the brief; each carries a
  comment naming its spec class and bounding near miss.
- `gather.CanonicalBuild.corroboration: dict[str, tuple[str, ...]] = {}` (trailing field) and a helper
  `gather._corroboration(parses, descriptions, chosen_desc, setlistfm_parse)`, called once in
  `build_canonical` right after `_collect_parses` (while `parses` is still parallel to `descriptions`, i.e.
  before the setlist.fm insert). Eligible: `lma:` parses whose `" ".join(desc.split())` differs from the
  chosen description's, plus the setlist.fm parse; never `chosen`/`llm`. Empty normalized titles skipped;
  sources sorted and de-duplicated. Built from the raw parses (before head-banner strip).
- No positional unpacks of `build_canonical`/`CanonicalBuild` remain (grepped packages/ and scripts/).

## TDD
- RED: test_placeholders.py -> `ModuleNotFoundError: No module named 'llama.placeholders'`;
  the 3 corroboration tests -> AttributeError (no `corroboration`).
- GREEN: test_placeholders.py 84 passed (brief tables + ruled-limitation pin); corroboration 3 passed.
- Added beyond the brief: `test_residue_class_demotes_the_ruled_limitation_cases` (Jam 12-31-99, Master,
  Matrix ARE demoted — the ruling's required pin), `test_build_canonical_corroboration_skips_items_that_normalize_to_nothing`
  (survivor-killer for mutant g), `test_recording_level_junk_item_title_that_normalizes_to_nothing_never_matches` (pins h).

## Mutation table (recipe: fresh rsync copy per mutant under $TMPDIR, PYTHONPATH shadow proven by printing
llama.__file__ under the copy each time, private PYTHONPYCACHEPREFIX, worktree python -m pytest; predictions logged before flipping)
| mutant | predicted test | result |
|---|---|---|
| (a) is_junk_tag uses is_timestamp | test_is_junk_tag_never_counts_letters[07:22 - IB49-True] | caught by predicted |
| (b) residue prefix loses `^` | test_letters_after_residue | caught by predicted |
| (c) is_placeholder accepts `untitled` | test_placeholder_near_misses[Untitled], test_is_placeholder_title[Untitled-False] | caught by both |
| (d) is_placeholder_title("") -> True | test_is_placeholder_title[-False] | caught (also [   -False]) |
| (e) corroboration keeps a copying sibling (copy check removed) | test_..._drops_a_sibling_that_copies_the_chosen_description | caught by predicted |
| (e2) copy check without whitespace normalisation | same | caught by predicted |
| (f) chosen parse included (`p.source == "chosen" or ...`) | test_..._excludes_the_chosen_description | caught (plus names_setlistfm, drops_a_sibling) |
| (f-equiv) source filter dropped, copy check kept | — | SURVIVED: equivalent. `parses` holds only `chosen` and `lma:` sources at that point, and the chosen parse's description IS the chosen description, so the copy check already excludes it. The `startswith("lma:")` filter is a deliberate second guard. |
| (g) empty-norm guard removed | test_..._skips_items_that_normalize_to_nothing (new) | caught by predicted |
| (h) recording_level_junk item guard -> `item_title is not None` | test_recording_level_junk_item_title_that_normalizes_to_nothing_never_matches (new) | caught by predicted |

## Full suite
`./.venv/bin/python -m pytest -q` -> 3383 passed, 1 skipped, 8 deselected (baseline 3294 + 89 new).
`llama.__file__` resolves inside the worktree.

## Files changed
- packages/llama/src/llama/placeholders.py (new)
- packages/llama/src/llama/stages/gather.py (CanonicalBuild field, _corroboration, build_canonical wiring)
- packages/llama/tests/test_placeholders.py (new)
- packages/llama/tests/test_stage_gather.py (appended 4 tests)

## Self-review
- Do-not-retune constants: diff grepped for every name in Global Constraints — zero hits. is_real_title untouched.
- The chosen description is read from `_description(meta)` rather than from the `chosen` parse: identical when
  the selected recording is in `candidate.recordings`, and still recognises pasted copies when it is not
  (Review Focus 1's shape, where there is no `chosen` parse at all).
- setlist.fm only in the vocabulary when `from_setlistfm` converted a non-empty result, matching what ranks.

## Deviations / concerns
1. `recording_level_junk`: the item-title arm requires `fuzzy_norm_title(item_title)` to be non-empty, not just
   `item_title` non-empty (brief wording). Stricter = fewer demotions (safe direction): otherwise an item title
   like `---` would make any three distinct empty-normalizing tags "the item's own title". Pinned by test (h).
   Revert to the literal wording if the orchestrator prefers.
2. `CanonicalBuild.corroboration` default `{}` is a shared mutable NamedTuple default (as the brief specifies);
   build_canonical always passes a fresh dict, but consumers (Tasks 9/10) must treat it read-only.
3. For Task 9 (strict surface): per the spec, `is_residue` counts fewer than 3 letters, so uncorroborated short
   tags like `FF`, `J`, `42`, `7-11` ARE residue-class (`is_placeholder_title` True). Only 2a's corroboration
   exemption protects them in 2b. That is the spec's design, but worth the Task 9 reviewer's eye.
