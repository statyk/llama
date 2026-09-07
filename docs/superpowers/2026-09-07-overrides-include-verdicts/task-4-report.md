# Task 4 report — `llama fix --include`

**Status:** DONE_WITH_CONCERNS (concerns are process/observations, not defects)
**Commit:** `ad5fce7` — `feat(fix): --include re-admits a file the junk filter dropped`
**Branch:** `overrides-include` (main checkout, no worktree). Not pushed.
**Suite:** `./.venv/bin/python -m pytest -q` → **1959 passed, 7 deselected** (baseline 1948 + 11 new tests).

---

## Changes, file by file

### `packages/llama/src/llama/cli.py`

1. **`import re`** added (line 2, after `import json`) — the module had none.

2. **`_HANDLE = re.compile(r"x\d+")` + `_resolve_include_tokens(show_ws, tokens)`**, placed
   immediately after `_resolve_exclude_tokens`. Expands comma groups, maps `xN` handles to
   filenames **through `_excluded_handles`** (never `show.excluded_files[N-1]`), passes
   non-handle tokens through as filenames. Out-of-range handle raises
   `LlamaError("no excluded file xN (show has K excluded files)")`; a handle token with no
   `show.json` raises `LlamaError`. Its docstring records *why* it goes through
   `_excluded_handles` (one producer ⇒ the handle the operator reads is the handle the
   resolver means), because that is the thing a future "simplification" would undo.

3. **`_edit_overrides`** grew `add_include=()` (signature wrapped onto a second line).
   The list building now reads:

   ```python
   exclude = [f for f in ov.exclude if f not in set(rm_exclude) | set(add_include)]
   ...
   include = [f for f in ov.include if f not in set(add_exclude)]
   for f in add_include: ...
   ```

   with a comment naming the invariant (mutual exclusion by construction ⇒ gather's
   "exclude wins" tiebreak is unreachable through the CLI). `"include": include` added to
   the `model_copy` update dict.

   **`rm_include=` was NOT added.** The spec's §3 bullet mentions it, but nothing in the
   task needs it: `--exclude` on an included file is expressed by `add_exclude` (which the
   `include = [...]` filter already honours), and there is no CLI flag that removes from
   `include` without adding to `exclude`. An unused keyword would be untested dead
   parameter surface. Flagging it as a deliberate deviation from the spec's prose.

4. **The `--include` option** on `fix`, immediately after `--unexclude`, with the brief's
   help text verbatim.

5. **`--suggest-titles` refusal** extended: guard `if exclude or unexclude or include:`;
   message now leads with `--suggest-titles cannot be combined with
   --exclude/--unexclude/--include: `. The brief said "change the two message strings" —
   there is only **one** occurrence of the literal `--exclude/--unexclude` in that message.
   I changed that one, and reworded "an exclusion" → "a file edit" / "Run the exclusion
   first" → "Run the file edit first" so the sentence is true of `--include` too. The
   remedy's `` `llama fix <slug> --exclude ...` `` example is left as-is (it is an example,
   not an enumeration). The `other_edit_requested` comment four lines below, which
   explains why `exclude`/`unexclude` are omitted from that check, was updated to name
   `include` as well — otherwise it would document a stale reason.

6. **`did_exclude` → `did_files`: FOUR sites**, counted against the file, matching the
   owner's ruling and not the brief's "both use sites":
   - `:2503` definition — now `did_files = bool(exclude or unexclude or include)`
   - `:2509` the `if not (did_files or did_meta or …)` guard
   - `:2519` the `if did_files:` block header
   - `:2581` the `stage = "gather" if (did_files or did_meta) else …` line

   (Line numbers post-change.) Sites 3 and 4 are separately load-bearing — mutation M6 and
   M7 below show the guard and the stage line fail differently.

7. **The edit block** (`if did_files:`) as briefed: resolve all three token lists first,
   then the `clash` check (exit 1 before any write or redo), then split `inc` into `undo`
   (row reason contains `operator-excluded` ⇒ edit `overrides.exclude`) and `readmit`
   (⇒ `overrides.include`), one `_edit_overrides` call, then the two conditional echo
   lines. `e.get("reasons", [])` throughout, per the defensive-read constraint.

