VERDICT: CHANGES REQUIRED

Reviewer: Opus, read-only. Reviewed b7147e0..09d50fd (one commit, 09d50fd) in a `git archive` snapshot with PYTHONPATH shadowing proven (llama.__file__ resolved inside the snapshot). No files in the worktree were changed and no commits were made. The snapshot and mutation copies are removed. Log: $D/fw5-rev/fw5-rev.log.

The implementation matches the brief exactly. Changes are required only because of the orchestrator's extra question: the comma rule the brief specified is broader than the defect, on the strict surface. Exactly one gate is recommended (I1).

## Spec compliance (fw5-brief.md)

| Item | Status | Where |
|---|---|---|
| 1. `song_comma_components`: depth-tracked comma split, fewer than 2 non-blank parts returns `[]`, otherwise the concatenated `song_components(part)`, with a docstring giving the reason and "only ADDS" | ✅ | brief.py:121-142 |
| 2. `briefing_guard` components set also takes `song_comma_components(t.title)`. `exact`, `known_song`, `song_components`, `normalize_song` and `_BRIEF_*` are unchanged. Mentions are not split. | ✅ | brief.py:217-219 (diff touches nothing else) |
| 3. Call-site audit of `song_components(` | ✅ | Non-test uses are only brief.py:142, 151, 217, 218. replay.py:257/353/461 call `briefing_guard` itself, so they inherit the change. scripts/replay_holds.py has no use. The report's claim is verified. |
| Test 1: smashingpumpkins shape | ✅ | test_stage_brief.py `test_comma_merged_title_parts_are_known_songs`. `_show` titles are `Song N`, so no other track carries those songs. |
| Test 2: commas inside parentheses (`[]` and `Phil Lesh` is flagged) | ✅ | `test_commas_inside_parentheses_never_split` |
| Test 3: a single-part title returns `[]` | ✅ | `test_single_part_title_has_no_comma_components` (also covers `Ripple,`) |
| Test 4: existing assertions unedited | ✅ | The diff to the test file adds lines only |
| Test 5: `Mayonaise` is still flagged | ✅ | `test_song_in_no_title_is_still_flagged_with_merged_title` |
| Commit message is verbatim | ✅ | 09d50fd |
| Do-not-retune grep over the diff | ✅ | Only context lines mention `normalize_song`/`_BRIEF_SEGUE`, and neither moved |

## Findings

### Critical
None.

### Important
**I1. The rule as built opens the strict surface far wider than the defect, for no measured benefit beyond it.** brief.py:139 is `if len(parts) < 2: return []`.

Failure scenario: a show has a track titled `Talk To Me Devil, Again`, `Sit Down, Baby`, `Wild, Free, & Reckless` or `Blind, Crippled, And Crazy`. Its briefing names a song `Again`, `Baby`, `Free` or `Crazy` (all real song titles) that research mentions but the tape does not contain. The guard now passes it.

Measured over the live library: 694 titles split, and 306 new single-word (component, title) pairs are not otherwise known. They include city names, `ca02`…`ca29` and numerals.

Benefit, measured over all 2,550 stored `briefing.json` × `show.json`: under **every** candidate gate, exactly **one** stored mention changes from unknown to known. That mention is the target, `smashingpumpkins-1994-04-17 | Girl Named Sandoz`. So the extra width of the rule as built buys nothing observed, and the narrowest gate costs nothing observed.

**Fix (the exact rule): a title splits only when EVERY top-level comma part carries its own trailing parenthetical.** This is the shape the helper's docstring already describes (`A (tease), B (tease), C (tease)`). Replace brief.py:139-140 with:

```python
    if len(parts) < 2 or not all(_BRIEF_PAREN.search(_BRIEF_TRAILING.sub("", p)) for p in parts):
        return []
```

Then update the docstring: "...split only when there are at least two non-blank parts and every part carries its own trailing parenthetical (the per-song annotation that marks a merged track)...". Add one behaviour test:
- `song_comma_components("Talk To Me Devil, Again") == []`
- `song_comma_components("Lawyers, Guns and Money (Warren Zevon)") == []`
- `briefing_guard` on a show with the track `Talk To Me Devil, Again` and the mention `Again` returns `["briefing mentions unknown song: Again"]`

