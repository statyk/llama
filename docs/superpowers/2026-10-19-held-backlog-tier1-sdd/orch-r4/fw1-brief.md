# fw1 — `fix --untitled` / triage `[u]`: clear a pre-existing encore, return a status, test the decline/zero-track rows

Files: `packages/llama/src/llama/cli.py` (`_untitled_resolution` ~line 1623, triage `[u]` branch ~1754, `fix --untitled` ~2790, `_overrides_snapshot` ~1618). Tests: `packages/llama/tests/test_fix.py` (existing `test_untitled_*`), `packages/llama/tests/test_triage.py` (or wherever triage `[u]` is tested — grep `untitled` / `"u"`).

## Items (final review I2 + Task 21 deferred minors)
1. **I2 — a fabricated encore.** `_untitled_resolution` calls `_edit_overrides(..., narration="vague", set_breaks=[])` and leaves a pre-existing `overrides.encore_after`, so the tape ships `1,1,1,encore,encore` after a confirmation that promised "one set". Pass `clear_encore=True` in that call (the `--clear-encore` flag is already refused with `--untitled`, so clearing internally is consistent). In `test_untitled_one_confirmation_writes_titles_narration_and_one_set_then_redoes` add `assert ov.encore_after is None` AND add a new test that seeds `overrides.encore_after = 3` first, runs `--untitled` with confirmation, and asserts it is cleared and the resulting show has a single set label (no `encore`).
2. **Status return instead of the byte-snapshot trick.** Both callers compare `_overrides_snapshot` before/after to tell "declined" from "confirmed but still held". Make `_untitled_resolution` return a small status instead — e.g. a `Literal["declined", "held", "packaged"]` plus the package path (a tuple or a tiny dataclass; match the file's existing idiom) — and use it at both call sites. Remove `_overrides_snapshot` if nothing else uses it (grep). Behaviour and printed texts stay exactly as today: fix prints `declined; nothing written` and exits 0; triage returns to the prompt on decline; otherwise `packaged: <path>` / `still held: <slug>`.
3. **Untested rows (add tests):** (a) a zero-track show → `fix --untitled` is refused (find the existing refusal text — `0 of 0` — and pin it, exit code included); (b) `fix --untitled` declined → output `declined; nothing written`, exit 0, `overrides.json` byte-identical (or absent) after; (c) triage `[u]` declined → the prompt is shown again (assert the prompt is asked twice, e.g. feed `u`, `n`, then `s`) and nothing is written.

## Constraints
No other behaviour change. `_edit_overrides`/`_clear_hold` running outside the per-show lock is a pre-existing pattern — leave it. Never run `llama` against `~/.llama`; tests use `tmp_path` workspaces like the existing ones.

## Mutants
- M1: drop `clear_encore=True` → predicted: the new seeded-encore test.
- M2: make the decline path return the "held" status → predicted: (b) and (c).

## Done when
Full suite green; commit(s) `fix(cli): --untitled clears a pre-existing encore and returns a status` (+ a separate test-only commit if you prefer), mutation table in the handback.
