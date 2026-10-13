# Deferred minors, parked items and flags for the final whole-branch review

## From the predecessor orchestrator (Tasks 1–11) — HANDOFF
### Flagged for the FINAL whole-branch review (G4)
1. Dry-run loads a presenter by filename stem (case-insensitive match in `_presenter_file`, cli.py) while a real run loads by the configured id (process.py `load_presenter(config.root, view.presenter)`) — on a case-sensitive FS dry-run can claim "resolves" for a presenter run cannot load. Pre-existing lookup; Task 6 makes dry-run claim more.
2. quality._attempt feeds hosted WAV to mlx_audio.wav_to_mp3 with no sampwidth==2 check and no wave.Error→SpeechError conversion (latent; Voxtral/ElevenLabs return 16-bit today).
3. SECURITY/ESCAPE: preflight-scan printed the live Mistral API key from ~/.emcee/config.toml into its local subagent transcript (not in any report/log/commit). Reported to parent; rotation is Shawn's call. All dispatches since say never print that file.

### Deferred minors (for G4 triage; all reviewed as Minor)
  - Task 1: minor (deferred): probe doc :142-144 phrases Task 11 404-unload as an action item; plan's SttClient.unload already accepts 404.
  - Task 1: minor (deferred): doc says whisper-asr-fp16 ~1.6 GB vs handback 1.5G (cosmetic).
  - Task 1: minor (deferred, plan-mandated verbatim script): wav_facts data.find(b"data") first match; midstream_kill fixed sleep(8); read_timeout `quick` client unclosed.
  - Task 2: minor (deferred): test_presenters.py:94 mid-file import of TTS_PINS (plan-mandated).
  - Task 2: minor (deferred): presenters.py:72 save_presenter PresenterError embeds full pydantic dump (same style as load path).
  - Task 3: minor (deferred): config template [tts] backend comment omits mlx_audio (field comment lists it) — Task 15 docs may fix.
  - Task 3: minor (deferred): duplicate-key test covers only voxtral house, not elevenlabs house.
  - Task 3: minor (deferred): MlxAudioConfig.timeout_s has no positivity bound; whitespace-only stt_model passes verify check (brief-verbatim).
  - Task 4: minor (deferred): RED produced after the fact (process note).
  - Task 5: minor (deferred → fold into Task 14): elevenlabs clone error says "a voice_clone resolves to the elevenlabs backend" — misleading for `say --clone` (brief-mandated wording; required substring survives rewording).
  - Task 5: minor (deferred): Presenter.voice_id dead in src (tests only).
  - Task 5: minor (deferred): unreachable `or "[tts] api_key"` key_hint fallback (tts/__init__.py:30).
  - Task 5: minor (deferred): test_speech_for_honors_a_presenter_pin asserts only backend, not whole tuple.
  - Task 6: minor (deferred, FINAL REVIEW): dry-run loads presenter by path.stem (case-insensitive match) while a real run loads by configured id — on case-sensitive FS dry-run can claim "resolves" for a presenter run can't load. Pre-existing lookup; Task 6 makes dry-run claim more.
  - Task 6: minor (deferred): `_presenter_file` iterdir() outside try — unreadable presenters/ aborts listing (pre-existing).
  - Task 6: minor (deferred): speech_for guard in new test passes on base too (regression guard only).
  - Task 7: minor (deferred): mid-module imports in test_voice_cmd.py:501-505.
  - Task 7: minor (deferred → Task 9 covers via test_run_continues_other_presenters_when_mlx_is_down): no run-level failed-preflight test.
  - Task 8: minor (deferred, no change): ReadError after prior 500 labelled mid-response — provider per package, wording only.
  - Task 8: minor (deferred, no change): float WAV reported as "non-WAV body (unknown format: 3)".
  - Task 9: minor (deferred): presenter-worded _mlx_provider error branches untested (defensive, unreachable via Presenter validation).
  - Task 10: minor (deferred): no test of a chunked single-sentence retry that then succeeds.
  - Task 10: minor (deferred): retry notice doesn't name the sentence (format plan-mandated).
  - Task 11: minor (deferred, FINAL REVIEW): quality._attempt feeds hosted WAV to mlx_audio.wav_to_mp3 with no sampwidth==2 check and no wave.Error→SpeechError (latent).
  - Task 11: minor (deferred): test_hosted_preflight_passes_on_a_good_transcription's `speech_bodies == []` "no hosted spend" assert proves nothing (brief-verbatim).
  - Task 11: minor (deferred): _assert_nothing_written_for sidecar branch mostly unexercised (failing seg is first).
  - Task 11: minor (deferred): no test lists elevenlabs in [tts.verify].
  (Minors marked 'folded into Task N' were fixed in that task and are omitted here.)

