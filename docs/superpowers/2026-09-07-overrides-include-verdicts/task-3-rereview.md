# Task 3 scoped re-review — fix rounds 1 and 2 (0401dc9..fd7e60d)

```
Finding 1 (Important): ADDRESSED
Finding 2 (Minor): ADDRESSED
Finding 3 (Minor): ADDRESSED
Finding 4 (Minor): ADDRESSED
Finding 5 (Minor): ADDRESSED
Finding 6 (author ruling): ADDRESSED
Sweep for stale row-shape assertions: complete
New breakage in the fix diff: none
VERDICT: all findings addressed
```

## Finding 1 — the `+` legend's false parenthetical

`cli.py:1284` now reads `  + = ruled in by the operator (overrides.include)`, with a
four-line comment above it (`cli.py:1280-1283`) recording why the old parenthetical was
untrue. The claim is exactly what `Track.included` encodes — the operator named the file
in `overrides.include` — and asserts nothing about what the junk filter did. One-line
shape and the `  + = ` prefix preserved, so the sibling-legend shape and the
`ln.startswith("  + = ")` negative in `test_no_re_admitted_legend_...`
(`test_show_cmd.py:450`) both still apply.

Wording is pinned, not merely prefixed: `test_show_cmd.py:434` asserts
`"  + = ruled in by the operator (overrides.include)" in r.output.splitlines()` —
exact line membership, so any rewording (including a restored parenthetical) fails.

## Finding 2 — the re-admit hint

Removed from `_format_tracks`; emitted at `cli.py:1586-1589` inside `_print_show_entry`'s
`if show_tracks:` block, gated on `_excluded_handles(s)` being non-empty and interpolating
`entry.slug`. The handle is `handles[0][0]` from `_excluded_handles`, not a literal
`"x1"` — the single-producer constraint holds at the new site.

Unreachable from the picker, by construction and not by a second guard:
`_pick_excludes` (`cli.py:1311`) prints only `_format_tracks`, which no longer emits the
hint; the walkthrough's own entry render is `_print_show_entry(entry)` at `cli.py:1425`
with `show_tracks` defaulting to `False` (`cli.py:1521`). Pinned by
`test_triage.py:166-167` (no line contains `--include`, none contains
`re-admit one with`) and, on the reader path, by the exact-line assertion at
`test_show_cmd.py:331` carrying the real slug `gratefuldead-1973-06-10`.

## Finding 3 — trailing whitespace on a reason-less row

The row is `.rstrip()`ed (`cli.py:1301-1303`), with the reason recorded in the comment
above. Rendered live from the shipped code: `'   x3       ?  no-reason.mp3'` — no
trailing space, duration `?` retained. Pinned by
`test_excluded_row_with_no_reasons_has_no_trailing_whitespace`
(`test_show_cmd.py:396-413`), which covers both reachable shapes (`reasons` key absent,
and present-but-empty) and asserts `ln == ln.rstrip()` plus an `endswith` on the filename
so dropping the field instead of the whitespace also fails.

## Finding 4 — the picker's excluded listing is pinned

`test_triage.py:142-167`,
`test_exclude_picker_lists_the_dropped_files_but_not_the_re_admit_hint`, drives the real
walkthrough (`cli_invoke(cfg, "triage", input="e\n\n")`), asserts `"excluded (1):"` as an
exact line and parses the entry row to
`["x1", "1:12", "spam.mp3", "filename", "convention", "mismatch"]` (so a
handle/entry mis-pairing cannot pass), asserts the hint's absence line-scoped, and
asserts `calls == []` so it is exercising rendering rather than a redo.

## Finding 5 — whole-output negatives

Every negative added or touched by the fix diff is line- or row-scoped:
`test_show_cmd.py:426`, `:462` (`not any(ln.startswith("excluded (") ...)`) and `:427`
(`not any("--include" in ln ...)`), `test_triage.py:166-167`. **No new whole-output
negative appears anywhere in the diff** — verified by reading every added line and by
`grep -n "not in r.output"` over both test files: the 8 hits in `test_show_cmd.py`
(48, 61, 69, 70, 81, 82, 261, 274) and 3 in `test_triage.py` (80, 245, 361) are all
outside the diff and pre-date this task.

The round-1 correction the report describes is real: `test_show_cmd.py:427` was
`assert "--include" not in r.output` at the time of the finding and is now line-scoped.

## Finding 6 — the excluded row's shape

`cli.py:1301-1303` is exactly the ruled shape,
`f"  {handle:>3s}  {_fmt_dur(...):>6s}  {e['filename']}  {', '.join(...)}"` + `.rstrip()`.
The `width = max(len(...))` computation is gone from the file entirely (grep: no `width`
in `_format_tracks`). No truncation anywhere. Rendered from the shipped code:

```
excluded (3):
   x1    0:37  a.mp3  spam
   x2   62:02  gd73-06-10.sbd.hollister.174.sbeok.shnf.t07.mp3  duplicate-listing
   x3       ?  no-reason.mp3
```

26 / 81 / 29 characters — only the genuinely long row is long, reasons ragged, the
47-character filename printed in full. `e.get("duration_sec")` / `e.get("reasons", [])`
retained.

### Sweep for stale row-shape assertions — complete

I swept the tree myself rather than trusting the report's table. Every site that can
depend on the excluded row's field order, widths, or `endswith`:

