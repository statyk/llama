# Paragraph-Aware Chunking (emcee) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Voice each DJ segment in paragraph-aware chunks of up to 250 characters, fill exact-silence runs with the segment's own room tone, stop splitting after dotted abbreviations, and have the scriptwriter write paragraphs, without weakening the content-filter repair.

**Architecture:** Two pure helpers land first (`plan_chunks` in `audio.py`, `fill_room_tone` in a new `tts/room_tone.py`). A behaviour-preserving refactor then replaces `chunk: bool` with one required `chunking: Chunking | None` argument from the CLI/`process_package` boundary down. After that, `_chunked_pcm` switches to the packer and room tone and the cache key gains the chunk digest. In-chunk narrowing goes into the same loop. Prompt and doc changes come last.

**Tech Stack:** Python 3.11+, numpy, pydantic v2, pytest; emcee package only (`packages/emcee`).

**Spec:** `docs/superpowers/specs/2026-10-26-paragraph-chunking-design.md`. Read it before any task: it carries the reasons, the measured values and the strict surfaces.

## Global Constraints

- Ceiling default **250** characters; `[tts] chunk_chars` is a strict integer, **50 to 1000**; `[tts] room_tone` bool, default **true**.
- Join silence stays **180 ms** (`_SILENCE_MS`); `_MIN_FRAGMENT_LEN` stays **20**.
- Room tone: 20 ms frames, quietest **8%** by RMS, **5 ms** crossfades, fills exact-zero runs of **≥ 20 ms**, pool excludes frames containing an exact-zero run of **≥ 1 ms**; mono only; seed from sha256 of the spoken text, never `hash()`.
- No chunk sent to a provider contains `"\n"` (mlx_audio splits generations on it).
- The **unchunked** cache key stays byte-identical to today's formula; unchunked rendering stays one call per segment.
- `_locate_block` and `rephrase_problems` keep splitting by sentence; `render_speech_mp3`'s chunked re-raise stays.
- emcee never imports llama.
- **Worktree venv:** this worktree has its own `.venv` (created in Task 0). Always run `./.venv/bin/python -m pytest ...` from the worktree root, never a bare `pytest` and never `./.venv/bin/pytest`.
- **Mutation checks** (spec Acceptance): after committing each task, break each new rule by hand. Before running, write down which test you expect to fail first. Run with `PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -m pytest -p no:cacheprovider packages/emcee -q`, see that test fail, then restore with `git checkout -- <file>` and confirm `git status` is clean. Report each mutation (edit, predicted test, observed result) in the task's handback. A mutation that fails nothing means the test is missing: add one.

## Review Focus

1. **CRLF paragraph breaks** (an `emcee say` file saved on Windows: `"\r\n\r\n"`) must count as one paragraph break, and no `"\r"` may reach a provider. Test in Task 2.
2. **Whitespace-only or trailing blank paragraphs** (a script ending `"...\n\n  \n"`) must produce no empty chunk and no empty provider call. Test in Task 2.
3. **A whole segment shorter than 20 characters** has no neighbour to join; it must come out as one chunk with no error. Test in Task 2.
4. **PCM whose length is not a whole number of 20 ms frames**, or with a zero run that touches both clip edges, must be filled without an index error, and the length must be unchanged. Test in Task 3.
5. **A content-filter block on a multi-sentence chunk while a bed is active** (the bed path calls `_segment_pcm` → `_chunked_pcm`) must narrow and fall back exactly as without a bed. Test in Task 6.

---

### Task 0: Worktree venv (setup, no commit)

- [ ] **Step 1:** From the worktree root `/Users/shawn/projects/llama/.claude/worktrees/emcee-paragraph-chunking`, run:
  `python3 -m venv .venv && ./.venv/bin/pip install -q -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"`
- [ ] **Step 2:** Run `./.venv/bin/python -c "import emcee, herder; print(emcee.__file__, herder.__file__)"`. Expected: both paths are inside this worktree.
- [ ] **Step 3:** Run `./.venv/bin/python -m pytest packages/emcee -q`. Expected: all pass. Record the count as the baseline.

---

### Task 1: Dotted abbreviations stay whole in `_split_sentences`

**Files:**
- Modify: `packages/emcee/src/emcee/audio.py` (`_split_sentences`, around lines 53-87)
- Test: `packages/emcee/tests/test_audio.py` (the `_split_sentences` block)

**Interfaces:**
- Produces: `_split_sentences(text: str) -> list[str]`, same signature. It now never splits after a token of two or more single letters each followed by a dot (`U.S.`, `D.C.`, `B.B.`).

- [ ] **Step 1: Write the failing tests**

```python
OUTRO_1974_05_19 = (  # gratefuldead-1974-05-19 outro, verbatim (spec section 4)
    "And that brings us to the end of the Grateful Dead at the Portland Memorial Coliseum in "
    "Portland, Oregon, on May nineteenth, 1974. Think back over that second set: Truckin' "
    "sprinting ahead at full force, then the jam stretching out and turning quieter and slinkier "
    "under Keith's electric piano before it settled into Not Fade Away, then Goin Down The Road "
    "Feelin Bad, and finally Bob Weir shouting his way through One More Saturday Night. The "
    "encore was U.S. Blues, still a new song that spring, where I'd say the real star was Phil "
    "Lesh's bass, while Garcia and Keith Godchaux took the solo on together like a beast with "
    "two heads. Earlier in the night we also had the Weather Report Suite and a Wharf Rat full "
    "of pregnant pauses that, to my ear, belongs among the best. Tonight's recording came from "
    "the master soundboard reels, and the same concert was officially released in 2018 as part "
    "of the Pacific Northwest box set. As I see it, the universe hands out only so many nights "
    "like this one, and the tapes are how we hold on to them. I'm Professor Chapman, and this "
    "has been One More from the Archive. Join me next time, when we'll pull another reel off "
    "the shelf and see what it remembers.")


@pytest.mark.parametrize("token", ["U.S.", "D.C.", "L.A.", "B.B.", "K.C.", "U.K."])
def test_split_keeps_dotted_abbreviation_with_what_follows(token):
    # Prefix >= 20 chars so the short-fragment merge cannot be the reason.
    text = f"Tonight the band played a long version of {token} Blues for the crowd."
    assert _split_sentences(text) == [text]


def test_split_real_sentence_end_after_dotted_abbreviation_is_harmless():
    text = "They finally made it to Washington, D.C. The band came out swinging after that."
    assert _split_sentences(text) == [text]


def test_split_outro_keeps_us_blues_without_gluing_three_sentences():
    pieces = _split_sentences(OUTRO_1974_05_19)
    assert any("U.S. Blues, still a new song" in p for p in pieces)
    assert not any(p.endswith("U.S.") for p in pieces)
    # The pre-pass runs before the short-fragment merge: the "Saturday Night." sentence and
    # the "U.S. Blues" sentence stay separate pieces (no ~500-character piece).
    assert max(len(p) for p in pieces) < 320
```

