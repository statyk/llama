Status: DONE
Commit: see `git log -1` on playout-player: "transmitter: published briefings drop the pointer to the cut Cautions"
Tests: transmitter 949 passed, 1 skipped; debian12 script 950 passed.

## Measurement (read-only, 3650 briefings in ~/.llama/shows, case-insensitive)
Every distinct parenthetical containing "caution" (50 distinct texts; counts / briefings / section):
- `(see cautions)`: 413 / 362 / Set 1 239, Set 2 97, Encore 35, Notable moments 23, Why this show 10, Context 5, Reception 4. ONLY exact casing seen: lowercase. REMOVED.
- Left alone, each 1 occurrence unless noted (more words than a pointer):
  (title disputed; see cautions) x2; (see notable moments and cautions) x2; (see cautions on the title) x2; (see cautions on this title); (see cautions for the full structure); (1:27; the archive gives a longer title for it, see cautions); (title as tagged; see cautions); (setlist.fm lists this song under a different name; see cautions); (see cautions on how to phrase this); (see cautions before naming it on air); (see cautions on attribution); (see cautions on naming it); (the show data lists "helicon 2" as a tenth song in set 1; see cautions); (see cautions on the name); (unverified; see cautions); (see cautions about what follows it); (see cautions on sourcing for album attributions); (see cautions on who); (single source, see cautions); (5:18; see cautions); (9:05; see cautions); (see cautions on set structure); (see cautions on structure); (see cautions on verifying this); (see cautions on that title); (see cautions about that track's title); (an override title; see cautions); (see cautions on how to read this); (see the encore entry and cautions); (6:45, title uncertain; see cautions); (see cautions on that song's title); (the city is unconfirmed; see cautions); (the track list gives it twice; see cautions); (see cautions about this sequence); (single-source; see cautions); (see cautions on the date); (see cautions on the count); (see cautions about this slot); (see cautions on this song's origin); (see the WSLR and "best ever" cautions below). These are in Set 1/Set 2/Encore/Notable moments/Context, so they still point at the cut section on public pages: a follow-up decision for the operator (brief said leave them).
- Parentheticals inside the Cautions section itself (not rendered): (e.g., Golden Road, Caution > Jam); (for example Dark Star, Doin' That Rag, Other One, Cryptical and Caution); ("Playin' reprise," "Caution," "Donor Rap"); (e.g., Here Comes Sunshine, Mississippi Half-Step, Caution); (Sittin On Top ... Caution Jam, ...); (Cryptical Envelopment, ..., Caution Jam, ...); (the research mentions ... Caution); (A-, "Very Cool, esp Caution").
- Note: the brief's 471 does not match; I count 413 pointer occurrences in 362 briefings (all in ordinary sections; none in Cautions).
- "caution" outside any parenthetical, above the Cautions heading: 415 lines in 242 briefings (the song Caution (Do Not Stop on Tracks), prose). All stay.

## Implementation
site.py: module-level `CAUTIONS_POINTER = re.compile(r"\s*\(see cautions\)", re.IGNORECASE)`; parse_briefing applies `.sub("", line).strip()` right after the cautions-heading break, so paragraphs, bullets and headings all get it. Stored briefing/notes untouched.

## TDD
RED: `./.venv/bin/pytest packages/transmitter/tests_transmitter/test_site.py -q` -> 1 failed (test_parse_briefing_drops_the_bare_see_cautions_pointer), 80 passed. GREEN after change: 949 passed, 1 skipped (full transmitter suite).
Tests added (test_site.py): pointer removed from paragraph (with its period kept), bullets, case-insensitive, leading-position pointer; and a byte-identical test for the song "Caution (...)", prose "cautions", and four non-bare variants.

## Library check (step 4)
Old (HEAD) vs new parse_briefing on all 3650 briefings: 362 briefings changed, 413 occurrences removed; each changed line equals the old line with `\s*\(see cautions\)` removed and stripped; 0 doubled spaces and 0 space-before-punctuation introduced; section structure identical.

## Concerns
- 38 longer "see cautions ..." variants remain on public pages (listed above); needs an operator ruling.
- Edge, unmeasured: a bullet that was only "- (see cautions)" would become "-" and render as a paragraph; none in the library.
Files: packages/transmitter/src/transmitter/site.py, packages/transmitter/tests_transmitter/test_site.py

## Fix round 1
Change: site.py now `line, hit = CAUTIONS_POINTER.subn("", line)` and `if hit: line = line.strip()`, so lines without the pointer are exactly as before.
Tests added: `** bold** text` stays " bold text" (leading space kept); `(see cautions) Bar` paragraph gives `Bar`.
Mutants (scratch copy via git archive, PYTHONPATH on the copy, `python -m pytest`; expectation named first):
- M1 strip on every line: expected red = the bold test only. Got: 1 failed (test_parse_briefing_leaves_a_line_without_the_pointer_unstripped), 4 passed.
- M2 strip deleted: expected red = the leading-pointer test. Got: 1 failed (test_parse_briefing_strips_a_leading_pointer_from_a_paragraph_line), 4 passed.
- Baseline in the copy: 5 passed.
Suite: `./.venv/bin/pytest packages/transmitter/tests_transmitter -q` 951 passed, 1 skipped.