### `packages/llama/tests/test_fix.py`

- `test_old_show_flags_are_not_fix_flags`: `("--include", "x.mp3")` removed from the loop,
  with the briefed four-line comment saying why.
- 11 new tests appended (list in the mutant table's "predicted test" column, plus
  `test_exclude_and_include_of_different_files_both_apply`).

---

## Tests I did not take from the brief as written

**One briefed assertion was wrong and was rewritten** —
`test_excluding_an_included_file_removes_it_from_include`:

```python
assert ov.exclude == ["intro.mp3"]      # briefed — FAILED
assert ov.exclude == ["dropped.mp3", "intro.mp3"]   # what is actually true
```

The brief's own `_show_with_excluded` fixture seeds `Overrides(exclude=["dropped.mp3"])`.
The briefed assertion would only hold if `--exclude` *replaced* the list instead of
appending — i.e. it silently asserted a behaviour the codebase does not have and never
should. It failed outright rather than passing for an incidental reason, so this one was
caught by running, not by mutation. The corrected line carries a comment recording the trap.

**Three tests added beyond the brief**, each pinning a ruled-on requirement the briefed set
left unpinned:

1. `test_include_handle_is_the_one_show_tracks_printed` — the ruling that
   `_resolve_include_tokens` MUST consume `_excluded_handles`. It runs the real
   `show --tracks`, parses `spam.mp3`'s handle out of the printed listing, and feeds that
   handle straight back to `fix --include`. This is the only test that fails when the two
   call sites *diverge* while each remains internally consistent. **Honest limit:** it
   cannot catch a change to `_excluded_handles` itself, because both consumers would drift
   together — which is precisely the property the single-producer design buys, so that
   blindness is correct rather than a gap.
2. `test_including_a_staged_exclusion_leaves_the_lists_disjoint` — pins the
   `| set(add_include)` clause in `_edit_overrides`, which the briefed tests left dead. The
   reachable path is `fix --exclude a.mp3 --no-run` (stages the exclusion without
   re-gathering, so `a.mp3` is still an ordinary track with no `operator-excluded` row),
   then `fix --include a.mp3`. Without the clause that writes `a.mp3` into **both** lists —
   the exact state the CLI exists to make unreachable. Mutant M3 confirms nothing else
   catches it.
3. `test_exclude_and_include_of_different_files_both_apply` — the "different files together
   is allowed" half of the ruling, which the briefed set only tested negatively.

Plus `test_resolve_include_tokens_needs_show_json`, a direct unit call: `fix` guards on
`sws.show.exists()` before reaching the resolver, so the resolver's own `show.json` guard
is unreachable through the CLI and can only be pinned this way. (`_resolve_exclude_tokens`
has the identical unreachable guard; I kept the symmetry rather than deleting it.)

**Negative-assertion discipline:** no whole-output negative was written. `stages == []` is a
parsed value; the "nothing was written" checks in `test_same_file_in_both_flags_errors`
read the parsed `Overrides` model, not the output text.

---

## Mutation results

Predictions were written **before** running. All mutations applied to
`packages/llama/src/llama/cli.py`, one at a time, each followed by
`git checkout HEAD -- packages/llama/src/llama/cli.py`. Runner script:
`<scratchpad>/sdd/t4-impl/mutate.py`. Suite used: `test_fix.py` (44 tests).

