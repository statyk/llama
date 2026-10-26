# Paragraph-aware chunking, room tone, and the abbreviation split (emcee)

Status: draft for review, 2026-10-26 (builder check done; operator answers folded in).
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
   begins with ~150 ms of exact digital zeros and sometimes has exact-zero runs
   inside it, so the silence at a join measured 0.19-0.65 s, and on a voice with
   any room sound every join is an audible dropout, even under the bed. Filling
   those silences with the clip's own quietest sound ("room tone") made the joins
   disappear in the operator's listening; shortening or removing the joins did not
   help (60 ms: slightly worse than today's; no join: rushed).
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
**paid TTS** (Voxtral characters are metered; every clip whose cache key changes
re-renders when its package is next voiced). **Strict surfaces:** the content-filter
recovery path (`_locate_block` and the `rephrase` repair) must keep working
sentence by sentence; a regression there can make a blocked show unvoiceable. The
render-cache key must change whenever the rendered audio would change, and must
not change otherwise; a stale hit ships old audio for new text.

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
by a blank line (a literal `\n\n` inside the JSON string). The existing hard rules
are unchanged; the paragraph instruction is guidance about structure, placed with
the description of the segments (not a fifth "hard rule").

`dj-notes.md` already renders each segment's text as-is, so paragraphs show there.

### 2. Paragraph-aware packing at a 250-character ceiling

A new packer replaces the sentence-per-chunk split **for synthesis only**
(`_chunked_pcm`, so DJ clips and `emcee say` both get it). For a segment's
speech-normalized text and ceiling `C` (`[tts] chunk_chars`, default 250):

1. Split into paragraphs on blank lines (one or more newlines with only whitespace
   between them count as one break). Whitespace inside a paragraph, including any
   single newline, collapses to one space.
2. A paragraph of at most `C` characters is one unit. A longer paragraph is split
   into sentences (the splitter in section 4) and its sentences are packed greedily
   into units of at most `C`; a single sentence longer than `C` is its own unit.
3. Units are then combined greedily, in order, while the combined text (joined by
   one space) stays at most `C`. So two short thoughts can share a chunk, but a
   chunk never ends inside a sentence.
4. Text with no paragraph breaks (every existing script) is one paragraph, so it
   packs plain sentences up to `C`. That is the "plain 250" variant that tested
   better than today on its own.

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

- Source: the segment's quietest non-silent 20 ms frames (the lowest ~8% by RMS,
  ignoring exact-zero frames), concatenated in a pseudo-random order with short
  (~5 ms) crossfades until the run is filled, and faded in and out against the
  neighbouring audio. Timing is unchanged: the fill replaces silence sample for
  sample.
- Deterministic: the frame order comes from a generator seeded from the segment
  text, so re-rendering the same text with the same audio gives the same bytes.
- If the segment has no usable quiet frames (for example the `fake` provider, or a
  provider that never emits exact zeros) the fill is a no-op.

It runs on the chunked path whether or not a bed is mixed, for every voice, behind
`[tts] room_tone` (default **on**; operator decision 2026-10-26: on everywhere, with a
switch as cheap insurance so a surprise is a config edit, not a release).

On a clean voice it is close to a no-op. Applied offline to Phil's Voxtral renders
(no API cost), Voxtral left no exact-zero runs inside its chunks; the only silences
were emcee's own 180 ms joins (5-12 per segment), filled at -63 to -69 dBFS (Kurt's
fill on Qwen sits near -40). The operator heard no difference on Phil, with or
without the bed. The experiment's
implementation is `room_tone()` in the harness's `noise_test.py` (see Evidence); the parameters
above are what was listened to.

### 4. The sentence splitter keeps dotted abbreviations whole