Pair it with a mutant M5 (drop the `all(...)` clause), predicted to be caught by that test.

I ran this rule and the probe test in a scratch copy:
- with the gate: test_stage_brief.py has 70 passed, including all 4 of fw5's tests, so smashingpumpkins still clears;
- on the as-built code, the probe test fails, so it discriminates.

Gate measurement (read-only parse of 3,467 `~/.llama/shows/*/show.json`). "New pairs" means (component, title) pairs not already in that show's base `exact | song_components | joined` set. "Stored mentions newly known" is over 2,550 stored briefings.

| gate | titles split | shows | new pairs | single-word | multi-word | smashingpumpkins clears | stored mentions newly known |
|---|---|---|---|---|---|---|---|
| G0 as built (>= 2 parts) | 694 | 511 | 872 | 306 | 566 | yes | 1 (the target) |
| G1 every part's components >= 2 words | 276 | 233 | 367 | 0 | 367 | yes | 1 (the target) |
| G2 at least 1 part has a trailing paren | 50 | 25 | 40 | 16 | 24 | yes | 1 (the target) |
| **G2b every part has a trailing paren (recommended)** | **3** | **3** | **3** | **0** | **3** | **yes** | **1 (the target)** |
| G3 >= 3 parts | 101 | 74 | 210 | 106 | 104 | yes | 1 (the target) |

The three titles G2b still splits are all genuinely merged tracks:
- `Stay With Me (tease), Girl Named Sandoz (tease), Happy Birthday (tease)`
- `(interview), Backstreet's Back [Backstreet Boys] (tease)`
- `Lovefool [The Cardigans] (tease), (picking the dancers)`

Why G2b over G1, which is the runner-up: G1 removes every single-word fragment, but it still splits 276 titles. Its residual multi-word fragments include real song names cut out of single songs: `touch me` (from `Touch Me, I'm Going to Scream, Pt. 2`), `wake up` (from `Wake Up, Little Suzie`), `new york` and `red roof`. G2b's residual is three genuinely merged tracks.

Known cost of G2b: a merged title with an unannotated first part, such as `Bullet with Butterfly Wings, Fly by Night [Rush] (tease)`, does not split. A mention of `Bullet with Butterfly Wings` there would stay a hold. No stored briefing hits this. It fails safe, which means a hold and not a silent pass.

### Minor
- M-a: square brackets do not count as nesting. A comma inside `[...]` splits, for example `[Banter- Dead Rider Owns, seriously, kylenote, ...]`. Under G2b this is moot unless every part also ends in `(...)`. No action is needed if I1 is applied.
- M-b: the brief's M3 mutant, which removes the `< 2` check, is close to behaviour-equivalent for the guard. One part is the whole title, so `song_components(part) == song_components(title)`, which is already in the set. It differs only when a stray top-level comma blocks `_BRIEF_PAREN`, e.g. `X (tease),`. `test_single_part_title_has_no_comma_components` catches it through the helper's specified return value, which is the brief's own contract, so this is acceptable.
- Code quality is otherwise fine. The `max(0, depth - 1)` clamp makes an unbalanced `)` harmless, and an unclosed `(` suppresses splitting, which is conservative. The mid-file test import matches the file's existing idiom.

## Mutation spot-check
Each mutant ran in its own copy under a private `MROOT` with its own PYTHONPYCACHEPREFIX, and shadowing was proven for each one. The predicted test for each was written to the log before the flip.

| mutant | predicted test | result |
|---|---|---|
| M1: drop the `song_comma_components` union (implementer's) | test_comma_merged_title_parts_are_known_songs | caught by it (1 failed, 68 passed) |
| M2: split on every comma, ignoring depth (implementer's) | test_commas_inside_parentheses_never_split | caught by it (1 failed, 68 passed) |
| M4: drop the blank-part filter (not listed in the brief; added by me) | test_single_part_title_has_no_comma_components (`Ripple,`) | caught by it (1 failed, 68 passed) |

## Suite
Snapshot at 09d50fd: `3769 passed, 1 skipped, 8 deselected, 26 warnings in 143.48s`. This matches the implementer's claim.
