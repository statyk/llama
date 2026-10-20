# t13-rev — Task 13 review (slice 1 gather venue block), 2f72aff..110f72d

### Spec Compliance

- ✅ Spec compliant, for the chain itself. `gather.py:1373-1432` implements the brief's order exactly: enrichment (byte-identical apart from the 1a guard `event.venue.strip()`), 1a, step 1, swap, signature, 1c (`len(events) == 1`), else today's flag; 1d after the chain on every show; then the overrides block, with a venue OR city override removing the 1d flag (`:1430-1431`), and the venue-mismatch removal still venue-override-only.
- Contract texts are verbatim. Swap note (`:1404-1405`): the two literals concatenate to the Contracts f-string exactly. 1c note (`:1412-1413`) and the 1d flag (`:1423`, via `_CITY_CONFLICT_FLAG`) match too.
- Notes go only to `op_notes`, which is `GatherResult.notes` (`:995`, `:1511`). There is nothing new in `notes`/`conflicts`/`review_flags` apart from the 1d flag the spec names.
- `two_venue_signature` (`:959-968`) and `jerrybase_city` (`:953-956`) match the Interfaces signatures and semantics.
- B3 complied with as ruled: `_jb_event` gains a `state` kwarg (default `"ST"` unchanged), and only the RFK test passes `state="DC"`, with a comment (`test_stage_gather.py:980-985, 1032-1041`). It is disclosed in the commit message.
- The rule that a blank vote venue with a blank jerrybase venue never flags holds. The enrichment arm does nothing in that case and nothing else runs; it is pinned by `test_1a_blank_vote_venue_on_a_blank_jerrybase_venue_takes_nothing_from_jerrybase`.
- Every brief test was appended verbatim, and one survivor test was added (`:2849`).
- Do-not-retune constants: the gather.py hunk touches none (only an import line plus the new block). Checked by reading the full hunk.
- Fixtures were checked for shape only. All three are `{files, metadata, reviews}`, with the metadata identifier, venue and coverage as the brief expects (DSO Barrymore Theater/Madison, WI; Guster Weesner/Apple Valley, MN; dodd Rambler Room/Chicago, IL).
- ⚠️ Cannot verify from the diff: step 1 now adds a `venue mismatch` hold to a show whose vote venue equals jerrybase's when the cities are unknown or uncomparable (spec: "In steps 1-3, unknown on either side means not compatible"). The RFK fixture needed B3 for exactly this reason. The flag text then reads `archive 'X' vs jerrybase 'X'`-like. This is a hold, the safe direction, and spec-mandated. Checkpoint C's `newly-held` list should be read for this class specifically.
- ⚠️ Cannot verify from the diff: 1d fires when the selected `coverage` is a non-city but non-empty string ("Minnesota", "USA", "Unknown", a country). `cities_compatible` treats it as a known, incompatible key, so 1d ships that string as the city on a held show. The spec says "an unknown selected city is no conflict". It is a hold, not a silent clear, but Checkpoint C should scan the 1d rows whose `selected_city` is not a city.

### Strengths

- The chain is written as one literal if/elif in the ruled order. The order comment at `:1373-1377` names every arm, so the "1a first and terminal" ruling and the swap-before-1d ordering can be read straight off the code.
- `sel` absent leaves `sel_venue`/`sel_city` None, so the swap, 1c and 1d all fall away naturally, as Review Focus 1 requires. A dedicated test pins it.
- The mutation step was done properly. The implementer predicted that mutant (a) would survive the brief's own GD78 test (it selects the Rambler tape, so the swap's equivalence never holds), confirmed it, and wrote a test that selects the Uptown tape so that only the signature blocks the swap. That was a real gap in the plan's tests, and they closed it.
- `test_two_venue_signature_keeps_the_same_city_double_held` also pins signature-before-1c. With the selected Rambler tape on a single-event Chicago date, 1c would otherwise fire.

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

