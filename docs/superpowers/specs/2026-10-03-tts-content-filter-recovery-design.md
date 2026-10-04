# emcee: recover from TTS content-filter blocks — design

**Date:** 2026-10-03
**Scope:** `packages/emcee` only (llama and herder untouched).
**Review mode:** Opus.

## Stakes

What is at risk is **on-air text quality**, not data. A repair could slip a
factual error into a script, or let the voiced audio, `dj-notes.md` and the
manifest's `dj_notes` disagree about what was said. Nothing here deletes or
overwrites anything that can't be regenerated (emcee re-scripts on every call).
**Strict surfaces:** (1) the manifest rewrite stays the package's *last* write,
done only on full success; (2) every revised script passes `script_guard`
before any of it is voiced; (3) the text that was synthesized, `dj-notes.md`,
and the manifest `dj_notes` block are identical on success.

## The failure

Production, 2026-10-03, `emcee run`:

```
error: gratefuldead-1971-08-06: voxtral returned 403: {"object":"error","message":"Request blocked by guardrail policy","type":"guardrail_violation","param":null,"code":"1920","raw_status_code":403,"guardrails":[{"moderation_llm_v2":{"action":"block","categories":{"sexual":{"violated":true},"hate_and_discrimination":{"violated":false},"selfharm":{"violated":false},"jailbreaking":{"violated":false}}}}]}
```

Measured afterwards by sending each chunk of the failed segment
(`set2-intro`, `[tts] chunk = true`) to Voxtral individually:

- Exactly one sentence is blocked: *"Be warned that a tape flip on this source
  brings that climax around a little early."* — the other nine, including the
  "Turn On Your Lovelight" sentence, pass. The outro (which also names
  Lovelight) was never attempted: segments render in order and the first
  failure aborts the package. All 11 outro sentences pass individually.
- **Deterministic:** the same sentence was blocked 2/2 times.
- **Contextual, not lexical:** "That climax comes around a little early."
  passes; "…tape flip on this source cuts into the end of that jam." passes.
  The moderator (`moderation_llm_v2`) reads whole-sentence innuendo.

Consequences for design: an identical retry of a blocked request is wasted
spend; changing chunk boundaries does not change the offending sentence; the
fix is to reword the sentence.

## Goals

1. A guardrail block is recognized as its own error, carrying the blocked
   text and the violated categories.
2. `emcee run`/`emcee voice` repair a blocked segment automatically: reword
   the offending sentence via a small LLM task, re-guard, re-voice just that
   segment, and finish the package.
3. When repair fails, the error names the segment, the category and the
   sentence, and says what to do.
4. Genuinely transient Voxtral failures (transport error/timeout, 429, 5xx)
   get one retry instead of failing the package on the first hiccup.
5. `emcee say` (no LLM) reports a block naming the exact sentence.

## Non-goals

- ElevenLabs block classification (its block response shape is unobserved;
  `SpeechBlocked` is backend-neutral so it can be added later).
- Pre-flight moderation (Mistral's public moderation endpoint is a different
  model from `moderation_llm_v2`; agreement is unmeasured).
- Prompt-level prevention in `scriptwrite.md` (the blocked sentence was
  innocent; the script model would not have seen it as risky).
- Retrying a blocked request identically.
- Any new CLI flag or config knob beyond the `rephrase` task key.

## Design

### 1. Error type and transient retry

`emcee/tts/provider.py` gains:

```python
class SpeechBlocked(SpeechError):
    """The speech backend's content filter refused this text."""
    def __init__(self, message, *, text: str, categories: list[str],
                 segment: str | None = None, whole_passage: bool = False): ...
```

- `text`: the exact string that was sent and refused.
- `categories`: the violated category names (`["sexual"]`); empty if the
  response doesn't say.
- `segment`: the DJ segment stem (`"set2-intro"`), filled in by the audio
  layer; `None` from the provider.
- `whole_passage`: set by the locator (section 2) when no individual sentence
  is blocked on its own.

`VoxtralProvider.synthesize`:

