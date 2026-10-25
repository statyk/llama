### Finding Verdicts

- **I-1: item 2's gain side ships false segues (run-on blobs, first-component hits) on last tracks and across set breaks; both add-guards wanted, removals unchanged, rule (b) on the SHIPPED sets (round 2)** — ADDRESSED.
  - gather.py:1041-1047. `may_add(k)` is `k + 1 < n and (shipped_sets[k] == shipped_sets[k+1] or tracks[k].title.rstrip().endswith(">"))`. The selector `o if m and (not o or p or may_add(k)) else p` guards only the pooled-False/own-True case.
  - Removals pass with no guard: when `o` is False the selector returns `o`. Case analysis confirms it, and so does the mutation below.
  - No constant; the substring heuristic is not used.
  - Round 2 (gather.py:1964-1972, 1976-1977):
    - `donor_segues` now runs after the final set decision, with `final_sets`. That is the jerrybase-anchored `result.sets`, or the taper's `placement.sets` (typed parallel to tracks, taper.py:629). The rebuild uses the same `final_sets`.
    - I checked that nothing between the old and new call sites reads `result.segues`. `anchor_breaks` takes `aligned_sets` only, `decide_taper` takes `today_sets` only, and `today_llm` reads coverage, which `donor_segues` does not change.
    - The `alignment != "llm"` skip is equivalent to the old placement: a winning `llm_result` replaced `result` wholesale before; a losing one leaves `alignment` deterministic, so item 2 still applies.
    - No set relabel follows the rebuild. Only `cosmetic_strip` (titles) runs later.
  - Override path untouched (gather.py:1825-1829).
- **I-2: G5's docstring claimed "Measured cost: one real mark"; the measured cost is 5** — ADDRESSED.
  - gather.py:900-911 now gives the 20c4e6a figure, 5 marks, names all five, and gives the cause: `is_filler` matching words inside real titles.
  - The current form's residual cost is deferred to the fix report, which measures it at 0 real marks.
- **Minor: test_stage_gather.py:4879/:4916 assert subsets; name the moe #5 `Bullet ->` loss** — ADDRESSED.
  - The moe test is now `_segued_tracks(res) == MOE_SEGUED` (test_stage_gather.py:4888). Comments at :4870 and :4880 name #5 `Bullet ->` as the known loss.
  - The gd88 test is exact, `== [12, 13, 14, 15, 17]` (:4914).
- **Minor: pin that G5 runs after the segue-bearing donor ranking** — ADDRESSED. `test_fw4r1_g5_runs_after_the_donor_ranking` (test_stage_gather.py:~5001) is load-bearing. Check run: in a scratch copy, a mutant applying G5 to every LMA parse before the segue-bearing filter turns exactly this test red (`['Bertha'] == []`). The other 20 pass.
- **llama-db ADDITION: G5 fires only on an entry that is (leads with) filler; is_filler/_FILLER untouched; closers and banter still cleared** — ADDRESSED.
  - `_leads_with_filler` (gather.py:883-890) is `_FILLER.match` after stripping leading non-word characters. structure.py is not in the diff (stat: gather.py and test_stage_gather.py only), so `_FILLER` is only imported.
  - It is a strict subset of `is_filler`: the stripped prefix is non-word, so `\b` and the match position are preserved. G5 can only clear fewer marks than before.
  - One test per case for the four real titles (parametrized, test_stage_gather.py:~4960-4985).
  - D&C closers: (a) still asserts Outro/Crowd cleared; Terrapin now kept.
  - warrenzevon-2000-04-22 banter: (b) is unchanged in the diff and in the suite.
  - Check run: a mutant reverting to `is_filler(title)` turns the dc15 test, the segue_donor test and all 4 parametrized cases red.
  - The "wholly filler" alternative was measured and rejected, with the stated reason: it reopens 2 wz2000 banter marks.
