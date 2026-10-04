# TTS Content-Filter Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When Voxtral's content filter blocks a DJ-script sentence, emcee rewords just that sentence, re-checks it, re-voices only that segment and finishes the package; transient Voxtral failures get one retry.

**Architecture:** A new `SpeechBlocked` error (subclass of `SpeechError`) is raised by the Voxtral backend for a guardrail 403. The audio layer narrows an unchunked block to one sentence, tags it with its segment, and persists the clip cache after every segment. `process_package` catches it, asks a new `rephrase` LLM task to reword the segment, gates the result through a deterministic containment check plus the existing `script_guard`, rewrites `dj-notes.md`, and re-synthesizes (rendered segments come from the cache).

**Tech Stack:** Python 3, httpx (`MockTransport` in tests), pydantic v2, herder (`run_json_task`, `provider_for`, `FakeProvider`), pytest.

**Spec:** `docs/superpowers/specs/2026-10-03-tts-content-filter-recovery-design.md`

## Global Constraints

- Scope is `packages/emcee` only; llama and herder are untouched.
- emcee never imports llama (`packages/emcee/tests/test_no_llama_imports.py` must stay green).
- The manifest rewrite (`rewrite_manifest`) stays the package's **last** write, done only on full success.
- Every revised script passes `script_guard` **and** `rephrase_problems` before any of it is voiced; `notes` only ever holds an accepted script.
- On success, the synthesized text, `dj-notes.md` and the manifest `dj_notes` block agree.
- No identical retry of a blocked request; transient retry is exactly **once**, only for transport errors/timeouts, 429 and 5xx.
- `MAX_REPHRASES = 2` per segment per `process_package` call.
- `DEFAULT_TIERS["rephrase"] = "medium"`.
- No new CLI flag or config knob beyond the `rephrase` task key.
- Work in a worktree at `/Users/shawn/projects/llama/.claude/worktrees/content-filter` on branch `content-filter`, with its own venv: `python3 -m venv .venv && ./.venv/bin/pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee`. Run tests with `./.venv/bin/pytest` **from the worktree root** and confirm `./.venv/bin/python -c "import emcee; print(emcee.__file__)"` resolves inside the worktree.
- Commit messages end with:
  ```
  Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01X5uiQcfXG7dM4oKpyCxmr4
  ```

## Review Focus

1. **Two different segments blocked in one run** (e.g. set 2 and the outro) — each gets its own 2-attempt budget and the package still succeeds. Pinned in Task 4 (`test_two_blocked_segments_each_get_their_own_budget`).
2. **The rephrase LLM itself fails** (invalid JSON three times → `TaskFailed`) mid-repair — the error propagates and the manifest is byte-for-byte unchanged. Pinned in Task 4 (`test_rephrase_llm_failure_leaves_manifest_untouched`).
3. **A guardrail body that names no violated category** — still a `SpeechBlocked`, message has no empty `()`. Pinned in Task 1 (`test_guardrail_without_violated_categories`).
4. **Common-word track titles** (`Deal`, `Loser`) — the containment check matches whole words only and does not reject "a great deal" when the original already said it, nor flag "ideal". Pinned in Task 3 (`test_rephrase_problems_title_match_is_whole_word`).
5. **A plain non-block `SpeechError` on the unchunked whole-passage call** (e.g. a 401) — no locating calls are made. Pinned in Task 2 (`test_render_non_block_error_is_not_located`).

---

### Task 1: `SpeechBlocked`, Voxtral guardrail classification, transient retry, fake blocking

**Files:**
- Modify: `packages/emcee/src/emcee/tts/provider.py`
- Modify: `packages/emcee/src/emcee/tts/voxtral.py`
- Modify: `packages/emcee/src/emcee/tts/fake.py`
- Test: `packages/emcee/tests/test_voxtral.py`, `packages/emcee/tests/test_tts.py`

**Interfaces:**
- Produces:
  - `emcee.tts.provider.SpeechBlocked(backend: str, *, text: str, categories: list[str], whole_passage: bool = False)` — subclass of `SpeechError`. Attributes: `.backend`, `.text`, `.categories: list[str]`, `.whole_passage: bool`, `.segment: str | None` (initially `None`, assignable). `str(exc)` is computed from the attributes at call time. `.details == [f'blocked: "{text}"']`.
  - `VoxtralProvider(..., retry_delay_s: float = 2.0, sleep: Callable[[float], None] = time.sleep)`.
  - `FakeSpeechProvider(fail: bool = False, block: str | None = None)` — when `block` is a substring of the text, records the call then raises `SpeechBlocked("fake", text=text, categories=["sexual"])`.

- [ ] **Step 1: Write the failing tests**

Append to `packages/emcee/tests/test_voxtral.py` (it already imports `base64`, `json`, `httpx`, `pytest`, `SpeechError`, `VoxtralProvider`, and defines `_ok_audio`/`make_preset`):

