# t1-impl handback: Task 1, `read_taper_structure` / `taper_text_for`

**Status: DONE_WITH_CONCERNS** (the concerns are about the brief and the spec, not failing work)

Commit: `f46da71 feat(taper): structure-only reader of the taper's set/encore markers` (single commit, branch `held-backlog-taper-markers`).

## What I implemented
`packages/llama/src/llama/taper.py` (new):
- `TaperItem` and `TaperText`, frozen dataclasses with exactly the brief's fields. No fields added.
- `read_taper_structure(text)`:
  - Preprocessing as `parse_setlist` does it (`<br>` and tags become newlines, then `html.unescape`), with no truncation, then `_INLINE_MARKER`'s split exactly as `_emit_items` does it.
  - On each line it strips `_TRACK_PREFIX`, plus `_NUM_PREFIX` when `_enumerated_prefix` holds, and then classifies the line as a numbered header, an encore header, or a song line.
  - Song lines go through `_NOISE`, `_split_songs`, `MAX_TITLE_LEN`, `is_junk_title`, the leading-timestamp strip, the timestamp-only drop and the bare-number line drop. `is_filler` items are excluded.
  - It applies the section 2 sequence and void rules and the set 4+ void.
  - Last comes the cross-check: if `parse_setlist(text)` has a label that the reader's structure (`1..n` plus `encore`) lacks, the result is `asserts=False` with `reason="cross-check: <labels>"`.
- `taper_text_for(meta)` returns the description when it has any recognised marker, else the notes when they have one, else `("", "none")`. A list field is joined with `\n`.
- Reason strings:
  - `"no markers"`
  - `"one set"` (fewer than two numbered sets, including encore-only text)
  - `"void: set 4 or higher"`
  - `"void: decreasing set number"`
  - `"void: skipped set number"`
  - `"void: empty set"`
  - `"void: numbered marker after the encore"`
  - `"void: continuation without its set's header"`
  - `"cross-check: <label[, label]>"`
  - `None`
- `git diff main -- packages/llama/src/llama/setlist.py` is empty, and no protected name was edited. `taper.py` imports `structure.is_filler` and setlist's helpers and uses them unchanged.

## Tests and results
`packages/llama/tests/test_taper.py`, 74 tests. It covers every bullet of the brief plus gap-closers. Real-case literals were copied verbatim from `~/.llama/cache/md_<identifier>.json` by a script, never by hand. Each one cites the slug and the cache file, and "excerpt" marks a contiguous slice. The pins (`test_parse_setlist_unchanged`, 3 excerpts: TTB, GD 1990-03-22, PAF) were generated with `/Users/shawn/projects/llama/.claude/worktrees/taper-base/.venv/bin/python`, after asserting that `llama.__file__` resolved in taper-base (main @ a26c4d1).

- **RED**: run in a scratch `git archive` copy with no `taper.py`, using `PYTHONPATH=<scratch>/packages/llama/src`, after checking that `llama.__file__` resolved in the scratch copy. The command was `./.venv/bin/python -m pytest packages/llama/tests/test_taper.py -q`. Output: `E   ModuleNotFoundError: No module named 'llama.taper'`, `1 error in 0.22s`.
- **GREEN**: `./.venv/bin/python -m pytest packages/llama/tests/test_taper.py -q` gave `74 passed in 0.26s`.
- **Full suite**: `./.venv/bin/python -m pytest -q` gave `4121 passed, 1 skipped, 8 deselected`. That is 4047 + 74.
- TDD caveat: I drafted `taper.py` before the test file, and captured RED afterwards by running the finished tests against a tree without the module. RED is still a genuine collection failure, but the order was not strictly test-first.
- **Mutation pass**: 23 mutants, each in its own scratch copy, run from the scratch cwd with `PYTHONDONTWRITEBYTECODE=1`. Each mutant's `llama.taper.__file__` was verified to be inside its copy. The expected red test was named before each run.
  - 22 were CAUGHT by the predicted test.
  - M1 survived: removing `(?!\w)` after the set token. It is near-equivalent, because every header must match the whole line and no tail can begin with a word character, so `Set Intro`, `Set IV` and `Set 12` already fail on their tails. The bound only matters for a glued `Set2cont`, and there a continuation changes no label either way. I kept the bound as the literal form of the spec's "word-bounded".
  - The log is in `t1-impl.log`.

