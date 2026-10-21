# Download fallback, archive.org courtesy, and the run sweep

Status: draft for review, 2026-10-21. Target release: v2.14.0.

## Why

The operator starts large unattended `llama get` batches and walks away: `~/.local/bin/getllama.sh` runs
`llama get --profile <p> --auto --wait` for every profile in sequence, and on heavy days 6-10 copies run in
parallel. Afterwards there are always a few `incomplete` runs whose failures are audio downloads that got
an HTTP 500 (`download of X failed after 3 attempts: Server error '500 …'`). The operator cleans up with a
hand loop:

```sh
while true; do for r in $(llama run list --no-flags | grep [[:digit:]]h | awk '{print $1}'); do
  date; llama run resume $r; done; echo ==========; sleep 600; date; done
```

The `grep [[:digit:]]h` (sessions idle for an hour or more) is a guess at "not currently running", because
nothing records whether a run is live.

**The cause, measured 2026-10-21.** These failures are not short blips. `archive.org/download/<id>/<file>`
redirects to one of several servers holding the item, and some of those copies are broken: specific
files on the `dn7203xx.ca.archive.org` servers return 500 every time, for days. Two runs had been failing
on the same file since 10-09 and 10-17, through the operator's resume loop. Probes of the four failing
files:
- **Persistent 500.** Three of them got 3/3 500s through the redirect (furthur2010-07-05set2t06,
  ymsb2007-02-21d2t07, and the mmj file timed out).
- **Lucky redirect.** The fourth (zt2005-09-04D1T01) got a 500 when the redirect chose `dn720308`, and 206
  when it chose `ia800903`.
- **The fix is in the metadata.** Every item's metadata lists its servers (`workable_servers`, `d1`, `d2`,
  plus `dir`). For all three stuck files, a direct request to either listed server (`ia800903`,
  `ia600903`) returned 206.
- **And the copy is good.** A full GET of furthur2010-07-05set2t06.mp3 from `ia600903` matched the
  cached md5 and size (20,032,077 bytes). It took 305 s, so slow listed servers are normal.
- **Speed is capped per connection, not per server.** 2 MB range probes of three items ran at 49-93 KB/s
  from every server. Three parallel connections to one server each got ~60-75 KB/s, while a Cloudflare
  download on the same machine ran at ~35 MB/s. So archive.org throttles each connection to roughly
  50-100 KB/s; switching between healthy servers gains nothing, but a server far below that rate is broken.

The operator's loop only "worked" when the redirect happened to land on a healthy copy. Retrying the same
URL harder or longer does not fix a broken copy; asking a healthy copy does.

`IAClient.download_file` (`packages/llama/src/llama/ia_client.py`) today tries only the redirect URL:
3 attempts with 1 s and 2 s sleeps, retrying every `httpx.HTTPError`.

## Goals

1. **Stop failing on broken copies.** When the redirect URL fails, fetch the file from the item's other
   listed servers.
2. **Bounded extra time.** A failing file adds about a minute (more only if its servers hang), so a run's
   added time is about a minute per failing show.
3. **Courtesy to archive.org.** Parallel llama processes must not pile simultaneous downloads onto
   archive.org.
4. **A clean cleanup command.** One command replaces the hand loop. It does one pass and exits; the
   operator loops it in the shell if they want.
5. **Know when a run is live**, for certain rather than by age.
6. **Don't teach the pacing gate wrong costs.** A resume or sweep must not drag the learned per-show cost
   toward zero.

## Non-goals

- Parallel processing of shows within one run. Raised by the operator and deferred to its own pass,
  because it interacts with usage pacing.
- Retry or fallback changes for the metadata/search API (`IAClient._get`). Only audio downloads.
- A built-in sweep loop or daemon. The command does one pass.
- Resuming `awaiting-approval` runs. They need a human decision.
- Refreshing stale cached metadata to discover new servers. The fallback uses the cached server list. If
  every listed server also fails, the file fails, as today.

## Anti-goals (failure even if it "works")

- A run that silently waits a long time on one stubborn file.
- Two workers on one run because the sweep or a manual resume mistook a live run for a dead one.
- A download cap that deadlocks or starves; a crashed process must never hold a slot.
- Any weakening of download integrity. The md5 check (or, for a file with no md5, the size check) and
  the atomic `.part` → rename apply to every server, fallbacks included.
- A sweep that re-spends LLM tokens every pass on a run that fails the same way every time.
- Spending tokens around the usage pacing gates.

