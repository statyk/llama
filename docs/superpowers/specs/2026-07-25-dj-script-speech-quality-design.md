# DJ script & spoken-text quality pass

**Status:** Approved design
**Date:** 2026-07-25

## Problem

Four TTS-facing defects observed in shipped DJ audio:

1. A literal segue symbol (`Help on the Way > Slipknot!`) reached the script,
   and the TTS read `>` aloud as "greater than."
2. Very short sentences ("Here's set two.") make the backend garble or
   hallucinate.
3. Only the first lead-in states the show's identity. Someone tuning in
   mid-set — or at any later set break — never hears what they're listening
   to.
4. The TTS mispronounces proper nouns (song titles, personnel). Example:
   "Sugaree" (correct: the *sugar* "sh" sound → "Shugaree") and keyboardist
   "Mydland" (pronounced "Midland").

## Guiding realization

The text the TTS **speaks** and the text a human **reads** (`dj-notes.md`)
need not be the same string. Today they are: `package._synthesize_dj_audio`
feeds raw `notes` text straight to `speech.synthesize()`. Inserting one
deterministic `normalize_for_speech(text)` step *only* on the path into the
synthesizer — and folding its output into the cache key — gives a place to fix
symbols (1) and pronunciation (4) **without touching the human-readable
script.** Points 2 and 3 are generation-quality issues fixed in the prompt.

## Scope

In scope: the four fixes above, via prompt edits + a deterministic
spoken-text normalization pass + a curated, user-extensible pronunciation
lexicon.

Explicit non-goals:
- **Bed music** — a separate spec (Spec B: numpy + WAV-only beds).
- **ElevenLabs pronunciation-dictionary API** — its proper phoneme mechanism,
  a future backend-specific enhancement.
- **SSML / inline `<phoneme>`** — neither current backend supports it (Voxtral
  accepts no markup; the ElevenLabs integration does not do SSML phonemes).
- **Phonetic respelling emitted by the scriptwriter LLM** — rejected: it
  depends on the model knowing pronunciations (unreliable) and degrades the
  human script.
- **A show-ID safety guard** — point 3 is prompt-only; an automated check
  would false-flag on artist nicknames ("the Dead" vs "Grateful Dead").
- **Per-backend lexicon columns** — the seed lexicon is tuned for the default
  backend (Voxtral); the backend-specificity caveat is documented, not solved.

## Design

### 1. Prompt edits — `src/llama/prompts/synthesize.md` (points 1, 2, 3)

- **No symbols in prose:** write segues as "into," never `>`; spell out `&`
  as "and," etc. (The normalizer below is the guarantee; this reduces how
  often it must fire.)
- **No very short sentences:** forbid one/two-word sentences; fold short
  punchy fragments into fuller lines. (Also improves the human script.)
- **Show ID in every break:** every lead-in *and* the outro must state
  **artist + date + venue and/or city** at least once — so a listener
  arriving mid-broadcast learns what they are hearing. Today only the first
  lead-in does this; later lead-ins only "recap + tease" and the outro does
  not require it. Rewrite the later-set and outro specs accordingly.

These edits touch the template body only — not the placeholder set, and not
the byte-for-byte `NEUTRAL_STYLE` constant in `synthesize.py` — so existing
prompt/neutral-render tests still pass.

### 2. `normalize_for_speech` — new module `src/llama/speech_text.py`

A pure, deterministic, unit-tested function applied **only** to the text
handed to `speech.synthesize()`:

```
normalize_for_speech(text: str, lexicon: Lexicon) -> str
```

Two ordered stages:

1. **Symbol expansion** (safety net for point 1): a conservative substitution
   table — `>` → " into ", `&` → " and ", `%` → " percent" — then collapse any
   doubled whitespace introduced. Deliberately small: expand only symbols that
   plausibly appear in DJ prose and that the TTS mis-voices. Numerals/years are
   left alone (the backends handle them acceptably).
2. **Pronunciation respelling** (point 4): apply the lexicon with
   word-boundary matching, preserving the source token's capitalization
   pattern where reasonable.

Applied per segment. `dj_notes.json` and `dj-notes.md` are never passed
through it, so the human script keeps "Sugaree" and readable segues.

### 3. Pronunciation lexicon (baked-in + user-extensible)

- **Baked-in seed:** vendored CSV at `src/llama/data/pronunciations.csv`
  (columns `written,spoken,note`), in the same spirit as the vendored
  `set_breaks.csv`. Seeded with known Dead offenders, including:
  - `Sugaree,Shugaree,sugar "sh" sound`
  - `Mydland,Midland,Brent Mydland`
  - plus a handful of other obvious cases.
- **Workspace overlay:** if `<workspace>/pronunciations.csv` (default
  `~/.llama/pronunciations.csv`) exists, its rows are merged **over** the
  baked-in set — workspace entries add new terms and override baked-in ones.
  A missing overlay is normal; a malformed overlay is warned about and
  ignored (never hard-fails packaging).
- Loaded once per package run into a `Lexicon` and passed into
  `normalize_for_speech`.

### 4. Cache integration — `src/llama/stages/package.py`

- Normalize each segment's text **before** computing its hash and before
  synthesis. The cache key becomes
  `sha256(normalized_text + voice + model + chunk)`. Consequences:
  - Existing DJ audio re-renders on `redo --from package` only for segments
    whose normalized text actually changed; unaffected clips stay cached.
  - Editing the lexicon later changes the normalized text of affected
    segments and thus auto-invalidates exactly those clips.
  - Consistent with the project's no-migration / redo ethos.
- **Chunked mode:** normalize the whole segment first, **then** split into
  sentences — so symbol removal cannot confuse the sentence splitter.
  Order becomes: normalize → split → per-sentence synth.

`factual_guard` continues to run on the raw `notes` (mentioned_songs spelled
as show data); it does not interact with the normalizer.

## Testing

- **`normalize_for_speech`:** symbol-expansion cases (`>`, `&`, `%`, doubled
  spaces), respelling with word boundaries and capitalization, idempotence,
  and confirmation that a passed-through string differs from the notes text
  only as expected.
- **Lexicon:** baked-in load; workspace overlay merge (workspace overrides
  baked-in; adds new terms); malformed overlay tolerated with a warning.
- **`package`:** cache key derived from normalized text — an affected segment
  re-renders, an unaffected one is skipped; chunked path normalizes before
  splitting.
- **`test_prompts.py`:** extend keyword assertions to cover the new prompt
  guidance (no-symbol segues, show-ID-every-break).
- Existing prompt/neutral-render and `factual_guard` tests must remain green.

## Error handling

- Malformed/unreadable workspace lexicon → warn and fall back to the baked-in
  set; do not fail the package stage.
- The normalizer is total: any string in, a string out; no exceptions on
  ordinary input.