```python
from emcee.tts.provider import SpeechBlocked

GUARDRAIL_BODY = {
    "object": "error", "message": "Request blocked by guardrail policy",
    "type": "guardrail_violation", "param": None, "code": "1920",
    "raw_status_code": 403,
    "guardrails": [{"moderation_llm_v2": {"action": "block", "categories": {
        "sexual": {"violated": True},
        "hate_and_discrimination": {"violated": False},
        "selfharm": {"violated": False},
        "jailbreaking": {"violated": False},
    }}}],
}


def _sequence(*responses):
    """Handler serving `responses` in order (an Exception is raised), and the
    list of request bodies it saw."""
    seen = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
    return handler, seen


def _ok():
    return httpx.Response(200, json={"audio_data": base64.b64encode(b"MP3").decode()})


def _make(handler):
    return VoxtralProvider(voice="v", api_key="k", transport=httpx.MockTransport(handler),
                           sleep=lambda s: None)


def test_guardrail_403_raises_speech_blocked_with_text_and_categories():
    handler, seen = _sequence(httpx.Response(403, json=GUARDRAIL_BODY))
    text = "Be warned that a tape flip brings that climax around a little early."
    with pytest.raises(SpeechBlocked) as ei:
        _make(handler).synthesize(text, fmt="wav")
    e = ei.value
    assert isinstance(e, SpeechError)
    assert e.text == text
    assert e.categories == ["sexual"]
    assert e.segment is None and e.whole_passage is False
    assert str(e) == "voxtral content filter blocked a sentence (sexual)"
    assert e.details == [f'blocked: "{text}"']
    assert len(seen) == 1  # a block is never retried


def test_guardrail_message_reflects_segment_set_later():
    handler, _ = _sequence(httpx.Response(403, json=GUARDRAIL_BODY))
    with pytest.raises(SpeechBlocked) as ei:
        _make(handler).synthesize("x y z")
    ei.value.segment = "set2-intro"
    assert str(ei.value) == "voxtral content filter blocked a sentence in set2-intro (sexual)"


def test_guardrail_without_violated_categories():
    body = {**GUARDRAIL_BODY, "guardrails": [{"m": {"categories": {"sexual": {"violated": False}}}}]}
    handler, _ = _sequence(httpx.Response(403, json=body))
    with pytest.raises(SpeechBlocked) as ei:
        _make(handler).synthesize("x y z")
    assert ei.value.categories == []
    assert str(ei.value) == "voxtral content filter blocked a sentence"


def test_non_guardrail_403_is_plain_speech_error_not_retried():
    handler, seen = _sequence(httpx.Response(403, json={"type": "forbidden", "message": "no"}))
    with pytest.raises(SpeechError) as ei:
        _make(handler).synthesize("hello there")
    assert not isinstance(ei.value, SpeechBlocked)
    assert "voxtral returned 403" in str(ei.value)
    assert len(seen) == 1


def test_non_json_403_is_plain_speech_error():
    handler, _ = _sequence(httpx.Response(403, text="<html>nope</html>"))
    with pytest.raises(SpeechError) as ei:
        _make(handler).synthesize("hello there")
    assert not isinstance(ei.value, SpeechBlocked)


def test_5xx_then_ok_retries_once():
    handler, seen = _sequence(httpx.Response(503, text="busy"), _ok())
    assert _make(handler).synthesize("hello there") == b"MP3"
    assert len(seen) == 2


def test_5xx_twice_fails_after_two_requests():
    handler, seen = _sequence(httpx.Response(500, text="a"), httpx.Response(502, text="b"))
    with pytest.raises(SpeechError) as ei:
        _make(handler).synthesize("hello there")
    assert "voxtral returned 502" in str(ei.value)
    assert len(seen) == 2


def test_429_then_ok_retries_once():
    handler, seen = _sequence(httpx.Response(429, text="slow down"), _ok())
    assert _make(handler).synthesize("hello there") == b"MP3"
    assert len(seen) == 2


def test_transport_error_then_ok_retries_once():
    handler, seen = _sequence(httpx.ConnectError("reset"), _ok())
    assert _make(handler).synthesize("hello there") == b"MP3"
    assert len(seen) == 2


def test_transport_error_twice_fails():
    handler, _ = _sequence(httpx.ReadTimeout("slow"), httpx.ReadTimeout("slow"))
    with pytest.raises(SpeechError) as ei:
        _make(handler).synthesize("hello there")
    assert "voxtral request failed" in str(ei.value)


def test_400_is_not_retried():
    handler, seen = _sequence(httpx.Response(400, text="bad"))
    with pytest.raises(SpeechError):
        _make(handler).synthesize("hello there")
    assert len(seen) == 1


def test_retry_sleeps_the_configured_delay():
    slept = []
    handler, _ = _sequence(httpx.Response(500, text="x"), _ok())
    p = VoxtralProvider(voice="v", api_key="k", transport=httpx.MockTransport(handler),
                        retry_delay_s=0.5, sleep=slept.append)
    p.synthesize("hello there")
    assert slept == [0.5]
```

Append to `packages/emcee/tests/test_tts.py`:

```python
from emcee.tts.provider import SpeechBlocked


def test_fake_blocks_text_containing_the_armed_phrase():
    fake = FakeSpeechProvider(block="climax")
    assert fake.synthesize("A clean sentence here.") == SILENT_MP3
    with pytest.raises(SpeechBlocked) as ei:
        fake.synthesize("The climax comes early.", fmt="wav")
    assert ei.value.text == "The climax comes early."
    assert ei.value.categories == ["sexual"]
    assert fake.calls == ["A clean sentence here.", "The climax comes early."]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/pytest packages/emcee/tests/test_voxtral.py packages/emcee/tests/test_tts.py -q`
Expected: FAIL — `ImportError: cannot import name 'SpeechBlocked'`.

- [ ] **Step 3: Implement**

In `packages/emcee/src/emcee/tts/provider.py`, after `SpeechError`:

```python
class SpeechBlocked(SpeechError):
    """The speech backend's content filter refused this text.

    `text` is exactly what was sent and refused; `categories` the violated
    category names (empty when the response doesn't say). `segment` (the DJ
    clip stem, e.g. "set2-intro") is filled in by the audio layer after the
    fact, so the message is computed in `__str__` rather than frozen here.
    `whole_passage` marks a passage whose every sentence passes on its own:
    the trigger only exists in context, and chunked synthesis avoids it.
    The full blocked text is always the first `details` line, which both CLI
    error boundaries print.
    """

    def __init__(self, backend: str, *, text: str, categories: list[str],
                 whole_passage: bool = False):
        super().__init__(f"{backend} content filter blocked", details=[f'blocked: "{text}"'])
        self.backend = backend
        self.text = text
        self.categories = list(categories)
        self.whole_passage = whole_passage
        self.segment: str | None = None

    def __str__(self) -> str:
        what = "a passage" if self.whole_passage else "a sentence"
        where = f" in {self.segment}" if self.segment else ""
        cats = f" ({', '.join(self.categories)})" if self.categories else ""
        msg = f"{self.backend} content filter blocked {what}{where}{cats}"
        if self.whole_passage:
            msg += ("; every sentence passes the content filter on its own, so "
                    "re-run with chunking on ([tts] chunk = true; for emcee say, "
                    "without --no-chunk)")
        return msg
```

In `packages/emcee/src/emcee/tts/voxtral.py`: add `import time` and `from collections.abc import Callable`; change the import to `from emcee.tts.provider import SpeechBlocked, SpeechError`; add the module constant and helper below `MAX_INPUT_CHARS`:

