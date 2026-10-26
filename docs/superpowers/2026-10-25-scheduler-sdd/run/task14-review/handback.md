# Task 14 review (ff7ba19..36282ce): runbook + CLAUDE.md

Reviewer: Opus. Read-only; no suites re-run (per brief).

### Accuracy (each documented claim checked)

**Rollback subsection (playout-setup.md 427-432)**
- 4fa87a7 = tolerant plan rows; af46d72 = byte-identical phase-1 serialisation: correct. Subjects match `git show`. af46d72 is on `main` (`git branch --contains`) and no transmitter/antenna commit landed on main after it, which fits "deployed to hugo". I can't check hugo itself.
- "af46d72 is the oldest safe target once the scheduler has run": correct. `layout.py` (PlanRow, the reader) is unchanged from af46d72 to HEAD (`git diff af46d72 HEAD -- layout.py` is empty), and 4fa87a7 makes timeline, site and row_analysis skip `kind != "show"`.
- "remove `[interstitials]` before rolling back past 684d323": correct. Across 02b6d49..HEAD, config.py gains only `InterstitialsConfig` (config.py:120-130, 140). 684d323 adds it (its `--stat` touches config.py). 0afcb9a only adds the absolute-path validator. No other config key was added, so no other removal is needed. Note that a HEAD `config init` writes a bare `[interstitials]` header (config.py:181). The instruction covers it, but only if the operator spots the empty table.

**7.2 Clock and schedule**
- Path `<TRANSMITTER_ROOT>/clock.toml` and `clock.last-good.toml`: correct (workspace.py:67-72). The copy is made only by the planning load (`live_clock(save=True)`, pipeline.py:166). schedule, status, library and announcements all pass `save=False` (service.py:478,584,638; cli.py:306). Correct.
- "No clock: implicit all-week open block; status says `no clock: open all week`": the status text is correct (service.py:459). The shape is only loosely right: `IMPLICIT_CLOCK` (clock.py:205-209) is a *daily* open block at 00:00 with 720-min wiggle, i.e. seven occurrences a week. The wording comes from the spec, and the effect is the same for planning.
- Strictness: unknown keys rejected (`extra="forbid"`), non-finite rejected (`allow_inf_nan=False`, clock.py:37), window fields ≤ one week (`le=_MAX_WINDOW_MIN`, clock.py:27,119-121,167), `weight > 0`, `on_this_day ≥ 0` (clock.py:98-99): all correct.
- `concert_gap_days = 0` disables the gap rule, and least recently aired still ranks first over 365 days: correct (rules.py:15,35-37).
- `max_shows` default 2 for a profile block, unbounded for an open block: correct (clock.py:293-297).
- Fill labels "pool short" / "longer than max_shows": correct (report.py:25). The sentence is muddled, though: "a long profile block whose pool cannot fill it ... gets structural fill (... 'pool short' or 'longer than max_shows')". "Structural" is only the second cause (`_blocksearch.py:572-579`).
- Draft workflow `schedule --clock draft.toml` then `mv`: correct. The draft goes through strict `load_clock`, so an invalid draft errors (service.py:589). `--days` default 7: correct.
- `schedule` and `library` read-only: correct (service.py:574 docstring; `scan_pieces(read_only=True)`; `test_schedule_writes_nothing`, test_cli.py:370,518). `--library delivered` description: correct.
- Invalid clock alerts `clock` "first at the next fill, not at once": correct. The alert fires inside `Station.clock()`, called only from `extend` (pipeline.py:166-170,186), which runs only while filling. It is not in `GATED_CODES`, so it sends at the first such call. The resolve is also delayed to the next fill, which the doc doesn't say.
- "status reports the clock as invalid": loosely right. The real line is `clock      last-good (invalid clock at …)` or `clock      no clock: open all week (invalid clock at …)` (service.py:455-458). The brief asked for "what status says", and the exact line isn't given.
- Edits reach air after one lead plus one show: matches the spec ("at most one show").
- MISS on a mid-way block's first show: correct (scheduler.py `miss=None if self.placed else not self._in_window(...)`). Bends counted once per block via `placed_bends`, only for offered options: correct.
- `awaiting_fix`: non-null means not airable (station.py:129-145,171-173; pieces.py:223). Dropped when not yet encoded; already encoded or on air finishes; lost-encode `LayoutError` limitation: correct (pipeline.py:409,420-421,457-460). **One error:** "`library` ... show `awaiting fix from llama: <reason>`". `library` groups by `report.reason_key`, which strips the detail (report.py:269-274, used at service.py:647), so it prints `awaiting fix from llama` with no reason. The reason shows only per package (e.g. `scripts/probe_estimates.py --time-one`).
- `aired.jsonl`: path correct (workspace.py:63). Published-and-past rows only (history.py:102-109). Idempotent by `(epoch_id, start_frame)` (history.py:131-152). Backfill uses the same rule on the first append. A partial last line is skipped with a warning on every load (history.py:112-128), and appends start on a fresh line (history.py:144-147). The epoch guard raises and alerts `history` (service.py:264-270,348). All correct. `history` also fires for any other append exception, not only the epoch mismatch.
- Plan lock: non-waiting, and manual plan/render refuse with `PlanLocked` (locks.py:21-32; cli.py:162,174). The service skips on it (service.py:253). Correct as written.

