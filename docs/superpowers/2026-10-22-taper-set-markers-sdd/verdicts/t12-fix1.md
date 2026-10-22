# t12-fix1 handback: fix round 1 for the Checkpoint A round (t12-r2)

**Status: DONE.** Both Important findings are fixed, plus one follow-up the probe turned up.
The full suite passes: **4326 passed, 1 skipped**. HEAD is c7eb3b0 and the tree is clean.
`setlist.py` and the protected names are untouched.

## Commits
| commit | what | suite |
|---|---|---|
| 930b3ac | finding 1: comma-kept items' parts count in placement | 4325 passed |
| 89db381 | finding 2 / ruling R8: `...` dropped; ruling attributions made exact | 4325 |
| c7eb3b0 | finding 1 follow-up: a comma inside a bracketed credit is no part separator | 4326 |

Each was run as `./.venv/bin/python -m pytest -q`. I also ran
`./.venv/bin/python -m pytest packages/llama/tests/test_taper.py scripts/test_taper_probe.py -q`,
which gives 279 passed.

## Finding 1: a comma-kept line can merge two songs
**Fix (taper.py only).** `_comma_parts(title)` splits an item on commas outside brackets.
Every comma left in an item is one the comma rule kept. In `_place_boundary` I chose both
options the review offered, so the taper owns as little as possible:
- **(A) Parts count as songs of their side.** Each comma part is added to `left_norms` and
  `right_norms`. Those lists feed the "also occurs on the other side" check (the boundary
  item's own parts are compared too) and the merged-span check.
- **(B) A later part on the tape declines.** If a boundary item's later comma part matches
  another track, or a component of the item's own merged track, the boundary declines:
  `comma-joined '<item>' names a second song on the tape`.

**Tests** (all RED before the fix except the single-title pin, which already owned):
- `test_comma_merged_boundary_item_never_moves_a_break`. This is the constructed case:
  `Jack Straw, Ripple` / Set 2 on the tape `…, Jack Straw, Ripple > Scarlet Begonias, Fire…`.
  It now declines; before the fix it owned and labelled Ripple as set 2.
- `test_comma_merged_boundary_item_on_separate_tracks_declines`. With Ripple on its own
  track, the boundary now declines through (B). 3d1c1e7 owned this case correctly, and the
  fix deliberately does not restore that. To own it, the reader would have to decide which
  comma part closes the set, which is the one-title question the comma rule cannot answer
  (CLAUDE.md's A2: there is no clean discriminator). Declining is the own-less choice.
- `test_comma_part_counts_for_the_other_side_check`. The item `Jam, Drums` sits on set 1's side
  and `Drums` opens set 2, so the boundary is unplaced. Before the fix the merged item hid it.
- `test_single_title_comma_boundary_item_still_owns`. This is the real case
  jackiegreene-2010-12-31: `09. Farewll, solong, Goodby` closes set 1 and still owns (9,).
- `test_comma_inside_parentheses_is_no_song_separator` (the follow-up).

**Follow-up (c7eb3b0).** The first gate3 run showed one new library decline:
joerussosalmostdead-2015-05-09. Its credits `(SM, NA)` and `(SM,NA)` sit on opposite sides of
the break, so the part `NA)` looked like a title repeated across it. Commas inside brackets
no longer split parts, and gate3 was re-run.

## Finding 2 (controller ruling R8, with the parent's attribution amendment)
**Code.** `...`/`…` are dropped from `_ANNOT`, and from the probe's annotation count, whose
label is now `rule: header + (duration|time) (ruling b)`.

**Deliberate pin change.** `Disc 1 - Set I...` / `Disc 2 - Set II...` and `Set 1...` /
`Set 2…` are no longer headers. The pair was removed from
`test_annotated_headers_are_headers`, and `test_trailing_dots_are_not_an_annotation` pins the
new behaviour. The commit message says so.

**Wording.** These places were reworded: spec §1 and §2, the plan's Global Constraints
"Recognised forms" bullet and Task 2 Step 3, and the taper.py docstring and comments
(`_ANNOT`, `_DISC_SET_HEADER`, `_SET_DISC_HEADER`, `decide_taper`).
- **Operator sentences.** Each "Operator ruling 2026-10-22 (Checkpoint A):" sentence now says
  only what was ruled:
  - (b): a recognised header followed by a trailing `(duration|time)` annotation is that header.
  - (c): admit the disc-and-set shapes cpa-decl listed, each carrying `Set` or an ordinal set.
    The list no longer includes `Disc 1, Set 1`.
  - (d): as ruled, "an encore boundary after the taper's last placed numbered break"; "this
    only turns ownership off; no merge".
- **"(llama-db reading of operator ruling (c), 2026-10-22: …)":**
  - Disc/Disk/CD are interchangeable, including in `Disc N (Set M)`, `Disc N - Set M` and
    `Disc N / Set M`.
  - The `Disc 1, Set 1` and `Set 1-Disk 1` joins are admitted.
- **"(llama-db reading of operator ruling (d), 2026-10-22: …)":** the rule is read as an
  `encore` label on any track after the last placed break (`today_sets[boundaries[-1]:]`).
- **"(My call: …)":** `_ANNOT` accepts a `~` range join and a `?` after a time.
- **Other limits.** "Must directly follow the header token" is stated as a plain constraint,
  and so is "a trailing `...` is not an annotation".

## Probe: gate3 (`~/.llama-harness/piece2/gate3/`, from c7eb3b0)
These are verbatim from gate3's summaries:
- in-scope rows: 186, identical to gate2 (`identical set: True`)
- ownership ratio: 77/186 = 0.414
- target match rate: 42/54 = 0.778 (53/54 = 0.981 counting filler-only); misses: 1
  (darkstarorchestra-2007-05-17)
- owned renum rows: 8; owned rows with no target: 15
- library: 3522 evaluated, 648 taper-owned (554 identical to stored, 94 differ)
- library tiers: songs moved 35, labels renamed 0, encore folded 0, encore added 31,
  sets merged 5, sets split 22, filler only 1
- numbered-set count decreased: the same 10 rows as gate2

**Delta gate2 → gate3 (`gate3/delta_summary.txt`):** 0 flips anywhere. That covers in-scope
gate rows, all yes/partial gate rows and the library: 0 newly owned, 0 newly not owned, and 0
owned rows with changed labels. Dropping `...` and adding the comma-part checks change no
decision the probe sees. In the first gate3 run, before c7eb3b0, the only flip was
joerussosalmostdead-2015-05-09, which became not owned (`unplaced: 1|2 'Music Never Stopped
(SM,NA)' also occurs on the other side`); the follow-up removed it. I did not re-run `forms`
in this round.

## Not addressed (review Minors, not in this round's brief)
1. `Set I (Disc 1)` is still excluded, and the test comment still says "not in the ruling's
   list".
2. The (d) `+1` index mutant still survives: there is no test where today's encore is the
   single track right after the last break.
3. Double-numbered lines such as `02. 02 FRIEND OF THE DEVIL` keep the second number.
4. The `_split_set_and_encore` shape test strips `_NUM_PREFIX` unconditionally, while `_scan`
   strips it only on enumerated text.
5. Header-rest junk such as `disc 1 - Bertha` still survives.

All five only make the taper own less, or are wording.
