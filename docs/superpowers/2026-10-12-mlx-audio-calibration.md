# mlx-audio calibration run (2026-10-12/13)

Evidence for the measured constants in `packages/emcee/src/emcee/tts/calibration.py`
(`CALIBRATED_MODELS`, the runaway guard) and `packages/emcee/src/emcee/tts/verify.py`
(the four transcript-verification thresholds), per spec
`docs/superpowers/specs/2026-10-12-local-tts-presenter-pinning-design.md` section 3
("Constants are measured, not guessed"). Implementation plan Task 12.

- **Script:** `scripts/mlx_audio_calibrate.py`.
- **Data:** `docs/superpowers/2026-10-12-mlx-audio-calibration-data.json`. It holds
  every unit with its WAV path, both STT models' transcripts and scores, `flagged`,
  `recommendation` and `analysis`.

## Setup

| item | value |
|---|---|
| date | rendering 2026-10-13 00:10–00:30; re-derivation 01:44 |
| host | M4 Mac mini, 16 GB, light desktop load (a couple of browser tabs, Claude Desktop) |
| server | `~/tts-bakeoff/venvs/mlx`, mlx-audio 0.5.8 (mlx 0.32.3), `HF_HUB_OFFLINE=1`, `127.0.0.1:8781` (port 8765 → 8781: 8765 belongs to an unrelated operator process) |
| TTS model | `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16`, unseeded, server defaults |
| STT model (adopted) | `mlx-community/whisper-large-v3-turbo-asr-fp16`, the probe's choice; **operator decision** |
| STT model (comparison only) | `mlx-community/parakeet-tdt-0.6b-v3`, **rejected by the operator**; its saved transcripts are kept below as the comparison |
| text source | station root `/Volumes/media/lma-radio/delivered`, read-only, `dj_notes` set_intros + outro. 258 manifests: 129 have dj_notes, 129 have `dj_notes: null`, 0 unreadable or skipped. That gives 376 texts and 3904 distinct sentences after `normalize_for_speech` + `_split_sentences`. |
| units | 50 sentences sampled evenly across the length range (20–347 chars), 3 whole unchunked segments (698, 999, 1200 chars), 10 Voxtral sentences |
| voices (Qwen clones) | `phil_ex` (`~/tts-bakeoff/refs/phil_ex.wav` with its evaluated transcript), plus `monroe1`, `kurt1`, `troymcclure2`, `billgraham2` (`~/.emcee/samples/*.wav`, 48 kHz stereo, 22–30 s) with **STT-drafted** transcripts (Whisper) in `~/tts-bakeoff/refs/<stem>.draft.txt`. No voice was skipped. |
| Voxtral | `voxtral-mini-tts-2603`, clone of `troymcclure2.wav`; 10 sentences, all 200 |
| clips | `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-local-tts/99c83788-8478-441d-8793-405d9af30862/scratchpad/calibrate/clips/NNN-<kind>-<voice>.wav` (scratch; WAV paths in the data file) |

Commands:

```
./.venv/bin/python scripts/mlx_audio_calibrate.py --url http://127.0.0.1:8781 \
  --stt-model mlx-community/whisper-large-v3-turbo-asr-fp16 --stt-model mlx-community/parakeet-tdt-0.6b-v3 \
  --voxtral --server-pid <pid> --clips-dir $S/clips --out docs/superpowers/2026-10-12-mlx-audio-calibration-data.json
# after the operator's ruling and the matching change: no server, no model loaded
./.venv/bin/python scripts/mlx_audio_calibrate.py --url http://127.0.0.1:8781 \
  --stt-model mlx-community/whisper-large-v3-turbo-asr-fp16 --stt-model mlx-community/parakeet-tdt-0.6b-v3 \
  --out docs/superpowers/2026-10-12-mlx-audio-calibration-data.json --reuse --rescore \
  --artefacts 2,3,53 --max-s-per-char 0.09
```

The run renders every unit first. It then cuts the two known runaways out of the
bake-off mixes and transcribes everything once per STT model, unloading each model
between passes. `--rescore` re-scores the saved transcripts with the current matching
(`verify.match_words`) without loading a model.

## Derivation rules (`recommend`'s docstring)

