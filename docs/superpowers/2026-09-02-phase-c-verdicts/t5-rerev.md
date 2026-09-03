# Task 5 — fix round 1 scoped re-review

Scope: `16e3e73` only. `e2e9066` / `951cfdc` / `c0ce4b3` (docs) not reviewed.
Pointer guard: `PTH-GUARD: OK`. Method: isolated copy at
`scratchpad/workc/t5-rerev`, `PYTHONPATH` shadowing proven by planted sentinel
(`MODULE FILE:` resolved into the copy; worktree grep 0), `__pycache__` purged
before and after every run, copy diffed byte-identical to `16e3e73:gather.py`
after each restore. Worktree `git status` clean throughout. No commits.

## Verdicts

### I1 — band gate had zero content coverage — **ADDRESSED**

Applied the exact reviewer mutant (deleted `return new_tracks, notes` inside
`if res.band != "auto":`). `test_operator_band_run_stays_unresolved_even_though_cplus_would_bracket_it`
goes red on its verbatim line:

```
>       assert [got[i].title_source for i in (3, 4)] == ["unresolved"] * 2
E       AssertionError: assert ['sibling-ali...ibling-align'] == ['unresolved', 'unresolved']
E         At index 0 diff: 'sibling-align' != 'unresolved'
packages/llama/tests/test_stage_gather.py:361: AssertionError
```
1 failed, 193 passed. No other test moved — this test is the sole detector.

**Independent judgement: the fixture IS discriminating**, not merely passing.
I dumped the rows both ways rather than trusting the docstring:

| track | unmutated | mutated |
|---|---|---|
| 1 | tags 'Morning Dew' | tags 'Morning Dew' |
| 2 | tags 'China Cat Sunflower' | tags 'China Cat Sunflower' |
| 3 | **unresolved** 'gd73-06-10d1t03.mp3' | **sibling-align 'I Know You Rider'** |
| 4 | **unresolved** 'gd73-06-10d2t01.mp3' | **sibling-align 'Dark Star'** |
| 5 | tags 'Eyes of the World' | tags 'Eyes of the World' |
| 6 | tags 'Bertha' | tags 'Bertha' |

The interior run really does adopt the moment the gate is removed, so
`cplus_filter` passes it (properly bracketed by agreeing anchors 2 and 5, and
count-forced) and the row ratio admits it. **Every path other than the band
gate would have adopted** — this is the defect the two zero-anchor tests had,
and it is genuinely absent here. The band is confirmed `operator` (not
`declined` / `no-anchors`) by the passing note assertion: 4 anchors, 3
agreeing = 75%, strictly between FLOOR 0.50 and AUTO 0.80.

**Note identity confirmed:** conflicts are byte-identical in both runs —
`['sibling alignment needs operator review (anchor agreement 75%)']`. The
title_source of tracks 3-4 is the *only* difference between mutated and
unmutated, so the band gate is the sole accountant for it.

### I2 — unguarded `ia.metadata` — **ADDRESSED**

**Idiom comparison (side by side, same file):**

`_collect_parses` (pre-existing, line ~268):
```python
try:
    meta = ia.metadata(rec.identifier).get("metadata", {})
except IAError as err:
    notes.append(f"could not fetch sibling {rec.identifier}: {err}")
    continue
```
`_sibling_transfer` (the fix, line ~172):
```python
try:
    files = ia.metadata(rec.identifier).get("files", [])
except IAError as err:
    notes.append(f"could not fetch sibling {rec.identifier}: {err}")
    continue
```
Same call, same exception type, **byte-identical note string and f-string
interpolation**, same `continue`. The only difference is the sub-key each
caller needs (`"metadata"` vs `"files"`). This is one idiom, not a second one.

Mutant (guard removed) reddens `test_a_sibling_fetch_failure_is_noted_not_fatal`
with `llama.ia_client.IAError: boom 503` escaping `run_gather` — so the
propagation was real and the guard is load-bearing and tested.

**Other-donors-survive, verified independently** (the shipped test has only one
donor, so it does not cover this): two donors, the alphabetically-first one
raising `IAError`, the second good — the failure is noted and the good donor
still wins and adopts tracks 2-5 as `sibling-align` with the correct titles.
Behaviour is right; the *test* for it is a coverage gap, listed as deferred.

### I3 — `_donor_key` had zero coverage — **ADDRESSED**

Reviewer's mutant (`return (rank, -cost, identifier)`) reddens
`test_the_higher_agreement_donor_wins_not_the_alphabetically_first_one`:
`At index 0 diff: 'gd73-06-10d1t02.mp3' != 'China Cat Sunflower'` (1 failed,
193 passed).

