# fw6 — strip a hyphen/underscore-joined track number from tag titles (operator-approved new predicate)

Diagnosis that motivates this (read it first): `/Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1/dso-diag/handback.md`. `darkstarorchestra-2012-05-19`'s tags are `01-Hell In A Bucket`, `03-Walkin' Blues`, …; neither `_TRACK_NUM_PREFIX` (needs whitespace after the number) nor `_GLUED_NUM_PREFIX` (needs `[A-Z][a-z]` right after two digits) strips them, so the shipped titles carry the numbers and a fresh briefing that names the songs fails the guard. Same form on `mountaingoats-*` (`_` separator), `ryanadams-2017-05-06`, `theblacklillies-2014-04-20`.

File: `packages/llama/src/llama/titles.py` (`clean_tag_titles`), `packages/llama/src/llama/stages/gather.py` (operator note, ~line 1130), `scripts/replay_holds.py` (the note-family table ~line 176). Tests: `packages/llama/tests/test_titles.py` (beside the 2c / `clean_tag_titles` tests), the gather note test beside 2c's, and replay_holds' family test if one pins the table.

## Required change
1. **A third predicate beside the two protected ones — both `_TRACK_NUM_PREFIX` and `_GLUED_NUM_PREFIX` stay byte-identical, as do `_ENUMERATED_MIN_FILES`/`_ENUMERATED_MIN_COVERAGE`:**
   `_JOINED_NUM_PREFIX = re.compile(r"^\d{1,3}[-_](?=[^\d\s])")`
   ORCHESTRATOR NOTE on the lookahead: the operator approved `(?=\S)`; it is narrowed to `(?=[^\d\s])` so that real titles like `4-20`, `1-800-…`, `24-7` are never matched (the operator required those untouched, as negative tests). It still strips `22-I Know You Rider` (do NOT copy 2c's `[A-Z][a-z]` lookahead — it would miss that). Comment block in the file's existing style: what it strips, why it is separate, the spec-style citation "held-backlog post-apply fix wave fw6, operator-approved 2026-10-20", and that the `\d{1,3}` bound and the digit-excluding lookahead are what keep `1922`, `2001`, `4-20` out of reach.
2. **Its own whole-recording vote, identical in shape to 2c's**: count voters (`voters` as computed today, so `gate_basis` scoping applies) matching `_JOINED_NUM_PREFIX`; when `>= _ENUMERATED_MIN_FILES` and `>= _ENUMERATED_MIN_COVERAGE * len(voters)`, strip it ONCE (`count=1`) from each title that matches; titles that don't match are untouched. Run it after the spaced and glued passes, independently of them (a tape numbered only in this form passes neither of the others). Do not apply `_GLUED_FOOTNOTE_TAIL` on this path.
3. **Scope** (operator): tag titles only — whatever reaches `clean_tag_titles` today, which includes the lossless-sibling titles under `sibling-format` recovery. Never override titles, setlist text or sibling-align text (they do not pass through `clean_tag_titles`; confirm by grep and say so).
4. **Operator note** in gather, beside 2c's and with the same conditions (only when `tag_source == "tags"`, only for a changed title whose raw form matches the new predicate, never for an overridden position), text verbatim: `stripped joined track number: track {i + 1} '{raw}' -> '{tag_titles[i]}'`. Add the family `("2d", "stripped joined track number:")` (or the table's next free key; read the table) to `scripts/replay_holds.py` so the harness reports it.

## Tests (add)
Positive: an enumerated tape `01-Hell In A Bucket`, `Bertha` (unnumbered), `03-Walkin' Blues`, `04-Ramble On Rose`, `22-I Know You Rider` → numbers stripped, `Bertha` untouched; an underscore tape `01_Love Love Love`, `02_Woke Up New`, `03_No Children` → stripped; strip once: `01-200 More Miles` → `200 More Miles`... careful: the remainder starts with a digit, so the predicate does NOT match `01-200 More Miles` — pin that it is left as-is (a false negative, today's behaviour) and say so in the test name.
Negative (operator-required): on a tape where the vote PASSES, the titles `1922`, `2001`, `4-20`, `24-7 Spyz` (and a `1-800-Suicide`-style title) are never changed; a tape where only 2 of 10 tracks carry `NN-` → nothing stripped (vote fails); `M80`, `7-Up` on a non-enumerated tape → untouched.
Note: the gather note appears once per stripped title with the verbatim text; nothing under format recovery.

## Mutants (recipe in the plan's Global Constraints; predicted test BEFORE each flip)
- M1: lookahead `(?=\S)` → predicted: the `4-20` / `24-7` negative test.
- M2: drop `_` from the class → predicted: the underscore tape test.
- M3: drop the vote (strip unconditionally) → predicted: the 2-of-10 test.
- M4: `count=1` removed → expected EQUIVALENT (the `^` anchor); say so, as the existing comment does for the spaced strip.
- M5: allow 2c's lookahead `[A-Z][a-z]` instead → predicted: the `22-I Know You Rider` row.

## Cache census (read-only; put it in the handback)
Over every `~/.llama/cache/md_*.json` (read-only JSON; mirror how gather builds `kept` files' titles closely enough to apply `clean_tag_titles` per item and per audio format — reuse llama's own functions via the worktree interpreter, do not write anything under `~/.llama`): count items where the new vote passes; for each such item list identifier, how many titles change, and 3 example `raw -> new`. Separately list EVERY changed title whose remainder (after the strip) is short (<= 3 chars) or starts with a non-letter — the closest calls. A changed title that looks like a destroyed real title is a concern: report it, do not tune the rule.

## Done when
Full suite green; commit `feat(titles): strip a hyphen/underscore-joined track number on enumerated tapes (fw6)` with the test command/result; mutation table + census in the handback.