## Stakes and review mode

**Review mode: Opus.** The spec, plan and final branch reviewers are on Opus.

**Stakes.** The library is ~3,800 shows feeding an on-air station. This change touches how audio is
fetched and how runs are started and resumed. It deletes or rewrites no user data, and it touches no
money or security surface.

**Strict surfaces:**
- **Download integrity.** No truncated or corrupt file is ever renamed into place, from any server.
- **Live-run detection.** A wrong "not live" verdict starts a second worker.
- **LLM spend.** The pacing gate applies to every show the sweep processes, its learned cost stays
  honest, and the sweep never loops spend on a run that fails the same way every time.

Everything else is ordinary.

## Design

### 1. Server fallback and bounded retry (`IAClient.download_file`)

**Candidate URLs, in order:**
1. The redirect URL as today (`archive.org/download/<id>/<file>`).
2. `https://<server><dir>/<file>` for each server in the item's cached `workable_servers`, in order.
   Only when `workable_servers` is missing or empty, use `d1` then `d2` instead, de-duplicated. A
   `d1`/`d2` absent from a non-empty `workable_servers` is one archive.org has marked not workable.

`<file>` is `quote(filename)` with `/` kept as a path separator, the same rule as `DOWNLOAD_URL`. About 3%
of audio names contain `/` and about 10% need quoting.

The metadata comes from `self.metadata(identifier)`, which is cached; `build_package` has already fetched
it for the md5s. No listed server (or no `dir`) means the redirect URL is the only candidate.

**Timeouts.** Download attempts use their own short timeouts: connect about 10 s, and a stall (read)
timeout of about 20 s, so no bytes for 20 s aborts the attempt. These replace the client's `timeout=60`
for downloads only; `_get` keeps its client settings. Successful transfers on 2026-10-20 took 111-130 s
(furthur tracks 14-15, ~110 KB/s), and a listed-server probe on 2026-10-21 ran at ~62 KB/s, so there is
no total-time bound on a transfer.

**Trickle switch.** A transfer that keeps receiving bytes, but far below archive.org's normal
per-connection rate, is abandoned for the next candidate:
- **Trigger:** throughput over a sliding window of about 30 s below a fixed floor of about 10 KB/s (roughly
  a tenth of the normal 50-100 KB/s). The window starts once bytes start arriving; the stall timeout covers
  the wait before that. A fixed floor, not a running mean: the normal rate is known and needs no history.
  Exact constants are the builder's (`TRICKLE_FLOOR_BPS`, `TRICKLE_WINDOW_S`).
- **Continue, don't restart:** the next candidate is asked for the rest of the file with
  `Range: bytes=<bytes so far>-`. A `206` whose `Content-Range` starts at that offset is appended to the
  same `.part`; any other answer (a `200` ignoring the range, a mismatched `Content-Range`) discards the
  `.part` and that attempt downloads from byte 0. Listed servers answered range requests with 206 in the
  probes. Continuation is used only when the file has an md5: with size alone, a prefix and a suffix from
  copies of different lengths could pass the size check, so without an md5 an abandoned `.part` is
  discarded and the next attempt starts from byte 0. When `size` is known, a `Content-Range` total that
  differs from it counts as mismatched. An abandonment is allowed only while another attempt will still
  start (the first pass is unfinished or the deadline has not passed), and never once the `.part` holds
  the full `size`.
- **Integrity is unchanged:** the md5 (or size) check runs over the whole finished `.part`, however many
  servers it came from. If it fails, the `.part` is deleted and the next attempt starts from byte 0.
- **Terminates:** each candidate can be abandoned for trickling at most once per file. The last candidate
  not yet abandoned is never abandoned: its transfer finishes however slow, as long as it isn't stalled.
  A trickle abandonment ends that attempt like any retryable error, and the schedule below carries on.

**Classification:**
- **Retryable:** 5xx, 429, 408, and transport errors (connect and stall timeouts, connection resets, a
  body stream that dies mid-transfer). These move on to the next candidate URL.
- **Other 4xx:** moves on to the next candidate; it does not fail the file at once. It is not retryable
  for the repeat attempts after the first pass, so a file whose every candidate answered 4xx fails after
  one pass.
- **md5 mismatch:** moves on to the next candidate, since a different copy may be good. The mismatched
  `.part` is deleted as today. That copy is not tried again in the repeat attempts: each copy is checked
  at most once per file, and the others are still tried.
