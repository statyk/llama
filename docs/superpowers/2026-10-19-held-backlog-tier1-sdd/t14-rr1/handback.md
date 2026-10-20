# t14-rr1 — Task 14 fix round 1 re-review (22f18d9..b9ae699)

### Finding Verdicts

1. **IMPORTANT: 3c negation windows crossed sentence/clause and briefing-field boundaries.** ADDRESSED.
   - `packages/llama/src/llama/stages/brief.py:67`: `_CLAUSE_BREAK = re.compile(r"[.!?;:,\n]")`.
   - `brief.py:128-132`: `_words_before` now tokenises only `_CLAUSE_BREAK.split(prose[:start])[-1]`. Only the two negation windows in `_qualified` (`brief.py:137,139`) call it.
   - `_SCOPE_AFTER` (`brief.py:142`) and the `_NOT_SHOW_WIDE` group-2 check are unchanged.
   - `brief.py:181`: `_guard_prose` joins fields with `"\n"` (field boundary). The vague branch (`brief.py:204-207`) still uses `_SET_COUNT_CLAIM`/`_ORDINAL_SET` `finditer`, and its code is untouched.
   - All 4 probes are tested and expect the claim KEPT:
     - three rows in `packages/llama/tests/test_stage_brief.py:341-344`;
     - the field-boundary probe in `test_3c_negation_does_not_cross_a_briefing_field_boundary` (`test_stage_brief.py:361`), which also asserts the guard verdict.
   - Same-clause negation rows (no / not / instead of / expected / without) still expect suppression in the same parametrize table.
   - Check I ran, a read-only sweep of `~/.llama/shows/*/briefing.json`:
     - 2,455 briefings and 2,446 today-regex matches. Old space-join and new newline-join match sets differ in **0** cases (same span, same words), which confirms the implementer's figure. This holds by construction too: `\s`/`\b` treat `\n` like a space, and the length is the same.
     - Suppressed matches on full-narration briefings with a show.json: **24** before the fix, **21** after.
     - The 3 recovered are all real cross-sentence claims, now correctly KEPT: `deadandcompany-2021-09-18` "...earlier than expected. The second set included...", and `gratefuldead-1990-03-24` twice ("...without a venue. The second set...", "...on Without a Net. | The second set as documented...").

2. **MINOR: compare's root fallback `or "."` must be a no-op when neither arm has a root.** ADDRESSED.
   - `scripts/replay_holds.py:663-664` passes `None` when neither arm has a root.
   - `replay_holds.py:285,295-296`: `_suppressed_claims(None)` reads nothing and reports 0.
   - Pinned by `scripts/test_replay_holds.py:707` (`test_suppressed_claims_without_a_root_in_either_arm_reads_nothing`). It uses a library-shaped tree in a chdir'd cwd that is not read, both directly and through `main(["compare", ...])`.

3. **MINOR: the vague-branch test must assert that "there is no second set" still counts under vague narration.** ADDRESSED.
   - `test_stage_brief.py:357-358` asserts exactly `["briefing asserts set structure under vague narration"]`.
   - The report records mutant r1d (vague ordinals routed through 3c), caught by that test.

### Comma deviation (`[.!?;:,\n]` vs the ruled `[.!?;:]`)

**Verdict: needed, and the cost is acceptable.**
- **Needed:** under the ruled set, the orchestrator's own probe "As expected, the second set was a monster." stays SUPPRESSED (I measured this: "ruled" variant → suppressed). The ruling's probe can only be KEPT if the comma clips the window.
- **Probes** (pre-fix / ruled / implemented):

  | probe | pre-fix | ruled | implemented |
  |---|---|---|---|
  | "no encore, no second set" | suppressed | suppressed | suppressed |
  | "There was no encore, no second set." | suppressed | suppressed | suppressed |
  | "no second set, no encore" | suppressed | suppressed | suppressed |
  | "not, as some claim, two sets" | KEPT | KEPT | KEPT |
  | "They played not three, but two sets" | KEPT | KEPT | KEPT |
  | "never, in their history, a second set" | KEPT | KEPT | KEPT |
  | "without a break, two sets" | suppressed | suppressed | KEPT |
  | "instead of the usual, two sets" | suppressed | suppressed | KEPT |
  | "expected, as always, two sets" | suppressed | suppressed | KEPT |
  | "without, oddly, a second set" | suppressed | suppressed | KEPT |

  - The first three keep the same-clause negation suppressed, because the negator repeats after the comma.
  - "not, as some claim, two sets" was never suppressed: "not" is beyond the 2-word window, so the comma costs nothing there. The same goes for the next two rows.
  - Only the last four rows are lost by the comma. They are comma-split constructions with the negator only before the comma, and some read as non-claims ("without a break, two sets" is arguably a real claim anyway).
- **Measured cost on stored data:** across all 2,455 stored briefings, the ruled and implemented variants suppress exactly the same matches (21; 0 differ either way). So the comma's cost is synthetic only.
- **Direction:** clipping can only remove suppressions, so any loss means more holds, never a silent pass. That is the conservative direction for this guard.
- **Doc gap (Minor, non-blocking):** neither the spec's negation sentence nor the `brief.py:61-66` comment lists the cost cases. Worth a line for the Checkpoint D reader.

### New Breakage in the Fix Diff

None at Critical or Important.
- `_guard_prose`'s newline join changes no `_SET_COUNT_CLAIM`/`_ORDINAL_SET` match (measured 0/2,455 differ; same length, `\s` spans `\n`).
- The only other reader of `_guard_prose`, `replay_holds._suppressed_claims`, gets the same prose as the guard.
- `.` in the break set also clips at abbreviations and decimals ("St. Louis", "2.5"). That too can only remove suppressions, so it is acceptable.

### Out-of-Scope Observations

- `_SCOPE_AFTER` (unchanged by ruling) still crosses a briefing-field boundary when a field lacks terminal punctuation: `_claim_counts("they played two sets\nA night to remember") == (set(), {})`, versus `({2}, {})` with a period.
  - This is the forward-looking twin of the fixed defect. It needs `^\s*` to skip a field-ending `\n` straight into `a/each/every/per night|day|weekend|tour`.
  - It is non-blocking and was ruled out of scope. It is worth a ledger line for the final review, or a one-character fix (`^[^\S\n]*`) if the orchestrator wants symmetry.
- My stored-library count of 3c suppressions is 21 (24 before the fix). The spec's prototype figure was ~68, and the spec says the specified rule is re-counted. Checkpoint D should expect a number near 21, not 68.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.

Checks run:
- A read-only probe script, `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-held-backlog-tier1/927bc958-2722-4419-85dd-93da116478c9/scratchpad/rr1_probe.py`, run with the worktree venv (llama resolved inside the worktree). It covered the comma probes and the stored-briefing sweep over `~/.llama` (read-only). Output is in `t14-rr1.log`.
- A two-line `_claim_counts` check for the scope-after observation.
- No suite re-run. The implementer's report names the covering tests with output: 194 passed for the 3 files, full suite 3621 passed, and r1a-r1e mutants all caught as predicted.