| # | Mutation | Predicted failing test | Result |
|---|---|---|---|
| M1 | `_resolve_include_tokens` bypasses `_excluded_handles`, builds handles by 0-based `enumerate` over `excluded_files` | `test_include_by_handle_writes_overrides_include`, `test_include_handle_is_the_one_show_tracks_printed` | **CAUGHT** — 7 failed, both predicted among them |
| M2 | `undo = []; readmit = list(inc)` (drop the operator-excluded routing) | `test_include_of_an_operator_excluded_file_unexcludes_it` | **CAUGHT** — exactly that one |
| M3 | drop `\| set(add_include)` from the exclude filter | `test_including_a_staged_exclusion_leaves_the_lists_disjoint` | **CAUGHT** — exactly that one |
| M4 | `include = list(ov.include)` (drop the `add_exclude` filter) | `test_excluding_an_included_file_removes_it_from_include` | **CAUGHT** — exactly that one |
| M5 | `clash = []` (drop the clash check) | `test_same_file_in_both_flags_errors` | **CAUGHT** — exactly that one |
| M6 | `did_files = bool(exclude or unexclude)` | `test_include_by_handle_writes_overrides_include` (exit 1, "nothing to fix") | **CAUGHT** — 7 failed, predicted one among them |
| M7 | `stage = "gather" if (did_meta) else …` (stage line only) | `test_include_by_handle_writes_overrides_include` on `stages == ["gather"]` | **CAUGHT** — 5 failed (incl. 3 pre-existing exclude tests), predicted one among them |
| M8 | `--suggest-titles` guard drops `or include` | `test_include_refuses_to_combine_with_suggest_titles`, on the message assertion | **CAUGHT**, but on the *earlier* assertion — see note |
| M9 | out-of-range handle passes through (`by_handle.get(p, p)`) | `test_out_of_range_handle_errors` | **CAUGHT** — exactly that one |
| M10 | drop the `show.json` guard in the handle branch | `test_resolve_include_tokens_needs_show_json` | **CAUGHT** — see note |
| M11 | no comma splitting in `_resolve_include_tokens` | `test_include_by_filename_and_comma_group` | **CAUGHT** — exactly that one |

**M8 note (prediction partly wrong, pin still genuine).** I predicted the message assertion
would fire. It failed one line earlier, on `assert r.exit_code != 0` → `assert 0 != 0`:
without the guard the invocation runs to completion and **exits 0**. That is a behaviour
failure, not an exception, and it is the stronger signal (the refusal did not happen at
all). Recording the mis-prediction rather than quietly claiming the predicted line.

**M10 note.** Caught by a `FileNotFoundError` escaping `read_model` at `cli.py:1257` instead
of the `LlamaError` the test expects, so `pytest.raises(LlamaError)` fails. Nominally
"caught by an exception", but here the exception *type* is exactly the pinned behaviour —
the guard exists to convert a raw `FileNotFoundError` into an operator-legible `LlamaError`
— so I am counting it as a real pin rather than re-running it in another form.

**Tree restored:** `git status --porcelain` empty after the battery, verified before the
commit was made and again after the two follow-up single-mutant re-runs.

---

## Concerns

1. **Process incident (self-inflicted, recovered, no impact on the delivered code).** My
   first mutation battery ran *before* the implementation was committed, and its
   `git checkout -- cli.py` restore step therefore reverted the entire uncommitted
   implementation after mutant M1. I detected it immediately (M2's anchor count came back
   0), reapplied the implementation from the same patch scripts, re-ran the full suite
   (1959 passed), committed, and only then re-ran the whole battery against a committed
   baseline using `git checkout HEAD --`. **Nothing was lost and no result in the table
   above predates the commit** — the table is entirely from the post-commit run. Worth
   recording as a durable rule for the rest of this plan: *commit before mutating, or
   restore from a saved copy rather than from git.*

2. **`rm_include=` omitted from `_edit_overrides`** — deliberate, reasoned in §3 above, but
   it is a departure from the spec's literal §3 wording and a reviewer should confirm the
   call.

3. **Pre-existing whole-output negatives found, LEFT UNTOUCHED per the ruling.** All three
   are in `packages/llama/tests/test_triage.py`, none in `test_fix.py`:
   - `:80`  `assert "other-1974-01-01" not in r.output`
   - `:245` `assert "zheld-1974-01-01" not in r.output`
   - `:361` `assert "suggest titles" not in r.output.lower()`

   `:361` looks the most exposed of the three (a short generic phrase against whole output);
   `:80` and `:245` match slugs, which are less likely to collide with a tmp_path. Reporting
   only — no edits made.

