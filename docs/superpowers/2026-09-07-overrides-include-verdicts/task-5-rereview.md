# Task 5 re-review — fix round 1 (0946d6a..f31cf50)

Finding 1 (Important): ADDRESSED
Finding 2 (Minor): ADDRESSED
Finding 3 (Minor): ADDRESSED
Finding 4 (Minor): ADDRESSED
Finding 5 (Minor): ADDRESSED
Docs match shipped code: yes
No .py touched: confirmed
Spec hunk additions-only: confirmed
New breakage in the fix diff: none
VERDICT: all findings addressed

## Evidence

### Finding 1 — excluded listing / `dropped` count are not junk-filter-only
`docs/workflow.md:639-645` now reads "includes an `excluded (N):` section — one line
per file missing from the track list, *whatever removed it*: most often the junk
filter, but a file dropped earlier via `--exclude` shows up here too, tagged
`operator-excluded`…". `docs/workflow.md:659-661` extends the same correction to the
count: "(`(24 tracks, 3 dropped)`) — again counting every missing file, not just
junk-filter drops". `README.md:191-192` matches: "lists every excluded file — most
often ones the junk filter dropped —". The junk filter remains the leading example in
all three places.

Verified against code, not the report:
- `cli._excluded_handles` (cli.py:1292-1298) enumerates `show.excluded_files` whole —
  no reason filter.
- `cli._format_tracks` (cli.py:1336-1357) iterates those handles verbatim.
- `cli.py:1591-1592` — `dropped = f", {len(s.excluded_files)} dropped"` on the
  `recording:` line: again the whole list.
- `gather.py:873-875` appends `{"filename": …, "reasons": ["operator-excluded"], …}`
  into that same `excluded` list, so both surfaces do carry operator drops.
- `CLAUDE.md` checked for the same claim: it makes none — it never describes the
  `excluded (N):` listing or the `dropped` count, and it already states
  "`--include` on an `operator-excluded` row un-excludes instead" (CLAUDE.md:211),
  which is the routing `cli.py:2546-2551` implements. Nothing to correct there.

### Finding 2 — the hint line
`docs/workflow.md:639` now says "includes an `excluded (N):` section" (the "ends with"
claim is gone) and `:643-645` says the section "is followed by a re-admit hint".
`docs/workflow.md:652` documents the line as
`  re-admit one with: llama fix <show> --include x1`.

