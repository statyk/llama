# SPEC ✅ — Task 4 (the guards), spec-compliance review

`PTH-GUARD: OK`. Worktree untouched, `git status` clean, no commits.
Mutations run on `.../workc/t4-rev-spec` (a `git archive` of `8c78eb3`), shadowing proven
with a planted sentinel (`SENTINEL: copy`, `shadowed: True`), `__pycache__` purged before
and after every run, driven only by `$WORKTREE/.venv/bin/python -m pytest` + `PYTHONPATH`.

## Brief requirements, one line each

| requirement | verdict |
|---|---|
| `loosely_same_title` in `structure.py` beside `fuzzy_title_eq`: norm-equality / containment either way / ratio >= 0.80 | ✅ verbatim (`structure.py:200`) |
| its docstring: guard + measurement scorers ONLY, never `align()`/`normalize_song`, changing it re-runs Task 7 | ✅ all three sentences present |
| `Disagreement`, `GuardResult`, `rate_alignment`, `cplus_filter` signatures | ✅ match the brief exactly |
| Anchor = independent evidence (`tags`/`sibling-format`/`override`) with a real title, paired by the DP | ✅ `INDEPENDENT_TITLE_SOURCES`, `_anchor_row` |
| bands `auto`/`operator`/`declined`/`no-anchors` | ✅ (see adjudication) |
| C+ by reuse: `unresolved_runs` + real `gap_span(anchors, lo, hi, len(tracks))` | ✅ real calls, proven load-bearing by mutation A |
| count-forcing `span[1]-span[0] == hi-lo+1` | ✅ |
| runs decline individually, reason per run, exact reason strings from the brief | ✅ both brief strings reproduced verbatim |
| both spec invariants land as comments AND tests | ✅ quoted verbatim in `cplus_filter`'s docstring; tests `test_cplus_applied_to_the_display_would_blind_the_operator`, count-forcing comment block |
| comparator tests: equality, containment, ratio case, BIODTL known limit, Rain-go-away near-miss as comment not fix | ✅ all present, both misses pinned as tests |
| band routing tests: 9/13 -> operator, 2/13 -> declined, 1 anchor -> operator, no tags -> no-anchors | ✅ all four |
| leading-edge adopts / tail never auto-adopts / bracketed interior adopts | ✅ all three, tail via absent `hi+1` |
| per-run independence asserted on both title strings AND both reasons | ✅ `test_runs_decline_individually_...` |
| localised-shift fixture: `rate_alignment` -> `auto`, `cplus_filter` adopts zero interior | ✅ built through the REAL `propose_rows` from durations, not hand-assembled |
| suite 1590 -> 1617, none removed | ✅ +27 `def test_` added, **0 removed**; the only deletions in the whole 2-commit package are the two `siblings.py` import lines it replaced |
| scope creep | ✅ none — `structure.py` touched for the comparator only (`SequenceMatcher` import + `LOOSE_TITLE_RATIO` + `loosely_same_title`) |

## Mutation evidence (all three applied by me, on the copy)

### A — `gap_span` call replaced with one-sided bracketing
Command: replaced `span = gap_span(anchors, lo, hi, len(tracks))` with an inline
`left`/`right` lookup accepting when `left is not None or right is not None`, taking the
run's own file count on the open side. **4 failed, 181 passed.**

- `test_a_tail_run_never_adopts_automatically` — `E AssertionError: assert 'Charlie' not in dict_values(['Alpha', 'Bravo', 'Charlie', 'Delta'])` (`test_siblings.py:585`)
- `test_the_localised_shift_adopts_zero_interior_titles_under_cplus` — `E AssertionError: assert 'Hotel' not in dict_values(['Alpha', 'Bravo', 'Charlie', 'Delta', 'Echo', 'Foxtrot', 'Golf', 'Hotel', 'India', 'Juliett', 'Mike', 'November'])` (`test_siblings.py:745`)
- bonus: `test_runs_decline_individually_one_unbracketed_run_does_not_sink_the_pair` — `E AssertionError: ... Left contains 2 more items: {6: 'Foxtrot', 7: 'Golf'}` (`:618`)
- bonus: `test_a_disagreeing_anchor_does_not_bracket_even_though_it_is_titled` — `E AssertionError: assert 'Bravo' not in dict_values(['Alpha', 'Bravo', 'Charlie'])` (`:651`)

