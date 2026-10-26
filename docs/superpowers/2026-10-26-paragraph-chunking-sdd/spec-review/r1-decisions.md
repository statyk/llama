# Round 1 decisions (author triage)

Four Opus reviews (2 breadth, 2 strict). Foundation: SOUND x4. 1 Important, 37 Minor (with
heavy overlap). Classes: L = strict surface, P = proportionate, D = simplification,
G = generic rigour (rejected or documented). Apply every item; keep the spec's voice (what and
why, no review/round labels, no history).

## Content-filter path (strict)

1. (L, 4/4) **Narrowing and fallback live per chunk, inside the chunk loop, and the
   fallback reuses the narrowing takes.** Rewrite section 5 so that: when a chunk of more
   than one sentence is refused, the chunked renderer (the per-chunk loop in `_chunked_pcm`)
   synthesizes each piece of `_split_sentences(<that chunk's text>)` alone as WAV (the format
   of the refused call), **keeping** the audio. The first refused piece is raised as an
   ordinary located `SpeechBlocked` for that sentence (`whole_passage` false), exactly what
   the `rephrase` repair handles today. If every piece passes, those takes, each
   loudness-normalized and joined with the usual 180 ms, ARE that chunk's render: no second
   synthesis, so the fallback costs nothing extra and does not depend on the filter giving
   the same verdict twice. Chunks before and after keep their packing and are not
   re-synthesized. `render_speech_mp3`'s chunked re-raise stays as is. A one-sentence chunk
   behaves exactly as today. Remove the phrase "today's chunking" from (b) (ambiguous: the
   segment-level split can cross chunk and paragraph boundaries). Because no new call is made
   after narrowing, there is no "blocked during fallback" case; say so in one clause.
2. (P) Documented limitations, one line each in section 5:
   - When `[tts.verify]` covers the backend, the narrowing takes are verified like any take
     (they are now kept, so this is meaningful); a quality failure there fails the package as
     any quality failure does.
   - The abbreviation rule (section 4) can make a two-sentence chunk count as one sentence; a
     trigger that exists only across that boundary then goes to the repair rather than the
     fallback. Rare and acceptable.
   - A block caused by a name the repair must keep (Voxtral blocks the band name "Cracker")
     stays unrepairable, as today; not a regression.
3. (D) **Drop the "rephrase repair keeps paragraph breaks" mechanism.** Remove the Settled
   bullet "The rephrase repair keeps a segment's paragraph breaks where it can..." and the
   Left-to-the-builder bullet "How the rephrase repair keeps paragraph breaks...". Replace
   with one line in section 1 (or section 5): `prompts/rephrase.md` asks the model to keep
   blank lines between paragraphs (as escaped `\n\n`, see item 9); no code re-inserts breaks,
   and a repaired segment that loses them simply packs as plain text. Reason: any
   re-insertion edits text around the repair's checks on the strict path, for little gain.

## Cache key (strict)

4. (L, 4/4) **Key on the planned chunks, not a hand-bumped version.** Replace section 6's
   `chunker=para-v1:250` with: on the chunked path the key carries a digest of the planned
   chunk texts (the packer's output for this spoken text and ceiling, joined with a separator
   that cannot occur in text), so the ceiling, the packer and the sentence splitter and its
   constants are all covered exactly with no version to remember. Room tone: when
   `room_tone` is on, the key carries `tone=<ROOM_TONE_VERSION>`, a named module constant
   like `LOUDNESS_VERSION`, whose comment says that any change to the fill's output (its
   constants or algorithm) bumps it. The existing `chunk=` and `loud=` parts stay. The
   unchunked path's key is unchanged. The per-chunk fallback (item 1) is a function of the
   provider's verdicts, not of the key; that is fine because blocks are rare and the next
   repair round changes the text.
5. (P) `chunk_chars` and `room_tone` are passed keyword-only with **no defaults** below the
   CLI / `process_package` boundary (into `_synthesize_dj_audio`, `render_speech_mp3`, the
   chunked renderer and the key), so the key and the render always read the same value (the
   house idiom, as `speech_provider_for`).
6. (D, 3 reviewers) **Correct the Stakes paragraph.** `process_package` writes a new script
   on every voicing (`write_script` every call), so with a real LLM every clip re-renders on
   every voicing whatever the key says. This change therefore adds no re-render spend, and in
   practice the key matters within one call (repair rounds, `rendered`, `--force`). Keep
   "must change whenever the rendered audio would change" as the strict rule; demote "must
   not change otherwise" to a preference (it buys nothing given re-scripting). Remove the
   paid-re-render cost claim for key changes from Stakes (paid TTS still matters for block
   narrowing and for the chunk size itself).

## Packing and splitting

7. (P, 2 reviewers incl. the one Important) **Minimum-fragment guard survives packing.** In
   section 2 add: after packing, a unit shorter than `_MIN_FRAGMENT_LEN` (20 characters) is
   joined to its previous unit (or the next, if it is first), even if that exceeds `C`, for
   the same reason the splitter does it today: a tiny context-free fragment makes a backend
   hallucinate. One rule, one test.