```python
# One retry for failures that are plausibly transient. A guardrail block is a
# 403 and is deterministic (measured 7/7 on the same sentence), so it is never
# retried; nor is any other 4xx but 429.
RETRY_DELAY_S = 2.0


def _is_transient(status: int) -> bool:
    return status == 429 or status >= 500


def _guardrail_block(resp: httpx.Response, text: str) -> SpeechBlocked | None:
    """A SpeechBlocked for a guardrail-violation body, else None (the caller
    raises its ordinary SpeechError). Observed shape (2026-10-03):
    {"type": "guardrail_violation", "guardrails": [{"<moderator>":
    {"categories": {"sexual": {"violated": true}, ...}}}]}."""
    try:
        body = resp.json()
    except ValueError:
        return None
    if not isinstance(body, dict) or body.get("type") != "guardrail_violation":
        return None
    categories: list[str] = []
    for entry in body.get("guardrails") or []:
        if not isinstance(entry, dict):
            continue
        for moderator in entry.values():
            cats = moderator.get("categories") if isinstance(moderator, dict) else None
            for name, verdict in (cats or {}).items():
                if isinstance(verdict, dict) and verdict.get("violated") and name not in categories:
                    categories.append(name)
    return SpeechBlocked("voxtral", text=text, categories=categories)
```

Extend `__init__`'s signature with `retry_delay_s: float = RETRY_DELAY_S, sleep: Callable[[float], None] = time.sleep,` (after `transport`) and store `self._retry_delay_s = retry_delay_s` and `self._sleep = sleep`. Replace the body of `synthesize` from the `try: resp = self._client.post(` line through the `if resp.status_code != 200:` raise with:

```python
        for attempt in (1, 2):
            try:
                resp = self._client.post(
                    API_URL, json=self._body(text, fmt),
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            except httpx.TransportError as e:  # includes timeouts
                if attempt == 1:
                    self._sleep(self._retry_delay_s)
                    continue
                raise SpeechError(f"voxtral request failed: {e}") from e
            except httpx.HTTPError as e:
                raise SpeechError(f"voxtral request failed: {e}") from e
            if attempt == 1 and _is_transient(resp.status_code):
                self._sleep(self._retry_delay_s)
                continue
            break
        if resp.status_code != 200:
            blocked = _guardrail_block(resp, text)
            if blocked is not None:
                raise blocked
            raise SpeechError(f"voxtral returned {resp.status_code}: {resp.text[:500]}")
```

(The `audio_data` decoding after it is unchanged.)

In `packages/emcee/src/emcee/tts/fake.py`: import `SpeechBlocked` alongside `SpeechError`; add `block: str | None = None` to `__init__` (store `self.block = block`, and extend the docstring: "Arm with block=<phrase> to have any text containing that phrase refused like a content-filter block."); in `synthesize`, after the existing `if self.fail:` raise, add:

```python
        if self.block is not None and self.block in text:
            raise SpeechBlocked("fake", text=text, categories=["sexual"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/pytest packages/emcee -q`
Expected: all pass (the existing voxtral/tts tests included).

- [ ] **Step 5: Commit**

```bash
git add packages/emcee/src/emcee/tts packages/emcee/tests/test_voxtral.py packages/emcee/tests/test_tts.py
git commit -m "feat(emcee): classify Voxtral guardrail blocks as SpeechBlocked; retry transient failures once"
```

---

### Task 2: Locate the blocked sentence, tag its segment, persist the cache per segment

**Files:**
- Modify: `packages/emcee/src/emcee/audio.py` (`render_speech_mp3`, `_synthesize_dj_audio`, new `_locate_block`)
- Test: `packages/emcee/tests/test_audio.py`, `packages/emcee/tests/test_say_cmd.py`

**Interfaces:**
- Consumes: `SpeechBlocked` and `FakeSpeechProvider(block=...)` from Task 1.
- Produces:
  - `render_speech_mp3(...)` (signature unchanged) raises a `SpeechBlocked` whose `.text` is the single offending sentence (unchunked path), or one with `whole_passage=True` and `.text` = the passage.
  - `_synthesize_dj_audio(pkg, notes, speech, force, chunk=False, lexicon=None, bed=None, rendered: set[str] | None = None) -> DJAudioBlock` — raises `SpeechBlocked` with `.segment` set to the clip stem (`"set2-intro"`, `"99-outro"`); adds each filename it renders to `rendered`; a filename already in `rendered` is exempt from `force`; writes `dj-audio/segments.json` after every rendered segment.

- [ ] **Step 1: Write the failing tests**

Append to `packages/emcee/tests/test_audio.py` (it already imports `pytest`, `Path`, `SILENT_MP3`, `FakeSpeechProvider`, `SpeechError`, `ScriptNotes`, `build_package`, and defines `_pkg`, `make_notes`):

