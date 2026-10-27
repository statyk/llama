# SDD ledger — plan: docs/superpowers/plans/2026-10-26-paragraph-chunking.md
Spec: docs/superpowers/specs/2026-10-26-paragraph-chunking-design.md (review mode Opus)
Orchestrator: peer session 5419dfd4-2b2c-4fbf-aff9-2cdd628626ee; start 2026-10-26 09:03:57 EDT; start head 9f3aadec
Meter at start: 5h 2%, 7d 71% (stop >85% 5h / >88% 7d)

## Escapes
- 09:5x Task 2 implementer left a hung background shell (`cat > $TMPDIR/tests_block.py` on stdin, followed by a python script re-inserting the plan_chunks test block into test_audio.py). Orchestrator killed it (pid 92214/92215) before it could run; tree verified clean, one copy of the tests. Added a 'leave nothing running' rule to implementer-common.md.

## Log
Task 0: complete — venv created by orchestrator; emcee/herder/llama import from worktree; baseline `./.venv/bin/python -m pytest packages/emcee -q` = 943 passed, 1 deselected. Full-suite baseline in orch/baseline-full.txt.

## Preflight scan (plan vs itself and spec)
| Pair / task | produces → consumes | finding |
|---|---|---|
| T1→T2 | `_split_sentences` (abbrev pre-pass) → `plan_chunks` step 2 | consistent |
| T1→T6 | splitter → `_narrow_chunk` pieces, `rephrase_problems` | consistent (spec §4 says fix applies everywhere) |
| T2→T5 | `plan_chunks(text, ceiling)` → `_chunked_pcm`, `_render_key` digest | consistent |
| T3→T5 | `fill_room_tone(pcm, rate, ch, seed_text=)`, `ROOM_TONE_VERSION` → `_chunked_pcm`, key | consistent |
| T4→T5/T6 | `Chunking`, `chunking=` kw, `CHUNKED`/`SENTENCES` helpers → tests | consistent; SENTENCES (ceiling 1) reproduces one-piece-per-chunk because `_split_sentences` already merges <20 |
| T5→T6 | chunk loop, neighbour context → catch around each chunk | consistent; fake blocks on `text` only (tts/fake.py:58), so neighbour context never trips a block |
| T4→T8 | template lines → doc wording | consistent |
| T7 | prompts + `_unescape_breaks` | self-consistent; independent |
| T1 | tests vs pre-pass rule | self-consistent |
| T2 | "drop empty parts" vs whitespace-only → `[""]` | not a conflict: empty after drop returns `[""]` (mirror `_split_sentences`); left to implementer, pinned by test |
| T3 | pseudocode vs tests (edge runs, odd length) | self-consistent |
| T4 | behaviour-preserving; key still `chunk={chunking is not None}` | self-consistent |
| T5 | new key formula vs `_expected_key` update | self-consistent |
| T6 | `calls` sequences assume PASSAGE packs into one chunk at 250 | consistent with T5 |
| T8 | docs only | — |
Scan clean: no rulings needed.
- 09:06 Task 1: implementer dispatched (Sonnet, t1-impl, a873ba59b31870054), BASE 9f3aadec
- 09:08 Task 1: implementer DONE 717bef24 (951 passed); reviewer dispatched (Opus, t1-rev, a353ce25905e04303)
- Task 1: review (Opus t1-rev): Spec ✅, quality Approved, 0 Critical/Important.
Task 1: minor (deferred): implementer's Mutation A was degenerate (literal block move = rule deleted); reviewer ran a faithful order mutant → only the outro test fails, so ordering IS pinned
Task 1: minor (deferred): no test pins the `U.S. B.B.` chain behaviour (works on HEAD)
Task 1: minor (deferred): `_split_sentences` docstring does not list dotted abbreviations
Task 1: minor (deferred): inline `re.sub(r"^[^A-Za-z0-9]+")` vs module-level compiled pattern convention
Task 1: complete (commits 9f3aadec..717bef24, review clean)
- 09:10 Task 2: implementer dispatched (Sonnet, t2-impl, af443990d13affd85), BASE 717bef24
- 09:14 Task 2: implementer DONE c110c025 (966 passed); reviewer dispatched next (Opus, t2-rev)
  t2-rev agentId a04cf591f50585f80
