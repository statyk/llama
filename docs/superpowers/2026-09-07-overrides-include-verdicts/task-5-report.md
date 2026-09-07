# Task 5 report — documentation for `overrides.include`

Status: DONE. Commit `0946d6a` on branch `overrides-include`. Tree clean.

## What I read before writing anything

- `packages/llama/src/llama/cli.py`: `_edit_overrides` (1170-1222),
  `_resolve_include_tokens`/`_HANDLE` (1247-1276), `_excluded_handles`
  (1292-1298), `_format_tracks` (1301-1357), `_print_show_entry`'s
  `--tracks` block and re-admit hint (1626-1638), and the `fix` command's
  `--include` option + handling (2369-2372, 2438-2566).
- `packages/llama/src/llama/junk.py`: `filter_files`'s `readmit` handling
  (182-263), which pins the "after the junk arms and dedupe, before
  ordering" claim used in CLAUDE.md.
- `packages/llama/src/llama/models.py`: `Track.included`, `Overrides.include`.
- Design spec sections 3 and 4
  (`docs/superpowers/specs/2026-09-07-overrides-include-design.md`).
- Ran `./.venv/bin/python -m llama fix --help` to get the real `--include`
  help text.
- Wrote a throwaway script
  (`.../scratchpad/sdd/t5-work/render_demo.py`, not committed) that builds a
  `Show`/`Track` model with excluded files of varying reasons/durations
  (including one with no duration and a deliberately long filename) and
  calls `_format_tracks` directly, to capture the real rendered lines
  rather than hand-typing an approximation.

## Places the brief/spec's prose disagreed with shipped behaviour

1. **Excluded-row layout.** Brief's step 2 and spec section 4 depict
   `x1  dm1969-08-08t13.mp3       0:37  implausibly short` (filename first,
   padded, then duration). The real code
   (`cli.py:1338-1356`) prints duration BEFORE the filename, the filename
   UNPADDED and never truncated, and the reasons ragged at the end via
   `.rstrip()`. Captured real output (via the throwaway script):
   ```
   excluded (4):
      x1    0:37  gd73-06-10d1t99.mp3  implausibly short
      x2    1:12  FOLLOW-ME @BYPIKENO.mp3  filename convention mismatch
      x3    4:02  gd73-06-10d2t04.mp3  duplicate-listing
      x4       ?  gd73-06-10d1t04-verylongfilenamethatislongerthanmostother...mp3  derivative of unknown original
   ```
   I used this shape (with a shorter, doc-appropriate three-row example) in
   `docs/workflow.md`'s new "Seeing what was dropped" subsection, and
   appended a correction to the spec (item 1) rather than editing section 4
   in place.

2. **The `+` legend wording.** Brief/spec don't specify exact wording, but
   the shipped string, read directly from `cli.py:1334`, is:
   `  + = ruled in by the operator (overrides.include)`
   — deliberately not "the junk filter had dropped it", because
   `Track.included` only records that the operator named the file in
   `overrides.include`, not that the filter would otherwise have dropped
   it (`cli.py:1329-1334` comment). Docs describe it that way (no false
   claim about what the filter would have done).

3. **The re-admit hint's location.** Brief doesn't mention this explicitly,
   but the spec's section 4 code block reads as if the hint lives inside
   the shared `_format_tracks` helper. It does not: it's printed by
   `_print_show_entry` after calling `_format_tracks` (`cli.py:1635-1638`),
   specifically because only that call site has `entry.slug` and because
   `_format_tracks` is also the interactive `[e]xclude` picker's renderer,
   where naming a `llama fix` command would be noise. I did not restate
   this location detail in the docs (it's an implementation-organization
   fact, not user-facing behaviour), but confirmed it before writing the
   "Seeing what was dropped" section so I didn't imply the hint appears in
   the picker.

4. **`--suggest-titles` refusal list is three flags, not two.** Both
   `docs/workflow.md:614` and `CLAUDE.md:242` (pre-edit) said `--exclude`/
   `--unexclude`; the shipped code (`cli.py:2448`, `2466-2467`) refuses the
   combination with `--exclude`/`--unexclude`/`--include` together, and the
   printed remedy dynamically names whichever of the three flags was
   actually typed (`cli.py:2462-2464`). Updated both docs to name all
   three and generalized "an exclusion renumbers tracks" to "any of the
   three renumbers tracks" since `--include` renumbers exactly the same
   way.

