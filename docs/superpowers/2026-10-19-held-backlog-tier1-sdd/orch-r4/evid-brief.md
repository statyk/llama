# evid — write `docs/superpowers/2026-10-19-held-backlog-tier1-evidence.md` + the CLAUDE.md pointer

Docs only. No code change. One commit: `docs: held-backlog Tier 1 evidence (checkpoints A-G, apply, fix wave)`.

## Sources (read; every number you write must come from one of these, cited by path in the doc's "Sources" section)
- Plan: `docs/superpowers/plans/2026-10-19-held-backlog-tier1.md` — the "Checkpoint A" … "Checkpoint G" sections and every "**Recorded at Checkpoint X**" block (lines ~1194, 1745, 2077, 2257, 2468, 2709, 3310).
- Spec: `docs/superpowers/specs/2026-10-19-held-backlog-guard-fixes-design.md` (stakes, slices) — only for naming slices.
- SDD ledgers (gitignored; read them, quote numbers, but cite them by role, e.g. "orch-r3 ledger, 02:07 G1 line"): `.superpowers/sdd/tier1/orch/ledger.md`, `orch-r1/ledger.md`, `orch-r2/ledger.md`, `orch-r3/ledger.md`, `orch-r4/ledger.md`. Checkpoint measurements and operator decisions are in their timestamped lines (grep `Checkpoint`, `MEASURED`, `Ruling:`, `approved-`, `rejected-`).
- Harness outputs (read-only): `~/.llama-harness/cmp-G2-held/summary.txt`, `~/.llama-harness/cmp-fw6-all/summary.txt`, `~/.llama-harness/G7-scoped.json` (only if you need a count; prefer the ledger lines).
- Final review verdict: `.superpowers/sdd/tier1/final-rev/handback.md`; deferred list: `.superpowers/sdd/tier1/orch-r4/deferred-minors.md`; DSO diagnosis: `.superpowers/sdd/tier1/dso-diag/handback.md`.

## Required structure (keep it tight: aim for ~150-250 lines of markdown; tables over prose)
1. **Purpose and scope** (3-5 lines): the 2026-10-19 survey of ~1,073 held shows; Tier 1 = deterministic, LLM-free guard fixes + replay harness + `llama reapply`; spec and plan paths.
2. **Method** (short): base/prev/cand arms, `compare`, the reproduction gate, predicted lists tied to sha + config fingerprint, operator hand-checks at each checkpoint, pre-screen, pilot, waves.
3. **Per-checkpoint table A–G**: for each checkpoint — what was measured (arms, the key counts), what the operator approved / rejected (approved-B..F, rejected-D/E/G with counts and the reason classes), and decisions recorded (e.g. 5c.2 dropped at F; 4a constant fixed at E; I1 fixed before the apply at G). Use the plan's "Recorded at" blocks as the authority; where a ledger line and the plan disagree, the plan wins and you note the discrepancy.
4. **The apply (G5 pilot + G6 waves)** — these numbers are verified; use them verbatim:
   - predicted_list 125 rows (103 needs-brief/fresh + 22 clears/reuse) after dropping 30 rejected slugs (D 5, E 6, G 19 = 13 pre-screen-flagged + 6 encore-inside-last-set); structure_changed_list 11 rows NOT applied.
   - Pilot 10/10 cleared as predicted (02:24–02:45, 2026-10-20). Wave 1 (38): 37 cleared, 1 held. Wave 2 (38): 37 cleared, 1 download failure. Wave 3 (39): 36 cleared, 2 held, 1 download failure which cleared on retry. Totals: **121 of 125 cleared**; 4 held:
     - smashingpumpkins-1994-04-17 — fresh brief held by `briefing mentions unknown song: Girl Named Sandoz` (a merged-tease title the guard did not split; fixed by fw5);
     - soundtribesector9-2006-06-11 — fresh brief held by `briefing claims 2 sets but structure has 1`;
     - darkstarorchestra-2012-05-19 — fresh brief held by 21 unknown-song flags; cause: tag titles carry joined track numbers (`01-Hell In A Bucket`), not a bad brief (fixed by fw6); the show had never been briefed before (held at gather by a blank jerrybase venue that 1a removed);
     - gratefuldead-1985-06-16 — archive.org HTTP 500 on track downloads (t01 twice, then t09), retryable; show.json never committed.
   - 0 new LLM failures, 0 usage refusals/pauses, 0 writes outside the lists, 0 re-deliver lines; meter cost: pilot+waves ≈ 5h-window 10%→14% (wave 1) and 0%→9% (waves 2–3 in the next window), weekly 3%→5%.
   - G7 post-run harness (read-only, 166 slugs = 125 + 11 + 30): 121 applied shows packaged/clean/0 field changes; 4 held as above; all 41 excluded rows identical to their G2 rows in every field.
   - Operator rule amendments made during the waves (fresh-guard holds allowed; download failures retried once) — say who decided (the operator, via llama-45).
5. **Post-apply fix wave** (table: task, what, commit range, review outcome): fw4 set-count `of` lookahead (b7147e0); fw5 comma-merged titles, narrowed to the G2b gate in review (09d50fd, 1089b76); fw1 `--untitled` encore/status (0c916da); fw6 joined track-number strip (3c75471, 33f44b4) with its census (8 of 13,339 cached items) and harness (exactly 5 shows change, 137 titles; mountaingoats-2017-06-02's proposed set breaks move [12,15,23]→[11,15,23] vs stored [10,15,23]); fw2 reapply `--allow-structure-change` (c106103, 00b0c6e, 9d5884b); fw3 stale-briefing drop (e7a029e); fw7a (19af9de..c255ca7); fw7b docs/tests (b30bed5..82fc3a3). Final suite at 82fc3a3: 3803 passed, 1 skipped, 8 deselected.
6. **Deferred minors** — summarise `orch-r4/deferred-minors.md` in ≤ 15 lines (behavioural ones by name; hygiene ones as a count + pointer).
7. **Operator follow-ups** — from the deferred file's last section, verbatim in substance.
8. **Sources** — paths. Note that `.superpowers/` is gitignored and must be copied out before the worktree is removed (plan "Finish").

## CLAUDE.md pointer
In the "**Tier 1 held-backlog guards**" bullet, the first sentence cites the spec and plan; add `; evidence: docs/superpowers/2026-10-19-held-backlog-tier1-evidence.md` there (wrap to the surrounding width). If the plan or CLAUDE.md elsewhere has a placeholder "evidence-doc pointer" note, resolve it.

## Done when
`./.venv/bin/python -m pytest -q` still green (state the count; scripts tests read nothing from docs, but run it anyway); one commit; handback lists every number in the doc that you could NOT trace to a source (should be none).
