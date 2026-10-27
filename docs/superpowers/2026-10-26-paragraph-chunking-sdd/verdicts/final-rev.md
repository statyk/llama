VERDICT: READY WITH FIXES

The fixes are tests only, plus one optional line of production code. The production code at HEAD 99a9e6da matches the spec on every strict surface I checked. Three tests that should guard the headline behaviour, or the `say --no-chunk` path, pass even when the behaviour is broken (shown by surviving mutants below). They are cheap to fix and should be fixed before merge.

Final whole-branch review (Opus), BASE 9f3aadec..HEAD 99a9e6da, 11 commits. Method: the code-reviewer rubric. I read the spec in full, the plan's Global Constraints and Review Focus, the HEAD source of every changed production file, and the diffs of production files and tests (the 124 KB diff in passes). I also read the unchanged collaborators the strict path depends on: `process._repair`, `rephrase_segment`, `rephrase_problems`, `SpeechBlocked`, `QualitySpeech`, `normalize_for_speech` and the calibration module. Probes and mutants ran in a scratch `git archive` copy of 99a9e6da. I confirmed `emcee.__file__` resolved inside each copy before trusting a run.

Baseline on the scratch copy: `PYTHONPATH=<scratch>/packages/emcee/src:<scratch>/packages/herder/src PYTHONDONTWRITEBYTECODE=1 <worktree>/.venv/bin/python -m pytest -p no:cacheprovider packages/emcee -q` gave **1017 passed, 1 deselected**.

## Strengths

- **Strict path is minimal and correct.** `_narrow_chunk` (audio.py:188-207) does exactly what spec section 5 asks:
  - A one-piece chunk re-raises without a call.
  - Each piece is synthesized alone as WAV and its take is kept.
  - The first refusal is raised as the provider's own located `SpeechBlocked` (`whole_passage` false, chained `from blocked`).
  - When every piece passes, the takes are the chunk's audio. Each is normalized and joined with 180 ms (audio.py:233-247), and nothing is re-sent.
  - `render_speech_mp3`'s chunked re-raise is unchanged (audio.py:367-368).
  - `_locate_block` is untouched apart from receiving collapsed text.
- **Cache key is right by construction.** `_render_key` (audio.py:383-396) hashes `plan_chunks(spoken, ceiling)` joined by `\x1f`. `plan_chunks` rebuilds every chunk with `str.split()`/`" ".join`, which treats `\x1f` as whitespace, so the separator really cannot occur in a chunk. The unchunked branch builds the same string as base (`chunk=False{bed}{loud}`).
- **`chunking` has no default anywhere.**
  - `Chunking` is a frozen dataclass with no defaults.
  - `TTSConfig.chunking(*, enabled)` is keyword-required.
  - Every render function takes `chunking` keyword-only with no default: `_render_key`, `_synthesize_dj_audio`, `render_speech_mp3`, `_render`, `_segment_pcm`, `_chunked_pcm`, `_synthesize_chunked`.
  - Both production callers pass it (process.py:307, cli.py:736).
- **Room tone matches the spec's parameters.** Frames 20 ms, 8%, 5 ms crossfades, runs of at least 20 ms, a 24-sample pool exclusion applied before the percentile, sha256 seed, mono-only, every no-op case, and the odd byte passed through.
- **Mutation evidence is strong.** 21 of the 24 mutants I ran were caught by the predicted test, or by a set that includes it. The three survivors are the findings below.

## Issues

### Critical (Must Fix)
None.

### Important (Should Fix)

**I1. Nothing shows that a script's paragraph breaks reach the packer.** The goal-1 behaviour has no end-to-end test.
- Files: packages/emcee/tests/test_audio.py (the `_synthesize_dj_audio` block); packages/emcee/tests/test_say_cmd.py:331.
- What's wrong: mutant M23 changes `normalize_for_speech` (speech_text.py:67) to `" ".join(text.split())`, which collapses every newline before `plan_chunks` sees it. **The whole suite stays green.**
  - The render-level paragraph tests call `render_speech_mp3` directly with P1/P2 at ceiling 100. Paragraph-aware and plain packing give the same chunks there.
  - `test_say_hard_wrapped_file_is_one_paragraph` tests single newlines only, which M23 also satisfies.