5. **`fix --include` on an `operator-excluded` row un-excludes rather than
   adding to `overrides.include`.** Confirmed at `cli.py:2545-2560`: the
   CLI computes `was_operator` from `show.json`'s `excluded_files` entries
   whose reasons include `operator-excluded`, splits `inc` into `undo` vs.
   `readmit`, folds `undo` into the `rm_exclude` argument, and prints:
   `<slug>: <file> was operator-excluded, not junk-filtered -- removed
   from overrides.exclude rather than added to overrides.include`.
   Documented in the `docs/workflow.md` flag table row and the CLAUDE.md
   overrides paragraph, matching the brief's description (which was
   accurate here).

6. **`_edit_overrides` has no `rm_include` parameter.** Spec section 3 says
   it "grows `add_include=()` / `rm_include=()`". Read signature at
   `cli.py:1170-1174`: only `add_include` exists. The removal-from-include
   effect (when `--exclude` names an included file) is derived inside the
   function itself: `include = [f for f in ov.include if f not in
   set(add_exclude)]` (line 1192). This is spec correction item 3 in the
   appended section — not a docs-visible behavior difference (the
   mutual-exclusion guarantee is unchanged), so no README/workflow/CLAUDE
   text needed correcting for it, only the spec.

7. **`xN` handle resolution goes through `_excluded_handles`, not
   `show.excluded_files[N-1]["filename"]` directly.** Spec section 3 says
   the latter; code (`cli.py:1250-1276`, `1292-1298`) goes through
   `_excluded_handles`, a single producer shared by `--tracks`'s listing
   and the resolver. Spec correction item 2. No user-facing docs needed
   correcting (the observable behavior — `xN` maps to the Nth excluded
   file in `show --tracks` order — is unchanged), only the spec's internal
   description of the mechanism.

## Files changed

- `README.md`: added a `llama fix ... --include x1` example line after the
  `--exclude` example (~line 152), and a sentence to the "Correct the
  data" bullet describing the reverse operation (~line 187).
- `docs/workflow.md`:
  - Added `; --include xN re-admits a file the junk filter dropped` to the
    **Correct** row's `fix` cell (~line 281).
  - Added a new `--include xN|FILE` row to the `fix` flag table, directly
    under `--unexclude` (~line 594).
  - Updated the `--suggest-titles` refusal paragraph (~line 614) to name
    `--exclude`/`--unexclude`/`--include` and generalized the "an exclusion
    renumbers tracks" clause to cover all three.
  - Added a new `#### Seeing what was dropped` subsection at the end of the
    `fix` reference (before `### llama redo ...`), with a three-row example
    built from the real rendered shape (shortened from the throwaway
    script's captured output to a doc-appropriate example matching the
    spec's original example filenames/reasons, but in the correct
    duration-first, unpadded column order).
- `CLAUDE.md`:
  - Extended the `fix` refuses-to-combine parenthetical (~line 49) to
    `--exclude`/`--unexclude`/`--include`.
  - Added a paragraph to the `overrides.json` description (~line 196-210)
    describing `--include xN|FILE`, its position in `filter_files`
    (after junk arms and dedupe, before ordering — verified against
    `junk.py:230-259`), the mutual-exclusion guarantee, the
    `operator-excluded` un-exclude behavior, and the "do not loosen the
    junk constants" framing per the task's binding instruction.
  - Extended the `--suggest-titles` refusal sentence (~line 242) to name
    all three flags.
- `docs/superpowers/specs/2026-09-07-overrides-include-design.md`: appended
  a `## Corrections made during implementation (2026-09-07)` section at
  the end (approved text above left untouched), listing the three
  divergences given in my instructions (excluded-table layout, `xN`
  resolution mechanism, and the omitted `rm_include` parameter).

No source file and no test file were touched.

## Real CLI output captured

`./.venv/bin/python -m llama fix --help` — confirmed the `--include` help
text matches exactly what's now described in docs:
```
--include  TEXT  Re-admit a file the junk filter dropped: an x-handle from
                  `llama show <show> --tracks` (e.g. x1) or the source
                  filename
```

`_format_tracks` real output (via
`.../scratchpad/sdd/t5-work/render_demo.py`, not committed, run against a
hand-built `Show`/`Track` model):
```
tracks:
   1.  set 1        Bertha                       tags             7:02  gd73-06-10d1t01.mp3
   2.+ set 1      - (unknown)                    unresolved          ?  gd73-06-10d1t02.mp3
   3.  set 2      ? (unknown)                    setlist          5:01  gd73-06-10d1t03.mp3
  ? = no setlist match
  - = not measured
  + = ruled in by the operator (overrides.include)
excluded (4):
   x1    0:37  gd73-06-10d1t99.mp3  implausibly short
   x2    1:12  FOLLOW-ME @BYPIKENO.mp3  filename convention mismatch
   x3    4:02  gd73-06-10d2t04.mp3  duplicate-listing
   x4       ?  gd73-06-10d1t04-verylongfilenamethatislongerthanmostotherfilenamesinthiscollectionbyquiteabit.mp3  derivative of unknown original
```
This confirms: duration-before-filename order, unpadded/untruncated
filename (the deliberately absurd-length x4 filename prints in full), the
ragged reasons tail (x4 has one reason, no trailing separator), the `?`
duration for a re-admitted track with no duration (`x2` at t02, matched
`None`), and the exact `+` legend string. Used this to write the
doc-appropriate example in `docs/workflow.md`.