- **No md5 in the metadata:** the byte count must equal the metadata `size` before the rename into place.
  A mismatch is handled like an md5 mismatch. Metadata `size` is present for every cached audio entry; 4
  of 531k entries lack an md5. With neither md5 nor `size`, the file is renamed into place as today.

A file whose every copy fails the check (a removed or darked item, or a stale cached md5) fails as
`download` on every sweep pass; the sweep keeps listing it and exits 1. This is a known limitation,
cleared by hand.

**Schedule.** First pass: every candidate gets one attempt, in order, with a short randomised sleep
between attempts (about 1-4 s, uniform; exact constants are the builder's). The first pass is never cut
short, so a hanging redirect can't starve the listed servers. After it, repeat attempts cycle through the
candidates whose last error was retryable, for a **monotonic deadline of about 60 s** of attempts and
sleeps counted from the end of the first pass. The deadline is checked before starting an attempt, and
an attempt in flight is allowed to finish. One exception: the attempt that follows a trickle abandonment
always starts, even past the deadline, because the abandonment was allowed only on the promise of a next
attempt; that attempt cannot itself be abandoned, so at most one runs past the deadline. Time spent waiting for a download slot (§2) does not count.
When the deadline passes, or no candidate is retryable, raise `IADownloadError` (below) naming every URL
tried and its last error. `Retry-After` is ignored: switching servers is the response to a struggling
server.

Worst case for a file whose every server hangs: about (number of candidates × stall timeout) + 60 s.

**New error class:** `IADownloadError(IAError)` for a download that exhausted its candidates. Callers that
catch `IAError` keep working.

New module constants for the download path (`DOWNLOAD_DEADLINE_S`, sleep bounds, connect and stall
timeouts); `max_retries` and `backoff_s` keep serving `_get` unchanged. The RNG and clock are injectable
for deterministic tests.

**Run-level bound (Goal 2).** A failing file adds about a minute (more only if its servers hang), and a
show usually fails on its first bad file. So a run's added time is about a minute per failing show: a
full archive.org outage on a 12-show run adds about 12 minutes, which is accepted. No run-level circuit
breaker.

### 2. Download cap (courtesy)

At most **8** concurrent audio downloads **per workspace** (`<root>`, i.e. across every llama process
using `~/.llama`; in practice the whole machine).
- **Mechanism:** flock slot files `<root>/.download-slots/0..7.lock`. A download polls the slots with
  non-blocking tries and a short jittered sleep (about 0.5-1 s) until it gets one; it doesn't block on one
  slot.
- **Visibility:** while waiting it prints one `detail` line (`waiting for a download slot`) once per
  file, not per poll.
- **Hold time:** a slot is held for one attempt's transfer and released before any sleep between
  attempts.
- **Crash safety:** flock releases on process death.
- **Constant:** `DOWNLOAD_SLOTS = 8`, not config (the operator's choice). archive.org already throttles each
  connection, so the cap only limits how many connections we open at once. It sits near the operator's
  heaviest parallelism (6-10 batches), so it rarely slows a batch; a cap of 4 would have cut total download
  speed by about 2.5× on those days. The per-process `rate_limit_s` throttle stays.

### 3. Failure records

Each entry in a session's `failures` gains two fields beside `show` and `error`:
- `kind`: set by the first match in this order (several of these classes subclass `HerderError`):
  1. `RateLimited` → `rate-limited` (recorded as a failure only under `--no-pacing`);
  2. `TaskFailed` → `llm`;
  3. herder's `ResearchNotSupported` → `other`;
  4. any other `HerderError` → `transport`;
  5. `IADownloadError` → `download`;
  6. any other `IAError` → `archive`;
  7. anything else → `other`.
- `at`: the UTC ISO time of the failure.

These records are persisted state and stay permissive. A legacy record with no `kind` is read as
`download` when its `error` starts with `download of `, else `other`.

### 4. Run lock (live-run detection)

The commands that work a run take an exclusive flock on `runs/<id>/.lock` **exactly once**, at command
entry, and hold it until exit. It is never taken inside `_execute`. The commands:
- `llama get`: query and profile forms, on its freshly claimed run dir, before interpret. The dir comes
  from `claim_run_dir`, or with `--name` the dir is created with `exist_ok=False`: success means a new dir, `FileExistsError` an existing one. On a dir
  this invocation created, `get` takes the lock **blocking**: only a reader's probe or the sweep's helper
  can hold a fresh dir's lock, and only briefly, so a collision with a `run list` probe never makes a fresh
  `get` exit and never leaves a request-less husk. `get --name <existing>` takes it non-blocking and
  refuses a live run, like resume.
- `llama run resume <id>`: before reading anything.
- `llama run approve`: at entry, before any prompt or write.
- `llama redo --run <id> --from search|winnow`: the run-level form only. The show-stage form is a show
  batch under show locks and is unchanged.
- `llama run rm`.

Rules:
- **Missing run dir:** for resume, approve, redo `--run`, rm and the readers, the lock helper refuses to
  create one, so a lock attempt that loses a race with `rm` can't recreate the run (one narrow window
  remains, below). `get` is the exception: it creates its dir before locking (above).
- **The locked file must still be the run's lock file:** after acquiring (blocking or not), the lock
  helper checks that the locked fd is still the file at `runs/<id>/.lock` (same inode and device).
  Otherwise, or if that file is gone, it releases the lock and treats the run as missing.
- **A held lock means live:** resume, approve, redo `--run` and rm try the lock non-blocking; on a live run
  they refuse with `run <id> is in progress in another process` and exit 1.
- **`run rm` holds the lock through `rmtree`.**
- **`run list`, `status --by-run` and `--json`** report a live run's state as `running`. This is a
  non-blocking acquire and immediate release, the only lock touch by a reader. `running` gets entries in
  `_ATTENTION_LABELS` and `_NEXT_STEP` ("in progress"). *My call.*
- **Lock order:** run ⊃ show ⊃ ledger. `process_show` stays lock-free.
- **Known remaining windows:**
  - The milliseconds between a fresh `get` creating its run dir and locking it. A `run rm` landing there
    can delete the new dir. Nothing guards this window.
  - A `run list` probe colliding with a resume starting at the same instant, which then refuses.
  - A lock attempt (resume, approve, redo `--run`) that opens `.lock` after `run rm`'s `rmtree` unlinked
    it but before the dir is removed recreates `.lock`. `rm` then fails with "directory not empty" and
    leaves a dir holding only `.lock`. It shows on the sweep's needs-attention list (no criteria, no
    request), and a second `run rm` removes it.

  Without the inode check, a `run rm` landing within milliseconds of a fresh `get` could leave `get`
  holding a lock on a deleted file while its artifacts recreate the dir unlocked, and a sweep would start
  a second worker. The check closes that, so none of the remaining windows can produce two workers.