- Why it matters: `normalize_for_speech` keeps `\n` today only because `_MULTISPACE` is `[ \t]{2,}`. The branch now depends on that, and nothing pins it. A later "tidy all whitespace" edit there, or any pre-packer collapse, would silently turn every DJ clip and every `say` render into plain 250 packing. On air that means chunks starting one sentence into a new thought, which is the defect this branch exists to fix, and it would show up only in a listening test.
- Fix: one `_synthesize_dj_audio` test, plus optionally one `say` test, with a segment where paragraph-aware and plain packing differ, asserting `speech.calls`. A probed fixture at ceiling 110:
  - X = "Tonight we head back to Portland for a spring night."
  - Y = "Listen for the long jam after Truckin' tonight. It stretches out and turns quiet."
  - `X\n\nY` gives `[X, Y]`.
  - Plain packing (and M23) gives `["X Listen for the long jam after Truckin' tonight.", "It stretches out and turns quiet."]`.

### Minor (fix in the same round: all cheap)

**M1. The Review Focus 1 CRLF test cannot fail.**
- Where: test_audio.py:188 `test_plan_chunks_crlf_breaks_and_no_carriage_returns`.
- Mutant M8 changes the split to `re.split(r"\n\n", text)`, so CRLF is no longer a paragraph break. It survives. At ceiling 100, P1/P2 sentence-pack to the same `[P1, P2]` with or without the break.
- HEAD itself is correct: I probed `\r\n\r\n` and `\n \n` with the X/Y fixture above and got `[X, Y]`.
- Fix: use the I1 fixture with `\r\n\r\n` and `\n \n` separators, and assert no `\r` appears in any chunk.

**M2. `say --no-chunk` lost its only guard on this branch.**
- Where: test_say_cmd.py:150 `test_say_no_chunk_sends_the_whole_passage_in_one_call` became vacuous.
- At base, chunked rendering sent two sentence calls, so the test told the paths apart. At the 250 default, the same 43-character passage is one chunk either way.
- Mutant M11 changes cli.py:736 to `chunking=config.tts.chunking(enabled=True)`, ignoring `--no-chunk`. It survives the whole suite, including `test_say_names_the_blocked_sentence`: chunked narrowing names the same sentence.
- This touches focus area (d): no caller may silently fall to the other path.
- Fix: use a passage over 250 characters, or assert the output bytes are the fake provider's MP3 returned untouched (only the unchunked no-bed path does that).

**M3. Room tone truncates to int16 instead of rounding.**
- Where: room_tone.py:85 `np.clip(out, ...).astype("<i2")`, which truncates toward zero. loudness.py:65 uses `np.rint`.
- Where it bites: inside a run with `env = 1`, the fill is the pool's own integers, so truncation is a no-op there. It acts only in the 5 ms crossfades and the edge envelopes. In those regions two pool frames can partly cancel.
- Measured on synthetic clips (10 x 1 s speech plus floor, nine 180 ms gaps), longest exact-zero run inside a filled gap, truncation vs `np.rint`:

| Floor | Truncation | `np.rint` |
|---|---|---|
| 60 Hz floor at -66 dBFS | 38 samples (1.6 ms) | 11 |
| White floor at -67 dBFS | 11 samples | 4 |
| 60 Hz floor at -81 dBFS | 40 samples | 16 |

- At those levels this is inaudible, but it breaks the spec's own 1 ms "no dropouts in the fill" rule.
- Fix: `np.clip(np.rint(out), -32768, 32767).astype("<i2")`, keep `ROOM_TONE_VERSION = "v1"` (unshipped), and add a one-line pin, for example a crossfade sample equals the rounded value. Not merge-blocking on its own; see the triage below.