- A non-200 whose JSON body has `"type": "guardrail_violation"` raises
  `SpeechBlocked`. Categories are the keys with `"violated": true` across
  every entry of `guardrails[*].<moderator>.categories`. Message:
  `voxtral content filter blocked (sexual): "<text>"` (text truncated in the
  message only, never in `.text`). A body that isn't parseable JSON, or any
  other 4xx, stays a plain `SpeechError` exactly as today.
- **Transient retry:** `httpx.TransportError` (incl. timeouts), 429, and 5xx
  are retried **once** after a short fixed sleep (2 s, injectable for tests).
  The second failure raises `SpeechError` as today. 4xx other than 429 —
  guardrail blocks included — are never retried.

### 2. Locating the blocked sentence

In `audio.py`:

- **Chunked path:** each chunk is its own request, so the `SpeechBlocked`
  from `_chunked_pcm` already carries the offending chunk as `.text`. No
  change needed beyond letting it propagate.
- **Unchunked path:** a whole-segment request is refused, so the culprit is
  unknown. On `SpeechBlocked` from the single whole-passage call,
  `render_speech_mp3` **locates**: it splits the passage with the existing
  `_split_sentences` and synthesizes each sentence in order (same `fmt` the
  path was using), discarding the audio, until one raises `SpeechBlocked`;
  that sentence's exception is raised. Other `SpeechError`s during locating
  propagate unchanged.
- **Every sentence passes alone:** the trigger only exists in context, and
  chunked synthesis would already have avoided it. The locator raises
  `SpeechBlocked(..., whole_passage=True)` whose message says so: *every
  sentence passes the content filter on its own; re-run with
  `[tts] chunk = true`*. **No rephrase is attempted** in this case (section 4)
  and no new knob is added — the message is the whole remedy. (In chunked mode
  this case cannot arise: every request is already a single chunk.)
- Locating lives in `render_speech_mp3`, the one function both DJ clips and
  `emcee say` go through, so `say` gets the same sentence-level error.
- `_synthesize_dj_audio` catches `SpeechBlocked` around each segment, sets
  `.segment = stem`, and re-raises.

**Per-segment cache persistence.** Today `segments.json` is written only after
every segment succeeds, so a retry within the same process would re-render
segments that already succeeded. Change: after each segment is rendered and
written, persist the sidecar as `{**cached, **keys_so_far}`. On full success
the final write is `keys` alone and orphan pruning runs, exactly as today
(so stale entries are still dropped and pruning still only happens on
success).

### 3. The `rephrase` LLM task

- New prompt `emcee/prompts/rephrase.md`; new schema in `models.py`:
  `RephrasedSegment(text: str)`.
- `config.TASK_KEYS` gains `"rephrase"`; `DEFAULT_TIERS["rephrase"] =
  "medium"`; the `config init` template documents it alongside
  `[llm.scriptwrite]`.
- New function (in `scriptwrite.py`, beside `write_script`):
  `rephrase_segment(provider, segment_text, blocked_text, categories,
  feedback="") -> str`.
- Prompt inputs: the original segment (script text), the blocked text (its
  speech-normalized form, as sent), the categories, and `feedback`.
  Instructions: a text-to-speech content filter refused the quoted passage as
  `<categories>`, most likely an unintended double meaning; reword only what
  is needed to remove it; keep every other sentence verbatim; keep the
  meaning, facts and speaking voice; introduce no new song names, people,
  dates or facts; return the whole segment.
- The model gets the **whole segment** back rather than a single sentence to
  splice, because the blocked text is the *normalized* form (lexicon
  substitutions etc.) and mapping it back onto script text by string matching
  is fragile.

### 4. Repair loop

In `process.py:process_package`, synthesis becomes a loop:

