Foundation: SOUND — the premises the plan relies on hold when checked against the code, httpx 0.28.1 and macOS flock (probes below), and the defects found are in eligibility rules, test pins and edge handling, not in the approach.

- **[Important] A sweep re-spends tokens once per usage window on a paused run that carries an `llm`/`transport` failure**
  - Where: Task 7, `sweep_verdict`: "Eligible: `paused` with `resume_after` past or absent" (spec §6, same rule).
  - Problem: a `paused` marker carries the failures the run had already taken. The failure-kind test applies only to `incomplete` runs, so a paused run with a show that fails the same way every time is eligible. Every sweep resume is a fresh `_execute` over `chosen`, so it retries that show and spends on it again. Inside one `--wait` process this does not happen: after a pause the loop takes `pending = unprocessed`, so failed shows are not retried.
  - Evidence: cli.py:672-678 (`_render_pause(..., failures=failures)` → cli.py:270 `mark_paused(ws, outcome, failures ...)`); cli.py:686 `pending = unprocessed`; spec §6 "Some `transport` failures repeat every time and cost tokens (a 900 s research timeout, retried 3× per pass)".
  - Failure scenario: a 12-show `--auto --wait --max-wait` run loses show 3 to a research timeout (3 × 900 s of Opus `research`, `kind: transport`), then pauses at show 7 past `--max-wait`. After the reset, the sweep resumes it. Show 3 is retried and fails again at full cost, and the run pauses again at show 10. Next window, the same again. The run spends on show 3 once per window until it finishes.
  - Setup and likelihood: the common setup on heavy days (6-10 parallel batches running out the window, `--no-wait` sweep default). Strict surface (LLM spend).
  - Suggested fix: apply the same failure-kind test to `paused` runs. A paused run with any failure whose kind is not `download`/`archive` gets `needs attention`. That adds one condition and one parametrized case.
  - Spec impact: §6 "Eligible" (paused-run rule).

- **[Important] The mutation pin for "never abandon the last non-abandoned candidate" names a test that stays green under that mutant**
  - Where: Task 2 `test_last_non_abandoned_candidate_is_never_abandoned` — "redirect-only item trickling at 100 B/s for a 6,000-byte file → completes (no exception)". Mutation table row "Allow abandoning the last non-abandoned candidate".
  - Problem: the at-most-once rule still holds under the mutant. So the single candidate is abandoned at t≈30 s, keeps its `.part`, and is retried in the repeat phase (deadline not passed: only a 1-4 s sleep elapsed). That retry cannot be abandoned and runs to completion, by Range continuation or a 200 restart. The file completes, and an "it completes" assertion cannot see the extra abandonment. The predicted red is wrong. This is the false-CAUGHT trap the mutation-pin rule exists to prevent.
  - Evidence: Task 2 "May abandon … iff c has not been trickle-abandoned … AND some other candidate d …" plus "A trickle abandonment is a retryable error for c (it stays in the repeat cycle, but can never be abandoned again)". Schedule: the deadline is measured from the end of the first pass.
  - Failure scenario: an implementer drops the "some other d" clause. All Task 2 tests pass if `test_each_candidate_abandoned_at_most_once` does not happen to count the server's requests. The reviewer's mutation run then scores a prediction that never went red.
  - Setup and likelihood: certain, for the pin as written.
  - Suggested fix: make the test assert that the redirect was requested exactly once and no `Range` header was ever sent. Also state in `test_each_candidate_abandoned_at_most_once` that the server got exactly one request. Two assertions.
  - Spec impact: none.

- **[Minor] Trickle abandonment ignores the deadline, so a progressing transfer can be dropped when no further attempt will follow**
  - Where: Task 2 "May abandon c iff … some other candidate d is … untried or its last error was retryable".
  - Problem: in the repeat phase, an attempt that started just before `DOWNLOAD_DEADLINE_S` can be abandoned at the 30 s window after the deadline. The rule allows it whenever any other candidate's last error was retryable, but the schedule then sees the deadline has passed and raises `IADownloadError`, deleting the `.part`. In spec terms this was the last candidate that would get an attempt. A related edge: an abandonment that fires on the final chunk discards a complete file. The next candidate gets `Range: bytes=n-`, then a 416, then a full re-download.
  - Evidence: Task 1 "The deadline is checked before starting an attempt; an attempt in flight finishes"; Task 2 abandonment predicate.
  - Failure scenario: redirect and listed server both return 500 during the first pass and early repeats. At T0+45 the redirect starts trickling at 5 KB/s. At T0+75 it is abandoned because the server's last error was retryable. The deadline has passed, so the download raises, the show fails as `download`, and the next sweep retries it.
  - Setup and likelihood: needs an outage pattern at the 60 s boundary. The worst case is one extra resume pass.
  - Suggested fix: add "and another attempt will actually start (first pass not finished, or deadline not yet passed)" to the predicate. Optionally, never abandon when the bytes held already equal the known `size`. One clause each.
  - Spec impact: none (refines §1 "Terminates").

