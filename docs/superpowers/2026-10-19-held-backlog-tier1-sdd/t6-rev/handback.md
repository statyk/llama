# t6-rev: Task 6 review (replay_holds compare), 3263f45..e5bf134

### Spec Compliance

- ✅ Spec compliant for everything verifiable from the diff. Every Interfaces bullet has its writer: gates `scripts/replay_holds.py:133-148`, exit 3 `:447-452`, drift `:155-161`, briefings `:164-187`, flags `:190-200`, outcomes `:208-215`, exposure (with `date`, ruling M7) `:81,218-241`, title_sources `:248-255`, structure_changed `:289-298`, hand_check `:301-309`, notes (with `format sibling tagged` and `other`) `:83-93,312-330`, closest_calls `:338-402`, needs_llm `:405-411`, lists `:414-432,473-480`, summary last `:486-504`.
- Exit 3 boundary (checked by reading): `ok / len(denom) < 0.99` at `:449`. At exactly 99%, any n/m equal to 0.99 rounds to the same double as the literal, so 99/100 passes and 98/100 fails. An empty denominator passes (`if denom and`). The message matches the brief word for word.
- Denominator (`:127-130`): held shows whose outcome is not `needs-llm`. Held unreplayable rows are included, and so are `state == "unknown"` + `unreplayable` rows (orchestrator ruling). Rows with a missing or false `reproduces` count as not reproducing (`:448`).
- Exit 2 fires on a `setlistfm_configured` difference, a `config_fingerprint` difference, a slug in one arm only (named) and a per-slug `digests` difference (`:135-146`). Each has a test (`test_replay_holds.py:611-641`). `_gates` runs before `out.mkdir` (`:441-443`), so nothing is written.
- `predicted_list.json` (`:474`) holds only cand rows whose outcome is `clears` or `needs-brief`. `digests` and `briefing` come from the cand row (`_list_row`, `:419-421`), and `sha`/`config_fingerprint` come from the cand arm (`:414-416`). Checked `replay.classify` (`packages/llama/src/llama/replay.py:354-369`): `needs-llm` is returned first and never sets `would_be`, so no needs-LLM show can reach `predicted_list.json`, `structure_changed_list.json` (filtered on `outcome == "structure-changed"`, `:475-476`) or `pilot_list.json` (taken from predicted). Also checked `compute_legs` (`replay.py:336-345`): a clearing outcome means no flags, so `briefing` is always `reuse` or `fresh` there, never `none`, which matches the list schema.
- `structure_changed_list` rows carry `outcome = would_be` (`:475`). This is the only reading that satisfies the Contracts schema (`clears|needs-brief`), and `classify` always sets `would_be` for `structure-changed`.
- Do-not-retune grep over the diff file (is_real_title, title_fraction, _TRACK_NUM_PREFIX, normalize_song, DEFAULT_ALIASES, GD_SHORTHAND, _RECOVER_*, TAIL_GUARD_ITEMS/TRACKS_REMAINING/MAX_SKIP, junk-duration constants, align_coverage_threshold, _ENUMERATED_MIN*, _STRUCTURE_PREFIX, _FOOTNOTE_TAIL): no hits (rc=1). The diff touches only `scripts/`.
- ⚠️ Cannot verify from the diff: the ruling says "held-scope rows with state unknown", but `_in_denominator` (`:130`) does not read `arm["scope"]`. In an `--all` arm, any show whose `derive_state` raised counts as held and not reproducing, even when it is really packaged. That is conservative (a false exit 3, never a false pass). Controller: confirm this reading of the ruling is intended.

### Strengths

- The gates run before any write, and exit 3 writes only `drift.txt` before returning. The "operator can read why" behaviour is exactly what the brief asks for.
- The apply lists can only be built from cand rows, through one `_list_row`. The needs-LLM exclusion rests on `classify`'s ordering rather than on a second check here, so prediction and apply cannot drift apart.
- Every library read is read-only, with placeholders on a missing or unreadable file: `_read_json`, `_show_json`, `_description`, the `vetting.json` read for 4b (`:258-286,379-381`). The 5a minutes use the right model field, `duration_sec` (checked `models.py:155`).
- The pilot swap follows the Contracts rule: it replaces the last non-reuse rows with the next reuse rows in order, then re-sorts by sha1 (`:424-432`).
- The tests run real `run` arms over the fixture library and mutate JSON from there, so they exercise the real `run` → `compare` contract and not mocks.

### Issues

#### Critical (Must Fix)
(none)

#### Important (Should Fix)