```python
import json as _json

from emcee.audio import _synthesize_dj_audio, render_speech_mp3
from emcee.tts.provider import SpeechBlocked

PASSAGE = ("First sentence is fine here. The climax comes too early here. "
           "Last sentence is fine too.")


def test_render_unchunked_block_locates_the_sentence():
    speech = FakeSpeechProvider(block="climax")
    with pytest.raises(SpeechBlocked) as ei:
        render_speech_mp3(PASSAGE, speech)
    assert ei.value.text == "The climax comes too early here."
    assert ei.value.whole_passage is False
    assert speech.calls == [PASSAGE, "First sentence is fine here.",
                            "The climax comes too early here."]


def test_render_block_only_in_context_is_whole_passage():
    # The armed phrase spans a sentence boundary: only the full passage has it.
    speech = FakeSpeechProvider(block="here. The climax")
    with pytest.raises(SpeechBlocked) as ei:
        render_speech_mp3(PASSAGE, speech)
    assert ei.value.whole_passage is True
    assert ei.value.text == PASSAGE
    assert "[tts] chunk = true" in str(ei.value)
    assert len(speech.calls) == 4  # whole passage + three sentences


def test_render_chunked_block_needs_no_locating():
    speech = FakeSpeechProvider(block="climax")
    with pytest.raises(SpeechBlocked) as ei:
        render_speech_mp3(PASSAGE, speech, chunk=True)
    assert ei.value.text == "The climax comes too early here."
    assert speech.calls == ["First sentence is fine here.", "The climax comes too early here."]


def test_render_single_sentence_block_is_not_resent():
    speech = FakeSpeechProvider(block="climax")
    with pytest.raises(SpeechBlocked) as ei:
        render_speech_mp3("The climax comes too early here.", speech)
    assert ei.value.text == "The climax comes too early here."
    assert speech.calls == ["The climax comes too early here."]


def test_render_non_block_error_is_not_located():
    speech = FakeSpeechProvider(fail=True)
    with pytest.raises(SpeechError) as ei:
        render_speech_mp3(PASSAGE, speech)
    assert not isinstance(ei.value, SpeechBlocked)
    assert speech.calls == [PASSAGE]


def test_synthesize_tags_segment_and_persists_cache_per_segment(tmp_path):
    pkg = _pkg(tmp_path)
    blocked = make_notes(set_intros={"1": "a", "2": "the climax"})
    with pytest.raises(SpeechBlocked) as ei:
        _synthesize_dj_audio(pkg.dir, blocked, FakeSpeechProvider(block="climax"), False)
    assert ei.value.segment == "set2-intro"
    assert "in set2-intro" in str(ei.value)
    sidecar = _json.loads((pkg.dir / "dj-audio" / "segments.json").read_text())
    assert "set1-intro.mp3" in sidecar

    second = FakeSpeechProvider()
    _synthesize_dj_audio(pkg.dir, make_notes(set_intros={"1": "a", "2": "b"}), second, False)
    assert second.calls == ["b", "o"]  # set 1 came from the cache


def test_synthesize_rendered_set_exempts_from_force(tmp_path):
    pkg = _pkg(tmp_path)
    rendered: set[str] = set()
    first = FakeSpeechProvider()
    _synthesize_dj_audio(pkg.dir, make_notes(), first, True, rendered=rendered)
    assert len(first.calls) == 3
    assert rendered == {"set1-intro.mp3", "set2-intro.mp3", "99-outro.mp3"}

    second = FakeSpeechProvider()
    _synthesize_dj_audio(pkg.dir, make_notes(outro="new outro"), second, True, rendered=rendered)
    assert second.calls == ["new outro"]  # changed text still re-renders


def test_synthesize_force_without_rendered_still_rerenders_everything(tmp_path):
    pkg = _pkg(tmp_path)
    _synthesize_dj_audio(pkg.dir, make_notes(), FakeSpeechProvider(), False)
    again = FakeSpeechProvider()
    _synthesize_dj_audio(pkg.dir, make_notes(), again, True)
    assert len(again.calls) == 3
```

Append to `packages/emcee/tests/test_say_cmd.py`:

```python
from emcee.tts.provider import SpeechBlocked


def test_say_names_the_blocked_sentence(tmp_path, monkeypatch):
    speech, _ = _arm_speech(monkeypatch)
    speech.block = "climax"
    src = _text_file(tmp_path, "First sentence here, fine. The climax comes too early here.")

    result = _run(["say", str(src), "--no-chunk"], tmp_path, monkeypatch)

    assert result.exit_code != 0
    assert isinstance(result.exception, SpeechBlocked)
    assert result.exception.details == ['blocked: "The climax comes too early here."']
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/pytest packages/emcee/tests/test_audio.py packages/emcee/tests/test_say_cmd.py -q`
Expected: FAIL — the locate tests see `.text == PASSAGE`; `rendered` is an unexpected keyword; the sidecar does not exist after the failure.

- [ ] **Step 3: Implement**

In `packages/emcee/src/emcee/audio.py`, change the import to `from emcee.tts.provider import SpeechBlocked, SpeechError`, and add above `render_speech_mp3`:

```python
def _locate_block(text: str, speech, fmt: str, blocked: SpeechBlocked) -> SpeechBlocked:
    """Narrow a whole-passage content-filter block to the sentence that trips
    it, by synthesizing each sentence alone (audio discarded) until one is
    refused. A single-sentence passage returns `blocked` untouched -- locating
    would resend the identical refused request. When every sentence passes
    alone, the trigger only exists in context: chunked synthesis avoids it,
    and the returned exception says so (whole_passage=True)."""
    sentences = _split_sentences(text)
    if len(sentences) <= 1:
        return blocked
    for sentence in sentences:
        try:
            speech.synthesize(sentence, fmt=fmt)
        except SpeechBlocked as located:
            return located
    return SpeechBlocked(blocked.backend, text=text, categories=blocked.categories,
                         whole_passage=True)
```

Rename the current body of `render_speech_mp3` (everything after its docstring) into a private `_render(text, speech, chunk, bed_pcm, bed_rate, bed_gain_db) -> bytes` placed directly above it, unchanged, and make `render_speech_mp3`'s body:

```python
    try:
        return _render(text, speech, chunk, bed_pcm, bed_rate, bed_gain_db)
    except SpeechBlocked as blocked:
        if chunk:
            raise  # each chunk is already its own request
        located = _locate_block(text, speech, "wav" if bed_pcm is not None else "mp3", blocked)
        if located is blocked:
            raise
        raise located from blocked
```

Add to `render_speech_mp3`'s docstring: "A content-filter block on an unchunked call is narrowed to one sentence (`_locate_block`) so the error names it; this is the one renderer `emcee say` and DJ clips share, so both get it."

In `_synthesize_dj_audio`: add the parameter `rendered: set[str] | None = None` after `bed`; first line of the body `rendered = set() if rendered is None else rendered`; replace the render block inside the loop with:

```python
        if (force and filename not in rendered) or not dest.exists() or cached.get(filename) != key:
            detail(f"synthesizing {filename}")
            try:
                data = render_speech_mp3(
                    spoken, speech, chunk=chunk, bed_pcm=bed_pcm, bed_rate=bed_rate,
                    bed_gain_db=bed.gain_db if bed is not None else 0.0)
            except SpeechBlocked as blocked:
                blocked.segment = stem
                raise
            atomic_write_bytes(dest, data)
            rendered.add(filename)
            # Persist as we go, so a retry after a later segment fails (the
            # content-filter repair loop, or a re-run) reuses this clip.
            atomic_write_text(sidecar, json.dumps({**cached, **keys}, indent=2))
```

