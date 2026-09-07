SPEC COMPLIANCE: PASS

Reviewer: spec-compliance, Task 3 (`overrides-include`), commit `0401dc9`.
Method: read the brief, the spec (§4/§5 binding), the full review diff, then the
shipped code and tests in the working tree. Rendered `_format_tracks` directly
against spec §4's own example data to compare layouts. Ran
`test_show_cmd.py test_cli.py test_triage.py` (99 passed); did not re-run the
whole suite.

## Requirement-by-requirement

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 1 | `_format_tracks` gains `excluded (N):` — handle, filename, duration, reasons; renders under `--tracks` AND in the `[e]` picker | **Met** (picker half untested — F4) | `cli.py:1283-1292`; single helper call sites `cli.py:1297` (`_pick_excludes`) and `cli.py:1563` (`show --tracks`). Pinned: `test_show_cmd.py:test_tracks_listing_shows_the_excluded_section` (whole-row `split()` pins, so handle/entry pairing is pinned, not just co-presence) |
| 2 | `+` marker in its OWN one-character column beside `?`/`-`; legend only when a track carries it | **Met** | `cli.py:1273` (`{'+' if t.included else ' '}` sits between `.` and `" set "`, `_MARK[t.matched]` untouched at its own position); legend `cli.py:1280-1281`. Pinned: `test_tracks_listing_marks_a_re_admitted_track` (whole-prefix `"   1.+ set "` / `"   2.  set "`, so a zero-width marker fails), `test_no_re_admitted_legend_when_no_track_was_re_admitted`, and `_MARK_COL` 17→18 in `test_cli.py:160` which keeps the orthogonal `?`/`-` column pinned by fixed offset |
| 3 | `recording: <id>  (N tracks, M dropped)`, always-visible line, only when `excluded_files` non-empty | **Met** | `cli.py:1527-1528`. Pinned both ways: `test_dropped_count_shows_without_the_tracks_flag` (present, and no `excluded (2):` without `--tracks`) and `test_no_dropped_clause_when_nothing_was_dropped` (exact line `recording: gd73  (1 tracks)`, which also kills the unconditional-clause mutant emitting `, 0 dropped`) |
| 4 | `include=[...]` on the `overrides:` line in BOTH `_print_show_entry` and `_print_show_json` | **Met** | `cli.py:1538-1539` and `cli.py:1601`. Pinned: `test_overrides_line_and_json_carry_include` (both halves) and `test_json_schema_spot_checks`' exact-dict assertion, now carrying `"include": []` |
| 5 | `_excluded_handles(show) -> list[tuple[str, dict]]`, `show.excluded_files` order, numbered from 1, SINGLE producer | **Met** | `cli.py:1244-1249`. Pinned: `test_excluded_handles_number_from_one_in_show_json_order`. Single-producer verified in the tree, not just the diff: `grep -rn 'f"x{' packages/llama/src` returns only `cli.py:1249`; the display path at `cli.py:1283` consumes the helper rather than re-numbering |
| 6 | Stale duration comment corrected per spec §5 | **Met** | `cli.py:1256-1260`; the old "can't co-occur: junk drops files with no length" is gone, replaced by the re-admission/`package.py`-reprobe explanation. Comment-only, so unpinnable by test — verified by reading |
| 7 | Scope cut: NO new interactive `[i]nclude` verb; picker prompt still play-order numbers | **Met** | `RESOLVE_PROMPT` (`cli.py:1321`) and the `choice ==` ladder (`cli.py:1425-1447`) are untouched by the diff and carry no `i` branch; `_pick_excludes`' prompt (`cli.py:1299`) is unchanged. Pinned incidentally but genuinely: `test_triage.py:24` holds `RESOLVE_PROMPT` verbatim, so adding a verb fails a test |
| 8 | Defensive reads — `e.get("duration_sec")`, never `e[...]` | **Met** | `cli.py:1289-1291` uses `e.get("duration_sec")` and `e.get("reasons", [])`. Pinned: `test_excluded_section_survives_a_show_json_written_before_duration_sec` (entry with the key absent renders `["x1", "old.mp3", "?", "spam"]`). `e["filename"]` is direct, correctly — `junk.py` writes it on every entry unconditionally |

