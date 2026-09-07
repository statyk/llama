# Task 4 scoped re-review — fix round 1 (`ad5fce7..542d690`)

```
Finding 1 (Important): ADDRESSED
Finding 2 (Minor): ADDRESSED
Finding 3 (Minor): ADDRESSED
Finding 4 (Minor): ADDRESSED
Finding 5 (Minor): ADDRESSED
Finding 6 (Minor): ADDRESSED
Finding 7 (Minor): ADDRESSED
Per-site fullmatch pinning: independently pinned
Bytecode-aliasing claim: mechanism real and fix sufficient
New breakage in the fix diff: none
VERDICT: all findings addressed
```

## Method and cache precaution

All mutation runs used a **fresh `tempfile.TemporaryDirectory()` as
`PYTHONPYCACHEPREFIX` per mutant** (plus `-p no:cacheprovider`), the script asserted a
**unique sha1 per mutated `cli.py`** and a **unique anchor** (`count(old) == 1`) before
writing, and restored with `git checkout HEAD -- packages/llama/src/llama/cli.py` after
every mutant. Runner: `<scratchpad>/sdd/t4-rerev/mut.py`; log
`<scratchpad>/sdd/t4-rerev/t4-rerev.log`. Suite driven:
`./.venv/bin/python -m pytest packages/llama/tests/test_fix.py -q` (baseline **49 passed**).
Focused confirmation run: `test_fix.py test_cli.py test_show_cmd.py` → **124 passed**.
`git status --porcelain` empty at the end (verified twice).

Nine mutants, every one CAUGHT by exactly the predicted test, all sha1s distinct:

| mutant | failing test(s) |
|---|---|
| MF1 `e.get("reasons", [])` → `e["reasons"]` | 12 failed, incl. `test_include_reads_a_pre_feature_excluded_row` |
| MF2a `fullmatch`→`match`, **guard site only** | `test_resolve_include_tokens_needs_show_json` (1) |
| MF2b `fullmatch`→`match`, **lookup site only** | `test_a_filename_that_merely_starts_like_a_handle_is_a_filename` (1) |
| MF2c both sites | both of the above (2) |
| MF3 delete the `readmit` echo | `test_include_echoes_the_new_include_list` (1) |
| MF4 delete the undo-routing echo | `test_unexclude_routing_says_what_it_did` (1) |
| MF5 remedy hardcodes `--exclude ...` | `test_include_refuses_to_combine_with_suggest_titles` (1) |
| MF6 drop the `(show has N excluded files)` clause | `test_out_of_range_handle_errors` (1) |
| MF7 only the first `--include` token read | `test_include_is_repeatable` (1) |

## Evidence per finding

**1 — ADDRESSED.** `test_fix.py:387-389` adds `{"filename": "legacy.mp3"}` (no `reasons`,
no `duration_sec`) **last** in `_show_with_excluded`'s list.
`cli.py:1298` — `_excluded_handles` is `enumerate(show.excluded_files, start=1)` in
show.json order, so a row appended last takes `x4` and renumbers nothing; the x1/x2/x3
tests are unchanged and green. `test_include_reads_a_pre_feature_excluded_row`
(`test_fix.py:576-590`) asserts `fix --include x4` exits 0 and writes
`include == ["legacy.mp3"]`. MF1 fails it at `test_fix.py:583` on
`assert r.exit_code == 0` with `<Result KeyError('reasons')>` — a behaviour assertion,
not an escaping exception. Bonus: `test_include_handle_is_the_one_show_tracks_printed`
runs the real `show --tracks` over this fixture, so the bare row is also proven
renderable.

**2 — ADDRESSED, and each site is independently pinned.** `cli.py:1260` (guard) and
`cli.py:1269` (lookup). Flipping **one site at a time** now fails a *different* test each
time (MF2a → `test_resolve_include_tokens_needs_show_json`, via the new
`cli._resolve_include_tokens(ws, ["x1foo.mp3"]) == ["x1foo.mp3"]` line at
`test_fix.py:546`; MF2b → `test_a_filename_that_merely_starts_like_a_handle_is_a_filename`,
failing at `test_fix.py:613`, i.e. the **mixed-group** `x1,x1foo.mp3` case, with
`no excluded file x1foo.mp3 (show has 4 excluded files)`). The implementer's account of
why the single token caught neither site alone is correct and reproduced. The concrete
defect the finding named — `x1foo.mp3` silently resolving to `x1`'s file — is now pinned
at the site that would cause it.