- [ ] **Step 2: Run the tests and confirm they fail.** Run `./.venv/bin/python -m pytest packages/emcee/tests/test_audio.py -q -k "dotted or outro"`. Expected: all three FAIL. Without the rule, Washington's "D.C." splits and the outro has a piece ending "U.S.".
- [ ] **Step 3: Implement.** In `_split_sentences`, add a pre-pass over `raw_parts` before the existing merge loop. The pre-pass joins a part to the next one (with one space) when the part's last whitespace-delimited word, stripped of leading non-alphanumerics (for example `(` and quotes), fully matches `(?:[A-Za-z]\.){2,}`. Repeat while it applies, so `U.S. B.B.` chains. Leave the existing loop (abbreviations, initials, decimals, short fragments) unchanged.
- [ ] **Step 4: Run the tests and confirm they pass.** Run `./.venv/bin/python -m pytest packages/emcee -q`. Expected: all pass. That includes `tests/test_scriptwrite.py`, because `rephrase_problems` uses the splitter.
- [ ] **Step 5: Commit** with message `fix(emcee): sentence splitter keeps dotted abbreviations (U.S., D.C.) whole`.
- [ ] **Step 6: Mutation check.** Mutation A: move the pre-pass after the merge loop. Predict `test_split_outro_keeps_us_blues_without_gluing_three_sentences`. Mutation B: change `{2,}` to `{3,}`. Predict the parametrized test.

---

### Task 2: The paragraph packer `plan_chunks`

**Files:**
- Modify: `packages/emcee/src/emcee/audio.py` (new functions next to `_split_sentences`)
- Test: `packages/emcee/tests/test_audio.py` (new `plan_chunks` block)

**Interfaces:**
- Consumes: `_split_sentences` (Task 1), `_MIN_FRAGMENT_LEN`.
- Produces: `plan_chunks(text: str, ceiling: int) -> list[str]`, a pure function. Each chunk contains no newline; they are returned in order. Whitespace-only text returns `[""]`, mirroring `_split_sentences`.

Algorithm (spec section 2, steps 1-5). The order matters and the tests pin it:
1. Paragraphs: `re.split(r"\n\s*\n", text)`. Collapse each part with `" ".join(part.split())` and drop empty parts.
2. A paragraph of at most `ceiling` characters is one unit. A longer one goes through `_split_sentences(paragraph)`, packed greedily into units of at most `ceiling` (a lone sentence over the ceiling is its own unit).
3. Greedy-combine all units in order, joining with one space, while the combined text is at most `ceiling`.
4. Any chunk shorter than `_MIN_FRAGMENT_LEN` joins the chunk before it, or the one after if it is first, even past the ceiling. A single chunk with no neighbour stays as it is.

- [ ] **Step 1: Write the failing tests**

```python
P1 = "Tonight we go back to Portland in the spring of 1974. The band was on fire."      # 75
P2 = "Listen for the long jam after Truckin'. It stretches out and turns quiet."        # 73
LONG = " ".join([f"Sentence number {i} keeps the long paragraph rolling along." for i in range(8)])


def test_plan_chunks_paragraphs_that_fit_share_a_chunk():
    assert plan_chunks(f"{P1}\n\n{P2}", 250) == [f"{P1} {P2}"]


def test_plan_chunks_paragraph_combined_only_when_it_fits():
    assert plan_chunks(f"{P1}\n\n{P2}", 100) == [P1, P2]


def test_plan_chunks_single_newline_is_a_space_two_or_more_are_a_break():
    assert plan_chunks("Line one of a wrapped file\ncontinues here on line two.", 250) == [
        "Line one of a wrapped file continues here on line two."]
    assert plan_chunks(f"{P1}\n \n\n{P2}", 100) == [P1, P2]


def test_plan_chunks_a_wrap_inside_a_long_sentence_is_not_a_boundary():
    # Ceiling 30 < the 54-char sentence: a single newline must not become a paragraph break.
    assert plan_chunks("Line one of a wrapped file\ncontinues here on line two.", 30) == [
        "Line one of a wrapped file continues here on line two."]
    wrapped = ("The jam after Truckin' stretches out for a long while and\nturns quiet "
               "before it settles into Not Fade Away. Then the band\nheads down the road "
               "and into One More Saturday Night to close.")
    assert all(c.endswith(".") for c in plan_chunks(wrapped, 60))


def test_plan_chunks_crlf_breaks_and_no_carriage_returns():      # Review Focus 1
    chunks = plan_chunks(f"{P1}\r\n\r\n{P2}", 100)
    assert chunks == [P1, P2]


def test_plan_chunks_blank_trailing_paragraphs_make_no_empty_chunk():  # Review Focus 2
    assert plan_chunks(f"{P1}\n\n   \n\n", 250) == [P1]


def test_plan_chunks_long_paragraph_packs_sentences_never_splits_one():
    chunks = plan_chunks(LONG, 130)
    assert all(len(c) <= 130 for c in chunks)
    assert " ".join(chunks) == LONG
    assert all(c.endswith(".") for c in chunks)


def test_plan_chunks_sentence_longer_than_ceiling_is_sent_whole():
    big = "This one sentence " + "goes on and on " * 20 + "until it finally ends."
    assert plan_chunks(big, 100) == [big]


def test_plan_chunks_no_paragraphs_packs_plain_sentences():
    assert plan_chunks(LONG, 250) == plan_chunks(LONG.replace(". ", ".\n"), 250)


def test_plan_chunks_tiny_chunk_joins_its_neighbour_past_the_ceiling():
    text = f"{P1}\n\nHere's set two.\n\n{P2}"           # 15-char middle paragraph
    chunks = plan_chunks(text, 80)
    assert chunks == [f"{P1} Here's set two.", P2]


def test_plan_chunks_tiny_first_chunk_joins_the_next():
    assert plan_chunks(f"Good evening.\n\n{P1}", 80) == [f"Good evening. {P1}"]


def test_plan_chunks_whole_short_segment_is_one_chunk():          # Review Focus 3
    assert plan_chunks("Here's set two.", 250) == ["Here's set two."]


def test_plan_chunks_never_contains_a_newline():
    text = f"{P1}\n{P2}\n\n{LONG}\n"
    assert all("\n" not in c and "\r" not in c for c in plan_chunks(text, 120))


def test_plan_chunks_outro_respects_ceiling_except_single_pieces():
    pieces = set(_split_sentences(OUTRO_1974_05_19))
    for c in plan_chunks(OUTRO_1974_05_19, 250):
        assert len(c) <= 250 or c in pieces


def test_plan_chunks_whitespace_only():
    assert plan_chunks("  \n\n ", 250) == [""]
```

