Plan review (2 x Opus, blind, frozen copy): 0 Critical; 2 Important shared by both (T3 fixture
has no floor-only frames; T2 newline rule unpinned / Mutation B prediction wrong); Minors.
All accepted and applied by the author directly (local edits, no task reshaped -> no second round):
T1 Washington test fails before. T2 wrap-inside-long-sentence test + Mutation B prediction.
T3 fixture with floor-only pauses (>8% of frames) and why; seed-capture test; abs(hash) mutant;
precise edge and odd-length assertions. T4 direct _chunked_pcm/_synthesize_chunked callers get
CHUNKED; fake chunk= kw renamed; Chunking above TTSConfig (eager annotations); SENTENCES helper.
T5 SENTENCES remedy (ceiling 50 was wrong: 42-char texts); _CHUNK_SEP constant (3.11 f-string);
ROOM_TONE_VERSION monkeypatch test + mutation. T6 middle-of-three fallback test (calls + PCM
length); chunked re-blocked twin; bed is constant-level, not silent; Mutation D predicts both
files, Mutation E; mutations run over packages/emcee. T7 insertion point before {{encore_note}}.
T8 root README.md; loudness wording now per chunk; timeout_s; CLAUDE.md "across sentences".
