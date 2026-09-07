SPEC COMPLIANCE: PASS

# Task 4 spec-compliance review — `llama fix --include`

**Diff reviewed:** `fd7e60d..ad5fce7` (review package read once; no `git diff` re-run).
**Tree state at review:** `git status --porcelain` empty, HEAD `ad5fce7`. Read-only review; nothing mutated.
**Suite:** not re-run (per instructions). Implementer reports 1959 passed / 7 deselected.

## Requirement-by-requirement

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 1 | `fix --include <handle\|filename>`, repeatable, comma-lists, redoes from `gather`, same shape as `--exclude` | **Met** (repeatability unpinned — Minor 3) | option `cli.py:2361-2365`; comma split `cli.py:1253`; `stage = "gather" if (did_files or did_meta)` `cli.py:2581`; pinned by `test_fix.py:404-410` (`stages == ["gather"]`), `:434-439` (comma group) |
| 2 | `_resolve_include_tokens` mirrors `_resolve_exclude_tokens`: comma groups, `xN`→filename, passthrough; handle needs `show.json` (same error style); out-of-range → `LlamaError` naming the count | **Partially met** — behaviour correct, but the count clause is unpinned (Minor 2) | `cli.py:1243-1270`; error text `cli.py:1263-1265`; `show.json` guard `cli.py:1256-1258` mirrors `:1223-1224`; pinned by `test_fix.py:519-525` (message prefix only) and `:528-540` (`show.json` arm, direct unit call) |
| 3 | Numbering comes from `_excluded_handles`, **not** `show.excluded_files[N-1]` | **Met** | `cli.py:1258-1259` calls `_excluded_handles(read_model(...))`; docstring `cli.py:1247-1251` records *why*. Pinned end-to-end by `test_fix.py:413-431`, which parses `spam.mp3`'s handle out of the real `show --tracks` output and feeds it back — the only test that fails when the two call sites diverge while each stays internally consistent. Implementer's mutation M1 confirms. Not reported as a spec deviation, per the orchestrator's ruling. |
| 4a | `--include` on an `operator-excluded` row edits `overrides.exclude`, not `overrides.include` | **Met** | routing `cli.py:2535-2540`; pinned by `test_fix.py:443-458`, whose own docstring correctly identifies that `ov.exclude == []` alone would *not* pin the routing and `ov.include == []` is the assertion that bites (M2 caught) |
| 4b | `--exclude` on a currently-included file removes it from `overrides.include` | **Met** | `include = [f for f in ov.include if f not in set(add_exclude)]` `cli.py:1185`; pinned by `test_fix.py:461-475` (M4 caught) |
| 4c | `--unexclude` unchanged | **Met** | `rm = _resolve_exclude_tokens(sws, unexclude or [])` `cli.py:2522` unchanged; `rm_exclude` now additionally carries `undo` (`cli.py:2539`), which does not alter `--unexclude`'s own semantics |
| 5 | Refuses to combine with `--suggest-titles`; refusal names `--include` alongside `--exclude`/`--unexclude` | **Met** | guard `cli.py:2441`; message `cli.py:2452-2460`; pinned by `test_fix.py:543-554` asserting the full new string (M8 caught — on `exit_code != 0`, i.e. the refusal not happening at all, which is the stronger signal). Pre-existing `test_cli.py:584` still passes: `--exclude/--unexclude` remains a substring of `--exclude/--unexclude/--include`. |
| 6a | `--exclude` + `--include` on **different** files allowed; both resolve against current `show.json` before any redo | **Met** | all three resolves precede any write and any redo (`cli.py:2520-2524` → `_edit_overrides` `:2539` → `_redo_show` `:2586`); pinned by `test_fix.py:478-489` |
| 6b | Same file in both = error, writes nothing, no redo | **Met** | `clash` check `cli.py:2527-2531`, exits before `_edit_overrides`; pinned by `test_fix.py:492-505` asserting `stages == []` **and** the unchanged parsed `Overrides` (not a whole-output negative). M5 caught. Clash is computed on **resolved filenames**, so `--include x1 --exclude intro.mp3` clashes — stronger than a raw-token comparison, and that is exactly the case the test exercises. |
| 7 | `_edit_overrides` grows `add_include=()`, applying the mutual-exclusion rule | **Met**, with a caveat (Minor 1) | signature `cli.py:1170-1171`; list building `cli.py:1178-1188`; `"include": include` in the `model_copy` update `cli.py:1193` |
| 8 | `rm_include=()` omitted | **Ruled: correctly-applied YAGNI, not a spec gap** — see below | — |
| A | `--include` routes to `redo --from gather` | **Met** | `cli.py:2581`; pinned by `stages == ["gather"]` at `test_fix.py:410` and `:489` (M7 caught) |
| B | Excluded entries read defensively (`e.get("reasons", [])`) | **Met** | `cli.py:2536`. `e["filename"]` at `cli.py:1259`/`:2535` is not `.get`-guarded, which is correct: `models.py:190` documents `filename` as always present and `junk.py:138,173,177` are the only producers, all of which set it. |
| C | `test_old_show_flags_are_not_fix_flags` no longer lists `--include`, with the reason in a comment | **Met** | `test_fix.py:56-62` — four-line comment recording the UX-redesign rename and the 2026-09-07 reintroduction |