- 09:15 emcee instruction: two separate Opus reviewers per task from Task 3 (spec first, then quality); Tasks 1-2 get one extra combined code-quality pass. Rubrics split into reviewer-spec.md / reviewer-quality.md.
- Task 2: review (Opus t2-rev, combined): Spec ✅, quality Approved, 0 Critical/Important.
Task 2: minor (deferred): test_plan_chunks_no_paragraphs_packs_plain_sentences compares plan_chunks to itself (plan-mandated literal); packing pinned elsewhere
Task 2: minor (deferred): step-2 inner _greedy is an equivalent mutant (step 3 alone gives the same result)
Task 2: minor (deferred): lone CR "\r\r" is not a paragraph break (out of spec scope; no \r reaches provider)
Task 2: minor (deferred): handback typo ("8 Task1 tests?")
Task 2: ⚠️ carried to Task 5: whitespace-only text → plan_chunks [""]; check caller makes no empty provider call (Review Focus 2)
Task 2: complete (commits 717bef24..c110c025, review clean)
- 09:17 dispatched t12-qual (Opus, a5639ad6ee18a322f, code-quality over 9f3aadec..c110c025) and Task 3 implementer t3-impl (Sonnet, aa24c141e398be8c1), BASE c110c025
- 09:19 Task 3: implementer DONE 8ac30889 (978 passed; note: tests+impl written together, RED shown by moving module aside); spec reviewer dispatched (Opus, t3-spec, a103546462054c099)
- Tasks 1-2: separate code-quality review (Opus t12-qual): Needs fixes — 2 Important (both missing tests, no code change):
  I1: trailing-carry append in `_split_sentences` pre-pass unpinned; deleting it drops a final "…Washington D.C." sentence, nothing fails
  I2: step-2 inner `_greedy` in plan_chunks unpinned (contradicts t2-rev's "equivalent mutant" note — t12-qual's mutant M3 changes output: a paragraph break vanishes inside a chunk); add exact-list test
