# Handoff: paragraph-aware chunking (emcee), 2026-10-26

**Where:** branch `emcee-paragraph-chunking`, worktree
`.claude/worktrees/emcee-paragraph-chunking` (cut from `main` @ `6fe245b5`). It needs
its own `.venv` before any test run (CLAUDE.md, worktree rule).

**State:** the design spec is written and has had its builder check:
`docs/superpowers/specs/2026-10-26-paragraph-chunking-design.md`. The operator
answered both builder-check questions (content-filter narrowing (a) and fallback (b);
the `[tts] room_tone` switch, default on). Nothing is built.

**Next, in order:**

1. **Spec review** (invoke the `spec-review` skill). Review mode **Opus** (set in the
   spec's status line). The stakes paragraph is in the spec; strict surfaces are the
   content-filter path (`_locate_block`, the `rephrase` repair) and the render-cache
   key. No Sonnet reviewers.
2. **Plan** (`superpowers:writing-plans`), reviewed the same way.
3. **Build** via subagent-driven development. Likely more than 3-4 tasks (prompt,
   packer + splitter fix, room tone, content-filter path, config + cache key, docs),
   so per `~/.claude/CLAUDE.md` launch a peer orchestrator on Opus (`sdd-delegation`).
4. **Acceptance listening check** before release: one Kurt (Qwen) and one Phil
   (Voxtral) segment voiced end to end with a real scriptwriter run, with bed. Voxtral
   is metered (the operator has a second key now; still keep it small).

**Operator-side actions, independent of the build (the operator's call):**

- Point Kurt at the un-evened reference: `emcee presenter edit kurt` with
  `voice_clone = ~/.emcee/samples/kurt1.wav` (same transcript). Kurt's clone hash
  changes, so his clips re-render on his next voicing.
- Add `live,Lyve,` to `~/.emcee/pronunciations.csv` (passed on Qwen and Voxtral).

**Evidence and tools:** the throwaway harness and every listening page are in
`~/.llama-harness/tts-experiments/` (see the spec's Evidence section). Findings are
also in project memory, `llama-qwen-tts-tuning`.

**Also on `main` this session (merged, not pushed, not released):**
`6223b31` emcee status TTS view + faster scan + `scripts/backfill_tts_record.py`
(applied? check `emcee status`: Phil/Jimmy rows read `voxtral`/`mlx_audio` once the
operator ran `--apply`); `9b60906` scriptwrite prompt bans present-anchored time and
a time of day. Both reach the operator's installed `emcee` only with a release.