## Files changed
- `packages/llama/src/llama/taper.py` (new)
- `packages/llama/tests/test_taper.py` (new)

## Judgment calls (regexes and forms)
1. **Decoration set** is `[-–—*~=\[\]()\s]` and nothing else (the spec's list). Braces, `#` and `.` are not decoration. As a result `~Set 1~ {1hr:59min:22sec}` (moe 2002-06-22 akg481) is not a header.
2. **Bare `E`/`E1`/`ENC` forms take no bracket or parenthesis decoration** on either side. The spec names `(E)` as a non-marker, and the evidence names `[E]`; pinned. The worded `Encore` forms do take full decoration, so own-line `(encore)`, `~Encore~` and `-Encore-` are markers. This matches the brief's own-line `(Set 2)`.
3. **A dash separator must be followed by whitespace or the line end**, like `_ENCORE_LINE`'s `-\s`. Without that, `E-Bow the Letter` would be an encore line; pinned.
4. **A header must be alone, or followed by `:`/dash and songs.** `Set 1 Bertha` with no separator is not a header (`_SET_LINE` would read it), and the cross-check then refuses any such text. `Set 2: (2:33:33)` is a header whose rest is a timestamp-only item, which is dropped.
5. **Continuation suffix** `cont`/`cont.`/`cont'd`/`continued`, optionally `(…)`-wrapped or after a comma. The spec names `Set 2 cont.` and `Set 2 continued` explicitly as lines that assert nothing, so they have to be recognised or they would become song items. A continuation whose number is not the current set (e.g. `Set 2 cont.` straight after set 1, or as the first marker) gives `void: continuation without its set's header`. I chose that rather than guessing where the unmarked set began (own less).
6. **Set-and-encore** (`+`, `&`, `/`, `,` or `and` followed by `Encore[s]`, after a set token) is recognised and changes no label. **I also count such a line as encore-like.** It names an encore it does not start, so if no real encore marker follows, the veto fires rather than folding the encore into the last set (own less). After an encore marker it voids, like any numbered marker.
7. **Disc forms** are exactly `Disc N (Set M)`, `Disc N - Set M` and `Disc N / Set M` (N is a digit or `one`–`six`/`i`–`iv`), with any trailing `:`/songs. **Not recognised**, because they are not on the list:
   - `Disc 1: Set 1` (colon)
   - `disc 01 [Set I]` (brackets)
   - `CD2 Set 2`
   - `Set 02` (leading zero)
   - `Set One (8:20PM - 9:45PM):`

   All of these make the taper own less. Measurement 5 may want to look at them.
8. **Empty set**: any started set (numbered, or the encore) with zero non-filler song items when the next set starts, or at the end of the text, voids. This covers a trailing `Encore:` with nothing after it, which the spec's "a header followed directly by another header" does not literally cover (own less). Filler-only sets count as empty.
9. **Leading block**:
   - When the first numbered marker is set 2 and the block holds songs, the block becomes set 1.
   - When the first numbered marker is set 1, the block is discarded.
   - If set 2 comes first with an empty block, or set 3 comes first, the result is `void: skipped set number`.
   - With no numbered marker at all, the items are labelled `"1"` (they must carry some label, and `asserts` is False).
10. **Set 4+** is matched anywhere in the text, prose included: `set` + 4–9 / multi-digit / `four`–`ten` / `iv`–`x`, `4th`–`19th set`, `fourth`–`tenth set`. A prose `the 4th set …` voids (own less). It also counts as "a recognised marker" for `taper_text_for`, so the description wins and then voids.
11. **Bare-number line drop** is `^\d{1,3}[.:)]?$`, slightly wider than the spec's `\d{1,3}:?`. It also drops the `18.`/`3.`/`9:`/`11` stubs that the inline split leaves in front of `E:`. Line level only, never item level.
12. **encore_like** is checked on every non-marker line, including `_NOISE` lines and prose such as `No encore performed`, and on the song "rest" of marker lines (`Set 2: …, Ripple (Encore)`). Recognised marker lines themselves are excluded.
13. **Cross-check** compares `parse_setlist` labels with the reader's structure labels (`{"1".."n"} ∪ {"encore" if has_encore}`). It runs only when nothing earlier refused.

## Self-review findings
- The brief's lotus claim does not hold on the real text (see concern 1). I tested what the real text gives and what the spec actually claims for it: the set-and-encore line changes no label, and the later marker starts the encore.
- `TaperText` keeps the brief's exact shape. `taper_text_for` uses a private `_scan` for "has any marker", so no field was added to the fixed interface.
- `parse_setlist` runs once per `read_taper_structure` call, and `taper_text_for` scans each text once more. That is cheap.

## Concerns
1. **`lotus-2005-10-15` (`lotus2005-10-15.481`, the selected recording)**:
   - What the text has:
     - The set-and-encore disc line is `~Disc 1: Set 1+Encore~`, the colon form, which is not a recognised form.
     - The later marker is a bare `Encore`, not `e:`.
     - `~Disc 2: Set 2~` (colon) comes after it. That form is not recognised either, and if it were, it would void as a numbered marker after the encore.
   - So the brief's "`asserts`" cannot hold. The reader gives `asserts=False`, `reason="one set"`, `has_encore=True`, `Nematode` labelled encore, and the test pins that.
   - The spec's own sentence (the line asserts nothing and the later marker still starts the encore) does hold.
   - The other lotus recording in the cache (`…dfc.stage-lip…`) is not the selected one.
2. **Excerpt substitutions** (the brief's form text could not be found in the named show's selected recording):
   - `antibalasmusic-2003-04-28`: the selected recording `antibalas2003-04-28` says only "Setlist unavailable". The `[1]…[5]` text is in the sibling `Antibalas2003-04-28.SBD`, which I used and cite.
   - `moe-2002-06-22`: the `[1]` footnotes are in the sibling `moe2002-06-22.akg481.dmic20.d8.flac16`, not the selected `km140`.
   - `gd1981-10-16`: "Set I is Bobby …" is in the `tobin` siblings, not the selected `sbd.miller.110351`. On that text, `parse_setlist` numbers `Acoustic Set`/`Electric Set` as labelled sets 2 and 3, so the reader ends at `cross-check: 3`. The pinned fact is that the line is a set-2 song, not a marker.
   - `3. Encore: Higgins` was not found anywhere in the cache. I used the real `3. E: Higgins` (`um2005-09-14.flac16`, umphreysmcgee-2005-09-14) plus a synthetic `3. Encore: Higgins`.
   - The `Encore #1` case is from `tsp2007-07-16.dpa4061.mt.flac16` (The Smashing Pumpkins, not in the library).
   - `(2:33:33)` is from `dso2018-07-08.r1.spyder9.flac16`, a sibling of darkstarorchestra-2018-07-08.
   - `-04:41.50- Right in Tune` is from railroadearth-2009-01-15's `notes`.
   - The DSO 2004-04-20, 2005-12-03 and 2004-04-24 texts contain only `Encore:` (no `Set 2:`), so they assert nothing (`one set`). Only 2005-11-16 asserts.
3. **The spec's source rule has a visible cost**:
   - `railroadearth-2009-01-15`'s description has an inline `17 E: "Happy Birthday Jen"`, which counts as a recognised (encore) marker.
   - So the description is read, and the notes' full `Set One:`/`Set Two:` structure is never consulted. The show then asserts nothing.
   - This is the literal spec rule ("any recognised marker"); pinned in `test_taper_text_for_real_cases`. Flagging it in case "explicit marker" was meant to mean a numbered one.
4. **Residual junk items that make placement fail (own less, never wrong)**:
   - `N - e: …` leaves a `-` item (`7 -`, then `_NUM_PREFIX`). In PAF it sits as set 2's last item.
   - `~Set 1~ {duration}` headers become song items.

   These are for Task 2 and 3's measurement to weigh. Titles are unchanged from `parse_setlist`'s own cleaning, apart from the spec-mandated timestamp strip.
5. Unrecognised forms seen in the evidence: `Disc N: Set M`, `disc 01 [Set I]`, `CD2 Set 2`, `Set 02`, `Set2cont`, and a header followed by a parenthesised clock time. They are left out per "exactly section 1's list".

---

# t1-fix1 handback: Task 1 fix round 1

**Status: DONE.** Commit `1467961 fix(taper): single track-prefix strip; widen the encore-like veto input`.

## What changed
1. **Finding 1 (double track-prefix strip).**
   - The bug: `_scan` passed a song line's already-stripped `core` to `_song_titles`, which stripped `_TRACK_PREFIX`/`_NUM_PREFIX` a second time.
   - The fix: a song line now passes the unstripped `line` as `rest`, so `_song_titles` does the single strip, exactly as `_emit_items` does it. Marker classification still tests the stripped `core`, and marker rests keep their single strip.
   - Sweep: over 15,376 cached descriptions (read-only), no reader title is a digit-truncated `parse_setlist` title any more. The 16 texts that still differ from `parse_setlist` all differ by the spec-mandated leading-timestamp strip (`[03:47]  51 Phantom` gives `51 Phantom`).
2. **Ruling R4: the encore-like veto input is widened.** It only raises `encore_like`, and `has_encore` is unchanged. Every rule is applied to song lines and to the song text after a marker, never to the marker itself. The work is in the new `_encore_like()`, which applies:
   - the existing `\bencores?\b`/`\benc\b` rule;
   - the existing `E.`/`E)`/`E<digit>`/`(E)` line-start rule, now also after an unconditional `^\d{1,3}\s+` strip (d);
   - a new rule for a line ending ` E`/` (E)`/` [E]`/`, E`, case-insensitive (b);
   - a new rule for any `_split_songs` item that is exactly `E`/`E<digit>`/`ENC` after stripping decoration `-–—*~=[]() \t` (a, and an own-line `[E]` or `(E)`, c).
3. **Module docstring** (now a raw docstring) documents the veto rules and the three own-less void rules: a continuation without its set's header, an empty trailing set, and a filler-only set counting as empty.
4. **Deliberate pin change** (stated in the commit): `test_title_lookalikes_are_not_markers` gained an `encore_like` column, and an own-line `[E]` now asserts `encore_like is True`. It is still no marker and still a set-1 title. The column also pins `E.Ville`, `E. Rutherford`, `(E)` and `E.` as True, and `B. E. Women`, `I Know You Rider`, `J`, `Untitled #12` and `E-Bow the Letter` as False.

## Covering tests (all in `packages/llama/tests/test_taper.py`)
| Test | Covers |
|---|---|
| `test_enumerated_digit_leading_title_keeps_its_number` | Finding 1. Titles equal `parse_setlist`'s; `02 100 Years` gives `100 Years` and `04 72 (This Highway's Mean)` keeps its number. |
| `test_encore_like_bare_e_item` | R4 (a), on a verbatim real excerpt from `md_gd1985-03-31.sonyecm220t.keshavan.miller.106791.flac16.json`, a sibling of gratefuldead-1985-03-31 (`... Day Tripper, E`). Pins that the item `E` stays a set-2 item. |
| `test_encore_like_bare_e_item_forms` | `E2`, `ENC`, `enc`, own-line `[E]`, `, e`. |
| `test_encore_like_trailing_e_on_a_song_line` | R4 (b), on a verbatim real excerpt from `md_ymsb2007-10-05.Analog_Nagra_Reel_to_Reel.flac.json` (`Traffic Jam E`). |
| `test_encore_like_trailing_e_forms` | `US Blues (E)`, `[E]`, ` E`, `,E`. |
| `test_encore_like_trailing_e_collateral_is_accepted` | `D to E` raises the flag; documented as accepted, own-less. |
| `test_encore_like_line_start_after_a_bare_track_number` | R4 (d): `14 E. Playin' Reprise` on a non-enumerated text. |
| `test_encore_like_new_rules_negatives` | `E-Bow the Letter`, a clean two-set text and DTB 2006-01-25 stay False. |

The `~E~` own-line case was dropped from the forms list: it is already a recognised decorated bare-`E` encore marker, so it starts the encore.

## TDD evidence
- **RED**: `./.venv/bin/python -m pytest packages/llama/tests/test_taper.py -q` gave `13 failed, 76 passed`. The failures were the `[E]` lookalike, the enumerated-title test, the bare-E item tests, the trailing-E tests, the collateral test and the leading-number test. (`ENC`/`enc` already passed through `\benc\b`.)
- **GREEN**: the same command gave `89 passed in 0.26s`.
- **Full suite**: `./.venv/bin/python -m pytest -q` gave `4136 passed, 1 skipped, 8 deselected`, which is 4121 + 15.
- `git diff main -- packages/llama/src/llama/setlist.py` is still empty.

## Concerns
- Rule (a) is redundant with `\benc\b` for `ENC`. It is harmless, and kept as the ruling states it.
- A header behind a leading timestamp (`(103:53) 2nd set`, RRE2014-11-28) is still not a marker, because the timestamp is stripped only from song text. That is an own-less outcome; noted, not changed.