Check each expected value against the stated algorithm. If a literal here disagrees with the algorithm (a miscounted length, for example), fix the literal, not the algorithm, and note it in the handback.

- [ ] **Step 2: Run the tests and confirm they fail.** Run `./.venv/bin/python -m pytest packages/emcee/tests/test_audio.py -q -k plan_chunks`. Expected: FAIL with `ImportError`/`NameError` on `plan_chunks`.
- [ ] **Step 3: Implement** `plan_chunks(text: str, ceiling: int) -> list[str]` in `audio.py` per the algorithm above. A private `_greedy(items: list[str], ceiling: int) -> list[str]` helper is fine. Nothing calls `plan_chunks` yet.
- [ ] **Step 4: Run the tests and confirm they pass.** Run `./.venv/bin/python -m pytest packages/emcee -q`. Expected: all pass.
- [ ] **Step 5: Commit** with message `feat(emcee): paragraph-aware chunk planner (plan_chunks)`.
- [ ] **Step 6: Mutation check.** Mutation A: remove step 4. Predict `test_plan_chunks_tiny_chunk_joins_its_neighbour_past_the_ceiling`. Mutation B: split paragraphs on `\n+`. Predict `test_plan_chunks_a_wrap_inside_a_long_sentence_is_not_a_boundary`; the other newline tests survive this mutant because short pieces recombine. Mutation C: skip step 3 (return the units). Predict `test_plan_chunks_paragraphs_that_fit_share_a_chunk`.

---

### Task 3: Room-tone fill (`tts/room_tone.py`)

**Files:**
- Create: `packages/emcee/src/emcee/tts/room_tone.py`
- Test: `packages/emcee/tests/test_room_tone.py`

**Interfaces:**
- Produces:
  - `fill_room_tone(pcm: bytes, framerate: int, channels: int, *, seed_text: str) -> bytes`. Takes int16 little-endian PCM and returns PCM of the same length. It returns the input unchanged when `channels != 1`, when no frame is eligible for the pool, or when there is no qualifying run.
  - `ROOM_TONE_VERSION = "v1"`. Its comment must say: in the DJ-clip cache key; bump when any constant or the algorithm below changes the output.
  - The module constants: `FRAME_S = 0.02`, `POOL_PERCENTILE = 8.0`, `CROSSFADE_S = 0.005`, `MIN_RUN_S = 0.02`, `POOL_ZERO_RUN_S = 0.001`, `LIVE_RMS = 1.0`.

Follow the style of `tts/loudness.py`: pure numpy and a module docstring that cites the spec. The reference is `room_tone()` in `~/.llama-harness/tts-experiments/noise_test.py`. Copy its structure: frames, pool, a fill built by chaining pool frames with crossfades, and the tone *added* over the run plus `xf` on each side with an envelope. Apply exactly these deltas:

```text
x      = int16 samples; n = round(FRAME_S*rate); xf = round(CROSSFADE_S*rate)
runs   = maximal runs of x == 0 with length >= round(MIN_RUN_S*rate)        (on the input)
frames = whole n-sample frames only (a partial tail frame is never in the pool)
pool   = frames with rms > LIVE_RMS AND no zero run >= round(POOL_ZERO_RUN_S*rate) inside;
         then keep those with rms <= percentile(their rms, POOL_PERCENTILE). Empty -> return pcm.
rng    = np.random.default_rng(int.from_bytes(sha256(seed_text.encode()).digest()[:8], "big"))
for each run (s, e):
    start_edge = s < xf ; end_edge = e > len(x) - xf
    lo = 0 if start_edge else s - xf ; hi = len(x) if end_edge else e + xf
    fill = pool frames chained with xf crossfades (as the harness), cut to hi - lo
    env = ones(hi - lo); env[:xf] = ramp up; env[-xf:] = ramp down
        (at a start edge the ramp up starts at sample 0 = fade in from zero at the clip start;
         at an end edge the ramp down ends at the last sample = fade out to zero at the clip end)
    out[lo:hi] += fill * env
return clip(out, int16).tobytes()
```

