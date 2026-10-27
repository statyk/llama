
## What to look for (strict-surface review)
Review ONLY the two strict surfaces, and report every defect on them, nothing else. Read the
current code paths end to end first (`render_speech_mp3`, `_chunked_pcm`, `_locate_block`,
`SpeechBlocked` and its fields, `process.process_package`'s repair loop, `_repair`,
`rephrase_problems`, `rephrase_segment`, the rephrase prompt, `_synthesize_dj_audio` and its key,
the `rendered` set, `--force`/`--fresh`), then check the design against scenarios such as:
- Content filter: a block on a packed chunk of 1, 2 and N sentences; a chunk whose sentences
  each pass alone (cross-sentence trigger) — does the fallback really avoid it, and what if the
  per-sentence fallback is itself blocked; a block whose trigger is a band/song name a rephrase
  cannot remove ("Cracker"); a block on the narrowing calls themselves; a sentence that
  `_split_sentences` and the packer disagree about (abbreviation rule, newlines, paragraph
  collapse); the rephrased segment's sentence count or paragraph breaks changing, and
  `rephrase_problems` comparing sentence lists after the abbreviation change; how the error
  identifies the segment and sentence back to `_repair`; repeated blocks across MAX_REPHRASES;
  `emcee say` (no repair) and `chunk = false` parity; mlx_audio (which may never block) vs
  Voxtral; bed vs no bed (`fmt` wav vs mp3 in `_locate_block`).
- Cache key: every input that changes the rendered bytes (text incl. paragraph breaks vs the
  collapsed text, chunk_chars, room_tone on/off, room-tone algorithm version, packer version,
  abbreviation-rule change to sentence boundaries, the per-chunk fallback after a block, bed,
  loudness, voice/model, lexicon) — is each in the key, or provably unable to change the
  audio; anything in the key that does not change the audio (needless paid re-renders);
  the unchunked path staying byte-identical in key; the per-chunk fallback producing different
  audio for the same key on a later run (deterministic?); `emcee say` (does it cache?);
  `rendered`/`--force` interaction after a repair; room tone's seed and determinism across
  runs; a mid-run crash leaving a cached clip under a key that would later be reused wrongly.
Anything you find unclear on these surfaces is a finding.