**Other minors (defer):**
- **M4. A fallback chunk is silent.** `_chunked_pcm` prints no `detail()` line when a chunk is narrowed and falls back. On metered Voxtral the operator cannot see that a block happened or that extra calls were spent. One `detail(f"content filter blocked a chunk; rendered from its {len(takes)} sentence takes")` would do it. Optional.
- **M5. Stale wording:**
  - tts/loudness.py:3 "the sentence chunks of one DJ clip"
  - tts/provider.py:79 "concatenate sentences"
  - In `_chunked_pcm` (audio.py:219-245), the loop variables `sentences`/`sentence` now hold chunks. Accepted per the Task 8 ruling (no renames on the strict path); worth a later cosmetic pass.
- **M6. Abbreviation test suffix sits at the boundary.** In test_audio.py:131, "Blues for the crowd." is exactly `_MIN_FRAGMENT_LEN` (20) characters. Raising the constant by one would make the parametrized case pass for the wrong reason. Lengthen the suffix (already in the deferred list).

## Deferred-minor triage

Promote before merge:
- **"room_tone.py:85 astype truncates" (Task 3, RECOMMEND FIX):** promote, as M3 above. It is one line, the version is unshipped, and it is folded into the same test fix round. It does not block merge on its own. The audible effect is nil, and since every voicing re-scripts, a later v2 bump would cost no extra spend either.
- **Task 6 "fallback is silent":** optional promote (M4). Visibility on metered spend; not required by the spec.

Everything else stays deferred. Notes on specific items:
- Task 1 degenerate mutation A: resolved by the reviewer's faithful mutant.
- Task 1 `U.S. B.B.` chain: done (the parametrize includes it).
- Task 1 docstring and inline regex: cosmetic.
- Task 2 self-comparing no-paragraph test: packing is pinned elsewhere, but see M1/I1 for the real gap.
- Task 2 step-2 `_greedy` equivalent mutant: I agree it is equivalent. Greedy over a paragraph's sentences, then greedy over units, equals greedy over the sentences.
- Task 2 lone CR: out of scope, and no `\r` reaches a provider.
- Task 2 tiny-chunk runs: done (`test_plan_chunks_consecutive_tiny_paragraphs_all_join_the_chunk_before`).
- Task 3 vacuous assertion: the rule is still pinned (my mutant M18 killed by two tests).
- Task 3 defensive guards, odd-byte and degenerate-rate tests, edge assertion in the odd-length test: harmless.
- Task 3 linear crossfade 3 dB dip: this is what the operator listened to in the harness. Carry it to the listening check, especially Kurt, whose fill sits near -40 dBFS.
- Task 4 items: the validator path is shared; `room_tone` as a loose bool matches the spec; the docstrings were fixed in Task 8.
- Task 5 docstring items: fixed in Task 8 and fix round 1 (verified at HEAD: `_synthesize_dj_audio` says `tone=` only when room_tone is on).
- Task 6 "reblocked-twice feedback": HEAD now checks the feedback line excludes CLEAN_S1.
- Task 6 narrowing through QualitySpeech: correct by construction, since `speech` is the wrapper and the spec lists it as a known limit.
- Task 6 rate checks on later takes: a pre-existing limitation.
- Task 7 prompt-test brittleness, unescape-before-strip, `\n` only: within spec scope.
- Task 8 Rich `[tts]`: fixed in `say` at 99a9e6da; the file-wide pre-existing cases are a follow-up.

