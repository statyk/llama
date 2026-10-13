VERDICT: NEEDS FIXES

### Findings

#### Critical
None.

#### Important

1. **No test checks R16's resolve wiring or the dispatcher install in `transmitter run`. Two non-equivalent mutants both survive.**
   - `service.py:428-432`: `tick` passes `resolves=("plan", "station-root")` and `resolves=("render",)`. Nothing in `tests_transmitter/` calls `resolve`, configures a `Dispatcher` from `test_service.py`, or checks what ends up in alerts.json after a successful step. I removed both `resolves=` tuples in a scratch copy and the full transmitter suite passed: **384 passed**.
   - `cli.py:241`: `alerts.configure(alerts.dispatcher_from_config(cfg, st.ws))` is the only line that turns the feature on in production. With it removed, `test_cli.py`, `test_alerts.py` and `test_service.py` still pass: **47 passed**.
   - Why it matters: R16 is a binding ruling, and these two lines are its only implementation. If the resolves are dropped, a level code stays `active` forever:
     - `status` (Task 16) shows a stale alarm;
     - no "resolved" message is ever sent;
     - a repeat of the condition within `repeat_hours` of the last send is silently deduped instead of sent at once.
   - If the configure line is dropped, hugo never emails or pushes anything. Every test stays green, and nothing would show it until a real outage.
   - Fix: add two tests.
     - In `test_service.py`: install a `Dispatcher` with a `Recorder` channel. Make `plan_step` raise `StationRootError` on tick 1 and succeed on tick 2. Assert that a `resolved: station-root` message was sent and `active()` is `[]`. Do the same for `render`.
     - In `test_cli.py`: monkeypatch `alerts.configure` or `dispatcher_from_config`, then assert that `run --once` installs a dispatcher and clears it afterwards (`configure(None)`).

#### Minor

2. **The ~30 s bound on a down channel holds only for a server that answers quickly** (`alerts.py:85-109`, `153-157`, `166-169`). This is the implementer's concern, weighed as asked.
   - What actually bounds it:
     - `getaddrinfo` has no timeout at all; the resolver's own retries apply.
     - `socket.create_connection` tries each resolved address in turn, each with the full timeout (Python 3.11 has no happy-eyeballs).
     - smtplib applies its 20 s to each socket operation: connect, EHLO, STARTTLS and the handshake, EHLO again, AUTH, MAIL, RCPT, DATA, QUIT.
     - A black-holed or stalled server can therefore hold one `send` for well over a minute.
   - The brief's own `fire()` re-attempts an undelivered message on **every** occurrence, because `last_sent_at is None` bypasses the repeat window. So this part is plan-mandated. The implementer's resolve-retry adds the same cost to every successful plan or render step.
   - Effect on the loop: at most about 4 blocking calls per tick:
     - `plan`, `render`, at most one `publish` (`publish_all` breaks on the first error), `prune`, and `horizon-held` at count 3;
     - or the resolves in their place.
   - With both channels black-holed, a tick stretches from 60 s to roughly 2-4 minutes. Publish slips, and Task 14's "two consecutive checks" dead-clock test slows in proportion.
   - That does not threaten:
     - the air: the lead is hours;
     - the R15 watchdog: 45 min, pinged after every step and batch, with at most about 2 blocking calls between pings.
   - So it is Minor, not Important. A cheap fix that also gives a real bound: a per-channel cool-down. Record when each channel last failed and skip it for about 5 min. That caps blocking at one timeout per channel per cool-down, whatever the DNS or address count.

3. **The dedupe fails open into a storm when alerts.json cannot be written** (`alerts.py:156-159`).
   - `fire()` sends **before** `write_json`. If the write fails, `alert()` swallows the exception as a warning, and the next occurrence sends again.
   - A plausible trigger: hugo's disk fills from rendering, so the user-owned atomic temp write gets ENOSPC.
   - Result: every failing code emails and pushes every tick. ntfy.sh's free tier (about 250 a day) and Gmail's sending limit run out within hours, which locks out the alerts that matter.
   - Fix: keep `last_sent_at`/`count` in memory on the `Dispatcher` too, and use the in-memory value when it is newer than what is on disk.

4. **The corrupt-state test cannot see a swallowed exception** (`test_alerts.py:642-655`).
   - `alert()` and `resolve()` wrap the dispatcher in `except Exception`, so a `TypeError` inside `fire()` passes the "does not raise" part. The only remaining check, `len(rec.sent) >= 4`, is far below the 13 sends that actually happen.
   - Mutant: I removed the `_is_num(last_sent_at)` normalisation, so `"x"` reaches `now - last` and raises inside `fire()`. The test stayed green: **11 passed**.
   - Fix: assert the exact count (13), or that no `"alert dispatch failed"` / `"alert resolve failed"` warning appears in `caplog`.