Both brief-named tests die. The `gap_span` reuse is load-bearing, not decorative.

### B — count-forcing clause deleted
**2 failed, 183 passed.**

- `test_a_run_whose_donor_span_holds_more_tracks_than_files_declines` — `E AssertionError: assert {1: 'Alpha', ...: 'Echo', ...} == {1: 'Alpha', 5: 'Foxtrot'}` / `Left contains 3 more items: {2: 'Bravo', 3: 'Charlie > Delta', 4: 'Echo'}`
- `test_the_localised_shift_adopts_zero_interior_titles_under_cplus` — `E AssertionError: assert 'Kilo > Xray' not in dict_values([... 'Juliett', 'Kilo > Xray', 'Mike', 'November'])`

Both brief-named tests die, and the fixture **does** reproduce the sweep's finding: track 11
is bracketed by two agreeing anchors and count-forcing alone stops it shipping `"Kilo > Xray"`
onto a one-song file. Mutations A and B each name a *different* wrong title, so the split
assertion in `8c78eb3` earns its place.

### C — `MIN_ANCHORS = 1`
**2 failed, 183 passed.**

- `test_a_single_agreeing_anchor_routes_to_the_operator_not_auto` — `E AssertionError: assert 'auto' == 'operator'`
- bonus: `test_a_setlist_gap_title_is_not_an_anchor` — `E AssertionError: assert 'auto' == 'operator'` (proves that test is a real band assertion, not a count assertion)

**No mutation broke nothing.** No finding against the tests on this axis.

## Both-direction spot checks (I ran six, independently of the report)