**Rollout caveat:** a run started by a pre-v2.14 binary holds no lock, so it is invisible to the sweep.
Don't sweep while pre-v2.14 runs are going. This goes in the release notes.

### 5. Honest pacing samples

In `_execute`'s first-pass loop, a show records a pacing boundary only if **an LLM provider was invoked
during its `process_show` call**. The builder chooses how, e.g. `process_show` reports whether any
provider call happened, or a provider wrapper counts calls.

Doing work is not enough. A resume of a download-failed show re-runs only `package`, with no LLM call.
That is exactly the sweep's population, and its near-zero deltas would gut the EWMA (alpha 0.4).

This matters beyond the sweep. Today every `run resume` re-walks finished shows and folds near-zero deltas
into the EWMA. The deferred pass is unchanged; it already records nothing.

### 6. The sweep: `llama run resume --all`

One pass, then exit. *Flag name is my call.* A positional session plus `--all` is an error.

**Eligible:**
- `paused` with `resume_after` in the past or absent, and every recorded failure (if any) `download` or
  `archive`;
- `incomplete` with no recorded failures (a crash or kill left no clean stop);
- `incomplete` whose every failure is `download` or `archive`.

A run with no session marker (`session.json` absent) reads as `incomplete` with no failures. It is
eligible when its `request.json` has `auto: true` or no `auto` key.

**Skipped, one line each, with the reason:**
- live (`running`);
- `paused until HH:MM`;
- `awaiting approval`;
- `needs attention`:
  - an incomplete or paused run with any `transport`, `llm`, `rate-limited` or `other` failure. These
    are left for an explicit `run resume <id>`, so a sweep loop never re-spends on a show that fails the
    same way every time. Some `transport` failures repeat every time and cost tokens (a 900 s research
    timeout, retried 3× per pass). A paused marker carries the failures already taken, and a resume
    re-runs every chosen show, so a show that fails the same way would be re-paid once per window;
  - a run with neither `criteria.json` nor `request.json`;
  - a run with no session marker whose `request.json` has `auto: false`: an interactive `get`
    interrupted at a prompt, which the sweep would otherwise process with `--auto`.