## Test command and output tail

```
./.venv/bin/python -m pytest -q
```
Tail:
```
1964 passed, 7 deselected, 26 warnings in 6.35s
```
Matches the stated baseline exactly (1964 passed, 7 deselected) — docs-only
change, no test count drift.

## Commit

```
0946d6a docs: llama fix --include and the excluded-files listing
```
4 files changed (README.md, docs/workflow.md, CLAUDE.md, the design spec),
85 insertions, 16 deletions. `git status --short` clean after commit.

## Concerns

- None blocking. One judgment call: in `docs/workflow.md`'s new "Seeing
  what was dropped" subsection I used a doc-appropriate three-row example
  (reusing the spec's original example filenames/reasons) rather than
  pasting the throwaway script's full four-row output verbatim (which
  includes a deliberately absurd 90+ character filename chosen to prove
  no-truncation, not to read well as documentation) — the column order and
  spacing in the doc example were verified against the real
  `_format_tracks` output and match it exactly for the fields shown
  (leading two spaces, `x`-handle right-aligned to width 3, duration
  right-aligned to width 6, unpadded filename, ragged reasons), so nothing
  in the doc example is invented.
- I did not independently re-verify `--include`'s interaction with
  `triage`'s `[e]xclude` picker, since the brief and spec both say the
  scope cut leaves no `[i]nclude` verb there and I found no code adding
  one (`grep` for `include` in the triage command path turned up only the
  `--tracks` listing's shared `_format_tracks` call, consistent with the
  spec's "Deliberate scope cut" note).

## Fix round 1

Review verdict: SPEC COMPLIANCE passed; TASK QUALITY changes requested (1
Important, 4 Minor). All five addressed, docs-only, no source/test touched.

### What I verified before writing

- `packages/llama/src/llama/stages/gather.py:864-874` — confirmed
  `overrides.exclude` matches are appended to the same `excluded` list
  (`show.excluded_files`) that the junk filter populates, tagged
  `"operator-excluded"`. This is the evidence for item 1: `_excluded_handles`
  (`cli.py:1292-1298`) enumerates that whole list, so both the `x`-handle
  listing and the `dropped` count include operator-excluded rows, not just
  junk-filter drops.
- Built a full render via a new throwaway script
  (`.../scratchpad/sdd/t5-work/render_full.py`, not committed) that
  constructs a real `ShowWorkspace`/`CatalogEntry`, writes a `Show` with one
  `operator-excluded` row mixed into three junk-reason rows, and calls the
  actual `_print_show_entry(entry, show_tracks=True)` under
  `contextlib.redirect_stdout`, rather than calling `_format_tracks`
  directly as in the initial pass — this is what produced the authoritative
  `recording: ... (3 tracks, 4 dropped)` line, the excluded table with a
  real `operator-excluded` row, and the re-admit hint line, all in one
  captured render:
  ```
  recording: gd73-06-10.sbd.hollister.174.sbeok.shnf  (3 tracks, 4 dropped)
  ...
  excluded (4):
     x1    0:37  gd73-06-10d1t99.mp3  implausibly short
     x2    1:12  FOLLOW-ME @BYPIKENO.mp3  filename convention mismatch
     x3    4:02  gd73-06-10d2t04.mp3  duplicate-listing
     x4    3:00  gd73-06-10d1t05.mp3  operator-excluded
    re-admit one with: llama fix gd1973-06-10 --include x1
  ```
  This confirmed both the operator-excluded mixing (item 1) and the exact
  hint line format (item 2): two-space indent, `re-admit one with: llama
  fix <slug> --include <handle>`, printed after the excluded table, not
  inside it.
- Read `docs/superpowers/specs/2026-09-07-overrides-include-design.md`'s
  decision 4 to get the exact "ships that recording twice" wording being
  corrected (item 4), and confirmed in `junk.py`'s
  `_dedupe_duplicate_listings` docstring that a `duplicate-listing` row is
  one file listed twice on the same item, not a second recording.

### Item 1 — reworded sentence (verbatim, `docs/workflow.md`)

> `llama show <show> --tracks` includes an `excluded (N):` section — one
> line per file missing from the track list, *whatever removed it*: most
> often the junk filter, but a file dropped earlier via `--exclude` shows
> up here too, tagged `operator-excluded` (that's the row `--include` folds
> into an un-exclude rather than an `overrides.include` addition). Each row
> carries an `x`-handle, its duration and the reasons, and the section is
> followed by a re-admit hint, e.g.:

Companion fix to the `recording:` line sentence, same section:

> The count also appears on the always-visible `recording:` line
> (`(24 tracks, 3 dropped)`) — again counting every missing file, not just
> junk-filter drops.

And in `README.md`'s "Correct the data" bullet:

> The reverse also works: `llama show <s> --tracks` lists every excluded
> file — most often ones the junk filter dropped — with an `x`-handle, and
> `llama fix <s> --include x1` puts one back — the junk thresholds are
> measured and stay put, so a wrongly-dropped track is fixed per show, not
> by loosening the filter.

Checked `CLAUDE.md` for the same junk-filter-only claim: it never describes
the `excluded (N):` listing or the `dropped` count at all (only
`docs/workflow.md` and `README.md` do), so no equivalent defect existed
there. `CLAUDE.md`'s existing "`--include xN|FILE` ... re-admits a file the
junk filter dropped" sentence is a true statement of the *flag's* purpose,
not a claim about what the listing enumerates, so it was left as-is except
for the item-5 addition below.

### Item 2 — "ends with" claim and the undocumented hint

Fixed: "ends with" → "includes ... and the section is followed by a
re-admit hint". Added the captured hint line (with `<show>` as the doc's
standard placeholder, matching every other example in this file) to the
worked example:
```
excluded (3):
   x1    0:37  dm1969-08-08t13.mp3  implausibly short
   x2    1:12  FOLLOW-ME @BYPIKENO.mp3  filename convention mismatch
   x3    4:02  dm1969-08-08t07.mp3  duplicate-listing
  re-admit one with: llama fix <show> --include x1
```

