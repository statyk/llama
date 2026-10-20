### Spec Compliance

- ❌ Issues found: one spec requirement is not met. Slice 2b says a 2b-demoted track gets a title only from setlist-gap or sibling-align, and 2a's own text says its veto "rejects a 2b placeholder". 2a re-accepts a position that 2b's recording-level class demoted (Important 1). Everything else matches the brief and spec, with one deliberate, justified deviation (the fixpoint).
- ⚠️ Cannot verify from diff:
  - That `CanonicalBuild.corroboration` also leaves out sibling descriptions that are whitespace-equal copies of the chosen one (ruling 3, Task 8 code at gather.py:777-835). This task tests only the chosen-description exclusion (`test_2a_does_not_count_the_chosen_recordings_own_description`).
  - The spec's own text is ambiguous about the shipped marker set (Minor 2). The harness hand-check should confirm the intended reading.

**The three questions the controller asked**

(1) **Fixpoint deviation. Accepted.** The spec line (spec:542) is: "No shipped title keeps a trailing taper marker." The brief's single pass `HASH(TAIL(s))` leaves a shipped-set marker that sat under a free-standing `#`: `Dew > #` ships as `Dew >`, and `1922 $ #` and `F > #` keep their tails the same way. Looping to a fixpoint fixes that.
  - **Check I ran:** every base in {F, Dew, F#, 100%, Song #9, Moment #2} with every 1-3 suffix drawn from 15 marker forms. 1,158 strings came out differently under fixpoint and single pass.
  - In **0** of them did the fixpoint remove a character outside ` >-=*$+#` or eat into the base.
  - An attached `#` survives, because `_SHIPPED_HASH` needs `\s+`: `F# > #` ships as `F#`.
  - `%`, `@`, `^`, `~` and a bare `-` are never removed: `100% - # #` ships as `100% -`.
  - `Song #9` and `Moment #2` are untouched, since their `#` is not trailing.
  - The loop terminates, because every pass either shortens the string or stops.
  - So the fixpoint strips only what the spec's shipped set names, and it strips nothing the spec wants kept.

(2) **Wiring position. Correct, apart from Important 1.** The order in gather.py is:
  1. `resolve_titles` (:1132), where 2b demotes;
  2. the `overrides.titles` loop (:1135-1140);
  3. `_sibling_transfer` (:1146);
  4. `adopt_gap_titles` (:1177);
  5. `accept_short_tags` (:1191);
  6. the structure branch (`flags = []`, :1196).

  Because 2a runs after both sibling-align and setlist-gap, and both of those fill only unresolved tracks, neither can see or replace a 2a title.

  **Check I ran:** awk over gather.py:1190-1420 for `title_source`, `"title"` and `model_copy`. Every later `model_copy` updates only `set` (:1201, :1226) or `matched` (:1286-1288). Nothing after 2a rewrites a title.

  2a reads `tag_titles` and `tag_source` from the same `tag_layer` call that 2b used (:1086). `tag_source` is `"tags"` or `"sibling-format"`, and 2a judges only positions where `title_source == "unresolved"`. So overrides (M9), sibling-align, setlist-gap and real tags are never touched.

  **The gap:** "unresolved" also includes positions 2b demoted, which brings in Important 1.

(3) **tnd set labels moving. Expected.** Spec:188-195 ("Set structure under a title change … a deterministic re-gather can still move labels elsewhere, hence the structure-changed list") and the acceptance bullet at spec:544 both make this the harness's job, not a 2a defect.

**Same output as before when nothing is accepted? Yes, by construction.** When no position qualifies, `accept_short_tags` returns `list(tracks)` with the same `Track` objects and `[]` for notes, so `op_notes` is unchanged. The only other change at the call site is binding `tag_layer`'s second return value, which used to be thrown away. 2a has no branch that depends on providers.

**Protected constants:** I grepped the source and test hunks of the diff for every do-not-retune name (`is_real_title` body, `_YEAR_LIKE`, `title_fraction`, `_TRACK_NUM_PREFIX`, `normalize_song`, `DEFAULT_ALIASES`, `GD_SHORTHAND`, `_RECOVER_*`, tail-guard names, junk-duration names, `align_coverage_threshold`, `_ENUMERATED_MIN_*`, `_STRUCTURE_PREFIX`, `_FOOTNOTE_TAIL`, `TAUTOLOGICAL`). The only hits are imports, call sites, comments and tests. No protected definition changed.

**Ruling 6:** the 2a notes go only to `op_notes` (gather.py:1194). Nothing is added to `structure.conflicts` or `review_flags`.

**Contract string:** gather.py:915-916 matches the 2a row of the Contracts table verbatim, with the source list sorted and unioned.

### Strengths
- The brief's rule is implemented exactly. The order of the checks is cheap first, and the input list is left untouched (pinned at test_stage_gather.py:~2552).
- The added tests close real holes the brief left open:
  - mutant (c), with "J > X" against "J > F >";
  - the `is_real_title` gate (f), which the brief's `tmp` row could not pin alone because the junk veto also catches `tmp`;
  - stamping the `sibling-format` source;
  - M9 on the real fixture.
- The mutation table follows the recipe. Every mutant is caught by the test predicted for it, and survivor (f) was found and fixed.
- The 2a fixture is captured from cache offline. The no-sibling test checks ruling 3 end to end, including the remaining `unresolved track titles` flag.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **gather.py:899-905 and the call at :1191: 2a re-accepts a position 2b demoted as recording-level junk.** This is the STRICT SURFACE (a junk title accepted onto a show).
   - **Mechanism:** 2b judges the whole tag (`fuzzy_norm_title(t) in corroboration`, titles.py:326). 2a judges each segue component separately. A recording-level 2b placeholder can therefore fail `is_real_title`, pass `is_junk_tag` (which has no recording-level arm), and have every component corroborated.
   - **Measured on HEAD:** `placeholder_positions(["J > J"]*4, corroboration={"j"})` returns `[0, 1, 2, 3]`, meaning all four are demoted. `accept_short_tags` with the same tags and `{"j": ("lma:x",)}` then ships `J > J` on all four tracks, with the note `accepted short tag title: track 1 'J > J' corroborated by lma:x`.
   - **Which spec text it breaks:** spec 2b says "Setlist-gap and sibling-align … are the only ways such a track can still get a title", and spec 2a says the veto "rejects a 2b placeholder".
   - **Reach:** only tags with at most 2 letters that contain a segue (`J > J`, `42 > 42`), identical on 3 or more tracks. That is rare, but it is a demonstrated path onto the strict surface, and the fix costs one line.
   - **Partial cause:** the implementer's `Jam > Jam` test comment (test_stage_gather.py `test_accept_short_tags_never_judges_a_real_title_tag`) spots this class but relies on the `is_real_title` gate, and that gate does not cover tags with at most 2 letters.
   - **Fix:** give `accept_short_tags` the positions 2b demoted, for example a keyword `demoted: frozenset[int]` passed `frozenset(demoted)` from gather.py:1087, and skip them. Add a unit row with `["J > J"]*3`, plus a mutant that drops the skip.

#### Minor (Nice to Have)
1. **gather.py:902-905: the junk veto and the `metadata_norms` veto look only at the whole core, never at each segue component.**
   - Example: `is_junk_tag("J > 05:27")` is False. If a timed tracklist in a sibling description made `05:27` an item, `J > 05:27` would be accepted.
   - This follows the spec literally ("the core passes 2a's junk veto"), and the case is contrived, so it is not blocking.
   - Applying both vetoes to each component would be cheap and strictly safer.
2. **titles.py:279 (`_CORE_TAIL`) and :280 (`_SHIPPED_TAIL`): accepted titles can still ship with a trailing marker. Plan-level, copied verbatim from the brief.**
   - The brief's core set adds a bare `-`, which the spec's core list at spec:502 ("`> -> => * % # @ ^ ~ $ +`") does not include. So `J -` has core `J` and ships as `J -`.
   - `@`, `^` and `~` are in the core set but not the shipped set, so `FF ~` ships as `FF ~` and `J @` as `J @`.
   - The spec allows this for `%` explicitly. Its acceptance line "No shipped title keeps a trailing taper marker" (spec:542) reads against it for `-`, `@`, `^` and `~`.
   - The controller or the human should decide which reading wins, or make sure the harness hand-check of accepted short tags looks at these.
3. **test_titles.py: the `("Dew > #", "Dew", "Dew")` row tests a tag that passes `is_real_title`, so that tag never reaches 2a in the pipeline.** A row that 2a can actually reach would pin the fixpoint where it matters: `("1922 $ #", "1922", "1922")` or `("F > #", "F", "F")`. I measured both on HEAD, and both come out correct.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The implementation matches the brief, the wiring order is right, the fixpoint is safe and justified, and the tests and mutation evidence are solid. But 2a can re-adopt a 2b recording-level-demoted placeholder, measured on HEAD, which breaks spec 2b's "only setlist-gap and sibling-align" rule on the strict surface. The fix is a one-line skip of the `demoted` positions plus a test.