- **Clean** = status ok, not a loop (under any STT model), not classified a defect
  (`classify`).
- **Guard**: TTS-only, computed once, over clean mlx units:
  - `max_floor_s` = 2.0.
  - `max_s_per_char` = the smallest 0.005 step with every clean unit ≤ 0.8 × (`max_floor_s` + `max_s_per_char` × chars). That is 25 % headroom.
  - `min_slack_s` = 0.5.
  - `min_s_per_char` = the largest 0.005 step with every clean unit ≥ 1.25 × (`min_s_per_char` × chars − `min_slack_s`).
  - `cap_s_per_char` = `max_s_per_char`; `cap_margin_s` = 1.0.
  - `cap_floor_s` = `max_floor_s` + 3.0, which satisfies ModelCalibration's invariant.
- **Verification**: per STT model, over that model's results on clean units, split at
  8 comparable words. It is derived three ways: every clean unit (`all`, the
  recommendation), clean mlx units only, and clean Voxtral units only.
  - `MISS_FLOOR` = max(2, 1 + worst short-unit missing).
  - `MISS_FRACTION` = max(0.15, 1.5 × worst long-unit missing/words), in 0.05 steps.
  - `EXTRA_FLOOR` = max(4, 1 + worst short-unit extra).
  - `EXTRA_FRACTION` = max(0.25, 1.5 × worst long-unit extra/words), in 0.05 steps.
- Every defect must fail the derived guard or thresholds (`defects_passing`).

## Per-voice durations (clean, status ok)

| voice | units | median s/char | max s/char | min s/char |
|---|---|---|---|---|
| phil_ex | 28 | 0.0566 | 0.084 | 0.0483 |
| monroe1 | 7 | 0.0516 | 0.0583 | 0.0447 |
| kurt1 | 6 | 0.0543 | 0.0622 | 0.0464 |
| troymcclure2 | 6 | 0.056 | 0.0627 | 0.0512 |
| billgraham2 | 6 | 0.0502 | 0.0547 | 0.0467 |
| voxtral-house (no guard) | 10 | 0.0569 | 0.104 | 0.0502 |

Clean-unit extremes (mlx):

| what | unit | chars | seconds | s/char |
|---|---|---|---|---|
| lowest s/char | #1 (monroe1) | 34 | 1.52 | 0.0447 |
| highest s/char | #0 (phil_ex) | 20 | 1.68 | 0.084 |
| shortest / longest text | — | 20 / 1200 | 1.68 / 66.88 | — |

- `max_s_per_char` is driven by #26: phil_ex, "The encore was Touch Of Grey…", 130 chars, 9.76 s. It sat at 0.787 of its long limit at the derived 0.08.
- `min_s_per_char` is driven by #25: monroe1, 126 chars, 5.68 s, at 1.251× its short limit.
- Leave-one-out on the guard: 0 of 53 fail.

## Known runaways

Both are cut from the bake-off's bed-mixed MP3s, so music sits under the voice.

| row | text | measured | adopted guard (0.09) | Whisper transcript check |
|---|---|---|---|---|
| `qwen3tts-0.6b-bf16` (set1-intro, sentence 5) | "This was the fifteenth show of the Europe seventy-two tour, …Concertgebouw in Amsterdam." (147 chars) | 320.0 s | **cap-margin check** (satisfied by construction: the clip is placed at the cap): "clip is 18.2s, at the 18.2s token cap"<br>**measured 320 s vs the non-cap long limit**: "320.0s > long limit 15.2s" | "heard 57 words for a 23-word script" |
| `chatterbox-fp16` (set2-intro, sentence 9) | "Here is Morning Dew." (20 chars) | 10.1 s | "clip is 10.1s, at the 6.8s token cap (a capped runaway)" | "only 1 of the script's 4 words were heard" |

Whisper's 0.6B transcript ends in "Oh, my God." nine times. Parakeet's transcript of the
same 320 s clip stops after the first clause ("…concert uh uh the the") and **passes**
the transcript check. That is one reason Parakeet was rejected (see below).

## Flagged units and their classification

The first scoring flagged 4 units. All were classified **artefact**:

| # | kind / voice | text | flags (first scoring) | WAV | classification |
|---|---|---|---|---|---|
| 0 | sentence / phil_ex | "Listen for West L.A." | Parakeet recall 0.60 ("LA") | `clips/000-sentence-phil_ex.wav` | artefact: **mechanical default accepted** (Whisper heard it exactly) |
| 2 | sentence / phil_ex | "Here is the second set, from Pittsburgh." | recall 0.67, both models ("Here's") | `clips/002-sentence-phil_ex.wav` | artefact: **by the operator** (Qwen itself said "Here's"; it sounded fine) |
| 3 | sentence / kurt1 | "Here is the Grateful Dead, live at Red Rocks." | recall 0.78, both models ("Here's") | `clips/003-sentence-kurt1.wav` | artefact: **by the operator** (same) |
| 53 | voxtral | "Listen for West L.A." | Parakeet recall 0.60; 1.83× its voice's median s/char | `clips/053-voxtral-voxtral-house.wav` | artefact: **by the operator** (listened; fine) |

- No unit errored, hit the measurement cap, looped, or was a defect.
- After the matching change (below), only #53 remains flagged, on duration alone.
- No unit contained "De Doelen".

## Verification: the matching change, and the thresholds

**Operator decision (option B).** All four first-scoring flags, and the first derived
values `MISS_FLOOR` 3 and `MISS_FRACTION` 0.35, came from joined or split words:
"Here is" heard as "Here's", and "L.A." as "LA". The operator approved folding these
into the matching. `verify.match_words` now counts both directions as found:

- A script bigram whose concatenation is one heard word, for example "l a"/"la" and "wharf rat"/"wharfrat".
- A heard bigram whose concatenation is one script word, for example "throw in"/"throwin".

Each heard word is used at most once.

Because `comparable_words` drops the apostrophe, "here's" is "heres", which is not
"here"+"is". So the join also recognises contractions through a fixed table:
is/has/us→s, are→re, am→m, have→ve, will→ll, would/had→d, not→nt. This is what makes
the operator's here+is ↔ heres example hold.

**Operator decision: the nothing-heard rule.** A script with at least one comparable
word fails when none of them was heard. Below `MISS_FLOOR` a total mishearing used to
pass. No "n ≤ 2, any miss" variant was adopted.

Re-derivation from the saved transcripts (130 re-scored, no model loaded):

| model | derivation | MISS_FLOOR | MISS_FRACTION | EXTRA_FLOOR | EXTRA_FRACTION | STOP ceilings |
|---|---|---|---|---|---|---|
| Whisper | **all (adopted)** | **2** | **0.25** | **4** | **0.25** | none exceeded |
| Whisper | mlx only | 2 | 0.25 | 4 | 0.25 | none |
| Whisper | Voxtral only | 2 | 0.15 | 4 | 0.25 | none |
| Parakeet (comparison) | all / mlx / Voxtral | 2 / 2 / 2 | 0.25 / 0.25 / 0.15 | 4 | 0.25 | none |

**Adopted in verify.py: 2 / 0.25 / 4 / 0.25.** These equal the values the operator
approved in advance. Compared with the interim values (2 / 0.25 / 4 / 0.5), only
`EXTRA_FRACTION` changed, from 0.5 to 0.25, which is tighter.

Step 3 checks under the adopted thresholds, Whisper:
- `verify_checks.clean_failures` = [].
- qwen3tts-0.6b-bf16 → "heard 57 words for a 23-word script".
- chatterbox-fp16 → "only 1 of the script's 4 words were heard".
- `defects_passing` = [].

Under Parakeet, the 0.6B runaway passes (null). That Step 3 check fails for Parakeet.

Missing and extra counts on clean units after the change (Whisper):

| backend | missing n / median / p90 / max | missing per word p90 / max | histogram | extra median / p90 / max | extra histogram |
|---|---|---|---|---|---|
| mlx | 53 / 0 / 2 / 3 | 0.048 / 0.158 | {0:37, 1:10, 2:2, 3:4} | 0 / 0 / 1 | {-1:5, 0:47, 1:1} |
| Voxtral | 10 / 0 / 0 / 1 | 0.0 / 0.038 | {0:9, 1:1} | 0 / 1 / 1 | {0:8, 1:2} |

Every remaining miss on a clean unit is an STT spelling, not a TTS fault:

- the lexicon's spellings: goin', feelin', Shugaree, Drumz, Wharfrat
- proper nouns: Godchaux, Kezar, Porcelina, "Saint" heard as "Santa"
- variants: grey/gray, Eddy/Eddie

**False alarms** (the share of clean takes the adopted thresholds would re-render):

- Leave-one-out, mlx: 1/53, unit #21. Without #21, `MISS_FRACTION` derives at 0.15, and #21's 3 misses in 19 words ("Wharfrat and Goin' Down The Road Feelin' Bad") would fail.
- Leave-one-out, Voxtral: 0/10.
- Interim thresholds: 0/53 and 0/10.
- Cross-backend: Voxtral-derived thresholds on mlx units fail 1/53 (#21); mlx-derived thresholds on Voxtral units fail 0/10.
- **Interpretation:** about 2 % of takes are one lexicon-heavy sentence away from a spurious re-render. The 95 % upper bound on 53 clean takes is about 5.7 %.

**What verification caught that the guard did not:** nothing. No calibration take had
a content defect, under either model or threshold set.

**Short sentences:**
- 0 of 63 units have ≤ 2 comparable words.
- In the 3904-sentence corpus, 1 does ("Some background first." — "first" is a number word), and 6 have exactly 3. The sentence splitter folds fragments under 20 chars into a neighbour.
- The nothing-heard rule fails 0 of 63 clean units under both models.

## STT model comparison (Parakeet kept as evidence)

| | Whisper large-v3-turbo asr-fp16 | Parakeet TDT 0.6B v3 |
|---|---|---|
| median / max transcription wall per clip | 1.22 s / 6.87 s | 0.31 s / 2.59 s |
| catches the 0.6B babble runaway by transcript | yes | **no** (its transcript stopped after one clause) |
| catches Chatterbox | yes | yes (0 of 4 heard) |
| derived thresholds (after the change) | 2 / 0.25 / 4 / 0.25 | 2 / 0.25 / 4 / 0.25 |
| disfluencies | smooths them (probe) | verbatim (probe) |

**Operator decision:** Whisper. Parakeet is rejected and its cache deleted. No STT
model id is hard-coded in packages/emcee; `[tts.mlx_audio] stt_model` stays unset by
default.

## Adopted guard constants

| field | derived | adopted | note |
|---|---|---|---|
| frame_rate_hz | 12.5 | 12.5 | qwen3_tts/config.py |
| cap_floor_s | 5.0 | 5.0 | |
| cap_s_per_char | 0.08 | **0.09** | kept equal to max_s_per_char (the derivation rule). The invariant holds: 0.09 ≥ 0.09, and 5.0 − 1.0 > 2.0 |
| max_floor_s | 2.0 | 2.0 | |
| max_s_per_char | 0.08 | **0.09** | **deviation, approved by the operator**: the probe measured a 28 % take-to-take spread on one sentence (6.32 s vs 8.08 s), and #26 sat at 0.787 of its 0.08 limit, so a 28 %-longer take of #26 would have been rejected |
| min_s_per_char | 0.04 | 0.04 | |
| min_slack_s | 0.5 | 0.5 | |
| cap_margin_s | 1.0 | 1.0 | |

Step 3 guard checks at 0.09 (`recommendation.adopted_guard`):
- `clean_failures` = []. The worst clean unit now sits at 0.712 of its long limit.
- chatterbox-fp16 = "clip is 10.1s, at the 6.8s token cap (a capped runaway)".
- qwen3tts-0.6b-bf16 cap-margin = "clip is 18.2s, at the 18.2s token cap (a capped runaway)".
- qwen3tts-0.6b-bf16 measured-vs-long-limit = "320.0s > long limit 15.2s".

**Synthetic cap-margin check** (`test_a_synthetic_cap_length_clip_fails_for_every_length`):
a clip at the cap, or one `cap_margin_s` below it, fails with "token cap" at 5, 20, 60,
150, 400 and 1200 characters.

## The bundled preflight clip (`packages/emcee/src/emcee/data/preflight_en.wav`)

| item | value |
|---|---|
| model | `mlx-community/Kokoro-82M-bf16`, HF revision `a71e4d38b236d968966a2002c4c895dbd12b1c3c` (cache `refs/main`) |
| voice file | `af_heart`, fetched by mlx-audio's Kokoro pipeline from `prince-canuma/Kokoro-82M`, revision `e02c9eada7ce7416798af36b190a8a2dd2ecd566` (`voices/af_heart.safetensors`) |
| license | Apache-2.0, as stated on the model cards (both repos; upstream `hexgrad/Kokoro-82M` also Apache-2.0) |
| lang_code | `a` |
| mlx-audio | 0.5.8 (mlx 0.32.3, misaki 0.9.4), `~/tts-bakeoff/venvs/kokoro`, served online on `127.0.0.1:8782` |
| request | `POST /v1/audio/speech` `{"model": "mlx-community/Kokoro-82M-bf16", "input": "Good evening, and welcome to the show.", "voice": "af_heart", "lang_code": "a", "response_format": "wav"}` |
| take | 1 of 3. All three passed; the first was kept. |
| format | 16-bit, mono, 24000 Hz, 2.625 s |
| sha256 | `74721f2126863262363cde20407fbf53c4d4915419894f23bbc2efba92f8f1ed` |
| transcript (Whisper) | "Good evening and welcome to the show." |
| check | `transcript_problem(PREFLIGHT_TEXT, transcript) is None` under the adopted thresholds. It was checked with them set during Step 4 and re-checked after verify.py was written. |

**The Kokoro venv.** It was installed with:

```
uv pip freeze --python ~/tts-bakeoff/venvs/mlx/bin/python > docs/superpowers/2026-10-12-mlx-audio-requirements.txt
uv venv --python 3.12 ~/tts-bakeoff/venvs/kokoro
uv pip install --python ~/tts-bakeoff/venvs/kokoro/bin/python "mlx-audio[server,tts,stt]==0.5.8" "misaki[en]" \
    -c docs/superpowers/2026-10-12-mlx-audio-requirements.txt
```

`misaki[en]` resolved under the constraints. One more step was needed.

- **What happened:** misaki's English G2P needs spaCy's `en_core_web_sm`. spaCy tried to download it on the first request by shelling out to `uv pip install`, which failed ("No virtual environment found") because the server process has no `VIRTUAL_ENV`. The request then hung after its 200.
- **What I did:** stopped the server and installed the model explicitly with `uv pip install --python ~/tts-bakeoff/venvs/kokoro/bin/python "en_core_web_sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl" -c docs/superpowers/2026-10-12-mlx-audio-requirements.txt` (en_core_web_sm 3.8.0, MIT). This is one of misaki's runtime dependencies, which Checkpoint 1 approved.
- **For the runbook:** a Kokoro venv needs this step.

## Memory headroom

The spec's "Unverified premises" section lists memory headroom. Two readings exist.

**1. Calibration run (`footprint -p <server pid>`):**
- After rendering, with Qwen resident and Whisper unloaded: 5068 MB.
- After the Whisper pass, with Qwen unloaded: 2786 MB.
- Lifetime `phys_footprint_peak`: **14 GB**. It most likely came from the 1200-char *unchunked* segment, which is not the production shape.

**2. Production shape.** One full real segment (unit #52, 1200 chars, 9 sentences) was
rendered sentence-chunked through emcee's own path:
`render_speech_mp3(..., chunk=True)` over `QualitySpeech(MlxAudioProvider(phil_ex, adopted calibration), backend="mlx_audio", verifier=Verifier(SttClient(whisper)))`,
preflight included. Whisper stayed resident. It ran on a freshly started server (port
8781, offline), with a scratch script and no `~/.emcee`. All 9 sentences passed
verification on the first attempt.

| | run 1 (first after server start) | run 2 (same shape, warm) |
|---|---|---|
| wall | 170.6 s | 159.5 s |
| server `phys_footprint` before → after | 1938 MB → 6423 MB | 6376 MB → 6434 MB |
| server `phys_footprint_peak` | **12 GB** | 12 GB (lifetime) |
| footprint samples every 10 s | 6.6–7.0 GB between sentences, spikes of 10–12 GB during generation | 6.6–7.0 GB, spikes of 11 GB |
| `vm.swapusage` before | total 3072 MB, used 1398.50 MB | total 6144 MB, used 4708.94 MB |
| `vm.swapusage` after | **total 6144 MB, used 5508.94 MB** | total 6144 MB, used 5075.12 MB |
| `memory_pressure` free % before → after | not captured → 76 % (a few minutes later) | 76 % → 70 % (dips to 16 % and 34 % at the spikes) |
| swapins / swapouts | 26787478 / 33283788 → 27526912 / 34300970 | 27578325 / 34300970 → 28234155 / 35025473 |

**SWAP GREW.**
- Run 1: the swap file grew from 3 GB to 6 GB, and used swap rose by about 4.1 GB (1.4 → 5.5 GB).
- Run 2: used swap rose by about 0.37 GB, and swapouts grew by about 0.72 M pages.

With Qwen 1.7B and Whisper resident, the server spikes to 10–12 GB during each
sentence's generation. On a 16 GB Mac with a light desktop load, that pushes the system
into swap. Rendering still completed with no errors, and transcription stayed fast. But
the memory-headroom premise is **not** comfortably met: the host is running at its
memory limit.

## Operator decisions and recommendations

1. **STT model:** `mlx-community/whisper-large-v3-turbo-asr-fp16`. Parakeet v3 is rejected.
2. **Verification:** the thresholds above are adopted. The default stays **off**
   (`[tts.verify] backends = []`).
   - **Recommendation:** enable it for `mlx_audio` when a Qwen presenter (Phil) goes live.
   - Keep `voxtral` off for now, for three reasons:
     - there are only 10 Voxtral takes;
     - the troymcclure2 clone is an announcer voice and produced no disfluencies (the operator listened to 053–062 and heard no ums or repeats), so the **disfluency effect on the thresholds is unmeasured**;
     - verification would make hosted voicing depend on the local mlx server.
   - Weigh the memory finding above before enabling it: Whisper resident is part of the shape that swapped.
3. **Matching change** (option B) and the **nothing-heard rule**: adopted, see above.
4. **Flagged units:** all artefacts, as classified in the table above.
5. **Guard:** the derived calibration with `max_s_per_char` = `cap_s_per_char` = 0.09.

**Go-live prerequisite (for the runbook, Task 15).** The four Whisper-drafted reference
transcripts `~/tts-bakeoff/refs/{monroe1,kurt1,troymcclure2,billgraham2}.draft.txt` are
fed to the clone as `ref_text`. The operator must correct them against the audio before
those voices go live. Suspect words seen in the drafts are listed below. They come from
reading the text only, not from listening, so the operator's ear decides:

| draft | suspect words |
|---|---|
| kurt1 | "Montecino" (Montecito?); "He was a freshman" (odd in context); "in the plastic steel" (plastic seal?) |
| billgraham2 | "instead of the 73rd"; "a group being so much like that" (garbled?) |
| troymcclure2 | "Tracy Ullman" (the show is "Tracey Ullman"); "Damnation" (a Groening comic title? check) |
| monroe1 | "WWNC", "WFBC" (call letters; check) |

## Opt-in live test

Run against the server on 8781:

```
EMCEE_MLX_URL=http://127.0.0.1:8781 EMCEE_MLX_STT_MODEL=mlx-community/whisper-large-v3-turbo-asr-fp16 \
  ./.venv/bin/pytest -m live packages/emcee/tests/test_mlx_live.py -q
```

Result: **1 passed in 17.32s**. That covers the verified preflight on phil_ex plus one
verified sentence, both with the adopted calibration. Every server was stopped afterwards
and ports 8781 and 8782 were confirmed free.

## What this does not show

- **Production rates are sampled, not proven.** The unseeded false-alarm and defect rates come from one take per text: 53 Qwen takes and 10 Voxtral takes. No content defect occurred, so verification's catch rate on real Qwen faults is unmeasured.
- **Untested presenters.** Presenters beyond these five voices are unmeasured, and four of the five clones used STT-drafted reference transcripts.
- **Voxtral disfluencies** were not exercised (announcer-voice clone).
- **The runaway evidence is limited.** It consists of two clips from other models (Qwen 0.6B, Chatterbox), cut from bed-mixed mixes. No 1.7B runaway was observed.
- **Memory** was measured on one host, under one desktop load, on one segment.
- **The go-live listen remains required.**
