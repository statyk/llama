# Junk-drop audio check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every junk-title drop is listened to by a bundled YAMNet classifier; a drop that sounds like music holds the show, and the rollout's commit and re-voice points refuse unchecked drops.

**Architecture:** A new package `llama.audio_check` holds four focused modules: the YAMNet model runner (ONNX + numpy front end), the pure measurement/verdict rule, the decoder, and the per-show verdict cache with a `Checker` that gather (online) and replay/reapply (cache-only) inject into `compute_gather`. A `llama audio-prepass` command fills caches from station copies before the rollout's replay arm; the rollout script and `reapply` gate on the recorded outcomes.

**Tech Stack:** Python 3.12, onnxruntime, miniaudio (decode + resample to 16 kHz), numpy, PyInstaller onefile; pytest offline suite with a fake classifier.

**Spec:** `docs/superpowers/specs/2026-11-14-junk-drop-audio-check-design.md` (commit e081073b). Evidence: `docs/superpowers/2026-11-14-audio-check-evidence/`. Read both before any task.

## Global Constraints

- Rule constants, verbatim: window `Music` > **0.55**; drum labels (`Drum kit`, `Drum`, `Percussion`, `Snare drum`, `Bass drum`, `Drum roll`) max > **0.3**; `Speech` < **0.3**; verdict `music` iff `run` >= **120 s** AND `frac` >= **0.60**. Fixed in code, never config.
- Windows: n = max(1, floor(duration_s / 10)) bins over the F YAMNet frames, bin k = frames [floor(k*F/n), floor((k+1)*F/n)), averaged; duration_s is the decoded length; no partial window dropped.
- `VERSION = "yamnet-onnx-1/rule-0.55-120-0.60"` is a literal constant; a test pins the bundled model file's sha256.
- Outcomes are exactly `music` | `junk` | `unchecked`. A stored verdict never becomes `unchecked`.
- The check never removes a track the current code keeps and never changes the kept track list: it only adds a hold flag and records an outcome.
- Nothing new is written to the station manifest (`DroppedTrack`/`Manifest` unchanged).
- No TensorFlow, PyTorch or ffmpeg at runtime or in the binary. TensorFlow may be used only by the one-off model-export script, in a throwaway venv.
- Runtime imports (`onnxruntime`, `miniaudio`) are lazy: only when a drop is checked.
- New-show failures never hold and never raise out of gather.
- Tests stay offline and deterministic; pipeline tests use a fake classifier. The only committed audio is the synthetic tone (Task 4), documented next to `preflight_en.wav`.
- In a git worktree, run `./.venv/bin/python -m pytest` with the worktree's own venv (repo CLAUDE.md).
- Implementers use `model: sonnet` only where the task header says so; Opus otherwise.

## Review Focus

1. **Decoded length vs metadata length** (VBR MP3s, padded frames): bins must use the decoded length; a 1 s disagreement must not shift the run by a window on a 120 s track more than the spike did. Test in Task 3 (`test_bins_use_decoded_length_not_metadata`).
2. **Very short or silent files** (a 4 s "Crowd", digital silence): one window, verdict `junk`, never a crash or `unchecked`. Test in Task 3 (`test_short_track_single_window_is_junk`) and Task 4 (`test_silent_file_is_junk`).
3. **Cache written by an older VERSION, read offline after a recalibration**: used as stored, hold kept. Test in Task 5 (`test_cache_only_uses_stale_verdict`).
4. **Same-titled drops in one show** (three "Tune Up" files): verdicts keyed per source file, never collapsed. Test in Task 5 (`test_same_title_files_keep_separate_verdicts`) and Task 9 (`test_prepass_pairs_same_title_drops_by_index`).
5. **Operator overrules the music hold, then the show is re-gathered with slightly different numbers**: the overrule still matches (filename key). Test in Task 6 (`test_music_overrule_survives_changed_numbers`).

---

### Task 1: Remove `silence` from the junk-title vocabulary (model: sonnet)

**Files:**
- Modify: `packages/llama/src/llama/junk_titles.py:28` (`_W`), docstring line 2
- Test: `packages/llama/tests/test_junk_titles.py`

