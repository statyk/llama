# Task 9b: strip "(see cautions)" from published briefings

Why: the Cautions section stays off public pages (operator's ruling), and parse_briefing already cuts it, but 471 of 3,625 library briefings keep a literal "(see cautions)" pointing at it, in the text the show page and the notes panel render. Example: gratefuldead-1977-05-08, "missing a chunk of this pairing (see cautions)".

Scope, from the decision:
- Remove only that parenthetical and any space it leaves. Change no other briefing text.
- Do it in `parse_briefing` in packages/transmitter/src/transmitter/site.py, so the page and panel both get it. The stored briefing, stored notes and old pages are untouched.
- Match case-insensitively if the library varies.

Step 1, measure first. Read-only over ~/.llama/shows/*/briefing.md (write nothing there; do not import or run anything that writes). Count every distinct parenthetical containing "caution", by exact text and count, and the number of briefings for each, and which section each falls in, cut Cautions included. Put the table in your handback. Also count mentions of "caution" outside any parenthetical: those stay. Only parentheticals that are a bare pointer to the Cautions section ("see cautions" in any case, and any near variant that is the same bare pointer) are removed; if a variant carries more words than a pointer, leave it and list it.

Step 2, write failing tests in packages/transmitter/tests_transmitter/test_site.py:
- a real sentence from the library loses the parenthetical and the space before it, keeping its punctuation: "...this pairing (see cautions)." gives "...this pairing."
- a sentence that merely mentions cautions without the parenthetical, and a parenthetical that isn't a pointer, stay byte-identical.
- each measured variant you cover.
- bullets as well as paragraphs, if the parser treats them apart.

Step 3, implement with one compiled regex at module level. Python 3.11. Ordinary sections only; the behaviour of every other line stays the same.

Step 4, check over the library, read-only: run parse_briefing on every briefing before and after, and confirm the only difference anywhere is the removed text (give the count of briefings changed and of occurrences removed), and that no result has a doubled space, or a space before punctuation, that the input did not have.

Step 5, run `./.venv/bin/pytest packages/transmitter/tests_transmitter -q`, and `packages/transmitter/scripts/test-in-debian12.sh` (site.py must stay 3.11-compatible). Commit: `transmitter: published briefings drop the pointer to the cut Cautions`.