- **[Minor] Narrowing `except httpx.HTTPError` lets `TooManyRedirects`/`DecodingError` escape and crash the whole run**
  - Where: Task 1 classification: "5xx, 429, 408 and every `httpx.TransportError` … → retryable. Other 4xx → not retryable."
  - Problem: today every `httpx.HTTPError` is caught (ia_client.py:141). `TooManyRedirects` and `DecodingError` are `RequestError`s, not `TransportError`s. The plan classifies neither, so they would escape `download_file` as raw httpx exceptions. `_process` catches only `(TaskFailed, HerderError, IAError)` (cli.py:582), so `_execute` aborts, and every later show in the run is lost with no marker written.
  - Evidence: ia_client.py:141; cli.py:582; httpx exception hierarchy (`TooManyRedirects(RequestError)`, `DecodingError(RequestError)`).
  - Failure scenario: archive.org redirect loop on one item → `get` dies mid-batch.
  - Setup and likelihood: rare.
  - Suggested fix: treat any other `httpx.HTTPError` as a retryable attempt error. One `except` arm.
  - Spec impact: none.

- **[Minor] Task 3's interface has no way to inject the slot pool its own tests need**
  - Where: Task 3 Interfaces "`IAClient.__init__(..., slots_dir: Path | None = None)`" vs tests "`test_slot_released_before_sleep_between_attempts` — a 1-slot `DownloadSlots`" and "`test_slot_wait_does_not_count_toward_deadline` — a `DownloadSlots` stub whose acquire advances the fake clock by 500 s".
  - Problem: a `slots_dir` path always builds an 8-slot pool with unstated clock, sleep and rng. Neither test can be written through the stated interface, so the implementer has to make up an injection point (`slots=` or a private attribute).
  - Evidence: the quoted interface and test lines.
  - Failure scenario: two Sonnet implementers make two different choices. Reviewers then argue about whether a private-attribute monkeypatch is acceptable.
  - Setup and likelihood: certain at implementation time. Cosmetic in effect.
  - Suggested fix: specify `slots: DownloadSlots | None = None` on `IAClient` (with `_setup` building `DownloadSlots(config.root / ".download-slots")`), and say the pool built in production uses real time. One line.
  - Spec impact: none.

- **[Minor] Task 5's test instructions can't be followed through `_drive` as it stands**
  - Where: Task 5 Step 1 "the `process` stub calls `providers["brief"]`'s first rung `.complete("x")`; needs `_drive` to pass providers through".
  - Problem: `_drive` stubs `make_providers` as `collections.defaultdict(lambda: None)`. Every wrapped rung is therefore `None` and there is nothing to call. `_drive` must also hand back ladders of `herder.FakeProvider`, which the plan doesn't say. Separately, skipping the after-read for an LLM-free show shifts the meter-read order. So more tests than the two named break, for example `test_per_show_gate_stops_between_shows`, whose 4th read (the over-ceiling one) becomes before-b, letting `b` run. The plan's "find them by running the file" covers this, but the cause should be stated.
  - Evidence: test_pace_loop.py:84-85; test_pace_loop.py:645-660.
  - Failure scenario: the implementer edits each stub ad hoc, or weakens assertions instead of adding a call.
  - Setup and likelihood: certain at implementation time.
  - Suggested fix: say "`_drive`'s `make_providers` stub returns `defaultdict(lambda: [FakeProvider(completes=[...]*k)])` (or a counting stub). Tests that count meter reads lose the after-read for LLM-free shows." Two sentences.
  - Spec impact: none.

- **[Minor] Permanent download failures are swept every pass forever, and a stale md5 re-downloads the whole file several times each pass**
  - Where: Task 7 eligibility ("incomplete whose every failure is `download` or `archive`"), together with Task 1 ("md5 mismatch → retryable").
  - Problem: a file whose every copy answers 4xx (darked or removed) gives `IADownloadError` (`download`) on every pass. So does a cached md5 that no longer matches any server copy (a re-derived MP3; the cache never expires). The run is eligible every 10 min forever and the sweep exits 1 every pass. For the md5 case, each pass downloads the full file from every candidate plus at least one repeat (a 20 MB file at ~60 KB/s is about 5 min per copy). No LLM spend. The operator's current hand loop already did the same, so this is no worse than the status quo, but it works against Goal 3 (courtesy).
  - Evidence: spec §1 classification; ia_client.py:73-79 (`_cached` never refreshes).
  - Failure scenario: one darked item keeps the loop's exit status at 1 permanently and hides real new failures in the noise.
  - Setup and likelihood: plausible over months of looping.
  - Suggested fix: document it as a limitation in Task 8. Or, cheaply: when the download failed with every candidate non-retryable, or with md5/size mismatches from at least 2 distinct servers, record kind `other` (needs attention).
  - Spec impact: §3/§6 only if the kind rule changes; none if documented.