**7.3 Announcements**
- id = hash of rendered text (announce.py:46-47), so template, title, time_format or zone edits retire clips: correct.
- Two-block forms only for a different block within 12 h (`TWO_BLOCK_MAX_HOURS`, announce.py:20,54-60): correct. Zones default Eastern/Pacific (clock.py:71-73): correct.
- `[interstitials] dir` absolute (config.py:124-129), default `<station root>/interstitials` (interstitials.py:15-20); IDs `id-*.mp3` (interstitials.py:45): correct.
- `announcements --export` writes `ann-<id>.txt` for the missing ones; without it, lists present and missing; `--days` default 8 (cli.py:291-326): correct.
- `emcee say "$f"` writes `ann-<id>.mp3` beside the txt (emcee cli.py `dest = out or text_file.with_suffix(".mp3")`). The temp name ends `.tmp`, so the scanner can't pick it up: correct.
- Quiet period applies to clips (pipeline.py:154, interstitials.py:53): correct. The key is `[station] quiet_minutes`, and the doc names it bare.
- Fallback chain two-block, one-block, ID, gap: correct (scheduler.py:497-505,511-518,582-588). `announcement-broken` is logged, never alerted (pipeline.py:238-240): correct.

**CLAUDE.md**
- The Commands addition and the Scheduler paragraph are accurate on every point above, rollback hashes included.
- Stale or contradictory lines are left next to them:
  - line 274 still reads "Run (transmitter, playout on hugo — phases 1-2)";
  - lines 461-462 still read "(phases 1–2 built; the scheduler and the full player are phases 3–4)". That sits directly above the new "Scheduler (phase 3 …)" paragraph and contradicts the "phases 1-3" edit at line 11.

**Warnings check.** pytest.out holds only the last 5 lines. The one visible warning is the CPython 3.14 `popen_fork` multi-threaded `fork()` DeprecationWarning. Only llama tests use multiprocessing (test_concurrency, test_locks, test_sessions, test_ledger_concurrency, test_atomic_write). No branch test adds multiprocessing, fork or warnings. The Debian-12 transmitter run (deb.out) reports 887 passed with 0 warnings. No evidence of a new transmitter warning. I can't attribute all 26 individually from the truncated file. The `*.rc` files contain `done`, not exit codes.

### Completeness (operator needs that are missing)
1. **No clock reference or template.** The runbook says "Copy `clock.toml` to a draft". At rollout there is no clock.toml, and nothing in docs/ or the CLI gives the field set: `timezone` (required), `[[block]]` name/title/days/start/profiles/max_shows/wiggle_minutes/early_minutes+late_minutes/prefer, `[announce]` templates and `time_format` (`short12`|`hm12`|`24h`, default short12), `[open] exclude_profiles`, `[rotation] concert_gap_days` (45) / `on_this_day_weight` (3.0). The spec sketch lacks `[rotation]` and calls its names "a proposal". The operator can't write a first clock from the runbook.
2. **New hugo alert codes are not in 7.1 or the incident runbook.** `clock` (pipeline.py:168) and `history` (service.py:348) are event codes (not in `LEVEL_CODES`/`GATED_CODES`, alerts.py:53,59). They are absent from 7.1's level/event/gate lists (playout-setup.md 504-506) and from `docs/playout-incident-runbook.md`, which 7.1 names as the "what each alert means and how to respond" reference. `clock` also collides with 7.1's cloud "clock" *family* wording.
3. **No phase-3 rollout/cutover steps**:
   - deploy HEAD to hugo and restart;
   - the first run backfills `aired.jsonl`, and the cutover block records a MISS;
   - optional `clock.toml`;
   - create the interstitials folder and voice IDs;
   - `status`/`schedule` checks;
   - the player change (`antenna/public/nowplaying.js`/`player.js`, 6e0e282) only reaches listeners after `ANTENNA_BUCKET=<bucket> npm run deploy:assets`, and nothing says so.
