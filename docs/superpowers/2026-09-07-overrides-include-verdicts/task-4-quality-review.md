TASK QUALITY: CHANGES REQUESTED

Scope: code quality only (clarity, YAGNI, routing correctness, error handling, test hygiene,
comment accuracy). Spec compliance is covered independently.

One Important finding, test-only — no production-code change is required to clear it.

---

## Verification I ran myself (tree left clean, `git status --porcelain` empty)

Four mutants applied to the **committed** `cli.py` (`ad5fce7`), each restored with
`git checkout -- <path>`, `packages/llama/tests/test_fix.py` (44 tests) as the runner:

| mutant | result |
|---|---|
| M2 `undo = []; readmit = list(inc)` | 1 failed — `test_include_of_an_operator_excluded_file_unexcludes_it`, on the `ov.include == []` line (cli.py:458 in the test). Exactly the table's claim, and exactly what that test's own docstring says will bite. |
| M3 drop `\| set(add_include)` | 1 failed — `test_including_a_staged_exclusion_leaves_the_lists_disjoint`. Exactly the table's claim. |
| M5 `clash = []` | 1 failed — `test_same_file_in_both_flags_errors`. Exactly the table's claim. |
| **(mine, not in the table)** move the clash check to AFTER `_edit_overrides` | 1 failed — `test_same_file_in_both_flags_errors`. The "errors, writes nothing" property is pinned by ORDER, not just by exit code. |

Two further mutants of my own that **survived** (findings M2/M3 below), and one direct
invocation of `fix --include x1` against a legacy `show.json` row (`{"filename":
"legacy.mp3"}`, no `reasons`/`duration_sec`): exit 0, `overrides.include ==
['legacy.mp3']`, no crash — the defensive read is correct.

**Process-incident claim (flagged item 2): VERIFIED.** `git status --porcelain` is empty,
so the working tree is byte-identical to `ad5fce7`. All four mutations above were applied
to that committed file by exact-string match with `count == 1` asserted, i.e. every
construct the table names exists verbatim in the commit; three of them reproduced the
table's single-test result exactly. `test_fix.py` collects 44 tests, matching the report's
stated runner, and 1948 + 11 new = 1959 is internally consistent. Nothing in the table is
inconsistent with the committed state; the committed state is coherent.

---

## Issues

### Critical (Must Fix)

None.

### Important (Should Fix)

**I1 — the defensive `.get("reasons", [])` is pinned by nothing.**
`packages/llama/src/llama/cli.py:2536`

Mutating `e.get("reasons", [])` → `e["reasons"]` leaves **182 tests green**
(`test_fix.py`, `test_show_cmd.py`, `test_triage.py`, `test_cli.py`,
`test_cli_commands.py` — verified). Every row in `_show_with_excluded`
(`test_fix.py:373-383`) carries `reasons`, so the back-compat arm is never exercised.