**Interfaces:** Produces: `is_a_title("Silence") is False`; everything else unchanged.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("title", ["Silence", "silence", "SILENCE"])
def test_silence_is_not_junk(title):
    assert not junk_titles.is_a_title(title)

def test_crowd_and_tuning_still_junk():
    assert junk_titles.is_a_title("Crowd/Tuning") and junk_titles.is_a_title("Tune Up")
```
(Combination titles containing "silence" do not occur in the corpus; pin whatever the existing combo grammar now yields for `Crowd/Silence` with a one-line comment, no special case.)

- [ ] **Step 2: Run** `./.venv/bin/python -m pytest packages/llama/tests/test_junk_titles.py -q` — Expected: FAIL on `Silence`.
- [ ] **Step 3:** Drop `|silence` from `_W`; update the module docstring and any test that asserted silence drops.
- [ ] **Step 4: Run** the junk-title tests and `./.venv/bin/python -m pytest packages/llama/tests -q -k "junk or gather"` — Expected: PASS.
- [ ] **Step 5: Commit** `fix(junk-titles): "silence" is not a junk word (Gomez song; spec 2026-11-14)`.

---

### Task 2: YAMNet as a bundled ONNX model (GATE, model: opus)

The fallback-branch gate the spec requires. Produce a model file the runtime executes on all four legs and prove it matches TF Hub YAMNet.

**Files:**
- Create: `scripts/export_yamnet_onnx.py` (one-off; runs in a throwaway venv with `tensorflow`, `tensorflow_hub`, `tf2onnx`; documented in `scripts/CLAUDE.md`)
- Create: `packages/llama/src/llama/data/yamnet.onnx`, `packages/llama/src/llama/data/yamnet_class_map.csv`
- Create: `packages/llama/src/llama/audio_check/__init__.py`, `packages/llama/src/llama/audio_check/model.py`
- Create: `docs/superpowers/2026-11-14-audio-check-evidence/onnx-parity.md`
- Test: `packages/llama/tests/test_audio_check_model.py`

**Interfaces:**
- Produces: `model.load() -> Model` (raises `ClassifierUnavailable(LlamaError)` when the runtime or file can't load); `Model.frame_scores(wave16k: np.ndarray[float32]) -> np.ndarray` shape (F, 521); `model.CLASS_NAMES: tuple[str, ...]` (521, from the csv); `model.MODEL_FILE: Path`; `model.MODEL_SHA256: str` (literal).

- [ ] **Step 1: Export.** Branch A (try first): convert the TF Hub `google/yamnet/1` waveform model whole, front end included, with tf2onnx (opset >= 17 for STFT). Branch B (if A fails or onnxruntime rejects the ops): export only the core from the log-mel patch input, and implement YAMNet's front end in numpy in `model.py` (16 kHz, 25 ms window, 10 ms hop, periodic Hann, 512-pt FFT, 64 mel bins 125-7500 Hz, `log(mel + 0.001)`, 96-frame patches at 48-frame hop, padding as YAMNet's `features.py`). Record which branch and why in `onnx-parity.md`. Report the file size (expect ~15 MB float32; do not quantize).
- [ ] **Step 2: Parity.** On 5 labelled tracks from the evidence (one each: song, Space, tuning, crowd, at-bar `smashingpumpkins-2008-08-12`), compare ONNX frame scores to TF Hub: max abs diff per class and the resulting (run, frac) via Task 3's rule (or an inline copy if Task 3 is not merged). Pass: identical verdicts and max abs diff < 0.02 on `Music`/`Speech`/drum classes. Record the table in `onnx-parity.md`.
- [ ] **Step 3: Write tests**

```python
def test_model_file_sha256_pinned():
    assert hashlib.sha256(model.MODEL_FILE.read_bytes()).hexdigest() == model.MODEL_SHA256

def test_class_map_has_rule_labels():
    for name in ("Music", "Speech", "Drum kit", "Drum", "Percussion", "Snare drum", "Bass drum", "Drum roll"):
        assert name in model.CLASS_NAMES