`complete` runs are not listed.

**Related fix:** `_execute`'s early return on "no matching artists found" writes `mark_complete` with
that message, so such runs no longer read as `incomplete`.

**Order:** oldest `updated_at` first, one at a time, in-process, via a helper extracted from `run_resume`.
The helper takes the run lock itself and the sweep does not pre-acquire it. A run that turned live since
the listing reports `running` (the helper's non-blocking acquire decides).

**Isolation:** each run's resume is wrapped. Any `Exception` or `typer.Exit` from one run is reported as
`error: <message>`, and the helper writes `mark_incomplete` for that run with one failure of kind `other`
(the error text) while it still holds the run lock, so no other resume can be overwritten. The run then reads as needs-attention instead of re-running, and re-spending, every
pass. A run the helper finds live is reported as `running`, not caught as a crash, and gets no marker.
The sweep continues. `KeyboardInterrupt` stops the sweep.

**Flags:**
- `--wait/--no-wait` defaults to `--no-wait` for the sweep (unlike plain `run resume`), so a usage pause
  checkpoints the run as `paused` instead of napping inside the operator's loop. `--max-wait` and
  `--no-pacing` pass through.
- Always non-interactive (`--auto`); there is no `--interactive`.

**Stopping on a pause:** after each resume the sweep re-reads that run's state. If it is `paused`, the
sweep stops, lists the eligible runs it didn't reach, and exits. The window is account-wide.

**Exit status:**
- 0 when every resumed run ended `complete`, or nothing was eligible (`nothing to resume`);
- 1 when any resumed run ended `incomplete`, `paused` or `error`, or ended in any other state (e.g.
  `awaiting-approval` from a replayed `--plan`).

A summary at the end lists each run and its result.

The operator's loop becomes `while true; do llama run resume --all; sleep 600; done`.

## Left to the builder

- The exact sleep, timeout and deadline constants within the stated bounds.
- How an LLM provider call is detected (§5).
- Where the run-lock helper lives (`locks.py` vs `sessions.py`).
- Output wording beyond the quoted lines.
- How the resume helper is factored out of `run_resume`.

## Testing expectations

- Offline and deterministic: injected clock, sleep and RNG; mocked HTTP transport (httpx `MockTransport`).
- **Download:**
  - a 500 on the redirect URL with success on a listed server;
  - every server failing raises `IADownloadError` after the first pass and the repeat deadline;
  - a hanging redirect does not starve the listed servers;
  - a slow but progressing transfer above the floor finishes;
  - a trickle below the floor switches to the next candidate and continues from the byte offset (206), and
    the whole-file md5 passes;
  - a range request answered with 200 or a wrong `Content-Range` restarts from byte 0;
  - a stitched file whose md5 fails is deleted and re-fetched from byte 0;
  - the last non-abandoned candidate is never abandoned, however slow;
  - a 4xx on one candidate followed by success on the next;
  - an md5 mismatch on one server with success on the next, and each copy checked at most once;
  - the size check for a file with no md5;
  - no `.part` left behind;
  - a mid-stream failure;
  - missing server fields mean redirect only.
- **Cap:** acquire/release counters show never more than 8 held, with real flock across processes or
  threads and no timing sleeps; a dead holder frees its slot.
- **Failure records:** each kind is recorded, following the classification order; legacy records are read
  correctly.
- **Run lock:** resume, approve, redo `--run` and rm refuse a live run; `get`'s lock is blocking; `get
  --name` creates and locks its dir; `run list` shows `running`; no self-deadlock on the get → interpret →
  `_execute` path or the sweep → helper path; the helper never creates a missing run dir; a lock acquired
  on a replaced `.lock` is treated as a missing run.
- **Pacing:** a show whose `process_show` invoked an LLM provider records a boundary; a download-only
  resume (only `package` re-runs) and an already-packaged show record none.
- **Sweep:**
  - eligibility per state and per failure kind, including legacy records, paused runs with failures, and
    marker-less runs by their `auto`;
  - `transport` runs are needs-attention;
  - live runs skipped;
  - stops on a pause;
  - one run raising doesn't stop the others, and a caught crash writes a marker;
  - `--no-wait` is the default;
  - exit codes.
- **Mutation:** pin the load-bearing lines with a named predicted red test per mutant.
