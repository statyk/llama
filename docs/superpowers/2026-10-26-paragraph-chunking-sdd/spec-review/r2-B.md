Foundation: SOUND (R2 informed B, Opus). 6 Minor, no strict-surface regression.
1 (R, from D14) pool exclusion "a few samples": clean-voice quietest frames have 2-4 zero samples at zero crossings; >=2 makes Phil's fill ~10 dB louder (-55 vs -65 as listened). Fix: zero run >= ~1 ms (24 samples @24k), excluded before percentile, empty pool = no-op. Measured: 1 ms leaves Phil exactly as listened, removes 2-5% of Kurt's.
2 step 3 can end a chunk one sentence into a new paragraph (2/74 chunks on harness paragraphs) -> rule or accept.
3 (R, from D1/D2) "more than one sentence" = pieces of _split_sentences(chunk); limit wording = whatever _split_sentences keeps together (merges, abbreviations, step-4 guard).
4 strict base doesn't reject "250"/250.0 -> StrictInt ge=50 le=1000.
5 template test can't see commented keys -> name test_default_config_template_mentions_every_section markers.
6 (R, from D15) fill overlaps ~5 ms under neighbouring speech (harness); edge = run within one crossfade of clip start/end (Qwen starts with dither then zeros at sample 15).
Unverified: Jimmy never listened with room tone (pool -58..-62 offline; offline fill + listen, no spend).
