# t9-rev handback: review of 22f565a..9388d09 (fix round 2: B4, G1, D1, R1, R9)

Spec: ✅
Quality: Needs fixes

One Important finding: a test-strength gap on the branch that does R1's main job. It is a one-line fixture change. Everything else is Minor.

## What I checked
- **G1 predicate equals today's LLM condition.** The refactor at `stages/gather.py:1386,1388,1404,1420` preserves behaviour:
  - `anchor_note` is set exactly when `anchored is not None` (`:1355-1363`). So in the `elif` chain the old `elif canonical.items and result.coverage < thr` already implied `anchored is None`.
  - `result` is replaced only inside `if anchored is not None`, so `result.coverage` is the same object on the path where `today_llm` can be true.
  - `threshold` is the same `structure_cfg.align_coverage_threshold`.
  - The owned-flag expression is identical to the old inline one.
  - `decide_taper` has no other production caller (grep: gather and `scripts/taper_probe.py` only). `replay`/`reapply` go through `compute_gather`.
- **B4 semantics match the ruling.** A numbered break is a step-1 label change between two non-`encore` labels, which is right because labels are `1|2|3|encore` per `models.py:91`. "Before the hit" means k in [0, h-1], so a change at h-1→h counts and a change at h→h+1 does not. `boundaries` is never empty, because placement requires ≥2 groups and sets run consecutively from 1. A short `today_sets` is guarded.
- **Veto order** (placement → B4 → (d) → G1). Every veto only reduces ownership, so the order changes reason strings only, never ownership.
- **Attribution and text.**
  - "(llama-db reading of operator ruling (d), 2026-10-22)" appears in the code comments and both spec bullets.
  - R9 now reads "confirmed by llama-db, 2026-10-22" at spec :318, taper.py :78 and taper.py :303.
  - The D1 limitation is verbatim apart from the capitalised first letter and the final period. The parenthetical after it is accurate.
  - The two extra limitation lines are present.
  - My read-only probe of the library at HEAD found darkstarorchestra-2009-11-14, deadandcompany-2015-10-29 and stringcheeseincident-2005-03-25 all `has_encore=True` and still owned. So G1 does not make that limitation stale.
- **Global constraints.**
  - `git diff main -- packages/llama/src/llama/setlist.py` is empty (0 lines).
  - A grep of the changed lines for every protected name and constant, `conflicts`, `add_argument` and `config` found nothing.
  - No new config keys or flags.
  - The relaxation in `replay.py` is untouched, so it still keys on ownership alone. G1 is a veto inside the ownership decision, not a relaxation predicate.
- **Tests run in the live worktree.** taper, gather, replay, reapply, replay_holds and taper_probe: 795 passed. `llama.__file__` resolves in the worktree.
- **New tests that fail on pre-fix code.**
  - B4: the real-case test, just-before-the-hit, next-item fallback.
  - G1: the 4 real cases, the inverse, and gather's exactly-today test.
  - R1: the new tier test.
  - The inverse and conjunct pins are guards, not behaviour changes, and the implementer's mutants kill them.

## Findings

**Important: R1's needs-LLM-base branch is untested, and it is the branch that makes the tier work on real data.**

Location: `scripts/replay_holds.py:635` (`_segues_before`), test `scripts/test_replay_holds.py:1226`.

`compute_legs` runs the full gather and diff even for a stored-`llm` show and only then appends `stored alignment llm`. So a base-arm needs-LLM row carries `segue_changes`: its deterministic step-1 segues against the stored LLM segues, which is exactly D1's loss. The candidate's taper-owned row carries the same changes, because segues come from step 1 in both arms. Only the `needs-llm → []` branch keeps such rows out of "provenance only".

The test's `seg-llm` base row sets `segue_changes=[]`, so it cannot tell the branch apart from plain `b["segue_changes"]`.

Mutant M1, run in a scratch `git archive 9388d09` copy with PYTHONPATH shadowing proven and the prediction logged first: `return list(b.get("segue_changes") or [])`. Predicted to survive; it **survived** all 88 tests in test_replay_holds and test_taper_probe. Control M2 (`segues_differ=False`) was caught by the new test.

Real data, `~/.llama-harness/piece2/accept/{base,cand}.json`: of 57 non-held rows with a needs-LLM base and a newly owned candidate, 44 carry base `segue_changes` identical to the candidate's non-empty ones. Under M1 all 44 would drop silently from `segues changed` to `provenance only`, and that tier is what the D1 limitation says lists these rows.

Fix: in the test, also set `_row(b, "seg-llm")["segue_changes"] = lost`, the realistic shape. It still lands in `segues changed` and kills M1.

**Minor: the probe docstring files G1's stored proxy under the wrong heading.**

Location: `scripts/taper_probe.py:24,31`.

The heading reads "Judgment calls (each errs toward the taper owning LESS)", but the stored proxy errs both ways:
- false where today's code would now reach the LLM branch but the stored show did not, so the probe owns more;
- true where current code would now anchor or align, so it owns less.

The bullet itself describes the proxy honestly. Only the heading claim is wrong for it. Say "approximate, direction mixed", or move the bullet out from under that heading.

**Minor: B4 takes the earliest hit, which leans toward owning more; it is a documented "my call".**

Location: `taper.py:787` (`h = hits[0]`).

Using the earliest hit means a set-1 first song that also appears in an unrecognised leading block escapes the veto. That is the B4 class itself: in SKB 2000-03-31, `Rainbow's Cadillac` is played in both the Happy Hour set and Set 1.

I ran a read-only probe over the library, with stored labels standing in for step 1. Among 628 owned rows, 15 have set 1's first hit item matching more than one track in the set-1 window. Only joerussosalmostdead-2019-09-28 (item `Jam`) would flip with the latest hit instead. The exposure is small. It is listed so llama-db can rule on it if they want; no change is requested.

**Minor: `today_reaches_llm` defaults to the own-more value.**

Location: `taper.py:797`.

The default `False` means any future caller that forgets the argument silently owns more. Today gather is the only production caller, and mutant G1d pins that wiring. Making the argument a required keyword would force every caller to choose. It would touch many unit-test call sites, so it is optional.

**Minor: two small spec gaps.**

Location: spec `:408` and `:596`.
- The §4 low-confidence paragraph could say that, since G1, the owned low-confidence flag can arise only on an encore-marked taper. The same paragraph also leaves out the "canonical items" conjunct; that omission predates this round.
- The limitation example furthur-2012-07-08 carries operator `set_breaks: [7]` / `encore_after: 17` in `~/.llama/shows/furthur-2012-07-08/overrides.json`. Production ships the override, so the fold is visible only in the harness's override-ignoring mode. A few words saying so would keep the example from reading as a production case.

## ⚠️ Cannot verify from the diff
- Whether `compute_gather`'s real `today_llm` is True for the 4 named G1 shows under current code. The unit tests pass the predicate directly and use a stand-in step 1 (stored labels with the LLM encore relabelled to set 2), which was not re-measured. The orchestrator's replay re-run is the measurement.
- B4 on stevekimockband-2000-03-31 through the real gather. The probe cannot see it (override or tautological titles). Only the replay arms with the kept title overrides exercise it.
- G1's library and gate yield cost (13 library flips, including 2 C4 "better than stored" rows and 1 gained segue). The ruling decides it; it was reported to the manager.

Scratch: `~/.llama-harness/piece2/accept/work/t9-rev/` (hitprobe.py and the mutant copies S0, M1, M2). Log: `$D/t9-rev/t9-rev.log`.
