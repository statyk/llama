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
