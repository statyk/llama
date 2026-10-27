# Paragraph chunking: SDD record

This is the record of the subagent-driven build of paragraph-aware chunking for emcee.

- **Branch:** `emcee-paragraph-chunking`, cut from main @ 6fe245b5.
- **Build start:** a25b334c / 9f3aadec.
- **Spec:** docs/superpowers/specs/2026-10-26-paragraph-chunking-design.md
- **Plan:** docs/superpowers/plans/2026-10-26-paragraph-chunking.md
- **Pre-build reviews:** the spec and plan reviews are in `spec-review/` and `plan-review/` here.

## How the build ran

One peer orchestrator session, `orch` (5419dfd4), ran the whole cycle on 2026-10-26 from 09:03 to 10:24 EDT, with no relay. Its parent session was `emcee`.

**Review mode was Opus.**
- Every reviewer was Opus, including the final whole-branch review (`verdicts/final-rev.md`) and its re-review (`verdicts/final-rerev.md`).
- Every implementer and fix round was Sonnet; no task was escalated to Opus.

**Combined reviews on Tasks 1 and 2.** Each got one combined spec-and-quality review (`t1-rev`, `t2-rev`). At the parent's request, a separate Opus code-quality pass over both (`t12-qual`) followed. It found two Important missing tests, fixed in 8fa473df.

**Two reviewers per task from Task 3 on:** spec compliance (`t*-spec`), then code quality (`t*-qual`).

**Task 6 (the content-filter narrowing) is the strict surface.** Both its reviewers got the spec's Stakes paragraph verbatim.

**Final review.** It returned READY WITH FIXES: 0 Critical, 1 Important, 3 Minor. All four were fixed in 278c1757 and 3aa6d279 (`verdicts/final-fix.md`), and the re-review confirmed it.

**One deferred minor, done at the finish.** M4, the silent content-filter fallback, was added after the run by the parent session in e6c0ba33, with its own Opus code-quality review (`verdicts/m4-rev.md`).

**Suites.**

| | Baseline (9f3aadec) | After the build (3aa6d279) |
|---|---|---|
| Full suite, `./.venv/bin/python -m pytest -q -p no:cacheprovider` | 5920 passed, 1 skipped, 8 deselected | 5998 passed, 1 skipped, 8 deselected (the parent re-ran it) |
| emcee only | 943 passed | 1021 passed |

**Acceptance listening check.** The operator ran it on 2026-10-26 (Kurt on Qwen, Phil on Voxtral) and judged the chunking good. A separate Kurt finding: "live" (as in concert) is still mispronounced about 10% of the time even respelled `Lyve`. That is outside this branch; see the evidence in `~/.llama-harness/tts-experiments/out/live3/`.

## Contents

- **`orch/ledger.md`:** the orchestrator's ledger, copied byte for byte. It holds every dispatch with its model, the review outcomes, the rulings, the preflight scan and the Escapes list.
- **`orch/deferred-and-rulings.md`:** the deferred minors and rulings list the final reviewer triaged.
- **`verdicts/<task>.md`:** the `handback.md` of every subagent task dir in the run's `.superpowers/sdd/paragraph-chunking/`, copied unedited: implementers (`t*-impl`), reviewers (`t*-rev`, `t*-spec`, `t*-qual`, `*-rerev*`), fix rounds (`*-fix*`), and `final-rev`, `final-fix`, `final-rerev`. That is 32 files, plus `m4-rev.md`.
- **Not copied:** the briefs, per-task logs, the parent's tick state and the empty `taken-over/` dir (no takeover happened). The whole run dir is archived at `~/.llama-harness/paragraph-chunking/sdd-full/`. No source tree or diff package is in this record.

## Filed follow-ups

- **Deferred minors that are not fixed:**
  - the `sentences`/`sentence` loop variables in `_chunked_pcm` now hold chunks; a rename is left for a cosmetic pass off the strict path
  - the abbreviation test's suffix is exactly `_MIN_FRAGMENT_LEN` characters (M6)
  - a duplicate `Chunking` import, plus an `_Chunking` alias, in `test_audio.py`
  - the vacuous older CRLF test, kept beside the new one
- **Pre-existing, outside this branch:**
  - Rich markup swallows `[tts]` in the other `emcee` `--help` strings.
  - transmitter's `test_schedule_lists_missing_announcement_audio` depends on the wall clock and fails at some hours on main.
- **For the next voicings:** watch the room-tone fill (the linear-crossfade dip of about 3 dB is most audible on Kurt) and the mlx server's memory peak at 250-character chunks.
