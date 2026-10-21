Foundation: SOUND — the premises I could check hold: httpx 0.28.1 MockTransport streams generator bodies lazily, chunk by chunk, and a ReadError raised mid-body propagates; `request.extensions["timeout"]` is a dict; flock on macOS conflicts across two fds in the same process, including an O_RDONLY probe fd; the cached metadata carries `dir`/`d1`/`d2`/`workable_servers` and string `size`; `_process` catches only `(TaskFailed, HerderError, IAError)`.

Probes were run in the scratchpad only (`rev-b/probe.py`, `rev-b/fl.py`). One cached `~/.llama/cache/md_*.json` was read, read-only.

## Findings

- **[Important] The Task 2 tests cannot pin the abandonment rules, and the mutation table names a test that a mutant passes**
  - Where: Task 2 Step 1, "`test_slow_but_above_floor_transfer_finishes` — single candidate at 2 × floor" and "`test_last_non_abandoned_candidate_is_never_abandoned` — redirect-only item trickling at 100 B/s". The mutation table says: "Allow abandoning the last non-abandoned candidate | `test_last_non_abandoned_candidate_is_never_abandoned`".
  - Problem: both tests use one candidate. A lone candidate can never be abandoned under the correct rule, and under the mutant it is abandoned once and then completes on its unabandonable retry. So neither test can tell the floor or the "other candidate exists" clause from a mutant.
  - Evidence: the plan's own rule, "may abandon `c` iff `c` has not been trickle-abandoned … AND some other candidate `d` …". Take the mutant that drops the `d` clause but keeps at-most-once. The redirect is abandoned at about 30 s. The repeat pass re-requests it (Range ignored → 200, or 206) and it completes. "completes (no exception)" passes.
  - Failure scenario: a reviewer flips the mutant, the named test stays green, and the reviewer either scores it uncaught and is confused, or scores "any failure" elsewhere as caught. Separately, a floor mutated to 100× passes `test_slow_but_above_floor…`, because nothing could be abandoned anyway.
  - Setup and likelihood: certain. This is the strict-surface termination rule the brief asks about.
  - Suggested fix: give both tests a second candidate. For the slow test, the redirect at 2 × floor plus a healthy server, asserting the server is never requested. For the last-candidate test, redirect trickling, S1 404, S2 trickling, asserting S2 is requested exactly once with no abandonment. Name that test in the mutation table and assert request counts, not just the final body. That is about two tests' worth of edits.
  - Spec impact: none.

- **[Important] Task 1 narrows the retry net to `httpx.TransportError`, so other `httpx.HTTPError`s escape `download_file` and kill the whole run**
  - Where: Task 1, "Classification: 5xx, 429, 408 and every `httpx.TransportError` … → retryable. Other 4xx → not retryable."
  - Problem: today `download_file` catches every `httpx.HTTPError` and ends in `IAError`. The plan names only status codes and `TransportError`. `httpx.TooManyRedirects` and `httpx.DecodingError` are `RequestError`s, not `TransportError`s (probe: `issubclass(..., TransportError)` is `False` for both). An implementer following the text lets them propagate.
  - Evidence: `ia_client.py:141` (`except httpx.HTTPError`); `cli.py` `_process` catches only `(TaskFailed, HerderError, IAError)`. Probe output: `False False True` for TooManyRedirects, DecodingError, RemoteProtocolError.
  - Failure scenario: an archive.org redirect loop on one file raises `TooManyRedirects` out of `process_show`. That exits `_execute` uncaught, the run's remaining shows are never processed, and a stray `.part` is left (the next call cleans it up). Under the sweep, the run gets a crash marker and needs a human.
  - Setup and likelihood: rare on archive.org, but it is a regression against current behaviour, and the fix is one clause.
  - Suggested fix: add "any other `httpx.HTTPError` → this candidate fails (retryable; never escapes `download_file`)" to the Task 1 classification, plus one test whose handler raises `httpx.TooManyRedirects`.
  - Spec impact: none. Spec §1 says transport errors are retryable but does not license escaping.