Loser's identifier genuinely sorts first: `gd73-06-10.aud.a-loser` <
`gd73-06-10.aud.z-winner`, so the identifier tie-break cannot produce the right
answer by accident. I also ran the mutant the test's own *name* claims to guard
against — `return (identifier,)`, alphabetical-only — and it reddens the same
test on the same line. Two independent mutants, both killed.

Observation (not a defect): under both mutants the kill arrives via the *band
gate* (loser is operator-band, so tracks stay unresolved filenames) rather than
by shipping the loser's `"Wrong N"` strings, so the test's second assertion
(`not any(t.title.startswith("Wrong "))`) does not itself fire. The first
assertion kills, so the finding is closed.

### m1 — signature not pinned — **ADDRESSED**

Restoring `sibling_titles: dict[str, str] | None = None` as unused dead code
reddens `test_resolve_titles_no_longer_has_a_sibling_fallback` at
`test_titles.py:68` on the new
`assert "sibling_titles" not in inspect.signature(resolve_titles).parameters`.

### m2 — docstring/behaviour mismatch — **ADDRESSED**

`return list(tracks), notes` on the no-candidates path. Verified live:
`out is tracks -> False`, `out == tracks -> True`, `notes -> []`. Matches the
rewritten docstring's "always a NEW list ... on every return path including
'no candidate donor at all'".

## Suite delta — **CONFIRMED 1629 -> 1632, +3, nothing removed or weakened**

- `--collect-only` on the copy at `16e3e73`: **1632/1639 collected (7
  deselected)** — matches the claim exactly.
- `numstat`: `test_stage_gather.py` **112 added / 0 deleted** (purely
  additive); `test_titles.py` 13 added / 1 deleted, the single deletion being a
  docstring closing line replaced by the extended docstring.
- `+def test_` added: exactly the 3 named tests. `-def test_` removed: **none**.
- Every removed line in the whole fix diff, enumerated: 7 docstring lines
  (rewritten), 1 docstring line in `test_titles`, the unguarded
  `kept, _, _ = filter_files(ia.metadata(...)...)` (replaced by the guarded
  form), `return tracks, []` (replaced by `return list(tracks), notes`), and
  the `notes: list[str] = []` declaration (hoisted above the loop so
  fetch-failure notes survive the no-candidates return). **Zero test functions
  and zero assertions removed.**
- The two pre-existing hollow zero-anchor tests were left in place, not
  deleted — correct: the new test supplies the content coverage they lacked.

## Fan-out comment — **CONFIRMED**

Unit and population both named, per the standing rule: "0.015 / 0.067 / 0.23 /
1.88 **SECONDS** at 20 / 40 / 60 / 120 target tracks", "**per donor**",
"Against **37,144 real candidates** (`~/.llama/runs`)", "**89 gathered
shows**". Numbers match `progress.md:623`/`:643` exactly — donors median 1 /
p90 9 / max 38; tracks median 22 / p90 31 / max 63; ~0.3 s p90; ~9 s
worst-observed. The only wording drift is "typical ~0.02-0.06s" vs the
review's "~0.05 s typical" — a range containing the review's point estimate,
not a contradiction. The disk-cache / no-added-network claim is carried too.

## New breakage in the fix diff

**None found.** The hoisted `notes` list is correct and is what lets a
fetch-failure note survive the `if not candidates:` return.

## Deferred (out of scope, one line each)

- `_collect_parses` and `_sibling_transfer` both fetch the same identifier and
  emit the *same* note string, so a flaky sibling now lands in
  `structure.conflicts` **twice** (observed live) — cosmetic duplication, and a
  direct consequence of the reviewer-mandated idiom identity.
- `test_a_sibling_fetch_failure_is_noted_not_fatal` uses a single donor, so
  "one failure does not lose the other donors" is behaviourally correct but
  untested; I verified it by hand.
- I3's test kills via the band gate rather than via shipped loser titles, so
  its `not any(t.title.startswith("Wrong "))` assertion is currently inert.
- Pre-existing, already reviewer-deferred: incomplete-durations donor skip
  redundant with `propose_rows`' own check; `structure.conflicts` unlabeled
  channel now carries a few more note shapes.

## Overall verdict

**ALL FIVE FINDINGS ADDRESSED.** Every hollow-coverage fix kills its mutant —
I1 under the exact reviewer mutation with a fixture I independently confirmed
discriminating (the note is identical both ways; only the gated tracks move),
I3 under two independent mutants, I2 under guard removal, m1 under parameter
restoration. Suite delta is exactly +3 with nothing removed or weakened. No new
breakage in the fix diff. Clear to proceed.
