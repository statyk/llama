# YAMNet ONNX export and parity with TF Hub (audio-check plan, Task 3)

## Branch taken: A (whole waveform model, front end included)

TF Hub `google/yamnet/1`'s `serving_default` signature (`waveform` float32 [N] -> scores,
embeddings, log-mel) was converted whole with tf2onnx at opset 17, so the bundled model
carries YAMNet's own log-mel front end; no numpy front end is needed (branch B not used).
tf2onnx lowered the STFT to a DFT matmul (`MatMul`, `Pow`, `Sqrt`, `Log`, ...), and the
graph uses only standard ONNX ops (op counts: Conv 27, Relu 27, Cast 11, Concat 11,
Reshape 9, Add 8, Unsqueeze 8, Mul 6, Sub 5, Max 4, Div 4, Gather 4, Shape 3, Slice 3,
Squeeze 3, Transpose 3, MatMul 3, Pad 2, Split 2, Range 2, Pow 2, Ceil, Sqrt, Log,
GlobalAveragePool, Sigmoid). onnxruntime 1.26.0 (TF venv) and 1.32.0 (llama venv,
Python 3.14) both load and run it. Only `output_0` (scores [F, 521]) is kept
(`onnx.utils.extract_model`).

One false start, recorded so it is not retried: wrapping the signature in a
`tf.function` and calling `tf2onnx.convert.from_function` left 27 resource (variable)
tensors as graph inputs. The CLI's `--saved-model` loader freezes them; the export script
runs that.

## Pinned combination (throwaway venv, macOS arm64, 2026-11-14)

- Python 3.11.15 (uv-managed)
- tensorflow 2.15.1, tensorflow_hub 0.16.1, tf2onnx 1.16.1, onnx 1.17.0, numpy 1.26.4,
  protobuf 3.20.3, setuptools 69.5.1 (`<70`: tensorflow_hub imports `pkg_resources`)
- parity decode: librosa 0.11.0, soxr 1.1.0, soundfile 0.14.0

Recipe and command: `scripts/export_yamnet_onnx.py` docstring.

## The file

- `packages/llama/src/llama/data/yamnet.onnx`: **16,108,442 bytes (16.11 MB)**, float32,
  not quantized (the spec's ~4 MB was wrong; the plan's ~15 MB estimate was close).
- sha256 `f6715c8eea28e034b467756202d1adc1f9cd6cc9582ee76021c2824d44d791a9`
  (= `llama.audio_check.model.MODEL_SHA256`).
- **The export is not byte-reproducible**: two runs of the same script in the same venv
  gave files one byte apart (16,108,442 / 16,108,441) with different sha256s. Re-exporting
  therefore changes `MODEL_SHA256`, which by design fails the VERSION pin test: a new
  export is a new model and needs parity re-run and `rule.VERSION` bumped.
- Class map: the Hub model's `class_map_path()` CSV is byte-equal (line endings folded)
  to the committed `packages/llama/src/llama/data/yamnet_class_map.csv` (the export
  script checks it and refuses otherwise).

## Parity (Step 2)

Five labelled tracks from the evidence, read from the station copy (read-only). Each was
decoded ONCE in the TF venv exactly as the spike did (librosa 32 kHz mono, resampled to
16 kHz) and the same float32 waveform was scored by TF Hub YAMNet and by the bundled ONNX
model through `model.load().frame_scores()` (onnxruntime 1.32.0), so the comparison
isolates the model. The TF side ran TF 2.15.1 (the spike's venv had TF 2.21) on the
same Hub SavedModel; the at-bar row below matching the spike's numbers suggests no drift.
(run_sec, frac) from Task 2's `rule.measure` on the decoded length.
Scripts: `onnx_parity_tf.py` (TF side), `onnx_parity_onnx.py` (ONNX side).

| track | label | dur s | frames | max diff (all 521) | max diff (Music/Speech/6 drums) | worst rule class | TF run_sec, frac, verdict | ONNX run_sec, frac, verdict |
|---|---|---|---|---|---|---|---|---|
| charlieparr-2003-01-10 `16 - Yo-Yo Blues.mp3` | song | 186.5 | 388 | 2.98e-06 | 2.98e-06 | Music | 160, 0.89, music | 160, 0.89, music |
| gratefuldead-1983-10-08 `13 - Space.mp3` | space | 476.9 | 993 | 4.89e-06 | 2.92e-06 | Music | 430, 0.96, music | 430, 0.96, music |
| furthur-2010-09-25 `01 - Tuning.mp3` | tuning | 165.1 | 344 | 3.28e-06 | 2.68e-06 | Speech | 0, 0.00, junk | 0, 0.00, junk |
| gratefuldead-1977-05-28 `30 - Crowd.mp3` | crowd | 153.9 | 320 | 2.83e-06 | 2.83e-06 | Music | 10, 0.13, junk | 10, 0.13, junk |
| smashingpumpkins-2008-08-12 `01 - Intro.mp3` | song (at bar) | 131.5 | 273 | 5.33e-06 | 4.53e-06 | Percussion | 120, 0.92, music | 120, 0.92, music |

**PASS**: identical verdicts on all five, max abs diff on the rule classes 4.5e-06 (bar
0.02). The at-bar track reproduces the spike's `population2.tsv` row exactly (run 120,
frac 0.92, music).
