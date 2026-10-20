Fix round 1 for fw7b (from the orchestrator). Read the Opus verdict: /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1/fw7b-rev/handback.md. Fix Minors 1-6 and the duplicate import:
1. CLAUDE.md ~112-113: the stored `"llm"` alignment lives in show.json (`structure.alignment`) — move it to the gather clause.
2. README.md:257: "its only LLM call: one task of up to two attempts" → "its only LLM work: one brief task of up to two attempts".
3. scripts/test_replay_holds.py:439: `_two_arms(...)` call with three positional args → keywords.
4. Re-wrap every line the branch's fix wave added/rewrote in CLAUDE.md (115, 134, 135, 142, 154, 513, 530, 535 per the verdict; re-check) and README:257 to the surrounding ~80-column width. Wording unchanged.
5. CLAUDE.md ~126-128: only the `--from-list` dry-run prints a summary line; and the dry-run DOES predict the skip (`would: <slug> -> skipped: structure changed` / names form `-> dry-run: skipped: structure changed`) — correct the sentence.
6. Add a test pinning the names-form dry-run skip line (`reapplied: <slug> -> dry-run: skipped: structure changed`).
7. test_stage_brief.py imports `briefing_guard` twice — drop the duplicate.
Full suite; one commit `docs,test: fw7b review minors`. Append to fw7b-impl/handback.md and touch `$D/fw7b-impl/done-r1`. Check takeover flags before committing.
