# Checkpoint B2 — marking dry run with the fifth trigger (read-only)

Code: bulk-apply at **f1f447db** (T15c: newly held with no visible change is marked; review Approved, no Critical/Important). Tree clean. All commands from the worktree with its own interpreter; `--campaign-dir ~/.llama-harness/bulk/campaign-b2` (scratch). `find ~/.llama -newer <start marker>` found no file written; the station was only read.

1. `replay_holds.py run --all --out ~/.llama-harness/bulk/cpb2/arm.json` — rc 0; arm sha f1f447db, generated 2026-10-27T18:22:13.245029+00:00, 3983 shows: clean 1252, clean-changed 1709, needs-brief 3, needs-llm 654, newly-held 220, still-held 135, still-held-package 1, structure-changed 9 (identical to Checkpoint B's arm). sha256 `18b97967fce92bd2b62d40bb048a2b8380c168147b4372c0cee314197d801c93`.
2. `freeze` — rc 0: 654 frozen. 3. `reselect-check --write` — rc 0: 17 of 20.
4. `mark --arm …/cpb2/arm.json` (dry run) — rc 0. Output `~/.llama-harness/bulk/cpb2/mark.out` (sha256 `48dbe620f9117b0c98ba298f69b1f76008db15bd640f68b86a20963a8508daf9`):

```
marking plan: 2640 show(s)
  changed by the held-backlog fixes: delivered unvoiced 1322, delivered voiced 116, packaged 347, briefed 13, held 80
  replay needs an LLM call: delivered unvoiced 344, delivered voiced 20, packaged 99, briefed 4, held 185
  stored briefing fails today's guard: delivered unvoiced 1, delivered voiced 0, packaged 2, briefed 0, held 1
  recording re-selection: delivered unvoiced 11, delivered voiced 0, packaged 4, briefed 0, held 2
  newly held by today's checks: delivered unvoiced 1, delivered voiced 0, packaged 88, briefed 0, held 0
by arm outcome: clean 2, clean-changed 1683, needs-brief 3, needs-llm 654, newly-held 219, still-held 70, structure-changed 9
unreadable station manifests: 0
unreplayable, not marked: 0
unplannable shows: 0
emcee running: no
dry run: nothing written (pass --apply)
```

## Counts by reason × state

| reason | delivered unvoiced | delivered voiced | packaged | briefed | held | total |
|---|---|---|---|---|---|---|
| changed by the held-backlog fixes | 1322 | 116 | 347 | 13 | 80 | 1878 |
| replay needs an LLM call | 344 | 20 | 99 | 4 | 185 | 652 |
| stored briefing fails today's guard | 1 | 0 | 2 | 0 | 1 | 4 |
| recording re-selection | 11 | 0 | 4 | 0 | 2 | 17 |
| **newly held by today's checks (new)** | **1** | 0 | **88** | 0 | 0 | **89** |
| total | 1679 | 136 | 540 | 17 | 268 | **2640** |

Was (Checkpoint B, d1bb0127): 2551. The difference is exactly the 89 B-90 class-A shows (newly held, no visible change): 88 packaged get a library record only; 1 delivered unvoiced (`aquariumrescueunit-2005-01-08`) gets a library record and a station mark. Newly-held rows marked: 219 of 220 (was 130); the one left is the label-only `stantonmoore-2005-05-14`, unmarked by rule. Voiced 136 (unchanged; none of the 89 is voiced), unreadable station manifests 0, unplannable 0, emcee not running. The other four reasons' counts are byte-for-byte the same as Checkpoint B's.

Note: this arm predates the backfill (not applied), so newly held is 220 here; after the backfill --apply and a fresh arm the newly-held population shrinks to the shows whose flags are still listed.

Nothing has been applied.
