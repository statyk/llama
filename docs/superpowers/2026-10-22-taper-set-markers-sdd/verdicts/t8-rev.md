# t8-rev: Task 8 review (mutation run + R14 killing tests), a892b7a..6bddf0d

**Status: DONE_WITH_CONCERNS.** I made no commits and changed nothing in the repo. Every mutant ran in my own scratch copy.

### Spec Compliance

- ❌ **Issues found, all in Measurement 6's "forms' word boundaries" item.** Everything the brief and R14 listed was done correctly: (a)–(p), (q)–(x), (y1)–(y3), and the five Step A tests. But three boundaries that Measurement 6 asks to be pinned have no test, and mutation.md says the opposite (details under Important 1 and 2):
  - **o2** (`taper.py:166`) and **o3** (`taper.py:167`) SURVIVE. These mutants drop the `(?!\w)` after the ordinal set tokens. I measured both boundaries as load-bearing.
  - (o)'s **header-side effect** has no test either.
- ⚠️ **Cannot verify from the diff:** the full suite count (4434 passed, 1 skipped). The implementer's log shows it. As instructed, I did not re-run the suite in the worktree.

### Checks run (my own scratch copy)

**Instrument.** All runs were set up like this:
- The copy is `git archive 6bddf0d` into `scratchpad/t8-rev/base`, with a fresh copytree per mutant.
- Tests ran from an empty scratch cwd as `<wt>/.venv/bin/python -m pytest -p no:cacheprovider`, on the same 6 test files t8-impl used (760 tests).
- `PYTHONPATH` shadowed the copy, with a fresh `PYTHONPYCACHEPREFIX` per mutant and a 600 s timeout.
- Before each run I asserted that `llama.taper`, `llama.stages.gather`, `llama.replay` and `herder` resolve inside that mutant's copy.
- Each mutant's old text had to occur exactly once, and the diff had to be exactly one `-` line and one `+` line.

**Predictions came first.** I wrote them to `$D/t8-rev/t8-rev.log` before the run, which started at 13:52:45.

