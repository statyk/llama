APPROVED

Read-only review of e6c0ba33 (HEAD e6c0ba33; no diff under packages/; emcee.__file__ inside worktree; emcee suite 1023 passed, 1 deselected).

(1) Print scope - only on the successful fallback. The detail() call sits after _narrow_chunk returns (audio.py:232-236). A one-piece chunk re-raises `blocked`, a refused sentence raises `located`; both leave the except block before the line runs. Control flow, audio frames and which exceptions propagate are unchanged (one added statement after the assignment).

(2) "extra calls" count - len(takes) is correct. Without the block: 1 call. With it: 1 refused call + N sentence calls, so N extra. Never singular ("1 extra calls" can't happen) because the fallback only runs for >= 2-sentence chunks. The count is speech.synthesize calls; transport retries / mlx quality-layer re-synthesis inside the provider are not counted, which is fine for this purpose.

(3) Bed path and `emcee say` - both reach _chunked_pcm, so the only effect is the printed line. say_cmd writes the MP3 via atomic_write_bytes(dest, ...) (cli.py:735-740), never stdout; the only --stdout is on `config init` and the only --json on `emcee status` (cli.py:950), neither synthesizes. Synthesis is sequential per clip and preceded by the "synthesizing <file>" line (audio.py:472), so "chunk N" is attributable. A rephrase re-render prints it again, which is accurate (the fallback calls are spent again).

(4) Pinning - yes. test_chunked_fallback_is_reported asserts the exact string including chunk number and count (catches deletion, {i} vs {i + 1}, a wrong count). test_chunked_located_block_prints_no_fallback_line uses block="climax" (blocks the chunk then sentence 2 alone, so a located block is raised) and catches moving the print into a finally or before the narrowing. No mutation run; reasoned from assertions vs fixture (PASSAGE = 3 sentences, ceiling 250, one chunk).

(5) Style - matches the existing detail() line in process.py:253 ("content filter blocked a sentence in {seg}{cats}; rephrased"): lowercase, semicolon, split f-string; the comment states why.

Findings:
- Minor - audio.py:235: the line doesn't name the segment, relying on the preceding "synthesizing <file>" line. Fine while synthesis is sequential; if it ever goes concurrent, add the segment stem. No change needed now.

No Critical or Important findings.

(Reviewer: Opus, dispatched by the parent session `emcee`; text transcribed from its returned report.)
