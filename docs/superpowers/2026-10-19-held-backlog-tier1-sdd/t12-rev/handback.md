# t12-rev handback — Task 12 (1b venues_equivalent + cities_compatible), 9b74164..715c3db

### Spec Compliance

- ❌ Issues found: one interface deviation. `_city_parts` turns region punctuation into SPACES (via `_clean_place`), where the brief's interface says region punctuation is DROPPED. Result: `Washington, D.C.` vs `Washington, DC` -> False (details under Important #1). Everything else verified against the brief/spec:
  - `_one_edit` (structure.py:279-294) correct Levenshtein<=1; callers apply the floor (`_tokens_equal` :309-312, `cities_compatible` :421).
  - `_place_tokens` (:297-306): `'`/`’` deleted, `race track`->`racetrack` (ruling B2, present at :303 and pinned by the Meramec row; implementer's mutant f caught), `_PLACE_FOLD` before the stopword drop.
  - `venues_equivalent` (:344-364): empty handling unchanged -> joined-string test -> subset over university-stripped lists, declined (not True, not False) when a side empties -> acronym on unstripped lists. Matches the brief's order exactly.
  - `_UNIVERSITY_TOKENS`, `_CITY_FOLDS`, `_METRO_ALIASES` (4 entries), `_REGION_FOLDS` (verbatim from the brief, operator-approved; comment "Decision P8, signed off with the plan."), `_COUNTRY_NOISE` all present and byte-matching the brief.
  - `cities_compatible` (:411-426): empty key False; both regions non-empty and different False; equality / one-edit >=6 / whole-token containment. Matches.
  - Every brief test row present in test_structure.py (venue true/false parametrizations, `test_one_edit`, `test_cities_compatible`, `test_cities_not_compatible`).
  - Do-not-retune constants: the diff touches only the venue block of structure.py and test_structure.py; none of the protected names appears in any hunk. `_PLACE_ABBREV` is untouched and still has `theatre` (structure.py:254, checked).
  - Callers: `venues_equivalent(` only at gather.py:1350; `_place_tokens` also at scripts/replay_holds.py:38/423 (grep-checked, matches the implementer's report). `_tokens_equal` is also used by `_acronym_match` (:326), so the one-edit rule widens the acronym path's token compare too — consistent with the spec's "one edit allowed on tokens of >= 6 characters".
- ⚠️ Cannot verify from diff: (1) the full-suite count (3523) and the mutation table are the implementer's claims; the table is complete for brief mutants a-e plus extras f/g/g2/a2 and names a test per mutant, but I did not re-run it. (2) Whether gather composes the jerrybase side as `"<city>, <state>"` with a two-letter state (jerrybase CSV has a separate `state` column) — Task 13's wiring; the D.C. finding below assumes it does.

### Strengths

- Clean, small, readable implementation; `_one_edit` is a correct O(n) one-pass without a DP table.
- The university-strip decline is implemented exactly as the spec's subtle "neither True nor short-circuit False" wording requires, with a comment saying why (structure.py:358-360).
- The implementer found that brief mutants (a) floor >=5 SURVIVED the brief's own tests on both venue and city paths, and pinned the floor from both sides (Bryce/Bruce, Macon/Mason below; Barton/Burton, Austin/Austen at exactly 6). These extra tests are good: each is a true boundary pair, and the 715c3db fix (a genuine 6-char pair) shows the inclusive side was checked properly rather than assumed.
- Apostrophe handling is robust beyond the brief: `‘` and backtick variants still match via the joined-string test (probed).

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)

1. **structure.py:404 (`_city_parts`, region via `_clean_place` at :395-396) — dotted region abbreviations never match their postal form.** `_clean_place` maps punctuation to spaces, so `D.C.` -> `d c`, `N.Y.` -> `n y`, and these differ from `dc`/`ny`. Probed: `cities_compatible("Washington, D.C.", "Washington, DC")` False; `("Utica, N.Y.", "Utica, NY")` False; `("New York, N.Y.", "New York, NY")` False. The brief's interface says region punctuation is *dropped* (key punctuation goes to spaces; region punctuation is dropped — two different rules, and the code applies the key rule to both). This is real data, not hypothetical: 15 of 3,293 library `show.json` cities with a region end `, D.C.` (plus `N.Y.` x2, `N.Y` x1), and 28 `D.C.` / 10 `N.Y.` / 3 `N.J.` / 2 `W.V.` region fields among 12,800 cached archive.org `coverage` values (read-only scan of `~/.llama/shows/*/show.json` and `~/.llama/cache/md_*.json`). Consequence once Task 13 wires it in: step 1 cannot clear these shows, and — worse — 1d, which runs on every show, treats `Washington, D.C.` (selected) vs `Washington, DC` (vote) as a known city conflict, swaps the shipped venue/city and adds a NEW hold `recordings of this date disagree on city`. The brief's own row `("Washington, District of Columbia", "Washington, DC")` shows DC equivalence was intended. Fix: for the region, delete punctuation (`re.sub(r"[^a-z0-9 ]", "", ...)`) before the country-noise strip and the fold; add test rows `("Washington, D.C.", "Washington, DC")`, `("Utica, N.Y.", "Utica, NY")` to `test_cities_compatible`. (Side effect worth checking with that fix: `CO / U.S.A.` would then read `co usa` -> `co`, which is also right.)

#### Minor (Nice to Have)

1. **structure.py:312 and :421 — the 6-character floor is an unnamed literal, duplicated.** The spec's "New constants" lists "the one-edit rule's 6-character floor", and the Global Constraints say new constants are "named in code with a comment citing the spec section". The brief's interface text itself wrote `>= 6` inline, which induced this. Both copies are independently pinned by tests (mutants a/a2/g/g2), so behaviour is safe today; a named `_ONE_EDIT_MIN_LEN = 6` with a spec-citing comment, used at both sites, would satisfy the constraint and keep the two from drifting. Similarly `_METRO_ALIASES` carries no comment saying it is the survey's four measured pairs, fixed a priori (the section header at :375 cites the spec section, which arguably covers it).
2. **Spec-mandated widening to surface for Task 13 / the harness hand-check (not an implementation defect).** The university strip creates new equivalences that the city check does NOT catch when both venues are in the same city. Probed True now (False before): `UC Berkeley` vs `Berkeley Community Theatre`; `UC Santa Barbara` vs `Santa Barbara County Bowl`. Also True now: `University of Oregon` vs `Oregon State University`, `University of Michigan` vs `Michigan State University` (different cities, so the city predicate should catch these). And in the conservative direction: `MIT` vs `Kresge Auditorium, MIT` was True (plain subset) and is now False (strip empties a side). Since the venue tripwire is a strict surface (a wrong clear ships a mislabelled show), the Task 13 harness change list should be scanned for clears where one side was university-stripped. Spec authority, so this is for the controller/operator, not the implementer.
3. **Spec-mandated containment with a missing region:** `cities_compatible("York, PA", "New York")` and `("Portland", "South Portland, ME")` are True (whole-token containment, one side has no region). Per spec; noted for the same hand-check.
4. **test_structure.py — `test_cities_not_compatible` asserts one direction only** (brief-supplied shape), whereas `test_cities_compatible` and both venue tests assert symmetry. Every negative row happens to be symmetric under the code, but a symmetric assert would cost nothing.
5. `_COUNTRY_NOISE` does not cover `united states of america` (leaves `of america`) or dotted `u.s.a.` (leaves `u s a`, fixed by Important #1's punctuation drop). Brief-conformant as written.

### Checks run
- Shadowing: `./.venv/bin/python -c "import llama; print(llama.__file__)"` resolves inside this worktree.
- Read-only probe (logged in t12-rev.log) of `cities_compatible`/`_city_parts`/`venues_equivalent` on: dotted regions (D.C., N.Y., Wash., ON Canada, CA, USA), region-less containment, university-strip widening, apostrophe variants. Results as quoted above.
- Grep of callers of `venues_equivalent(`, `_place_tokens`, `_tokens_equal`, `cities_compatible`, `_one_edit` across packages/ and scripts/.
- Read-only scan of library show.json cities and cached coverage fields for dotted region forms (counts above).
- No suite re-run, no mutation re-run, no worktree mutation.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** A faithful, well-tested implementation of 1b and the city predicate, with good boundary pins added beyond the brief; but region punctuation goes to spaces instead of being dropped, so `Washington, D.C.` is not `Washington, DC`. Real library data has that form, and once Task 13 wires the predicate into 1d it would create spurious city-conflict holds and string swaps.
