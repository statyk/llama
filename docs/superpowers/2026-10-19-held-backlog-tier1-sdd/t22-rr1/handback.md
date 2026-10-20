### Finding Verdicts

- **[Important 1] Stale live per-show-cost reading (~3e-11, "gate inert")**: ADDRESSED. The number and the word "inert" are gone. CLAUDE.md:128-131 now says the durable thing almost word for word from the review: the EWMA cannot size the batch, the gate still pauses at a ceiling but cannot project a show's cost, so size waves from the pilot's `meter: 5h A% -> B%` lines.
- **[Important 2] Length and shape**: ADDRESSED. Against merge-base(main), CLAUDE.md is +90 lines, inside the 80-100 target (it was +179). The Commands entries are now CLAUDE.md:108-155. The guards are ONE Architecture bullet at CLAUDE.md:495-536, one short sentence or clause per item (1a-1d, 2a-2c, 3a-3c, 4a-4d, 5a, 5c.1, 5c.3). Every listed cut was made:
  - the 14-file enumeration is now a pointer to `OUTPUT_FILES`;
  - the outcome-class list, the "Procedure:" sentence, the write-order parenthetical and the digest file list are dropped;
  - the history tags "(V, Checkpoint C)", "frozen copy of tier1-cp-B2", "kept at 0.5 at Checkpoint E" and "(Task 16b)" are dropped;
  - 1b and 3c are cut down to the predicate plus one clause.
- **[Minor] `_ENUMERATED_MIN_FILES`/`_COVERAGE`**: ADDRESSED. CLAUDE.md:517-518 names `_ENUMERATED_MIN_COVERAGE` in full, matching titles.py:181.
- **[Minor] Exit 2 is not only "library changed"**: ADDRESSED. CLAUDE.md:146-147 says "when the arms differ (digests, config fingerprint, setlist.fm configuration, show set)". That matches `_gates` in scripts/replay_holds.py:225-241, which checks setlistfm_configured, config_fingerprint, base-only/cand-only slugs and digests.
- **[Minor] "ONE fresh brief (the only LLM call)"**: ADDRESSED in CLAUDE.md:114-115 ("one fresh brief task, its only LLM work"). README.md:257 still says "its only LLM call" (see Out-of-Scope).
- **[Minor] vet also writes `notes.json`**: ADDRESSED. CLAUDE.md:152 says "written by gather, and by vet for 4a; `reapply` rewrites it". Verified against:
  - vet_research.py:334-336 (vet sets `notes.vet`);
  - gather.py:1562 (gather writes `ShowNotes(gather=..., vet=[])`, so "each gather replaces the file" holds);
  - reapply.py:131-132.
- **[Minor] 2b omits the item's-own-title arm**: ADDRESSED. CLAUDE.md:510-511: "one string or the item's title on every track".
- **[Minor] Name `ADJACENT_DAY_WINDOW = 1`**: ADDRESSED. CLAUDE.md:526 matches vet_research.py:18.
- **[Minor] 4d unmeasured, changes nothing in the backlog**: ADDRESSED. CLAUDE.md:528-530: "prompt wording, unmeasured offline; `reapply` never re-extracts, so it changes nothing in the backlog".
- **[Minor] 3c also exempts ordinals**: ADDRESSED. CLAUDE.md:521-522: "set-count and ordinal claims are ignored when qualified (`_NOT_SHOW_WIDE`), negated or scoped". This matches brief.py's `_claims`: counts pass both the `_NOT_SHOW_WIDE` and `_qualified` tests, while ordinals pass only `_qualified`. The sentence slightly blurs that `_NOT_SHOW_WIDE` applies to counts only. That is acceptable at one sentence.
- **[Minor] Evidence pointer should name the evidence doc**: deliberately left, as the controller accepted, not counted as open. `docs/superpowers/2026-10-19-held-backlog-tier1-evidence.md` does not exist yet. The header pointer to the plan (CLAUDE.md:497) is accurate for now and must be updated when Finish writes that doc.
- **[Minor] README "three resolutions" contradicts "a fourth route"**: ADDRESSED. README.md:189 now reads "three resolutions (plus a fourth for tapes with no titles, below)", which agrees with README.md:209.
- **[Minor] README `compare` example paths**: ADDRESSED. README.md:245 now uses `~/.llama-harness/base.json ~/.llama-harness/cand.json`.
- **[Minor] README "audio for never-packaged shows"**: ADDRESSED. README.md:257-258: "downloads any missing audio (first-time packages are the bulk)".

