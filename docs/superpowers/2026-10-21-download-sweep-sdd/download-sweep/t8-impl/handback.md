# t8-impl report
Status: DONE
Edits:
- CLAUDE.md Commands llama bullet: `run list` `running` state; `run resume --all` (eligibility, skips, order, --no-wait default, stop-on-pause, results, exit codes, crash marker, operator loop, no-matching-artists -> complete, refusal messages).
- CLAUDE.md Architecture parallel-safe bullet: run lock paragraph (commands, once at entry, never in _execute, order, inode check, rm through rmtree, readers probe, rollout caveat pre-v2.14, limitations) and download cap paragraph (+ non-FIFO limitation).
- CLAUDE.md pacing paragraph: boundary only if an LLM provider was invoked.
- CLAUDE.md Domain gotchas: two new bullets (download fallback incl. limitations; failure kinds incl. legacy rule).
- README.md session commands: `run resume --all` + running state.
Code vs brief: no disagreements found; refusal messages, skip reasons, results, crash marker, kinds all matched source. Note ia_client treats 416 as a retryable attempt end that discards the .part (next attempt from 0); documented as such.
Test: ./.venv/bin/pytest -q -> 3934 passed, 1 skipped, 8 deselected.
Concerns: none; CLAUDE.md additions are ~100 lines (dense, per the brief's list).