| bound | direction | result | dying test / line |
|---|---|---|---|
| `MIN_ANCHORS` 2 | ↑ 3 | 2 failed | `test_two_agreeing_anchors_are_enough_for_the_automatic_band`, `test_an_override_title_anchors_the_guard_like_a_tag` — `assert 'operator' == 'auto'` |
| `AUTO` 0.80 | **↓ 0.65** | 2 failed | `test_agreement_below_auto_but_above_floor_routes_to_the_operator` — `assert 'auto' == 'operator'`; `test_the_localised_shift_passes_the_ratio_band_the_ratio_is_blind` — `assert 0.8 == 0.65` |
| `FLOOR` 0.50 | **↓ 0.10** | 1 failed | `test_agreement_below_floor_is_declined_outright` — `assert 'operator' == 'declined'` |
| `FLOOR` 0.50 | ↑ 0.75 | 1 failed | `test_agreement_below_auto_but_above_floor_routes_to_the_operator` — `assert 'declined' == 'operator'` |
| `AUTO` 0.80 | ↑ 0.85 | 1 failed | `test_the_localised_shift_passes_the_ratio_band_the_ratio_is_blind` — `assert 0.8 == 0.85` (the same test's `assert res.band == "auto"` also inverts, so the pin is behavioural, not a value pin) |
| `MIN_ANCHORS` 2 | ↓ 1 | mutation C above | |

Every result reproduces the implementer's table exactly. **No bound is inert in either
direction, and every death is a band/title assertion rather than a bare value pin.**
(`LOOSE_TITLE_RATIO` I did not re-mutate; the two known-limit tests pin it at 0.833 above
and 0.774 below by construction, which is a genuine two-sided pin.)

## The four spec invariants

**1. C+ gates the automatic band, never the proposal display — YES.**
Repo-wide grep: the only non-test occurrences of `cplus_filter` are its definition in
`siblings.py` and a mention in `structure.loosely_same_title`'s docstring. Nothing in
`cli.py`, `correspondence.py` or `stages/` calls it. The spec's own sentence ("A wholly
untagged tape has no anchors and therefore no brackets; applied to the renderer, C+ would
show ymsb2005 *nothing* — the phase's trigger case destroyed by its own guard…") is quoted
**verbatim** in the docstring at the definition, and pinned behaviourally by
`test_cplus_applied_to_the_display_would_blind_the_operator`, which asserts the untagged
tape adopts `{}` *while every row still carries its proposed title* for the renderer.

**2. Per-item, not per-donor — YES.**
`cplus_filter` loops `for lo, hi in unresolved_runs(tracks)` and `continue`s on a passing
run; the decline is recorded per run in `demoted[pos+1]` with a per-run reason string.
`test_runs_decline_individually_one_unbracketed_run_does_not_sink_the_pair` asserts on
both title strings (`{1: "Alpha", 2: "Bravo", 3: "Charlie", 4: "Delta", 5: "Echo",
8: "Hotel"}`) and both reasons (`"tracks 6-7: not bracketed by agreeing anchors"` x2), and
mutation A shows the pair-level outcome is genuinely reachable, not vacuous.

**3. Reuse, no second anchor definition — YES, and I attacked this one directly.**
I read the call, not the comment. `cplus_filter` calls the real
`structure.unresolved_runs(tracks)` and the real
`structure.gap_span(anchors, lo, hi, len(tracks))`. There is **no** re-statement of the
leading-edge exception and **no** trailing branch anywhere in `siblings.py` — I grepped the
whole file for `lo == 0`, `hi + 1` and `left`/`right` and the only occurrences are inside
`structure.gap_span` itself. Mutation A is the proof: re-implementing the composition
one level up (exactly the Task-3 failure mode) turns four tests red immediately, including
the leading-edge and tail cases. `anchor_spans` is deliberately *not* called and the
docstring states why (it binds tracks to canonical setlist *items* by title matching;
here the binding is the DP's duration pairing). Only its half-open span **shape** is
reused, which is what lets `gap_span` take `donor_span`s unconverted. That is a correct
reading of the primitive, not an evasion.

**4. `sibling-align` not added to `TAUTOLOGICAL_TITLE_SOURCES` — YES.**
The constant is untouched (`frozenset({"setlist-gap", "setlist"})`); the string
`TAUTOLOGICAL` does not appear in the diff at all. `INDEPENDENT_TITLE_SOURCES` is a
separate frozenset for *anchoring* and makes no claim about alignment evidence. Nothing in
Task 4 presumes Task 5's change.

## Constants

`AUTO = 0.80`, `FLOOR = 0.50`, `MIN_ANCHORS = 2` sit under a shared DO-NOT-RETUNE banner
citing `docs/superpowers/2026-09-02-sibling-transfer-evidence.md`, each with its own
measured rationale. `LOOSE_TITLE_RATIO = 0.80` carries its DO-NOT-RETUNE and the same
citation in the immediately-following docstring, plus the sharp note that it is not
`AUTO`'s 0.80 (independent bounds sharing a value) — a good catch on the implementer's part.

## Band-ambiguity adjudication

**The implementer is right. `operator` is correct, and the anchor-count clause takes
PRECEDENCE — it is not a tie between two equal clauses.**

First, a correction to the framing I was given (the orchestrator has since corrected it
itself, and I reached the same arithmetic independently): "agreement 0.3 with 1 anchor" is
impossible — with one anchor the ratio is 0.0 or 1.0. The real overlap is exactly one case:
**one anchor that disagrees**, ratio 0.0, which satisfies both `< 0.50` and `< 2 anchors`.

**The spec answers it once, and unambiguously.** Only the *plan* is ambiguous. The spec
says: "**MIN_ANCHORS = 2** for the automatic band (bands measured over >= 2 anchors;
**under it, operator path regardless of agreement**)." "Regardless of agreement" is a
precedence statement, not a tiebreak. The implementer's ordering — anchor count checked
before the ratio — is the literal spec.

**And it is right on the merits, three ways.** (a) The `declined` band's justification is a
*measurement* ("below 0.30 the marginal error is 68–99%") taken over pairs with >= 2
anchors; over one anchor that statistic does not exist, so it cannot license discarding.
(b) 24.1% of disagreeing anchors are tape-wrong, so a lone disagreement is roughly
one-in-four odds that the *anchor* is the wrong thing — near-zero evidence either way.
(c) Invariant 1's logic points the same direction: neither band adopts anything
automatically, so the only cost of `operator` over `declined` is a minute of operator
attention, while the cost of `declined` over `operator` is silently discarding a possibly
correct alignment for a barely-tagged tape — which is the exact population this phase
exists to serve. `declined` is the destructive error here; `operator` is the conservative one.

**Suggested plan wording** (the plan file is the thing to fix, not the code) — state the
bands as an ordered evaluation rather than a set of predicates:

> Bands, evaluated **in this order**: `no-anchors` when there are 0 anchors; `operator`
> when anchors < `MIN_ANCHORS`, *regardless of agreement* (the ratio is not a measured
> statistic below 2 anchors, so it may neither license adoption nor justify discarding);
> then `auto` when agreement >= `AUTO`; `operator` when agreement >= `FLOOR`; else
> `declined`.

**The 0-anchor case is handled explicitly, not by accident.** `rate_alignment` returns
`GuardResult(None, 0, [], "no-anchors")` **before** the division, so there is no
`ZeroDivisionError` and no coercion to 0.0 that would land the phase's central case in
`declined`. `GuardResult`'s docstring states the distinction in terms ("`agreement is None`
means wholly untagged — distinct from 0.0, which means it has anchors and they all
disagree"), and `test_a_wholly_untagged_tape_has_no_anchors_and_no_agreement` pins
`agreement is None` alongside the band. This is explicit and correct; no finding.

## Findings

**Minor 1 — the "agreeing anchor" predicate is composed twice.**
`rate_alignment:420` and `cplus_filter:490` each write
`_anchor_row(track, row) and loosely_same_title(track.title, row.proposed)` inline rather
than sharing one `_agreeing(track, row)` helper. Both compose the same two single-sourced
primitives, so nothing is duplicated *logically* today — but this is the same shape as the
Task-3 drift (primitives imported, composition restated one level up), and a future change
to what "agreement" means in layer 1 would not propagate to layer 2. One three-line helper
closes it. Not blocking.

**Minor 2 — the evidence-doc citation is a forward reference with a guessed date.**
All four constants cite `docs/superpowers/2026-09-02-sibling-transfer-evidence.md`, which
does not exist; the plan's file table names it `docs/superpowers/2026-09-XX-sibling-transfer-evidence.md`,
created by Task 7. The citation is *required* by the plan, so this is correct as written —
but Task 7 must create the doc at exactly that path, or four do-not-retune comments dangle.
Flagging so it lands on Task 7's checklist.

**Minor 3 — an anchor requires the row to carry a proposal (implementer's Concern 4), which
is a defensible narrowing of the spec's literal wording.**
The spec's denominator is "target tracks carrying a surviving real tag **that the alignment
paired**"; `_anchor_row` additionally requires `bool(row.proposed)`, so a tagged track
paired with an *untitled* donor is neither an agreeing nor a disagreeing anchor. I agree
with the choice — counting it as a disagreement would let an untitled donor drag a correct
alignment below `FLOOR`, which is a failure mode with no upside — and it is pinned by
`test_an_unpaired_tagged_track_is_not_an_anchor`. But it is a real deviation from the
literal text, and **Task 7's measurement scorer must adopt the same rule** or its
agreement numbers will not reconcile with the shipped guard. Task 7 blocker, not a Task 4 one.

**Note (no finding) — implementer Concerns 1, 2 and 3 are correctly scoped to Task 5.**
C+ says nothing about a track that already has a title (Concern 1) is right for a per-run
filter and is pinned with the consequence spelled out in the test docstring; Task 5 must
intersect adopt rows with the unresolved set. Concern 2 (run reasons reconstructible only
from rows) and Concern 3 (C+ does not itself check the band) are both genuine Task 5
interface questions, correctly raised rather than solved here.

## Verdict

**SPEC ✅.** Every brief requirement met, all four spec invariants hold under direct
inspection of the calls, all three named mutations kill their named tests with a second
bonus kill each, all six both-direction constant mutations kill a behavioural test, and the
one genuine spec ambiguity was resolved the way the spec's own words and the measurement
both require. Three Minor findings, none blocking.