def test_frame_scores_shape_on_tone():   # skip if onnxruntime missing
    wave = 0.1 * np.sin(2 * np.pi * 440 * np.arange(16000 * 3) / 16000).astype(np.float32)
    s = model.load().frame_scores(wave)
    assert s.shape[1] == 521 and 5 <= s.shape[0] <= 7

def test_load_failure_is_classifier_unavailable(monkeypatch):
    monkeypatch.setattr(model, "MODEL_FILE", Path("/nonexistent.onnx"))
    with pytest.raises(model.ClassifierUnavailable): model.load()
```
- [ ] **Step 4:** Add `onnxruntime>=1.18`, `numpy>=1.26` to `packages/llama/pyproject.toml` dependencies; `./.venv/bin/pip install -e packages/llama`; run the tests — Expected: PASS.
- [ ] **Step 5: Commit** `feat(audio-check): bundled YAMNet ONNX model with parity record`. **Report to the operator** (boundary): branch taken, file size, parity table.

---

### Task 3: Measurement and verdict rule (model: sonnet)

**Files:**
- Create: `packages/llama/src/llama/audio_check/rule.py`
- Test: `packages/llama/tests/test_audio_check_rule.py`

**Interfaces:**
- Consumes: `model.CLASS_NAMES`.
- Produces: `VERSION: str` (the Global Constraints literal); `@dataclass(frozen=True) class Measure: run_sec: int; frac: float`; `windows(frame_scores: np.ndarray, duration_sec: float) -> np.ndarray` (n, 521); `measure(frame_scores, duration_sec) -> Measure`; `verdict(m: Measure) -> Literal["music","junk"]`; constants `MUSIC_MIN=0.55, DRUM_MIN=0.3, SPEECH_MAX=0.3, RUN_MIN_SEC=120, FRAC_MIN=0.60, WINDOW_SEC=10`.

- [ ] **Step 1: Write the failing tests** (synthetic score arrays; build with a helper `scores(F, music=..., speech=..., drum=...)`):

```python
def test_bins_cover_all_frames_no_partial_drop():
    w = rule.windows(np.ones((25, 521)), duration_sec=12.4)   # n = 1
    assert w.shape == (1, 521)

def test_bins_use_decoded_length_not_metadata():
    assert rule.windows(np.ones((260, 521)), 125.0).shape[0] == 12

def test_music_run_and_frac():
    m = rule.measure(scores(260, music=0.9, speech=0.0), 125.0)
    assert m == rule.Measure(run_sec=120, frac=1.0) and rule.verdict(m) == "music"

def test_speech_blocks_music():
    assert rule.verdict(rule.measure(scores(260, music=0.9, speech=0.5), 125.0)) == "junk"

def test_drum_clause_counts_as_musical():
    assert rule.verdict(rule.measure(scores(260, music=0.1, drum=0.6), 125.0)) == "music"

def test_thresholds_are_strict_and_inclusive_as_spec():
    # Music must be > 0.55 (0.55 itself is not musical); run >= 120 and frac >= 0.60 pass.
    assert rule.verdict(rule.measure(scores(260, music=0.55), 125.0)) == "junk"

def test_frac_bar():
    frames = np.vstack([scores(120, music=0.9), scores(90, music=0.0, speech=0.9)])
    m = rule.measure(frames, 210.0)            # 21 windows: 12 musical then 9 talk
    assert m == rule.Measure(run_sec=120, frac=12 / 21) and rule.verdict(m) == "junk"

def test_short_track_single_window_is_junk():
    assert rule.verdict(rule.measure(scores(8, music=1.0), 4.0)) == "junk"