- [ ] **Step 1: Write the failing tests.** Build the PCM in a test helper with numpy, at 24 kHz. Alternate 0.5 s "speech" bursts (a sine at -20 dBFS plus the floor) with 0.15 s floor-only pauses, where the floor is Gaussian noise near -60 dBFS rounded to int16 and never exactly 0 (replace any 0 sample with 1). Repeat for about 4 s, and put one 0.3 s exact-zero gap between two bursts. The floor-only pauses must be well over 8% of the 20 ms frames, because the pool is the quietest 8% of live frames: with speech under every frame, the "quiet" frames would be speech. Tests:
  - `test_fill_replaces_zero_runs_and_keeps_length`: the output length equals the input length, and the output has no run of ≥ 20 ms exact zeros.
  - `test_fill_is_deterministic_and_seeded_by_text`: the same input and seed text give identical bytes; a different `seed_text` gives different bytes.
  - `test_seed_is_the_sha256_of_the_text`: monkeypatch `emcee.tts.room_tone.np.random.default_rng` with a wrapper that records its argument and calls the real one. The recorded seed equals `int.from_bytes(hashlib.sha256(b"some text").digest()[:8], "big")`.
  - `test_fill_level_comes_from_the_quietest_frames`: the RMS over the filled gap is within 6 dB of the floor's RMS and at least 30 dB below the speech.
  - `test_fill_overlaps_neighbouring_audio_by_the_crossfade`: the output differs from the input within 5 ms before the gap start (the tone is added there), and is identical more than 5 ms before it.
  - `test_pool_excludes_frames_with_a_1ms_zero_run`: give the quietest frames 30-sample zero runs (above 1 ms) and slightly louder frames none, then check that the fill contains no zero run ≥ 24 samples. As a control, frames with only 3-sample zero runs at crossings are still used: the fill's RMS matches those frames.
  - `test_edge_runs_fade_from_and_to_zero`: in a clip that begins with 10 samples of ±2 dither, then 0.2 s of zeros, then speech, and ends with 0.2 s of zeros, `out[0]` and `out[-1]` are within ±3 of 0, `mean(|out[0:60]|) < mean(|out[60:120]|)` (fading in from zero), `mean(|out[-60:]|) < mean(|out[-120:-60]|)` (fading out), and there is no run ≥ 20 ms of zeros.
  - `test_noop_without_live_frames`: all-zero PCM (as from the fake provider) is returned byte-identical.
  - `test_noop_when_pool_empty`: when every live frame contains a ≥ 1 ms zero run, the input is returned byte-identical and nothing raises.
  - `test_noop_without_qualifying_run`: only 10 ms zero gaps give byte-identical output.
  - `test_skips_non_mono`: `channels=2` gives byte-identical output.
  - `test_odd_length_pcm` (Review Focus 4): a clip of 24 001 samples (not a multiple of 480) with an edge zero run at the start (0.1 s), live floor-plus-speech in the middle, and an edge zero run at the end (0.1 s). The output length is unchanged, nothing raises, and both ends are within ±3 of 0.
- [ ] **Step 2: Run the tests and confirm they fail.** Run `./.venv/bin/python -m pytest packages/emcee/tests/test_room_tone.py -q`. Expected: FAIL on import.
- [ ] **Step 3: Implement** `fill_room_tone` and the constants per the pseudocode.
- [ ] **Step 4: Run the tests and confirm they pass.** Run `./.venv/bin/python -m pytest packages/emcee -q`. Expected: all pass.
- [ ] **Step 5: Commit** with message `feat(emcee): room-tone fill for exact-silence runs`.
- [ ] **Step 6: Mutation check.** Mutation A: drop the pool's zero-run exclusion. Predict `test_pool_excludes_frames_with_a_1ms_zero_run`. Mutation B: seed with `abs(hash(seed_text))`. Predict `test_seed_is_the_sha256_of_the_text`. Mutation C: set `lo = s` (no overlap). Predict `test_fill_overlaps_neighbouring_audio_by_the_crossfade`.

---

### Task 4: One `chunking` argument and the config keys (behaviour-preserving)

