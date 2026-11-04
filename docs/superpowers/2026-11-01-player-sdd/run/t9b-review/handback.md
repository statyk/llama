### Spec Compliance

- ❌ Issues found: one requirement missed. The brief says "the behaviour of every other line stays the same", but `.strip()` at site.py:145 runs on every line, so lines with no pointer change too (Important 1). The rest matches the brief: one module-level regex (site.py:103), in `parse_briefing`, after the Cautions break, ordinary sections only, tests added, stored files untouched.
- ⚠️ Cannot verify from diff: none. Check run for the page-and-panel requirement: `parse_briefing` has one call site (site.py:192), so both read its output.

Library claim, checked independently (`git show` of both site.py versions into scratch, run over every briefing, read-only, nothing written under ~/.llama):

| population | files | changed | removed | structure diffs | wrong diffs | new doubled space | new space before punctuation |
|---|---|---|---|---|---|---|---|
| library `shows/*/briefing.md` | 3650 | 362 | 413 | 0 | 0 | 0 | 0 |
| library `shows/*/package/briefing.md` | 3629 | 359 | 409 | 0 | 0 | 0 | 0 |
| station `delivered/*/briefing.md` (what is published) | 2786 | 289 | 331 | 0 | 0 | 0 | 0 |

- "Only the removed text differs" is TRUE on today's data, on all three populations. Every changed block equals the old one with `\s*\(see cautions\)` removed. Changed files equal files holding the pointer, so no non-pointer line changed.
- Line-level strip with other text remaining: today it does nothing. Every one of the 413 pointers follows text (alnum or a closing quote; nothing follows a period) and is followed by `.` (409) or `,` (4). No pointer leads a line, ends a line bare, or stands alone, so `.strip()` removes nothing from any library line. Its cost is only on inputs not in the library (below).
- 413 is also every occurrence: none below a Cautions heading, none wrapped across a line, all lowercase.

Count: the report (413 occurrences in 362 briefings of 3650) is right for the thing being removed. The brief's 471 is right for a different thing. 471 of 3,625 comes from t9-review.log:115, and it counts the case-sensitive bare substring `see cautions` in package briefings, parenthesised or not, not the literal `(see cautions)`. Today `grep -l 'see cautions' ~/.llama/shows/*/package/briefing.md` gives exactly 471. So the brief mislabelled it as the literal parenthetical; the implementer did not undercount. Case-insensitive, the substring is in 544 of 3650 library briefings.

### Strengths

- The regex is exact: it cannot touch `(title disputed; see cautions)` or the song `Caution (Do Not Stop on Tracks)`, and the test at test_site.py:410 pins that with real library variants.
- The sub sits after the break at site.py:143-144, so the heading check still sees the raw line.
- The measurement was real: the 413/362 figures, the 50 distinct parentheticals and the absence of case variants all reproduced. The implementer stated the 471 mismatch rather than papering over it.

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

1. packages/transmitter/src/transmitter/site.py:145: `.strip()` applies to every line, not just lines that lost a pointer. Line 142 strips before `replace("**", "")`, so a bold marker at a line edge leaves whitespace the old parser kept and the new one removes. Measured old vs new on lines with NO pointer:
   - `** ## Heading` was paragraph text, now starts a new section.
   - `** - item` was a paragraph, now a bullet.
   - `** **` between two lines was one paragraph, now splits it in two.
   - `** bold** text` and `word **` lose a space.
   This breaks the brief's "the behaviour of every other line stays the same". Zero library effect today, but briefings are LLM-written and this changes block structure, not just spacing.
   The `.strip()` is also unpinned: with it deleted in a scratch copy, test_site.py still gives 81 passed. Fix: strip only on a hit, e.g. `line, hit = CAUTIONS_POINTER.subn("", line)` then `if hit: line = line.strip()`, and add two tests: a `** bold** text` line stays as it was, and a paragraph line `(see cautions) Bar` gives `Bar`.

#### Minor (Nice to Have)

1. site.py:145, shapes with no text left or a period already present (0 of 413 in the library, so optional):
   - a lone `(see cautions)` line becomes blank and splits the paragraph;
   - `- (see cautions)` becomes a paragraph reading `-` (the report's concern, confirmed);
   - `## (see cautions)` becomes `##`, which then joins the next line as `## b` in a heading-less section;
   - `Foo. (see cautions).` gives `Foo..`, a doubled period the brief's check does not name;
   - `*(see cautions)*` leaves `**` on the page.
2. Report accuracy: "caution outside any parenthetical ... (the song Caution, prose). All stay" hides what remains. After this change 217 occurrences of `see cautions` stay on public text in 198 library briefings: 178 unparenthesised in 160 briefings ("Its title is disputed; see cautions.", "See cautions before referring to...") plus the longer parentheticals. The Concerns section names only the 38 parenthetical ones. The brief says these stay, so no code change here, but the operator's follow-up decision should carry the full figure: the dangling pointer is reduced by about two thirds (413 of 630), not removed.
3. test_site.py: the `,` follower (4 in the library) and the closing-quote predecessor (24 in the library) are untested. The regex treats them the same, so this is coverage only.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The claimed library result is correct and the count mismatch is explained, but the blanket `.strip()` changes parsing of lines with no pointer, against the brief, and no test pins it. A one-line `subn` guard plus two tests fixes it.