```
- [ ] **Step 2: Run** — Expected: FAIL (module missing).
- [ ] **Step 3: Implement.** Label indices come from `model.CLASS_NAMES.index(name)`; `run_sec = longest_run * WINDOW_SEC`.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Spike parity test**: `test_rule_reproduces_spike_on_population2` reads `docs/superpowers/2026-11-14-audio-check-evidence/population2.tsv` and asserts `rule.verdict(Measure(run_055, frac_055)) == music_chosen` for every row (pure arithmetic, no audio). Commit `feat(audio-check): window measure and verdict rule`.

---

### Task 4: Decoder and single-file classify, plus the synthetic tone (model: sonnet)

**Files:**
- Create: `packages/llama/src/llama/audio_check/decode.py`, `packages/llama/src/llama/audio_check/classify.py`
- Create: `scripts/make_audio_check_tone.py` (lameenc, already in the dev env via emcee) and committed `packages/llama/src/llama/data/audio_check_tone.mp3` (~5 s, 440 Hz + harmonics, mono 16 kHz, < 20 KB)
- Modify: root `CLAUDE.md` Conventions (the no-audio exception list gains the tone, one line)
- Test: `packages/llama/tests/test_audio_check_classify.py`

**Interfaces:**
- Consumes: `model.load`, `rule.measure`, `rule.verdict`.
- Produces: `decode.to_16k_mono(path: Path) -> tuple[np.ndarray, float]` (wave, decoded seconds) raising `DecodeError(LlamaError)` for unreadable or non-MP3/FLAC (by content, via miniaudio); `@dataclass(frozen=True) class Result: verdict: str; run_sec: int; frac: float`; `classify.classify_file(path: Path) -> Result` (raises `ClassifierUnavailable` / `DecodeError`); `classify.get_model() -> Model` caches one loaded model per process and, the first time loading fails, prints one stderr line `llama: audio check unavailable (<reason>); junk-title drops are recorded unchecked`.

- [ ] **Step 1: Write the failing tests**

```python
def test_tone_mp3_decodes_to_16k():
    wave, sec = decode.to_16k_mono(TONE)
    assert 4.5 < sec < 5.5 and abs(len(wave) - 16000 * sec) < 160

def test_non_audio_is_decode_error(tmp_path):
    p = tmp_path / "x.mp3"; p.write_text("not audio")
    with pytest.raises(decode.DecodeError): decode.to_16k_mono(p)

def test_silent_file_is_junk(fake_model):          # fake_model returns zeros
    assert classify.classify_file(TONE).verdict == "junk"

def test_unavailable_warns_once(monkeypatch, capsys):
    ...  # two classify_file calls with load() raising -> exactly one stderr line
```
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** with `miniaudio.decode_file(path, output_format=SIGNED16, nchannels=1, sample_rate=16000)`; add `miniaudio>=1.59` to dependencies.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `feat(audio-check): decode and classify one file; synthetic tone`.

---

### Task 5: Verdict cache and the Checker (model: opus)

**Files:**
- Create: `packages/llama/src/llama/audio_check/cache.py`
- Modify: `packages/llama/src/llama/workspace.py` (add `ShowWorkspace.audio_check = dir / "audio-check.json"`; NOT in `show_stage_artifacts`)
- Test: `packages/llama/tests/test_audio_check_cache.py`

**Interfaces:**
- Consumes: `classify.classify_file`, `rule.VERSION`, `IAClient.download_file(identifier, filename, dest, md5)`.
- Produces:
  - `@dataclass(frozen=True) class Outcome: check: Literal["music","junk","unchecked"]; run_sec: int | None; frac: float | None; error: str | None = None; stale: bool = False`
  - `identity(identifier: str, filename: str, metadata: dict) -> dict` — `{"identifier", "filename", "md5"}` or, with no md5 in `metadata["files"]`, `{"identifier","filename","size"}`.
  - `lookup(cache_path: Path, identifier: str, filename: str, metadata: dict) -> CachedVerdict | None` (shared by gather, `_show_json_plan`, pre-pass); `CachedVerdict(verdict, run_sec, frac, version, checked_at)`; raises `CacheUnreadable` on a corrupt file.
  - `write_verdicts(cache_path: Path, entries: list[tuple[dict, Result]]) -> None` — merge by identity, atomic via `workspace.atomic_write_text`.
  - `class Checker: __init__(self, cache_path: Path, metadata: dict, identifier: str, *, ia=None, tmp_dir: Path | None = None)`; `check(filename: str) -> Outcome`; `new_verdicts: list[tuple[dict, Result]]` (online computations for `run_gather` to write). `ia=None` means cache-only.
  - Semantics (spec "The verdict cache"): current cached -> its verdict; stale + online -> recompute, on failure use stale with `stale=True` and a note; stale + cache-only -> use as stored (`stale=True`); missing + online -> fetch to `tmp_dir`, classify, delete; missing + cache-only -> `unchecked` (`error="no cached verdict"`); unreadable + online -> treat as missing; unreadable + cache-only -> `unchecked` (`error="verdict cache unreadable"`); any fetch/decode/unavailable failure online -> `unchecked` with the reason.

- [ ] **Step 1: Write the failing tests** (fake `classify_file`, fake `ia`):

```python
def test_cached_current_verdict_used_without_classifier(tmp_path): ...   # classify_file must not be called
def test_cache_only_uses_stale_verdict(tmp_path): ...                   # version "old" stored music -> Outcome("music", stale=True)
def test_online_stale_recompute_failure_keeps_stale(tmp_path): ...
def test_cache_only_missing_is_unchecked(tmp_path): ...
def test_unreadable_cache_online_recomputes_and_cache_only_is_unchecked(tmp_path): ...
def test_online_miss_fetches_classifies_and_deletes_temp(tmp_path): ...  # temp file gone; new_verdicts has one entry
def test_fetch_failure_is_unchecked_with_reason(tmp_path): ...
def test_same_title_files_keep_separate_verdicts(tmp_path): ...
def test_identity_falls_back_to_size_without_md5(): ...
def test_write_is_atomic_merge(tmp_path): ...                           # existing entries for other files survive
def test_cache_not_a_stage_artifact():
    assert ws.audio_check not in sum((show_stage_artifacts(ws, s) for s in SHOW_STAGE_ORDER), [])
