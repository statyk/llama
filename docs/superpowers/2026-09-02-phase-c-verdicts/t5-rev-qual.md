# QUALITY: CHANGES REQUESTED

Task 5, code-quality review. Pointer guard `PTH-GUARD: OK`. All mutation work on
`/private/tmp/.../workc/t5-rev-qual`, shadowing proven by planted sentinel
(`SENTINEL: copy`, all three packages resolved to the copy), `__pycache__` purged
before and after every run, copy byte-identical to the worktree afterwards,
`git status --porcelain` on the worktree empty. No commits, no worktree edits.

The code itself is good: clean separation (all IO in gather, `siblings.py` stays
pure), no in-place mutation of `Track`s, deterministic sort key, notes routed the
same way jerrybase's soft closers already are, `is_real_title` import correctly
dropped, commit message states the test command (`Test: ./.venv/bin/pytest -q ->
1629 passed, 7 deselected.`) and the census before-counts, and `e34fda0` touches
exactly the five briefed files -- no scope creep.

Two of the three Important findings are ~5-line fixes. The third is a ~20-line
fixture I have already written and verified.

---

## Important

### I1. The `rate_alignment` band gate has ZERO content coverage -- the whole 1629-test suite stays green when it is deleted

`packages/llama/src/llama/stages/gather.py:190-192` (the
`return new_tracks, notes` closing the `if res.band != "auto":` block).

Mutation M3 -- delete that `return` alone, so a `declined` / `operator` /
`no-anchors` pair keeps its note and then falls through into `cplus_filter` and
adopts whatever survives:

```
1629 passed, 7 deselected, 26 warnings in 6.24s
```

Not one test notices. This is the guard the entire phase is built on -- the thing
that stops an unreviewed, sub-`AUTO` alignment from shipping titles silently.

**It is genuinely reachable, not vacuously redundant.** I built the missing
fixture and ran it both ways on the gd73 fixture: tracks 1, 2, 5 tagged and
agreeing with the donor, track 6 tagged "Bertha" and disagreeing, tracks 3-4
unresolved (an interior run bracketed by agreeing anchors and count-forced, so
C+ passes it). Agreement 3/4 = 75% -> `operator` band.

| | tracks 3-4 |
|---|---|
| unmutated | `unresolved` / `unresolved`, titles = filenames |
| M3 | `sibling-align` / `sibling-align`, "I Know You Rider" / "Dark Star" |

Both runs emit the identical note `sibling alignment needs operator review
(anchor agreement 75%)` -- so the *note* is pinned and the *behaviour* is not.
Two automatic titles ship from a 75%-agreement pair and nothing in the repo
objects.