1. **The 99% gate boundary has no test. Verified by mutation:** mutant `ok / len(denom) < 0.99` → `< 1.0` (`replay_holds.py:449`) SURVIVED all 11 compare tests (scratch copy, PYTHONPATH-shadowed, `llama.__file__` and `replay_holds.__file__` resolved inside the copy). The tests only use 1/1, 0/1 and 1/2, so a gate demanding 100%, or one that is `<=`, passes them. The gate is strict per the brief. Fix: add a pure test that calls `rh.main(["compare", ...])` on two synthetic arm JSONs, with no `run` needed: 100 held rows, 99 reproducing → exit 0; 98 reproducing → exit 3 with `98/100`. Consider integer arithmetic (`ok * 100 < 99 * len(denom)`) so the boundary does not rest on a float-rounding argument.
2. **The pilot swap rule is never exercised. Verified by mutation:** mutant `while ... < 2 and spare:` → `while False:` (`:427`) SURVIVED. In `test_pilot_list_swaps_in_reuse_rows` (`test_replay_holds.py:732-737`), the reuse rows `s12` and `s13` sort to sha1 positions 8 and 9, inside the first 10, so the loop never runs (computed: order `s08 s03 s05 s09 s00 s07 s04 s06 s12 s13 s02 …`). The implementer's "weak if the first 10 already hold 2 reuse rows" is exactly what happens. The test is not merely weak: it asserts nothing about the swap. Fix: build rows whose sha1 order puts the reuse rows after position 10 (or pass `_pilot` an explicit pre-ordered list, since it does not re-sort its input). Assert the exact resulting slug set: the first 8 non-reuse rows plus the first 2 reuse rows beyond position 10, with the last two non-reuse rows of the first 10 dropped.
3. **`structure_changed_list.json`'s content is untested.** `reapply` consumes it (Tasks 19-20). No test asserts that it holds only `structure-changed` rows, that each row's `outcome` is `would_be` (`clears|needs-brief`) and not `"structure-changed"`, or that rows carry cand digests. A mutant writing `r["outcome"]` at `:475` would pass. Fix: in one compare test, set a held cand row to `outcome="structure-changed", would_be="needs-brief", briefing="fresh"`. Assert it appears in `structure_changed_list.json` with `outcome == "needs-brief"`, and is absent from `predicted_list.json` and `pilot_list.json`. Add a `needs-llm` cand row and assert it is in no list. This pins "no needs-LLM show is ever in an apply list" directly, rather than through `classify` alone.

#### Minor (Nice to Have)

- `replay_holds.py:443-452`: on exit 3 (and exit 0) the `--out` directory is reused without clearing it. An earlier successful compare's `predicted_list.json`, `pilot_list.json` and `summary.txt` survive beside a fresh failing `drift.txt`, which invites signing off or applying a stale list. Either refuse a non-empty `--out`, or remove the known output names before writing.
- `:302` vs `:509-510`: `hc_rows` duplicates `_hand_check`'s selection (`sorted(_newly_cleared(...), key=_skey)[:20]`). It is a public-named helper defined after its caller. Have `_hand_check` return the slugs too, or call `hc_rows` from it.
- `:483`: a lambda assigned to a name (`held_nl`, E731). Make it a small function.
- `:444`: `root` falls back to `"."` when neither arm has `root`, so the reports silently read relative to the cwd. Neither the gate nor anything else checks `base["root"] == cand["root"]`. The digest equality mostly covers it, but a root mismatch could be named in `arms differ`.
- `:97-104`: `_load_arm` accepts any `shows` dict. A non-dict row raises an uncaught `AttributeError` (a traceback, not exit 2). Arms come from `run`, so this is low risk.
- Untested content: `briefings.txt` sections (2) and (3), the `hand_check_sample.txt` sha1 order and 20-row cap, the `title_sources.txt` and `structure_changed.txt` bodies, and the 1c bottom-10 cut. Coverage could be broader. Item 3 above is the one that matters for apply.
- `:347`: the 1c regex uses greedy `(.*)`. A venue containing `' vs '` would split wrongly. Not a real case.

### Checks run

- Mutation A (`< 0.99` → `< 1.0`): SURVIVED. Mutation B (pilot swap disabled): SURVIVED. Each mutant ran in its own `git archive` scratch copy with a private pycache and the shadowing proven; the scratch was removed afterwards.
- `replay.classify`, `compute_legs` brief decision, `run`'s `state="unknown"` origin (`replay.py:437-465`): read to confirm list exclusivity and the `briefing` values.
- `structure._place_tokens` signature (`structure.py:266`) and `Track.duration_sec` (`models.py:155`): confirmed the names used.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The implementation matches the brief and the rulings, and the gate and apply-list logic read correct. But the two operator-signed rules the brief calls strict, the 99% boundary and the pilot reuse swap, are each unpinned (both mutants survive), and the apply list `reapply` consumes from the structure-changed path has no content test. These are test-only fixes.