## Global constraints (verified in the code, not the diff)

- `junk.py:66` `SHORT_FRACTION_OF_MEDIAN = 0.25`, `junk.py:69` `MIN_MEDIAN_SAMPLE = 5`, `junk.py:70` `MIN_PLAUSIBLE_SEC = 90.0` — **unchanged**, and untouched by this diff (`junk.py` is not in the changed-files list).
- `models.py` `ManifestTrack` — six fields, **no new field**.
- `models.py` `Overrides` — plain `BaseModel`, **no `extra="forbid"`**; `include` is a defaulted `list[str]`, so a pre-feature `overrides.json` still loads.
- No test in the diff reaches the network; all new tests are `cli_invoke` over `tmp_path` with `_redo_show` stubbed (`test_fix.py:_stub_redo`).

## Strengths

- Requirement 3 is not merely *implemented* but *pinned by the only test shape that can pin it* (`test_fix.py:413-431`): it round-trips through the real `show --tracks` rendering rather than asserting `x1 == excluded_files[0]`, which would have passed under the 0-based mutant just as happily. The docstring's stated blind spot (a change to `_excluded_handles` itself moves both consumers together) is the correct property of the single-producer design, not a gap.
- The implementer caught and corrected a **wrong assertion in the brief** (`test_fix.py:471-475`): `ov.exclude == ["intro.mp3"]` would only hold if `--exclude` *replaced* the list; the fixture seeds `exclude=["dropped.mp3"]`. The corrected line carries a comment recording the trap. Given this plan's history of assertions pinning something other than their name, that is the right catch.
- `test_including_a_staged_exclusion_leaves_the_lists_disjoint` (`test_fix.py:478-491` region) finds the *reachable* path into the `| set(add_include)` clause via `--exclude … --no-run`, which the briefed set left dead. Without it that clause is untested.
- Negative assertions are all scoped to parsed values (`stages == []`, the parsed `Overrides`), not whole-output substrings — the discipline this repo's tests have repeatedly needed.
- The mutation report records a **mis-prediction** (M8) rather than quietly claiming the predicted line, and the pre-commit-battery incident is disclosed with the recovery.

## Findings

### Critical
None.

### Important
None.

### Minor

**Minor 1 — `_edit_overrides` does not itself enforce the invariant its comment claims (`cli.py:1178-1188`).**
With `add_exclude=["a"]` and `add_include=["a"]` the function returns `a` in **both** lists: the `exclude` filter drops it (line 1181), the `add_exclude` loop re-appends it (1182-1184), the `include` filter drops it (1185), and the `add_include` loop re-appends it (1186-1188). The comment at `cli.py:1178-1180` states the property as belonging to the function ("mutually exclusive by construction: adding to one removes from the other"), but the enforcement actually lives in the caller's `clash` guard at `cli.py:2527`. Not reachable through `fix` today, and the guard is tested — so this is a documentation/robustness nit, not a behaviour defect. Remedy (either): skip names already in `add_exclude` when appending to `include` (`for f in add_include: if f in set(add_exclude): continue`), or reword the comment to name `fix`'s clash guard as the enforcement point so a second caller is not misled.

**Minor 2 — requirement 2's count clause is unpinned (`cli.py:1263-1265`, `test_fix.py:519-525`).**
The spec requires the out-of-range error to name *how many* excluded files there are. `test_out_of_range_handle_errors` asserts only `"no excluded file x9"`; deleting `(show has {len(by_handle)} excluded files)` would break no test. Remedy: add `assert "3 excluded files" in r.output` to that test.

**Minor 3 — `--include` repeatability is unpinned (`cli.py:2361`, `test_fix.py`).**
Spec §3 says "repeatable". Every new test passes a single `--include`; only the comma-group form is exercised. Repeatability follows structurally from `list[str]` + `typer.Option`, but nothing would fail if the annotation were narrowed to `str`. Remedy: one invocation with `--include x1 --include spam.mp3`.

