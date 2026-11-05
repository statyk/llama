### Spec Compliance

- ✅ Spec compliant on every interface the brief names, with one gap in the contract's "release in `finally`" guarantee (Important 1 below). Checked: the file name and location (station_lock.py:189, `Path(delivered).absolute() / LOCK_NAME`; the station root is the delivered folder per station.py:374 `scan`); `O_CREAT|O_EXCL|O_WRONLY`, 0o644, write loop, fsync (station_lock.py:120,133-136); magic line, token, then tool/command/host/pid/started with a trailing newline (station_lock.py:111-117); empty, garbage and vanished locks all refused, never retried (station_lock.py:121-128); non-EEXIST create errors become `EmceeError` with `[Errno n] strerror`, `from None` (station_lock.py:129-131); release unlinks only on its own token and warns otherwise; read or unlink errors warn and never raise (station_lock.py:149-170); the re-entry guard runs before any filesystem call (station_lock.py:104-108); handlers are installed only on the main thread and restored in a nested `finally` (station_lock.py:184-197); `_COMMAND_ORDER` (cli.py:43) and the boundary test; `lock show` and `lock clear` text, exit codes, the no-TTY refusal and the bytes re-compare (cli.py:1447-1502). Nothing parses holder text: `release` uses only `token_of` on line 1.
- ⚠️ Cannot verify from this diff: (a) whether later callers (Tasks 7/9/10) wrap the `with` body in `except BaseException` or bare `except:`, which would swallow the `SystemExit(128+signum)`; (b) that no caller holds the lock across a prompt. Both belong to the tasks that add callers.

### Strengths

- The protocol is tight and matches the contract: exclusive create, a random token, refuse on any existing file, token-checked release, no expiry and no automatic break. A vanished-while-reading lock is still a refusal (station_lock.py:124-125).
- The failure path after create cleans up under `except BaseException` (station_lock.py:137-143), so a signal or error during write or fsync removes the partial file. The scratch run confirmed this.
- `holder_text` escapes control characters, so a hostile lock file cannot drive the terminal.
- `lock clear` never acquires. It re-reads and compares bytes before unlinking, and it treats a vanish after display as "changed".
- The tests are real. Signals are tested with a subprocess and real SIGTERM/SIGHUP. Handler restore is tested on the refused path too. The reported mutation run (with a sentinel) pins the token check, the re-entry guard, the write-failure cleanup, handler restore and the signal handler.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)

1. **station_lock.py:144-147 with 189, and 155-162: an error or signal in acquire's tail, or during release, leaves a lock that nothing releases.** The cleanup at 137-143 covers only write and fsync. From `fsync` returning until `held = acquire(...)` is stored in `station_lock`'s local (189), the `finally` sees `held is None` and releases nothing. All four cases below were demonstrated in a scratch script that imported the worktree's module and monkeypatched it in-process; the checkout was not touched:
   - `os.close(fd)` raising at 144: leaves a complete lock carrying **this process's token and pid**, and the error propagates. SMB close can report deferred write errors, so this path is plausible on the real station share. It is also the one path where the process returns without being killed and still leaves a lock naming itself.
   - SIGTERM after fsync (before 189): `SystemExit 143` with the full lock left behind.
   - SIGTERM between create and write (the handler runs when `os.open` returns, before `fd` is stored): `SystemExit 143` leaves an **empty** lock, and the fd leaks.
   - SIGTERM during `release`, between the read at 157 and the unlink at 161 (for example a second TERM while the first is unwinding): `SystemExit 143` with our token's lock left. `release`'s "never raises" does not hold for BaseException.

   All four fail safe: every writer refuses, names the holder, and `emcee lock clear` recovers. There is no collision. But each one wedges all writers on a STRICT surface in exactly the cases the spec's "release in `finally`, with handlers that raise into it" exists to cover, and Task 10 will copy the pattern.

   Fix:
   - (a) Move `os.close(fd)` inside the protected try, and make the cleanup's own `os.close` non-fatal so the unlink still runs.
   - (b) On the main thread, wrap `held = acquire(...)` and `release(held)` in `signal.pthread_sigmask(SIG_BLOCK, {SIGTERM, SIGHUP})` and unblock immediately after. A pending signal then fires at the unblock: either inside the `try` with `held` set (so it releases), or after release has finished.

   Tests: patch `sl.os.close` so it raises once, and so it `os.kill(os.getpid(), SIGTERM)` after the real close; assert no lock file remains.

