# t11-rev: Task 11 (2c glued track-number prefix) review, e5e4411..127dd45

### Spec Compliance

- ✅ Spec compliant. `_GLUED_NUM_PREFIX = re.compile(r"^\d{2}(?=[A-Z][a-z])")` is exactly as the brief says (titles.py:186). The second vote runs over the same `voters` with the unchanged `_ENUMERATED_MIN_*` constants (titles.py:222-224). The gather note matches Contracts 2c verbatim (gather.py:1108-1109). The note is gated on `tag_source == "tags"` as the brief says, and M9 (overridden positions get no note) is applied (gather.py:1103-1107). The fixture, the brief's three titles tests, the brief's gather test and the extra both-paths tests are all present.
- Do-not-retune grep of the diff: `_TRACK_NUM_PREFIX`, `_ENUMERATED_MIN_FILES`/`_ENUMERATED_MIN_COVERAGE`, `is_real_title`, `title_fraction` and `clean_tag_title` all appear only as context lines. None of them changed. The only removed lines are the old early return and the old final `return`. Ruling 2 holds: this is a new predicate beside `_TRACK_NUM_PREFIX`, which is not loosened. Ruling 6 holds: notes go only to `op_notes` (gather.py:1108).
- ⚠️ Spec acceptance says "Every stripped title is listed". `sibling_format_titles` calls `clean_tag_titles` (titles.py:255), so the glued strip also fires silently on format-recovered titles, and the plan's `tags`-only gate gives those no note. The controller should confirm that Checkpoint B's harness diff of shipped fields (not only the `stripped glued track number:` grep) is accepted as the listing for that path. The spec's survey puts the population at 0 (4 RRE shows, all `tags`; the fixture test sees 23 notes on `tags`).

### Named-risk checks

1. **Fall-through is byte-identical whenever the glued vote fails: PROVEN.**
   - By reading: on the spaced-fails path `titles` is untouched and returned. On the spaced-passes path the same list comprehension is assigned and returned. Either way it is the old output.
   - By a differential check: the old `clean_tag_titles` from `git show e5e4411` against the new one, over 200,000 random inputs. The pool includes `100 Years`, `1952 Vincent Black Lightning`, `2001`, `01 200 More Miles`, `3AM`, `M80`, `7-Up`, `01ABBA`, `52Nd Street` and `10Th Avenue`, and 30% of the cases carry a random `gate_basis`. All 199,609 cases where the glued vote failed matched exactly: 0 mismatches. The script is `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-held-backlog-tier1/d4918098-e484-43e4-8857-2fae7853ad18/scratchpad/diff_check.py` and its output is in t11-rev.log.
   - The `100 Years` accepted gap, `1952 …` and `2001` cannot match the glued regex: the third character is a digit or a space, never `[A-Z][a-z]`.
2. **Double strip: structurally impossible.**
   - No string matches both regexes. The spaced regex needs `\s+` after the digits and an optional `[.)\-:]`; the glued regex needs an uppercase letter directly after exactly two digits. So `numbered + glued <= len(voters)`, and both reaching ≥ 0.8·len (with each ≥ 3) is impossible. At most one strip fires per call.
   - The differential run confirms it: the "both votes pass" count is 0.
3. **Gather note condition and raw layer: correct.**
   - `tags`-only is what the brief specifies. Under recovery `tag_titles` come from the FLAC sibling, so comparing them to the mp3's `clean_tag_title` would be spurious. See the ⚠️ above for the acceptance consequence.
   - `raw = clean_tag_title(f.get("title"))` over `kept` is exactly the per-file layer `clean_tag_titles(kept, …)` starts from, so raw is the pre-strip text the strip acted on.
   - A title changed by the SPACED strip cannot be mis-noted as glued: its raw matches the spaced regex, so it cannot match `_GLUED_NUM_PREFIX` (risk 2's disjointness).
   - `is_real_title` gives the same answer before and after the strip for `01Pig In A Pen`/`Pig In A Pen`, `05Star` and `52Nd Street`. So the strip does not shift the format-recovery gating that `title_fraction` feeds (checked in diff_check.py).
4. **Is the both-paths structure pinned? Yes, where it matters.** Mutants run in scratch copies, with the copy's `llama.__file__` proven to resolve inside the copy and a private PYTHONPYCACHEPREFIX each time:
   - **Mutant A (early return restored, glued strip reachable only when the spaced vote passes).** Predicted red: `test_glued_strip_applies_when_the_spaced_vote_fails`. CAUGHT by it, plus `test_clean_tag_titles_strips_a_glued_prefix_when_the_recording_votes_for_it`, `test_glued_strip_never_reaches_uppercase_or_digit_second_characters` and `test_stage_gather.py::test_2c_strips_railroad_earths_glued_numbers_and_notes_each`.
   - **Mutant B2 (spaced-pass path returns immediately, glued strip only on the fails path).** Predicted: SURVIVES as an equivalent mutant. It SURVIVED (220 passed). It is equivalent by risk 2's proof: the glued vote can never pass when the spaced vote has.
   - So the "runs on both paths" ruling only has an effect on the fails path, and that path is pinned.
   - (An earlier botched B variant that made the spaced strip unconditional is discarded; it is in the log only.)

### Strengths

- The restructure is minimal and readable. The comment block on the inert `count=1` is preserved verbatim under the inverted condition.
- The near-miss test was made load-bearing as ruled: with 8 glued of 10 voters the vote passes, so `3AM` and `01ABBA` stay intact only because of the lookahead, and the implementer's lookahead mutant confirms it.
- The gather test pins the exact count (23 notes) as well as the brief's single note, so a lost note or a duplicated one goes red.
- Ruling M9 is applied consistently with 2b's override exemption.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
- **titles.py:219-221 and test_titles.py (`test_glued_strip_runs_beside_a_passing_spaced_vote`): misleading comments.**
  - The code comment "It runs on both paths (the spaced vote passing or failing)", and the test comment "glued vote also passes on the same voters only if glued >= 80%", both suggest the glued vote could pass when the spaced vote has. It cannot: the two shapes are disjoint and both floors are 0.8.
  - Suggest one line in the code instead: "the two shapes are disjoint and both need 80% of voters, so at most one strip fires."
  - That test is still a useful regression pin (the pass path stays unaffected), but its comment should say the glued vote cannot pass there.
- **gather.py:26: the reformatted `from llama.titles import (...)` line is 145 characters.** It is the only line in gather.py over 110. Re-wrap it.
- **Import of a private name: gather.py:25 imports `_GLUED_NUM_PREFIX`.** The brief's interface implies this, and the implementer flagged it. A public alias or a small `titles.glued_prefix(raw) -> bool` helper would be tidier. Not blocking.
- **Plan-mandated scope note: no glued-strip note under `sibling-format`.** See the ⚠️ above. Population 0 per the spec survey. Surface it at Checkpoint B instead of changing code now.
- **Accepted-gap analogue for the record.** On a tape that passes the glued vote, an UNPREFIXED real title in `str.title()` casing such as `52Nd Street` or `10Th Avenue` would be stripped to `Nd Street`. This is the same class as the ruled `100 Years` gap; it is not pinned by a test, and no instance is known. Optional: a test documenting it as accepted, as `100 Years` has.

### Assessment

**Task quality:** Approved

**Reasoning:** The implementation matches the brief exactly. The fall-through is proven byte-identical whenever the glued vote fails (by reading and by a 200k-case differential check), and a double strip is impossible by construction. The only both-paths mutant that survives is a proven equivalent. The remaining items are comment accuracy, line length and a plan-mandated acceptance nuance for Checkpoint B.
