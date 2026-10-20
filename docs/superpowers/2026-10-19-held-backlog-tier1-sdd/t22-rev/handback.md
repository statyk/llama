### Spec Compliance

- ❌ Issues found:
  - **Shape requirement missed:** the brief asks for ONE Architecture paragraph, "each one sentence" (1a–1d, 2a–2c, 3a–3c, 4a–4c, 5a/5c). CLAUDE.md:554-625 is a 72-line bullet whose per-item "sentences" run 4–10 lines each (1b–1d alone is CLAUDE.md:565-577). The Commands entries add another ~107 lines (CLAUDE.md:108-214). Total +179 lines in a file loaded into every agent's context. Content is mostly accurate; the size is the problem (cuts listed under Important #2).
  - **Live reading in a durable doc, and it is false:** CLAUDE.md:153-156 says "`pacing-state.json`'s learned per-show cost reads ~3e-11, so the proactive gate is inert for this batch". Where it comes from: the spec (design.md:229-230, :877, :1123: "`3.0e-11` over 4,241 samples"), not the live file. Live `~/.llama/pacing-state.json` (read-only; mtime 2026-10-19 16:05) holds `per_show_delta: 2.4754619516377256e-09, samples: 4608`. So the number is already stale by ~80x. "Inert" also overstates: `pacing.decide` (pacing.py:224-229) still pauses when a meter is at/over its ceiling; only the projection part is useless.
- ⚠️ Cannot verify from diff: whether `llama redo <s> --from gather` on the delivered `eotoband-2007-10-09` ends held with every track `unresolved` (the precondition for the route at CLAUDE.md:170-173 / README.md:217-219). That depends on the live library and network data. The route matches the brief verbatim. The controller can check it with the harness on that slug.

Checks run and found TRUE (code at e408703):
- reapply: lock span, write order, needs-llm writes nothing, never writes reviews/provenance/research/ledger, the `re-deliver with:` line (reapply.py:68-147; cli.py:3226-3236, 3357-3360).
- reapply: `-dirty` refused on either side, sha/fingerprint refusal (reapply.py:166-176). Batch dir `sha256(list bytes)[:16]` + `list.json` + `progress.jsonl` (reapply.py:180-183; cli.py:3266-3271).
- reapply: resume on `retryable: false`, pacing gate before the lock (non-dry-run), `RateLimited` arm above `HerderError` with exit `1 if failed else 0`, `STOP_AFTER_LLM_FAILURES = 3`, reset only on a fresh brief that applied, `missing:` retryable, dry-run `summary:` line (cli.py:3272-3364).
- `input_digests` file set (replay.py:86-105). `briefing_reusable` fields, narration and normalised guard (replay.py:237-260). needs-LLM sources (replay.py:323-333).
- `fix --untitled`: the refused flag list matches every `--clear-*` in `fix`'s signature. `_untitled_counts`, filenames listed first, one confirm, `set_breaks=[]`, then gather → overrule → brief (cli.py:1611-1648, 2767-2806). The gather override path takes `[]` (gather.py:1246).
- replay_holds: `run`/`compare` flags, identity refusal exit 2, `--out`/`--scratch` overlap refusal, the 99% gate exit 3 and `--no-repro-gate`. `OUTPUT_FILES` matches the doc's list exactly. `CLEARING = ("clears","needs-brief")`, pilot of 10 with ≥2 reuse, lists carry `sha`/`config_fingerprint` (replay_holds.py:58-109, 167-186, 688-713, 715-790, 796-822).
- Guards: 1a/step 1 + S/swap/two-venue/1c/1d + V and override suppression (gather.py:1371-1447). `accept_short_tags` (gather.py:873-929). 2b classes (placeholders.py). `_GLUED_NUM_PREFIX` (titles.py:187). 3a/3b/3c (brief.py:40-60, 98-157). 4a constants and gate (vet_research.py:22-26, 181-220). 4c and day-00 (vet_research.py:52-113, 245-266). `encore_lost`, `closer_contradictions`/`filler_tail_closers`, 5c.3 fallback (structure.py:1183, jerrybase.py:287-360, :188).
- "No do-not-retune constant moved": `git diff $(merge-base main HEAD) HEAD` shows no change to `_TRACK_NUM_PREFIX`, `SHORT_FRACTION_OF_MEDIAN`, the tail-guard constants, `_RECOVER_*` or the sibling bands (risk: a doc claiming a protection the branch broke).
- 5c.2 is documented as dropped and not as behaviour (CLAUDE.md:622-624), consistent with Checkpoint F. V+S (Checkpoint C) and 0.5 + day-00 (Checkpoint E) are reflected.
- **4d** (assignment check 2): CLAUDE.md:614-615 describes it correctly as a prompt change that "affects only fresh extractions". It is not claimed as measured behaviour. It omits the spec's "unmeasurable offline, changes nothing in this backlog" (design.md:746-750) (Minor below).