## Global constraints (verified in the working tree, not the diff)

| Constraint | Verdict | Evidence |
|---|---|---|
| `SHORT_FRACTION_OF_MEDIAN` 0.25 / `MIN_PLAUSIBLE_SEC` 90.0 / `MIN_MEDIAN_SAMPLE` 5 unchanged | Met | `junk.py:66,69,70`; `junk.py` is not in the commit's file list at all |
| `ManifestTrack` gains no field | Met | `models.py:253-259` — six fields, `models.py` not modified by this commit |
| No `extra="forbid"` on `Overrides` or a persisted artifact | Met | `models.py:200-213` — no `model_config`; `models.py` untouched |
| `llama show` strictly read-only | Met | Every added line is a `typer.echo`/list append or a dict literal; no `write_artifact`, no `open(..., "w")`, no workspace mutation in the diff |
| Offline, deterministic; no network in any test | Met | New tests use `build()` fixtures + `cli_invoke`; no `requests`/`urllib`/HTTP import added |

## Rewritten and added tests — does coverage survive?

The brief's six tests: three shipped rewritten, three effectively as-written. Checked
assertion by assertion; **no coverage was dropped**, and three cases got stronger.

- `test_no_dropped_clause_when_nothing_was_dropped`: the brief's
  `assert "dropped" not in r.output` is genuinely broken as the implementer reports —
  `show` prints `path:` carrying pytest's `tmp_path`, whose basename is
  `test_no_dropped_clause_when_no0`, which contains `dropped`. The assertion matched the
  directory name and failed against correct code. The replacement (exact `recording:`
  line) covers the original intent **and** the `, 0 dropped` mutant the original could not
  distinguish. Strictly better.
- `test_tracks_listing_marks_a_re_admitted_track`: original `"1.+" in intro` /
  `"2.+" not in dew` retained in substance, replaced by whole-prefix pins that
  additionally assert an unmarked row carries a **space** in that column — which is what
  makes requirement 2's "own one-character column" (rather than a variable-width marker)
  actually pinned. Coverage strictly increases.
- `test_tracks_listing_shows_the_excluded_section`: all four of the brief's substring
  assertions are subsumed by the two `split()` row pins (`x1`+`spam.mp3`+reasons,
  `x2`+`tuning.mp3`+`0:12`), plus column-padding and the hint. The original could not
  detect a handle/entry mis-pairing — the exact failure `_excluded_handles`-as-sole-producer
  exists to prevent — and the rewrite can. Strictly better.
- The four added tests (`e.get` survival, the `if handles:` guard, the legend's absence,
  `data["excluded"]` gated on `--tracks`) each pin a requirement the brief stated but left
  unpinned. Requirement 8 in particular had **no** brief test.
