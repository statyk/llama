### Finding Verdicts

All line numbers are in `docs/superpowers/2026-10-22-title-hygiene-evidence/acceptance.md` at 8b77edd. Its sha256 is ec2e2732…3f7e, which matches the implementer's report.

- **I-1: stevekimockband-2002-04-20 (as-is) and gratefuldead-1989-07-19 (fresh-get) were described as "not hand-checked".** ADDRESSED.
  - Fixed at lines 108 and 126, in the "Good shows held" block (lines 141-145), and in the bar section's Q1 bullets (diff lines 138-139).
  - Checked against the census:
    - `handcheck/S1/rows.jsonl`: gratefuldead has 19 tracks, all right, `all-right`, and the note "whole-tape rung filled everything correctly. Operator overrides … agree".
    - `S3/rows.jsonl` and `U3/rows.jsonl`: stevekimockband has 12/12 right, `all-right`, with the 24-bit sibling durations noted.
  - `gate_table.md` R2's "good shows losing fills, Q1" lists both. It gives gratefuldead "newly held: True".
  - The good-show count is now 2 per view, with 1 counted against the bar. That is consistent with B3 and with Q1 being excluded from the bar.
- **I-2: the status line named only one open item.** ADDRESSED. Line 5 now lists both: (1) C-1, and (2) the kinggizzard hold, awaiting a ruling. No residual "one item is still open" text remains anywhere in the file (checked by grep).
- **M-1: the PLF cost was understated.** ADDRESSED (both rows).
  - The text now says "#1-#9 and #18 were right".
  - r2 `cmp-asis/title_rows.json` gives today's #9 as `Viola Lee Blues`. cpb-k08 says "today title is right here".
  - Today's #18 is `Box of Rain`, and cpb-k08's `correct_title` is `Box of Rain`. Its `why` text is the templated "today's title is wrong", but the titles are equal.
  - Recomputing the 7 wrong (#10-#14, #16, #17) and #15 partial against the table gives the same result.
- **M-2: soulive "wrong in cpb-k12".** ADDRESSED (both rows). cpb-k12 #10 has verdict `cant-tell`, and its `why` says the duplicate is wrong. Census `S2/rows.jsonl` gives #10 `wrong`, show `shifted`, and is now cited.
- **M-3: charliehunter said "not hand-checked".** ADDRESSED. The row now cites census `S0/rows.jsonl`: 10 tracks, all `wrong`, `some-wrong-not-shift`. The file matches.
- **M-4: the umphreys census conflict was not disclosed.** ADDRESSED (both rows). Census `S3/rows.jsonl` gives #12 `wrong` ("unlisted/continuation…", "adjacent duplicate"). The row discloses this and says it favours the hold.
- **M-5: DSO-2014 "#4-#21 are right".** ADDRESSED (diff line 124). cpb-k13 has 17 right and 1 right-partial (#10) over #4-#21, which matches.
- **M-6: B6 was overstated.** ADDRESSED (diff line 144). Ruling 6 in `checkpoint-b-rulings.md` reads "MRG via C2, O via slice 4" only. The new text says SOTM via D is not named.
- **M-7: pre-screen paths.** ADDRESSED (diff line 38). `~/.llama-harness/piece3/accept/handcheck/prescreen/` contains `adjusted.jsonl` and `tally.json`.
- **M-8: the gate table's final numbers.** ADDRESSED.
  - The new table (diff lines 148-161) matches `gate_table.md` R1 cell for cell: S 59/53/4/2/7.0%; D 464/411; C1 136/22; C2 118/20; 4 22/2; 5 422/97; pooled 1235/617/4/2/0.6%.
  - The R2 lines match too: slice-1 bar 2 (lotus, steepcanyon), caught 32, uncaught 5, Q1 12, other 6.
  - One small omission is noted under New Breakage.
- **M-9: final-rev Recommendation 3.** ADDRESSED (diff line 146). The quote is verbatim from `final-rev/handback.md:95` and is tied to DSO-2014 #3.
- **Item 4: the kinggizzard rows should state the computed cause.** ADDRESSED (lines 107 and 127, and the attribution and B4 notes).
  - Every figure matches `kg-why/handback.md`:
    - 12/13 = 0.9231 → 10/13 = 0.7692;
    - #6 no longer fuzzy-matches `Her and I (Slow Jam 2)`, and #13 consumes `Evil Death Roll`, which strands #14;
    - either replacement alone gives 11/13;
    - `--disable-slices slice3` gives clean;
    - needs-llm, with the outcome unmeasured;
    - the only C2-added state.
  - The 6 as-is and 9 fresh removal lists are exact.
  - Spec lines 57 and 290 were checked; both say "It adds no holds".
  - The verdict cell reads "accepted cost — PENDING OPERATOR RULING (orchestrator recommends …)", as briefed.
  - The cited `~/.llama-harness/piece3/kg-why/` and `accept/arms/base-asis.json` exist.
  - The old D-fills explanation is reduced to one clause.
  - The C-1 section is untouched: no hunk reaches past the rulings table.
- **(d) summary counts against the rows.** CONSISTENT.
  - As-is has 14 rows: 10 stop a wrong title (buttholesurfers, DSO-2015, PLF, railroadearth, signalpath, soulive, stringcheese, umphreys, charliehunter, dumpstaphunk), 3 are accepted by ruling (DSO-2004, lotus, stevekimock), 1 is pending (kinggizzard), and 0 are other.
  - Fresh-get has 15 rows: 11 stop a wrong title (the same, minus charliehunter, plus derektrucks and steepcanyon), 3 are accepted by ruling (DSO-2004, lotus, gratefuldead-1989), 1 is pending, and 0 are other.

### New Breakage in the Fix Diff

- **Minor: line 137, the summary row label "accepted cost, by ruling (all good shows held)".** It includes darkstarorchestra-2004-04-24, which is not hand-checked good. The row at line 96/113 and the "Good shows held" block (line 146) give it as set 1 right and sets 2-3 cant-tell, and count only 2 hand-checked-good shows per view. So the label claims more than the block beneath it, though in the direction that overstates cost. Suggested wording: "(DSO-2004 set 1 good, sets 2-3 cant-tell; lotus and the Q1 show hand-checked good)", or just drop the parenthetical.
- **Minor: the M-8 table (diff lines 150-158) leaves out R1's `other` row (14 tracks, 12 judged right).** Without it, the per-path rows do not visibly reconcile with the pooled row. The table also leaves out the inferred and unjudged columns, but the header calls it a selection ("final per-path numbers"), so that part is defensible.

### Out-of-Scope Observations

- cpb-k08's PLF rows use a templated `why` ("today's title is wrong (shifted one late)") even on #18, where today's title equals `correct_title`. Anyone who reads the `why` field alone would miscount. The acceptance text now reads it correctly.
- `gate_table.md` R2 gives stevekimockband-2002-04-20 "newly held: False", because the gate measured the fresh view, where the base already holds it. The as-is row cites R2 only for "good show losing fills, Q1", which is accurate. A reader cross-checking "newly held" might stumble on it, but there is no defect.

### Verdict
All findings addressed: yes
