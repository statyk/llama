# Junk short-keep: SDD record

Record of the subagent-driven build of "piece 4: junk short-keep" (branch held-backlog-junk-filter, from main @ e37f670 / v2.17.0). Spec: docs/superpowers/specs/2026-10-23-junk-short-keep-design.md. Plan: docs/superpowers/plans/2026-10-24-junk-short-keep.md. Acceptance write-up (Checkpoints A, B and C with the operator's rulings verbatim): docs/superpowers/2026-10-23-junk-short-keep-evidence/acceptance.md.

The cycle was run by six successive peer orchestrator sessions, whose parent was llama-db (relays were on its RELAY-NOW): orch (c03ad18d), orch-r1 (68216777), orch-r2 (0c3554ba), orch-r3 (69caf142), orch-r4 (7126b474) and orch-r5 (ed6a3f15). The ids are the ones in each ledger's header. Review mode was Opus: every reviewer was Opus (the final whole-branch review `verdicts/tfin-rev.md` included), except the Checkpoint hand-check checkers (`t9-hc1`, `t9-hc2`, `t10-a4hc`), which were Sonnet. Implementers were Sonnet or Opus per task and per ruling (see the ledgers for each dispatch and its model).

Contents:

- `orch/`, `orch-r1/`, `orch-r2/`, `orch-r3/`, `orch-r4/`, `orch-r5/`: each orchestrator's `ledger.md`, copied byte for byte. orch-r5's ledger was still being written when this record was committed (it was copied as it stood at Task 23); the orchestrator re-syncs it at the finish, so the final ledger is the one in the finish commit, not necessarily this copy.
- `orch-r5/checkpoint-c.md`: the Checkpoint C report (Task 22) with its nine questions and recommendations; the operator's rulings are in the ledger and in acceptance.md.
- `orch-r4/fw1-rulings.md`: the operator's and llama-db's 2026-10-25 rulings on the format choice (I-1) and the doubled derivatives (I-2) that opened fix wave 1.
- `verdicts/<task>.md`: the `handback.md` report of every subagent task dir under the run's `.superpowers/sdd/junk-short-keep/` that has one, copied unedited: implementers (`t*-impl`), reviewers (`*-rev`, `*-rr*`), fix rounds (`*-fix*`), the hand-check and pre-screen runs (`t9-*`, `t10-a4hc`, `t15-p4read`), the segue investigation (`t22-seg`), the mutation run (`t21-mut`), the final branch review (`tfin-rev`), the four fix waves (`tfw1-*` to `tfw4-*`) and Task 23 itself (`t23-impl`, `t23-rev`, `t23-fix1`, `t23-rr1`, added by the orchestrator at the finish). 94 task dirs.
- Task dirs without a `handback.md`: `tfw2-rev` only. It is the dead claim from orch-r4's meter stop (the dispatch directory was claimed but no agent was ever launched); its work was done as `tfw2-rev2`, whose report is in `verdicts/`. The orchestrator dirs (`orch*`) carry ledgers instead of handbacks.
- `mutation.md`: the mutation record of Task 21 (written earlier, left as committed).

Not committed here:

- Harness outputs (arms, compare directories, hand-check packets, reuse and gate dumps, migration dry runs) live under `~/.llama-harness/piece4/` and are not committed. The acceptance write-up names the paths and sha256 of the ones it relies on.
- The briefs, scripts, diffs, review packages and per-task logs of the run stay in the worktree's git-ignored `.superpowers/sdd/junk-short-keep/`. No source tree and no diff package is copied into this record.

## Filed follow-ups

Named and not closed by this branch (the spec's section 7 has the accepted limitations in full):

- **Segue classes.** B: run-on chosen descriptions (`parse_setlist`'s documented merge). C: `blend_segues`' exact-title pooling of `Space` and `Jam` where the donor's own alignment does not cover the track.
- **The LLM `align_structure` branch.** FW4 item 2 (the donor's own alignment wins over pooling) does not apply there, and pooled marks still feed `correspondence._merge_legal` and the `align_structure` prompt.
- **An in-track flow into a non-filler solo**, `warrenzevon-1994-02-07` #15 (`^ > Dr. Babyhead Solo`), already shipped today.
- **4 real segue gains declined under a wrong shipped set label** (upstream of the guard).
- **A `_vbr` preference flip** (`PREFER_VBR_DERIVATIVE`) needs a duration tie-break or refusal first: a flip would air truncated `_vbr` copies in all 13 library / 48 cache duration-mismatched pairs (Checkpoint C Q1).
- **FW2 M2.** A pair whose copies are both operator-excluded is counted twice in its format's running time. Latent: multi-format items only, 0 library shows.
- **The 2 re-selections that orphan operator overrides**, `gratefuldead-1970-05-06` and `gratefuldead-1985-11-10`: the bulk apply surfaces them (the dangling-key refusal names the `llama fix --clear-*` route) and they are fixed by hand afterwards (Checkpoint C Q3).
- **The 20 GD re-selections** (the selected recording changes once doubled track counts stop steering `select_recording`) re-gather and re-research at the bulk apply (Checkpoint C Q4). Stale `_vbr` excludes on the 5 hand-repaired shows are left (Q5).
- **Reapply's path extended to packaged and delivered shows** (spec 5.2), the bulk apply of pieces 1-5, and its apply lists: planned separately.
- **Deferred minors** carried in the ledgers (each task's "minor (deferred)" lines, the final review's triage in `verdicts/tfin-rev.md`, and FW4's N1-N4).

## Dropped from the record

Rule carried over from the piece 2 and piece 3 records (it cost a history rewrite there): copied or mutated source trees are never committed. Size policy: only files of 256 KB or less; no file exceeded it, so none was skipped. 99 files (including `mutation.md`), 900,003 bytes, before this README was added; at the finish the orchestrator re-synced `orch-r5/ledger.md` and `orch-r5/checkpoint-c.md` and added the four Task 23 verdicts.
