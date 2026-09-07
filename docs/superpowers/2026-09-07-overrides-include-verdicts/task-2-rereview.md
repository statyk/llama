Finding 1 (Important): ADDRESSED
Finding 2 (Important): ADDRESSED
Finding 3 (Minor): ADDRESSED
Finding 4 (Minor): ADDRESSED
New breakage in the fix diff: none
VERDICT: all findings addressed

Scoped re-review of `10d3202..2b6ccef` on branch `overrides-include` (main
checkout). Read-only except for four temporary in-place mutations, each
restored from a backup; `git status --porcelain` is empty at the end of this
review and `git diff --stat` is empty.

## Finding 1 (Important) — mutation-blind `test_gather_leaves_ordinary_tracks_unmarked` — ADDRESSED

`packages/llama/tests/test_stage_gather.py:2088-2104`. The test now writes
`Overrides(include=["FOLLOW-ME @BYPIKENO.mp3"])`, so the guarded stamp block at
`gather.py:1152-1155` genuinely executes, and asserts `included is False` on
every track OTHER than the re-admitted one, with an `assert others` non-vacuity
guard on the sample.

Verified by mutation, not by reading:

- **Mutant A** — `gather.py:1155` `t.included = t.filename in forced` →
  `t.included = True` (over-marking, inside the same guard).
  `./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py -q -k unmarked`
  → `1 failed` on `test_gather_leaves_ordinary_tracks_unmarked`. This is the
  exact mutant the finding said the old test survived; it is now caught.
- **Mutant B** — deleted the whole `if overrides.include:` block
  (`gather.py:1152-1155`).
  `-k "unmarked or readmit"` → `1 failed, 2 passed`: the deletion is caught by
  `test_gather_readmits_an_operator_included_file:2079`, which asserts the
  positive stamp. So the stamp is pinned in both directions across the pair —
  over-marking by the rebuilt test, absence by its sibling.
- Both mutants restored; baseline `-k "readmit or unmarked or both_override or
  include_entry or lossless_orphan or recovers_titles_from_the_lossless"` →
  `6 passed, 92 deselected`.

## Finding 2 (Important) — recording-level side effect undocumented and unpinned — ADDRESSED

**(b) The test is a real pin, not a vacuous negative.**
`test_readmitting_a_lossless_orphan_suppresses_sibling_format_recovery`
(`test_stage_gather.py:901-923`). Its assertion is negative
(`all(t.title_source != "sibling-format")`), so I did not take the implementer's
control claim on trust — I mutated the mechanism itself:

- **Mutant C** — `gather.py:880` changed to compute recovery on a
  PRE-re-admission `kept`:
  `_recover_format_titles(md.get("files", []), [f for f in kept if f["name"] not in set(overrides.include)], ordering)`.
  `-k "lossless_orphan or recovers_titles_from_the_lossless"` →
  `1 failed, 1 passed`: the new test FAILS (recovery now fires for the six
  ordinary tracks) while the control
  `test_gather_recovers_titles_from_the_lossless_sibling:779` still PASSES.

That is the decisive evidence: the negative assertion flips precisely on the
hazard it names, so it cannot be passing because recovery failed for some
unrelated reason. The control is a genuine A/B partner — both tests build the
same `md` from `_with_tagged_lossless(json.loads(FIXTURE.read_text()))`, the
same `make_candidate()`/`IDENT`/`StubIA`, and differ ONLY by the
`write_artifact(sws.overrides, Overrides(include=[...]))` line. The helper's own
non-vacuity is separately guarded by
`test_the_tagged_lossless_helper_is_not_vacuous:771` (`len(kept) == 6`).

**(a) Both directions in the extended comment are true of the code as written.**
Comment at `gather.py:846-865`.

- OFF direction — trivially true from `titles.sibling_format_titles:223`
  (`if not kept or len(kept) != len(other_kept): return None`) plus the stem-set
  equality at `:227`. A re-admitted file with no lossless counterpart raises
  `len(kept)` and the bijection declines for the whole tape.
- ON direction — I did not take this on the comment's word either, because
  `_recover_format_titles:340` filters the lossless side with a plain
  `filter_files(files, want_format=fmt)` (no `readmit`), so passing the
  `title_fraction < 0.5` gate at `:335` is necessary but not sufficient: the
  bijection must still hold. I ran a read-only pure-function probe against the
  real `filter_files` / `_recover_format_titles` with a synthetic 7-track item
  whose 7th mp3 derivative is truncated (`00:30`) beside a full-length tagged
  `.shn`. Result: without `readmit`, 6 kept mp3s, 3 tagged → fraction 0.5, gate
  returns `None` (no recovery). With `readmit={"...t07.mp3"}`, 7 kept, 3 tagged
  → 0.43 < 0.5, the 7↔7 bijection holds, and recovery fires with titles for ALL
  SEVEN tracks. So the ON direction is genuinely reachable, not hypothetical.

