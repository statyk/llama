### Finding Verdicts
- **Important 1: the runbook `monitor-stalled` grep could not show a dead thread's traceback, and it sent the operator to R2.** ADDRESSED. docs/playout-incident-runbook.md:218 is now `grep -E -A20 'transmitter\.(monitor|relay)|transmitter-monitor'`, exactly the ruling. The format at cli.py:262 (`%(name)s`) puts the logger name on each record's first line, so the `transmitter\.` alternatives match. `-A20` brings in the journald-split traceback frames, and `transmitter-monitor` matches the excepthook line, since the thread is named that at monitor.py:111. The new sentence at runbook:219-224 quotes both messages exactly as the code builds them: `the dead-clock monitor thread is not running` (monitor.py:130) and `the dead-clock monitor has completed no pass for N minutes` (monitor.py:133, `{age/60:.0f}`). It maps the first to a dead thread and the second to a stuck pass. "R2 latency" is widened to "a slow network read (R2, the `live.m3u8` fetch, DNS)" at runbook:224-226. The quoted logger messages all exist: `dead-clock check failed` (monitor.py:84), `alert relay pass failed` (:92) and `dead-clock monitor pass failed` (:101). playout-setup.md:462/464 and CLAUDE.md:273 only describe the trigger, not the grep or the R2 inference, so leaving them unchanged was correct.
- **Minor 1: `doc_problem` rejected an integral float seq that antenna accepts.** ADDRESSED.
  - **Mirror.** `_is_seq` (relay.py:68-72) is `_is_int(v) or (isinstance(v, float) and v.is_integer())`. That matches antenna's `typeof seq === "number" && Number.isInteger(seq)` (antenna/src/alerts.ts:432-443) case by case:
    - bool is rejected, because `_is_int` excludes it and a bool is not a float.
    - NaN and inf are rejected, because `float.is_integer()` is False for both. `JSON.parse` gives `Infinity` for `1e400`, and `Number.isInteger` rejects it, so both sides agree.
    - Non-integral floats, strings, None and a missing seq are rejected.
    - Negative integral floats are accepted on both sides.
  - **Cursor.** The cursor-file reader still uses the strict `_is_int` (relay.py:143), so a hand-edited `seq: 2.0` in the cursor file is still malformed. That is right, because only this module writes that file.
  - **Coercion.** The seq is coerced once, at relay.py:175 (`ring = [{**m, "seq": int(m["seq"])} ...]`), after `doc_problem` returned None, so `int()` cannot raise. Every later use of the seq (the `> start` filter, the sort, `handled`, the log `%d`s, `Cursor(stream, handled)`, `write_json`) reads the coerced copy, so a float cannot reach the cursor file.
  - **Tests.** The `doc_problem` docstring (relay.py:75-80) is updated. test_relay.py:239-242 moves 1.0/2.0/0.0/-3.0 to the accepted side and adds NaN and inf to the rejected side. The new test `test_an_integral_float_seq_is_relayed_and_the_stored_cursor_is_an_int` (test_relay.py:247-255) can fail where it matters. `Cursor("s", 2) == Cursor("s", 2.0)` is True in Python, but the test also asserts `type(r.cursor.seq) is int` and `"2.0" not in text` on the cursor file, so removing the coercion would fail it. It also checks that a second pass re-sends nothing.
- **Minor 4: the strict no-put test did not exercise the relay path.** ADDRESSED. test_monitor.py:131-152 builds a real `relay_mod.Relay(reader.get_json, ...)` over the same `FakeBucket`, with a one-message ring at `RELAY_KEY`, and passes it to `MonitorLoop`. The test asserts three things:
  - the relay actually ran and pushed exactly once over two passes: `ntfy.sent == ["st: T"]`;
  - the bucket saw only `get`;
  - the key set now includes `RELAY_KEY`.

  The guard-cache, sdnotify and `fired` assertions are unchanged. The relay's cursor goes to `tmp_path / "relay-cursor.json"`, not under R2 or the guard cache, so no assertion is weakened.

### New Breakage in the Fix Diff
None.

Nit (no fix required): at docs/playout-incident-runbook.md:226 the widened cause list ends "check R2 latency and status", so the action still names only R2, not the `live.m3u8` fetch or DNS. Each of those has its own section, and this is wording only.

### Out-of-Scope Observations
- service.py:293 sends a third `monitor-stalled` message, `the monitor-stalled check failed: <Type>: <exc>`, when `stalled()` itself raises. The runbook's new "tell the cases apart" sentence names only the two thread-state messages. This is a rare path (it would be a code bug), and its `log.exception` record is under the `transmitter` logger, which the new grep does not match. This was outside the ruling. It could be covered by one more clause if anyone touches the runbook again.

### Verdict
**Fix wave:** All findings addressed, no new Critical/Important breakage. Important 1, Minor 1 and Minor 4 are all ADDRESSED. No tests were run: there was no specific doubt, and each test's ability to fail was established by reading it.