```
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `feat(audio-check): per-show verdict cache and Checker`.

---

### Task 6: Gather integration, music hold and its overrule (model: opus)

**Files:**
- Modify: `packages/llama/src/llama/junk_titles.py` (`JunkDrop` gains `check: str = "unchecked"`, `run_sec: int | None = None`, `frac: float | None = None`, `check_error: str | None = None`; add `MUSIC_PREFIX = "junk-title drop sounds like music: "` and `music_flag(drop: JunkDrop) -> str`)
- Modify: `packages/llama/src/llama/stages/gather.py` (`compute_gather(..., checker_factory=None)`, `GatherResult.new_verdicts`, `run_gather` builds the online checker and writes the cache, excluded rows carry the outcome, notes)
- Modify: `packages/llama/src/llama/overrules.py` (`_PATTERNS` entry), `packages/llama/src/llama/adjudicator/gate.py` (`OVERRULE_BAR["junk-music"] = "never"`), `packages/llama/src/llama/replay.py` (`_FAMILIES` entry `("junk-music", lambda f: f.startswith(junk_titles.MUSIC_PREFIX))`)
- Test: `packages/llama/tests/test_gather_audio_check.py`, extend `test_overrules.py`

**Interfaces:**
- Consumes: `cache.Checker`, `cache.Outcome`.
- Produces:
  - `compute_gather(..., checker_factory: Callable[[str, dict], Checker] | None = None)` — called as `checker_factory(identifier, metadata)` only when `_junk_drop` dropped something; None means every drop is `unchecked` with `check_error="no checker"` (keeps all existing callers' behaviour).
  - `music_flag(drop)` -> `f"{MUSIC_PREFIX}'{title}' ({m}:{ss}) {run_m}:{run_ss} continuous, {pct}% music, file {filename}"`.
  - excluded row for a junk-title drop gains keys `check`, `run_sec`, `frac`, `check_error` (the latter only when unchecked).
  - `GatherResult.new_verdicts: tuple = ()`; `run_gather(...)` writes them with `cache.write_verdicts(show_ws.audio_check, ...)` after `show.json`.
  - Notes: one gather note per unchecked drop `audio check skipped for <filename>: <error>`, one per stale use `audio check used a stale verdict for <filename>`.
  - Overrule: `(re.compile(r"^junk-title drop sounds like music: .* file (.+)$", re.S), "junk-music", "raw")`.

- [ ] **Step 1: Write the failing tests** (a fake checker returning scripted outcomes; the gd73-06-10 fixture or the existing junk-drop gather fixtures):

```python
def test_music_outcome_adds_hold_and_keeps_drop(...):
    # track list identical to the no-checker run; flags gain exactly one MUSIC_PREFIX flag ending "file <filename>"
