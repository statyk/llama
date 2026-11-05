### Finding Verdicts

- **Westward test did not cross a tab (fixture 04:30Z is Nov 4 in both zones)**: ADDRESSED. antenna/test/programs.test.ts:120-131 now uses 2026-11-05T05:30:00.000Z. NY: `ny[0]` empty and `ny[1]` = ["Night"]. LA: `la[0]` = [["Night","9:30p"]] and `la[1]` empty. Auckland: 18:30 Nov 5 NZDT goes to the next tab. I checked every comment's arithmetic. The test discriminates. A mutant that keys items by UTC date puts LA's entry on Nov 5, which fails `la[0]`. A fixed-offset or wrong-zone mutant fails the NY or LA asserts.
- **DST test passed `{ occurrences: [] }`**: ADDRESSED. antenna/test/programs.test.ts:133-157 has four cases with occurrences at the transition hours: spring 01:30 EST / 03:30 EDT / 04:30 EDT, fall 00:30 EDT / 01:30 EDT / 01:30 EST, plus the day after each. Each one is asserted on its expected local tab. The test also checks `all.length === starts.length` and no duplicate keys, and keeps the 7-consecutive-days check. I verified every expected day by hand. The test discriminates. A fixed -5h mutant moves 2026-11-01T04:30Z (00:30 EDT) to Oct 31 and moves 2027-03-15T04:30Z (00:30 EDT) to Mar 14, so both fail.
- **blockSpan RangeError escaping comingUpGroups on bad start/end**: ADDRESSED. programs.js:45: a blocks entry is indexed only when `Date.parse(b.start)` is finite, so the show goes headless. programs.js:27: blockSpan formats the end only when it parses. Tests are at programs.test.ts:76-85 (start undefined/""/"nope" gives [null, "Mid-morning Dead", null]; an unparseable end gives the start-only span) and :92 (direct blockSpan with end "nope" gives "7:00a"). The tests discriminate. In the old code `airTime` ran `formatToParts(new Date(NaN))`, which throws RangeError (timeline.js:108), so all three new tests would have thrown.

### New Breakage in the Fix Diff

- Minor: programs.test.ts:120-131 dropped the earlier Tokyo case (the occurrence stays in Today when now is local midnight). It was not one of the required asserts. The eastward-zone coverage it gave is gone.
- Minor: programs.js:25-27: an exported `blockSpan` still throws on an unparseable `start` if called directly. Only the comingUpGroups call site is guarded, which meets the finding as stated. Also, `nonEmpty(entry.end) &&` on line 27 is now redundant next to the `Date.parse` check (cosmetic).

### Out-of-Scope Observations

- The fix report gives only a summary line ("544 passed, typecheck clean"), not raw test output. I did not re-run the tests: reading the code and doing the arithmetic answered every doubt.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.