Load-bearing content check after the cuts (each item checked against the code):
- `show.json` LAST as the commit marker: kept (CLAUDE.md:116-119).
- Per-show lock span from the still-held check through the last write: kept (CLAUDE.md:115-116).
- `-dirty` refused on either side: kept (CLAUDE.md:123-124).
- Resumability (batch dir `sha256(list bytes)[:16]`, `list.json`, `progress.jsonl`, skipping `retryable: false`): kept (CLAUDE.md:125-127).
- Stop rule `STOP_AFTER_LLM_FAILURES = 3`: kept (CLAUDE.md:128). Its reset condition was cut; that is acceptable, since it lives in code.
- `notes.json` never reaches the LLM: kept (CLAUDE.md:153-155; models.py:216-221 agrees).
- `reapply` never delivers, plus the `re-deliver with:` line: kept (CLAUDE.md:120-122).
- 5c.2 dropped / do not re-add: kept (CLAUDE.md:534-536).
- "Sits beside the protected predicate" and needs-LLM: kept (CLAUDE.md:499-502).
- Also verified: "metro table fixed a priori" (spec :441, :982); `RIGHT_SHOW_MIN_TAPE_FRACTION = 0.5` "stays 0.5" (vet_research.py:20-25, kept at Checkpoint E); `OUTPUT_FILES` (replay_holds.py:182-186); the run-side `llama.__file__` refusal (replay_holds.py:58-65); `--untitled` everything-unresolved gating (pinned by ed8b0c5).
- Tests: the fix report states the suite (3761 passed, 1 skipped, 8 deselected). It is a docs-only diff, and no code changed in e408703..030caa7 (stat: CLAUDE.md and README.md only). Not re-run.

### New Breakage in the Fix Diff

All Minor. These are accuracy losses from compression; none is false in a way that would break code.
- **Minor, CLAUDE.md:126-127.** "A pacing gate runs before each show's lock" lost the qualifier "Single-show form has no list, batch dir or pacing gate". The gate exists only in `_reapply_list` (cli.py:3246, 3276-3298). `llama reapply <show>...` has none, so an agent passing many named shows gets no proactive pacing. Restore "(list form only)".
- **Minor, CLAUDE.md:505-506.** 1c dropped its "on a single-event date" condition. The code requires `len(events) == 1` (gather.py:1413). As written, 1c reads as if it also applies to two-event dates. Restore "on a single-event date".
- **Minor, CLAUDE.md:501-502.** "A show whose gather would reach an LLM call is needs-LLM" lost the second source, a stored `structure.alignment == "llm"` (replay.py:327-328). The third source, no `vetting.json`, is still covered at CLAUDE.md:113. Add "or whose stored alignment is `llm`".
- **Minor, CLAUDE.md:144-146.** "writes the reports in `replay_holds.OUTPUT_FILES` plus `predicted_list.json`, `structure_changed_list.json` … `pilot_list.json`": `OUTPUT_FILES` already contains the three lists (replay_holds.py:185-186), so "plus" is wrong. Use "including".

### Out-of-Scope Observations

- README.md:257: "(otherwise it asks for one fresh briefing, its only LLM call)". This has the same imprecision as the CLAUDE.md minor that was fixed: `generate_briefing` makes up to two attempts. The fix diff rewrapped this line and left the phrase. It is non-blocking; "its only LLM work" would match CLAUDE.md.
- Carried from the previous review, not verifiable from the diff: the `eotoband-2007-10-09` route's precondition, that `redo --from gather` leaves every track `unresolved`. It needs a harness run on that slug at Checkpoint G.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage. The evidence-pointer minor stays deferred by decision until the evidence doc lands. There are four new Minor compression losses (CLAUDE.md:126-127, :505-506, :501-502, :144-146), each a one-phrase restore. They are non-blocking.