- **Round-2 change: rule (b) compares shipped labels** — ADDRESSED.
  - `test_fw4r2_gain_ships_when_the_shipped_sets_agree` uses jrad-2017-04-29, `Morfbeats` canonical set 1 / shipped set 2. Check run: a mutant passing `list(result.sets)` instead of `final_sets` turns exactly this test red.
  - The cross-shipped-break pin (gd87 #8) holds.

Mutation checks run (scratch `git archive 4dd0ea6` under ~/.llama-harness/piece4/tfw4-rr1/mut). Shadowing was proven by a `SENTINEL_MUT` attribute imported from the copy (`llama.stages.gather.__file__` inside the copy), the run was `python -m pytest -k "fw4 or g5"`, and `__pycache__` was purged per mutant. Each mutant turned the predicted test red:

| mutant | red test |
|---|---|
| M1, own-title exception dropped | `test_fw4r1_cross_set_gain_ships_when_the_track_is_tagged` |
| M2, rule (a) dropped | `test_fw4r1_no_gain_on_the_last_track` |
| M3, canonical sets | `test_fw4r2_gain_ships_when_the_shipped_sets_agree` |
| M4b, guard applied to removals | `test_fw4r1_removal_on_the_last_track_still_happens` |
| M5, `is_filler` | the 6 G5 tests |
| G5-before-ranking | the ranking pin |

The one survivor is M6, below.

Measured-outcome sanity checks, against cached descriptions via tfw3-rev/desc.py:
- Row diffs are segues/segue_changes plus outcome/briefing knock-ons only:
  - rowdiff-ef: 72 rows, of which 13 knock-ons;
  - rowdiff-fg: 18 rows, of which 1 knock-on.
- cand-g sha is 4dd0ea6, not dirty. arms-g: BLOCKS MERGE (0).
- Restored, all RIGHT:
  - gd1977-05-01 #14 `Dancin' In The Streets-> Brown Eyed Women` (the selected description and two set-2 sbds);
  - gd1984-04-17 #9 `Take A Step Back > Help On The Way` (many descriptions);
  - furthur-2009-09-19 #9 set-2 `Jam -> Shakedown` (selected `Jam ->`, set 2).
- Declined, both RIGHT:
  - gd1990-03-15 #10 Don't Ease Me In ends set 1 in every set-marked description. The mark comes from the run-on blob `Don't Ease Me In China Cat Sunflower->`.
  - gd1993-08-22 #8 MNS ends set 1. The selected description is a one-line blob `The Music Never Stopped Help On The Way->`.
- Reopened G5 false mark, warrenzevon-1994-02-07 #16, CONFIRMED as described:
  - The donor reads `17. Roland Chorale Intro. > Roland The Headless Thompson Gunner > Roland Chorale Outro. ^`. The in-track Outro does not lead with a filler word, so the mark into #17 Mr. Bad Example is kept.
  - Today's stored show.json already ships this mark, so it is a reopen, not new output.

### New Breakage in the Fix Diff

- Minor, gather.py:884-890. The leading-non-word strip in `_leads_with_filler` is unpinned. Mutant M6 (`_FILLER.match(title)` with no strip) passes all 21 FW4/G5 tests. It is the only thing that makes `[banter]`, `[crowd]` and `-encore break-` count as filler, and none of the tests has a marked donor item followed by a bracketed filler entry.
- Minor, gather.py:894. The `_drop_dangling_segues` docstring's first paragraph still says "followed ... by an `is_filler` item". The second paragraph (gather.py:900) says `is_filler` is not used.
- Minor, test_stage_gather.py:5014. The comment above the add-guard tests still says "in the same set as the next track (canonical alignment)". After round 2 it is the shipped labels.
- Minor, test_stage_gather.py:4914 vs :4918. `test_fw4_gd88_regained_marks_still_ship` and `test_fw4_gd88_space_takes_the_donors_jam_mark` now make the identical assertion. Redundant, harmless.

### Out-of-Scope Observations

- warrenzevon-1994-02-07 #15 `Excitable Boy` ships a mark from donor `16. Excitable Boy ^ > Dr. Babyhead Solo`. That is a flow into a non-filler in-track solo. G5 never covered it, in either form. It is in today's stored show.json too.
- Carried from earlier rounds, unchanged and not measurable offline:
  - On the LLM `align_structure` branch, item 2 is skipped wholesale.
  - Pooled marks still feed `correspondence._merge_legal` and the `align_structure` prompt.
- 4 real gains are still declined by rule (b) because the shipped set label itself is wrong: discobiscuits-1999-12-30 #16, discobiscuits-2009-07-01 #9/#17, gd1990-07-14 #8. This is a set-label defect upstream of FW4.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage. Four Minors are new in the fix diff (the unpinned leading-punctuation strip, two stale comments, one redundant assertion). None blocks.