This is the plan's own stated global constraint ("a `show.json` written before this
feature has excluded entries with no `reasons`/`duration_sec` key; read them
defensively"), and the failure mode it guards is a hard `KeyError` crash of `fix
--include` for any operator with a pre-feature library — a class this branch has already
been burned by three times with assertions that pinned something other than their name.
The code is correct today; only the pin is missing.

Remedy (~5 lines, tests only): append a fourth row `{"filename": "legacy.mp3"}` — no
`reasons`, no `duration_sec` — to `_show_with_excluded`. It takes handle `x4` and
renumbers nothing, so `x1`/`x2`/`x3` and `test_out_of_range_handle_errors`'s `x9` are all
unaffected. Then assert `fix --include x4` exits 0 with `include == ["legacy.mp3"]`.
Confirm the pin by re-running the `e["reasons"]` mutant and predicting *that* test.

### Minor (Nice to Have)

**M1 — `fix --include x3` reports only `overrides.exclude`, never saying why.**
`cli.py:2541-2543`

On the operator-excluded routing (`undo` non-empty, `readmit` empty) the only output is
`<slug>: overrides.exclude = [] (the hold clears itself…)`. The operator typed
`--include` and is told about `exclude`, with nothing naming the routing. The message is
truthful but the mechanism is invisible at exactly the point it is least expected.
Remedy: when `undo` is non-empty, name it — e.g. append `(x3 was an operator exclusion,
not a junk drop; removed from overrides.exclude)`.

**M2 — `fullmatch` vs `match` is correct but unpinned.** `cli.py:1253`, `:1262`

Both sites use `fullmatch`, consistently, and `fullmatch` is the right choice: with
`match`, a source filename such as `x2disc.mp3` would be misread as a handle and die with
`no excluded file x2disc.mp3` instead of passing through as a filename. Flipping **both**
sites to `match` leaves all 44 `test_fix.py` tests green (verified). Remedy: one line in
`test_resolve_include_tokens_needs_show_json`'s neighbourhood —
`assert cli._resolve_include_tokens(ws, ["x1intro.mp3"]) == ["x1intro.mp3"]`.

**M3 — the `readmit` echo line's text is pinned by nothing.** `cli.py:2544-2546`

Deleting the whole `if readmit:` echo block leaves all 44 tests green (verified). The
implementer flagged this (concern 4) and chose symmetry with the equally-unpinned
pre-existing `exclude` echo, which is a defensible call — noting it as measured rather
than as a demand.

**M4 — `--include` on a staged exclusion writes a semantically wrong entry.**
`cli.py:2535-2538`

`was_operator` is derived from `show.json` rows only, never from `ov.exclude`. So
`fix --exclude a.mp3 --no-run` followed by `fix --include a.mp3` (the exact path
`test_including_a_staged_exclusion_leaves_the_lists_disjoint` walks) writes
`include == ["a.mp3"]` for a file the junk filter never dropped — and Task 3's `--tracks`
display will then mark it re-admitted, which is a lie about provenance. The net effect on
`gather` is identical (the file is kept either way), so this is labelling, not behaviour.
Deriving `was_operator` as `{rows…} | set(ov.exclude)` would route it to `undo` instead
and be strictly more faithful — at the cost of making `_edit_overrides`' `| set(add_include)`
clause unreachable through the CLI (it would remain as defence-in-depth for a hand-mangled
file). The current shape is what the brief specified; flagging the trade-off for the owner
rather than asserting the alternative is better.

**M5 — `_resolve_include_tokens` is a near-clone of `_resolve_exclude_tokens`.**
`cli.py:1218-1237` vs `:1240-1269`

Identical scaffolding: the comma-splitting comprehension (byte-identical), the
`if not any(...): return parts` short-circuit, the `show.exists()` guard, the
map-lookup loop. Only the predicate and the map differ. A full parameterised helper would
need ~5 behaviour arguments and be worse than the duplication, so I am **not** asking for
one — but the one genuinely identical line is worth extracting:
`def _split_tokens(tokens) -> list[str]` used by both. Brief-specified shape; Minor.

**M6 — `show.json` is read twice in one block.** `cli.py:1259` (inside the resolver) and
`cli.py:2535`. Harmless (small file, same process), but re-reading an artifact inside one
edit path is the shape that later grows a divergence. Remedy if touched: read `Show` once
at the top of the `if did_files:` block and pass it down.

**M7 — the `--suggest-titles` refusal's remedy example still says `--exclude`.**
`cli.py:2451-2453`. An operator who typed `--include` reads
`` `llama fix <slug> --exclude ...` `` as their remedy. The implementer's reasoning (it is
an example, not an enumeration) is sound; a `--include`-aware phrasing would still be
kinder. Cosmetic.

---

## The two flagged items

**1. `rm_include=` omitted from `_edit_overrides` — correctly-applied YAGNI. Agreed.**
Every removal from `include` in this codebase is expressed by `add_exclude`, and the
`include = [f for f in ov.include if f not in set(add_exclude)]` filter already implements
it. An `rm_include=` keyword would have no caller and no test, i.e. exactly the untested
parameter surface the rubric calls a defect. It will not bite the next caller either: to
use it, that caller would need a flag meaning "stop re-admitting this file *without*
excluding it", and no such flag exists or is planned — adding the keyword now would be
guessing at its semantics ahead of the flag that defines them. Separately worth the
owner's notice (feature scope, not this task): there is currently **no way to undo an
`--include` except by `--exclude`ing the file**, which changes the recorded reason from
"junk filter" to "operator". Effect on the shipped show is identical; only the recorded
provenance differs.

**2. The mutation-battery process incident — claim verified, no impact on the delivered
code.** See the verification table above: the tree is identical to `ad5fce7`, every
mutated construct exists verbatim in the commit, and three independent re-runs reproduced
the table's exact single-test results. The committed state is coherent, and I found no
sign that any table row predates the commit. The durable rule the implementer drew from it
(commit before mutating, or restore from a saved copy rather than from git) is the right
one and worth carrying to Task 5. Self-reporting an incident that left no trace in the
artifacts is the behaviour this process wants.

---

## Strengths

- **The mutual-exclusion invariant is genuinely two-layered and both layers are pinned.**
  Routing (`undo`/`readmit`, cli.py:2537-2538) decides *which* list, and `_edit_overrides`'
  `| set(add_include)` / `not in set(add_exclude)` filters (cli.py:1177-1186) make
  disjointness hold *regardless* of the routing. M2 and M3 fail on different tests, so the
  two layers are independently load-bearing rather than one masking the other.
- **The self-healing property was worth checking and holds.** From a hand-mangled
  `overrides.json` naming the same file in both lists, either `fix --include f` or `fix
  --exclude f` converges to a disjoint state in one invocation — traced through both
  branches; no CLI path can produce or preserve the state `gather`'s "exclude wins"
  tiebreak exists for.
- **Order of operations is right and is pinned by order, not by coincidence.** Both token
  lists resolve before the clash check, so `--include x1 --exclude intro.mp3` clashes on
  the *resolved* filename rather than on spelling; the clash exits before any write and
  before any redo, and moving the check one statement later fails a test (verified).
- **`test_include_handle_is_the_one_show_tracks_printed` (test_fix.py:394-409) is the
  right test and knows its own limits.** It parses the handle out of the real `show
  --tracks` output and feeds it back, which is the only construction that catches the two
  call sites diverging; the docstring records honestly that it cannot catch a change to
  `_excluded_handles` itself, and explains why that blindness is the design working.
- **The corrected brief assertion is a real catch, correctly explained.** `test_fix.py:472-475`:
  the brief's `ov.exclude == ["intro.mp3"]` would have asserted that `--exclude` *replaces*
  the list; the comment recording the trap is exactly the kind of durable note this
  repository runs on.
- **Comment accuracy held up under checking.** `test_including_a_staged_exclusion…`'s
  docstring claims `a.mp3` "is still an ordinary track" — `a.mp3` is in fact the fixture's
  single `Track` (test_catalog.py:16), so the narrative is true, not merely plausible.
  The `other_edit_requested` comment (cli.py:2477-2479) was updated rather than left to go
  stale, and the `_resolve_include_tokens` docstring records *why* it goes through
  `_excluded_handles` — the thing a future simplification would undo.
- **No new whole-output negative assertions.** Every new negative is a parsed value
  (`stages == []`, `Overrides` model equality), never `not in r.output`.
- **Error messages and streams are consistent with the file.** `no excluded file x9 (show
  has 3 excluded files)` mirrors the existing `no track N (show has K tracks)`; all three
  new errors go to stderr with `err=True`, the two success lines to stdout, matching the
  surrounding `fix` conventions.
- **`did_exclude` → `did_files` is complete at four sites, and two of them are separately
  load-bearing** (the table's M6/M7 fail differently) — the rename is not cosmetic.
- **Scope discipline:** the diff touches only `cli.py` and `test_fix.py`. `junk.py`'s
  do-not-retune constants, `ManifestTrack`, and the persisted models' permissiveness are
  all untouched; nothing new reaches the network.

## Assessment

**Task quality:** Needs fixes — one Important, test-only.

**Reasoning:** The routing is correct, converges from a hand-mangled state, is pinned by
order as well as by outcome, and survived every mutant I applied independently; the
comments and error messages are accurate and idiomatic for this file. The single blocking
gap is that the plan's explicitly named back-compat constraint — the defensive
`e.get("reasons", [])` read — has no test at all, which on this branch is precisely the
class of gap that has already shipped three mis-pinned assertions.