Tasks 1-2: minor (deferred): chain `U.S. B.B.` untested (also t1-rev) — folded into fix round 1
Tasks 1-2: minor (deferred): no test for 2+ consecutive tiny middle chunks — folded into fix round 1
Tasks 1-2: minor (deferred): no_paragraphs test near-tautological; regex rebuilt per part; t2 handback lacks mutation command line
FIX_BASE for t12 fix round 1: 8ac30889
- 09:20 Tasks 1-2: fix round 1/5 dispatched — resumed T2 implementer (Sonnet, af443990d13affd85) as t12-fix1 with I1, I2 + minors M3, M5
- Task 3: spec review (Opus t3-spec): Approved, 0 Critical/Important.
Task 3: minor (deferred): test_pool_excludes_… "no zero run ≥24" assertion cannot fail on its fixture (holes inside the crossfade window); rule still pinned by the RMS line; move holes to f[200:230]
Task 3: minor (deferred): defensive extras beyond brief (odd byte passthrough, n<=xf guard, max(1,…), unreachable len(pool) guard)
Task 3: minor (deferred): tests and impl written together (RED shown by moving module aside)
- 09:21 Task 3: quality reviewer dispatched (Opus, t3-qual, a7995867895225164)
- 09:22 Tasks 1-2: fix round 1 DONE 8fa473df (982 passed; 4 tests, mutants each kill only their test); scoped re-review dispatched (Opus, t12-rerev1, a7a2cf880f4006604)
- Tasks 1-2: fix round 1/5 (4 addressed, 0 open — I1 carry append, I2 step-2 greedy, M3 chain, M5 tiny runs; commits 8ac30889..8fa473df) — re-review t12-rerev1 (Opus): all findings addressed, no new breakage
Tasks 1-2: minor (deferred): parametrized abbreviation suffix "Blues for the crowd." is exactly _MIN_FRAGMENT_LEN; raising the constant by 1 would make the test vacuous — lengthen the suffix
Tasks 1-2: note: live-worktree mutations are the plan's sanctioned exception (ruling recorded in each dispatch), not a mandate-5 breach
Tasks 1-2: separate code-quality pass: complete after fix round 1 (emcee instruction satisfied)
- Task 3: quality review (Opus t3-qual): Approved, 0 Critical/Important.
Task 3: minor (deferred, RECOMMEND FIX BEFORE MERGE): room_tone.py:85 `astype("<i2")` truncates toward zero (loudness.py uses np.rint); makes exact zeros in crossfades (10% zeros at RMS~2 floor). Fix while ROOM_TONE_VERSION v1 is unshipped.
Task 3: minor (deferred): two unreachable guards (len(frames), len(pool)) — drop or comment as defensive
Task 3: minor (deferred): odd-byte passthrough and degenerate-rate early return untested/undocumented
Task 3: minor (deferred): test_odd_length_pcm doesn't assert edge runs filled (add longest-zero-run check)
Task 3: minor (deferred): linear crossfades on noise dip ~3 dB mid-crossfade (~67 Hz); harness-mandated; flag for listening check
Task 3: complete (commits c110c025..8ac30889, review clean: spec t3-spec + quality t3-qual)
- 09:24 Task 4: implementer dispatched (Sonnet, t4-impl, ab5ce3262fb36613d), BASE 8fa473df
- 09:27 Task 4: implementer DONE 6623bae5 (992 passed; no RED capture, mutations A/B fail as predicted); spec reviewer dispatched (Opus, t4-spec, a5698b657d9232a73)
- Task 4: spec review (Opus t4-spec): Approved, 0 Critical/Important.
Task 4: minor (deferred): no RED run (tests written after impl); mutations A/B carry it
Task 4: minor (deferred): TOML load-error test covers only the string case; parametrize "250"/250.0/1001
Task 4: minor (deferred): room_tone is a loose bool (matches chunk: bool; spec asks no strictness)
- 09:28 Task 4: quality reviewer dispatched (Opus, t4-qual, a54f998adbab2ee67)
- Task 4: quality review (Opus t4-qual): Approved, 0 Critical/Important.
Task 4: minor (deferred): render_speech_mp3 / _synthesize_dj_audio docstring wording (Task 5/8 rewrite these)
Task 4: minor (deferred): test stand-in fakes accept chunking=None with a default (brief-mandated rename)
Task 4: minor → carried into Task 5 dispatch: no test pins forwarding of configured chunk_chars/room_tone through process_package and say
Task 4: complete (commits 8fa473df..6623bae5, review clean: spec t4-spec + quality t4-qual)
Ruling: carry Task 4 quality minor 4 (end-to-end forwarding test of non-default chunk_chars via process_package and say) into Task 5's dispatch — Task 5 is where the settings first change behaviour, so that is where the test can fail; costs one or two extra tests if wrong.
- 09:30 Task 5: implementer dispatched (Sonnet, t5-impl, a8642476a567f2774), BASE 6623bae5; carries T2 ⚠️ (no empty provider call) and T4 forwarding test
- 09:34 Task 5: implementer DONE 21db2638 (1004 passed, 1 skipped = T6 rewrite); RED captured; ruling A result: whole-empty text keeps today's single empty call, trailing blank paragraph makes none
- 09:34 Task 5: spec reviewer dispatched (Opus, t5-spec, a34748b9c9f29625f)
- Task 5: spec review (Opus t5-spec): Needs fixes — 1 Important + 1 ruling:
  I1: "collapse before _locate_block" untested: the test's newlines all follow a period so probes never contain "\n" either way; reviewer's mutant (collapse for _render only) passes the whole suite
  R2: whitespace-only text makes one empty provider call on the chunked path (pinned by test_chunked_empty_text_is_one_call_as_before)
