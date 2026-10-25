# t22-seg handback: why de-doubling moves segue marks (read-only, HEAD 65be006)

## Verdicts
**Q1, mechanism.** FW1's rule is not what moves the marks. `align()` is not the cause either. The marks come from a pre-existing count-sensitive choice in `gather.build_canonical` (stages/gather.py:915-932). Two calls use `target_count=len(kept)`:
- `rank_parses(parses, target_count=len(kept))` picks the canonical. setlist.fm always wins when it exists, and `from_setlistfm` writes `segue=False` on every item.
- A second `rank_parses(<LMA parses only>, target_count=len(kept))` picks the **segue donor** for `blend_segues`. Its last tie-break is `-abs(len(items) - target_count)`, and `max()` keeps the first maximum, so the chosen recording wins ties. `blend_segues` (structure.py:575) then returns the winner UNCHANGED if that donor has no segue at all, and otherwise copies flags by exact `normalized` title.
- De-doubling halves `len(kept)`, so a different description becomes the donor. On 1987-06-30 (no setlist.fm entry) the canonical itself changes: GEMS (27 items) at target 50, the chosen run-on parse (25) at target 25.
- align() then copies `items[hit].segue` onto the matched tracks (structure.py:1047/1124). Doubled, every `_vbr` twin misses (coverage 0.39-0.50). That is why the two arms' coverages differ. It does not change the segues.
- Reproduced two ways under this tree (`llama.__file__` is inside the worktree):
  (a) `scripts/replay_holds.py run --slugs` for 1988-06-23 and 1990-03-16 gives clean-changed=2, segues equal to cand-c2;
  (b) a driver that toggles ONLY `junk._dedupe_derivatives` (a no-op patch, in memory) reproduces cand-c's segues exactly and cand-c2's segues exactly, for all 9 shows (18/18 arm-rows OK). So the dedupe alone causes the change; nothing else between a693878 and HEAD does.
- The two named shows:
  - **1988-06-23**: setlist.fm wins (21 items, 0 segues). Donor at target 38 is `lma:...127253.shureSM57.chuckm` (24 items, 11 segues); 7 marks. Donor at target 19 is `chosen` (20 items, |20-19|=1, and it wins the tie against the 20-item terrapin-flyer). The chosen description is a bare numbered list with no `>` anywhere, so blend returns setlist.fm as is: 0 marks. Jerrybase anchoring places the breaks in both arms, so set labels and breaks are unaffected.
  - **1990-03-16**: the reverse. Donor at target 40 is `senn-hubbard.cpb.83791` (23 items, **0 segues**), so there are no marks. Donor at target 20 is `132660.mtx.tobin` (20 items, 8 segues), so 8 marks are gained.