Rulings, one line each:
- "Carry T4 minor 4 (forwarding test) into Task 5": **agree.** The resulting tests kill M15 and M17.
- "Task 5 R2: whole-empty text keeps one empty call": **agree.** It matches base behaviour and plan Task 2's `[""]`. Review Focus 2 is about blank paragraphs inside a script, which make no call (pinned).
- "Start T7 while T6's read-only review runs": **agree.** The files are disjoint and there was never more than one writer.
- "Task 8 carries the deferred wording items, comments only, no strict-path renames": **agree.**
- "Report the transmitter failure and continue": **agree.** It is wall-clock dependent, reproduces on base and main, and this branch touches no transmitter file.
- "Fold cheap T8 wording minors into fix round 1": **agree.** All of them landed at 99a9e6da.

## Per-focus-area verdicts

**(a) Strict path end to end: PASS.** Traced the full chain:
1. `_chunked_pcm` gets a blocked chunk.
2. `_narrow_chunk` synthesizes each `_split_sentences(chunk)` piece alone.
3. The refused piece's provider exception (exact text, `whole_passage` false) is raised, and `render_speech_mp3` re-raises it unchanged.
4. `_synthesize_dj_audio` sets `.segment`.
5. `process_package` does not short-circuit, because `whole_passage` is false.
6. `_repair` gets `blocked.text` equal to the single sentence and hands it to `rephrase_segment` with the whole segment text. There is no splicing, so whitespace collapse in the chunk cannot desynchronize it.
7. `rephrase_problems` folds whitespace, so paragraph breaks gained or lost are not counted as edits.
8. The segment re-renders.

Notes:
- With a bed, `_render` goes through `_segment_pcm` to the same `_chunked_pcm`, so narrowing and fallback behave identically. Pinned by `test_chunked_block_with_bed_narrows_and_falls_back`.
- The fallback can never produce `whole_passage`, and nothing is synthesized after narrowing.
- Mutants M3, M4 and M5 were killed. M4 failed 4 tests including the process-level repair test, which now asserts the logged `blocked:` text is the single sentence.
- No regression against base: wherever a sentence chunk was blocked before, the narrowed piece is blocked now. A cross-sentence trigger, which sentence chunks never sent together, now renders from the same sentence takes.

**(b) Cache key: PASS.**
- The chunk digest covers ceiling, packer, splitter and `_MIN_FRAGMENT_LEN` exactly, because it hashes the plan itself.
- `tone=<ROOM_TONE_VERSION>` is added only when room_tone is on, so the flag and the version are both covered.
- The room-tone seed is the spoken text, which is already in the key.
- The unchunked key is byte-identical to base: same f-string, `chunk=False`. Pinned against a literal.
- Mutants killed: M1 (drop the digest), M2 (tone always on), M16 (key plans at a fixed 250).
- Not keyed: `_SILENCE_MS`, as on base, and the fallback's verdict dependence, which the spec accepts.

**(c) No "\n" or "\r" reaches a provider: PASS in code.** One test weakness (M1).
- Chunked: every chunk is `" ".join(p.split())`. That removes `\n`, `\r`, `\x0b`, `\x0c`, `\x1c-\x1f`, `\x85`, ` ` and ` `.
- Narrowing pieces and `previous_text`/`next_text` are drawn from those chunks.
- Unchunked: collapsed at the top of `render_speech_mp3`, before both the provider call and `_locate_block`, including the bed path's `_segment_pcm`. Mutants M6 and M21 were killed.
- `say` goes through the same renderer, and the preflight sends a fixed sentence.

**(d) `chunking` has no default and every caller passes it: PASS in code.**
- Signatures verified for all seven functions. `test_chunking_has_no_default` checks four of them, and the rest were confirmed by reading the code.
- `process.py` honours `[tts] chunk` (M10 killed by 3 tests).
- **`say`'s honouring of `--no-chunk` is unpinned** (M11 survives, M2 above).