def test_junk_outcome_changes_nothing(...)
def test_unchecked_outcome_records_and_notes_but_never_holds(...)
def test_checker_not_built_when_nothing_dropped(...)
def test_kept_track_list_identical_for_every_outcome(...)   # strict surface (1): music/junk/unchecked/raise
def test_checker_exception_is_unchecked_not_raise(...)
def test_excluded_row_carries_outcome(...)
def test_run_gather_writes_new_verdicts_to_cache(...)
def test_music_overrule_survives_changed_numbers():
    k1 = flag_key(music_flag(drop_with(run=550, frac=0.98)), show); k2 = flag_key(music_flag(drop_with(run=540, frac=0.97)), show)
    assert k1 == k2 and k1.kind == "junk-music"
def test_music_and_size_holds_have_distinct_kinds(): ...
def test_adjudicator_bar_never_for_music_hold(): ...
```
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** Call the checker after `_junk_drop` and before `renumber_text`'d flags are appended; append music flags after the size `hold_flag`s, using `jd`'s drops. `run_gather` passes `checker_factory=lambda ident, md: Checker(show_ws.audio_check, md, ident, ia=ia, tmp_dir=<temp dir>)`. Metadata is the `md = ia.metadata(identifier)` gather already reads.
- [ ] **Step 4: Run** the new tests plus `./.venv/bin/python -m pytest packages/llama/tests -q` — Expected: PASS (all existing gather/replay tests unchanged).
- [ ] **Step 5: Commit** `feat(gather): audio-check every junk-title drop; music holds the show`.

---

### Task 7: Replay, arm rows, input digests and the reapply commit-point gate (model: opus)

**Files:**
- Modify: `packages/llama/src/llama/replay.py` (`compute_legs` passes a cache-only `checker_factory` built from `ws.audio_check` and `CacheOnlyIA.metadata`; `input_digests` gains `"audio-check.json"`; arm row `junk_drops` dicts gain `check`, `run_sec`, `frac`, `check_error`)
- Modify: `packages/llama/src/llama/reapply.py` (new outcome `skipped: unchecked drop (<files>)`)
- Test: `packages/llama/tests/test_replay_audio_check.py`, extend `test_reapply.py`

**Interfaces:**
- Consumes: `cache.Checker(ia=None)`, `GatherResult.junk_drops` with outcomes.
- Produces: arm-row keys above; `ReapplyOutcome` status string `skipped: unchecked drop (<comma-separated filenames>)`, retryable, written nothing (same no-write path as `skipped: inputs changed`).
- Decision (plan's reading of the spec's "when `reapply` runs from a rollout list"): the gate applies to **every** `reapply`, since reapply is only the campaign/rollout tool; it is strictly safer and needs no mode flag.

- [ ] **Step 1: Write the failing tests**

```python
def test_replay_checker_reads_real_show_dir_not_scratch(...)   # cache in ws.dir found; scratch has only overrides
def test_replay_never_downloads(...)                             # CacheOnlyIA.download_file never called
def test_input_digests_include_audio_check(...)
def test_arm_row_junk_drops_carry_outcome(...)
def test_reapply_skips_show_with_unchecked_drop_and_writes_nothing(...)   # show.json, package, campaign.json bytes unchanged
def test_reapply_commits_when_all_drops_junk_or_music(...)
def test_cache_change_after_arm_is_inputs_changed(...)
```
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** full suite — PASS.
- [ ] **Step 5: Commit** `feat(replay,reapply): cache-only audio check; reapply skips unchecked drops`.

---

### Task 8: Diagnostic subcommand and status count (model: sonnet)

**Files:**
- Modify: `packages/llama/src/llama/cli.py` (hidden `_audio-check FILE` command; `status` gains the unchecked count)
- Test: `packages/llama/tests/test_cli_audio_check.py`

**Interfaces:**
- Produces: `llama _audio-check FILE` prints exactly `verdict=<music|junk> run=<int> frac=<0.00>` and exits 0; exits 2 with `unchecked: <reason>` on `ClassifierUnavailable`/`DecodeError`. `llama status` prints a line `audio check: <n> show(s) with unchecked junk-title drops` when n > 0 (counted from library `show.json` excluded rows with `check == "unchecked"`).

- [ ] **Step 1: Tests**: `test_audio_check_cmd_prints_verdict(fake_model)`, `test_audio_check_cmd_unchecked_exit_2`, `test_audio_check_hidden_from_help`, `test_status_counts_unchecked_shows`.
- [ ] **Step 2-4:** fail, implement, pass.
- [ ] **Step 5: Commit** `feat(cli): _audio-check diagnostic and unchecked count in status`.

---

### Task 9: `llama audio-prepass` (model: opus)

**Files:**
- Create: `packages/llama/src/llama/audio_check/prepass.py`
- Modify: `packages/llama/src/llama/cli.py` (command registration)
- Test: `packages/llama/tests/test_audio_prepass.py`

**Interfaces:**
- Consumes: `cache.lookup/write_verdicts`, `classify.classify_file`, `audio_reuse.plan_reuse(show_ws, station_dir, strict=False)`, `audio.read_duration`, `IAClient.download_file`, the library show lock (`locks.file_lock` as llama's stages take it), `junk_titles` patterns.
- Produces: `llama audio-prepass --out DIR [--arm FILE] [--slug SLUG ...]`.
  - Input per show: every `show.json` track whose title matches `junk_titles` A/B/C vocabulary ignoring position (`is_a_title or is_intro_title or is_outro_title`), plus, with `--arm`, every `junk_drops` filename of that show's arm row.
  - Audio: pair via `plan_reuse(...).station[source]`; accept the station file only if `read_duration` is within the same tolerance `reuse_into` uses of the metadata `length`; else fetch from archive.org to a temp file.
  - Skips files whose cache already holds a current verdict (resumable).
  - Before any show: `classify.get_model()`; on `ClassifierUnavailable` exit 3 with `audio-prepass: classifier unavailable (<reason>); nothing written`.
  - Writes `DIR/summary.json`: `{"version", "started_at", "finished_at", "files": [{"slug","source_file","outcome": "music|junk|failed","run_sec","frac","error"}]}` (atomic, rewritten after each show so an interrupted run leaves a valid file).
  - Takes the show lock per show; never the station lock; writes only `audio-check.json` and `DIR`.
- Create also: `scripts/audio_check_population.py --summary DIR/summary.json` compares to `population2.tsv` on its (slug, source_file) rows: prints flips, the held-show count, and exits 1 if a caught labelled song flipped to junk outside the at-bar exemption or the held count is outside 28 +/- 3 (spec "Pass bar").

- [ ] **Step 1: Tests** (temp library with two shows, fake station dir, fake classifier, fake ia): `test_prepass_input_superset_includes_mid_show_intro`, `test_prepass_pairs_same_title_drops_by_index`, `test_prepass_rejects_station_file_with_wrong_length_and_fetches`, `test_prepass_resumes_skipping_cached`, `test_prepass_unavailable_exits_3_writes_nothing`, `test_prepass_failure_recorded_with_reason`, `test_prepass_arm_adds_drops`, `test_population_script_pass_and_fail` (synthetic tsv + summary).
- [ ] **Step 2-4:** fail, implement, pass.
- [ ] **Step 5: Commit** `feat(audio-check): rollout pre-pass and population gate script`.

---

### Task 10: Rollout script: outcomes in the list, live re-voice gate (model: opus, strict surface)

**Files:**
- Modify: `scripts/junk_drop_rollout.py` (`_arm_drops`, `_show_json_plan`, `cmd_list` report, `cmd_approval`, `cmd_recheck`)
- Test: `packages/llama/tests/test_junk_drop_rollout.py` (existing file; extend)

**Interfaces:**
- Consumes: arm rows' outcome keys (Task 7); `cache.lookup` for needs-llm rows (metadata from `<root>/cache/md_<identifier>.json`).
- Produces:
  - Each drop dict in `members.json` gains `check`, `run_sec`, `frac`; `held` becomes `size_held or check == "music"` and a separate `music_held` key.
  - `list` prints per member each drop `(slug, source file, outcome)` and a final `unchecked: <n>` line. It never refuses on counts.
  - `approval` and `recheck`, for each voiced member, re-read live `show.json` `excluded_files` junk-title rows; refuse a row whose `check` is not `junk` unless `check == "music"` and the show's overrides hold an overrule matching its `junk-music` key. Message: `<slug>: <filename> audio check is <check>; clear the hold with llama triage (records an overrule) or retitle the track`.

- [ ] **Step 1: Tests**: `test_list_carries_outcome_and_unchecked_total`, `test_show_json_plan_reads_cache_for_needs_llm_rows`, `test_recheck_refuses_unchecked_voiced_drop`, `test_recheck_refuses_music_without_overrule`, `test_recheck_passes_music_with_overrule`, `test_recheck_reads_live_show_json_not_list`, `test_approval_lists_refusal_with_remedy`.
- [ ] **Step 2-4:** fail, implement, pass.
- [ ] **Step 5: Commit** `feat(rollout): audio-check outcomes in list; live re-voice gate`.

---

### Task 11: Packaging, smoke step and the labelled gate (model: opus)

**Files:**
- Modify: `packaging/llama.spec` (onnxruntime and miniaudio native libraries: `collect_dynamic_libs("onnxruntime")`, hiddenimports as needed; model, class map and tone already ride `collect_data_files("llama.data")`)
- Modify: `packaging/build.py` (`smoke_test` runs `<binary> _audio-check <extracted tone path>`; fails unless output starts `verdict=`)
- Modify: `.github/workflows/release.yml` only if a leg needs a build dep
- Create: `scripts/audio_check_labelled_gate.py --binary PATH` (runs the binary's `_audio-check` over the 145 labelled tracks listed from the evidence sample/label files, station paths; prints flips; exit 1 per the spec pass bar)
- Test: `packages/llama/tests/test_build_smoke.py` (unit-test the smoke-output parser)

**Interfaces:** Produces: a dry-run release (`workflow_dispatch` dry run, or the existing dry-run mode in `release.yml`) green on all four legs with the new smoke step; size and `llama --version` startup time before/after per leg recorded in `docs/superpowers/2026-11-14-audio-check-evidence/packaging.md`.

- [ ] **Step 1:** unit test for the smoke parser; implement; pass.
- [ ] **Step 2:** dry-run release build; if a leg cannot carry onnxruntime or miniaudio, **stop and report to the operator** (spec: a leg ships always-unchecked only by operator decision).
- [ ] **Step 3:** download the macOS arm64 artifact; run `scripts/audio_check_labelled_gate.py --binary <artifact>` on this Mac (station share mounted). Expected: exit 0, flips listed. Record results in `packaging.md`.
- [ ] **Step 4: Commit** `build(llama): bundle onnxruntime + miniaudio + YAMNet; audio-check smoke step`. **Report to the operator** (boundary): sizes, startup, gate result.

---

### Task 12: Runbook and docs (model: sonnet)

**Files:**
- Modify: `docs/superpowers/plans/2026-11-14-junk-tag-drop.md` Appendix A: insert the pre-pass step before the arm (spec "Runbook order"), the population gate (`scripts/audio_check_population.py`), "any pre-pass run after an arm invalidates that arm: re-arm and rebuild the list", acceptance readings (~28 held by the check, 8 size-held; `unchecked` total 0 except recorded failures), and the reapply `skipped: unchecked drop` retry loop.
- Modify: `packages/llama/CLAUDE.md` (junk-title drop paragraph: the audio check, outcomes on excluded rows, `audio-check.json` not a stage artifact, music hold kind `junk-music`, `_audio-check`, `audio-prepass`), `scripts/CLAUDE.md` (the three new scripts), root `CLAUDE.md` (only the audio-exception line from Task 4 if not already there).

- [ ] **Step 1:** edit; **Step 2:** `./.venv/bin/python -m pytest -q` full suite green (state the command and count in the commit message); **Step 3: Commit** `docs(audio-check): rollout runbook and component docs`.
