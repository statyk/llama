### Spec Compliance
- ✅ Spec compliant. The rule matches the ruling exactly and nothing else in it moved.
  - `lossless_titles.py:248` is `if sum(1 for i in delivered_shift if i in changed) >= 2:`. The signature computation (`:245-247`), the demotion set (`:249-251`) and the note are byte-identical to before.
  - The new condition implies the old `len(delivered_shift) >= 2`. Because the signature requires `_real(dt)`, a signature position can only enter `changed` through C2. So "confirmed by C with a lossless tag" means "a C2 at a signature position", which is what the comment at `:235-243` describes.
  - The note loop in `gather.py:1297` now skips `i in c_changed or i in c_demoted`. `c_demoted` (`:1273`) is read from `lossless` after the override restore (`_without_override_positions` wraps `apply_lossless`, `:1265-1269`), so an override position is never skipped wrongly. That position is also guarded separately by `(i + 1) not in overrides.titles`.
  - Protected names: the diff touches none. `_GLUED_NUM_PREFIX`/`_JOINED_NUM_PREFIX` appear only as unchanged context. `titles.py`, `structure.py`, `siblings.py` and `setlist.py` are untouched.
- ⚠️ Cannot verify from the diff:
  - (a) The commit body. The diff file's commit header shows only the subject and the trailers, with no test command or result line, which the brief's step 5 and mandate 4 require. Either the body is missing, or the diff view did not include it. I did not re-run git, per the rubric.
  - (b) The 4-show replay ran on `sha b653592…-dirty`, i.e. the uncommitted fix, before the commit, not on 3751735 itself. That is consistent with the workflow, but the arm is not bound to the committed sha.

### Strengths
- **The repro test really exercises `compute_gather`** (`test_title_cascade.py`, `test_shifted_reference_with_right_tags_demotes_nothing_c1_narrowing`). It builds demo_gather.py's synthetic show and asserts the strongest form:
  - the shipped titles equal all 8 right MP3 tags, which excludes every shifted title (`Mama Tried`, and Deal/Loser/… on the wrong tracks);
  - no `setlist-gap` source;
  - `lossless.demoted == ()`;
  - no demotion note.

  The docstring states which outcome is pinned.
- **The boundary unit tests are minimal and correct** (`test_lossless_titles.py`):
  - one-confirmed: signature {2,3}, changed {2}, so nothing is demoted;
  - two-confirmed: signature {2,3}, changed {2,3}, so track 4 is demoted.

  The one-confirmed case keeps `len(delivered_shift) == 2`, so it separates the new rule from the old one.
- **Mutants:** I ran 5 in a scratch `git archive HEAD` copy, all predicted before running.
  - The scratch tree is `scratchpad/c1nrev`. `llama.__file__` was proven under the scratch every run, with `PYTHONPATH` shadowing, `PYTHONDONTWRITEBYTECODE=1`, `__pycache__` purged, and `-p no:cacheprovider`. Baseline: 80 passed.
  - Log: `c1n-rev.log`.

  | Mutant | Prediction | Result |
  |---|---|---|
  | M1, the old `len(delivered_shift) >= 2` | killed | **Killed**: one-confirmed and the gather repro fail. This confirms both are RED on the old rule. |
  | M2, `>= 1` | killed | **Killed**: `test_one_shifted_delivered_tag_changes_nothing` and one-confirmed fail. |
  | M3, `>= 3` | killed | **Killed**: 3 existing exactly-2 tests, two-confirmed, and the note-loop test (which needs an exactly-2 demotion) fail. |
  | M5, drop `or i in c_demoted` | killed | **Killed**: the note-loop test fails. |
  | M4 | survives | Survives (see Minor 1). |
- **The DSO-2014 pins are unchanged and still pin the outcome.**
  - The unit test pins `changed` (17 C2 at 4-20 + C1 at 21), `demoted == (2,)`, track 3 blank, and the note.
  - The gather test pins #3 not `Duprees Diamond Blues`, an unresolved/desc-position/setlist source, the 4-20 C2 titles, and the note.
  - The replay fresh view shows DSO `newly-held` with flag `unresolved track titles` and `c_demoted [3]`.
- **The note-loop test is real.**
  - It has glued-number MP3 tags, C2 at tracks 2-3, and track 4 (`04Big River`) demoted.
  - It asserts that glued notes exist for the shipped tracks and that none names track 4.
- **The replay evidence is real and covers both views.**
  - `~/.llama-harness/piece3/c1n/{asis,fresh}.json` exist (scope `slugs`, the 4 slugs). They carry the same `config_fingerprint` as r2 and `disabled_slices []`.
  - The override flags match the r2 arms: asis has nothing stripped; fresh has both title and structure overrides stripped.
  - I diffed every row key (titles, title_sources, notes, cascade, gather_flags, outcome, …) against `accept/r2/arms/cand-{asis,fresh}.json`: there are zero differing keys for all 8 rows.
    - asis: DSO `clean`, lettuce `clean`, both tedeschi `clean-changed`, all `c_demoted []`.
    - fresh: DSO `newly-held` with `c_demoted [3]`; the other three `clean-changed`, `c_demoted []`.
  - This matches the handback.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **`test_lossless_titles.py`, the new boundary tests: "at signature positions" is not pinned against "any C change".**
   - Mutant M4, `if len(delivered_shift) >= 2 and len(changed) >= 2:`, survives the whole relevant set (80 passed). No test has 2 or more C changes while fewer than 2 of them sit on signature positions. DSO doesn't separate the two either, because all of its changes are signature positions.
   - Why it matters: the ruling specifically says signature positions. A refactor to "C confirmed ≥2 things" would reopen the false signature on a show whose C2 changes sit elsewhere, and nothing would catch it.
   - Fix: add a unit case with signature {2,3}, only track 2 C2-confirmed, plus a C2 change at a non-signature position, and assert no demotion.
2. **`test_title_cascade.py:519` (pre-existing, not changed here): the DSO gather pin's "held" is a disjunction.** It asserts `needs_review or review_flags or not shipped_unconfirmed`, so "held" itself is pinned only by the replay evidence. The brief allowed this, and fixwave-rr accepted it; it is noted only because this review was asked to confirm "held".
3. **The commit body may lack the test command and result line** (see ⚠️ a). If it does, it can't be fixed without an amend; record the command in the SDD ledger instead.
4. **The handback reports 26 warnings in the full suite with no attribution** (`4787 passed, 1 skipped, 8 deselected, 26 warnings`). It does not say whether they are pre-existing. The 80-test focused run in the scratch copy showed no warnings.

### Assessment
**Task quality:** Approved
**Reasoning:** The C-1 condition is exactly the ruling (sum over C-confirmed signature positions ≥ 2) and nothing else in the rule moved. The repro, boundary and note-loop tests are real and kill the `>=1`, `>=3`, old-rule and no-skip mutants. The 4-show replay is unchanged in both views. The only gap is coverage: a surviving "count any C change" mutant (Minor 1).
