# Round 2 decisions (author triage) — final round

Two informed Opus reviews. Foundation: SOUND x2. 0 Critical, 0 Important, 13 Minor (overlapping).
Stop rule: no Critical, 3 new non-self-inflicted L/P items (< 8) -> no round 3. Self-inflicted
share is high (6 of 10 accepted repair round-1 wording), so each fix below is the simplest
precise rule, not a new mechanism. Apply every item; keep the spec's voice.

## Room tone (repairs of round-1 items 14 and 15)

1. (R, 2/2) **Pool exclusion threshold.** Replace "(a few samples or more)" with: a frame is
   left out of the pool when it contains a run of exact zeros of at least 1 ms (24 samples at
   24 kHz). The exclusion is applied first and the ~8% quietest are taken over the frames that
   remain. Reason, one clause: a clean voice's quietest frames have 2-4 zero samples at each
   zero crossing, so a shorter threshold would empty the pool and push the fill up into
   speech-bearing frames (measured: about 10 dB louder on Phil); at 1 ms Phil's pool is
   exactly as listened and 2-5% of Kurt's frames drop out (those next to Qwen's long runs).
   Add "no eligible frames remain" to the no-op cases, and to Acceptance (an empty pool is a
   no-op, never an error).
2. (R, 2/2) **Where the fill sits.** Replace "faded in and out against the neighbouring
   audio. Timing is unchanged: the fill replaces silence sample for sample." with: the tone
   covers the zero run and overlaps the neighbouring audio by the crossfade length on each
   side, fading in and out across that overlap and added to it (as in the harness); the
   clip's length and timing are unchanged. Edges: a run that starts within one crossfade
   length of the clip start, or ends within one of the clip end, is an edge run (Qwen clips
   begin with a few samples of dither before their first zero run); it is filled, fading in
   from zero at the clip start / out to zero at the clip end. Replace the existing Edges
   bullet with this.

## Content-filter path (strict)

3. (L) **Name the new narrowing on the strict list.** Stakes' strict-surface list adds
   section 5's in-chunk narrowing and fallback alongside `_locate_block` and the `rephrase`
   repair. Acceptance adds two process-level tests: (a) the existing chunked repair test
   (`test_chunked_repair_through_process_package`) also asserts the text handed to the
   rephrase task as blocked is the single refused sentence, not the whole chunk; (b) a chunked
   `process_package` run on a fake provider that blocks only a cross-sentence string renders
   through the fallback and the package succeeds.
4. (R) **Define "sentence" once.** In section 5, "a refused chunk of more than one sentence"
   becomes "more than one piece of `_split_sentences(<the chunk's text>)`" (a one-piece chunk
   is re-raised as today, never re-sent). State once, near section 2/4, that "sentence" in
   this spec means a `_split_sentences` unit, which can hold more than one written sentence
   (its short-fragment merge, abbreviations, initials, decimals). Reword the known limit:
   "a trigger spanning text that `_split_sentences` keeps together (its merges, the
   abbreviation rule) or that step 4 joined goes to the repair rather than the fallback".
5. (R) **Acceptance wording vs step 4.** The U.S.-outro test's assertion becomes: no chunk
   exceeds the ceiling except a single splitter unit longer than it, or a step-4 join.

## Script text

6. (P, new) **Double-escaped breaks.** A reply that double-escapes parses to the literal
   two characters backslash-n, which the voice would speak. `write_script` and
   `rephrase_segment` convert any literal `\n` sequence in segment text to a real newline
   before the text is used. One test each (or one shared helper test). Add to section 1.

## Configuration and interfaces

7. (R) `chunk_chars` is a strict integer (`StrictInt`, or `Field(strict=True)`) with bounds
   50-1000: the strict config base forbids unknown keys but does not stop pydantic coercing
   `"250"` or `250.0`. Keep the Acceptance item (a string, a float and out-of-range values are
   load errors).
8. (R) Acceptance's template item names the right test: the `emcee config init` template
   lists `chunk_chars` and `room_tone` (commented, like every `[tts]` key), pinned by adding
   them to `test_default_config_template_mentions_every_section`'s markers
   (`test_default_config_template_matches_defaults` cannot see commented keys).
9. (P/D) **One argument for chunking.** Replace the configuration sentence about passing
   `chunk_chars` and `room_tone` keyword-only with no defaults: chunking on/off and its
   settings (ceiling, room tone) travel together as one required keyword argument from the
   CLI / `process_package` boundary down through `_synthesize_dj_audio`, `render_speech_mp3`
   and the chunked renderer, where "unchunked" is one of its values; no default anywhere, so
   the cache key and the render read the same settings and no caller can silently fall to a
   default path. The exact type is the builder's.

## Documented, not changed

10. (G) Section 2: step 3 can join a long paragraph's short first unit onto the previous
    chunk, so that chunk ends one sentence into the new paragraph (measured 2 of 74 chunks on
    the harness's hand-placed paragraphs). That is the packer the operator listened to and
    chose at 250; accepted, no rule added. One sentence beside the existing "short tail chunk"
    note.
11. Acceptance's operator listening check also notes (no spend): watch the Kurt run's log for
    "quality check failed" retries and the mlx server's memory peak (the 16 GB host is near
    its limit; 250-character requests are longer than sentences), and optionally apply the
    fill offline to an existing Jimmy render and listen (Jimmy was never listened to with
    room tone; his pool measures -58 to -62 dBFS offline).

## Not adopted

- Rebalancing step 3 to keep paragraph starts at chunk starts: the operator chose this packer.