**Why the two tests that name this guard don't catch it.** M2 (a narrower
mutation: treat `no-anchors` as `auto`) also leaves `test_stage_gather.py` 88/88
green. `test_wholly_untagged_tape_gets_zero_automatic_sibling_adoptions` and
`test_shifted_fully_tagged_sibling_does_not_transfer_positionally` both use a
tape with **zero** anchors -- and on a zero-anchor tape `cplus_filter` has no
brackets and declines every run regardless. So on those two fixtures the band
gate can never make a difference: both tests reach the right outcome through the
wrong mechanism, which is precisely the failure mode this phase's brief names
("a fixture passed its acceptance wording while reproducing the wrong
mechanism"). Their docstrings assert the mechanism explicitly ("`rate_alignment`
reports band == 'no-anchors' ... and gather must adopt nothing"), which makes
them read as binding when they are not.

**Change I would make:** add the operator-band fixture above to
`test_stage_gather.py` -- same `_gd73_donor` / `MultiIA` machinery already in the
file, ~20 lines -- asserting `[got[i].title_source for i in (3, 4)] ==
["unresolved"] * 2` **and** `[got[i].title for i in (3, 4)] == [got[i].filename
...]`. That single test converts M2, M3 and the below-FLOOR band arm from inert
to pinned. Optionally add its `declined`-band twin, but the operator one is the
dangerous band (it is the one whose rows survive C+).

### I2. `ia.metadata` in `_sibling_transfer` is unguarded and now kills the whole gather stage

`packages/llama/src/llama/stages/gather.py:157`.

Verified by probe: a sibling recording whose `metadata()` raises `IAError`
propagates straight out of `run_gather` and aborts the show.

```
packages/llama/src/llama/stages/gather.py:157: in _sibling_transfer
    kept, _, _ = filter_files(ia.metadata(rec.identifier).get("files", []), ...)
E   llama.ia_client.IAError: boom 503
```

The old `_sibling_titles` had the same unguarded call, so this is not a new
*class* of bug -- but its **reach** is what changed, and that is the whole point
of the loosened gate. Before: fired only when `canonical.confidence == "low" or
len(canonical.items) != len(kept)`. Now: fires on every show with
`title_fraction < 1.0`, which on the live library is the common case (75
unresolved + 21 legacy-sibling tracks across 89 shows).

`_collect_parses` forty lines below (gather.py:245-248) already establishes the
house convention for exactly this call, on exactly these identifiers:

```python
try:
    meta = ia.metadata(rec.identifier).get("metadata", {})
except IAError as err:
    notes.append(f"could not fetch sibling {rec.identifier}: {err}")
    continue
```

Worse, the two interact: `IAClient.metadata` is disk-cached, so a sibling that
`_collect_parses` already failed on (and softly noted) is guaranteed to be
re-attempted and to raise here. gather degrades gracefully at one call site and
hard-fails at the other, for the same fetch of the same object.

**Change I would make:** wrap gather.py:157 in the identical three-line
`try/except IAError` and append the same note, then `continue`. `gather` is the
most safety-sensitive stage in the project; one flaky sibling should not lose the
show.

### I3. `_donor_key` -- the function that decides whose titles ship -- is entirely untested (this is Q2)

`packages/llama/src/llama/stages/gather.py:110-118`.

Mutation M4 -- invert the whole ranking to prefer the *worst* donor
(`return (rank, -cost, identifier)`), full suite:

```
1629 passed, 7 deselected, 26 warnings in 6.38s
```

Nothing binds any of it: not the agreement-first ordering, not the cost
tie-break, not the identifier tie-break, and not the carefully-reasoned
`agreement is None -> -1.0` branch (which has a five-line docstring justifying a
distinction no test exercises). The implementer flagged this himself as concern
#3 and was right to. See the Q2 ruling below for the minimal fixture.

---

## Minor

### m1. `test_resolve_titles_no_longer_has_a_sibling_fallback` does not detect what it is named for

`packages/llama/tests/test_titles.py:50-62`. Mutation M1 -- restore the
`sibling_titles: list[str] | None = None` parameter **and** the
`elif sibling_titles and len(sibling_titles) == n:` rung to `resolve_titles`:
`test_titles.py` stays 57/57 green. The test never passes `sibling_titles`, so
re-adding it as a defaulted parameter is invisible. Its assertions
(`all(t.title_source == "unresolved")`, `tracks[0].title == "d1t01.mp3"`) are a
near-duplicate of `test_unresolved_flagged_not_guessed` three lines below.

The removal *is* pinned -- at the gather level, by
`test_shifted_fully_tagged_sibling_does_not_transfer_positionally`, which the
implementer showed red against the restored old rung. So the coverage is not
lost, only misplaced. **Change:** either assert the signature
(`"sibling_titles" not in inspect.signature(resolve_titles).parameters`) or drop
the test and let the gather-level pin carry it; a docstring claiming a removal
the assertions cannot see is the shape of pin this phase keeps shipping.

### m2. Docstring overstates the copy guarantee

`_sibling_transfer`'s docstring says "`tracks` is a NEW list (inputs are never
mutated in place)". The `if not candidates: return tracks, []` path returns the
**input object**. Harmless today (nothing downstream mutates), but the sentence
is the kind of invariant a later editor will rely on. Either
`return list(tracks), []` or soften the wording.

### m3. The new note strings enlarge a known unlabeled channel

`sibling alignment declined/needs operator review/skipped (...)` land in
`Show.structure.conflicts`, which per the project's own parked defect reaches the
briefing LLM unlabeled. Correct per the brief and consistent with jerrybase's
soft closers, so not this task's to fix -- but the population on that channel just
grew, and it is worth carrying to whoever owns that defect.

## Nit

### n1. The incomplete-durations donor skip is behaviourally redundant

`gather.py:164-165`'s `if any(d is None for d in durations): continue` produces
the identical outcome to letting `propose_rows` hit its own `_all_present` check
and return `(None, diag)` -- the loop `continue`s either way. So no mutation can
catch it. It is fine as a guard on `DonorTape`'s documented contract ("the caller
guarantees none missing") and the brief asked for it; noting only so nobody
mistakes it for a tested safety property.

