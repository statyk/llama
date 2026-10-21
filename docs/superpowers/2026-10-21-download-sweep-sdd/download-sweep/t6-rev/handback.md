### Spec Compliance
- ✅ Spec compliant. I checked every command in the wiring list against spec §4 and the brief:
  - **get, query form** (cli.py:839-879): `claim_run_dir` gives `created=True`. `--name` uses `mkdir(parents=True, exist_ok=False)`; success means created and `FileExistsError` means existing. The call is `_run_locked(ws, blocking=created)`, taken before `request.json`, before `_preflight_gate` and before interpret.
  - **get, profile form** (cli.py:885-906): `claim_run_dir`, then `_run_locked(ws, blocking=True)`, then `request.json`, `criteria.json` and `_execute`.
  - **get --name on an existing dir:** non-blocking, so a live run is refused. A non-live dir is reused exactly as before; the only change is how created-vs-existing is decided.
  - **run resume** (cli.py:1160): `_run_locked` right after `_resolve_run`, before any read.
  - **run approve** (cli.py:1113): `_run_locked` before the shortlist read or print and before any prompt.
  - **redo --run X --from search|winnow** (cli.py:3135): the lock is in `_redo_run_level` before the `criteria.json` check. The show-stage `--run` path (cli.py:3203-3206) is untouched.
  - **run rm** (cli.py:1223): `_run_locked`, then `session_state`, the prompt and `rmtree`, all under the lock.
  - **Readers:**
    - `_ATTENTION_LABELS[STATE_RUNNING]="running"` and `_NEXT_STEP[STATE_RUNNING]="in progress"`.
    - `_session_json` `next` is `None` for a running run.
    - `_by_run_rollup` rows carry `"running": run_is_live(d)`, and the text row appends `  [running]`.
    - `iter_sessions(root, *, probe_live=True)` reports running whatever the marker says. `session_state` never probes (sessions.py:162-165).
  - **Locks module** (locks.py:42-113):
    - `RunMissing`.
    - `run_lock`: `O_CREAT` without mkdir. `FileNotFoundError` or `NotADirectoryError` becomes `RunMissing`. A held lock in non-blocking mode becomes `Locked`. After acquiring, the `(st_ino, st_dev)` of `fstat(fd)` must equal that of `stat(run_dir/.lock)`; a `FileNotFoundError` from the stat is `RunMissing`.
    - `run_is_live`: `O_RDONLY`, no `O_CREAT`, missing means False, held means True, and any other OSError propagates.
    - `RunWorkspace.lock` is added (workspace.py:126).
  - **Exact copy:** `run <id> is in progress in another process` matches (cli.py:1244).
- ⚠️ I cannot verify from this diff alone whether the documented windows behave as spec §4 describes under a real cross-process race. Two items rest on reasoning, not on a test: the `.lock` husk left after `rm` races a lock attempt (operator-ruled known window), and the create-to-lock window in a fresh `get`. On the husk window, my reasoning agrees with the spec's claim. rmtree's unlink order is arbitrary, so a resume could recreate `.lock`, lock it, see a matching inode, and briefly read a surviving `criteria.json`. Even then, the only worker holds a valid lock on the current `.lock` and `rm` is not a worker, so this window cannot produce two workers.