Ruling: Task 5 R2 — keep today's behaviour (whole-empty text → one empty call, as before this branch) and keep its test. Review Focus 2's text and example ("a script ending ...\n\n  \n") are about whitespace-only PARAGRAPHS inside a script, which make no call (pinned by test_chunked_trailing_blank_paragraph_makes_no_empty_call); plan Task 2 itself mandates plan_chunks("  ") == [""]; inventing a skip/raise for a wholly empty segment changes the unchunked-equivalent behaviour and the MP3 path for no listening benefit. Cost if wrong: an empty DJ segment still makes one empty provider call, exactly as today.
Task 5: minor (deferred to Task 8 doc pass): stale "Sentence-by-sentence" docstring on _synthesize_chunked; _synthesize_dj_audio key description lacks chunks=/tone=; loop vars still named sentences/sentence
Task 5: minor (deferred): forwarding test for process_package added after code (no RED); mutations B/E carry it
FIX_BASE for t5 fix round 1: 21db2638
- 09:37 Task 5: fix round 1/5 dispatched — resumed implementer (Sonnet, a8642476a567f2774) as t5-fix1 with I1 + unused-param minor
- 09:38 Task 5: fix round 1 DONE f105fb96 (1004 passed, 1 skipped); dispatched re-review t5-rerev1 (Opus, a6e6afff0320153d8) and quality t5-qual (Opus, a3eea23a81558497d) over 6623bae5..f105fb96
- Task 5: spec fix round 1/5 (1 addressed, 0 open — I1 collapse-before-locate test; commits 21db2638..f105fb96) — re-review t5-rerev1 (Opus): addressed, no new breakage
Task 5: minor (deferred): collapse test could also assert "long jam" in ei.value.text and not whole_passage
- Task 5: quality review (Opus t5-qual): Approved, 0 Critical/Important.
Task 5: minor (deferred → Task 8): _synthesize_dj_audio cache-key docstring lacks chunks digest / tone
Task 5: minor (deferred): forwarding test fixture paths built from dict repr; clever lambda recorder
Task 5: minor (deferred): mid-module aliased import `Chunking as _Chunking` and in-function imports in test_audio.py
Task 5: minor (deferred): room-tone recorder checks only seed (not pcm length/channels)
Task 5: complete (commits 6623bae5..f105fb96, 1 fix round; spec t5-spec + re-review t5-rerev1, quality t5-qual)
- 09:41 Task 6 (STRICT): implementer dispatched (Sonnet, t6-impl, ac942250c9b8213ce), BASE f105fb96
- 09:46 Task 6: implementer DONE 2cb14e34 (1012 passed, no skips; RED captured; narrowing passes no neighbour context). Implementer again hung a 'cat > file' shell, says it stopped it by task ID; orchestrator verified no stray cat process, tree clean.
- 09:46 Task 6: spec reviewer dispatched (Opus, t6-spec, aa4471394cb923c5c) with Stakes verbatim + Review Focus 5 explicit
- Task 6: spec review (Opus t6-spec, Stakes verbatim): Approved, 0 Critical/Important. Review Focus 5 traced in code (bed and no-bed share _chunked_pcm/_narrow_chunk); _locate_block..render_speech_mp3 byte-identical; rephrase receives one sentence.
Task 6: minor (deferred): narrows test uses CHUNKED (room_tone=True) not brief's Chunking(250, False); no behavioural difference
Task 6: minor (deferred): reblocked-twice test could check the quoted sentence in the feedback field specifically
Task 6: minor (deferred): mutants B/C/E run with -x (first failure only, each the predicted test)
Task 6: ⚠️ (spec reviewer, not blocking): narrowing takes pass through QualitySpeech/[tts.verify] wrapper; untested (spec does not require)
- 09:49 Task 6: quality reviewer dispatched (Opus, t6-qual, abd93a28c6d6cee8a)
Ruling: start Task 7's implementer while Task 6's read-only quality review runs (reviewer works from a scratch copy; T7 files are disjoint from audio.py). If T6 needs a fix round, it waits for T7's implementer to finish, so there is never more than one writer. Cost if wrong: a T6 fix rebases onto T7's commit; no conflict expected (disjoint files).
- 09:49 Task 7: implementer dispatched (Sonnet, t7-impl, a13d828a2e92e4c01), BASE 2cb14e34
- 09:50 Task 7: implementer DONE 675d16e5 (1017 passed; RED 4 failed/1 passed as expected)
- 09:50 Task 7: spec reviewer dispatched (Opus, t7-spec, a7bffd86c133eac34)
- Task 7: spec review (Opus t7-spec): Approved, 0 Critical/Important.
Task 7: minor (deferred): prompt test depends on "never a raw line break" staying on one line (a rewrap breaks it)
- 09:52 Task 7: quality reviewer dispatched (Opus, t7-qual, a6ab66308c858e675)
- Task 6: quality review (Opus t6-qual, Stakes verbatim): Approved, 0 Critical/Important. Review Focus 5 confirmed in code; QualitySpeech/verify wraps narrowing takes; only SpeechBlocked caught; chaining sound.
Task 6: minor → carried into Task 8: stale comment `raise  # each chunk is already its own request` (audio.py:363) and render_speech_mp3 docstring says narrowing is unchunked-only — code stays, wording changes
Task 6: minor (deferred): fallback is silent (no detail() line) — optional visibility
Task 6: minor (deferred): later takes not checked against first take's rate/channels/width (pre-existing; cheap guard)
Task 6: minor (deferred): redundant `_split_sentences` import at test_audio.py:1086; one-caller `_bed` helper
Task 6: minor (deferred): coverage — SpeechError during narrowing propagates; fallback with room_tone=True; bed fallback PCM length
Task 6: complete (commits f105fb96..2cb14e34, review clean: spec t6-spec + quality t6-qual, both with Stakes)
- Task 7: quality review (Opus t7-qual): Approved, 0 Critical/Important.
Task 7: minor (deferred): prompt test brittle to rewrap — compare whitespace-collapsed copy
Task 7: minor (deferred): no test pins unescape-before-strip in rephrase_segment
Task 7: minor (deferred): only \n unescaped (not \r, \t) — spec scope
Task 7: complete (commits 2cb14e34..675d16e5, review clean: spec t7-spec + quality t7-qual)
Ruling: Task 8 dispatch also carries the deferred wording items from Tasks 4-6 (stale "sentence" docstrings on _synthesize_chunked/_chunked_pcm/render_speech_mp3/_synthesize_dj_audio, the cache-key formula docstring missing chunks=/tone=, and the `raise  # each chunk is already its own request` comment) — they are exactly Task 8's wording scope; comments/docstrings only, no code or variable renames in the strict path. Cost if wrong: a slightly larger Task 8 diff.
- 09:54 Task 8: implementer dispatched (Sonnet, t8-impl, afcba35f46101cc1c), BASE 675d16e5
- 09:57 Task 8: implementer DONE_WITH_CONCERNS 6d964b94 (docs only; emcee 1017 passed; full suite 5993 passed, 1 failed, 1 skipped, 8 deselected).
  Failing test: packages/transmitter/tests_transmitter/test_cli.py::test_schedule_lists_missing_announcement_audio. Orchestrator check: fails at HEAD AND at the branch base 9f3aadec (scratch copy, transmitter shadowing proven) at 09:56 EDT; the same full suite passed at 09:05 (baseline-full.txt rc=0). The branch changes no file outside packages/emcee, README.md, CLAUDE.md. => pre-existing wall-clock-dependent test, not a regression from this branch.
