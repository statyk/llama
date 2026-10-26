### Finding Verdicts

**A (r2 Minor 1, `ahead=1` unpinned): ADDRESSED.**
- `test_scheduler.py:354` `live(..., ahead: int = 2)` passes `ahead` through to `project(...)[0]` (`:362-363`).
- `test_scheduler.py:386` parametrizes `test_appending_first_pieces_reproduces_one_projection` over `[1, 2]`.
- That matches the pipeline's call shape: `pipeline.py:207/225` use `project(inp, ahead=1)[0]` with no `until_frame`, which is the `last_pos = ahead` branch at `scheduler.py:678`.
- I reproduced the implementer's mutant in a scratch `git archive` copy (import path proven to resolve inside the copy). The mutant is `scheduler.py:678` `last_pos = ahead - 1 if ahead == 1 else ahead`. Result: `[1]` FAILED (IndexError), `[2]` passed.
- That mutant only crashes, so I also tried a subtler one that changes rows instead: `boundary` skips `_try_next` when `last_pos < 2` (`scheduler.py:580`), so ahead=1 picks an ID where ahead=2 picks a two-block announcement. Result: `[1]` FAILED with an AssertionError (row mismatch), `[2]` passed.
- So the test pins the real risk (piece [0] depending on `ahead`), not just a crash.

**B (r2 Minor 3, tautological guard): ADDRESSED.**
- `pipeline.py:318` now goes straight from `next_start(...)` to `st.extend`. The guard is gone.
- The test that pinned its message (`test_plan_step_guards_the_first_appended_rows_start`, old `test_pipeline.py:1237-1247`) was removed, as ruled.
- The real guard is still pinned: extend's per-row "gap" `LayoutError` (`pipeline.py:236`) is tested by `test_appended_rows_obey_the_gap_layout` (`test_pipeline.py:846-862`).
- `LayoutError` is still imported and used in both files, so there is no dangling import.

**C (r2 Minor 4, ping after render-path analyze + runbook sentence): ADDRESSED.**
- `pipeline.py:430-431` pings `notify("WATCHDOG=1")` right after `st.engine.analyze(piece.show)`, the same idiom as the encode ping at `:446-447`.
- New test `test_pipeline.py:275-294` asserts that a ping follows every `analyze`. It would be red without the fix, because the next event would be "encode".
- `test_systemd.py:431` count (`+ len(st.engine.encoded)`) and `:467` (`2 * len(encodes)`) match the new behaviour. Every render-path analyze in those fixtures is followed by an encode.
- The runbook sentence (`docs/playout-setup.md:364`, item 5) is accurate against the code:
  - the render re-plan calls `st.extend(kept, pool, ...)` with no `max_new` (`pipeline.py:482`);
  - `frames_of` pings per analysis (`pipeline.py:124-129`) and `_ping` runs after each projection (`:208/:226`);
  - `Runner` wires `st.notify` (`service.py:223-224`);
  - publish runs after render in the same tick (`service.py:338-344`).

**D (r2 Minor 6, `[interstitials]` header): ADDRESSED.**
- `config.py` template now reads `# [interstitials]`, with the explanatory comments kept.
- I extracted HEAD's `DEFAULT_CONFIG_TOML` and loaded it with `load_config` from two scratch builds: `684d323^` (pre-interstitials) and `dbd3601`. Both loaded OK.
- The runbook 7.5 bullet (`docs/playout-setup.md:592`) is updated with "only if you uncommented it".

**E (r2 Minor 2, conditional MISS wording): ADDRESSED.**
- Fixed at:
  - `cli.py:253` (short, "may record a MISS ... (clock file only)");
  - `CLAUDE.md:262`;
  - `docs/playout-setup.md:497` (7.2);
  - `docs/playout-setup.md:578` (7.4 step 3, plus "With no clock file (step 4) none is recorded").
- Checked against the code:
  - `miss = not self._in_window(occ, s)` on an occurrence's first show only (`scheduler.py:618`, `_in_window` at `:397`);
  - a missing `clock.toml` yields `IMPLICIT_CLOCK` regardless of last-good (`clock.py:241-244`), and `test_implicit_clock_never_records_a_miss` pins that it never misses.
- A grep for `records a MISS|records MISS|MISS therefore|record a MISS|a MISS on` outside `.superpowers/` and `docs/superpowers/` finds only the four fixed sites.

**F (name-docs Minor 1): ADDRESSED.**
- `docs/playout-setup.md:558` now says "The show pages and hugo's alerts take it from `station_name`; antenna's emails from the Worker's `STATION_NAME` (7.4 step 8)".
- Checked against the code:
  - show pages: `publish.py:264`;
  - hugo's dispatcher: `alerts.py:390`;
  - relay titles: `service.py:213`;
  - antenna's emails: `antenna/src/alerts.ts:363` (`env.STATION_NAME`, default "llama radio", `wrangler.jsonc:44`).

**G (name-docs Minors 2-3): ADDRESSED.** `docs/playout-setup.md:581` (7.4 step 8) now covers each point:
- "do this before step 1's restart, or restart again after" is there.
- Commit the `wrangler.jsonc` edit "like `METRONOME`". This is consistent with the existing advice at `:656`.
- The re-PUT claim is exact. The digest covers the notes body plus the page rendered with `station_name` (`publish.py:263-266`), and pages are PUT only for timeline shows in the window `end_us > now - DAY_US` (`publish.py:241-247`).
- "aired more than a day ago ... keep 'llama radio'" is exact. Nothing else re-renders `show/` pages.

### New Breakage in the Fix Diff

**None at Critical or Important.** One Minor:
- **Minor:** `config.py` template. With the header commented, an operator who uncomments only `# dir = "..."` puts `dir` under `[station]`. The strict model then refuses it as an unknown key. The failure is loud, not silent, and the comments still show the header line, so this is a usability nit only. Optional fix: a one-line comment such as "uncomment both lines".

Python 3.11: no new syntax, only trivial changes.

### Out-of-Scope Observations

- The 7.5 wording "only if you uncommented it: `config init` on this build writes the header commented out" is not quite true for a config made by `config init` on a branch build between `684d323` and `2ae8bad`. Those builds wrote the header uncommented. As far as the runbook says, only `af46d72` (before `684d323`) was deployed to hugo, so this is theoretical.
- The first sentence of the runbook watchdog item 5 lists the ping points as "step, publish batch, prune batch, show encode". It still does not name analyses as a ping point, though the paragraph refers to them. This predates the fix; cosmetic.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.