### Strengths
- Unusually accurate for its density. Every flag, file name, exit code, constant value and message string I checked against code matched, including the exact `OUTPUT_FILES` set, the `--untitled` refusal list and the `RateLimited`-above-`HerderError` ordering.
- The reapply write order and the `show.json`-last commit-marker contract are stated precisely, and so is the partial-failure consequence. That is the load-bearing thing a future agent must not break.
- The `notes.json` entry states the right invariant ("never reach the briefing LLM") and the reason (the whole `show.json` is the prompt input, brief.py:255-256).
- 5c.2 is recorded as dropped with a do-not-re-add warning: good durable content.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **CLAUDE.md:153-156: stale live reading.** The number is ~3e-11; the live value is 2.48e-9 over 4,608 samples. "Inert" is also wrong, because the ceiling check in pacing.py:224-229 still fires. A live meter value in CLAUDE.md goes stale on the next run, and it already has. Fix: drop the number and say the durable thing: "the learned per-show EWMA cannot size this batch (spec 'Re-processing cost'); the gate still pauses at a ceiling but cannot project a show's cost, so size waves from the pilot's `meter: 5h A% -> B%` deltas, not `llama pacing`."
2. **CLAUDE.md:108-214 and 554-625: length, and departure from the brief's one-sentence-per-guard shape.** Concrete cuts, all redundant with the spec/plan, the code, or the README:
   - CLAUDE.md:174-206 (replay harness): replace the 14-file enumeration with "the report files in `replay_holds.OUTPUT_FILES` plus three lists". Drop the outcome-class list (`replay.classify` is the source, and it is incomplete anyway: no `still-held-package`/`newly-held`/`clean-changed`/`clean`). Drop the "Procedure: …" sentence: it is the plan's Checkpoint G and README.md:265-271 repeats it.
   - CLAUDE.md:119-127 (reapply): the write-order parenthetical and the digest file list duplicate the module docstring (reapply.py:1-11) and `input_digests`. Keep "show.json last = commit marker", drop the enumerations.
   - CLAUDE.md:554-625: cut run history that is not a rule: "(V, Checkpoint C)" :573, "a frozen copy of the tier1-cp-B2 rule" :577, "kept at 0.5 at Checkpoint E, not 2/3" :605-606 (the constant's own comment already says it), "(Task 16b)" :611. Keep the 5c.2 do-not-re-add line.
   - Tighten 1b (:565-569) and 3c (:598-601) to the predicate name plus one clause. The token-level fold lists live in `structure.py` and `brief.py` with their constants.
   - A reasonable target is ~80-100 lines total, not 179.

#### Minor (Nice to Have)
- CLAUDE.md:592: `_ENUMERATED_MIN_FILES`/`_COVERAGE`. The second constant is `_ENUMERATED_MIN_COVERAGE` (titles.py:221, 234).
- CLAUDE.md:184-185: "(exit 2, the library changed between runs)". `_gates` also exits 2 on config-fingerprint and setlist.fm mismatches and on show-set differences (replay_holds.py:225-241). Those are not library changes.
- CLAUDE.md:118: "ONE fresh brief (the only LLM call it makes)". `generate_briefing` makes up to two attempts (brief.py:262-275). Say "one fresh brief task".
- CLAUDE.md:207: "written by gather; `reapply` rewrites it with vet's notes". The vet stage also writes `notes.json` (vet_research.py:334-336), and that is where 4a's note comes from in a normal run.
- CLAUDE.md:583-585: the 2b class list omits the "item's own title on every track" arm of `recording_level_junk` (placeholders.py:151-160).
- CLAUDE.md:609: 4b's window is the spec-fixed constant `ADJACENT_DAY_WINDOW = 1` (vet_research.py:17). The impl prompt asked that new constants be named.
- CLAUDE.md:614-615: add "unmeasured offline; reapply never re-extracts, so it changes nothing in the backlog" to 4d (design.md:746-750).
- CLAUDE.md:598-601: 3c's negation and scope also exempt ordinal claims, not only counts (brief.py:156).
- CLAUDE.md:624-625: the evidence pointer names the plan. The plan's Finish section says `docs/superpowers/2026-10-19-held-backlog-tier1-evidence.md` will hold the numbers. Update the pointer when that doc lands.
- README.md:189: "A held show has **three resolutions**" is now contradicted by "A fourth route" at README.md:209. Make it "four" or reword.
- README.md:245: the `compare` example uses bare `base.json cand.json` while the `run` line writes `~/.llama-harness/base.json`. Use the same paths.
- README.md:257-258: "downloads audio for never-packaged shows". `build_package` fetches whatever track audio is missing, and the dry-run estimate counts shows with no `manifest.json` (cli.py:3341). Say "downloads any missing audio (first-time packages are the bulk)".

### Assessment

**Task quality:** Needs fixes

**Reasoning:** Factual accuracy against e408703 is high. Every flag, constant, exit code and file name checked out except the items above. But CLAUDE.md carries a stale live meter reading with an overstated conclusion, and the Architecture/Commands additions run to 179 lines against a one-sentence-per-guard brief. Both should be fixed before merge, since the cost lands in every future agent's context.