8. (P) **Abbreviation re-join runs before the short-fragment merge.** In section 4: the
   dotted-abbreviation rule is applied to the raw split parts as a pre-pass, before
   `_split_sentences`' existing short-fragment merge; otherwise "The encore was U.S." (19
   characters) merges backward and the rule then glues the next sentence forward, giving a
   ~500-character unit (measured: the gratefuldead-1974-05-19 outro; 5 of 593 delivered
   segments). Test with that outro's text, no paragraph break, and assert no unit exceeds the
   ceiling except a single sentence longer than it.
9. (P) **Paragraph rule wording.** Section 2 step 1: "two or more newlines, with only
   whitespace between them, count as one break"; a single newline collapses to a space.
10. (P, 2 reviewers) **Prompt wording.** Section 1: the paragraph break is written as the JSON
    escape `\n\n` inside the string, never a raw line break (raw control characters are
    invalid JSON and herder's `model_validate_json` rejects them, costing a high-tier retry).
    Acceptance gains: a fake-LLM test that a reply with escaped `\n\n` round-trips to real
    newlines in `ScriptNotes`, and the real-scriptwriter acceptance run checks the notes
    contain paragraph breaks and the log shows no invalid-JSON retries.
11. (P) **Unchunked collapse location.** Settled bullet on `chunk = false`: whitespace is
    collapsed once at the start of `render_speech_mp3`'s unchunked branch, before both the
    provider call and `_locate_block`, so narrowing probes and error text match what was
    sent. Documented limitation: the unchunked key is unchanged, so a cached unchunked clip
    whose text had a newline would not re-render; harmless because no existing segment
    contains a newline (593/593 checked) and every voicing re-scripts.
12. (G, documented) Section 2: plain greedy packing of a long paragraph can leave a short
    tail chunk; that is what was listened to and chosen at 250; no minimum-size rebalancing
    (the earlier MIN=150 variant was dropped). One line so a builder does not add it back.
    (Item 7's 20-character guard is separate and stays.)

## Room tone

13. (P, 4/4) Seed: an integer derived from sha256 of the spoken text (never Python's
    `hash()`, which is salted per process). Determinism is a test property; cache reuse
    stores bytes and does not depend on it.
14. (P) Pool: frames containing an exact-zero run (a few samples or more) are excluded from
    the quiet-frame pool, not just all-zero frames, so the fill itself carries no dropouts.
    (Small departure from the harness; the listening check covers it.)
15. (P) Edges: a zero run at the very start or end of the segment has a neighbour on one side
    only; it is filled, faded in from zero at the clip start and out to zero at the clip end
    (over the crossfade length), so a no-bed clip does not end on a step.
16. (P) No-op wording in section 3: the fill is a no-op when the segment has no non-silent
    frames to draw from (e.g. the `fake` provider) or no qualifying zero run. Remove "a
    provider that never emits exact zeros" (contradicted by the Voxtral paragraph: emcee's own
    joins are zero runs).
17. (P) Mono only: the fill runs on mono PCM and is skipped when channels != 1 (no current
    provider returns stereo).

## Configuration and docs

18. (P) `chunk_chars` bounds, stated in the spec (remove the vague Left-to-builder bullet):
    an integer from 50 to 1000 under the strict config base. Below 50 nothing is gained (a
    sentence longer than `C` is its own unit, so tiny values degrade to one sentence per
    chunk); 1000 keeps every chunk well under Voxtral's 2000-character input guard. Values
    above ~400 were not listened to.
19. (P) Acceptance also lists the doc and template updates: the `emcee config init` template
    (pinned by `test_default_config_template_matches_defaults`) gains both keys with
    comments; the config comments, `--chunk` help text, `quality.py` docstring and any other
    "sentence-by-sentence" wording are updated; README runbook and the CLAUDE.md emcee bullet
    describe paragraph packing and room tone.

## Premises (write results into the spec)

20. Add to Evidence (or a short "Checked" list): the mlx-audio server does not override
    Qwen3-TTS's default `split_pattern="\n"` (checked in the installed server); all 593
    delivered segments contain no newline; the U.S. split reproduces on the 1974-05-19 outro.
    The "~150 ms" leading-zero figure becomes "0.04-0.58 s measured" (design does not depend
    on it).
21. Related operator actions: `live,Lyve,` is already in the overlay (done). Add one caveat:
    the lexicon matches whole words case-insensitively, so the bare entry also respells the
    verb ("what I live for"); a phrase entry (e.g. `Live from the Basement`) is the narrower
    alternative, the operator's call.

## Rejected

- Reusing the narrowing takes with neighbour context fields (ElevenLabs prosody): not
  specified; builder's call.
- A separate premise reviewer / extra mechanisms for non-deterministic Voxtral blocks:
  item 1 removes the dependence.