and add to its docstring: "`rendered` (filenames already rendered earlier in the same `process_package` call) is exempt from `force`, so a repair round under `--force` does not re-pay for clips it just made. The sidecar is persisted after every rendered segment; the final write and orphan pruning still happen only on full success."

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/pytest packages/emcee -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add packages/emcee/src/emcee/audio.py packages/emcee/tests/test_audio.py packages/emcee/tests/test_say_cmd.py
git commit -m "feat(emcee): name the blocked sentence, tag its segment, persist the clip cache per segment"
```

---

### Task 3: The `rephrase` task and the containment check

**Files:**
- Create: `packages/emcee/src/emcee/prompts/rephrase.md`
- Modify: `packages/emcee/src/emcee/models.py`, `packages/emcee/src/emcee/scriptwrite.py`, `packages/emcee/src/emcee/config.py`
- Test: `packages/emcee/tests/test_scriptwrite.py`, `packages/emcee/tests/test_config.py`

**Interfaces:**
- Consumes: `emcee.audio._split_sentences(text: str) -> list[str]` (existing).
- Produces:
  - `emcee.models.RephrasedSegment(text: str)`.
  - `emcee.scriptwrite.rephrase_segment(provider, segment_text: str, blocked_text: str, categories: list[str], feedback: str = "") -> str` — returns the stripped revised segment.
  - `emcee.scriptwrite.rephrase_problems(original: str, revised: str, manifest: dict) -> list[str]` — empty list means acceptable.
  - `config.TASK_KEYS == ["scriptwrite", "rephrase"]`, `DEFAULT_TIERS == {"scriptwrite": "high", "rephrase": "medium"}`.

- [ ] **Step 1: Write the failing tests**

Append to `packages/emcee/tests/test_scriptwrite.py`:

```python
from emcee.scriptwrite import rephrase_problems, rephrase_segment

SEG = ("China Cat Sunflower leads set two. The climax comes a little early tonight. "
       "Stay with us for the rest of the night.")
MANIFEST = {"tracks": [{"title": "China Cat Sunflower"}, {"title": "Deal"},
                       {"title": "Morning Dew"}]}


def test_rephrase_segment_returns_text_and_prompt_carries_inputs():
    provider = FakeProvider(completes=[json.dumps({"text": "  Revised segment.  "})])
    out = rephrase_segment(provider, SEG, "The climax comes a little early tonight.",
                           ["sexual"])
    assert out == "Revised segment."
    prompt = provider.calls[0][1]
    assert SEG in prompt
    assert "The climax comes a little early tonight." in prompt
    assert "sexual" in prompt
    assert "previous attempt" not in prompt


def test_rephrase_segment_feedback_reaches_prompt():
    provider = FakeProvider(completes=[json.dumps({"text": "x"})])
    rephrase_segment(provider, SEG, "b", [], feedback="dj notes claim 3 sets")
    prompt = provider.calls[0][1]
    assert "previous attempt" in prompt and "dj notes claim 3 sets" in prompt
    assert "unspecified" in prompt  # empty categories


def test_rephrase_problems_single_sentence_edit_passes():
    revised = SEG.replace("The climax comes a little early tonight.",
                          "A tape flip cuts into the peak tonight.")
    assert rephrase_problems(SEG, revised, MANIFEST) == []


def test_rephrase_problems_two_separated_edits():
    # First and third sentences changed, the middle one kept: two separate edits.
    revised = (SEG.replace("China Cat Sunflower leads", "China Cat Sunflower opens")
                  .replace("Stay with us", "Do stay with us"))
    assert any("more than one passage" in p for p in rephrase_problems(SEG, revised, MANIFEST))


def test_rephrase_problems_newly_named_track():
    revised = SEG.replace("The climax comes a little early tonight.",
                          "Morning Dew arrives a little early tonight.")
    assert rephrase_problems(SEG, revised, MANIFEST) == [
        "rephrase names a track the original did not: Morning Dew"]


def test_rephrase_problems_new_number():
    revised = SEG.replace("The climax comes a little early tonight.",
                          "The peak lands 3 minutes early tonight.")
    assert rephrase_problems(SEG, revised, MANIFEST) == [
        "rephrase adds numbers the original did not have: 3"]


def test_rephrase_problems_title_match_is_whole_word():
    revised = SEG.replace("The climax comes a little early tonight.",
                          "The ideal peak comes a little early tonight.")
    assert rephrase_problems(SEG, revised, MANIFEST) == []  # "ideal" is not "Deal"
    orig = SEG.replace("The climax", "A great deal of the climax")
    rev = orig.replace("A great deal of the climax comes", "A great deal of the peak comes")
    assert rephrase_problems(orig, rev, MANIFEST) == []  # "deal" was already there
```

In `packages/emcee/tests/test_config.py`, update the three vocabulary/template tests:

```python
def test_default_tiers_vocabulary():
    assert DEFAULT_TIERS == {"scriptwrite": "high", "rephrase": "medium"}


def test_task_keys_vocabulary():
    assert TASK_KEYS == ["scriptwrite", "rephrase"]
```

and in `test_default_config_template_matches_defaults` replace the last two lines with:

```python
    assert set(parsed.llm) == {"scriptwrite", "rephrase"}
    for task in ("scriptwrite", "rephrase"):
        assert parsed.llm_for(task) == default.llm_for(task)
```

and add `"[llm.rephrase]"` to the marker tuple in `test_default_config_template_mentions_every_section`. Also add:

```python
def test_rephrase_defaults_to_medium():
    assert resolve_model(EmceeConfig().llm_settings(), "rephrase") == ("claude_cli", "sonnet")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/pytest packages/emcee/tests/test_scriptwrite.py packages/emcee/tests/test_config.py -q`
Expected: FAIL — `ImportError: cannot import name 'rephrase_problems'`, and the vocabulary asserts.

- [ ] **Step 3: Implement**

`packages/emcee/src/emcee/models.py`, after `ScriptNotes`:

```python
class RephrasedSegment(BaseModel):
    """`rephrase` task output: one DJ segment with only the sentence a TTS
    content filter refused reworded; every other sentence verbatim."""

    text: str
```

Create `packages/emcee/src/emcee/prompts/rephrase.md`:

```
You are editing one segment of a radio DJ script that will be read aloud by a
synthetic voice. The text-to-speech service's content filter refused part of it
as: {{categories}}. The refused text (as sent to the voice, so spellings may be
expanded) was:

"{{blocked}}"

The script was innocent — the filter most likely read an unintended double
meaning into it. Reword ONLY what is needed so that no reasonable reader could
take it that way.

Rules:
- Change only the refused sentence (or the smallest stretch around it that you
  must). Copy every other sentence exactly, word for word.
- Keep the meaning, every fact, and the speaker's voice and tone.
- Introduce no song titles, people, places, dates, numbers or facts that the
  segment does not already contain.
- No symbols; write for the ear; no one- or two-word sentences.
{{feedback}}
The full segment:

{{segment}}