**Durable-record quality.** A reader six months out can tell the pinned
behaviour from an accident: the comment names WHICH heuristics flip
(`_recover_format_titles`' mp3-side `title_fraction` gate and
`sibling_format_titles`' exact-count bijection) and names the test; the test's
docstring names the counts at which it flips (6 kept mp3s bijecting 6 Shorten
entries → 7 vs 6 on re-admission) and states that the loss hits all seven
tracks, not just the re-admitted one. Spec section 2 (`:111-112`) sanctions the
behaviour, so the code correctly stands.

## Finding 3 (Minor) — `Track.included` comment — ADDRESSED

`packages/llama/src/llama/models.py:167-170`. Now reads "True when the operator
named this file in `overrides.include` -- not necessarily that the junk filter
would otherwise have dropped it; the stamp is `filename in overrides.include`,
and `filter_files`' return shape does not expose which re-admitted names were
actually junk." That matches `gather.py:1155` exactly, and matches spec section
1 (`:56-59`). Code correctly unchanged. The `ManifestTrack`-exclusion rationale
in the second half of the comment is preserved.

## Finding 4 (Minor) — no warning on the both-lists case — ADDRESSED

`gather.py:869-871`:
`for both in sorted(set(overrides.include) & drop): log.warning("overrides: %r is in both include and exclude; exclude wins", both)`.
Placement inside the `overrides.exclude` block is correct — the include block's
own `matched no file` loop (`:843-844`) is computed against a `kept` that by
then already contains the re-admitted file and structurally cannot see the
ambiguity.

Pinned by `test_exclude_wins_when_a_file_is_in_both_override_lists:2107-2126`,
which now takes `caplog` and asserts a record containing both the filename and
`"exclude wins"`. Verified by mutation, not by reading:

- **Mutant D** — deleted the three-line warning loop. `-k both_override` →
  `1 failed`. Restored; test green again.

The assertion uses `r.message` (already %-substituted by caplog's handler on
capture), consistent with the correction documented for the sibling warning
test — so it is not the `r.message % r.args` TypeError trap.

## New breakage in the fix diff

None. The fix touches three files and nothing else:
`models.py` (comment only, no field/validator change), `gather.py` (a comment
block plus the three-line warning loop — no change to control flow, ordering, or
any value), and `test_stage_gather.py` (one new test, two extended). The new
warning loop is inside the existing `if overrides.exclude:` guard, iterates a
set intersection, and cannot raise. No import was added.

Constraints re-verified directly:
- `junk.py:66,69,70` — `SHORT_FRACTION_OF_MEDIAN = 0.25`,
  `MIN_MEDIAN_SAMPLE = 5`, `MIN_PLAUSIBLE_SEC = 90.0`. Unchanged; `junk.py` is
  not in the diff.
- `ManifestTrack` gains no field; `Overrides` carries no `extra="forbid"`
  (grepped both).
- The `overrides.exclude` block still runs after re-admission
  (`gather.py:866-878`, below the `filter_files(..., readmit=...)` call at
  `:839-841`), so a both-lists file still ends up excluded — asserted by the
  test above.
- `Track.included` is still stamped immediately before `show = Show(`
  (`gather.py:1152-1157`).
- No test reaches the network: all the touched tests use `StubIA`/`FakeProvider`
  and `tmp_path`.

Confirming run after restoring every mutation:
`./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py packages/llama/tests/test_junk.py packages/llama/tests/test_models.py -q`
→ `142 passed in 0.40s`. I did not re-run the full suite; the implementer's
`1935 passed, 7 deselected` claim is consistent with the +1 net new test in this
round.

## Out-of-Scope Observations (deferrable minors, non-blocking)

1. The finding named four recording-level heuristics; the extended comment
   names two (`_recover_format_titles`' fraction gate and
   `sibling_format_titles`' bijection). `clean_tag_titles`' enumeration gate is
   arguably covered implicitly — it is invoked inside the fraction gate at
   `gather.py:335` — but `fetch_siblings` (`gather.py:921`,
   `bool(kept and title_fraction(clean_tag_titles(kept)) < 1.0)`) is a third,
   separate recording-level gate that a re-admitted untagged file can flip from
   False to True, and it is not mentioned anywhere. It sits ~55 lines below the
   comment and outside this fix diff, so it does not block; a one-line
   cross-reference there would complete the record.
2. `test_gather_leaves_ordinary_tracks_unmarked`'s name is now slightly narrower
   than what it does (it also exercises the stamp block). Cosmetic.