1. **The city gates on step 1 and on the swap are unpinned.** Both mutants survive every venue-touching test file. Locations: `gather.py:1398` (step 1's `and cities_compatible(archive_city, jb_city)`) and `gather.py:1401` (the swap's `and cities_compatible(sel_city or vote_city, jb_city)`).
   - The spec says city compatibility is "enforced in code on each" arm, and its acceptance item is "Zero cleared shows whose cities are not compatible (also unit-tested)". Only the 1a, 1c and 1d city gates are unit-tested.
   - Measured in a scratch copy (`mktemp -d $TMPDIR/mut-t13-rev-*`, PYTHONPATH shadowing proven by `llama.__file__` under the copy, private PYTHONPYCACHEPREFIX, since removed). Predictions were recorded in the log before the runs.
     - Mutant (f), step 1 without the city gate. Predicted: SURVIVED. Result: SURVIVED. `test_stage_gather.py` 145 passed; test_get_cmd, test_multi_event_integration, test_pipeline, test_replay, test_sessions, test_stage_search and scripts/test_replay_holds 235 passed.
     - Mutant (g), the swap without the city gate. Predicted: SURVIVED. Result: SURVIVED, with the same counts.
   - Both are wrong-clear paths on a strict surface:
     - (f) silently ships a same-name hall in a different city, e.g. a vote "Orpheum Theatre"/"Boston, MA" against jerrybase "Orpheum Theatre"/Madison, WI.
     - (g) swaps in a selected venue that matches jerrybase's name while its city does not, and 1d stays silent whenever the selected city is compatible with the vote's.
   - The plan's mutant list (a)-(e) did not include these, so this is a gap in the plan's test list rather than a failure by the implementer. It still leaves the strict predicate unpinned on two of its four jerrybase-side arms.
   - Fix: two tests.
     - Step 1: vote venue equivalent to jerrybase, vote and selected city e.g. "St. Louis, MO" against the DSO event in Madison, WI, a single recording (so no signature). Expect `venue mismatch` and the vote venue unchanged.
     - Swap: selected venue "Barrymore Theater" with coverage "St. Louis, MO", the vote "The Pageant"/"St. Louis, MO", a single recording (so no signature). Expect no swap note, today's flag, and the venue "The Pageant".

#### Minor (Nice to Have)

1. **1d tests `vote_city` by truthiness without stripping it** (`gather.py:1421`), as the implementer flagged. A whitespace-only vote city is "unknown" under the spec ("known to be incompatible"), yet it fires 1d: the flag reads `vs '  '`, and the selected venue and city ship on a held show. Grouping votes `Counter(r.coverage for r in recs if r.coverage)` (`grouping.py:38`), so a whitespace coverage can win the vote, though rarely. It is the brief's literal text and the hold is the safe direction. Suggested fix: `_stripped(vote_city)` in the 1d guard; the flag can keep the raw text or use the stripped one. This is a deviation from the spec's wording, not from the brief.
2. **Swap and 1c notes survive an operator venue override** (`gather.py:1404, 1412` vs `:1426-1428`). With `overrides.venue` set, `notes.json` still says "venue taken from the selected recording: …" while the override's string ships. This is harmless to `compare` (checkpoint item 2 only checks city compatibility on noted shows), but `llama show` prints a claim that is no longer true. Suggested fix: either drop those two notes when `overrides.venue is not None`, or accept this and document it.
3. **When the signature or else-arm flag is followed by 1d**, the `venue mismatch` text names the vote venue (`archive '{vote}'`), while 1d then ships `sel_venue` (`gather.py:1394`, built before 1d). The flag text describes a string that no longer ships. Both are holds, so this is cosmetic.
4. **`two_venue_signature(candidate)` is computed twice** on the path where the swap's other conditions hold (`:1402`, `:1407`). It is O(n²) over the recordings, which is negligible, but binding it once before the chain is cleaner.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The chain, the contract texts, the rulings and the brief's mutation list are all correctly implemented. However, the city gates on step 1 and on the swap (both wrong-clear guards on a strict surface) survive mutation, which leaves the spec's "zero cleared shows with incompatible cities, also unit-tested" acceptance only partly pinned. Adding two tests closes it, with no code change needed.