Respond with ONLY JSON in this shape:
{"text": "<the whole segment, with only the refused sentence reworded>"}
Raw JSON only.
```

`packages/emcee/src/emcee/scriptwrite.py`: add `import difflib`; import `RephrasedSegment` alongside `ScriptNotes` from `emcee.models`; add `from emcee.audio import _split_sentences`; append:

```python
# --- content-filter repair: the `rephrase` task and its containment check.

def rephrase_segment(provider, segment_text: str, blocked_text: str,
                     categories: list[str], feedback: str = "") -> str:
    """Reword the sentence a TTS content filter refused, returning the whole
    segment. `blocked_text` is the speech-normalized form that was sent, so
    the model gets the whole script segment back rather than a sentence to
    splice: mapping normalized text back onto script text is fragile."""
    note = (f"\nIMPORTANT: your previous attempt was rejected: {feedback}. "
            "Fix that too.\n" if feedback else "")
    result = run_json_task(
        provider, "rephrase", RephrasedSegment, template=load_prompt("rephrase"),
        segment=segment_text, blocked=blocked_text,
        categories=", ".join(categories) or "unspecified", feedback=note,
    )
    return result.text.strip()


_DIGITS = re.compile(r"\d+")


def _names(title: str, text: str) -> bool:
    # Whole-word, case-insensitive; lookarounds rather than \b so titles
    # ending in punctuation ("Truckin'") still match.
    return re.search(rf"(?<!\w){re.escape(title.lower())}(?!\w)", text.lower()) is not None


def rephrase_problems(original: str, revised: str, manifest: dict) -> list[str]:
    """Deterministic limits on a rephrase, beyond `script_guard` -- whose song
    checks read only the self-reported `mentioned_songs`, which a rephrase
    never updates. One contiguous edit; no newly named track; no new numbers.
    Out-of-show songs and reworded facts inside the edited sentence remain
    undetectable here; the prompt forbids them and the repair prints the
    revised segment."""
    problems: list[str] = []
    a, b = _split_sentences(original), _split_sentences(revised)
    edits = [op for op in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes()
             if op[0] != "equal"]
    if len(edits) > 1:
        problems.append("rephrase changed more than one passage; "
                        "keep every other sentence verbatim")
    titles = sorted({t["title"] for t in manifest["tracks"] if t.get("title")})
    for title in titles:
        if _names(title, revised) and not _names(title, original):
            problems.append(f"rephrase names a track the original did not: {title}")
    new = sorted(set(_DIGITS.findall(revised)) - set(_DIGITS.findall(original)), key=int)
    if new:
        problems.append(f"rephrase adds numbers the original did not have: {', '.join(new)}")
    return problems
```

`packages/emcee/src/emcee/config.py`: `TASK_KEYS = ["scriptwrite", "rephrase"]`; `DEFAULT_TIERS = {"scriptwrite": "high", "rephrase": "medium"}` with the comment extended: "rephrase rewords one sentence a TTS content filter refused -- small, so medium." In `DEFAULT_CONFIG_TOML`, directly after the `[llm.scriptwrite]` block (before `# [llm.tiers.openrouter]`), add:

```toml
[llm.rephrase]
# rewords a DJ-script sentence the TTS content filter refused (rare).
# An unset task falls back to [llm.default], else claude_cli -- so if you
# change scriptwrite's backend above, change this one too.
backend = "claude_cli"
# Default: medium.
# tier = "low"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/pytest packages/emcee -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add packages/emcee/src/emcee/prompts/rephrase.md packages/emcee/src/emcee/models.py packages/emcee/src/emcee/scriptwrite.py packages/emcee/src/emcee/config.py packages/emcee/tests/test_scriptwrite.py packages/emcee/tests/test_config.py
git commit -m "feat(emcee): rephrase task and containment check for content-filter repairs"
```

---

### Task 4: The repair loop in `process_package`

**Files:**
- Modify: `packages/emcee/src/emcee/process.py`
- Modify: `CLAUDE.md` (one sentence in the emcee architecture bullet)
- Test: `packages/emcee/tests/test_process.py`

**Interfaces:**
- Consumes: `SpeechBlocked` (Task 1); `_synthesize_dj_audio(..., rendered=)` and its `.segment` tagging (Task 2); `rephrase_segment`, `rephrase_problems` (Task 3); existing `script_guard(notes, manifest, narration)`, `render_notes_md`, `detail` (from `emcee.audio`), `provider_for`.
- Produces: `process.MAX_REPHRASES = 2`; `process_package` signature unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `packages/emcee/tests/test_process.py` (it already imports `json`, `pytest`, `FakeProvider`, `EmceeConfig`, `TTSConfig`, `EmceeError`, `Package`, `process_package`, `FakeSpeechProvider`, `build_package`, and defines `_good_notes_json`):

