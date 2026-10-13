# TTS bake-off results (M4 mini 16 GB; host already had 5-11 GB swap in use from other workloads, so all RTFs are pessimistic)

All renders: emcee's own `render_speech_mp3(text, provider, chunk=True, bed_pcm, bed_rate, bed_gain_db=-20)`, text from emcee's `_segment_texts` + `normalize_for_speech`,
reference = 12.9 s excerpt of phil.wav (24k mono) unless noted. Transport = mlx_audio.server HTTP (`/v1/audio/speech`) except F5 (own HTTP shim around f5-tts-mlx, own venv).
ASR/WER: mlx-whisper large-v3-turbo, number/ordinal canonicalisation, repetition-loop collapse. "load" = first request incl. model load (first-ever run includes download).

| model | ref | load s | synth s | audio s | RTF | peak footprint GB* | WER | wrong names | defects |
|---|---|---|---|---|---|---|---|---|---|
| Voxtral (aired baseline) | phil | - | - | 97.6 | - | - | 2.3% | De Doelen, Godchaux | none |
| Qwen3-TTS 1.7B Base bf16 | ex | 46.7 | 229 | 81.7 | 2.80 | 12* | 1.9% | De Doelen ("Dedoulin"), Godchaux ("Godshow") | none found |
| Qwen3-TTS 0.6B Base bf16 | ex | 66.9 | 200 | 84.3 | 2.37 | 12* | 4.2% | De Doelen, Godchaux, "Playin'", "Good Lovin'" | set1: one sentence ran away to 320 s of babble (max_tokens hit) |
| Chatterbox fp16 | ex | 30.8 | 202 | 108.2 | 1.87 | 10* | 9.3% | De Doelen, Godchaux, "Goodlovin'" | 4-word closer "Here is Morning Dew." rendered as ~10 s babble; slower pace |
| Higgs Audio v3 4B bf16 | ex | 47.0 | 908 | 75.9 | 11.96 | 12* | 2.3% | De Doelen, Godchaux | works but swap thrash (host swap 15.5/16 GB), unusable on this box |
| F5-TTS-MLX (mlx 0.25.2 pin) | ex | 30.3 | 470 | 140.2 | 3.35 | 12* | 3.7% | De Doelen, Godchaux | stretched pacing (140 s vs ~80 s); needs estimate_duration=True (default predictor returns ~0.04 s) |

*footprint figures are NOT trustworthy per model: `footprint` reported 10-12 GB for every model, including 0.6B; likely dominated by MLX allocator cache / system pressure. Unverified.

Long-form set1-intro (seed 42, ex ref): Qwen 1.7B: synth 316 s, 120.3 s audio, RTF 2.63, WER 2.3%, max ASR gap 1.3 s, no defects found.
Qwen 0.6B: synth 884 s, 432 s audio (!), WER 52% -> runaway sentence (see above). Voxtral set1 baseline copied to inputs/voxtral-set1-intro.mp3 (not transcribed).

Reference length (Qwen 1.7B, seed 42, set2): excerpt 12.9 s WER 3.3-3.7% / 79-81 s audio; full 26.4 s WER 2.3% / 77.1 s audio. Difference within noise; voice similarity not judged.
Determinism: seed set via wrapper (mx/np/random seed before server start) but two seed-42 renders differed (79.3 s vs 80.7 s, different WER) -> NOT deterministic via this path (per-request seed is not in the mlx-audio server API). Chatterbox: no Perth watermark code in mlx-audio's implementation (not verified by detector).