**Q2, which arm is right.** Song level, 33 changed marks over 9 shows (21 gained, 12 lost). Judged by the description vote (each description parse aligned to the de-doubled tracks), the chosen description, and the track's own `>`/`->` tag.
- The de-doubled arm is right on 18: 15 real marks gained and 3 false marks removed.
- It is wrong on 9: 1 false mark added and 8 real marks lost.
- 6 are unclear. In those the selected taper's own tag or description says segue and most siblings say not, or the reverse.
- The biggest single regression is **1988-06-23: it loses 5 real marks** (He's Gone, Drums, Space, I Need A Miracle and Watchtower, 8/9 to 8/8 of descriptions). This is a delivered show, so a re-process would ship it with no segues at all.
- Doubled arm caveat: even its "right" marks sit on the X copy, whose next track is its own `_vbr` twin. The shipped doubled manifest says "Bird Song > Bird Song", and the twin into the next song is unmarked.

**Q3, defect or not.** It is not a defect of FW1. FW1 makes `len(kept)` the true count. The doubled count was steering the donor and canonical ranking arbitrarily, sometimes toward a description with segues (1988-06-23) and sometimes away from one (1990-03-16). Net, de-doubled is better (18 vs 9). Every regression is pre-existing behaviour that any tape with that file count already hits. It is not something alignment hid. Three pre-existing classes:
- **(A) No-segue donor** (1988-06-23). Smallest fix, in gather.py:930: rank the donor only among LMA parses that carry a segue:
  `rank_parses([p for p in parses if p.source != "setlist.fm" and any(i.segue for i in p.parsed.items)], target_count=len(kept))`.
  Tested **in memory only** (fixtest.py; no file changed). On 1988-06-23 it restores 4 of the 5 real marks; Space is still missed because the new donor, terrapin-flyer, lacks it. The description-majority score goes from 11/16 to 15/16. It changes nothing on the other 8 de-doubled shows. Its library-wide effect is **unmeasured**: run a replay arm before adopting it. Not implemented.
- **(B) Run-on chosen description** (1987-06-30 `Don't Ease Me In Scarlet Begonias->`; 1990-07-14 `Take A Step Back Tuning % ~ Eyes Of The World ->`). This is parse_setlist's documented merge defect (CLAUDE.md "items are NOT a reliable oracle"). No small fix belongs in this branch.
- **(C) `blend_segues` pools by exact `normalized`** (1991-06-25: setlist.fm `Space` against the donor's `Jam`). It lacks align()'s Space/Jam rule. A one-line alias in the pool would fix it, but that is a separate change.

**Q4, the other differences** (all one root: the doubled list double-counted, or doubled copies were ambiguous; de-doubled is correct in each case):
- **1972-11-18, +15 unknown-song flags.** Vet 4a `right_show_gate` (vet_research.py:185) needs `len(unknown) <= len(asserted)`, and `asserted` counts TRACKS. Doubled: asserted=16 (every song twice) against unknown=15, so the gate held and the flags were demoted to a note. De-doubled: asserted=9 against 15, so the gate fails and the flags surface. The tape is 9 songs in 1 set, where jerrybase has 2 sets, so the research naming 15 songs that are not on the tape is accurate. Needs-LLM in both arms. The closer flag changes from UJB to OMSN for the same reason: closer_contradictions skips a closer that matches more than one track. Doubled OMSN had two identical copies, so it was skipped. Doubled UJB had one exact match, because the `_vbr` tag reads `John\'s`, and that match was not the last track, so it was flagged. De-doubled, UJB is the last track (no flag) and OMSN matches once (flagged).
- **1990-07-14.** Doubled coverage was 0.474, below the threshold with no anchoring, so the low-confidence flag was raised and `align_structure` was needed. De-doubled coverage is 0.947, so neither applies. OMSN matched twice when doubled, which made it ambiguous and silent. Now it matches once (track 7), is followed by `Take A Step Back` (not `is_filler`) still labelled set 1, and is flagged. The flag is pre-existing behaviour, now unmasked. It is arguably a cosmetic hold, since the break is off by one speech track. Still needs-LLM, because the stored alignment is `llm`.
- **1989-07-18.** Coverage went from 0.5 to 1.0, so the low-confidence flag and `align_structure` are gone. Still needs-LLM, because the stored alignment is `llm`.
- **14 shows, briefing reuse to fresh.** `replay.briefing_reusable` refuses on `"tracks differ"`, because the stored filename list is the doubled one. This is correct by construction. The cost is 14 fresh brief calls on apply.

## Per-show table (song level; c = doubled cand-c, c2 = de-doubled; vote = description parses marking it / matching it; own = the chosen description's mark plus the tape's own track tag)
| show | change (c -> c2) | vote | own desc / tag | verdict |
|---|---|---|---|---|
| 1973-10-29 | +Promised Land > | 6/6 | yes / `>` | right |
| 1974-09-11 | +Seastones-> | 2/2 | - / `->` | right |
| 1974-09-11 | +Wharf Rat | 3/9 | yes / none | unclear |
| 1974-09-11 | +Goin' Down The Road > | 3/8 | yes / `>` | unclear (taper's tag) |
| 1987-06-30 | +Don't Ease Me In (set-1 closer) | 2/8 | run-on merge / none | WRONG (false) |
| 1987-06-30 | -Scarlet Begonias > | 7/9 | merge lost it / `>` | WRONG (lost) |
| 1987-06-30 | +Drums >, +Space > | 9/9, 9/9 | yes / `>` | right x2 |
| 1987-07-06 | +Stagger Lee> | 1/10 | no / `>` | unclear (own tag only) |
| 1988-03-27 | +Ballad of a Thin Man ->, +To Lay Me Down -> | 3/16, 3/16 | yes / `->` | unclear x2 (taper's notation) |
| 1988-03-27 | -Fire on the Mountain | 15/17 | no / none | unclear (taper says no, siblings yes) |
| 1988-06-23 | -Bird Song, -Believe It Or Not | 1/9, 1/9 | no / none | right x2 (false marks removed) |
| 1988-06-23 | -He's Gone, -Drums, -Space, -I Need A Miracle, -Watchtower | 8/9, 8/8, 8/8, 8/8, 8/8 | chosen has no notation | WRONG x5 (lost) |
| 1990-03-16 | +Scarlet, +Ship of Fools, +Man Smart, +Jam, +Drums, +Space, +Other One, +Stella Blue | 17/18 to 18/19 (Man Smart 8/14) | yes (mostly) | right x8 |
| 1990-07-14 | -Eyes Of The World -> | 22/25 | run-on merge / `->` | WRONG (lost) |
| 1990-07-14 | +Throwing Stones ->, +The Last Time | 24/27, 15/29 | yes / `->`, yes | right x2 |
| 1991-06-25 | -Truckin' | 5/12 | no / none | right (follows taper) |
| 1991-06-25 | +Smokestack Lightning | 10/10 | yes | right |
| 1991-06-25 | -Space | 12/12 | donor writes `Jam` | WRONG (lost; class C) |

Totals: right 18, wrong 9 (1987-06-30 x2, 1988-06-23 x5, 1990-07-14 x1, 1991-06-25 x1), unclear 6. Description-majority agreement over the 179 voted tracks: doubled 153, de-doubled 156, de-doubled with fix (A) 160.

## Evidence (all under ~/.llama-harness/piece4/t22-seg/)
- `head2.json`: replay_holds run --slugs (1988-06-23, 1990-03-16) --rekey-overrides at HEAD.
- `driver.py`, `driver.txt`, `driver_out.json`: every rank_parses candidate, winner and blend result, both arms, 9 shows; reproduction checked against cand-c and cand-c2.
- `evidence.py`, `evidence.txt`, `evidence.json`: the per-track vote table (asserts the HEAD replay equals cand-c2).
- `flags.py`, `flags.txt`: Q4 coverage, flags, needs_llm and 4a gate inputs, both arms.
- `fixtest.py`, `fixtest.txt`, `fixtest.json`: fix (A) tested in memory, both arms.
- Code: stages/gather.py:877-937 (build_canonical), structure.py:532-589 (rank_parses, blend_segues), structure.py:1040-1131 (align segues), jerrybase.py:285-316 (closer ambiguity), vet_research.py:185-224 (4a), replay.py:445-492 (reuse).
- No writes to ~/.llama, the station or the main checkout; worktree untouched; no commits. The doubled arm is an in-memory monkeypatch, not a file edit.
