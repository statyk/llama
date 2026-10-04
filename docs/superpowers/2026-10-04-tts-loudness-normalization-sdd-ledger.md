# SDD ledger — plan: docs/superpowers/plans/2026-10-04-tts-loudness-normalization.md

Spec: docs/superpowers/specs/2026-10-04-tts-loudness-normalization-design.md (approved 2026-10-04)
Worktree: .claude/worktrees/loudness (branch loudness), own .venv; baseline 2081 passed.
Models: implementers Sonnet; task reviewers Opus; final reviewer Opus.

## Pre-flight scan
| rows | produces / consumes | finding |
|---|---|---|
| T1 -> T2 | T1 produces normalize_speech(pcm, framerate)->bytes, active_level_db(pcm, framerate)->float|None, LOUDNESS_VERSION="v1", TARGET_DB; T2 imports exactly these | consistent |
| T1 self | tests import CEILING_DB, LOUDNESS_VERSION, MAX_GAIN_DB, TARGET_DB, active_level_db, normalize_speech; impl defines all; files created = files committed | consistent |
| T2 self | tests import _SILENCE_MS/_chunked_pcm/_segment_pcm (exist in audio.py), Lexicon/normalize_for_speech (speech_text); hardcoded "\nloud=v1" matches LOUDNESS_VERSION; -k filter selects only the 6 new tests (no existing name matches) | consistent |
| Global constraints | constants, no-knob, plain path untouched, key term only on chunk/bed | all tasks agree |
Rubric conflicts: none (no assert-nothing tests remain after plan review; no duplicated logic).
Task 1: dispatched implementer (Sonnet), BASE 6f92805
Task 1: implementer DONE 2695475 (16/16, suite 2097); task reviewer dispatched (Opus)
Task 1: ⚠️ full-suite evidence resolved — implementer reply states 2097 passed, 7 deselected
Task 1: minor (deferred): constants test pins only TARGET/CEILING/MAX_GAIN, not FRAME_S/GATE_DB/SILENCE_DB
Task 1: minor (deferred): rint after ceiling gain can exceed CEILING_DB by <=0.5 LSB (test tolerates +1 LSB)
Task 1: minor (deferred): task report lacks full-suite count line
Task 1: complete (commits 6f92805..2695475, review clean)
Task 2: dispatched implementer (Sonnet), BASE 2695475
Task 2: implementer DONE 4cfd8fd (suite 2103; 26 warnings = baseline count, pre-existing); task reviewer dispatched (Opus)
Task 2: minor (deferred): _chunked_pcm checks width on first sentence only; a later odd-byte non-16-bit chunk now raises numpy ValueError (was silent garbage) — pre-existing, theoretical
Task 2: minor (deferred): normalize_speech assumes mono; chunked no-bed path never asserts mono (stereo => approximate level, no crash)
Task 2: minor (deferred): mid-file imports in test_audio.py (plan-mandated, matches existing file style at line 562)
Task 2: complete (commits 2695475..4cfd8fd, review clean)
Final review: dispatched (Opus) over 6f92805..4cfd8fd
Final review: Ready to merge — Yes (0 Critical, 0 Important); all six deferred minors triaged stay-deferred
Final: minor — Ruling: `emcee say` help text / CLAUDE.md say entry don't mention that --no-chunk without a bed is not loudness-normalized — deferred, no fix wave — a one-clause doc gap doesn't justify a fix dispatch + re-review; costs a possible user surprise at a level difference on an uncommon path