```python
from herder import TaskFailed

from emcee.tts.provider import SpeechBlocked

CLEAN_S1 = "China Cat Sunflower leads set two."
BLOCKED_S2 = "The climax comes a little early tonight."
SEG2 = f"{CLEAN_S1} {BLOCKED_S2}"
SET1 = "Tonight: the Dead at RFK. Opens with Morning Dew."


def _arm(monkeypatch, rephrases, notes_json=None):
    """Route provider_for: scriptwrite -> one script, rephrase -> `rephrases`
    queue. Returns (rephrase FakeProvider, list of tasks requested)."""
    script = FakeProvider(completes=[notes_json or _good_notes_json(
        set_intros={"1": SET1, "2": SEG2})])
    rephrase = FakeProvider(completes=[json.dumps({"text": t}) if isinstance(t, str) else t
                                       for t in rephrases])
    requested: list[str] = []

    def fake_provider_for(settings, task):
        requested.append(task)
        return {"scriptwrite": script, "rephrase": rephrase}[task]

    monkeypatch.setattr("emcee.process.provider_for", fake_provider_for)
    return rephrase, requested


def _setup(tmp_path):
    pkg = Package(build_package(tmp_path / "station", voiced=False))
    return pkg, EmceeConfig(root=tmp_path / "home")


def test_blocked_sentence_is_rephrased_and_package_succeeds(tmp_path, monkeypatch):
    revised = f"{CLEAN_S1} The peak arrives a little early tonight."
    rephrase, _ = _arm(monkeypatch, [revised])
    pkg, config = _setup(tmp_path)
    speech = FakeSpeechProvider(block="climax")

    process_package(config, pkg, speech)

    m = pkg.manifest()
    assert m["dj_notes"]["set_intros"]["2"] == revised
    notes_md = (pkg.dir / "dj-notes.md").read_text()
    assert "The peak arrives" in notes_md and "climax" not in notes_md
    assert speech.calls.count(SET1) == 1          # set 1 rendered once, then cached
    assert revised in speech.calls                # the revision is what was voiced
    assert BLOCKED_S2 in rephrase.calls[0][1]     # located sentence reached the prompt


def test_force_still_renders_each_clip_once(tmp_path, monkeypatch):
    _arm(monkeypatch, [f"{CLEAN_S1} The peak arrives a little early tonight."])
    pkg, config = _setup(tmp_path)
    speech = FakeSpeechProvider(block="climax")

    process_package(config, pkg, speech, force=True)

    assert speech.calls.count(SET1) == 1


def test_reblocked_twice_raises_and_manifest_untouched(tmp_path, monkeypatch):
    rephrase, _ = _arm(monkeypatch, [f"{CLEAN_S1} The climax lands early tonight.",
                                     f"{CLEAN_S1} The climax hits early tonight."])
    pkg, config = _setup(tmp_path)
    before = pkg.manifest_path.read_text()

    with pytest.raises(EmceeError) as ei:
        process_package(config, pkg, FakeSpeechProvider(block="climax"))

    assert "set2-intro" in str(ei.value) and "sexual" in str(ei.value)
    assert any("also blocked" in d for d in ei.value.details)
    assert "also blocked" in rephrase.calls[1][1]
    assert pkg.manifest_path.read_text() == before


def test_guard_failing_rephrase_is_never_voiced(tmp_path, monkeypatch):
    bad = f"{CLEAN_S1} All three sets peak early tonight."   # guard: 3 sets vs 2
    good = f"{CLEAN_S1} The peak arrives a little early tonight."
    rephrase, _ = _arm(monkeypatch, [bad, good])
    pkg, config = _setup(tmp_path)
    speech = FakeSpeechProvider(block="climax")

    process_package(config, pkg, speech)

    assert not any("three sets" in c for c in speech.calls)
    assert "claim 3 sets" in rephrase.calls[1][1]
    assert "The peak arrives" in (pkg.dir / "dj-notes.md").read_text()
    assert pkg.manifest()["dj_notes"]["set_intros"]["2"] == good


def test_unchanged_rephrase_consumes_an_attempt(tmp_path, monkeypatch):
    good = f"{CLEAN_S1} The peak arrives a little early tonight."
    rephrase, _ = _arm(monkeypatch, [SEG2, good])
    pkg, config = _setup(tmp_path)

    process_package(config, pkg, FakeSpeechProvider(block="climax"))

    assert "unchanged" in rephrase.calls[1][1]
    assert pkg.manifest()["dj_notes"]["set_intros"]["2"] == good


def test_whole_passage_block_is_not_rephrased(tmp_path, monkeypatch):
    rephrase, requested = _arm(monkeypatch, [])
    pkg, config = _setup(tmp_path)
    before = pkg.manifest_path.read_text()

    with pytest.raises(SpeechBlocked) as ei:
        process_package(config, pkg, FakeSpeechProvider(block="two. The climax"))

    assert ei.value.whole_passage is True and ei.value.segment == "set2-intro"
    assert "rephrase" not in requested and rephrase.calls == []
    assert pkg.manifest_path.read_text() == before


def test_two_blocked_segments_each_get_their_own_budget(tmp_path, monkeypatch):
    outro = "I Know You Rider sends us off. The climax of the night was early."
    notes = _good_notes_json(set_intros={"1": SET1, "2": SEG2}, outro=outro)
    rev2 = f"{CLEAN_S1} The peak arrives a little early tonight."
    rev_outro = "I Know You Rider sends us off. The peak of the night came early."
    _arm(monkeypatch, [rev2, rev_outro], notes_json=notes)
    pkg, config = _setup(tmp_path)

    process_package(config, pkg, FakeSpeechProvider(block="climax"))

    m = pkg.manifest()
    assert m["dj_notes"]["set_intros"]["2"] == rev2
    assert m["dj_notes"]["outro"] == rev_outro


def test_rephrase_llm_failure_leaves_manifest_untouched(tmp_path, monkeypatch):
    script = FakeProvider(completes=[_good_notes_json(set_intros={"1": SET1, "2": SEG2})])
    rephrase = FakeProvider(completes=["not json", "still not json", "nope"])
    monkeypatch.setattr("emcee.process.provider_for",
                        lambda settings, task: {"scriptwrite": script, "rephrase": rephrase}[task])
    pkg, config = _setup(tmp_path)
    before = pkg.manifest_path.read_text()

    with pytest.raises(TaskFailed):
        process_package(config, pkg, FakeSpeechProvider(block="climax"))

    assert pkg.manifest_path.read_text() == before
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/pytest packages/emcee/tests/test_process.py -q`
Expected: the new tests FAIL — `SpeechBlocked` propagates out of `process_package` unrepaired.

- [ ] **Step 3: Implement**

In `packages/emcee/src/emcee/process.py`: extend the imports —

```python
from emcee.audio import _synthesize_dj_audio, broadcast_m3u_text, detail
from emcee.models import ScriptNotes
from emcee.scriptwrite import (render_notes_md, rephrase_problems, rephrase_segment,
                               script_guard, write_script)
from emcee.tts.provider import SpeechBlocked
```

Add above `process_package`:

