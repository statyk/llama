# fw5 — briefing guard: comma-merged track titles contribute their parts as known songs

File: `packages/llama/src/llama/stages/brief.py` (`song_components`, `known_song`, `briefing_guard`). Tests beside the existing 3b `known_song`/`song_components`/`briefing_guard` tests (grep `known_song` under `packages/llama/tests/`).

## The defect (measured on the live library, 2026-10-20)
`smashingpumpkins-1994-04-17` has a track whose tag title is
`Stay With Me (tease), Girl Named Sandoz (tease), Happy Birthday (tease)` (one file, three teases). Its fresh briefing's `mentioned_songs` includes `Girl Named Sandoz`, and the guard holds the show with `briefing mentions unknown song: Girl Named Sandoz`, because `song_components` splits only on segues (`>`, `->`, `→`) and strips only ONE trailing parenthetical, so that title yields a single normalised blob. (`Happy Birthday` passes only because another track is titled `Happy Birthday (tease)`; `Stay With Me` because one is titled `Stay With Me`.) The operator calls this a guard false alarm.

## Required change — additive only (3b's superset property must hold)
1. New brief-local helper `song_comma_components(title: str) -> list[str]`: split `title` on commas that are NOT inside parentheses (track depth while scanning; a comma inside `(...)` never splits). If that yields fewer than 2 non-blank parts, return `[]`. Otherwise return the concatenation of `song_components(part)` over the parts, in order. Docstring: why (merged-tease titles), and that it only ever ADDS known components.
2. In `briefing_guard`, the `components` set additionally includes `song_comma_components(t.title)` for every track. Nothing else changes: `exact` is unchanged; `known_song`'s logic and signature are unchanged (a mention like `Girl Named Sandoz` is then known through the existing "every component is a known component" rule). Do NOT split mentions on commas, do NOT touch `song_components` itself, `normalize_song`, `_BRIEF_*` regexes or any structure.py/songs.py code (do-not-retune list).
3. If `scripts/replay_holds.py` or `llama/replay.py` builds the guard's component set itself rather than calling `briefing_guard`, make it use the same helper (grep for `song_components(` across `packages/` and `scripts/`; report every call site you found and what you did with it).

## Tests (add)
1. The smashingpumpkins shape: a show with a track `Stay With Me (tease), Girl Named Sandoz (tease), Happy Birthday (tease)` and no other track for those songs; a briefing mentioning `Girl Named Sandoz`, `Stay With Me` and `Happy Birthday` → no `unknown song` problem for any of them.
2. Commas inside parentheses never split: a track `Jam (w/ Bob Weir, Phil Lesh)` → a mention `Phil Lesh` IS flagged unknown, and `song_comma_components` returns `[]` for it.
3. A single-part title (no top-level comma) → `song_comma_components` returns `[]`.
4. Superset: an existing `known_song` / guard test set still passes unchanged (do not edit existing assertions).
5. A song in no track title at all is still flagged (e.g. the same show as test 1, mention `Mayonaise` → flagged).

## Measurement (read-only, report it in the handback)
Over `~/.llama/shows/*/show.json` (read-only; just parse JSON): count tracks whose title has a top-level comma; list up to 15 distinct examples, and separately every case where a resulting comma part normalises to a SINGLE word (that is the loosening exposure: a briefing naming that one word as a song would now pass). Do not change the rule based on this; report it for the reviewer.

## Mutants (recipe in the plan's Global Constraints; predicted test written BEFORE each flip)
- M1: drop the `song_comma_components` union from `components` → predicted: test 1.
- M2: split on every comma (ignore parenthesis depth) → predicted: test 2.
- M3: return the parts even when there is only one (`< 2` check removed) → predicted: test 3 (if it survives, explain why it is equivalent and say so; do not invent a test that tests the implementation rather than behaviour).

## Done when
Full suite green, one commit `fix(brief): comma-merged track titles contribute their parts to the known-song set`, mutation table + measurement in the handback.