**(e) Room tone: PASS, with one recommended fix.**
- Parameters per spec. Determinism comes from sha256 (M7 killed).
- No-op cases: no live frames, empty pool, no qualifying run, non-mono.
- Edge runs fade from and to zero (M12 killed). Length is unchanged, including odd byte counts and partial frames. The pool exclusion is pinned (M18).
- int16 conversion: truncation, as M3. Not required for correctness or audibility, but recommended now: one line, `ROOM_TONE_VERSION` stays v1 because it is unshipped, and it makes the fill honour the spec's own 1 ms no-dropout rule.

## Mutation log

Each mutant ran in a fresh scratch copy of 99a9e6da, over the full emcee suite without `-x`. `emcee.__file__` was asserted inside the copy each time. The prediction was written before each run.

| Mutant | Change | Predicted | Observed |
|---|---|---|---|
| M1 | drop `chunks=` digest | cache_key_chunked_changes | that + 2 more |
| M2 | tone part always added | cache_key_tone_part | as predicted |
| M3 | one-piece chunk re-sent | one_piece_block_is_reraised | as predicted |
| M4 | raise chunk instead of sentence | block_narrows_to_refused_sentence | that + bed + 2 process tests |
| M5 | no gap between takes | fallback_audio_is_the_takes_joined | that + neighbours test |
| M6 | no unchunked collapse | unchunked_collapses... | as predicted |
| M7 | seed via `hash()` | seed_is_the_sha256 | as predicted |
| **M8** | paragraph split `\n\n` only | crlf test | **SURVIVED** (M1) |
| M9 | rephrase_segment no unescape | rephrase_segment_unescapes | as predicted |
| M10 | process ignores `[tts] chunk` | an unchunked process test | 3 tests |
| **M11** | `say` ignores `--no-chunk` | a `say --no-chunk` test | **SURVIVED** (M2) |
| M12 | edge start only `s == 0` | edge_runs_fade | as predicted |
| M13 | pool percentile 50 | fill_level_from_quietest | as predicted |
| M14 | seed ignores text | (recorder) | room_tone_applied_only_when_enabled |
| M15 | room tone ignores flag | room_tone_applied_only_when_enabled | that + 2 forwarding tests |
| M16 | key plans at fixed 250 | cache_key_chunked_changes | as predicted |
| M17 | render ignores ceiling | forwarding tests | 9 tests |
| M18 | pool zero-run exclusion off | pool_excludes... | that + noop_when_pool_empty |
| M19 | abbreviation pre-pass off | dotted_abbreviation param | 9 tests |
| M20 | tiny-chunk join off | tiny_chunk_joins | 3 tests |
| M21 | `_locate_block` gets a newline | unchunked_collapses | that + 2 more |
| M22 | write_script outro no unescape | unescapes_double_escaped | as predicted |
| **M23** | `normalize_for_speech` collapses `\n` | (none expected) | **SURVIVED** (I1) |
| M24 | write_script intros no unescape | unescapes_double_escaped | as predicted |

## Declined to judge

- The transmitter wall-clock failure: out of scope per brief, and no transmitter file is touched.
- Whether 250, the 8% pool and linear crossfades sound right: the operator's listening check owns that. I only flag the 3 dB crossfade dip for it.
- The mlx runaway-guard calibration at 250-character chunks: the calibration scales per character and the harness rendered 307 chunks of this size. Watching for "quality check failed" retries is already in the listening-check acceptance.
- File-wide Rich `[tts]` markup in other cli.py helps: pre-existing, filed as a follow-up.
- The lexicon not matching a phrase across a paragraph break: pre-existing semantics, and scripts do not break a paragraph inside a phrase.

## Assessment

**Ready to merge? With fixes.**

**Reasoning:** The production code meets the spec on all five focus areas, and the strict content-filter path is correct with and without a bed, backed by killed mutants. Three tests that guard a mandated behaviour cannot fail on the code they guard (I1, M1, M2), and the room-tone rounding is a free one-line correctness fix while v1 is unshipped. All four fit in one small fix round touching tests and room_tone.py:85 only.