#### Minor (Nice to Have)

1. **cli.py:1493-1497: the `lock clear` compare-then-unlink TOCTOU.** If the holder releases and a new writer acquires between the re-read and `path.unlink()`, clear deletes a live lock. POSIX has no atomic compare-and-unlink, so the window is inherent. It is microseconds wide, after the operator has already said yes, and matters only when the operator misjudged a live writer as dead. It could be narrowed by renaming aside first (`os.rename(path, path.with_name(f"{LOCK_NAME}.clearing-<rand>"))`), comparing the moved file, and on a mismatch `os.link`-ing it back (which fails if a new lock exists). Otherwise state the residual window in the docstring.
2. **cli.py:1456/1479/1497: non-ENOENT errors in `lock show` and `lock clear` print a traceback.** `read_lock` catches only FileNotFoundError (station_lock.py:74-79). EACCES, EIO, a directory at the lock path, or a PermissionError from `path.unlink()` all reach `main_cli`'s generic traceback branch (cli.py:1829). Wrap them in `EmceeError("cannot read/remove the station lock at {path}: ...")`.
3. **station_lock.py:155-162: if the file vanishes between `_read` and `os.unlink` in release,** a FileNotFoundError from unlink gives the "could not remove ... clear it with: emcee lock clear" warning. That warning is wrong here, because nothing is left to clear. Catch FileNotFoundError on the unlink and use the "missing" warning instead.
4. **Fsync (station_lock.py:136):** a plain `os.fsync` meets the contract. On macOS it does not flush the drive cache (no F_FULLFSYNC), and the directory entry is not fsynced. For a lock that is acceptable: after a power loss the writer is dead too, so a lost lock is the benign outcome. No change needed. Noted only because the named-risk list asked.
5. **Non-main-thread use (station_lock.py:184-186):** no handlers are installed and nothing is restored, which is correct and leaves no stray restore. A SIGTERM then kills the process under default disposition and leaves the lock. That is acceptable and covered by `lock clear`. The docstring says "on the main thread" but does not say what happens off it; add one line.

### Implementer concerns, judged
- `Held.started` extra field (station_lock.py:60-64): **accept.** The warning text the brief mandates needs it, and the default keeps `Held(path, token)` valid. Note that it takes part in `_held == held` equality, which is harmless.
- Decline exits 0 with `station lock kept` (cli.py:1490-1492): **accept.** It matches `run`'s decline. An operator's "no" is not an error.
- Umask narrowing 0644: **accept.** Passing the mode to `os.open` is the conventional reading of "created with mode 0644". Under a 022 umask the result is exactly 0644. A stricter umask only hides the holder text from other users; it never affects lock semantics, because unlink depends on directory permissions. Avoiding `fchmod` on SMB is right.

### Task 10 mirrorability
The structure is small and mirrors cleanly: module `_held`, `_read` as a test seam, and `acquire`/`release`/`station_lock`. Land the Important 1 fix here **before** Task 10 copies it, or the llama twin inherits the same windows. llama's refusal details must still name the `emcee lock show|clear` commands. `_CLEAR_HINT` is the string to copy verbatim.

### Checks run
- One scratch script in the session scratchpad (`t5rev/demo.py`), run with the worktree `.venv` python under `-I`. It confirmed that the module resolves to the worktree source and demonstrated the four Important 1 cases: close_error (full lock left), sig_after_fsync (full lock left), sig_after_create (empty lock left), sig_in_release (full lock left). Output is in the t5-review log.
- No suite re-run. The implementer's 36 / 1185 / 6675 results were taken as reported.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The protocol, refusal, token-checked release and `lock clear` are correct and well tested. However, acquire's tail (close and the hand-back to the context manager) and release itself are not covered by the signal-to-`finally` guarantee, and a close error escapes too. Each leaves a lock that wedges every writer until someone clears it by hand. Two small changes fix it (close inside the protected try, and a signal mask around acquire and release), and they should land before Task 10 mirrors the module.
