# Owner-visible notes for the final whole-branch review (orchestrator summaries, not reviewer verdicts)

1. A lone `fix --overrule` on a show that is not held now takes the show lock (may wait behind a get) and snapshots before saying "not held".
2. Triage re-resolves each show via catalog.resolve_show -> iter_shows on every turn: ~1 s/turn warm (3 s cold) on 3983 shows, plan-mandated; a one-directory entry builder would fix it.
3. Removed-show message in triage is "no show matches <path>", not slice C's "the show was removed" (brief's choice).
4. Edit lines in `fix` now print after the redo's progress; triage's "metadata override updated" is echoed inside the unit and then rolled back on failure.
5. Process escape (T6): an implementer showed RED by temporarily reverting cli.py in the live worktree; restored, no harm found.

## Task 9 measurement (replay harness, base 6ba3be2 vs this branch 36473d8, 3983 shows each)
- First compare exited 3 (base reproduces 134/147 held non-needs-LLM shows). Ruled by the owner's side: the 13 held drift rows are known base drift (Tier-1 owner-rejected / not applied) — stored show.json from pre-Tier-1 code; identical in both arms; not this branch. DO NOT chase them.
- Second compare with --no-repro-gate (measurement only; its predicted_list.json is not for apply): venue_changes 234 shows (154 delivered, 65 city changes), 0 venue/city flag added or removed anywhere; 8 shows' flag sets change, all removals, all slice D (curly apostrophe); nothing newly held; predicted_list 5 rows.
- Outputs: ~/.llama-harness/small-fixes/cmp-norepro/ (read-only for you).

## Deferred minors
Every deferred minor from the per-task reviews is one line in deferred-minors.md (same directory). Triage which, if any, must be fixed before merge.
