### Spec Compliance
- ✅ Spec compliant. Checked against the brief and spec slice 5:
  - `STRIP_SOURCES` equals the brief's set exactly (title_cosmetics.py:15-16); `override`/`unresolved` excluded and pinned (test_title_cosmetics.py:52).
  - The three shapes are the brief's regexes verbatim (title_cosmetics.py:18-22); the stem is case-insensitive as specified.
  - Keep rule (title_cosmetics.py:31-37): non-empty, not `is_placeholder_text`, `is_real_title` or 2a shape. The 2a shape is `any(isalnum)` on `tag_core` and not `is_junk_tag`, which is the same composition slice 4 uses (title_hygiene.py:658). Otherwise the title is unchanged.
  - Note string matches the fixed form `cosmetic title strip: track <n> '<old>' -> '<new>'`. `n = pos + 1`, which equals `Track.index` (titles.py:503 builds `index=pos + 1`) and matches the convention in title_hygiene.py:447/517 and lossless_titles.py:208.
  - All six required tests are present under the brief's names (test_title_cosmetics.py:16-57), and the brief's anti-goal titles stay unchanged.
  - Protected names: the diff adds two new files and edits no existing file. Protected names appear only as imports (`is_real_title`, `is_junk_tag`), never edited. `setlist.py` is untouched.
  - Extra, harmless: `_TAIL` is compiled with `re.I`, so `Song.FLAC` is also stripped. The brief does not say whether the tail is case-insensitive.
- ⚠️ Cannot verify from diff:
  - Placement ("after every gather flag is computed, immediately before `Show` is built") belongs to the later wiring task.
  - The suite count (4631 passed) is the implementer's claim. I did not re-run the suite.
  - The replay acceptance (zero flag and set-label changes) is Task 13's.

### Strengths
- Pure, small and non-mutating: it uses `model_copy`, and the test at test_title_cosmetics.py:35 checks that the inputs are not mutated.
- It reuses the existing predicates (`is_placeholder_text`, `is_real_title`, `tag_core`, `is_junk_tag`) and does not re-implement them.
- I probed 30+ adversarial inputs (log: t10-rev.log) and no real title was damaged:
  - `4:20 Polka`, `2:45 AM`, `1 Samuel 15:23`, `8 Cylinders`, `E: Ripple`, `S2: Song` and `set1: Song` are all unchanged.
  - `20:00 - 2:45 AM` is left whole: the leading strip would give `2:45 AM`, and the keep rule rejects that.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **The keep rule, slice 5's only guard on a strict surface, is not tested at all.** (test_title_cosmetics.py, whole file; title_cosmetics.py:31-37)
   - **What's wrong:** No test input produces a stripped result that is non-empty and should still be refused or accepted on the 2a arm. The only refusal test (`test_residue_only_title_left_alone`) strips to `""`, so only the `not text` arm is exercised.
   - **Evidence:** I ran an in-memory mutant, `_acceptable = lambda t: bool(t)`, against every test in the file, and zero tests failed (logged).
   - **Why it matters:** The placeholder arm is load-bearing. `is_real_title` passes, and only `is_placeholder_text` refuses, all of these: `track01.flac` -> `track01`, `tmp.wav` -> `tmp`, `d1t01 Track 1` -> `Track 1`, `06:58 - Track 03` -> `Track 03`, `gd1977-05-08.sbd.flac` -> `gd1977-05-08.sbd`. A regression in `_acceptable` would ship placeholders as titles with a green suite. Neither the 2a acceptance arm (`06:58 - 42` -> `42`) nor the `is_junk_tag` veto (`06:58 - 12/31/95` stays whole) is pinned either.
   - **Fix:** add assertions for each arm:
     - placeholder refusal: `track01.flac`, `d1t01 Track 1` and `06:58 - Track 03` stay unchanged;
     - 2a acceptance: `06:58 - 42` -> `42`;
     - junk/date veto: `06:58 - 12/31/95` stays unchanged.
     Re-run the mutant to confirm each arm is caught.

#### Minor (Nice to Have)
1. **A whitespace-only difference counts as a strip.** (title_cosmetics.py:28, 47-48)
   - **What's wrong:** `_strip` always `.strip()`s, so a title with no shape match but surrounding whitespace (`'Sugaree '`) is rewritten, gets a note, and is counted in `changed` (probed).
   - **Why it matters:** The spec says to strip only these shapes and otherwise leave the title exactly as it was. Tag titles arrive stripped (`clean_tag_title(' Sugaree  ')` -> `'Sugaree'`), so this is probably unreachable today. If any rung ever ships unstripped text, it would inflate slice 5's notes and its per-path wrong-title count.
   - **Fix:** count a change only when one of the three regexes matched, or compare against `t.title.strip()`.
2. **The verbatim stem regex leaves debris in some shapes** (plan-level, for the spec owner rather than the implementer). Examples (probed):
   - `Esau (s2t01)` -> `Esau ()`
   - `gd_d1t04 Song` -> `gd_Song`
   - `foo.bar.d1t1.Song` -> `foo.bar.Song`
   - `s1t2s1t3 Song` -> `s1t3 Song`

   All four are accepted, because `is_real_title` passes them. None damages a real title, since each input was already junk, but each result is still junk and carries a note claiming a cosmetic fix. Worth a look when Task 13's hand-check reviews slice-5 rows. An empty `()` result in particular could be refused cheaply.
3. **One input in `test_never_override_or_unresolved` does not test what it names.** (test_title_cosmetics.py:50-51)
   - **What's wrong:** The unresolved input `phish1995-12-31d2t05.flac` strips to `""` even under `tags`, so the source gate is not what keeps it unchanged.
   - **Mitigation:** the `STRIP_SOURCES` membership assertion on line 52 does pin the gate.
   - **Fix:** use an unresolved title that would otherwise strip to something acceptable, e.g. `06:58 - X` with source `unresolved`.

### Assessment
**Task quality:** Needs fixes
**Reasoning:** The implementation matches the brief exactly and damages none of the anti-goal titles. But the spec's keep rule, the only thing that stops slice 5 shipping placeholders on a strict surface, is unpinned: a mutant reducing it to `bool(text)` passes every test.