---

## Test hygiene -- what edit makes each new test fail

| Test | Source edit that makes it fail | Status |
|---|---|---|
| `test_sibling_transfer_adopts_into_a_bracketed_gap` | drop the `row.verdict == "adopt"` application branch, or stamp `"sibling"` instead of `"sibling-align"` | binding |
| `test_fully_tagged_tape_does_not_fetch_a_sibling_for_title_transfer` | `fetch_siblings = bool(kept)` -- **verified**, fetch count 1 -> 2, 1 failed / 87 passed | binding (fetch-count assertion, not just output -- good) |
| `test_wholly_untagged_tape_gets_zero_automatic_sibling_adoptions` | none found. M2 and M3 both leave it green; only `cplus_filter` binds it, never the band gate its docstring names | **HOLLOW w.r.t. its stated mechanism** (I1) |
| `test_below_floor_sibling_alignment_declines_with_a_note` | change the note wording. Its *content* assertions survive M3 (the sole unresolved track is trailing-edge, so C+ declines it anyway) | note binding; band arm hollow (I1) |
| `test_a_bracketing_failure_leaves_the_run_unresolved_with_its_reason_in_notes` | bypass `cplus_filter` (implementer's mutation B, red on title content) | binding |
| `test_shifted_fully_tagged_sibling_does_not_transfer_positionally` | restore the old positional rung (implementer's backward mutation, red) | binding for the old rung; **hollow w.r.t. the band gate** it also claims (M2/M3 green) |
| `test_an_already_titled_track_is_never_overwritten_by_a_surviving_adopt_row` | remove the `title_source != "unresolved"` continue (implementer's concern-#1 mutation, red naming the exact wrong string) | binding -- the strongest test in the set |
| `test_sibling_aligned_matches_count_as_independent_coverage_evidence` | add `"sibling-align"` to `TAUTOLOGICAL_TITLE_SOURCES` (mutation A, red on `coverage == 5/6`) | binding |
| `test_resolve_titles_no_longer_has_a_sibling_fallback` | none for its stated purpose -- M1 leaves it green | **HOLLOW** (m1) |
| -- (missing) | `_donor_key` inverted -- M4, full suite green | **NO TEST** (I3) |

**Suite delta 1622 -> 1629 (+9 / -2), audited.** `test_sibling_titles_are_cleaned`
is cleanly subsumed: its happy path by `test_sibling_transfer_adopts_into_a_bracketed_gap`,
its id-prefix stripping by `test_prefixed_tag_titles_align` and titles.py's own
`clean_tag_titles` tests. `test_sibling_fallback_when_setlist_misaligned`'s
replacement is hollow (m1), but the behaviour it guarded is covered more strongly
one layer up. Net: nothing weakened by the removals; the weaknesses are in what
the *additions* fail to reach.

---

## DP fan-out at corpus scale -- ACCEPTABLE, no change needed

Measured on this machine, `propose_rows` per donor (confirms Task 4's numbers):

| target tracks | per-donor |
|---|---|
| 20 | 0.015 s |
| 40 | 0.067 s |
| 60 | 0.229 s |
| 90 | 0.784 s |
| 120 | 1.884 s |

Against the real distributions -- 37,144 cached candidates in `~/.llama/runs`:
recordings per performance **median 1, p90 9, max 38**; 89 gathered shows: track
count **median 22, p90 31, max 63**:

- typical show (1-3 donors x 22 tracks): **~0.02-0.06 s**
- p90 show (9 donors x 31 tracks): **~0.3 s**
- worst observed (38 donors x 63 tracks): **~9 s**, once, at gather time

That is comfortably inside a stage that already does per-recording network IO and
audio downloads. **Crucially, the loosened fetch gate adds essentially zero
network**: `IAClient.metadata` is disk-cached via `_cached`, and
`_collect_parses` has already fetched every sibling's metadata for the same show
before `_sibling_transfer` runs -- the "loosened fetch gate" is a cache-read gate,
not a network gate. (The one thing it *does* newly expose is I2.)

Optional, not required: skipping donors whose cleaned `titles` are all empty
would cut the fan-out on tag-poor performances for free -- such a donor can never
produce an `adopt` row and already ranks below every titled donor
(`_anchor_row` requires `row.proposed`, so it scores `agreement = None`). Only
behavioural change would be losing its `no-anchors` note. I would not block on
it.

---

## Q1 ruling -- four verified mutations RESEMBLE discharging red-first; they do not discharge it

**Not discharged. The breach stands.** And this review is the evidence, not an
appeal to the rule.

Red-first and mutation testing buy different things. Red-first forces you to name
what the code is *for* before the code exists, so the test is written against the
**requirement**. Mutation testing only proves the test is sensitive to some edit
in the code you **actually wrote**. When the two are collapsed, the tests end up
covering the implementation's own contours and silently miss any requirement the
implementation happens to satisfy through a second, incidental path.

That is exactly what happened here, and it is measurable. All four of the
implementer's mutations bind -- they are honest, correctly run, and correctly
reported. Every one of them targets a line he had just written. Meanwhile the
guard the *spec* is built on -- "a sub-`AUTO` pair must not adopt automatically" --
can be deleted wholesale with all 1629 tests green (I1), because no test was ever
written against that sentence as a requirement. The fixtures that claim to cover
it all satisfy it through `cplus_filter` instead. Four green mutations produced a
confident report and a hole in the phase's central safety property.

The stated reason for the deviation also does not survive scrutiny for the tests
that matter. The rationale is that DP outcomes were not hand-computable -- but the
band tests assert nothing numeric at all (`title_source == "unresolved"`,
`title == filename`); they were writable red-first without computing a single DP
cost. Exactly one assertion in nine tests (`coverage == 5 / 6`) actually needed
the DP to be run first. The right response to that one assertion was to write the
other eight red-first and leave that one number as a fill-in -- not to co-develop
the set.

Mitigation credit is real and should be recorded: the disclosure was
unprompted, specific, and is what told me where to look. But candour is not
equivalence. The remedy is the missing fixture in I1, not a process ruling -- and
I would not ask for the work to be redone red-first, only for that gap to be
closed before Task 6 builds the operator surface on top of this pass.

## Q2 ruling -- Important, and now proven, not merely suspected

The implementer flagged it as a "worth a dedicated test if a future task depends
on it" concern. It is stronger than that: M4 shows the **entire ranking function
can be inverted with the full suite green**, and this is the code path that
decides *whose titles ship* onto the show -- the highest-consequence uncovered
line in the diff. Task 6's operator surface will read the same winner.

**Minimal fixture** (~18 lines, all machinery already in the file): two donors
via `_gd73_donor`, both landing in the `auto` band, disagreeing on the interior
gap. Target as in the existing happy-path test (tracks 1 and 6 tagged, 2-5
unresolved). Donor `gd73-06-10.aud.a` = `REAL_TITLES` and agrees with both
anchors (agreement 1.0). Donor `gd73-06-10.aud.b` proposes the same anchors but
`"Truckin'"` / `"Ripple"` in the gap and carries one disagreeing anchor
(agreement 0.5 -- still would adopt alone if it won). Register both on the
candidate, and assert the adopted gap titles are **`donor a`'s**. That pins
agreement-first; a second assertion with the two donors given equal agreement and
different DP cost pins the cost tie-break, and giving them equal agreement *and*
equal cost pins the identifier tie-break -- but the first assertion alone is what
I would require.

---

## Verification commands run (log: `t5-rev-qual.log`)

All under `PYTHONPATH=<copy>/packages/{llama,herder,emcee}/src` with
`<worktree>/.venv/bin/python -m pytest`; never a `.venv/bin/*` console script.

- sentinel shadowing proof -- `SENTINEL: copy`, all three packages from the copy
- M1 restore `sibling_titles` param + rung -> `57 passed` (test_titles.py)
- M2 `no-anchors` treated as auto -> `88 passed` (test_stage_gather.py)
- M3 delete band early-return -> `1629 passed` (full suite)
- M3 + purpose-built operator-band fixture -> adopts 2 titles; unmutated -> 0
- M4 invert `_donor_key` -> `1629 passed` (full suite)
- M5 `fetch_siblings = bool(kept)` -> `1 failed, 87 passed` (gate binding)
- IAError probe -> `IAError` propagates out of `run_gather`
- fan-out timings + `~/.llama` candidate/track distributions
- copy restored byte-identical to worktree; worktree `git status` empty