4. **The `readmit` echo line is unpinned by any assertion on its text.** Tests assert the
   resulting `Overrides` model, not that the `overrides.include = [...]` line printed. That
   matches how the pre-existing `overrides.exclude` echo is (not) tested, so I left it
   symmetric rather than adding a one-off output assertion — but a display reviewer may
   want it covered.

5. **`--include` on a file the junk filter would have kept anyway is silent** (no warning,
   `Track.included` still set). Task 3's `_format_tracks` comment already documents this as
   reachable and unwarned; nothing in Task 4 changes it. Noted only so it is not mistaken
   for a Task 4 regression.

---

# Fix round 1

**Status:** DONE_WITH_CONCERNS (one methodology finding below; no open defects)
**Commits:** `d3d0bf6` (the seven items) and `542d690` (a follow-up strengthening item 2's
pin after mutation showed it insufficient). New commits, no amend.
**Suite:** `./.venv/bin/python -m pytest packages/llama/tests/test_fix.py
packages/llama/tests/test_show_cmd.py -q` → **78 passed**;
`./.venv/bin/python -m pytest -q` → **1964 passed, 7 deselected** (was 1959; +5 tests).

All seven items done. Only three touched production, and none touched logic — two message
strings and one comment, exactly as scoped.

## The seven

**1 (Important) — `e.get("reasons", [])` pinned.** Added a fourth fixture row
`{"filename": "legacy.mp3"}` to `_show_with_excluded`: bare filename, no `reasons`, no
`duration_sec`, last in the list so it takes `x4` and renumbers nothing.
`test_include_reads_a_pre_feature_excluded_row` asserts `fix --include x4` exits 0 and
writes `include == ["legacy.mp3"]`. **Mutant MF1** (`e.get("reasons", [])` → `e["reasons"]`):
now **CAUGHT**, 12 tests failing including the new one — the `KeyError` takes down every
test whose fixture carries the legacy row, which is the point. It failed on
`assert r.exit_code == 0` (CliRunner converts the raised `KeyError` to exit 1), i.e. on the
behaviour assertion rather than by an escaping exception.

**2 (Minor) — `fullmatch` pinned, and my first attempt at it was insufficient.**
Detail below under "Where I went beyond the ask", because the first version of this test
passed for an incidental reason and mutation is what found it.

**3 (Minor) — the `--suggest-titles` remedy names the flag the operator typed.** The
remedy is now built from the flags actually given:

```python
typed = " ".join(f"{flag} ..." for flag, given in
                 (("--exclude", exclude), ("--unexclude", unexclude),
                  ("--include", include)) if given)
```

so `fix … --include x1 --suggest-titles` now says ``llama fix <slug> --include ...`` rather
than ``--exclude ...``. With both flags given it renders both, which stays copy-pasteable.
`test_include_refuses_to_combine_with_suggest_titles` extended to assert the remedy clause.
`test_cli.py:584` asserts `"cannot be combined with --exclude/--unexclude"`, still a prefix
of the leading sentence, so it is unaffected. **Mutant MF5** (hardcode `--exclude ...`
back): **CAUGHT**.

**4 (Minor) — the `readmit` echo pinned.** `test_include_echoes_the_new_include_list`
asserts the exact line via `any(ln == … for ln in r.output.splitlines())`, line-scoped, no
whole-output match. **Mutant MF3** (delete the block): **CAUGHT**.

**5 (Minor) — the routing now says what it did.** A new line, printed before the
`overrides.exclude = …` line whenever `undo` is non-empty:

```
<slug>: dropped.mp3 was operator-excluded, not junk-filtered -- removed from
overrides.exclude rather than added to overrides.include
```

Pinned by `test_unexclude_routing_says_what_it_did` (exact line match).
**Mutant MF4** (delete the block): **CAUGHT**. This also strengthened M2 — dropping the
operator-excluded routing now fails two tests instead of one.