| run | result | matches my prediction? |
|---|---|---|
| S0 | 0 / 760 red | yes |
| SENT (raise in `demote_jerrybase_flags`) | 15 red, all in `test_stage_gather.py`, including all 6 new helper and M5 tests | yes; proves the copy is what runs |
| t (M5) | exactly `test_set_count_note_excludes_the_taper_encore` | yes |
| u (M6, my own form: the fuzzy result AND raw `==`) | exactly the 3 fuzzy params | yes |
| u2 (extra: casefold equality instead of fuzzy) | `[Me & My Uncle]` and `[Mississippi Half Step]` red, `[charlie brown]` green | yes; each param pins its own dimension |
| q | exactly the same 21 tests as t8-impl | yes |
| s | exactly the 4 con't params | yes |
| i (my form: `and bool(gathered.needs_llm)`) | the same 5 tests as t8-impl | yes |
| a | `test_non_filler_between_is_unplaced`, plus `test_every_boundary_must_place` and `test_real_case_declines` | yes; reproduces t8-impl's undeclared extras |
| o | exactly `test_set_like_negatives[Set In Stone]`; `test_set_intro_is_not_set_one_and_set_iv_voids` green | yes |
| **o2** (drop `(?!\w)` after `(?P<ord>first\|second\|third)\s+set`) | **0 red** | yes; I predicted it would survive |
| **o3** (drop `(?!\w)` after `(?P<ordn>1st\|2nd\|3rd)\s+set`) | **0 red** | yes; I predicted it would survive |
| o4 (drop `(?!\w)` after `_E_HEADER`'s `(?:enc\|e\d?)`) | 0 red | yes; I judge this boundary redundant, because the tail needs `:`, a dash followed by a space, or the line end |

**Predictions precede results (check 2).**
- `mutants.json` has mtime 13:28:08. It was never modified afterwards.
- The log's PREDICT block is stamped 13:31:18. The sentinels finished at 13:31:10, and the first mutant ran after that.
- The Step A pre-check of t–x ran at 13:28:13, which is also after `mutants.json` was written.
- All 30 entries in `results.jsonl` are one-line, single-hunk diffs, and their imports resolve inside `/m/<id>/`.
- Every file:line in mutation.md matches HEAD. I spot-checked `gather.py` 105/115/121/124/1397/1400/1405, `taper.py` 562/684/715/774 and `replay.py` 331.

**The missing test name (check 4).** `test_unrecognised_forms_are_not_markers` exists nowhere under `packages/` or `scripts/`; grep finds nothing. The substitutes do pin what Measurement 6 means by "unrecognised forms are not markers":
- (l): `test_title_lookalikes_are_not_markers[E.*]` asserts `runs == ["1","2"]`, `has_encore is False` and the title is kept.
- (m): the n-colon tracklists and the DSO bare-digit lines.
- (o): this substitute is weaker; see Important 1.

**No production or existing-test changes (check 7).**
- `git diff a892b7a 6bddf0d -- packages/llama/src` is empty.
- `git diff main -- packages/llama/src/llama/setlist.py` is empty.
- The test diff has 0 `-` lines; it is purely additive (`test_stage_gather.py:3729-3824`).
- Both commits carry the suite command and the trailers.

### Strengths

- **The Step A tests test what they claim, and assert their own preconditions.**
  - **M5** runs through `compute_gather`. It asserts `has_encore is True`, which rules out a vacuous pass, and that the exact demoted count-flag text is in `notes` (`test_stage_gather.py:3742-3751`).
  - **M6** asserts that the reader kept the taper's spelling (`:3766`) and that `_CLOSER_FLAG` parses the flag (`:3738`). Without both, `kept == [flag]` would be a tautology.
  - **M2 and M3** use event and closer choices where the correct mapping and the mutant's mapping give different verdicts.
  - **M4** asserts the labels really differ, and only at the filler index (`:3821`).
- **The instrument is rigorous.** Every mutant had an import check, a one-line diff assertion, a fresh pycache, and a timeout. The pass + fail total of 760 rules out hangs and aborts. Sentinels were planted in all three mutated modules.
- **(o)'s outcome was predicted correctly.** The "Set Intro stays green" prediction was right and was written before the run. Splitting (c) and adding (d2) were sound choices.

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

1. **mutation.md is wrong to say the boundary is "redundant in the header regexes".** See the "(o)" Observations bullet in `docs/superpowers/2026-10-22-taper-set-markers-sdd/mutation.md`, the handback's "Observation for Task 9" section, and the PREDICT o line in the log.
   - **Why the claim fails:** `_CONT` (`cont…`) and the disc label in `_SET_DISC_HEADER` (`{_DISC}`) may directly follow the token, so the token is not always followed by a separator.
   - **Measured on base vs (o)** with `read_taper_structure("Set 1:\nBertha\nSet 2:\nSugaree\n<line>\nRipple\n")`:

     | line | base | without the boundary (o) |
     |---|---|---|
     | `Set2cont`, `Set 2cont:`, `Set IIcont` | a set-2 song title | a continuation header |
     | `Set 1CD1`, `Set 1Disc 1` | a song | header; voids with `decreasing set number` |

   - **So:** the boundary is load-bearing in the header reader too, and no test pins that, since (o)'s only red was `[Set In Stone]`.
   - **Why it matters:** this is an evidence document. A claim that a boundary is "redundant" is exactly what licenses someone to remove it later.
   - **Fix:** correct the observation, and record the header-side effect as unpinned. Pinning it is the orchestrator's call under R14.
   - **Separately, a pre-existing inconsistency outside this diff:** the comment at `taper.py:170` lists `Set2cont` as a recognised continuation form, but the `(?!\w)` at `taper.py:165` stops it being read as one. It ships as a song title. That belongs to the owning task, Task 1/2.

2. **Measurement 6's "forms' word boundaries" is only partly pinned: o2 and o3 survive.**
   - **The boundaries are load-bearing.** With each boundary removed, `read_taper_structure` returns `set_like=True` for a numbered-set item that today reads `set_like=False`:
     - o2: `songs from the first setlist`, `Second Settlement`;
     - o3: `2nd settle`, `1st Setting Sun`.
   - **Effect:** that makes the set-like veto (`taper.py:774`) fire.
   - **Risk is low.** An over-firing veto only leaves a show on today's path, so it costs yield and never ships a wrong structure.
   - **But the claim is wrong.** mutation.md's "the forms' word boundary is pinned" overstates coverage. The brief listed (o) alone, so this is a gap in the plan, not something the implementer skipped.
   - **Fix:** two params in `test_set_like_negatives`, for example `"from the first setlist"` and `"2nd settle"`, or record both as known survivors. Either is the orchestrator's call under R14 ("survivors outside (t)–(x) are reported").

#### Minor (Nice to Have)

1. **The extra-red count is wrong.** mutation.md (Result paragraph) and the 6bddf0d commit message say "Twelve mutants also turned other tests red". Scoring `results.jsonl` against `predicted` gives **13**: a, b, c1, c2, d, d2, e (undeclared) and i, j1, j2, l, m, n (declared).
2. **Some declared collateral is too vague.** The declarations for (l) ("any real-case fixture with a line starting `E.`") and (n) ("other Task 5 jerrybase-enabled gather tests…") are open-ended. They let `test_encore_like_flag_real_case` and `test_closer_flag_is_a_note_when_taper_text_names_another_closer` count as "declared" without having been named. These are acceptable, but they are weak predictions.
3. **The predictions for (a)–(e) were narrow.** Each named only the single eponymous test, which is why 7 mutants carried undeclared reds. That is harmless, because each was read and explained; see R15 below.

### Ruling R15 (seven undeclared extra reds scored CAUGHT-AS-PREDICTED)

**The ruling is sound.** What [[mutation-scoring-needs-a-prediction]] guards against is a red that fails for the wrong reason, and requires the difference to be reported.
- **Every core prediction was red**, and mutation.md lists each extra as "not declared" (difference reported).
- **I reproduced (a)'s two extras.** I also read c1's extra in the test source: the show becomes owned, the `reason` is `None`, and `.startswith` raises `AttributeError`. That is the rule's own behaviour, not collateral.
- **One caveat:** "CAUGHT-AS-PREDICTED" is a generous label for a red set that is a strict superset of the prediction. "CAUGHT (+n undeclared, read)" would make the record self-describing. The substance is fine.

### Assessment

**Task quality: Needs fixes**

**Reasoning:** The Step A tests are real and correctly targeted, and I independently reproduced the run (t, u, q, s, i, a, o all match, with sentinel proof). But the mutation record misstates (o)'s mechanism, and it overstates Measurement 6's word-boundary coverage: two load-bearing ordinal boundaries survive. The record needs correcting; whether to also add the two-param pin is for the orchestrator to decide.

### Evidence

- **Scratch:** `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-taper-markers/0443a042-e8ee-4093-a603-2fbd14e62179/scratchpad/t8-rev/` holds `run.py`, `run.out`, `base/` and `m/<id>`.
- **Log:** `$D/t8-rev/t8-rev.log` holds the predictions, then the teed run.
