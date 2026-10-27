# Paragraph-aware chunking, room tone, and the abbreviation split (emcee)

Status: draft, revised after spec review round 1, 2026-10-26.
Review mode: **Opus**.

## Why

emcee voices each DJ segment in chunks (`[tts] chunk`, default on): today one TTS
call per sentence, joined with 180 ms of silence. Listening tests on 2026-10-25/26
(local Qwen3-TTS for Kurt and Jimmy, hosted Voxtral for Phil) found three things
wrong with that, and one plain bug:

1. **Sentence chunks are too small and cut thoughts badly.** Many chunks are a
   short line on its own ("Apparently the joke stuck.", 26 characters), which
   sounds choppy, and larger chunks only help when their boundaries follow the
   script's thoughts. A chunk that starts one sentence into a new thought sounds
   wrong. But chunks that are too large (300-400 characters) sound rushed and
   droning. The operator's verdict after a sweep of today / 150 / 250 / 300 / 400:
   **250 characters, for both voices tested (Qwen and Voxtral).**
2. **The gaps are dead silence, which exposes the voice's own background.** A
   cloned voice reproduces its reference clip's room sound. Each Qwen chunk also
   begins with exact digital zeros (0.04-0.58 s measured) and sometimes has
   exact-zero runs inside it, so the silence at a join measured 0.19-0.65 s, and on
   a voice with any room sound every join is an audible dropout, even under the bed.
   Filling those silences with the clip's own quietest sound ("room tone") made the
   joins disappear in the operator's listening; shortening or removing the joins did
   not help (60 ms: slightly worse than today's; no join: rushed).
3. **The scriptwriter gives the chunker nothing to work with.** All 593 delivered
   segments are one block of text with no paragraph breaks.
4. **Bug: the sentence splitter splits after dotted abbreviations.** "The encore
   was U.S." and "Blues, still a new song..." went out as two TTS calls with a gap
   in the song title (gratefuldead-1974-05-19 outro). It affects every voice, today.

The goal: segments that sound like one person talking, with natural breaks between
thoughts, on any presenter, without rushed delivery.

## Stakes

This changes how every DJ clip is rendered, on air, for every presenter. Nothing
here deletes, migrates or overwrites user data, and readiness is untouched, so no
broadcast-ready package changes state. The real costs are **on-air quality** and
**paid TTS** (Voxtral characters are metered; narrowing a blocked chunk spends extra
calls, and the chunk size shapes every request). It adds no re-render spend:
`process_package` writes a new script on every voicing, so with a real LLM every clip
re-renders on every voicing whatever the cache key says; in practice the key matters
within one call (repair rounds, the `rendered` set, `--force`). **Strict surfaces:**
the content-filter recovery path (`_locate_block` and the `rephrase` repair) must keep
working sentence by sentence; a regression there can make a blocked show unvoiceable.
The render-cache key must change whenever the rendered audio would change; a stale
hit ships old audio for new text. Leaving it unchanged otherwise is preferred, but
buys little given re-scripting.

## Goals

- Chunk boundaries fall between thoughts, and chunks stay near the 250-character
  ceiling instead of one sentence each.
- No exact-silence dropout at joins or inside chunks, on any voice.
- "U.S. Blues", "Washington, D.C.", "L.A." and "B.B. King" are never split.
- The scriptwriter writes segments as short paragraphs.

## Non-goals

- Changing the 180 ms join length (tested; today's is preferred).
- Per-backend or per-presenter ceilings (the operator chose one value for both
  voices tested; it stays configurable, see below).
- Re-voicing already-voiced packages. New rendering applies when a package is next
  voiced (`emcee run` for pending packages, `emcee voice` by hand).
- Denoising or filtering reference clips (tested: a high-pass/hum filter thinned
  Kurt's voice; ffmpeg `afftdn` did nothing on his low-frequency room sound).
- A voice-drift detector (an experiment showed promise but is parked).
- Operator configuration changes that came out of the same tests (pointing Kurt at
  the un-evened `kurt1.wav`, adding `live,Lyve,` to the pronunciation overlay).
  Those are config edits, recorded under "Related operator actions" below.

## Anti-goals

- Anything that makes the content-filter repair unable to find or reword the one
  blocked sentence.
- A chunk boundary inside a sentence. A sentence longer than the ceiling is sent
  whole, never split.
- Room tone that is audible as added noise on a clean voice (it must come from the
  clip itself, so a clean clip yields near-silence).
- Silent cache reuse of audio rendered under the old rules for a segment whose
  chunking changed.

## Design (decided)

### 1. The scriptwriter writes paragraphs

`prompts/scriptwrite.md` asks for each lead-in and the outro to be written as short
paragraphs: one thought per paragraph, typically two to four sentences, separated
by a blank line. The prompt says the break is written as the JSON escape `\n\n`
inside the string, never a raw line break: raw control characters are invalid JSON,
and herder's `model_validate_json` rejects them, which costs a retry at a higher
tier. The existing hard rules are unchanged; the paragraph instruction is guidance
about structure, placed with the description of the segments (not a fifth "hard
rule").

`prompts/rephrase.md` asks the model to keep the blank lines between paragraphs (the
same escaped `\n\n`). No code re-inserts breaks: a repaired segment that loses them
simply packs as plain text (section 2, step 5). Re-inserting them would edit text
around the repair's checks, on the strict path, for little gain.

`dj-notes.md` already renders each segment's text as-is, so paragraphs show there.

### 2. Paragraph-aware packing at a 250-character ceiling

A new packer replaces the sentence-per-chunk split **for synthesis only**
(`_chunked_pcm`, so DJ clips and `emcee say` both get it). For a segment's
speech-normalized text and ceiling `C` (`[tts] chunk_chars`, default 250):

1. Split into paragraphs on blank lines: two or more newlines, with only whitespace
   between them, count as one break. A single newline, like any other whitespace
   inside a paragraph, collapses to one space.
2. A paragraph of at most `C` characters is one unit. A longer paragraph is split
   into sentences (the splitter in section 4) and its sentences are packed greedily
   into units of at most `C`; a single sentence longer than `C` is its own unit.
3. Units are then combined greedily, in order, while the combined text (joined by
   one space) stays at most `C`. So two short thoughts can share a chunk, but a
   chunk never ends inside a sentence.
4. After packing, a chunk shorter than `_MIN_FRAGMENT_LEN` (20 characters) is joined
   to the chunk before it (or the one after, if it is first), even if that exceeds
   `C`, for the same reason the splitter does it today: a tiny, context-free fragment
   makes a backend hallucinate. This is the only way a chunk of more than one
   sentence can exceed `C`.
5. Text with no paragraph breaks (every existing script) is one paragraph, so it
   packs plain sentences up to `C`. That is the "plain 250" variant that tested
   better than today on its own.

Greedy packing of a long paragraph can leave a short tail chunk. That is what was
listened to and chosen at 250, so there is no rebalancing toward a minimum chunk
size; the 20-character guard in step 4 is the only floor.

Every chunk sent to a provider contains **no newline character**. This matters on
mlx_audio: Qwen's generator splits its input on `"\n"` and renders each piece as a
separate generation, so a newline inside a chunk would silently become several
requests.

Measured on the test scripts (characters, Kurt's six segments with hand-placed
paragraph breaks): today 68 chunks of 28-230; ceiling 250, 52 chunks of 57-246.
Characters were checked against words and syllables as the length unit: across 307
rendered chunks, characters predicted spoken duration best (correlation 0.973;
syllables 0.967, words 0.960).

### 3. Room-tone fill

After a segment's chunks are rendered, loudness-normalized and joined (today's
`_chunked_pcm`, 180 ms joins unchanged), every run of exact digital silence of at
least ~20 ms in the joined PCM, at the joins and inside chunks alike, is filled
with room tone taken from the same segment:

- Source: the segment's quietest non-silent 20 ms frames (the lowest ~8% by RMS),
  concatenated in a pseudo-random order with short (~5 ms) crossfades until the run
  is filled, and faded in and out against the neighbouring audio. Timing is
  unchanged: the fill replaces silence sample for sample.
- Pool: a frame containing an exact-zero run (a few samples or more) is left out of
  the pool, not only an all-zero frame, so the fill itself carries no dropouts (the
  harness left out only all-zero frames; the release listening check covers the
  difference).
- Edges: a zero run at the very start or end of the segment has a neighbour on one
  side only. It is filled, faded in from zero at the clip start and out to zero at
  the clip end (over the crossfade length), so a no-bed clip does not end on a step.
- Deterministic: the frame order comes from a generator seeded with an integer
  derived from the sha256 of the spoken text (never Python's `hash()`, which is
  salted per process), so re-rendering the same text with the same audio gives the
  same bytes. Determinism is a test property; cache reuse stores bytes and does not
  depend on it.
- The fill is a no-op when the segment has no non-silent frames to draw from (for
  example the `fake` provider) or no qualifying zero run.
- Mono only: the fill runs on mono PCM and is skipped when the audio has more than
  one channel (no current provider returns stereo).

It runs on the chunked path whether or not a bed is mixed, for every voice, behind
`[tts] room_tone` (default **on**; operator decision 2026-10-26: on everywhere, with a
switch as cheap insurance so a surprise is a config edit, not a release).

On a clean voice it is close to a no-op. Applied offline to Phil's Voxtral renders
(no API cost), Voxtral left no exact-zero runs inside its chunks; the only silences
were emcee's own 180 ms joins (5-12 per segment), filled at -63 to -69 dBFS (Kurt's
fill on Qwen sits near -40). The operator heard no difference on Phil, with or
without the bed. The experiment's implementation is `room_tone()` in the harness's
`noise_test.py` (see Evidence); the parameters above are what was listened to.

### 4. The sentence splitter keeps dotted abbreviations whole

`_split_sentences` gains one rule: never split after a token made of two or more
single letters each followed by a dot (`U.S.`, `D.C.`, `L.A.`, `U.K.`, `B.B.`,
`K.C.`). When such a token really ends a sentence ("...in Washington, D.C. The band
came out..."), the two sentences stay together, which costs nothing. This fixes the
split everywhere `_split_sentences` is used, including the content-filter locator
and the rephrase comparison.

The rule is applied to the raw split parts as a pre-pass, before `_split_sentences`'
existing short-fragment merge. In the other order, "The encore was U.S." (19
characters) merges backward first and the rule then glues the next sentence on as
well, giving a unit of about 500 characters (measured on the gratefuldead-1974-05-19
outro; 5 of 593 delivered segments are affected).

### 5. A content-filter block on a multi-sentence chunk (operator decision)

Today one chunk is one sentence, so a refused chunk already names its sentence:
`render_speech_mp3` re-raises a chunked `SpeechBlocked` as is ("each chunk is already
its own request"), and the `rephrase` repair rewords exactly that sentence. A packed
chunk can hold several sentences, so the chunked renderer (the per-chunk loop in
`_chunked_pcm`) handles a refused chunk of more than one sentence itself:

- **(a) Narrow first.** Each piece of `_split_sentences(<that chunk's text>)` is
  synthesized alone as WAV (the format of the refused call), and the audio is kept.
  The first piece refused is raised as an ordinary located `SpeechBlocked` for that
  sentence (`whole_passage` false), which is what the `rephrase` repair handles
  today; the repair rewords that sentence only. The extra calls happen only on a
  block, which is rare.
- **(b) Fall back, never fail.** If every piece passes alone, the trigger exists only
  across sentences, and those takes, each loudness-normalized and joined with the
  usual 180 ms, are that chunk's render. Nothing is synthesized a second time, so the
  fallback costs nothing extra and does not depend on the filter giving the same
  verdict twice; since no call is made after narrowing, there is no "blocked during
  fallback" case. Chunks before and after keep their packing and are not
  re-synthesized. The old "re-run with `[tts] chunk = true`" failure is not reachable
  on the chunked path. It still applies to `chunk = false`.

`render_speech_mp3`'s chunked re-raise stays as is. A one-sentence chunk behaves
exactly as today.

Known limits:

- When `[tts.verify]` covers the backend, the narrowing takes are verified like any
  take (they are kept, so this matters); a quality failure there fails the package
  as any quality failure does.
- The abbreviation rule (section 4) can make a two-sentence chunk count as one
  sentence; a trigger that exists only across that boundary then goes to the repair
  rather than the fallback. Rare and acceptable.
- A block caused by a name the repair must keep (Voxtral blocks the band name
  "Cracker") stays unrepairable, as today; not a regression.

### 6. The cache key

On the chunked path the clip render key gains a digest of the planned chunk texts:
the packer's output for this spoken text and ceiling, joined with a separator that
cannot occur in text. The ceiling, the packer, and the sentence splitter and its
constants are then all covered exactly, with no version to remember. When
`room_tone` is on, the key also carries `tone=<ROOM_TONE_VERSION>`, a named module
constant like `LOUDNESS_VERSION`, whose comment says that any change to the fill's
output (its constants or its algorithm) bumps it. The existing `chunk=` and `loud=`
parts stay. The unchunked path's key is unchanged.

A chunk rendered through section 5's fallback is a function of the provider's
verdicts, not of the key. That is acceptable: blocks are rare, and the text changes
on the next repair round or voicing.

### 7. What does not change

- `_locate_block` (content-filter narrowing on the unchunked path) and
  `rephrase_problems` keep splitting by **sentence**; they gain only the abbreviation
  fix. Section 5's narrowing splits by sentence the same way but keeps its audio, so
  it lives in the chunked renderer.
- The 180 ms join, `normalize_speech`, the bed mix, the runaway guard, and transcript
  verification.
- `[tts] chunk = false` (one call per segment) renders as today.

## Configuration

- `[tts] chunk_chars` (integer, 50 to 1000, default 250): the packing ceiling, used
  only when `chunk` is true. A setting rather than a constant so the operator can
  retune it without a release; one value for every backend. `emcee say` reads it too.
  Below 50 nothing is gained (a sentence longer than `C` is its own unit, so tiny
  values degrade to one sentence per chunk); 1000 keeps every chunk well under
  Voxtral's 2000-character input guard. Values above ~400 were not listened to.
  Validated under the strict config base (a non-integer or out-of-range value is a
  load error).
- `[tts] room_tone` (bool, default true): the room-tone fill, chunked path only.
- Below the CLI / `process_package` boundary both values are passed keyword-only with
  **no defaults** (into `_synthesize_dj_audio`, `render_speech_mp3`, the chunked
  renderer and the key), so the key and the render always read the same value, as
  `speech_provider_for` does.

## Settled at the builder check (coordinator's calls, not the operator's)

- With `chunk = false` the text may now contain paragraph breaks. Whitespace is
  collapsed once, at the start of `render_speech_mp3`'s unchunked branch, before both
  the provider call and `_locate_block`, so narrowing probes and error text match
  what was sent (mlx_audio would otherwise split at each newline). The unchunked key
  is computed before that and is unchanged, so a cached unchunked clip whose text
  had a newline would not re-render; harmless, because no delivered segment contains
  a newline (593/593 checked) and every voicing re-scripts.
- `emcee say` takes `chunk_chars` and `room_tone` from config like DJ clips.

## Left to the builder

- Function names, where the packer and room tone live (`audio.py` or small new
  modules), and test structure.
- Exact room-tone constants, within what was listened to (20 ms frames, ~8% quietest,
  ~5 ms crossfades, runs of ~20 ms or more).
- Whether section 5's narrowing takes pass neighbour context
  (`previous_text`/`next_text`) to a context-aware backend.

## Acceptance

- Tests pin: paragraph splitting (two or more newlines are one break, a single
  newline is a space) and whitespace collapse; the packing rules (including a
  sentence longer than the ceiling, paragraphs combined only when they fit, and the
  no-paragraph fallback); the 20-character guard; no newline in any chunk the
  provider receives; the abbreviation rule (and that a real sentence end after one is
  harmless), including the gratefuldead-1974-05-19 outro's text with no paragraph
  break, where no chunk exceeds the ceiling except a single sentence longer than it;
  room tone fills exact-zero runs, keeps length, draws no frame containing a zero
  run, fades the clip's first and last runs from and to zero, is deterministic, is a
  no-op without non-silent frames or qualifying runs, and is skipped on non-mono
  audio; the cache key changes when the planned chunks change (ceiling, packer,
  splitter) and with `ROOM_TONE_VERSION`, and is unchanged on the unchunked path;
  `room_tone = false` disables the fill and drops it from the key; `chunk_chars`
  outside 50-1000, or not an integer, is a config error; `_locate_block` and the
  rephrase checks still work sentence by sentence; a refused multi-sentence chunk is
  narrowed and raised as a located block for its sentence (`whole_passage` false);
  one whose sentences all pass alone is rendered from those takes with no further
  synthesis call and without re-synthesizing its neighbours; `chunk = false` sends no
  newline; the scriptwrite prompt asks for paragraphs as escaped `\n\n` and the
  rephrase prompt asks to keep them; a fake-LLM reply with escaped `\n\n` round-trips
  to real newlines in `ScriptNotes`.
- Each new rule is shown load-bearing by mutation (break it, name the test expected
  to fail first, see it fail).
- Docs and templates: the `emcee config init` template (pinned by
  `test_default_config_template_matches_defaults`) gains both keys with comments; the
  config comments, the `--chunk` help text, the `quality.py` docstring and any other
  "sentence-by-sentence" wording are updated; the README runbook and the CLAUDE.md
  emcee bullet describe paragraph packing and room tone.
- An operator listening check before release, kept small because Voxtral is metered:
  one Kurt (Qwen) and one Phil (Voxtral) segment voiced end to end with a real
  scriptwriter run, with bed, compared with today's rendering. Phil's check confirms
  room tone is inaudible on a clean voice. The run also checks that the notes
  contain paragraph breaks and that the log shows no invalid-JSON retries.

## Related operator actions (not part of this change)

- Point Kurt at the un-evened reference: `kurt1_even.wav` (levelled on 2026-10-04,
  before emcee normalized chunks itself) lifts his low-frequency room sound to a
  12 dB speech-to-floor gap; `kurt1.wav` gives 19 dB (21 dB in rendered output), and
  the operator preferred it clearly.
- `live,Lyve,` is in `~/.emcee/pronunciations.csv` (done). Plain "live" (as in
  concert) is read as "I live" inside long "Live from the Basement" chunks.
  Capitalised `Lyve`: 53/62 right on Qwen (Kurt and Jimmy), 14/14 on Voxtral (Phil,
  plain "live" 12/14). Lowercase `lyve` scored 17/42 on Qwen, so the capital matters.
  Caveat: the lexicon matches whole words case-insensitively, so the bare entry also
  respells the verb ("what I live for"); a phrase entry (e.g. `Live from the
  Basement`) is the narrower alternative, the operator's call.

## Evidence

Throwaway harness and renders: `~/.llama-harness/tts-experiments/` (outside the
repo; `render.py`, `para_test.py`, `bed_test.py`, `noise_test.py`, `d300_test.py`,
`sweep_test.py`, `voxtral_test.py`, `live_test.py`, listening pages under `out/`).
Every comparison was blind or side by side, with and without the bed, judged by the
operator. Two traps found there: macOS filenames are case-insensitive (a `Lyve`
render overwrote `lyve`), and Voxtral's content filter blocks the band name
"Cracker" (`hate_and_discrimination`), which a rephrase cannot work around.

Checked:

- The installed mlx-audio server does not override Qwen3-TTS's default
  `split_pattern="\n"`, so a newline in a request does split it.
- None of the 593 delivered segments contains a newline.
- The `U.S.` split reproduces on the gratefuldead-1974-05-19 outro.
