# fw7b — docs + test hygiene for the post-apply fix wave (last task)

Run `git log --oneline 4cd1ebc..HEAD` first: every commit in that range is a fix-wave task whose behaviour the docs must now describe. Read each commit's diff before editing docs. Keep CLAUDE.md terse — it is already long; add to the existing bullets rather than new sections, and wrap lines like the surrounding text.

## A. CLAUDE.md / README.md accuracy (docs only)
1. Tier 1 guards bullet ("Tier 1 held-backlog guards"): add one clause each —
   - fw6: `2d` — `_JOINED_NUM_PREFIX` (`^\d{1,3}[-_](?=[^\d\s])`) strips a hyphen/underscore-joined track number (`01-Hell In A Bucket`, `01_Song`) under the same enumerated vote, once, note `stripped joined track number:`; a `7-Up`-style title on an enumerated tape is an accepted loss like `100 Years`; `1.02 - ` and `1-002` forms are not covered.
   - fw5: 3b also treats the parts of a comma-merged title as known songs ONLY when every top-level comma part ends in its own parenthetical (`Stay With Me (tease), Girl Named Sandoz (tease)`); a comma inside one song title never splits.
   - fw4: both set-count regexes' `of` lookahead stops at the briefing-field newline (the vague branch's too — operator ruling 2026-10-20).
2. Reapply bullet ("Run (held-backlog tooling)"): `llama reapply` refuses to apply a show whose replay is structure-changed unless `--allow-structure-change` (names form and `--from-list` alike; skipped rows are `skipped: structure changed`, retryable); the dry-run summary counts `downloads` (incl. purged-audio re-downloads). Check the fw3 sentence a previous task added there and re-wrap its long line to the file's width.
3. `--untitled` bullet: it also clears a pre-existing `overrides.encore_after`.
4. The Task 22 deferred docs list (each a one-line accuracy fix; find the current text and correct it):
   - the pacing gate in `reapply` runs in the list form only;
   - 1c (same-city venue difference) applies only on a single-event date;
   - needs-LLM also covers a stored alignment of `"llm"`;
   - README "its only LLM call" → the fresh brief is one task of up to two attempts;
   - `OUTPUT_FILES` already includes the three lists — say "including", not "plus".

## B. Code comments / docstrings
5. `packages/llama/src/llama/stages/brief.py` `_guard_prose` docstring and the comment in `test_guard_prose_field_marker_leaves_todays_matches_unchanged`: they say joining fields by newline leaves today's matches "and with them the vague branch" unchanged — add "except the `of` lookahead, which stops at the newline (fw4)".
6. The vague-branch comment "Unchanged by slice 3: today's regexes" in `briefing_guard`: append that fw4 changed the shared `of` lookahead under an operator ruling.
7. `packages/llama/tests/test_titles.py` ~line 661: comment says "keeps these five intact" — there are now six; add the mandatory `[-_]` to the list of reasons.

## C. Tests (behaviour pins; no production change)
8. fw1 review M-1: a confirmed `fix --untitled` run that ends still held (stub both redos to return None) prints `still held: <slug>` and NOT `declined`; same for triage `[u]` if cheap. Mutant: make the confirmed-but-held path return "declined" → predicted: this test.
9. fw3 review M6: a held show with only `briefing.md` (no briefing.json) and a shipped title change → the `.md` is dropped. Mutant: drop the `or ws.briefing_md.exists()` clause → predicted: this test.
10. Test hygiene from the final review (keep each change mechanical; do not change what a test asserts):
   - move mid-file imports to the top of the test modules that have them (grep `^import\|^from` after the first `def test` in `packages/llama/tests/` and `scripts/test_replay_holds.py`; only files this branch touched: `git diff --name-only f1744ad..HEAD`);
   - `test_cities_not_compatible`: assert both argument orders;
   - `_two_arms` helper in `scripts/test_replay_holds.py`: keyword arguments at call sites if it takes 3+ positional args;
   - a harness test that disables logging restores it (`logging.disable(logging.NOTSET)` in a finally/fixture).

## Done when
Full suite green (state the count); commits `docs: post-apply fix wave (fw1-fw6) in CLAUDE.md/README` , `docs(brief,titles): comments match the fw4/fw6 behaviour`, `test: fix-wave review pins (untitled still-held, briefing.md drop) + hygiene`; mutation table for 8 and 9 in the handback.

## D. Added after the fw2 re-review (cheap)
11. `cli.py` ~3366-3367: the comment says the operator can "move the row to the structure list" — no longer true (that list needs `--allow-structure-change` too); fix the comment.
12. README.md reapply section (~255-270): document `--allow-structure-change` and that `structure_changed_list.json` is applied with `llama reapply --from-list <it> --allow-structure-change` after hand-checking each row.
13. Dry-run consistency (small code change + test): without `--allow-structure-change`, a dry-run of a row/show whose replay is structure-changed must print `would: <slug> -> skipped: structure changed` and must NOT count its fresh brief or download (with the flag: unchanged, `-> structure-changed`, counted). Mutant: count it anyway → predicted: the new dry-run test.
