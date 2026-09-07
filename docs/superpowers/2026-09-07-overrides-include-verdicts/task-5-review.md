SPEC COMPLIANCE: PASS
TASK QUALITY: CHANGES REQUESTED
DOCS MATCH SHIPPED CODE: no (1 divergence: the `excluded (N):` listing and the `dropped` count are documented as junk-filter-only, but both also contain `operator-excluded` rows)

# Task 5 review — documentation for `overrides.include`

## Scope checks (all pass)

- **No source or test file touched.** `git diff --name-only 542d690..0946d6a` →
  `CLAUDE.md`, `README.md`, `docs/workflow.md`,
  `docs/superpowers/specs/2026-09-07-overrides-include-design.md`. Zero `.py`.
- **Junk constants unmoved.** `junk.py:66` `SHORT_FRACTION_OF_MEDIAN = 0.25`,
  `:69` `MIN_MEDIAN_SAMPLE = 5`, `:70` `MIN_PLAUSIBLE_SEC = 90.0` — none appear
  in the diff, and the working tree still carries those values.
- **Spec appended, not edited.** The spec hunk is `@@ -207,10 +207,38 @@` with
  28 `+` lines and zero `-` lines; sections 1-5 and "Out of scope" are byte-
  identical. Heading is exactly
  `## Corrections made during implementation (2026-09-07)`.
- **Suite not re-run** (docs-only diff; implementer reports 1964 passed,
  7 deselected, matching baseline). No warning noise in the reported tail.

## Verified against the real code

- **Excluded-row example reproduces byte-for-byte.** I rendered
  `cli.py:1352-1356`'s format string
  (`f"  {handle:>3s}  {_fmt_dur(...):>6s}  {e['filename']}  {', '.join(reasons)}"` + `.rstrip()`)
  over the doc's three rows and `diff`'d it against `docs/workflow.md:643-647`:
  **identical**. Duration before filename, filename unpadded and untruncated,
  ragged reasons — the trim from the implementer's four-row capture introduced
  no inaccuracy.
- **`fix --help` matches.** Ran `./.venv/bin/python -m llama fix --help`; the
  `--include` help string is verbatim `cli.py:2370-2372`, and the docs describe
  it (x-handle from `show --tracks`, or the source filename) without quoting
  anything the CLI does not say.
- **`+` legend.** `cli.py:1334` is `  + = ruled in by the operator (overrides.include)`,
  emitted only when some track carries it (`cli.py:1332`). `docs/workflow.md:653-654`
  says "carries a `+` in the track table, with its own legend line" — no false
  claim about what the filter would have done, matching the `cli.py:1330-1333`
  comment.
- **Re-admit hint's location.** `cli.py:1635-1638` — inside `_print_show_entry`'s
  `if show_tracks:` block, after `_format_tracks`, not inside the shared helper.
  The docs make no claim that it appears in the `[e]xclude` picker. Correct.
- **`--include` on an `operator-excluded` row un-excludes.** `cli.py:2547-2553`
  computes `was_operator` from `show.json`'s reasons, splits `undo`/`readmit`,
  folds `undo` into `rm_exclude`, and prints the explanatory line at `:2557-2560`.
  Documented at `docs/workflow.md:597` and `CLAUDE.md:209`.
- **Three-flag refusal.** `cli.py:2448` `if exclude or unexclude or include:` and
  the dynamic remedy at `:2461-2464`. Both `docs/workflow.md:615-616` and
  `CLAUDE.md:250-252` now name all three, and the "an exclusion renumbers tracks"
  clause is correctly generalised.
- **Repeatable / comma / gather.** `--include` is `list[str]` (`cli.py:2369`),
  `_resolve_include_tokens` splits comma groups (`cli.py:1259`), and
  `did_files = bool(exclude or unexclude or include)` feeds
  `stage = "gather" if (did_files or did_meta) ...` (`cli.py:2516`, `:2601`).
  `docs/workflow.md:597` states all three.
- **CLAUDE.md's mechanism claim is exact.** `junk.py:250-257` sits after
  `_keep_and_exclude` and after `_dedupe_duplicate_listings` (`:231-232`) and
  before the ordering block (`:259-266`); the docstring at `:213-216` and the
  comment at `:234-246` say precisely "the floor cannot move", "a re-admitted
  duplicate listing would be immediately re-dropped", and "re-admitting a file
  with no track tag reverts the whole recording to filename order". CLAUDE.md's
  sentence reproduces all three.