- **[Minor] A trickle abandonment near or after the 60 s deadline turns a transfer that would have finished into a failure**
  - Where: Task 2, "May abandon … iff … some other candidate `d` is neither trickle-abandoned nor known non-retryable (i.e. `d` is untried or its last error was retryable)."
  - Problem: in the repeat phase, a `d` whose last error was retryable counts even when the deadline has passed or will pass during `d`'s attempt. After the abandonment the schedule checks the deadline, raises `IADownloadError` and deletes the `.part`. The abandoned candidate never gets the continuation attempt that the "never abandoned twice" rule was meant to give it.
  - Evidence: Task 1 says the deadline "is checked before starting an attempt" and "Exhausted … delete any `.part`". Spec §1: the last candidate's "transfer finishes however slow".
  - Failure scenario: candidates [R, S1]. First pass: R 500, S1 500. Repeat pass: S1 starts at +40 s and trickles at 5 KB/s. It is abandoned at about +70 s because R is "retryable". The deadline has passed, so the file fails and the bytes are discarded.
  - Setup and likelihood: needs a trickling server plus a 500ing one, and the probes measured no trickling servers. Worst case is one failed show and an extra sweep pass.
  - Suggested fix: allow an abandonment only while the deadline has not passed, and exempt the abandoned candidate's single continuation attempt from the deadline. That is one clause and one test.
  - Spec impact: clarifies §1 "Terminates" and "Schedule". No decision changes.

- **[Minor] Gaps in continuation integrity when there is neither md5 nor size, or when the copies disagree**
  - Where: Task 2, "`206` with `Content-Range` starting `bytes <offset>-` → append". Task 1, "Neither → rename as today."
  - Problem: there are three gaps on the strict surface:
    - A file with neither md5 nor size can be stitched from two servers with no verification at all. Today such a file always comes from a single source.
    - The total in `Content-Range` (`/n`) is never compared with the earlier response's length or with the metadata `size`. With size-only verification, a prefix from a copy of a different length followed by a suffix from a copy whose length matches the metadata passes the size check.
    - A 206 to a request sent without Range is not excluded from "success".
  - Evidence: spec §1 says 4 of 531k entries lack md5; size is present on every cached entry. The integrity strict surface says "from any server".
  - Failure scenario: an entry with no md5, metadata `size` = n2, and redirect copy length n1 ≠ n2. R trickles to k and S1 serves `bytes k-(n2-1)/n2`. The stitched length is n2, so the size check passes and a franken-file is renamed into place.
  - Setup and likelihood: vanishingly rare, given md5 is almost always present.
  - Suggested fix: do not use Range continuation unless an md5 is known, or require the `Content-Range` total to equal the metadata `size`. Accept a 206 only for a ranged request. That is about three lines.
  - Spec impact: none, or a one-line note in §1.

- **[Minor] Unspecified details of the continuation mechanics, and the test's `k` is ambiguous**
  - Where: Task 2, "At each chunk arrival at time `t` …" and "the server saw exactly `bytes=<k>-` where `k` is the redirect's byte count at abandonment".
  - Problem: the plan does not say four things:
    - Whether the triggering chunk is written before the trickle check. That changes `k` by one chunk, and the implementer and test writer must agree on it.
    - Whether an abandonment on a chunk that completes the body is suppressed. If not, the next candidate answers `416` and a complete file is discarded.
    - Whether `offset` is derived from the `.part`'s on-disk size. "200 → truncate" followed by a stream that dies before the first byte leaves an empty `.part`; a counter would carry a stale offset.
    - Whether the monitor restarts on the re-issued no-Range request.
  - Evidence: plan text as quoted.
  - Failure scenario: the test is written to one convention and the implementation follows the other, so it is red or flaky. Or the last chunk is wasted: `416` → restart from 0.
  - Setup and likelihood: the first and third are likely to come up as an implementer question. The second needs a trickle on the very last chunk.
  - Suggested fix: add one sentence each: write the chunk, then check; never abandon once `total` equals the expected length; `offset = tmp.stat().st_size`.
  - Spec impact: none.