- Two pre-existing tests were adapted rather than weakened: `_MARK_COL` 17→18 (the
  `+` column shifts every row by exactly one; the constant remains a fixed-offset pin, and
  the implementer's mutation 12 shows reverting the layout fails it) and
  `test_tracks_flag_prints_every_title_source_in_full`'s `SimpleNamespace` gaining
  `excluded_files=[]`. Neither removes an assertion.

## Findings

### Minor 1 — excluded-table indent is one space wider than spec §4 depicts
Spec §4 shows `  x1  dm1969-08-08t13.mp3       0:37  implausibly short`; the shipped
renderer emits `   x1  dm1969-08-08t13.mp3        0:37  implausibly short` — three leading
spaces, because `cli.py:1289` right-aligns the handle in width 3 (`{handle:>3s}`) so `x10`+
stay column-aligned with `x1`. Verified by rendering §4's own example data. This is a
divergence from the depicted layout and better than the depiction; column order, content
and separator widths otherwise match exactly. **Remedy: none — record it, do not "fix" it
back to the spec's two spaces.**

### Minor 2 — the `re-admit one with:` hint is beyond spec §4's depicted table
`cli.py:1292` appends `re-admit one with: llama fix <show> --include x1`. Spec §4's example
block does not contain it; it comes from the brief's Step 3, so it is sanctioned, but three
things about it are worth an owner decision:
1. It advertises `fix --include`, which lands in **Task 4**. Between this commit and Task 4
   the branch instructs an operator to run a command that exits with a usage error.
   Self-resolving inside the branch; the concrete risk is only merging Task 3 to `main`
   alone. Matches the implementer's concern 1 — I agree it is not a defect, but it **is**
   a merge-order constraint that should be recorded on the branch.
2. It prints a literal `<show>` placeholder, where the sibling hint in the same command
   (`to overrule after inspecting: llama fix gratefuldead-1973-06-10 --overrule`,
   `test_show_cmd.py:test_overrule_hint_points_at_fix`) prints the real slug. Inconsistent
   with the established display convention.
3. It also renders inside the `[e]` picker (shared helper), where the prompt cannot accept
   `x1` — an operator is shown an `x`-handle and a command in the same breath as a prompt
   that rejects handles.
**Remedy (optional, owner's call):** substitute the show's actual slug as the `--overrule`
hint does, and consider suppressing the hint in the picker path. Both are cosmetic; neither
blocks.

### Minor 3 — `data["excluded"]` in `--json` is beyond spec §4
`cli.py:1600` adds `data["excluded"] = s.excluded_files if s is not None else None` inside
`if show_tracks:`. Spec §4 names only the `include=` addition for `_print_show_json`; the
brief's Step 4 specifies this, so it is in-scope for the task, but it is a **new public JSON
field** not described in the design. It mirrors `data["tracks"]`' gating and is pinned both
ways (`test_overrides_line_and_json_carry_include`,
`test_json_omits_excluded_without_the_tracks_flag`), so it cannot drift silently.
**Remedy: none needed; flagging so the spec/CLAUDE.md text can be updated when the branch's
docs pass runs.**

### Minor 4 — requirement 1's picker half is correct but unasserted
The `[e]` picker gets the excluded listing purely because `_pick_excludes` (`cli.py:1297`)
calls `_format_tracks`. That is exactly what spec §4 asks for, and the single call site
makes it true by construction — but nothing asserts it. `test_triage.py:120-137` exercises
the picker (`input="e\n1\n"`) without looking at the rendered table, and no test in the tree
touches `_pick_excludes` directly. A future refactor that gave the picker its own formatter
would silently drop half of requirement 1 with a green suite.
**Remedy:** one line in `test_exclude_action_writes_overrides_and_redoes_gather` (or a new
sibling) asserting `any(ln.startswith("excluded (") for ln in r.output.splitlines())` on a
held show whose `show.json` carries an excluded entry.

### Minor 5 — the legend parenthetical can assert something false
`+ = re-admitted by operator (the junk filter had dropped it)` (`cli.py:1281`). `Track.included`
means "the operator named this file in `overrides.include`", not "the junk filter had
dropped it" — Task 1's own docstring says so, and `junk.filter_files(readmit=)` is a no-op
for a file the filter would have kept, while `gather` still stamps `included=True` on it.
For that row the parenthetical is a false claim. The wording is the brief's and the spec's,
so shipping it as specified is correct behaviour for an implementer; raising it is mine.
**Remedy (owner's call, one-word edit):** `(re-admitted past the junk filter)`, which is
true in both cases. Not a compliance failure — the implementer rendered exactly the text
they were given.

### Nothing Critical or Important
No requirement is unmet, nothing was built beyond the brief except the two brief-sanctioned
additions in Minor 2 and Minor 3, and every global constraint holds in the tree.

`⚠️ Cannot verify from diff`: nothing. Every claim above was checked against the working
tree or by executing the shipped renderer.