```
used = {}                                  # segment stem -> attempts used
while True:
    try:
        dj_audio = _synthesize_dj_audio(...); break
    except SpeechBlocked as e:
        if e.whole_passage or e.segment is None: raise
        feedback = ""
        while True:                        # one iteration = one attempt
            if used.get(e.segment, 0) >= MAX_REPHRASES:   # 2
                raise <exhausted EmceeError>
            used[e.segment] += 1
            revised = rephrase_segment(..., feedback=feedback)
            candidate = <notes with that segment replaced by revised>
            problems = script_guard(candidate, manifest, narration)
            if revised is empty or unchanged: feedback = "<returned unchanged>"
            elif problems: feedback = "; ".join(problems)
            else: break                    # accept
        notes = candidate                  # only a guard-passing candidate
        rewrite dj-notes.md; detail(before/after)
        # loop: re-synthesize; done segments come from the cache
```

A rejected candidate is never adopted: `notes` only ever holds a script that
passed `script_guard`.

- Segment stem → `ScriptNotes` field: `set<key>-intro` → `set_intros[key]`,
  `99-outro` → `outro`.
- **Budget:** 2 rephrase attempts per segment per `process_package` call. An
  attempt is consumed by a guard failure, an empty/unchanged result, or the
  revised text being blocked again. Guard problems from a failed attempt are
  passed as `feedback` to the next one.
- **Success:** `dj-notes.md` is rewritten from the revised notes before
  re-synthesis; segments already rendered are served from the cache
  (section 2). A `detail()` line reports the repair:
  `content filter blocked a sentence in set2-intro (sexual); rephrased` plus
  two indented lines: `blocked: <blocked text>` and `revised: <full revised
  segment>` — the operator must be able to see what will go on air.
- **Exhausted:** raise `EmceeError` —
  `content filter blocked a sentence in set2-intro (sexual) and 2 rephrase
  attempts did not clear it` with details: the blocked text, and *re-run
  `emcee voice <package>` for a fresh script*. `emcee run`'s existing
  per-package error handling reports it and moves on.
- **`whole_passage`:** propagates unrepaired with the re-run-chunked message.
- The manifest rewrite stays last and only on success; `rewrite_manifest`
  receives the final (possibly revised) notes, so `dj_notes`,
  `dj-notes.md` and the audio agree.
- The narration directive is the manifest's `briefing.narration`, read as
  `write_script` does, so the re-guard applies the vague-narration checks too.

### 5. Testing (offline)

- `FakeSpeechProvider` gains `block: str | None` — any text containing that
  substring raises `SpeechBlocked(categories=["sexual"])`. Existing `fail`
  behaviour unchanged.
- **Voxtral** (`httpx.MockTransport`): guardrail 403 → `SpeechBlocked` with
  text + categories; non-guardrail 403 and non-JSON 403 → plain
  `SpeechError`, not retried; 500-then-200 succeeds with exactly 2 requests;
  500/500 fails after exactly 2; 429-then-200 succeeds; transport
  error-then-200 succeeds; guardrail 403 sent exactly once.
- **Locator:** unchunked block → exception `.text` is the blocked sentence,
  not the passage; every sentence passes alone → `whole_passage=True` and the
  message mentions `[tts] chunk`; chunked block → `.text` is the chunk with no
  extra locating calls; `emcee say` on blocked text exits non-zero naming the
  sentence.
- **Sidecar:** a failure in segment 2 leaves `segments.json` containing
  segment 1's key; a following call does not re-synthesize segment 1.
- **Repair (process):** block a phrase that the fake `rephrase` response
  removes → package succeeds; `dj-notes.md`, the manifest `dj_notes` and the
  synthesized texts all carry the revised wording; the earlier segment was
  synthesized once. Rephrase output still blocked twice → `EmceeError`
  naming segment + category, manifest untouched. Rephrase output that fails
  `script_guard` consumes an attempt and its problems reach the next
  rephrase's prompt. Unchanged output consumes an attempt. `whole_passage`
  → no rephrase call made.
- `test_no_llama_imports` continues to pass.

## Files touched

`tts/provider.py`, `tts/voxtral.py`, `tts/fake.py`, `audio.py`,
`process.py`, `scriptwrite.py`, `models.py`, `config.py`,
`prompts/rephrase.md` (new), tests, and `CLAUDE.md`'s emcee bullet (one line
on block recovery).