**Files:**
- Modify: `packages/emcee/src/emcee/config.py` (the `TTSConfig` fields, a new `Chunking`, `DEFAULT_CONFIG_TOML`'s `[tts]` block)
- Modify: `packages/emcee/src/emcee/audio.py` (`_chunked_pcm`, `_synthesize_chunked`, `_segment_pcm`, `_render`, `render_speech_mp3`, `_synthesize_dj_audio`)
- Modify: `packages/emcee/src/emcee/process.py:305-308`, `packages/emcee/src/emcee/cli.py` (`say`)
- Modify tests: every caller of the changed functions. Currently `tests/test_audio.py`, `test_quality.py`, `test_recording.py`, `test_run_cmd.py`, `test_say_cmd.py` and `test_verify.py` (find them with `grep -rn "render_speech_mp3\|_synthesize_dj_audio\|_chunked_pcm\|_segment_pcm\|_synthesize_chunked" packages/emcee`), plus `tests/test_config.py` and `tests/helpers.py`.

**Interfaces:**
- Produces:
  - In `emcee/config.py`:
    ```python
    @dataclass(frozen=True)
    class Chunking:
        """How a chunked render packs and finishes a segment (spec 2026-10-26)."""
        ceiling: int
        room_tone: bool
    ```
  - `TTSConfig.chunk_chars: StrictInt = Field(default=250, ge=50, le=1000)` and `TTSConfig.room_tone: bool = True`.
  - `TTSConfig.chunking(self, *, enabled: bool) -> Chunking | None`. It returns `Chunking(self.chunk_chars, self.room_tone)` when `enabled`, else `None`.
  - Every function listed under Files takes `chunking` as a **required keyword-only** argument with **no default**, in place of `chunk: bool`. `None` means unchunked. `_chunked_pcm` and `_synthesize_chunked` take `chunking: Chunking` (never None).
  - `Chunking` is defined **above** `TTSConfig` in `config.py`: `TTSConfig.chunking`'s return annotation is evaluated eagerly (`test_annotations_resolve_eagerly.py`, the 3.11 guard).
  - `tests/helpers.py` gains `CHUNKED = Chunking(ceiling=250, room_tone=True)` and `SENTENCES = Chunking(ceiling=1, room_tone=False)`. The dataclass is unvalidated, and a ceiling of 1 reproduces today's one-piece-per-chunk exactly. Task 5 uses `SENTENCES`.
- Callers: `process_package` passes `chunking=config.tts.chunking(enabled=config.tts.chunk)`; `emcee say` passes `chunking=config.tts.chunking(enabled=chunk)`, so its `--chunk/--no-chunk` flag is unchanged.
- **Behaviour is unchanged in this task.** `_chunked_pcm` still synthesizes one `_split_sentences` piece per call and ignores `ceiling`/`room_tone`. The cache key is unchanged in every branch, still written as `chunk={chunking is not None}`, so `True`/`False` render as today. Task 5 turns the new behaviour on.

- [ ] **Step 1: Write the failing tests** (in `tests/test_config.py`):

```python
def test_chunk_chars_defaults_and_bounds():
    assert TTSConfig().chunk_chars == 250 and TTSConfig().room_tone is True
    assert TTSConfig(chunk_chars=50).chunk_chars == 50
    assert TTSConfig(chunk_chars=1000).chunk_chars == 1000


@pytest.mark.parametrize("bad", [49, 1001, "250", 250.0, 250.5, True])
def test_chunk_chars_rejects_non_strict_ints_and_out_of_range(bad):
    with pytest.raises(ValidationError):
        TTSConfig(chunk_chars=bad)


def test_chunk_chars_bad_value_in_config_toml_is_a_load_error(tmp_path):
    # write a config.toml with [tts] chunk_chars = "250" and load it through the same
    # loader the CLI uses; expect ConfigError (follow the existing load-error tests' pattern)
    ...


def test_tts_chunking_helper():
    t = TTSConfig(chunk_chars=300, room_tone=False)
    assert t.chunking(enabled=True) == Chunking(ceiling=300, room_tone=False)
    assert t.chunking(enabled=False) is None
```

Also add `"chunk_chars"` and `"room_tone"` to the marker tuple in `test_default_config_template_mentions_every_section`. In `tests/test_audio.py`, add `test_chunking_has_no_default` with `inspect.signature`: for each of `render_speech_mp3`, `_synthesize_dj_audio`, `_render` and `_segment_pcm`, the `chunking` parameter is `KEYWORD_ONLY` and its default is `inspect.Parameter.empty`, and no `chunk` parameter remains.

- [ ] **Step 2: Run the tests and confirm they fail.** Run `./.venv/bin/python -m pytest packages/emcee/tests/test_config.py packages/emcee/tests/test_audio.py -q -k "chunk"`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Add the config fields and `Chunking`. Rewrite the `[tts] chunk` field comment so it no longer says "sentence-by-sentence". Add commented template lines after `# chunk = false`, keeping the template's voice:
    - `# chunk_chars = 250`: the packing ceiling in characters, 50-1000, one value for every backend; chunks follow the script's paragraphs and never end inside a sentence.
    - `# room_tone = true`: fill exact-silence gaps in chunked clips with the clip's own quietest sound; set false to turn it off.
  - Replace `chunk` with `chunking` through the call chain. Update every test call site mechanically: `chunk=True` → `chunking=CHUNKED`, `chunk=False` → `chunking=None`, and an omitted `chunk` → `chunking=None`, except that direct calls to `_chunked_pcm`/`_synthesize_chunked` (which never took `chunk`) get `chunking=CHUNKED`. Test fakes and monkeypatched stand-ins that accept a `chunk=` keyword (for example `fake_synth(..., chunk=False, ...)` in `test_run_cmd.py` and `test_recording.py`) rename it to `chunking=None`. Leave the test assertions alone.
- [ ] **Step 4: Run the tests and confirm they pass.** Run `./.venv/bin/python -m pytest packages/emcee -q`. Expected: all pass, at the baseline count plus the new tests. No existing assertion changed.
- [ ] **Step 5: Commit** with message `refactor(emcee): one required chunking argument; [tts] chunk_chars and room_tone`.
- [ ] **Step 6: Mutation check.** Mutation A: give `render_speech_mp3`'s `chunking` a default of `None`. Predict `test_chunking_has_no_default`. Mutation B: make `chunk_chars` a plain `int`. Predict `test_chunk_chars_rejects_non_strict_ints_and_out_of_range["250"]`.

---

### Task 5: Packed chunks, room tone and the chunk-digest cache key

**Files:**
- Modify: `packages/emcee/src/emcee/audio.py` (`_chunked_pcm`, `render_speech_mp3`, `_synthesize_dj_audio`'s key; a new `_render_key`)
- Test: `packages/emcee/tests/test_audio.py`, `packages/emcee/tests/test_say_cmd.py`

**Interfaces:**
- Consumes: `plan_chunks` (Task 2), `fill_room_tone` and `ROOM_TONE_VERSION` (Task 3), `Chunking` (Task 4).
- Produces:
  - `_chunked_pcm(text, speech, *, chunking: Chunking) -> tuple[bytes, int, int]` synthesizes one call per `plan_chunks(text, chunking.ceiling)` chunk, passing neighbour **chunks** as `previous_text`/`next_text`. Each chunk is loudness-normalized, the chunks are joined with 180 ms of silence, and `fill_room_tone(pcm, framerate, channels, seed_text=text)` is applied last when `chunking.room_tone` is set.
  - `_render_key(spoken: str, speech, *, chunking: Chunking | None, bed_key: str, loud_key: str) -> str` returns the sha256 hex. The unchunked string is exactly today's: `f"{spoken}\n{speech.voice}\n{speech.model}\nchunk=False{bed_key}{loud_key}"`. The chunked string is today's chunked string plus `"\nchunks=" + digest`, where `digest = sha256(_CHUNK_SEP.join(plan_chunks(spoken, chunking.ceiling)).encode()).hexdigest()[:16]` and `_CHUNK_SEP = "\x1f"` is a module constant. Compute the digest outside any f-string: a backslash inside an f-string expression is a SyntaxError on Python 3.11, which emcee supports. Add `f"\ntone={ROOM_TONE_VERSION}"` when `room_tone` is set. `_synthesize_dj_audio` uses it.
  - `render_speech_mp3`: when `chunking is None`, `text = " ".join(text.split())` first, before `_render` and before `_locate_block`.

- [ ] **Step 1: Write the failing tests and update the affected ones.**
  - New tests:
    - `test_chunked_sends_packed_chunks_not_sentences`: a three-sentence `PASSAGE` with `CHUNKED` gives `speech.calls == [PASSAGE]`.
    - `test_chunked_paragraphs_become_chunks_with_no_newline`: text `f"{P1}\n\n{P2}"` with `Chunking(100, False)` gives `calls == [P1, P2]`, no call contains `"\n"`, and `speech.context == [(None, P2), (P1, None)]`.
    - `test_room_tone_applied_only_when_enabled`: monkeypatch `emcee.audio.fill_room_tone` with a recorder. It is called once with `seed_text` equal to the passed text when `room_tone=True`, and not called when `False`.
    - `test_cache_key_chunked_changes_with_planned_chunks`: same spoken text, ceilings 250 vs 100 that plan differently, give different keys; ceilings 250 vs 260 that plan identically give the same key.
    - `test_cache_key_tone_part`: `room_tone` False vs True give different keys, and the key string for False contains no `tone=` (assert via a monkeypatched `hashlib.sha256` capture, or by recomputing `_expected_key`).
    - `test_cache_key_changes_with_room_tone_version`: monkeypatch `emcee.audio.ROOM_TONE_VERSION` to `"v2"`; the key for the same text and `CHUNKED` differs from the `"v1"` key.
    - `test_cache_key_unchunked_still_the_pre_feature_formula`: keep the existing test, using `chunking=None`.
    - `test_unchunked_collapses_whitespace_before_send_and_locate`: an unchunked render of `f"{P1}\n\n{P2}"` sends exactly `f"{P1} {P2}"`. With `block="climax"` on a two-paragraph text, `_locate_block`'s probe calls contain no `"\n"`.
    - `test_say_hard_wrapped_file_is_one_paragraph` (in `test_say_cmd.py`, following its fake-provider pattern): a file with single-newline wraps produces calls with no `"\n"`, as many as `plan_chunks` of the collapsed text.
  - Update every existing test whose expectation assumed one call per sentence (`test_synthesize_chunked_threads_neighbor_text_as_context`, `test_render_speech_mp3_chunked_synthesizes_each_sentence`, `test_chunked_pcm_normalizes_each_sentence_to_target` and any others that fail). Either pass `SENTENCES` (from `tests/helpers.py`; one sentence per chunk, as today) or assert the packed result. `test_render_speech_mp3_chunked_synthesizes_each_sentence` and `test_say_cmd.py::test_say_chunks_by_sentence_by_default` use a 42-character two-sentence text that packs into one chunk at 250, so either assert `calls == [text]` (and rename the test) or pass `SENTENCES`. Keep the intent of each test. `test_render_chunked_block_needs_no_locating` is rewritten in Task 6. For now, mark it `@pytest.mark.skip(reason="rewritten in Task 6")` only if it fails.
  - Update `_expected_key` in `test_audio.py` to the new chunked formula.
- [ ] **Step 2: Run the tests and confirm the new ones fail.** Run `./.venv/bin/python -m pytest packages/emcee -q`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** per the Interfaces block. The fake provider returns all-zero WAV, so room tone is a no-op in process-level tests.
- [ ] **Step 4: Run the tests and confirm they pass.** Run `./.venv/bin/python -m pytest packages/emcee -q`. Expected: all pass, with at most the one Task-6 skip.
- [ ] **Step 5: Commit** with message `feat(emcee): voice chunks packed by paragraph at [tts] chunk_chars, with room tone`.
- [ ] **Step 6: Mutation check.** Mutation A: drop the `chunks=` part from the key. Predict `test_cache_key_chunked_changes_with_planned_chunks`. Mutation B: apply room tone regardless of the flag. Predict `test_room_tone_applied_only_when_enabled`. Mutation C: move the unchunked collapse after the `_locate_block` call. Predict `test_unchunked_collapses_whitespace_before_send_and_locate`. Mutation D: hard-code `tone=v1` in the key. Predict `test_cache_key_changes_with_room_tone_version`.

---

### Task 6: Content-filter narrowing inside the chunk loop (STRICT SURFACE)

**Files:**
- Modify: `packages/emcee/src/emcee/audio.py` (`_chunked_pcm`; a new `_narrow_chunk`)
- Test: `packages/emcee/tests/test_audio.py` (the block-test section around `PASSAGE`), `packages/emcee/tests/test_process.py` (the repair section around `CLEAN_S1`/`BLOCKED_S2`)

**Interfaces:**
- Consumes: `_chunked_pcm` (Task 5), `_split_sentences`, `SpeechBlocked`.
- Produces: `_narrow_chunk(chunk: str, speech, blocked: SpeechBlocked) -> list[bytes]`. When `_split_sentences(chunk)` has one piece, it re-raises `blocked` without making a call. Otherwise it synthesizes each piece alone with `fmt="wav"` and keeps the WAV bytes. When a piece is refused it raises that piece's `SpeechBlocked` (`raise located from blocked`, `whole_passage` False). When every piece passes it returns the WAV takes in order. `_chunked_pcm` catches `SpeechBlocked` around each chunk's call. On a return, it uses the takes as that chunk's audio: each is loudness-normalized, the takes are joined with the usual 180 ms, and the chunk is joined to its neighbours as usual. Neighbours are never re-synthesized. `render_speech_mp3`'s `if chunking is not None: raise` stays as it is. Whether the narrowing calls pass neighbour context is left to you; say which you chose in the handback.

- [ ] **Step 1: Write the failing tests.** In `test_audio.py`, with `C = Chunking(250, False)` and `PASSAGE` as in the file:
  - `test_chunked_block_narrows_to_the_refused_sentence` (this replaces `test_render_chunked_block_needs_no_locating`; remove that test and any Task-5 skip): `block="climax"` raises `SpeechBlocked` with `text == "The climax comes too early here."` and `whole_passage is False`, and `speech.calls == [PASSAGE, "First sentence is fine here.", "The climax comes too early here."]`.
  - `test_chunked_cross_sentence_block_falls_back_to_the_takes`: `block="here. The climax"` returns MP3 bytes, and `speech.calls == [PASSAGE, s1, s2, s3]`, with exactly 4 calls and nothing re-sent.
  - `test_chunked_fallback_audio_is_the_takes_joined`: with `_chunked_pcm` and the same block, the PCM length equals `3 * len(SILENT_WAV frames) + 2 * 180 ms` (compute it from `fake._silent_wav`'s 0.3 s at 24 kHz).
  - `test_chunked_fallback_chunk_keeps_its_neighbours_on_both_sides`: three paragraphs `f"{P1}\n\n{M}\n\n{P2}"` with `Chunking(100, False)`, where `M = "The first half of the middle thought is here. The climax lands in the second half."` (two pieces, together under 100). Use `block="here. The climax"`, which spans M's sentence boundary. Assert `speech.calls == [P1, M, M1, M2, P2]`, with M1 and M2 the two pieces of `_split_sentences(M)`: every chunk is synthesized once and the chunk after the fallback is not dropped. Also assert the `_chunked_pcm` length is `4 * 0.3 s + 3 * 180 ms` in samples at 24 kHz (takes P1, M1, M2 and P2; joins P1|M1, M1|M2 and M2|P2).
  - `test_chunked_one_piece_block_is_reraised_not_resent`: a single-sentence chunk blocked raises that block, with `speech.calls == [chunk]`.
  - `test_chunked_block_with_bed_narrows_and_falls_back` (Review Focus 5): the two tests above repeated through `render_speech_mp3(..., bed_pcm=..., bed_rate=24000)` with a 24 kHz bed (reuse `_bed_file`, a constant-level bed); assert the same `speech.calls` sequences as without a bed.
  - Keep `test_render_unchunked_block_locates_the_sentence`, `test_render_block_only_in_context_is_whole_passage` and `test_render_single_sentence_block_is_not_resent` passing unchanged (with `chunking=None`).

  In `test_process.py`:
  - Extend `test_chunked_repair_through_process_package` with `assert f'blocked: "{BLOCKED_S2}"' in out`, which shows the single refused sentence, not the chunk, reached the repair. Construct its config with `chunk=True` explicitly.
  - Add `test_chunked_reblocked_twice_raises_and_names_the_sentence`, the chunked twin of `test_reblocked_twice_raises_and_manifest_untouched`. Use the same two rephrase replies, but build the config with `TTSConfig(chunk=True)` instead of `_setup`'s unchunked one. Assert `"also blocked" in rephrase.calls[1][1]`, that the text quoted after it is the single reworded sentence `"The climax lands early tonight."` (not the whole segment), and that the manifest is untouched.
  - Add `test_chunked_cross_sentence_block_needs_no_rephrase`. Use `_arm(monkeypatch, [])`, `TTSConfig(chunk=True)` and `FakeSpeechProvider(block="two. The climax")`. `process_package` succeeds, the manifest's `dj_notes.set_intros["2"] == SEG2` unchanged, `"rephrase" not in requested`, and `pkg.dir / "dj-audio" / "set2-intro.mp3"` exists.
- [ ] **Step 2: Run the tests and confirm they fail.** Run `./.venv/bin/python -m pytest packages/emcee/tests/test_audio.py packages/emcee/tests/test_process.py -q -k "block or repair"`. Expected: the new tests FAIL. Before the change, a chunked block re-raises the whole chunk's text.
- [ ] **Step 3: Implement** `_narrow_chunk` and the catch in `_chunked_pcm` per the Interfaces block.
- [ ] **Step 4: Run the tests and confirm they pass.** Run `./.venv/bin/python -m pytest packages/emcee -q`. Expected: all pass, with no skips left from Task 5.
- [ ] **Step 5: Commit** with message `feat(emcee): narrow a blocked packed chunk to its sentence; fall back to the passing takes`.
- [ ] **Step 6: Mutation check.** Mutation A: re-raise `blocked` (the whole chunk) instead of narrowing. Predict `test_chunked_block_narrows_to_the_refused_sentence`, then the process-level `blocked:` assertion. Mutation B: on all-pass, re-synthesize each piece instead of using the takes. Predict `test_chunked_cross_sentence_block_falls_back_to_the_takes` (call count 7 ≠ 4). Mutation C: drop the one-piece guard. Predict `test_chunked_one_piece_block_is_reraised_not_resent`. Mutation D: on all-pass, raise `whole_passage=True`. Predict `test_audio.py::test_chunked_cross_sentence_block_falls_back_to_the_takes` and `test_process.py::test_chunked_cross_sentence_block_needs_no_rephrase`. Mutation E: after a fallback chunk, stop the loop. Predict `test_chunked_fallback_chunk_keeps_its_neighbours_on_both_sides`. Run every Task 6 mutation over `packages/emcee` (not one file).

---

### Task 7: The scriptwriter writes paragraphs; literal `\n` is unescaped

**Files:**
- Modify: `packages/emcee/src/emcee/prompts/scriptwrite.md`, `packages/emcee/src/emcee/prompts/rephrase.md`
- Modify: `packages/emcee/src/emcee/scriptwrite.py` (`write_script`, `rephrase_segment`, a new `_unescape_breaks`)
- Test: `packages/emcee/tests/test_scriptwrite.py`

**Interfaces:**
- Produces: `_unescape_breaks(text: str) -> str`, which replaces each literal backslash-`n` two-character sequence with `"\n"`. `write_script` applies it to every `set_intros` value and to `outro` (through `model_copy`) **before** `script_guard`. `rephrase_segment` applies it to `result.text` before `.strip()`.

- [ ] **Step 1: Write the failing tests:**
  - `test_scriptwrite_prompt_asks_for_paragraphs_as_escaped_breaks`: `load_prompt("scriptwrite")` contains `"paragraph"` and the two-character-pair sequence `\n\n` (in Python, `"\\n\\n"`), and says "never a raw line break".
  - `test_rephrase_prompt_asks_to_keep_paragraph_breaks`: `load_prompt("rephrase")` contains `"\\n\\n"` and `"blank line"`.
  - `test_write_script_round_trips_escaped_breaks`: a `FakeProvider` reply whose JSON string holds `"A first thought here.\n\nA second thought here."` as a JSON escape gives `notes.outro` containing a real `"\n\n"`.
  - `test_write_script_unescapes_double_escaped_breaks`: a reply whose JSON holds `\\n\\n` (which parses to literal backslash-n) gives `"\\n" not in notes.outro` and `"\n\n" in notes.outro`. The same holds for a `set_intros` value.
  - `test_rephrase_segment_unescapes_literal_breaks`: the same check for `rephrase_segment`'s return value.

  Follow the file's existing `FakeProvider`/package fixtures for `write_script`. The reply must also pass `script_guard`, so start from the file's existing good-notes JSON helper.
- [ ] **Step 2: Run the tests and confirm they fail.** Run `./.venv/bin/python -m pytest packages/emcee/tests/test_scriptwrite.py -q -k "paragraph or escape or unescape"`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - `scriptwrite.md`: directly after "...no separate show intro or set-break segments." and before the `{{encore_note}}` line, add guidance in the prompt's voice. It is not a new hard rule (spec section 1):
    > Write each lead-in and the outro as short paragraphs: one thought per paragraph, typically two to four sentences. Separate paragraphs with a blank line, written inside the JSON string as the escape \n\n — never a raw line break inside a JSON string.
  - `rephrase.md`: add a rule bullet:
    > - Keep the blank lines between paragraphs, written as \n\n inside the JSON string.
  - `_unescape_breaks` and the two call sites.
- [ ] **Step 4: Run the tests and confirm they pass.** Run `./.venv/bin/python -m pytest packages/emcee -q`. Expected: all pass. Check that no prompt-snapshot test broke; if one pins the prompt text, update the snapshot deliberately.
- [ ] **Step 5: Commit** with message `feat(emcee): scriptwriter writes paragraphs; unescape literal \\n in script text`.
- [ ] **Step 6: Mutation check.** Mutation A: drop `_unescape_breaks` in `write_script`. Predict `test_write_script_unescapes_double_escaped_breaks`. Mutation B: apply it after `script_guard`; the guard's verdict does not change with whitespace, so expect no failure, and say so in the handback (this is an observation, not a gap).

---

### Task 8: Docs, help text and wording

**Files:**
- Modify: `packages/emcee/src/emcee/cli.py` (the `--chunk` help text and the `say` docstring's CHUNKING paragraph), `packages/emcee/src/emcee/tts/quality.py` (the docstring's "the sentence when chunked"), `packages/emcee/src/emcee/audio.py` (the "Sentence-level chunked synthesis" header comment and the `_chunked_pcm`/`_synthesize_chunked`/`render_speech_mp3`/`_synthesize_dj_audio` docstrings), the repo-root `README.md` (which holds the emcee runbook), and `CLAUDE.md` (repo root, the emcee architecture bullet's chunking/TTS sentence).

- [ ] **Step 1:** Run `grep -rn -i "sentence-by-sentence\|sentence by sentence\|per sentence\|each sentence\|across sentences\|sentence request" packages/emcee/src README.md CLAUDE.md` (the emcee runbook is the repo-root `README.md`; there is no `packages/emcee/README.md`). List every hit that describes the chunked synthesis path. That includes loudness normalization, which is now per chunk (for example README.md "(default: per sentence, loudness-normalized)", the config template's "loudness-normalized per sentence", and `_chunked_pcm`'s comment). It also includes `[tts.mlx_audio] timeout_s`'s "seconds per sentence request" (now per chunk request) and CLAUDE.md's emcee sentence "a block that exists only across sentences fails with 're-run with `[tts] chunk = true`'", which now holds only for `chunk = false` (on the chunked path the block falls back to the passing takes). Leave alone the hits that correctly describe `_locate_block`, `rephrase_problems` or the narrowing.
- [ ] **Step 2:** Update each listed hit to describe the new behaviour in one or two plain sentences: chunks follow the script's paragraphs up to `[tts] chunk_chars` (default 250) and never end inside a sentence; exact-silence gaps in chunked clips are filled with the clip's own room tone (`[tts] room_tone`, default on); a blocked multi-sentence chunk is narrowed to its sentence and falls back to its passing takes. Add the two keys to the README's config reference if it has one.
- [ ] **Step 3:** Run `./.venv/bin/python -m pytest packages/emcee -q`, then `./.venv/bin/python -m pytest -q` (the full repo suite). Expected: all pass.
- [ ] **Step 4: Commit** with message `docs(emcee): paragraph chunking, room tone, chunk_chars`.

---

## After Task 8 (orchestrator, not an implementer)

- Final whole-branch review on Opus (review mode: **Opus**), against the spec.
- Hand back to the operator for the **acceptance listening check**, which is outside the build and is the operator's call because Voxtral is metered. It is spec Acceptance's last bullet: one Kurt and one Phil segment voiced end to end with a real scriptwriter run, with the bed, compared with today's rendering. Also check that the notes have paragraph breaks, that there are no invalid-JSON retries, Kurt's `quality check failed` lines, and the mlx memory peak. Optionally apply the fill offline to a Jimmy render. Release only after it.