Rendered against the real code (imported `llama.cli._format_tracks` /
`_excluded_handles` with a stub Show carrying the doc's three excluded entries):

```
'excluded (3):'
'   x1    0:37  dm1969-08-08t13.mp3  implausibly short'
'   x2    1:12  FOLLOW-ME @BYPIKENO.mp3  filename convention mismatch'
'   x3    4:02  dm1969-08-08t07.mp3  duplicate-listing'
'  re-admit one with: llama fix <show> --include x1'
```

Byte-for-byte identical to `docs/workflow.md:648-652`, including the two-space
indent on the hint. The hint's source is `cli.py:1635-1638`:
`f"  re-admit one with: llama fix {entry.slug} --include {handles[0][0]}"` — it
interpolates `entry.slug` (the doc block uses `<show>`, the same placeholder the
section's own `llama show <show> --tracks` uses two lines above, so the substitution
is consistent with the surrounding convention) and the FIRST handle, `x1`, which is
what the doc prints.

### Finding 3 — ragged rewrap
The paragraph at `docs/workflow.md:604-625` is rewrapped: max line width in
604-666 is 76 columns (measured with awk); the 83-column line and the one-word
`track.` line are both gone (`:621-623` now reads "…An explicit / `--set-title
N=\"...\"` on the same invocation always wins over the proposal / for that track.").
The one >78-column line in the range (`:668`, 89 cols) is the pre-existing
`### llama redo …` heading, untouched by this diff.

### Finding 4 — "ships that TRACK twice" + spec appendix
`docs/workflow.md:663-665`: "re-admitting a `duplicate-listing` row will ship that
track twice — it's one file listed twice on the archive.org item, not the whole
recording." Accurate against `junk._dedupe_duplicate_listings` (junk.py:146-158):
"Some archive.org items list every track twice — once at top level, once under an
`<identifier>/` directory prefix".

Spec: `git diff --numstat 0946d6a..f31cf50` shows `6  0` for
`docs/superpowers/specs/2026-09-07-overrides-include-design.md` — six additions, zero
deletions, so every approved section is byte-identical. The added entry is a fourth
bullet appended to the existing `## Corrections made during implementation
(2026-09-07)` list (numbered `4.`, following `3.`), and it states the correction
accurately.

### Finding 5 — `--include` redoes from `gather`
`CLAUDE.md:203-205`: "`--include xN|FILE` (`overrides.include`), which re-admits a
file the junk filter dropped **and redoes from `gather` like the other two**".
True in code: `cli.py:2516` sets `did_files = bool(exclude or unexclude or include)`
and `cli.py:2600` picks `stage = "gather" if (did_files or did_meta) else …`.

### Regression spot-checks (previously-verified content)
- Excluded-row example reproduces byte-for-byte from the `_format_tracks` format
  string `  {handle:>3s}  {duration:>6s}  {filename}  {reasons}` + `.rstrip()` —
  see the render above (`x3` row ends after the reason; column order duration-then-
  filename preserved).
- `+` legend: `cli.py:1334` emits `  + = ruled in by the operator (overrides.include)`;
  `docs/workflow.md:658-659` still describes the `+` and its own legend line.
- Three-flag `--suggest-titles` refusal: `cli.py:2448` guards on
  `if exclude or unexclude or include:` and `cli.py:2464-2469` names all three flags,
  echoing the flag the operator actually typed. `docs/workflow.md:614-621` still
  documents the three-flag refusal, the renumbering rationale, the
  "run the file edit first, not staged with `--no-run`" remedy, and the stale-
  `show.json` refusal.
- CLAUDE.md's `filter_files` placement claim (CLAUDE.md:205-209 — after the junk arms,
  after duplicate-listing dedupe, before play-order derivation, filename-order
  consequence) matches `junk.py:236-258` comment and code exactly.
- Junk constants unmoved: `junk.py:66` `SHORT_FRACTION_OF_MEDIAN = 0.25`, `:69`
  `MIN_MEDIAN_SAMPLE = 5`, `:70` `MIN_PLAUSIBLE_SEC = 90.0` — and no `.py` appears in
  the diff at all, so they could not have moved. The docs still say plainly that the
  feature exists so they need not move: `README.md:193-194` ("the junk thresholds are
  measured and stay put, so a wrongly-dropped track is fixed per show, not by
  loosening the filter") and `CLAUDE.md:211-212` ("**Do not loosen the junk constants
  instead** — this override is why they stay put").

### Diff scope
`git diff --name-only 0946d6a..f31cf50` → `CLAUDE.md`, `README.md`,
`docs/superpowers/specs/2026-09-07-overrides-include-design.md`, `docs/workflow.md`.
Zero `.py` files. Working tree clean (`git status --porcelain` empty); nothing
committed or modified by this review. Suite not re-run: a docs-only diff cannot move
1964 passed / 7 deselected, and no reading raised a doubt an existing run does not
answer.

## New breakage in the fix diff
None.

## Out-of-scope observations (deferrable, non-blocking)
1. `cli._excluded_handles`'s docstring (cli.py:1293) still says "`x`-handles for the
   **junk-filtered** files" — the same narrowing finding 1 corrected in the docs, now
   surviving only in source. Cosmetic; Task 5 may not touch `.py`.
2. `--include`'s `--help` text (cli.py:2371) reads "Re-admit a file the junk filter
   dropped", which likewise omits the `operator-excluded` row it also handles. Same
   class, same reason it is out of scope here.