Ruling: report the transmitter failure to emcee now as a stop-point notice, and continue the in-progress Task 8 review cycle (read-only reviewers, docs-only diff) — the failure is independent of every file this branch touches and reproduces on the base commit. Cost if wrong: emcee wanted a full halt; the extra work is two read-only doc reviews.
- 09:57 Task 8: spec reviewer dispatched (Opus, t8-spec, a90557e066ab4f5dd). emcee confirmed transmitter failure also on main 98d4eda6 at 09:57; ruling stands; finish report must name it.
- Task 8: spec review (Opus t8-spec): Approved, 0 Critical/Important; no executable code changed; grep clean.
Task 8: minor (deferred, cheap): _synthesize_dj_audio docstring says key always carries tone=; code adds it only when room_tone is on
Task 8: minor (deferred): quality.py "the chunk when chunked" omits narrowing takes as their own verified units
Task 8: minor (deferred): Rich eats `[tts]` in say --help strings (pre-existing pattern in cli.py; escape as \[tts])
- 10:00 Task 8: quality reviewer dispatched (Opus, t8-qual, a54816a4e2820931e)
- Task 8: quality review (Opus t8-qual): Needs fixes — 1 Important:
  I1: new `--chunk` help and `say` CHUNKING docstring lose `[tts]` to rich markup in --help ("up to  chunk_chars"); escape the 3 new instances as \[tts]. File-wide pre-existing cases → follow-up (deferred minor).