### Item 3 — ragged rewrap

Rewrapped the `--suggest-titles` paragraph (`docs/workflow.md`, the
`--exclude`/`--unexclude`/`--include` refusal through "exiting early.")
programmatically with `textwrap.fill(width=74)` over the whole paragraph
rather than hand-editing individual lines, then diffed to confirm the
joined text was byte-identical before and after (only line breaks moved).
Confirmed via `git diff` that no words were added, dropped, or reordered.

### Item 4 — "recording" → "track"

Fixed in `docs/workflow.md`:
> No exclusion reason is refused: re-admitting a `duplicate-listing` row
> will ship that track twice — it's one file listed twice on the
> archive.org item, not the whole recording. The reason is printed next to
> the handle so the choice is made with it in view.

Appended a fourth entry to the spec's `## Corrections made during
implementation (2026-09-07)` section (approved text above left untouched):
> 4. **Decision 4's "re-admitting a `duplicate-listing` row ships that
>    recording twice" names the wrong unit.** A `duplicate-listing` row is
>    one file listed twice on the same archive.org item; re-admitting it
>    ships that one track twice, not the recording. Docs (`README.md`,
>    `docs/workflow.md`) describe it correctly, per this correction, as
>    shipping the track twice.

### Item 5 — CLAUDE.md missing the redo stage

Added "and redoes from `gather` like the other two" to the `--include`
sentence in `CLAUDE.md`'s `overrides.json` paragraph, matching how every
other file/metadata edit in that paragraph states its stage.

### Files changed this round

`README.md`, `docs/workflow.md`, `CLAUDE.md`,
`docs/superpowers/specs/2026-09-07-overrides-include-design.md` (append
only). No source file, no test file.

### Test command and output tail

```
./.venv/bin/python -m pytest -q
```
Tail:
```
1964 passed, 7 deselected, 26 warnings in 6.32s
```
Unchanged from baseline and from the prior round.

### Commit

```
f31cf50 docs: fix round 1 - excluded listing is not junk-filter-only
```
4 files changed, 30 insertions(+), 16 deletions(-). New commit, not an
amend. `git status --short` clean after commit.

### Concerns

None blocking. One note: item 1's fix touches the same paragraph as item
4's "recording"→"track" fix (both live in the "Seeing what was dropped"
section's closing sentences), so both are visible in one diff hunk in
`docs/workflow.md` — flagged here in case the reviewer expects them as
separable hunks; the content of each fix is independent and traceable to
its own item number above.
