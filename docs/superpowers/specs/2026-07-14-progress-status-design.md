# Progress Status — Design

**Date:** 2026-07-14
**Status:** Approved design, pending implementation plan
**Extends:** `2026-07-14-llama-design.md` (pipeline stages / CLI)

## Problem

After winnow's mechanical-filter log line, a `llama find` run can be silent
for 10–30+ minutes: up to 40 rate-limited metadata fetches, several batched
review-scoring LLM calls, and up to a dozen sequential web-research LLM calls
(each 1–3 minutes), followed by more multi-minute LLM calls and audio
downloads per show. A user cannot distinguish "working" from "hung", and a
cron log records nothing between stage boundaries.

## Design

### `src/llama/status.py`

One public helper:

```python
@contextmanager
def step(label: str, *, interval_s: float = 15.0):
```

Behavior:

- On entry: `log.info("%s", label)` on the existing `"llama"` logger — this
  is the line cron/piped logs see.
- If `sys.stderr.isatty()`: start a daemon thread that writes a heartbeat
  line to stderr every `interval_s` until the context exits:
  `  … still working: {label} ({elapsed})` where elapsed renders as `45s`,
  `1m30s`, `12m05s`.
- Non-TTY: no thread, no heartbeat — exactly one log line.
- Exit (success or exception): the thread stops promptly (event-based wait,
  not sleep), and the exception propagates unchanged.
- Plain newline-terminated lines only. No `\r` redraws, no new dependencies;
  heartbeats interleave safely with interleaved log output.

### Instrumentation (labels include position/total counts)

- `stages/winnow.py`:
  - review fetch loop: `log.info("winnow: fetching reviews %d/%d", i, n)`
    (one line per fetch; the loop is rate-limited so lines arrive ~2/s max)
  - scoring: each batch call wrapped in
    `step(f"winnow: scoring reviews batch {i}/{n_batches}")`
  - light research: each call wrapped in
    `step(f"winnow: researching {pid} ({i}/{n})")`
- `pipeline.py` `process_show`: each stage call wrapped in a `step` labeled
  `[{performance_id}] selecting recording` / `gathering` / `researching` /
  `synthesizing` / `packaging`. (The select/gather steps are usually fast;
  wrapping them anyway keeps the sequence legible.)
- `stages/package.py`: per-track download log line:
  `log.info("downloading %d/%d: %s", i, n, filename)` (downloads use the
  plain line, not `step` — they emit steadily on their own).

### Out of scope

- rich/spinner rendering, progress bars, percentages
- Any change to stage function signatures (instrumentation is internal)
- Quiet/verbose flags (logging is already INFO-level via the CLI's
  `basicConfig`; revisit only if the lines prove too chatty)

## Testing

- `tests/test_status.py`:
  - non-TTY (monkeypatched `sys.stderr.isatty` → False): exactly one INFO
    log record, no heartbeat output, no thread left running.
  - TTY (monkeypatched → True) with `interval_s=0.05` and a short sleep
    inside the context: at least one heartbeat line captured on stderr;
    after exit, a further wait produces no more output (thread stopped).
  - exception inside the context propagates and still stops the thread.
  - elapsed formatting: `45s`, `1m30s`, `12m05s`.
- Existing winnow test extended with `caplog` assertions for the batch and
  research count lines; package test asserts the download count line.
- Determinism: heartbeat tests use generous assertions (≥1 line) rather than
  exact counts to avoid timing flakes.

## Docs

No README changes needed (output is self-explanatory). CLAUDE.md: no change.