```python
# Rephrase attempts per blocked segment per process_package call. An attempt
# is consumed by a guard/containment failure, an unchanged reply, or the
# revision being blocked again.
MAX_REPHRASES = 2


def _segment_text(notes: ScriptNotes, stem: str) -> str:
    if stem == "99-outro":
        return notes.outro
    return notes.set_intros[stem.removeprefix("set").removesuffix("-intro")]


def _with_segment(notes: ScriptNotes, stem: str, text: str) -> ScriptNotes:
    # model_copy is shallow: build a new set_intros dict, never mutate notes'.
    if stem == "99-outro":
        return notes.model_copy(update={"outro": text})
    key = stem.removeprefix("set").removesuffix("-intro")
    return notes.model_copy(update={"set_intros": {**notes.set_intros, key: text}})


def _repair(notes: ScriptNotes, blocked: SpeechBlocked, manifest: dict, provider,
            used: dict[str, int], last: dict[str, str], repaired: set[str],
            pkg_dir: Path) -> ScriptNotes:
    """Reword the segment `blocked` names until a revision passes
    `rephrase_problems` and `script_guard`, within MAX_REPHRASES; return the
    accepted notes. Each attempt rephrases the ADOPTED text, never a rejected
    candidate, and a rejected candidate is never returned."""
    seg = blocked.segment
    narration = manifest["briefing"]["narration"]
    cats = f" ({', '.join(blocked.categories)})" if blocked.categories else ""
    if seg in repaired:
        last[seg] = f'your previous rewording was also blocked: "{blocked.text}"'
    current = _segment_text(notes, seg)
    while used.get(seg, 0) < MAX_REPHRASES:
        used[seg] = used.get(seg, 0) + 1
        revised = rephrase_segment(provider, current, blocked.text, blocked.categories,
                                   feedback=last.get(seg, ""))
        candidate = _with_segment(notes, seg, revised)
        if not revised or revised == current.strip():
            problems = ["the rephrase returned the segment unchanged"]
        else:
            problems = (rephrase_problems(current, revised, manifest)
                        + script_guard(candidate, manifest, narration))
        if not problems:
            repaired.add(seg)
            detail(f"content filter blocked a sentence in {seg}{cats}; rephrased")
            detail(f'  blocked: "{blocked.text}"')
            detail(f'  revised: "{revised}"')
            return candidate
        last[seg] = "; ".join(problems)
    raise EmceeError(
        f"content filter blocked a sentence in {seg}{cats}; "
        f"{MAX_REPHRASES} rephrase attempts failed",
        details=[f'blocked: "{blocked.text}"',
                 f"last attempt: {last.get(seg, 'unknown')}",
                 f"re-run `emcee voice {pkg_dir}` for a fresh script"],
    )
```

In `process_package`, replace

```python
    dj_audio = _synthesize_dj_audio(pkg.dir, notes, speech, force,
                                    chunk=config.tts.chunk, lexicon=lexicon, bed=bed)
```

with

```python
    # A TTS content-filter block is repaired in place: reword the segment,
    # re-guard, rewrite dj-notes.md, re-synthesize. Clips already rendered
    # this call come from the cache (even under --force, via `rendered`).
    rendered: set[str] = set()
    used: dict[str, int] = {}
    last: dict[str, str] = {}
    repaired: set[str] = set()
    rephraser = None
    while True:
        try:
            dj_audio = _synthesize_dj_audio(pkg.dir, notes, speech, force,
                                            chunk=config.tts.chunk, lexicon=lexicon,
                                            bed=bed, rendered=rendered)
            break
        except SpeechBlocked as blocked:
            if blocked.whole_passage or blocked.segment is None:
                raise
            if rephraser is None:  # built lazily: most packages never need it
                rephraser = provider_for(config.llm_settings(), "rephrase")
            notes = _repair(notes, blocked, manifest, rephraser, used, last, repaired, pkg.dir)
            atomic_write_text(pkg.dir / "dj-notes.md", render_notes_md(notes, manifest))
```

and add to `process_package`'s docstring, after the "Order:" paragraph: "A TTS content-filter block (`SpeechBlocked`) is repaired in place by `_repair` -- see the 2026-10-03 content-filter spec; `rewrite_manifest` receives the final notes, so `dj_notes`, `dj-notes.md` and the voiced audio agree."

In `/Users/shawn/projects/llama/CLAUDE.md` (worktree copy), in the "**emcee (station-side voicing), architecture:**" bullet, after the sentence ending "`broadcast.m3u` → atomically rewrite the manifest's `dj_notes`/`dj_audio` blocks last, in place, in the package directory llama delivered (`package_io.py:rewrite_manifest`).", insert:

```
A Voxtral content-filter refusal (403 `guardrail_violation`) is `SpeechBlocked`:
emcee narrows it to the sentence, rewords just that segment with the small
`rephrase` task (2 attempts, gated by `rephrase_problems` + `script_guard`),
and re-voices only that segment; a block that exists only across sentences
fails with "re-run with `[tts] chunk = true`". Blocks are deterministic
(measured 7/7), so they are never retried identically; transport errors, 429
and 5xx get one retry.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/pytest -q` (whole repo, from the worktree root)
Expected: all pass, including `test_no_llama_imports`.

- [ ] **Step 5: Commit**

```bash
git add packages/emcee/src/emcee/process.py packages/emcee/tests/test_process.py CLAUDE.md
git commit -m "feat(emcee): repair content-filter blocks in process_package by rephrasing the segment"
```

---

### Task 5: Live smoke check (controller-run, after the branch review)

Not for an implementer subagent: it spends real Mistral and LLM calls on the operator's keys. The controller runs it once, from the worktree, after the final branch review.

- [ ] **Step 1: Rephrase the real blocked segment and voice it**

Save as `<scratchpad>/live_rephrase.py` (not in the repo) and run with the worktree's `./.venv/bin/python`:

```python
from pathlib import Path
from herder import provider_for
from emcee.audio import _split_sentences
from emcee.config import load_config
from emcee.scriptwrite import rephrase_segment
from emcee.speech_text import load_lexicon, normalize_for_speech
from emcee.tts.provider import SpeechBlocked
from emcee.tts.voxtral import VoxtralProvider

cfg = load_config()
md = Path("/Users/shawn/Documents/llama/delivered/gratefuldead-1971-08-06/dj-notes.md").read_text()
seg = md.split("## Set 2 lead-in\n", 1)[1].split("\n## ", 1)[0].strip()
blocked = "Be warned that a tape flip on this source brings that climax around a little early."
revised = rephrase_segment(provider_for(cfg.llm_settings(), "rephrase"), seg, blocked, ["sexual"])
print("REVISED:", revised)
p = VoxtralProvider(clone_ref=cfg.tts.voice_clone, api_key=cfg.tts.api_key)
for s in _split_sentences(normalize_for_speech(revised, load_lexicon(cfg.root))):
    try:
        p.synthesize(s, fmt="wav"); print("ok      ", s)
    except SpeechBlocked:
        print("BLOCKED ", s)
```

Expected: every sentence `ok`. Record the outcome (and the revised wording) in the spec's "Premises checked" section, replacing the "Unverified — a medium-tier rephrase clears the moderator" bullet.

- [ ] **Step 2: Re-voice the real package**

Run: `./.venv/bin/emcee voice /Users/shawn/Documents/llama/delivered/gratefuldead-1971-08-06`
Expected: `voiced` with all three clips; if the fresh script happens to trip the filter, the `rephrased` detail lines appear. Report the output to the user either way.