Task 8: minor (deferred, follow-up): pre-existing file-wide rich-markup swallowing of `[tts]` in cli.py help (~8 option helps)
Ruling: fold the cheap Task 8 wording minors into fix round 1 (all docs, same files): _synthesize_dj_audio docstring line 420 reflow + accuracy (chunks=/tone= are separate key parts; tone= only when room_tone on; point at _render_key), quality.py narrowing wording, ragged say-docstring line, README mlx-memory "(measured with sentence-sized chunks)" qualifier. Cost if wrong: a few extra doc lines in the fix diff.
FIX_BASE for t8 fix round 1: 6d964b94
- 10:02 Task 8: fix round 1/5 dispatched — resumed implementer (Sonnet, afcba35f46101cc1c) as t8-fix1 with I1 + 4 wording minors
- 10:03 Task 8: fix round 1 DONE 99a9e6da (emcee 1017 passed); re-review dispatched (Opus, t8-rerev1, a13889556b95006f9)
- Task 8: fix round 1/5 (5 addressed, 0 open — I1 help markup escape, M1-M4 wording; commits 6d964b94..99a9e6da) — re-review t8-rerev1 (Opus): all addressed, no new breakage
Task 8: complete (commits 675d16e5..99a9e6da, 1 fix round; spec t8-spec, quality t8-qual, re-review t8-rerev1)
- 10:05 Final whole-branch review dispatched (Opus, final-rev, a3d1f6b449dac53cd) over 9f3aadec..99a9e6da, Stakes verbatim, deferred-and-rulings.md for triage
- Final review (Opus final-rev): VERDICT: READY WITH FIXES. 0 Critical, 1 Important, 3 Minor-to-fix, 3 Minor-defer. 24 mutants run, 3 survived (= the findings).
  I1: no test shows paragraph breaks reach the packer through normalize_for_speech (mutant M23 collapsing newlines there survives)
  M1: CRLF test (Review Focus 1) cannot fail at ceiling 100 (mutant M8 split on "\n\n" survives)
  M2: say --no-chunk lost its only guard (43-char passage is one chunk either way; mutant M11 survives)
  M3: room_tone int16 truncation (promoted from deferred) — np.rint; keep ROOM_TONE_VERSION v1 (unshipped)
  Defer: M4 silent fallback (no detail line); M5 stale wording loudness.py:3/provider.py:79 + `sentences` loop vars; M6 abbreviation suffix == _MIN_FRAGMENT_LEN
  Final reviewer agrees with all six Ruling: lines.
Ruling: final fix wave = I1, M1, M2, M3 plus M5's two stale-wording lines (comments only); M4 (new operator-facing output on the strict path) and the loop-variable rename stay deferred — they change behaviour/code in the strict path for no correctness gain. Cost if wrong: fallback stays silent in `emcee run` output until a follow-up.
- 10:17 Final fix wave dispatched (Sonnet, final-fix, aa1440fbe9f9657d3), FIX_BASE 99a9e6da
- 10:20 Final fix wave DONE 278c1757..3aa6d279 (emcee 1021 passed; full 5998 passed, 1 skipped, 8 deselected — transmitter wall-clock test passed this run). Escape: 278c1757 was committed with one failing test (mandate 4), fixed by 3aa6d279; only 3aa6d279 is green.
- 10:21 Final fix re-review dispatched (Opus, final-rerev, a4252c528178c2382)
- 10:22 Orchestrator verification at 3aa6d279 (imports resolve in worktree): ./.venv/bin/python -m pytest packages/emcee -q → 1021 passed, 1 deselected; ./.venv/bin/python -m pytest -q → 5998 passed, 1 skipped, 8 deselected, 26 warnings (the transmitter wall-clock test passed at 10:22)
- Final fix wave re-review (Opus final-rerev): all findings addressed (I1, M1, M2, M3, M5), no new breakage; strict path (audio.py) untouched by the wave. Cosmetic: duplicate Chunking import / _Chunking alias in test_audio.py. Note: pre-fix room-tone clips would hit a stale tone=v1 cache key — use --force or a fresh station root for the listening check.
Final: minor (deferred): duplicate `Chunking` import and `_Chunking` alias in test_audio.py
Final: minor (deferred): M4 silent fallback (no detail() line); M6 abbreviation suffix == _MIN_FRAGMENT_LEN; `sentences` loop vars in _chunked_pcm; pre-existing cli.py rich `[tts]` swallowing
Final review: complete. Final commit 3aa6d279.
- 10:24 FINISH: tick e169794f deleted, armed-5419… removed (armed-global kept: armed-e028… still present); STATE mode done; no children, shells or monitors running. Workspace kept for the operator (not merged).