- **[Minor] The download cap is unfair when more than 8 processes are downloading**
  - Where: Task 3 `acquire`: "Polls … with non-blocking `flock`, in order; if all are held … `sleep(rng.uniform(0.5, 1.0))`".
  - Problem: a holder that finishes a track releases its slot and re-acquires within milliseconds for its next track (`tag_audio`/`read_duration` in between). Waiters poll only every 0.5-1 s, so they almost never see the free slot. A waiter can sit until some holder finishes all of its show's tracks, potentially tens of minutes. This is not a deadlock and total throughput is unchanged, but it touches the spec's "starves" anti-goal.
  - Evidence: stages/package.py:47-58 (back-to-back `download_file` per track).
  - Failure scenario: 10 parallel `get`s all packaging at once; two of them stall at `waiting for a download slot` until another show finishes downloading.
  - Setup and likelihood: the operator's heavy days, during download-heavy phases only.
  - Suggested fix: document it in Task 8 ("FIFO is not guaranteed; a waiter gets a slot when a holder's show finishes"). Do not add a fairness mechanism.
  - Spec impact: none.

- **[Minor] The crash marker and the sweep's error line render poorly**
  - Where: Task 7 "`failure_record(None, exc, kind=KIND_OTHER)`" and "a caught exception → `error: <message>`".
  - Problem: `_print_sessions` prints `failure.get('show', '?')`, which returns `None` for a key that is present with value `None`, so `run list` shows `- None: boom`. `str(typer.Exit(1))` is `'1'`, so an Exit-driven crash prints `error: 1` (the reason went to stderr earlier).
  - Evidence: cli.py:1035; verified `str(typer.Exit(1)) == '1'` on typer 0.27.3.
  - Failure scenario: the operator reads `error: 1` and `None: 1` with no context.
  - Setup and likelihood: whenever a swept run exits non-zero.
  - Suggested fix: render `typer.Exit` as `exit <code>`, and print `-` (or `run`) for a `None` show. Two lines.
  - Spec impact: none.

- **[Minor] Two continuation rules read the spec narrowly without saying so, and Review Focus 3 gives the wrong reason for one of them**
  - Where: Task 2 "any other status → classified as in Task 1, `.part` kept" and "`416` → discard the `.part`, retryable"; Review Focus 3 "must not loop until the deadline".
  - Problem: spec §1 says "any other answer … discards the `.part` and that attempt downloads from byte 0". The plan instead keeps the `.part` on a status error, and on a 416 moves on rather than restarting within the same attempt. Both are reasonable, arguably better, but they deviate and are not flagged as interpretations, so a spec-compliance reviewer may bounce them. The 416 rationale is also wrong: without the 416 rule, a 416 is a non-retryable 4xx with the `.part` kept. Every candidate would then 416 and the file would fail after one pass. It would not loop to the deadline. The rule is warranted for that reason. The other added mechanisms are warranted: rename-then-rmtree makes the spec's own claim ("a lock attempt racing `rm` can't leave a husk") true, since `O_CREAT` inside a dir being rmtree'd recreates `.lock`; `gone` avoids `mark_incomplete` creating a husk via `write_artifact`'s mkdir; and the `running` bool is the only way `status --by-run`, which has no state column, can meet spec §4.
  - Evidence: spec §1 "Continue, don't restart"; workspace.py:27 (`mkdir(parents=True)` in atomic writes).
  - Failure scenario: review churn only.
  - Setup and likelihood: likely, at review.
  - Suggested fix: add one sentence to Task 2 naming both interpretations, and correct Review Focus 3's rationale.
  - Spec impact: none (or a one-line clarification of §1).

### Unverified premises
- Listed servers answer an open-ended `Range: bytes=k-` with `206` and a `Content-Range` starting at `k` for all items. The spec probed only a handful. Cheapest settlement: a live 3-item probe, outside this offline review. Integrity does not depend on it (md5 is whole-file), only efficiency.
- On real sockets at 1-10 KB/s, `iter_bytes()` delivers chunks often enough for a 30 s window to be evaluated promptly. Verified in mock only. Cheapest settlement: an opt-in live test throttled via a local proxy, or accept it as is (low risk).
- Healthy archive.org connections rarely average below 10 KB/s over 30 s. A false switch is cheap thanks to continuation. Cheapest settlement: log abandonments for a week.
- Verified here, no longer open:
  - httpx 0.28.1 keeps the `Range` header and the per-request `timeout` across a 302.
  - `request.extensions["timeout"]` is `{'connect': 10, 'read': 20, ...}`.
  - A generator body streams lazily through `MockTransport`, and an `httpx.ReadError` raised inside it propagates unwrapped.
  - On macOS, a read-only fd's `LOCK_EX|LOCK_NB` probe both detects and takes the lock. Two fds in one process conflict.
  - `O_CREAT` under a missing dir raises `FileNotFoundError`.
  - `typer.Exit` subclasses `Exception` (via `RuntimeError`).
  - All of 3,000 cached metadata files carry `dir` and `workable_servers`; 31 have a `d1` absent from `workable_servers`.
  - Every test double for `cli.IAClient` accepts `**kwargs`, so `slots_dir=` won't break them.

TOTAL: 10 findings (0 Critical, 2 Important, 8 Minor)