**Minor 4 — the brief's "two message strings" resolved as one (`cli.py:2452-2460`).**
Only the leading sentence enumerates `--exclude/--unexclude/--include`; the remedy sentence's example still reads `` `llama fix {slug} --exclude ...` ``. Requirement 5 as stated ("the refusal messages name `--include` alongside `--exclude`/`--unexclude`") is met, and the implementer's reasoning — that the remedy is an example, not an enumeration — holds. Rewording "an exclusion" → "a file edit" is the right adjustment and makes the sentence true of `--include`. Recorded only so the brief/implementation divergence is visible to the controller. No change requested.

**Minor 5 — an x-handle passed to `--exclude` is not recognized as a handle, and bypasses the clash check (`cli.py:1218-1236`, `:2527`).**
`fix --include x1 --exclude x1` produces `add = ["x1"]` (a literal filename, since `_resolve_exclude_tokens` only maps *digit* tokens) and `inc = ["intro.mp3"]`, so no clash fires and `overrides.exclude` gains a name matching no file — gather then logs its existing `matched no file` warning. The resulting state is not the forbidden both-lists state, and this is pre-existing `--exclude` behaviour for any bogus filename rather than a Task 4 regression. Noted for the controller only; fixing it is a `--exclude` change, out of Task 4's scope.

## Ruling on requirement 8 (`rm_include=()`)

**Correctly-applied YAGNI. Not a spec gap.**

Reasoning, in order of weight:

1. **Every normative statement in §3 is satisfied without it.** §3's two mutual-exclusion clauses are "`--include` on an `operator-excluded` row removes from `overrides.exclude`" and "`--exclude` on a currently-included file removes it from `overrides.include`". The first is served by `rm_exclude` (which already existed, for `--unexclude`); the second is served by the derived filter at `cli.py:1185`. The `rm_include=()` mention sits in the *implementation-sketch* clause of §3's last bullet ("grows `add_include=()` / `rm_include=()`"), which is prose about how to build the rule, not a statement of behaviour. Nothing in §3, §4, §5 or §6 describes an operation that would pass it.

2. **The derived form is the stronger design, not merely the smaller one.** An explicit `rm_include` makes removal a *caller obligation*: a future caller that passes `add_exclude=["a"]` and forgets `rm_include=["a"]` writes the forbidden state, and the type system cannot see the omission. Deriving the removal from `add_exclude` inside the function makes it unforgettable. Since §3's own framing is "mutually exclusive **by construction**", the parameter the spec sketches actively works against the property the spec asks for. (Minor 1 above is the residual hole in that construction, and note that `rm_include` would not have closed it either.)

3. **No CLI surface would pass it.** There is no flag that removes a name from `include` without adding it to `exclude`; §3 defines none and "Out of scope" adds none. The nearest hypothetical is an `--uninclude` (revert a re-admission without marking the file `operator-excluded`), which the spec does not request. Were it added later, it lands as exactly one new parameter in exactly this place — a two-line change, not a design reversal.

4. **The unused-parameter cost is real in this repo.** An untested keyword-only parameter on a helper with a single caller is dead surface that later readers must reason about, and this codebase has repeatedly paid for exactly that kind of drift (`CLAUDE.md`'s "do not simplify it away" notes exist because inert code got removed by someone who could not tell inert from load-bearing — the inverse cost of shipping inert code in the first place).

I am ruling on the code, not on the implementer's stated rationale: had the omission left any §3 behaviour unimplemented, the YAGNI framing would not have saved it. It does not.

## ⚠️ Cannot verify from diff

- The reported suite total (1959 passed / 7 deselected) — not re-run, per instructions. Spot-checked that the two pre-existing assertions most exposed to this diff still hold by inspection: `test_cli.py:584` (`"cannot be combined with --exclude/--unexclude"` remains a substring of the new message) and `test_show_cmd.py:225` (`show --include` must still be "no such option" — `show`'s signature is untouched by this diff).
- The implementer's mutation battery (M1-M11) — the results are reported, not independently reproduced; reproducing them would require mutating the tree, which this review is forbidden from doing. The two mutants whose pins I checked by reading (M1 → `test_fix.py:413-431`, M4 → `:461-475`) are consistent with the reported outcomes.

## Assessment

**Task quality:** Approved.

**Reasoning:** Every requirement in the brief and spec §3 is implemented and, with the exception of the error-message count clause and repeatability (both Minor), pinned by a test that would fail if the requirement were dropped. Nothing beyond the requirements was added: the three tests written past the brief each pin a ruled-on requirement the briefed set left uncovered, and the one deliberate deviation (`rm_include`) is a correct reading of what §3 actually requires.