4. `announcements --clock FILE` (cli.py:292; spec "Commands") is documented in neither file. It is the way to voice a draft clock's announcements before moving it into place, so new blocks are announced from the first occurrence.

### Issues

#### Critical
None.

#### Important
1. **CLAUDE.md contradicts itself on phase status.** Lines 461-462 ("phases 1–2 built; the scheduler … phases 3–4") and line 274 ("phases 1-2") were not updated. Every future agent reads this file. Fix: "phases 1–3 built; the full player is phase 4", and "phases 1-3" in the Run bullet.
2. **`clock` and `history` alerts are undocumented where the operator looks up alerts** (Completeness 2). Add both to 7.1's hugo event-code and "sent at once" lists, with a row each in the incident runbook:
   - `clock`: fix clock.toml (check with `schedule --clock`). It resolves at the next fill.
   - `history`: epoch mismatch between `publish.json` and `epoch.json`, so `aired.jsonl` is not appended and rotation recency goes stale. Other append failures (e.g. disk) also raise it.
3. **No clock field reference or template** (Completeness 1). Add a minimal annotated example with the real keys and defaults, or a pointer to `clock.py`'s models. Write the first-time path as "write `draft.toml` from the example", not "copy `clock.toml`".
4. **Player assets deploy missing** (Completeness 3). Without `npm run deploy:assets`, station breaks show "We'll be back shortly." A short cutover checklist would close this and the other rollout steps.

#### Minor
1. 7.2 `awaiting_fix`: `library` prints `awaiting fix from llama` without the reason (report.py:269-274). Point to `probe_estimates.py --time-one SLUG` for the reason.
2. 7.2 "status reports the clock as invalid": give the real line (`clock      last-good (invalid clock at …)` / `… no clock: open all week (invalid clock at …)`). Also say the alert resolves only at the next fill.
3. 7.2 fill sentence: "gets structural fill" mislabels the pool-short case. Say "gets fill; `schedule` labels the cause 'pool short' (too few or too short own shows) or 'longer than max_shows'".
4. Plan-lock sentence: say that the service holds the lock only during its plan/render steps while filling. A manual `plan`/`render` normally succeeds when the service isn't filling, as the publish-lock text in CLAUDE.md says for publish.
5. Copy-paste voicing loop: `for f in ann-*.txt` re-voices every script left from earlier exports.
   - Effects: repeat TTS spend; the replaced clip drops out of the pool for its quiet period; a planned, not-yet-encoded row using it re-plans as "clip changed" (pipeline.py:427-429).
   - Suggested: `for f in ann-*.txt; do [ -e "${f%.txt}.mp3" ] || emcee say "$f"; done`.
   - Also note that `emcee say` mixes the house `[tts] bed` under clips unless given `--no-bed`. Decide which is wanted.
6. Quiet period: name it `[station] quiet_minutes`.
7. Section order: 7.2 and 7.3 sit before 7.1, and "Rolling transmitter back" is unnumbered. The document title still says "(phases 1 and 2)".
8. CLAUDE.md `announcements` signature omits `--clock FILE`.
9. Hash durability: 684d323 is branch-only. If the branch is rebased or squashed rather than merged, the runbook's hash goes stale. The subject line is quoted next to it, which mitigates this. Merge with `--no-ff`, or re-check the hash after integration. "af46d72 is what was deployed to hugo" becomes historical once HEAD deploys. Consider "was deployed before the scheduler".
10. 7.2 "remove that one fragment by hand": add "with the service stopped", since the service appends to the file every tick.
11. Implicit clock described as "one all-week open block": it is a daily 00:00 open block (clock.py:205-209). This only matters when reading `schedule` output, which shows seven `open` occurrences a week.

### Assessment
**Task quality:** Needs fixes

**Reasoning:** Every load-bearing claim I checked against the code is correct:
- rollback targets, and what must be removed before rolling back;
- clock paths, strictness and last-good behaviour;
- the two-block rule;
- the fallback chain;
- `aired.jsonl` semantics;
- the epoch guard;
- the plan lock;
- read-only views.

Nothing would cost air time or data. The fixes are completeness and consistency:
- CLAUDE.md now contradicts itself on which phases are built, and that file propagates to every agent.
- The two new hugo alert codes are missing from the alert reference the runbook points to.
- An operator has no clock template or field list to write a first `clock.toml`.
- The player assets deploy is never mentioned.

All are doc-only edits.