## From this orchestrator (Tasks 12–15)
- 2026-10-13T00:04:34-0400 Ruling: Task 12 split at Checkpoint 2 — phase A (Steps 1–3 + STT comparison) dispatched now; phase B (Steps 4–10) is a later dispatch after Shawn's answer — the plan already stops at Step 3 for the operator — cost if wrong: none.
- 2026-10-13T00:04:34-0400 Ruling: scratch S = this session's scratchpad/calibrate; ports 8781 (Qwen/STT), 8782 (Kokoro) instead of 8765/8766 — brief's path belongs to the planning session; 8765 is Shawn's serve.py — cost if wrong: none.
- 2026-10-13T00:04:34-0400 Ruling: primary STT for drafting clone ref transcripts and the brief's original fields = whisper-large-v3-turbo-asr-fp16 (probe doc's stt_model); parakeet-tdt-0.6b-v3 transcribes every unit too — cost if wrong: the 4 clone voices' ref text reflects whisper's quirks; re-draftable.
- 2026-10-13T00:04:34-0400 Ruling: flag if ANY STT model's recall < 0.8; mechanical-default defect only if max recall across models < 0.5 or s/char > 2x voice median — one model mishearing what the other hears is an STT artefact — cost if wrong: a real defect heard by one model defaults to artefact; operator listens to every flagged unit anyway.
- 2026-10-13T00:04:34-0400 Ruling: false-alarm rate reported leave-one-out + under interim thresholds + cross-backend, since derived thresholds are 0% on their own data by construction — cost if wrong: extra analysis only.
- 2026-10-13T01:40:19-0400 Ruling: phase B by RESUMING the phase-A implementer (Opus, ab6282aa41673673b) under new task name t12b — it finished cleanly and holds the script's context; t12 is single-use — cost if wrong: one cold re-write of a 200k context.
- 2026-10-13T02:10:08-0400 Ruling: dispatch the Task 12 review while the swap gate is with Shawn — the review is read-only and needed whatever he decides; Task 13 is NOT started until he answers — cost if wrong: a re-review of any delta his answer causes.
- 2026-10-13T02:10:55-0400 llama-9b decision while Shawn away, pending his review: (1) MEMORY option (a) — no code change; Task 15 runbook records server 6.6–7 GB between sentences / 12 GB peak, swap 1.4→5.5 GB cold under light desktop, Whisper ~1.6 GB resident; guidance: close other apps for voicing runs, verification costs Whisper's resident set; evidence doc follow-ups: "memory headroom on the 16 GB mini: measured, tight" as open item. (2) #21 — TDD fold of g-dropped lexicon spellings in comparable_words (in'↔ing both directions), re-score saved transcripts, re-derive (pre-approved, Step 3 ceilings bind), confirm #21 passes leave-one-out; residual lexicon misses listed as known limit. Done as a Task 12 fix round, reviewed. (3) both recorded in evidence doc + ledger + finish report as llama-9b decisions pending Shawn's review.
- 2026-10-13T02:10:55-0400 Ruling: hold the #21 fold until t12-review returns, then send it and any review findings to the implementer as ONE fix round — a mutating implementer beside a live reviewer in the same worktree is the shared-surface hazard — cost if wrong: ~30 min of wall clock.
- Task 12: minor (deferred): --rescore documented "with --reuse" but not enforced (one-off script).
- Task 12: minor (deferred): phase A calibration stdout appended to t12.log afterwards rather than live-teed (process; progress lines echoed per poll).
- 2026-10-13T02:16:49-0400 Ruling: fold review minors 1 (pin same-word guards — a deletion over-credits repeated words), 2 (narrowness tests), 3 (wrong comment), 4 (memory-gate outcome — required anyway by llama-9b decision), 5 (8766→8782 note) into fix round 1, since it edits the same code and doc — cost if wrong: slightly larger fix diff to re-review.
- 2026-10-13T02:23:15-0400 t12-fix1 back (verified: done, commits 076089d + 05f3436, tree clean). in' fold adopted; re-derived Whisper thresholds 2/0.15/4/0.25 — MISS_FRACTION TIGHTENED 0.25→0.15 (driven by #39: Drumz + Wharf Rat 3/32), pre-approved, labelled "llama-9b decision while Shawn away, pending his review"; #21 passes LOO (0/53, 0/10); D1 test asserts found==1 not 2 (implementer argues guard semantics; re-reviewer to judge). Child suite 2852p/1s/8d.
- Task 12: minor (deferred): verify.py:51 _DROPPED_G folds a closing single quote of a multi-word quoted phrase ending in "in" ('Fire on the Mountain' → mountaing) — script-side false alarm only, never false credit; 1 quoted span in 129 delivered scripts; doc:143-145 sentence inaccurate ("no closing apostrophe").
- Task 12: minor (deferred): test_verify.py:138-142 asserts ==1 which freezes a conservative under-credit; <= 2 would pin guards without freezing it.
- Task 12: note for Shawn: MISS_FRACTION 0.15 → 8-19-word sentences tolerate 2 misses; lexicon-dense sentences are where spurious re-renders come from (nearest clean unit #39 at 3 of allowed 4).
- Task 13: minor (deferred): _build_presenter catches Exception rather than pydantic.ValidationError (equivalent today).
- Task 13: minor (deferred): edit loads the presenter before flag-conflict checks (unknown id + conflicting flags → exit 1 not 2; brief-verbatim).
- 2026-10-13T02:33:50-0400 Ruling: fold T13 minors 1/2/4 into Task 14's dispatch — Task 14 reuses _draft_transcript and reworks add, so it touches exactly that code — cost if wrong: slightly larger T14 diff.
- 2026-10-13T02:43:19-0400 Ruling: fold T14 minors 1 (declined-prompt test asserts unload), 2 (exact unpinned show output), 4 (exit_code assert in hosted-house say test) into fix round 1 — tests only, same files, pin strict surfaces — cost if wrong: slightly larger fix diff.
- Task 14: minor (deferred): add-side test for --transcribe + --voice-clone-text (edit side covered).
- Task 14: minor (deferred): no unmocked end-to-end test of say --clone X --clone-text Y under an mlx house (wire contract).
- Task 14: minor (deferred): declined-transcribe test comment "unloaded before the prompt" overstates — pins unload on decline path, not strict order vs prompt.
- Task 14: minor (deferred): elevenlabs clone message has a double colon ("the house voice: voice cloning …: a clone reference …"), pre-existing.
- 2026-10-13T02:52:20-0400 Ruling: add the config-cleanup sentence to rollback despite the plan's verbatim text — the spec's rollback intent is a working station; the plan text is incomplete, verified by the reviewer against v2.8.1's strict TTSConfig — cost if wrong: one extra sentence.
- 2026-10-13T02:52:20-0400 Ruling: fold all 7 T15 doc minors into the fix round (shape sentence never-mlx exception, stale "after the calibration doc exists", "error points you there", cross-ref item 6 from R1 paragraph, ~2.6 s clip, re-wrap the three long CLAUDE.md lines, trailing space) — all one-line doc edits in the same files — cost if wrong: none.
- Task 15: minor (deferred → G4): rollback moves only the hosted key back, not [tts.voxtral] model (house silently reverts to default model if deleted not moved).
- Task 15: minor (deferred → G4): rollback names only Phil — any other mlx_audio-pinned presenter needs the same unpin + a Voxtral-suitable --voice-clone, else v2.8.1 voices its mlx ref clip on Voxtral.
- Task 15: minor (deferred → G4): "harmless" pins cover loading, not voicing (v2.8.1 ignores tts pin; an elevenlabs pin under a voxtral house would send an ElevenLabs voice id to Voxtral).
- Task 15: minor (deferred): README.md:475 reflow ~96 cols; :458 ~88 cols (cosmetic).
