# Review: `overrides-include` recording-level title gates (`f31cf50..bf343c8`)

Branch `overrides-include`, commits `e473431` (code + tests) and `bf343c8` (spec correction 5).
Baseline reproduced: **1967 passed, 7 deselected**. Tree restored clean after every mutant
(`git status --porcelain` empty).

## Verdicts

- **Spec compliance: PASS with one required doc correction** (Important #2 below) and one
  unresolved scope gap (Important #1).
- **Code quality: PASS with two Important findings and four Minors.** No Critical findings
  at either verdict — stated explicitly, not padded.

---

## Q1. Are the two bases correct, and is the pre/post-exclusion split right?

**Yes, both bases are right at their own call site.**

- `recovery_basis` (gather.py:867) is computed *above* the `overrides.exclude` block
  (gather.py:870-881), so it equals "the set the junk filter kept, with neither operator
  list applied". That is exactly what the pre-existing guard comment above it demands
  (the recovery map must not be decided by a dropped file), now extended symmetrically to
  re-admitted ones. Verified by reading the ordering: `kept` is rebound at line 881, after
  line 867.
- `tag_gate_basis` (gather.py:936) is computed after that rebind, so it votes over the
  tracks that actually ship. That is correct for the enumeration gate, whose whole job is
  "does this *recording* look enumerated" where "recording" means the delivered track list.
- Reusing one for both is genuinely wrong and the comment's account of why is accurate.
  I reproduced it: mutating `tag_gate_basis = recovery_basis` fails
  `test_readmission_does_not_stop_the_track_number_strip` (3 numbered of 6 pre-exclusion
  = 0.50 coverage, under the 0.80 floor).

**Empty-basis behaviour is safe** (checked, not just assumed). If every kept file is a
re-admission, `tag_gate_basis == []` → `numbered = 0 < _ENUMERATED_MIN_FILES` short-circuits
before `_ENUMERATED_MIN_COVERAGE * len(voters)`, so no `ZeroDivisionError` and no strip —
conservative. `recovery_basis == []` → `title_fraction([]) == 0.0 < 0.5`, then
`sibling_format_titles([], other)` returns `None` on its `if not kept` guard. Both degrade
to "do nothing", which is the right direction.

---

## Q2. Missed recording-level consumers

The decisive fact for three of the four sites you listed: **`readmit=` is passed at exactly
one call site in the whole tree** — `gather.py:841`. Every other `filter_files(...)` call
omits it, so `overrides.include` is structurally invisible to them.

| site | whole-recording decision a re-admit can flip? | leaving it defensible? |
|---|---|---|
| `gather.py:204` (`load_donor_tapes`, `titles=clean_tag_titles(kept)`) | **No.** `kept` here is a *different* recording (a donor sibling), from `filter_files(files, want_format=want)` with no `readmit`. | Yes, trivially — the override never reaches it. |
| `select_recording.py:69` | **No**, same reason: `filter_files` at line 62 takes no `readmit`. | Yes — and for a stronger reason than the one you gave (see below). |
| `correspondence.py:310` | **No**, same reason (`filter_files` at line 305, no `readmit`), and it iterates *other* recordings, skipping `identifier`. | Yes. |
| `gather.py:927` (`fetch_siblings`) | **Yes** — reads post-re-admission, post-exclusion `kept`. | **Yes, and your justification understates the case.** |

**`select_recording` runs before overrides exist — REFUTED as stated, conclusion upheld.**
`SHOW_STAGE_ORDER` is `["select", "gather", …]` and `select` is a valid `redo --from`
target, so `llama redo <show> --from select` re-runs `run_select_recording` on a show whose
`overrides.json` already exists. The claim is only true of the first pass. The load-bearing
reason it is nonetheless safe is that `run_select_recording` never reads `overrides.json`
and never passes `readmit=`. Two independent reasons it *should* stay that way: its
`title_fraction` is scoring the raw archive.org item's tagging quality (a property of the
item, not of the operator's wishes), and its `completeness` term is `kept_tracks / max_kept`
— feeding a re-admission in would circularly bias selection toward the already-chosen
recording. **Recommend correcting the "runs before overrides exist" reasoning in whatever
record it lives in**; it will not survive the next reader who tries `redo --from select`.

**`fetch_siblings` correctly left alone — your claim holds, with a stronger argument
available.** The gate fires when `title_fraction(clean_tag_titles(kept)) < 1.0`. The only
state a re-admission can flip is `1.0 → <1.0`. But when the fraction *was* 1.0, every track
resolved from tags, so there are no `unresolved` tracks — and `_sibling_transfer`'s adoption
is intersected with the unresolved set at application time. Therefore the *only* track the
newly-triggered fetch can possibly write a title onto is the re-admitted file itself. The
gate cannot change any other track's provenance even in principle, which is a firmer
guarantee than "the tape genuinely is no longer fully tagged". Worth putting in the comment.

### The consumer you missed: `build_canonical`'s `target_count=len(kept)`

`gather.py:912` passes post-re-admission `kept` into `build_canonical`, which uses
`len(kept)` as `rank_parses`' `target_count` (`gather.py:791` and again at `:803` for the
setlist.fm blend). `rank_parses` ranks on `plausible = len(items) >= min(target_count,
max(5, target_count // 2))` and tie-breaks on `-abs(len(p.parsed.items) - target_count)`
(`structure.py:373-379`). **One re-admitted file shifts `target_count` by 1 and can flip
which description becomes the canonical setlist for the entire show** — changing set labels,
segues, and every setlist-derived title on the tape. Demonstrated directly:

```
two parses, 23 items and 24 items, both confidence=high
target 23 -> winner A (the 23-item parse)
target 24 -> winner B (the 24-item parse)
```

Two candidate recordings whose descriptions parse to counts straddling the tape size is an
ordinary configuration on a multi-recording performance, so this is reachable, not exotic.

Also `resolve_titles`' whole-tape setlist rung (`len(setlist.items) == n`, titles.py:288) is
sensitive to the same ±1, though it is measured dead in production (0 of 2,015 tracks).

I am **not** claiming this site must change — a plausible reading is that after a
re-admission the tape really does have one more track, so the canonical setlist *should*
be sized to it, exactly the `fetch_siblings` argument. What is wrong is the **generality of
the claim now in the code and the spec**: gather.py:861-862 says "recording-level decisions
vote on the tape minus re-admissions", and correction 5 says "each recording-level gate
votes on its own tape minus `overrides.include`". Of the five recording-level consumers of
`kept` in gather, **two** follow that rule and three (`fetch_siblings`, `target_count`, the
whole-tape setlist rung) do not. Only `fetch_siblings` is carved out. The next reader will
take the universal at face value. **(Important #1.)**

---

## Q3. Mutation sensitivity — re-run independently

Ran **all four** of your mutants, each with `PYTHONPYCACHEPREFIX=$(mktemp -d)`, tree
committed beforehand and restored with `git checkout --` after each. Every result is a fresh
full-suite run.

| # | mutant | result | red test |
|---|---|---|---|
| 1 | `_recover_format_titles(..., recovery_basis, ...)` → `kept` | **CAUGHT** 1 failed / 1966 passed | `test_readmitting_a_lossless_orphan_does_not_suppress_recovery` |
| 2 | `gate_basis=tag_gate_basis` → `gate_basis=None` at the call site | **CAUGHT** 1 failed / 1966 passed | `test_readmission_does_not_stop_the_track_number_strip` |
| 3 | `clean_tag_titles` ignores `gate_basis` (`voters = titles`) | **CAUGHT** 2 failed / 1965 passed | `test_clean_tag_titles_gate_basis_scopes_the_enumeration_vote` **and** the gather test |
| 4 | `tag_gate_basis = recovery_basis` | **CAUGHT** 1 failed / 1966 passed | `test_readmission_does_not_stop_the_track_number_strip` |

All four caught, each by the named predicted test, with no incidental collateral failures
apart from mutant 3's expected second red. **Your mutation claim is confirmed.**

I also verified the gather test is not vacuous: on the unmodified `gd73_metadata.json` the
recovery_basis title_fraction is 5/6 ≈ 0.83, above `_RECOVER_BELOW` (0.5), so
`format_titles` is `None` and `resolve_titles` genuinely takes the `clean_tag_titles`
branch where `gate_basis` is read. Had recovery fired, the test would have proved nothing.

**One test is near-vacuous** — `test_clean_tag_titles_gate_basis_defaults_to_the_files_themselves`.
I ran a fifth mutant, `voters = ([] if gate_basis is None else …)`, the only mutant that test
is shaped to catch:

```
7 failed: strips_numbers_on_an_enumerated_tape, leaves_a_four_digit_year_alone_even_when_enumerated,
leaves_an_unnumbered_year_title_alone, strips_once_never_loops,
strips_a_real_numeric_title_on_an_enumerated_tape, sibling_format_titles_cleans_recovered_titles,
gate_basis_defaults_to_the_files_themselves
```

It is red alongside six **pre-existing** tests, so it pins nothing the suite did not already
pin. Worse, its assertion shape is call-vs-call equality
(`clean_tag_titles(tape) == clean_tag_titles(tape, gate_basis=tape)`), which passes whenever
both sides are wrong the same way — e.g. bumping `_ENUMERATED_MIN_FILES` to 4 leaves both
unstripped and equal. **(Minor #1.)** Assert the concrete list
(`["Song 1", "Song 2", "Song 3"]`) instead; then it pins a value rather than a symmetry.

---

## Q4. Is the inverted test honest?

**Yes.** `test_readmitting_a_lossless_orphan_does_not_suppress_recovery`:

- The **name** changed from `…_suppresses_sibling_format_recovery` to `…_does_not_suppress_recovery`,
  so a grep for the old behaviour does not silently land on a test asserting the new one.
- The docstring's first sentence is explicit and unhedged: *"This test previously pinned the
  OPPOSITE behaviour and is deliberately inverted; its old body is the measurement that
  justified the change."* That is the disclosure a reversed pin owes its reader, stated
  first rather than buried.
- The mechanism it describes (7-vs-6 bijection on FOLLOW-ME's missing Shorten counterpart)
  matches the code and matches mutant 1's observed failure.
- The assertions got **stronger**, not weaker: the old test asserted only
  `all(title_source != "sibling-format")`; the new one asserts the exact count (`== 6`, with
  the list in the failure message) **and** that the orphan is not among them. The second
  clause is what pins "no free title", so the docstring's final sentence is backed by an
  assertion rather than being narration.

No dishonesty found at any level here.

---

## Q5. Does correction 5 match the code?

Mostly yes. Accurate and verified: the two-basis split; `recovery_basis` being pre-exclusion
and matching the existing guard; `tag_gate_basis` being post-exclusion; the claim that
reusing one basis let operator-excluded files vote (I reproduced it as mutant 4); the
`fetch_siblings` carve-out; and the 7-vs-6 / 0.43-against-0.50 measurements, both of which
are consistent with the fixture.

**The one sentence that does not match the code:**

> "A re-admitted file still RECEIVES a recovered title when the map covers it; it simply
> gets no vote in whether recovery happens."

**The map can never cover a re-admitted file.** `sibling_format_titles(kept, other)` builds
its return dict from `ours.values()`, where `ours` is derived from its `kept` argument — and
gather now passes `recovery_basis`, from which re-admitted names are removed by construction
(titles.py:243, gather.py:868). So for the sibling-format path the conditional is not merely
unlikely, it is unsatisfiable: `resolve_titles` looks the orphan up with
`format_titles.get(f["name"], "")`, gets `""`, and drops it through to setlist/unresolved.
Your own inverted test asserts exactly this (`"FOLLOW-ME @BYPIKENO.mp3" not in recovered`),
and its docstring says it plainly — *"it gets no vote, and no free title."* The spec and the
gather comment (line 862-863) say the opposite of the test.

The sentence is presumably meant to cover the *other* gate, where it is true: the leading
track-number strip decided by `tag_gate_basis` is applied to **every** file in `kept_files`,
re-admitted ones included, which `clean_tag_titles`' docstring states correctly. **The
sentence needs splitting** — the recovery gate gives the re-admitted file neither a vote nor
a title; the enumeration gate gives it no vote but does apply the result to it.
**(Important #2 — spec-compliance; the same wording is duplicated at gather.py:862-863 and
should be fixed in both places.)**

---

## Findings by severity

### Critical
**None.**

### Important

1. **The "recording-level decisions vote on the tape minus re-admissions" invariant is
   over-stated in both the code comment and correction 5.** Five recording-level consumers
   of `kept` exist in `run_gather`; two obey the rule, three do not, and only one of those
   three is carved out. The unlisted one — `build_canonical`'s `target_count=len(kept)`
   (gather.py:912 → :791/:803 → `structure.rank_parses`) — has the *largest* blast radius of
   any of them: a ±1 shift can change which description becomes the canonical setlist, and
   therefore every track's set, segue and setlist-derived title. Demonstrated reachable
   above. Either carve it out explicitly the way `fetch_siblings` was, or qualify the
   invariant to "the two title-provenance gates". Silence is the bad option.

2. **Correction 5's "still RECEIVES a recovered title when the map covers it" is
   unsatisfiable for the recovery path** and is contradicted by the very test the same
   commit introduced. Duplicated verbatim at `gather.py:862-863`. Split the claim per gate.

### Minor

1. **`test_clean_tag_titles_gate_basis_defaults_to_the_files_themselves` pins nothing
   uniquely** (measured: its only mutant reds six pre-existing tests too) and its
   call-vs-call equality shape survives any mutant that breaks both sides identically.
   Assert the literal expected list.

2. **`llama fix <show> --include <a-file-that-was-never-dropped>` is now a behaviour change,
   not a no-op — silently.** `_resolve_include_tokens` (cli.py:1259-1275) passes a non-`xN`
   token straight through with no check that it names an excluded row, so such a name lands
   in `overrides.include`. `junk.filter_files`'s `readmit` block only pulls names out of
   `excluded` (junk.py:252-253), so nothing is actually re-admitted — but both new bases
   filter on `f["name"] not in set(overrides.include)`, so that already-kept file loses its
   vote in the enumeration gate **and** is dropped from the recovery bijection, which can
   take a 6-vs-6 bijection to 5-vs-6 and turn recovery off for the whole tape. That is
   precisely the class of bug this change exists to prevent, re-entered through the front
   door. gather's "matched no file" warning (gather.py:842) cannot fire here, because the
   name *is* in `kept`. **Concrete fix, cheap:** `junk.filter_files` already computes the
   exact set at `junk.py:255` (`readmitted = {f["name"] for f in back}`) and throws it away
   next to the `ordering` dict it returns. Stash it as `ordering["readmitted"]` and have
   both bases filter on that instead of on `overrides.include`. The bases then mean "minus
   what was actually re-admitted", which is what the comments already claim they mean.

3. **`set(overrides.include)` is rebuilt on every iteration** of both list comprehensions
   (gather.py:867, :936) — the `if` clause of a comprehension is evaluated per element. Hoist
   it to a local; it is also the natural place to put the fix from Minor #2.

4. **API inconsistency:** `clean_tag_titles`' `gate_basis` is keyword-only (`*,`), but
   `resolve_titles`' new `gate_basis` is positional-or-keyword and sits after
   `format_titles`. The only production caller passes it by keyword. Make it keyword-only
   for symmetry and to keep the positional signature stable.

Non-findings, checked and clear: no whole-output negative assertion in any new test can
match `tmp_path` (the new negatives are membership tests over filename *lists*, not over CLI
output text); `by_name` in the inverted test is built for a single `in` check and could be a
list comprehension, which is too trivial to log as a finding.
