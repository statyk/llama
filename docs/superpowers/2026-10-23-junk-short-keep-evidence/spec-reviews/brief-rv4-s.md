You are a strict-surface reviewer checking ONE section of a design spec against a fixed scenario list. You are a reviewer only: write no files except the three protocol files below, make no git writes, and run nothing on remote hosts. Return your review as your final text reply.

## What to review
Read the frozen draft at /private/tmp/claude-501/-Users-shawn-projects-llama/2ee2e07b-09e3-44a9-ac41-83697a0e9d2c/scratchpad/piece45/review/spec-r4-frozen.md. Section 4 (positional overrides re-keyed by filename, the migration and its runbook) is what you judge. Read the rest of the spec for context only, and report on it only where it interacts with section 4. Do not open other copies of the spec or any git history.

## Context (read-only)
- The code: worktree /Users/shawn/projects/llama/.claude/worktrees/junk-filter, which is identical to main @ e37f670 (packages/llama/src/llama/: models.py Overrides, workspace.py, catalog.py iter_shows/resolve_show, cli.py _edit_overrides/fix/triage/redo, stages/gather.py, replay.py, reapply.py).
- The repo CLAUDE.md.
- The installed release binary ~/.local/bin/llama (v2.17.0). You may run `--version` / `--help` on it, and you may run e37f670 model code in the repo venv (/Users/shawn/projects/llama/.venv/bin/python) against scratch JSON written in the scratchpad dir /private/tmp/claude-501/-Users-shawn-projects-llama/2ee2e07b-09e3-44a9-ac41-83697a0e9d2c/scratchpad/piece45/rv4-s-scratch/. Never touch ~/.llama.

## Stakes
The migration rewrites hand-authored overrides.json for 606 shows, which hold 3,203 titles, 427 set breaks and 365 encore keys. A silent loss or a silent re-point of an operator override is the worst outcome. A loud refusal that has a documented way out is acceptable.

## Design under test
Section 4 now uses a whole-library non-audio SNAPSHOT: dry run and repairs under the still-installed v2.17.0, `--snapshot`, install the new release, `--apply` under a workspace lock with per-show re-check and raw-JSON edits, and `--restore <snapshot>` as the only undo (wholesale; discards everything since). A previous reviewer checked an earlier per-show-undo design; ignore that history and judge this text.

## Scenario list: walk through EVERY one, and for each say PASS (with the spec text that makes it pass) or FAIL (with the defect)
1. Normal run: dry run reports 0 refused, then --apply, then the new binary gathers every show.
2. Dry run refuses k shows. Follow the spec's repair route for each refusal reason, using the old binary while the library is all-legacy, and repeat until 0 refused.
3. SIGKILL / Ctrl-C at every point inside --apply's per-show write sequence, and between shows. Then: re-run --apply; or run --undo; or run the old binary; or run the new binary.
4. --restore: right after the migration; after edits, gathers and the bulk apply; interrupted mid-way; run twice; with shows created after the snapshot; with audio already re-packaged; with a station copy re-delivered.
5. Version skew: v2.17.0 run on a library that is partly or wholly migrated; the new binary run on a library that is wholly or partly legacy, or holds a mixed file. Cover both reads (status/show/listing) and writes (fix/triage/--no-run).
6. A writer edit on a legacy file before the migration, under each binary, including fix --no-run.
7. A writer edit after the migration, before and after the show is re-gathered under the new rule: --set-title N, --set-breaks, --set-encore, --clear-*, --exclude of a keyed file, --untitled, and triage [t]/[u].
8. set_breaks: [] (forced no breaks), titles {} and encore-only files, through the migration, undo and gather.
9. Harness and replay: a base arm at e37f670 run before and after the migration; apply lists generated before and after; reapply on a migrated library.
10. Two writers at once: the migration running while a fix/redo/triage holds the show lock; and the sweep loop.
11. A metadata-cache refresh between the dry run and --apply, or after the migration (a dangling filename key).
12. The gates: snapshot missing/stale/corrupt; the PATH binary is old, new, a dev build, absent, or more than one llama is on PATH; a llama process running; --restore after the old binary is reinstalled.

Then list any OTHER defect on the migration surface you find. Keep each finding in the usual format:
- [Critical|Important|Minor] title / Where / Problem / Evidence / Failure scenario / Suggested fix

End with `TOTAL: <n> findings (<c> Critical, <i> Important, <m> Minor)` and a one-line verdict: is section 4 ready for a plan?

## Protocol (D=/private/tmp/claude-501/-Users-shawn-projects-llama/2ee2e07b-09e3-44a9-ac41-83697a0e9d2c/scratchpad/piece45, task=rv4-s)
1. Your first action is `touch "$D/rv4-s/rv3-s.log"`. Echo a progress line into it after each few scenarios.
2. Write your full review to `$D/rv4-s/handback.md`, THEN touch `$D/rv4-s/done`. Also return the full review as your final reply.
3. If `$D/TAKEN_OVER` or `$D/taken-over/rv4-s` exists, stop.