### Strengths
- **Lock order and entry points.** I listed every `_execute(` call site in cli.py: 875, 904, 1129, 1206 and 3151. Each sits inside exactly one `_run_locked` and nothing takes the run lock under a show or ledger lock. `_execute`'s show locks (cli.py:629, 681) are inside the run lock, so the order is run ⊃ show ⊃ ledger. `process_show` takes no lock. The show-level redo at cli.py:2359 builds a `RunWorkspace` under a show lock but takes no run lock, which is correct.
- **Re-indentation.** `git diff -w` shows only the `with` headers, the `--name` mkdir block and the reader changes. No statement moved into or out of a block. Every early `return` or `raise typer.Exit` in the wrapped bodies leaves through the `with`, so the lock is released: the preflight `return`, `criteria is None`, "no matching ranks", rm declining, and `no criteria.json`.
- **fd hygiene in `run_lock`.** The single `try/finally` (locks.py:69-90) covers the Locked path, the stat `FileNotFoundError`, the inode mismatch, and errors raised inside the body. The only failure before the fd exists is the open itself. `LOCK_UN` on an unheld lock is harmless.
- **fd hygiene in `run_is_live`.** It closes the fd on every path (locks.py:108-113). It deliberately lets non-`BlockingIOError` errors propagate rather than reading them as "not live", which is the right bias on this strict surface.
- **`_run_locked` scope.** The ExitStack wraps only the acquisition in the except clauses (cli.py:1240-1249). A `Locked` raised from a non-blocking show lock inside the body therefore cannot be mis-reported as "run in progress".
- **Tests use real flock and assert real behaviour.**
  - Holders are a second fd, and the refusal tests snapshot bytes and mtimes.
  - The get tests record `(blocking, request.json existed)`, which pins "blocking" and "before request.json" together, and probe from a stubbed `_execute` that the lock is held.
  - The replaced-lock test is deterministic: an `fcntl` proxy does the replacement before the acquirer's real flock, with no sleeps. It is parametrized to hit both the inode-mismatch branch and the stat-`FileNotFoundError` branch, and it proves the acquirer holds nothing afterwards (the holder re-locks with `LOCK_NB` and `run_is_live` is False).
  - `test_run_list_reports_running` uses a `complete` marker, so it proves the live state overrides the marker.
  - The no-self-deadlock tests run the real `_execute` with stubbed stages.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **cli.py:1056-1062 (`_print_sessions`) and the marker fields in `_session_json`: a running row still shows the previous attempt's results.**
   - What's wrong: a running row still prints the previous attempt's `outcome` and its failure lines (implementer concern 3). On a run being resumed, this reads as `running … in progress … "q"   5 packaged, 1 failed` followed by stale `- show: download of …` lines. JSON likewise carries `outcome`, `failures` and `resume_after` from the marker.
   - Why it matters: the spec is silent, and nothing acts on these lines today. An operator could still read them as current.
   - Fix: suppress `outcome` and the failure lines for `STATE_RUNNING` in the text table, or prefix them with "last attempt:". Leave JSON as is, since it is raw marker data. This is a judgement call.
2. **cli.py:1078-1079: stale `run list` docstring.** It still says "List sessions awaiting approval, incomplete, or paused". The attention list now also includes running sessions, including one whose marker is `complete`. Add "or running".
3. **Unused `RunWorkspace.lock` (workspace.py:126).** The brief mandates the attribute, but nothing reads it. `run_lock` and `run_is_live` rebuild `run_dir / ".lock"` themselves (locks.py:63, 104), so the literal lives in two places. This is harmless because the interfaces take `run_dir`. A test could assert `RunWorkspace(...).lock == run_dir/".lock"` to keep the two from drifting.
4. **cli.py:1234 (implementer concern 1): the extra `blocking=False` keyword on `_run_locked`.** It is a superset of the brief's signature, and the default matches it. Routing `get` through `_run_locked` keeps every acquisition on the patched `cli.run_lock` and gives a clean `run <id> no longer exists` exit when a fresh `get` loses the create-to-lock race or the inode check. That is better than a traceback, and the spec does not dictate this output. No change needed. I record it here because it is a deviation from the brief's interface.
5. **cli.py:840-845: edge case where `--name` names an existing regular file under `runs/`.** `FileExistsError` gives `created=False`, and the open then raises `NotADirectoryError`, which becomes `RunMissing`. The command prints `run X no longer exists`, which is slightly misleading; before this change the user saw an artifact write error. This is negligible in practice.

### Assessment
**Task quality:** Approved
**Reasoning:** Every command in spec §4 takes the run lock once, at entry, outside `_execute`, and in the correct order. `run_lock` and `run_is_live` match the brief's interface exactly, including the inode/dev check and never creating the run dir, and neither leaks an fd on any path. The tests use real flock holders, deterministic ordering and snapshot assertions. What remains is presentation polish.

Named risks I checked:
- **Self-probe or self-deadlock:** `iter_sessions` and `attention_sessions` are called only from `run list` (cli.py:1081), and `_by_run_rollup` only from `status`. Neither runs under a held run lock.
- **Lock ordering:** I grepped every `_execute(` call site and every `file_lock(` site in cli.py.
- **Statement drift in the re-indent:** I used `git diff -w` on cli.py.
- **Show-stage `--run` redo:** cli.py:3199-3206 is unchanged and takes no run lock.
- **Import cycle from `sessions` → `locks`:** none. locks.py imports only `os`, `contextlib`, `pathlib` and `fcntl`.