**3 — ADDRESSED.** `cli.py:2459-2461` builds `typed` from the flags actually given
(`--exclude`/`--unexclude`/`--include`, `if given`) and interpolates it at `cli.py:2468`.
`typed` cannot be empty: the enclosing guard is `if exclude or unexclude or include`.
`test_fix.py:569` asserts the scoped substring
`` `llama fix gratefuldead-1973-06-10 --include ...` without --no-run `` — a positive,
specific assertion, not a whole-output negative. `test_cli.py`'s prefix assertion is
unaffected (124 passed on the three files).

**4 — ADDRESSED.** `test_include_echoes_the_new_include_list` (`test_fix.py:601-612`)
matches the exact line via `any(ln == "…" for ln in r.output.splitlines())` —
**line-scoped**, no whole-output match. MF3 caught it and nothing else.

**5 — ADDRESSED.** `cli.py:2554-2560` prints, before the `overrides.exclude = …` line and
only when `undo` is non-empty, `<slug>: <files> was operator-excluded, not junk-filtered
-- removed from overrides.exclude rather than added to overrides.include`. Pinned by
`test_unexclude_routing_says_what_it_did` (`test_fix.py:615-628`) with the same exact-line
`any(ln == …)` form. MF4 caught it and nothing else.

**6 — ADDRESSED, comment-only as directed.** `git diff ad5fce7..HEAD -- cli.py` filtered to
non-comment `+`/`-` lines yields **only** the `typed` construction, the remedy f-string
swap and the undo echo — **zero** non-comment changes inside `_edit_overrides`
(`cli.py:1177-1195`). The new comment states the real guarantee, states the counterexample
(`add_exclude=["a"], add_include=["a"]` in one call returns "a" in both) and names `fix`'s
clash guard as the enforcement.

**7 — ADDRESSED.** `test_fix.py:533` now asserts the whole message
`"no excluded file x9 (show has 4 excluded files)"` (MF6 caught). `test_include_is_repeatable`
(`test_fix.py:591-599`) passes **two separate `--include` flags** rather than a comma group
(MF7, `tokens[0]` only, caught it while the comma-group test stayed green — the two
properties are genuinely distinct).

## Bytecode-aliasing claim — assessed

**The mechanism is real.** CPython's default (timestamp) `.pyc` validation stores the
source's mtime truncated to whole seconds **plus its size**, and revalidates on exactly
those two. `fullmatch` → `match` removes exactly 4 bytes at either site, so the MF2a and
MF2b sources are **byte-identical in length**; written inside the same second, the second
run's import is served the first mutant's bytecode. The symptom is precisely what was
reported: a plausible CAUGHT attributed to the wrong test.

**The fix is sufficient.** A fresh `PYTHONPYCACHEPREFIX` per mutant relocates both the
cache **lookup** and the write into an empty tree, so recompilation is forced and no two
mutants can share a cache entry. Two caveats worth recording: printing distinct sha1s is a
good audit trail but is **not by itself** the fix (hashes differ while sizes match, which
is all the validator sees), and `PYTHONDONTWRITEBYTECODE`/`-B` would **not** have sufficed
(it suppresses writes, not stale reads). I re-ran the battery under the same precaution
independently and got MF2a and MF2b failing **different** tests — an outcome aliasing
would have made impossible — so the corrected results are corroborated, not merely
restated.

## New breakage in the fix diff

**None.** Two files touched (`cli.py`, `test_fix.py`); `junk.py`'s constants are unchanged
(`SHORT_FRACTION_OF_MEDIAN = 0.25`, `MIN_MEDIAN_SAMPLE = 5`, `MIN_PLAUSIBLE_SEC = 90.0`),
`ManifestTrack` gains no field, `Overrides` has no `extra="forbid"`, the resolver still
goes through `_excluded_handles` (`cli.py:1266`), and the two lists stay mutually exclusive
through the CLI (`clash` guard + `_edit_overrides`' cross-filters). The diff adds **no**
whole-output negative assertion (`grep -nE "^\+.*assert .* not in "` → none).

## Out-of-scope / deferrable observations

- `cli.py:2557` — `', '.join(undo)` with a singular "was" reads wrong if `undo` ever carries
  more than one file ("a.mp3, b.mp3 was operator-excluded"). Cosmetic; the implementer
  flagged the line-length half of this himself.
- `test_fix.py:533` now hardcodes the fixture's excluded-file count (`show has 4`), so a
  future fifth fixture row must update it. Acceptable coupling — the count is the property
  under test.
- Round-1 items already ruled and untouched here: `rm_include=` omitted from
  `_edit_overrides`, and the three pre-existing whole-output negatives in `test_triage.py`
  (`:80`, `:245`, `:361`).