**6 (Minor) — the `_edit_overrides` comment corrected.** It no longer claims the function
enforces mutual exclusion. It now states what the function actually guarantees (no call
that sets only one list can leave a name in both), states the counterexample explicitly
(`add_exclude=["a"], add_include=["a"]` in one call returns "a" in both), and names `fix`'s
clash guard as the enforcement and the only caller that can reach the case. No logic change,
as directed.

**7 (Minor) — both spec-named properties pinned.** `test_out_of_range_handle_errors` now
asserts the whole message, `"no excluded file x9 (show has 4 excluded files)"`, not a
prefix (**mutant MF6**, drop the count clause: **CAUGHT**). `test_include_is_repeatable`
uses two separate `--include` flags rather than a comma group (**mutant MF7**,
`tokens[0]` only: **CAUGHT** — and the comma-group test still passes under it, confirming
the two properties are genuinely distinct).

The four parked reviewer minors and the `test_triage.py` whole-output negatives were left
alone.

## Where I went beyond the ask (item 2)

The reviewer's stated mutant was "flipping **both** `fullmatch` to `match`". My first test
— the single token `x1foo.mp3` — caught that combined flip. **It caught neither site flipped
alone**, which I only learned by running them separately:

- *Guard site alone*: `any(match)` becomes true, so no early return; the **lookup** site's
  surviving `fullmatch` still routes the token to the filename path. Correct output.
- *Lookup site alone*: the **guard**'s surviving `fullmatch` returns early with the token
  untouched. Correct output.

A test that only catches a simultaneous two-site edit is a weak pin for two independent
call sites. So `542d690` added one case per site:

- The mixed group `x1,x1foo.mp3` — the real handle makes the guard fire on its own merits,
  so the lookalike reaches the **lookup** site, where `match` finds `x1` but the dict is
  keyed on the whole token, so the file is rejected as an unknown handle
  (`no excluded file x1foo.mp3`) instead of taken as a filename.
- `_resolve_include_tokens(ws, ["x1foo.mp3"])` with `show.json` unlinked, in the existing
  direct-call test — the **guard** site's only observable effect on its own, since `fix`
  checks `show.json` before the resolver is reached.

Post-change: **MF2a** (guard alone) → caught by `test_resolve_include_tokens_needs_show_json`;
**MF2b** (lookup alone) → caught by `test_a_filename_that_merely_starts_like_a_handle_is_a_filename`;
**MF2c** (both) → caught by both. Each site is now independently pinned.

## Methodology finding — stale bytecode aliased two mutants

While chasing MF2b I hit a result I could not reproduce by hand: the battery script
reported MF2b failing `test_resolve_include_tokens_needs_show_json`, while running the
identical file (verified by sha1) directly failed
`test_a_filename_that_merely_starts_like_a_handle_is_a_filename`.

**Cause:** CPython validates a cached `.pyc` on the source's **mtime in whole seconds plus
its size**. `fullmatch` → `match` shortens the file by exactly 4 bytes at either site, so
the MF2a and MF2b variants of `cli.py` are **the same size**; written within the same
second, the second run silently imported the **first mutant's bytecode**. The MF2b row was
therefore a re-test of MF2a wearing MF2b's label — a false CAUGHT, and exactly the
"caught for the wrong reason" class, but at the harness level rather than the assertion
level.

**Fix and re-verification.** I rebuilt the battery to give every mutant a unique
`PYTHONPYCACHEPREFIX` (a fresh temp dir per mutant, so no cache can be shared) and re-ran
**all 20 mutants** — both this round's 9 *and* the original 11 from the first report —
against current `HEAD` and the current tests. Script:
`<scratchpad>/sdd/t4-impl/mutate_all.py`. Each row prints the mutated file's sha1, and all
20 sha1s are distinct.

