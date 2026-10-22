### Finding Verdicts
- **Finding 1: double track-prefix strip on song lines.** ADDRESSED. In `taper.py` `_scan`, a song line now sets `rest = line` (the unstripped line), so `_song_titles` (taper.py:~251-256) does the one `_TRACK_PREFIX`/`_NUM_PREFIX` strip. That is the same transform that builds `core`, so the titles equal the old single-strip `core`, and marker classification still runs on `core`. Marker rests (`_classify`'s `rest` group) are unchanged and still get exactly one strip. The cross-check in `read_taper_structure` compares labels only (`parse_setlist(text).items` sets against `own`), so the change cannot move it. The new test `test_enumerated_digit_leading_title_keeps_its_number` asserts `titles(tt) == parse_setlist`'s titles. I checked that the text really is enumerated (`_enumerated_prefix` returns True) and that the reader gives `100 Years`/`72 (This Highway's Mean)` labelled 1/2. `git diff main -- packages/llama/src/llama/setlist.py` is still empty (0 lines).
- **Finding 2: widen the encore-like veto input (R4).**
  - (a) bare `E`/`E<digit>`/`ENC` split item: ADDRESSED. `_ENCORE_LIKE_ITEM` is applied to each `_split_songs` item after `.strip(_ITEM_DECOR)` in `_encore_like`. Tests: `test_encore_like_bare_e_item` (a real gd1985-03-31 sibling excerpt; it pins that `E` stays a set-2 item and `has_encore` stays False) and `test_encore_like_bare_e_item_forms`.
  - (b) trailing ` E`/` (E)`/` [E]`/`, E`: ADDRESSED. `_ENCORE_LIKE_END = \s(?:e|\(e\)|\[e\])$|,\s*e$` (re.I). Tests: `test_encore_like_trailing_e_on_a_song_line` (the real ymsb2007-10-05 text), `test_encore_like_trailing_e_forms`, and `test_encore_like_trailing_e_collateral_is_accepted` (`D to E` pinned True, still asserts, label 2).
  - (c) own-line `[E]`: ADDRESSED. It is caught by the item rule once decoration is stripped. The `test_title_lookalikes_are_not_markers` pin was changed on purpose: it gained an `encore_like` column with `[E]` True, and the line is still no marker and still a set-1 title.
  - (d) line-start test after an unconditional `^\d{1,3}\s+` strip: ADDRESSED. `_LEADING_NUMBER` is used in `_encore_like`. Test: `test_encore_like_line_start_after_a_bare_track_number`.
  - Negatives: ADDRESSED. `test_encore_like_new_rules_negatives` covers `E-Bow the Letter`, a clean two-set text and DTB_2006_01_25. The lookalike table also pins `B. E. Women`, `J` and `Untitled #12` False.
  - Docstring: ADDRESSED. The module docstring (now `r"""`) lists every veto rule and the three own-less voids: continuation without its header, an empty trailing set, and a filler-only set counting as empty.
  - `has_encore` is unchanged by every new rule: `_encore_like` only sets `s.encore_like`.

### New Breakage in the Fix Diff
None.
- Do the new rules fire on a recognised marker line? Not on the marker itself. For marker lines, `_encore_like` sees only `_classify`'s `rest` group, the song text after the header. Probes: `E: C` and an own-line `Encore` both give `encore_like False`, and the existing `ACOUSTIC_SYNDICATE` pin stays False.
- Library collateral (a read-only probe over `~/.llama/cache/md_*.json` through `taper_text_for`, with the probe run logged to `$D/t1-rr1/t1-rr1.log`):
  - 2194 texts assert with no encore marker.
  - Only 7 of them have `encore_like` raised by the new rules alone.
  - 5 of the 7 are gd1985-03-31 siblings (`Day Tripper, E`), 1 is ymsb2007-10-05 (`Traffic Jam E`), 1 is mogwai2001-06-16 (`1. D to E`, the accepted collateral) and 1 is jrad2021-10-23 (`E;`, plausibly a real encore cue).
  - None of the 7 came from a marker rest.
  - Every flip moves toward owning less.

### Out-of-Scope Observations
- Minor, non-blocking: on a marker line's rest, all the R4 rules now apply, not only the words rule. This is consistent with the docstring ("on the song text after a marker") and the spec's "outside a recognised marker". It is slightly broader than R4's literal "outside recognised marker lines". It also raises `encore_like` beside a real encore (`Encore: US Blues (E)` gives has_encore True, encore_like True), which does nothing when the veto only matters without an encore marker. It changed 0 library texts in the probe, and it errs only toward the taper owning less.
- The implementer's own note stands: a set header behind a leading timestamp (`(103:53) 2nd set`) is still no marker, an own-less outcome.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage.
