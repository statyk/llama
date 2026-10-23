### Spec Compliance
- ✅ Spec compliant. Every Task 4 interface in the brief is present, with the specified signature, in `packages/llama/src/llama/title_hygiene.py`: the constants, `INDEPENDENT_SOURCES`, `DESC_POSITION`, `ALL_SLICES`/`ENABLED_SLICES`, `agrees`, `duplicate`, `Hygiene` and `judge`. `structure.hygienic_title` gains only the keyword-only `require_real: bool = True`, and its clause expression is otherwise unchanged (`structure.py:1350-1381` in the diff). `judge` follows the brief's order (`title_hygiene.py:92-134`): filler entry, then slot placeholder, then metadata, then banner, header, annotation, timestamp, filename residue, no alnum, and finally `hygienic_title(..., require_real=False)`. The class name it gives for a `hygienic_title` failure is derived after that call returns False and is used only for the note. `is_junk_tag` is never used. All nine Step-1 tests are present, plus one extra filler test.
- Protected-names grep of the diff: the only protected name touched is `hygienic_title`, and only as the brief permits (the keyword-only parameter and a docstring paragraph). `git diff main` is empty for `setlist.py`, `titles.py`, `placeholders.py` and `siblings.py`.
- Named risk (callers must see byte-identical behaviour under the default). I grepped the callers. `structure.py:1435` (setlist-gap) and `siblings.py:310` (sibling-align) both call it with two positional arguments, and the parameter is keyword-only, so neither can pass it. With `require_real=True`, `(not True or is_real_title(t))` short-circuits exactly like the old `is_real_title(t)`, in the same clause order. The behaviour is identical.
- I probed every spec PASS fixture (`2:45 AM`, `09-15-00`, `12.28.99`, `42`, `405`, `118`, `420`, `J`, `1 in 7`): all are ok. I probed every DECLINE fixture with the expected scope. Their classes:
  - `"Set" 1:`: trailing colon.
  - `Disc 1, Track 10`: header.
  - `s1t07:`: trailing colon.
  - `w/ Eric Johnson` and `Fruit Bats opened`: annotation.
  - `soulive2012-02-24-d1t01`: filename residue.
  - `Unknown`, `unk` and `(unknown)`: track-level slot placeholder.
  - `Set 2` and `CD 2`: header.
  - A 200-character entry: over length.
  - `...` and the empty string: no alnum.
  - `05:12) --`: timestamp, through the `_LEAD_TIME` arm.
  - Unlike these, `Me &amp; My Uncle`, `“Sugaree”` and `Truckin’` pass. `agrees("Joel Piano Solo (02:05)", "piano solo^")` is True.
- ⚠️ Cannot verify from diff:
  - The implementer's full-suite count (4518 passed) is a claim, and per the rubric I did not re-run the suite.
  - The RED run for the structure pin test was not captured. It would plainly fail on the old code with a TypeError on the unknown keyword.

### Strengths
- `hygienic_title` change (`structure.py:1373-1376`): it is minimal and the default is pinned. `test_structure.py:2091-2096` covers both values of the parameter, plus `Set 1:` to show that the other clauses still apply under `require_real=False`.
- One definition (`title_hygiene.py:126-133`): check 1 calls `hygienic_title` rather than re-composing its length, junk and colon clauses. The class name is derived only after it returns False, as the brief says.
- `agrees` (`title_hygiene.py:50-59`): it applies `fuzzy_norm_title` with optional aliases, then the short-core equality gate (on either side), then `loosely_same_title` unmodified, all on `clean_one` copies. That matches the brief's "Aliases" constraint.
- Bare numbers (`title_hygiene.py:98-103`): the own-core exception is checked first. The rule compares against the 1-based `track_no` and is covered by tests (`4` at track 5 is ok).
- Sources pin (`test_title_hygiene.py:73-76`): it pins both the difference between the two source sets and the exact `siblings.INDEPENDENT_TITLE_SOURCES` set.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **Most decline tests do not check which class fired** (`test_title_hygiene.py:20-31`). Only `"Set" 1:` has its `check` asserted. Every other decline fixture asserts only `(ok, scope)`. The check name is load-bearing downstream: it goes into the fixed note string, and `SHIFT_CHECKS` and the gate's per-class counts key on it. Two concrete mix-ups would therefore pass the suite:
   - `Disc 1, Track 10` declining as, say, `junk title` instead of `header`.
   - `w/ Eric Johnson` falling through to a different show class.

   Fix: assert `h.check` per fixture (`hygiene:header`, `hygiene:annotation`, `hygiene:filename residue`, `slot placeholder` and so on).
2. **Several arms of `judge` have no test** (`title_hygiene.py:43`, `117-133`). Untested: the `_LEAD_TIME` timestamp arm, the bare `is_timestamp` arm, over length, no alnum, junk title and the header-only `Set 2`/`CD 2` shapes. I probed them and all behave correctly today, but no test would catch a regression in, for example, the `_LEAD_TIME` regex. Fix: add one fixture per class, which also fixes item 1.
3. **`judge` re-composes `is_placeholder_text` instead of calling it** (`title_hygiene.py:97`, `117-120`). It tests `is_placeholder`, `is_timestamp` and `is_real_title and is_residue` separately so that it can give each arm a different scope. The brief mandates this split, so it is plan-mandated. The same drift hazard `hygienic_title`'s docstring warns about still applies: an arm added to `is_placeholder_text` would not reach `judge`. Fix (cheap): a pin test asserting that for a handful of inputs, `is_placeholder_text(t)` implies `not judge(...).ok`. The metadata clause is expressed the same way, twice (`judge:105` and inside `hygienic_title`), also plan-mandated (judge must split track from banner before the call). Leave it.
4. **An empty stem matches empty text** (`title_hygiene.py:122`). `text.lower() == stem.strip().lower()` is True when both are empty, so `judge(clean_one(""), stem="")` returns `filename residue` instead of `no alnum`. Both are show-level, so only the note's class name is wrong, and a real file always has a stem. Fix: require `stem.strip()` to be non-empty before comparing.
5. **For the operator and gate, not this task's code; recorded so it is not lost.** Under the spec's predicates as written:
   - A lone `01-?` passes check 1 when the list's leader vote does not strip `01-`. `clean_one("(05:12) 01-?").text == "01-?"`, and `judge` returns ok. The spec's rosehilldrive fixture reaches `?` only through the list-level vote.
   - The spec's literal `\bopened\b` rule declines `Opened Up` as a show-level annotation.

   Both follow the spec's own rules, and both are worth a row at the Checkpoint A yield gate.

### Assessment
**Task quality:** Approved
**Reasoning:** The code matches the brief's interfaces, decision order and "One definition" constraint. Existing `hygienic_title` callers behave identically, and no other protected name changed. The remaining issues are test coverage of the class names and arms, plus one empty-stem edge case. None of them makes this task's behaviour untrustworthy.