`_split_sentences` gains one rule: never split after a token made of two or more
single letters each followed by a dot (`U.S.`, `D.C.`, `L.A.`, `U.K.`, `B.B.`,
`K.C.`). When such a token really ends a sentence ("...in Washington, D.C. The band
came out..."), the two sentences stay together, which costs nothing. This fixes the
split everywhere `_split_sentences` is used, including the content-filter locator
and the rephrase comparison.

### 5. A content-filter block on a multi-sentence chunk (operator decision)

Today one chunk is one sentence, so a refused chunk already names its sentence:
`render_speech_mp3` re-raises a chunked `SpeechBlocked` as is ("each chunk is already
its own request"), and the `rephrase` repair rewords exactly that sentence. A packed
chunk can hold several sentences, so on the chunked path:

- **(a) Narrow first.** A blocked chunk of more than one sentence is narrowed to the
  refused sentence the way an unchunked block is today (`_locate_block`: synthesize
  each sentence alone, audio discarded, until one is refused), and the repair rewords
  that sentence only. The extra calls happen only on a block, which is rare.
- **(b) Fall back, never fail.** If every sentence of the chunk passes alone, the
  trigger exists only across sentences; that one chunk is rendered sentence by
  sentence (today's chunking, which avoids it), and the rest of the segment keeps its
  packing. The old "re-run with `[tts] chunk = true`" failure must not be reachable
  on the chunked path. It still applies to `chunk = false`.

A one-sentence chunk behaves exactly as today.

### 6. The cache key

The clip render key gains the chunking rule and the room tone, so audio rendered
under the old rules is never reused for a chunked segment, and a later change to
either re-renders exactly the affected clips: something like
`chunker=para-v1:250` and, when `room_tone` is on, `tone=v1` in the existing key
string, on the chunked path only. The unchunked path's key is unchanged.

### 7. What does not change

- `_locate_block` (content-filter narrowing) and `rephrase_problems` keep splitting
  by **sentence**; they gain only the abbreviation fix (and section 5's new caller).
- The 180 ms join, `normalize_speech`, the bed mix, the runaway guard, and transcript
  verification.
- `[tts] chunk = false` (one call per segment) behaves exactly as today.

## Configuration

- `[tts] chunk_chars` (integer, default 250): the packing ceiling, used only when
  `chunk` is true. A setting rather than a constant so the operator can retune it
  without a release; one value for every backend. `emcee say` reads it too.
- `[tts] room_tone` (bool, default true): the room-tone fill, chunked path only.

## Settled at the builder check (coordinator's calls, not the operator's)

- With `chunk = false` the text may now contain paragraph breaks; whitespace is
  collapsed in what is sent to the provider (after the cache key is computed), so
  that path renders as today (mlx_audio would otherwise split at each newline).
- The rephrase repair keeps a segment's paragraph breaks where it can; a repaired
  segment that loses them only falls back to plain packing.
- `emcee say` takes `chunk_chars` and `room_tone` from config like DJ clips.

## Left to the builder

- Function names, where the packer and room tone live (`audio.py` or small new
  modules), and test structure.
- How the rephrase repair keeps paragraph breaks (the rephrase prompt copies untouched
  sentences verbatim but may not keep blank lines, and `rephrase_problems` folds
  whitespace); the approach is the builder's, the goal is above.
- Validation bounds for `chunk_chars` (it must at least reject values too small to
  hold a normal sentence, and non-integers, under the strict config base).
- Exact room-tone constants, within what was listened to (20 ms frames, ~8% quietest,
  ~5 ms crossfades, runs of ~20 ms or more).

## Acceptance

- Tests pin: paragraph splitting and whitespace collapse; the packing rules
  (including a sentence longer than the ceiling, paragraphs combined only when they
  fit, and the no-paragraph fallback); no newline in any chunk the provider
  receives; the abbreviation rule (and that a real sentence end after one is
  harmless); room tone fills exact-zero runs, keeps length, is deterministic, and is
  a no-op without quiet frames; the cache key changes with chunker version, ceiling
  and tone and is unchanged on the unchunked path; `_locate_block` and the rephrase
  checks still work sentence by sentence; a blocked multi-sentence chunk is narrowed
  to its sentence, and one whose sentences all pass alone falls back to per-sentence
  rendering without failing; `room_tone = false` disables the fill and drops it from
  the key; `chunk = false` sends no newline; the scriptwrite prompt asks for paragraphs.
- Each new rule is shown load-bearing by mutation (break it, name the test expected
  to fail first, see it fail).
- An operator listening check before release, kept small because Voxtral is metered:
  one Kurt (Qwen) and one Phil (Voxtral) segment voiced end to end with a real
  scriptwriter run, with bed, compared with today's rendering. Phil's check confirms
  room tone is inaudible on a clean voice.

## Related operator actions (not part of this change)

- Point Kurt at the un-evened reference: `kurt1_even.wav` (levelled on 2026-10-04,
  before emcee normalized chunks itself) lifts his low-frequency room sound to a
  12 dB speech-to-floor gap; `kurt1.wav` gives 19 dB (21 dB in rendered output), and
  the operator preferred it clearly.
- Add `live,Lyve,` to `~/.emcee/pronunciations.csv`. Plain "live" (as in concert) is
  read as "I live" inside long "Live from the Basement" chunks. Capitalised `Lyve`:
  53/62 right on Qwen (Kurt and Jimmy), 14/14 on Voxtral (Phil, plain "live" 12/14).
  Lowercase `lyve` scored 17/42 on Qwen, so the capital matters.

## Evidence

Throwaway harness and renders: `~/.llama-harness/tts-experiments/` (outside the
repo; `render.py`, `para_test.py`, `bed_test.py`, `noise_test.py`, `d300_test.py`,
`sweep_test.py`, `voxtral_test.py`, `live_test.py`, listening pages under `out/`).
Every comparison was blind or side by side, with and without the bed, judged by the
operator. Two traps found there: macOS filenames are case-insensitive (a `Lyve`
render overwrote `lyve`), and Voxtral's content filter blocks the band name
"Cracker" (`hate_and_discrimination`), which a rephrase cannot work around.