- `grep -rn "excluded ("` over `packages/` — `test_show_cmd.py:317, 426, 462`,
  `test_triage.py:163`; the only other hit is `cli_select.HELD_NOTE`, unrelated text.
- `grep -rn '"x1"|"x2"'` over `packages/` — `test_show_cmd.py:308` (the pure
  `_excluded_handles` unit test, no row), `:320, :321, :331, :348`; `test_triage.py:165`.
- `grep -rn "excluded_files"` over all test packages — the remaining hits are
  `test_stage_gather.py` (117, 1216, 2079-2148: entry-dict assertions, no rendering) and
  `test_show_cmd.py:113`, which passes `excluded_files=[]` and slices only the track rows.
- `grep -rn "endswith("` over the three affected test files — only
  `test_show_cmd.py:412-413` (updated to the filename) and an unrelated
  `test_cli.py:486`.

Both sites the supplied list did not name are indeed updated
(`test_show_cmd.py:412-413`, `test_triage.py:165`). **No site passes by coincidence and
no stale one remains.**

### The replacement for the retired padding assertion — verified by mutation, not reading

The retired `spam.index("1:12") == tuning.index("0:12")` is replaced by real column pins.
Arithmetically the shape gives: handle `>3` at cols 2-4, duration `>6` ending at col 12,
filename at col 15 — matching `test_show_cmd.py:326-327`
(`... + 4 == ... + 4 == 13`, i.e. both durations start at 9 and end at 13; and both
filenames at 15). That is a fixed-value pin, not a tautology.

The load-bearing one is `test_excluded_rows_align_regardless_of_filename_length`
(`test_show_cmd.py:352-394`), which uses a 5-character name against a 47-character one
and durations of *different widths* (`0:37` vs `62:02`), asserting the two durations end
at 13 but *start* at different columns — so right-alignment is pinned as right-alignment.

I ran the mutation the finding's doubt points at: reinstated the filename padding
(`_w = max(len(x['filename']) ...)`, `{e['filename']:<{_w}s}`) in `cli.py`.
Result: **1 failed, 55 passed** — sole failure
`test_excluded_rows_align_regardless_of_filename_length`, on
`assert len(short_row) == 15 + len("a.mp3") + 2 + len("spam")`
(`68 == 26`). The exact-length assertion bites; the report's account of the weaker
`len(short) < len(long)` form being replaced is accurate. `cli.py` restored
(`shasum -a 256` `ffc9dfec8470…b38cd` before and after; `git status --porcelain` empty).

## Process note — the amended round-1 commit

`git diff 24b20c3 eb1e278` is **one file, one hunk, one line**:
`test_show_cmd.py:377`, `assert "--include" not in r.output` →
`assert not any("--include" in ln for ln in r.output.splitlines())`.
`git diff --stat` confirms `1 file changed, 1 insertion(+), 1 deletion(-)`. **Nothing
else rode along.** The report's silence about the amend is a reporting omission only.

## Constraints re-checked

- `junk.py:66,69,70` — `SHORT_FRACTION_OF_MEDIAN = 0.25`, `MIN_MEDIAN_SAMPLE = 5`,
  `MIN_PLAUSIBLE_SEC = 90.0`, untouched (`models.py`/`junk.py` are not in the diff at all).
- `ManifestTrack` gains no field; no `extra="forbid"` on `Overrides` — the diff touches
  only `cli.py`, `test_show_cmd.py`, `test_triage.py`.
- `llama show` stays read-only: every added statement is a `typer.echo` or a pure helper
  call; `_excluded_handles` is pure.
- `e.get("duration_sec")` / `e.get("reasons", [])` retained, never `e[...]`; pinned by
  `test_excluded_section_survives_a_show_json_written_before_duration_sec`
  (`test_show_cmd.py:336-348`).
- `_excluded_handles` remains the single producer — the two consumers (`cli.py:1286`,
  `:1586`) both call it; no other numbering exists in the tree.
- Offline/deterministic: `./.venv/bin/python -m pytest packages/llama/tests/test_show_cmd.py
  packages/llama/tests/test_triage.py packages/llama/tests/test_cli.py -q` → **102 passed
  in 1.06s**, consistent with the report's 102 for those files.

## New breakage in the fix diff

None. `_print_show_entry`'s new block sits after the pre-existing `_format_tracks(s)`
call inside `if show_tracks:`, and `s` is non-`None` there by the early return at
`cli.py:1528-1533`, so the added `_excluded_handles(s)` introduces no new `None` path.
The double call to `_excluded_handles` (helper + entry) is pure and cheap.

## Out-of-scope observations (deferrable minors, non-blocking)

1. `docs/superpowers/specs/2026-09-07-overrides-include-design.md:156-160` still depicts
   the padded, filename-first row the author ruled wrong. The spec, not the code, is now
   stale; worth correcting at final review.
2. Eleven pre-existing whole-output negatives remain outside this task's code:
   `test_show_cmd.py` 48, 61, 69, 70, 81, 82, 261, 274 and `test_triage.py` 80, 245, 361.
   `assert "archive.org" not in r.output` (`test_show_cmd.py:69, 261`) is the shape most
   likely to be weakened silently by a rename.
3. `--json` excluded entries still carry no `handle` key (parked by prior ruling; Task 4's
   resolver will need the same numbering `_excluded_handles` produces).

## Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.