- **"A file in both lists is excluded."** `gather.py:869-876` — the exclude block
  runs after `filter_files(..., readmit=...)` and logs `"exclude wins"`. The CLI's
  mutual-exclusion guarantee is `_edit_overrides`'s cross-removal
  (`cli.py:1190-1196`) plus `fix`'s clash guard (`cli.py:2540-2545`). Both accurate.
- **`recording:` line.** `cli.py:1591-1592` prints `({N} tracks, {M} dropped)`
  unconditionally (not gated on `--tracks`), matching `docs/workflow.md:654-655`.
- **Spec corrections accurate.** (1) spec `:156-159` does depict a padded,
  filename-first table — superseded, correctly. (2) spec `:127` does say
  `show.excluded_files[N-1]["filename"]`; the code uses `_excluded_handles`
  (`cli.py:1264-1265`, `:1292-1298`). (3) spec `:144` does mention `rm_include=()`;
  `_edit_overrides`'s signature (`cli.py:1170-1174`) has only `add_include`, and
  the removal is derived at `:1192`.

## Strengths

- The implementer rendered the real `_format_tracks` output rather than
  hand-typing it, and the trimmed doc example survives a byte-level diff against
  the shipped format string. That is the right method for this task.
- The five reported divergences are all real and all correctly resolved in favour
  of the code, not the brief.
- CLAUDE.md's addition is in register: mechanism-first, names the three
  positions inside `filter_files`, states the consequence (filename ordering),
  and carries the "do not loosen the junk constants" framing plainly. README's
  sentence is operator-facing; workflow.md's is reference-manual voice. All three
  match their surroundings.
- The spec was appended to rather than rewritten, preserving the approved record.

## Issues

### Critical (Must Fix)

None.

### Important (Should Fix)

1. **`docs/workflow.md:639-640` (and `:654-655`, and `README.md:191`) describe
   the excluded listing as junk-filter-only; it is not.**
   `_excluded_handles` (`cli.py:1298`) enumerates *all* of `show.excluded_files`,
   and `gather.py:872-874` appends `operator-excluded` rows to that same list
   before `gather.py:1169` writes it. So an operator-excluded file gets an
   `x`-handle and is counted in `(N tracks, M dropped)` too. The same file
   contradicts itself: the flag-table row at `:597` explicitly documents the
   `operator-excluded` branch of `--include`, which only exists *because* such
   rows appear in this listing.
   Remedy: at `:639-640` say "one line per file that was dropped — junk-filtered
   or `operator-excluded` — with an `x`-handle…"; at `:654-655` "the count of
   dropped files"; at `README.md:191` "lists every dropped file with an
   `x`-handle".

### Minor (Nice to Have)

2. **`docs/workflow.md:639` "ends with an `excluded (N):` section".** It does not
   quite end there: `cli.py:1636-1638` prints
   `  re-admit one with: llama fix <slug> --include x1` after it, and that hint
   is documented nowhere. Remedy: "…ends with an `excluded (N):` section …
   followed by a `re-admit one with:` hint naming the first handle."

3. **`docs/workflow.md:622` is a ragged rewrap artifact.** The edit left
   ``` `--set-title N="..."` on the same invocation always wins over the proposal for that ```
   at 83 columns followed by a one-word line `track.`, where the surrounding
   paragraph wraps at ~74. Re-wrap the two lines.

4. **`docs/workflow.md:657-658` "re-admitting a `duplicate-listing` row will ship
   that recording twice."** The duplicated unit is one *track*
   (`junk.py:170-178` excludes a single duplicate copy per key). This reproduces
   the approved spec's own wording (spec `:47-48`), so it is not a new error, but
   "ship that track twice" is the accurate claim. (The whole-recording framing
   only holds in the `ymsb2005-12-31` 56→28 case cited at `junk.py:156-158`.)

5. **`CLAUDE.md:203-211` never states that `--include` redoes from `gather`.**
   The preceding "…all redo from `gather`" list closes before the new sentence
   begins, so the reader must infer it from "are joined by". `docs/workflow.md:597`
   states it explicitly; one clause in CLAUDE.md would close the gap.

## Assessment

**Spec compliance:** ✅ Every file and step the brief lists has its hunk
(README example + "Correct the data" sentence; workflow.md Correct row, flag-table
row, refusal sentence, new subsection; CLAUDE.md `:49`, overrides paragraph,
refusal sentence; spec appendix). Nothing extra, nothing skipped, no source or
test file touched.

**Task quality:** Needs fixes — one Important item (finding 1), which is a
one-line prose correction in three places. Everything else is Minor. The example
rendering, the mechanism claims, and the spec appendix are all verified correct
against the shipped code.