- **[Minor] The Task 3 interface gives the tests no way to inject a stub or a 1-slot pool, and the slot-wait accounting is ambiguous**
  - Where: Task 3, "`IAClient.__init__(..., slots_dir: Path | None = None)`", and the tests "a 1-slot `DownloadSlots`" and "a `DownloadSlots` stub whose acquire advances the fake clock".
  - Problem: three gaps:
    - The only constructor input is a directory, and `n` defaults to 8, so neither test can be written without inventing an injection point.
    - "the yielded wait seconds are subtracted from the deadline accounting" does not say that only waits after the first pass count. Subtracting first-pass waits too stretches the deadline.
    - The wait is measured on `DownloadSlots`' clock but subtracted from `IAClient`'s, and nothing says they must be the same object.
  - Evidence: plan text. The deadline is "measured … from the end of the first pass".
  - Failure scenario: an implementer adds an ad-hoc `ia._slots = …` monkeypatch. Or a long first-pass slot wait lets the repeat phase run past 60 s of attempts.
  - Setup and likelihood: certain to surface as an implementer question.
  - Suggested fix: make it `IAClient(..., slots: DownloadSlots | None = None)` (with `_setup` building it with the client's clock, sleep and RNG), and say "only waits after the first pass ends are subtracted".
  - Spec impact: none.

- **[Minor] A fresh `get`'s blocking lock can be granted on an unlinked inode, and the spec's claim that the window cannot produce two workers is false**
  - Where: Task 6, "`claim_run_dir`'s fresh dir → `run_lock(blocking=True)`" and "`run rm`: … rename `runs/<id>` to `runs/.removing-<id>-<pid>` and `rmtree` that". Spec §4: "Neither can produce two workers."
  - Problem: the sequence is:
    1. `get` creates the dir.
    2. `run rm` takes the lock first.
    3. `get` opens the same `.lock` and blocks.
    4. `rm` renames and deletes the dir, then exits.
    5. `get` wakes holding a lock on a deleted inode.
    6. `get`'s `write_artifact(ws.request)` recreates `runs/<id>/` (via mkdir of parents) with no `.lock`.
    7. The run now has `request.json` and no marker, so `run_is_live` reports it not live. The sweep finds it eligible and its helper's O_CREAT lock succeeds on a new inode, giving two workers.
  - Evidence: probe `fl.py`: "new inode acquired while old held -> two holders". `workspace.claim_run_dir`; `write_artifact` creates parents.
  - Failure scenario: as above.
  - Setup and likelihood: the operator must `run rm` a run within milliseconds of its creation. Practically never happens.
  - Suggested fix: after any blocking acquire, check `os.fstat(fd).st_ino == os.stat(run_dir/".lock").st_ino` (else `RunMissing`). Or record this as a documented limitation and correct the spec's sentence. The check is about four lines.
  - Spec impact: §4 "Known remaining windows", whose claim is wrong as written.

- **[Minor] `get --name` decides "created vs existed" with a check-then-create race**
  - Where: Task 6, "`--name`: record whether `runs/<name>` already existed; create it `exist_ok`; existed → `_run_locked` …, created → blocking."
  - Problem: two simultaneous `get --name X` both see the directory as absent, both "create" it, and both lock blocking. The second waits, then re-runs the first's run and overwrites its `request.json`.
  - Evidence: plan text.
  - Failure scenario: two shells start `get --name X` at once. The workers are serialized, not concurrent, but the second clobbers the first's run.
  - Setup and likelihood: rare; `--name` is mostly used in tests.
  - Suggested fix: decide with `mkdir(exist_ok=False)` and treat `FileExistsError` as "existed". No extra lines.
  - Spec impact: none.

- **[Minor] An md5 mismatch from every copy (stale cached md5) costs a full transfer per candidate on every sweep pass, forever**
  - Where: Task 1, "md5 mismatch → retryable, `.part` deleted"; Task 7 eligibility (`download` is eligible).
  - Problem: if archive.org re-derived an item, every copy fails the cached md5. The first pass downloads the whole file from every candidate, never cut short, then one more transfer starts before the deadline. That is about (candidates + 1) × ~300 s per file per pass, against Goal 2's "about a minute". The sweep repeats it every 10 minutes. Today the same file costs one transfer per resume, because a mismatch raises at once.
  - Evidence: `ia_client.py:136-138` (a mismatch is an `IAError`, not retried); spec §1 and Non-goals (no metadata refresh).
  - Failure scenario: a stale-md5 file on a 3-server item takes about 20 minutes of archive.org bandwidth per sweep pass, indefinitely, while the run sits on the list as `download`.
  - Setup and likelihood: unmeasured. It depends on how often derivatives change under a months-old cache.
  - Suggested fix: on a mismatch, move on, but drop that candidate from the repeat cycle (each copy is checked once). That is one line.
  - Spec impact: §1 Classification ("md5 mismatch: counts as retryable").

- **[Minor] The "never abandon the last candidate" rule has no lower bound**
  - Where: Task 2, "Otherwise the transfer runs to completion however slow, as long as it is not stalled."
  - Problem: a server that sends one byte every 19 s defeats the 20 s stall timeout. As the last non-abandoned candidate, it holds a download slot, the show lock and the run indefinitely, with no output. That conflicts with the spec's anti-goal "A run that silently waits a long time on one stubborn file".
  - Evidence: spec §1 "Terminates" and Anti-goals, bullet 1.
  - Failure scenario: a sick server dribbles bytes. One of the 8 slots, and one batch process, are gone for hours or days.
  - Setup and likelihood: no such server has been observed.
  - Suggested fix: add a hard floor (e.g. 1 KB/s over the window) that abandons even the last candidate, or record this as a documented limitation.
  - Spec impact: §1 "Terminates".

- **[Minor] The sweep resumes an interactive `get` that the operator aborted at a prompt, with `--auto`**
  - Where: Task 7, `sweep_verdict` eligibility, "`incomplete` with no failures".
  - Problem: an interactive `llama get "q"` interrupted with Ctrl-C at "Process which ranks?" leaves `request.json` (`"auto": false`) and no marker. The next sweep processes the top picks automatically and spends LLM tokens on shows the operator stopped choosing.
  - Evidence: `cli.py` `_get_query` writes `request.json` with `auto`; the `_execute` prompts at the artist-prune and process-ranks points.
  - Failure scenario: as above, with one unwanted batch of spend.
  - Setup and likelihood: occasional, whenever the operator uses interactive `get` while looping the sweep.
  - Suggested fix: classify "no marker and `request.auto` is false" as `needs attention`. That is one clause and one test case.
  - Spec impact: §6 Eligible.

- **[Minor] The crash marker records an empty error for `typer.Exit`, and `show: None` prints as "None"**
  - Where: Task 7, "`mark_incomplete(ws, outcome=None, failures=[failure_record(None, exc, kind=KIND_OTHER)])`", and "any `Exception` (including `typer.Exit` with a non-zero code)".
  - Problem: `str(typer.Exit(1))` is `""`, so the marker and the summary say `error: ` with no reason (the reason went to stderr earlier). `_print_sessions` then renders `- None: `.
  - Evidence: `cli.py` `_print_sessions` uses `failure.get('show', '?')`; click's `Exit` carries only a code.
  - Failure scenario: `run list` shows a needs-attention run with no explanation.
  - Setup and likelihood: whenever the resume path exits 1, e.g. "no criteria.json" or a non-query re-interpret.
  - Suggested fix: use the error text `exit <code>` when the message is empty, and print `(run)` for a `None` show. Two lines.
  - Spec impact: none.

- **[Minor] Task 5's stub cannot "make one provider call" through `_drive`'s provider map**
  - Where: Task 5 Step 1, "the `process` stub calls `providers["brief"]`'s first rung `.complete("x")` … Existing boundary tests … are updated so their stub makes one provider call".
  - Problem: `_drive` stubs `make_providers` as `defaultdict(lambda: None)`, so `providers["brief"]` is `None` before and after wrapping. The plan does not say that `_drive` must serve a fake ladder (e.g. `FakeProvider`) for this.
  - Evidence: `tests/test_pace_loop.py:84-85`.
  - Failure scenario: an implementer hits `TypeError: 'NoneType'` and invents a fix.
  - Setup and likelihood: certain.
  - Suggested fix: say that `_drive` gains a `providers=` hook, defaulting to `defaultdict` of a one-rung `FakeProvider` ladder.
  - Spec impact: none.

- **[Minor] Slot polling favours whoever just released a slot**
  - Where: Task 3, "Polls `dir/0.lock .. dir/{n-1}.lock` with non-blocking `flock` … `sleep(rng.uniform(0.5, 1.0))`".
  - Problem: a holder that finishes one file re-polls for its next file within milliseconds, while waiters are mid-sleep. With 9-10 batches, the extra processes catch a free slot only on a fraction of releases, so their downloads lag behind.
  - Evidence: `package.py` downloads sequentially, with only tagging between files.
  - Failure scenario: on 10-batch days, two batches run noticeably slower than the rest. There is no deadlock.
  - Setup and likelihood: only with 9 or more downloading processes at once.
  - Suggested fix: record this as a documented limitation, or have a releaser that just finished a file give up its first poll (sleep once). One line.
  - Spec impact: none.

- **[Minor] Fidelity of the added mechanisms: three are warranted, and the 416 rule diverges**
  - Where: Review Focus 3–5; Task 6 (`running` bool on `--by-run`, rename-then-rmtree); Task 7 (`gone`).
  - Problem: my verdicts:
    - Rename-then-rmtree is warranted. Without it, a resume that lands after `rmtree` unlinks `.lock` O_CREATs a fresh inode, gets the lock, and makes `rmdir` fail.
    - `gone` is warranted. Without it, `RunMissing` would be caught as a crash, and `mark_incomplete` → `write_artifact` would recreate a husk.
    - The `running` bool is a reasonable reading of "report as running" for a rollup that has no state column.
    - The 416 rule differs from the spec. The spec says any non-matching answer means "that attempt downloads from byte 0", but the plan moves on to the next candidate for 416 while restarting in the same attempt for a mismatched 206. That is harmless but inconsistent.
    - Minor cost: a failed `rmtree` leaves a `.removing-*` directory that nothing lists or cleans up.
  - Evidence: spec §1 "any other answer … discards the `.part` and that attempt downloads from byte 0"; probe `fl.py`.
  - Failure scenario: none of consequence.
  - Setup and likelihood: n/a.
  - Suggested fix: either re-issue without Range in the same attempt for 416 too, or say in the plan why 416 differs. Optionally have `run rm` mention leftover `.removing-*` directories.
  - Spec impact: none.

### Unverified premises
- **Listed servers answer `Range` with a 206 whose `Content-Range` is correct.** The spec's probes say 206, but I cannot check it offline. Cheapest test: one live ranged GET per server family, inspecting `Content-Range`.
- **Range offsets assume identity encoding.** httpx sends `Accept-Encoding: gzip, deflate` by default (probe), and `iter_bytes` decodes. If any server gzips an mp3, the offsets are in the wrong space; md5/size still guard integrity. Cheapest test: one live probe for `Content-Encoding`, or send `Accept-Encoding: identity` on downloads.
- **How often cached md5s go stale** (this drives the md5-mismatch finding above). Cheapest test: compare md5s in a sample of `md_*.json` cache files with live metadata.
- **Whether trickling servers exist at all.** The measurements found only 500s and roughly 60 KB/s connections. No test needed: the switch is insurance.
- **The run-lock fd is not inherited by `claude -p` or ffmpeg children.** Python's `os.open` fds are non-inheritable by default (PEP 446), so an orphaned child cannot fake liveness. None needed.

TOTAL: 15 findings (0 Critical, 2 Important, 13 Minor)