5. **When a message that failed is finally delivered, it drops its suppressed count** (`alerts.py:155`).
   - While channels are down, `count` keeps rising and `last_sent_at` stays `None`.
   - The eventual delivery takes the `if last and suppressed` branch with `last=None`, so "(N more since the last message)" is left off, even though N occurrences went unreported.
   - Fix: base the note on `suppressed` alone, worded "N more since the first" when nothing has been sent yet.

6. **ntfy title encoding** (`alerts.py:103`). http.client encodes header values as latin-1. A `[antenna] station_name` with a character outside latin-1 (an em dash, say) makes every ntfy send raise `UnicodeEncodeError`, so ntfy is permanently down with only a WARNING. The default is ASCII. Fix: either RFC 2047-encode the title, or restrict `station_name` to ASCII in the config model.

7. **Small test gaps.**
   - `test_ntfy_channel_posts_with_headers` captures `timeout` but never asserts it.
   - `test_channels_carry_a_timeout` only checks `> 0`; the SMTP test does check `20.0`.
   - No test covers a send that only partly succeeds (one channel accepts, one fails → recorded as sent, and the failed channel never gets that message). That behaviour is reasonable but unpinned.

8. **A failed resolve keeps a cleared level code `active`** (the implementer's hardening, `alerts.py:166-169`).
   - It is retried only on the next successful plan or render step, and those run only while filling.
   - So after filling stops, `status` can show a cleared `plan`/`render`/`station-root` code as active for hours.
   - It is a defensible trade against losing the "resolved" message, but it should be noted in the docstring: `status` can lag after a channel outage.

### ⚠️ Cannot verify from diff
- Whether the docs and runbook gained the `[alerts]` keys and the env file's `SMTP_USERNAME`/`SMTP_PASSWORD`/`NTFY_TOKEN`. The Global Constraints require docs for every new key; this task's file list has none, so presumably a later task does it.
- Task 14's dead-clock and guard-stale monitor must call `alerts.resolve("dead-clock"/"guard-stale")`, and must run in the service thread: `Dispatcher` read-modify-writes alerts.json with no lock.
- Task 15's watchdog ping placement relative to the blocking alert calls (finding 2 assumes "after every step and batch", per R15).
- Task 16's `status` must use `active_codes()` with `repeat_hours * 3600`.

### Strengths
- STARTTLS goes through `ssl.create_default_context()` (certificates verified). A server without STARTTLS raises before `login`, so credentials never travel in plaintext.
- No test reaches the network: `smtplib.SMTP` and `urlopen` are monkeypatched, and the `run --once` CLI tests have no `[alerts]`, so there are no channels. Hygiene is clean: only `example.com` addresses and fake tokens, and placeholders in the template.
- Every failure path is contained: per channel in `_send`, around the whole dispatcher in `alert()`/`resolve()`, and a corrupt or non-dict state file starts afresh.
- A message no channel accepted is not recorded as sent, so it is retried.
- The level/event split is centralised in `_expired`/`active_codes` for Task 16 to reuse.
- `_is_num` correctly excludes `bool`.
- The R4 floor sits on `TransmitterConfig` (it spans two sections). It is tested both ways, along with `extra="forbid"` rejecting `smtp_password` in config.
- The `StationRootError` arm sits ahead of the generic arm without disturbing the `FrameCountDrift`/`PublishLocked` handling.
- Python 3.11 compatible: nothing beyond 3.10 syntax.

### Checks run
- **R16 wiring pinned?** Scratch copy via `git archive HEAD packages/transmitter antenna/templates antenna/public`, run from an empty cwd with `PYTHONPATH` set to the scratch `src`. Shadowing proved: `transmitter.__file__` resolved inside the scratch tree. Ran with `PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider`.
  - M1: both `resolves=` tuples set to `()`. Prediction: all green. Result: `384 passed in 55.74s`. **Survived.**
- **Dispatcher install pinned?** M3: the `alerts.configure(dispatcher_from_config(...))` line removed from `cli.run`. Prediction: all green. Result: `test_cli + test_alerts + test_service: 47 passed`. **Survived.**
- **Does the corrupt-state test catch an internal exception?** M4: the `last_sent_at` type normalisation removed. Prediction: `test_a_corrupt_state_file_does_not_wedge_alerting` stays green. Result: `test_alerts.py: 11 passed`. **Survived.** The mutant is not equivalent: `"x"` reaches `now - last`.
- **Blocking per tick:** read `service.py:94-232`. `publish_all` breaks on the first error, and `HeldTracker` alerts only when the count reaches 3. That gives at most about 4 alert/resolve calls per tick.
- **Station-root alert flapping between plan success and render failure in the same tick:** checked `pipeline.py:131,249`. `plan_step` and `render_step` both call `scan_now`, which calls `require_root`, so they agree within a tick. No flap found.
- **Live worktree:** `git status --short` was clean after the work. The scratch copy has been deleted.
