# fw7a — cheap code minors: siblings `tmp >` bypass, `_date_flags` required keyword, 16b pins

## 1. siblings.py `tmp >` bypass (final review minor; title surface)
`packages/llama/src/llama/siblings.py` ~line 303-308: `proposed` is built from `t.strip().rstrip(">").strip()`, but the Task 11b placeholder refusal tests `is_placeholder_text(t.strip())`, so a donor title `tmp >` (or `Track 02 >`) is not refused and could be adopted as `tmp`. Make the refusal test the SAME stripped form the adoption uses (factor the strip into one local expression/helper used by both so they cannot drift). Do not change `is_placeholder_text`, `is_real_title` or `hygienic_title`.
Test (in `packages/llama/tests/test_siblings.py`, beside the 11b tests): a donor track titled `tmp >` (and one `Track 02 >`) → that row declines with reason `sibling title fails hygiene`, never adopts.
Mutant M1: revert to `is_placeholder_text(t.strip())` → predicted: that test.

## 2. Final review I5 — `_date_flags(..., day_unknown)` must be required
`packages/llama/src/llama/stages/vet_research.py:156`: `day_unknown: dict[str, str] | None = None`. Both callers pass it; a third that omits it silently drops every day-00 hold (the Checkpoint E decision). Make it a required keyword-only parameter (`*, day_unknown: dict[str, str]`), update callers/tests that rely on the default. No behaviour change. (No mutant: a signature change; the type error is the test.)

## 3. 16b deferred test pins (vet_research `_date_flags`)
Add tests pinning: (a) the ordering of the flags `_date_flags` emits when more than one kind applies (pin today's order exactly — read the code, do not change it); (b) `normalize_date('0/5/08')` (or whatever the 16b ledger line names — grep the ledgers `/Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1/orch-r2/ledger.md` and `orch-r1/ledger.md` for `16b` and `0/5/08`) → `'2008-05-00'` as currently produced; (c) first-surface-text de-dup of day-00 entries (two surface texts for the same day-00 date produce one flag carrying the first text). Pin current behaviour; if any of these shows behaviour that looks WRONG, do not change it — report it as a concern.

## Done when
Full suite green; commits `fix(siblings): placeholder refusal checks the stripped form adoption uses`, `refactor(vet): _date_flags day_unknown is required`, `test(vet): pin _date_flags ordering, day-00 parse and de-dup`; mutation table (M1) in the handback.