| # | Mutation | Predicted test | Result |
|---|---|---|---|
| M1 | bypass `_excluded_handles` (0-based) | handle + cross-check tests | CAUGHT (12) |
| M2 | drop the operator-excluded routing | `…of_an_operator_excluded_file_unexcludes_it` | CAUGHT (2) |
| M3 | drop `\| set(add_include)` | `…staged_exclusion_leaves_the_lists_disjoint` | CAUGHT (1) |
| M4 | drop the `add_exclude` filter | `test_excluding_an_included_file_removes_it_from_include` | CAUGHT (1) |
| M5 | drop the clash check | `test_same_file_in_both_flags_errors` | CAUGHT (1) |
| M6 | `did_files` ignores `include` | `test_include_by_handle_writes_overrides_include` | CAUGHT (12) |
| M7 | stage line ignores `did_files` | same, on `stages == ["gather"]` | CAUGHT (6) |
| M8 | suggest-titles guard ignores `include` | `test_include_refuses_to_combine_with_suggest_titles` | CAUGHT (1) |
| M9 | out-of-range handle passes through | `test_out_of_range_handle_errors` | CAUGHT (1) |
| M10 | no `show.json` guard | `test_resolve_include_tokens_needs_show_json` | CAUGHT (1) |
| M11 | no comma splitting | `test_include_by_filename_and_comma_group` | CAUGHT (2) |
| MF1 | `e.get("reasons", [])` → `e["reasons"]` | `test_include_reads_a_pre_feature_excluded_row` | CAUGHT (12) |
| MF2a | `fullmatch`→`match`, guard alone | `test_resolve_include_tokens_needs_show_json` | CAUGHT (1) |
| MF2b | `fullmatch`→`match`, lookup alone | `test_a_filename_that_merely_starts_like_a_handle…` | CAUGHT (1) |
| MF2c | `fullmatch`→`match`, both | both of the above | CAUGHT (2) |
| MF3 | delete the `readmit` echo | `test_include_echoes_the_new_include_list` | CAUGHT (1) |
| MF4 | delete the undo-routing echo | `test_unexclude_routing_says_what_it_did` | CAUGHT (1) |
| MF5 | remedy hardcodes `--exclude` | `test_include_refuses_to_combine_with_suggest_titles` | CAUGHT (1) |
| MF6 | drop the count clause | `test_out_of_range_handle_errors` | CAUGHT (1) |
| MF7 | only the first `--include` flag read | `test_include_is_repeatable` | CAUGHT (1) |

**SURVIVORS: none.** Every mutant is caught by the test predicted for it. The first
report's 11 rows are superseded by this run, which is strictly stronger (isolated caches,
current tests, verified distinct hashes).

A second, unrelated harness bug surfaced in the same rebuild and is worth recording: M11's
anchor `parts = [p.strip() for tok in tokens …]` occurs **twice** in `cli.py` — the line is
byte-identical in `_resolve_exclude_tokens`. The `count(old) == 1` assertion caught it and
the run aborted rather than mutating the wrong function. It is restored to the original
two-line anchor. (This is also the concrete reason the reviewer's "near-clone" park is
right on the merits but does cost something: the duplicated line makes single-line anchors
ambiguous.)

`git status --porcelain` empty after the battery, verified before and after.

## Concerns

1. **The stale-`.pyc` aliasing above is a standing hazard for the rest of this plan**, not
   a one-off: any two mutants that are the same size and written within the same second can
   alias, and the symptom is a plausible-looking CAUGHT on the wrong test rather than an
   error. Anyone running a mutation battery on this branch should set a per-mutant
   `PYTHONPYCACHEPREFIX` (or delete `__pycache__` between runs). Same-length identifier
   swaps — `fullmatch`/`match`, `get`/`pop`, `<`/`>` — are the exposed class.
2. **Item 5's new line is show-scoped prose, not a general facility.** If a future change
   lets `undo` carry many filenames, `', '.join(undo)` will produce a long line. Fine at
   today's scale; noting it so it is a known shape rather than a surprise.
3. Nothing else changed. The four parked minors and the `test_triage.py` whole-output
   negatives are untouched, as directed.
