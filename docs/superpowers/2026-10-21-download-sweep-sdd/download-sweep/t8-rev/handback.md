### Spec Compliance
- ✅ Spec compliant. Everything in the brief's Step 1 and Step 2 is present:
  - **Commands bullet** (CLAUDE.md:89-124): the `running` state; `run resume --all` eligibility; `--no-wait` default; stop-on-pause; exit codes; the crash marker; the operator loop.
  - **Architecture parallel-safe bullet** (CLAUDE.md:444-475): which commands take the run lock, taken once at entry, never inside `_execute`, readers probe without creating, the order run ⊃ show ⊃ ledger, `rm` held through `rmtree`, and the inode check. Also the download cap at `<root>/.download-slots/0..7.lock`.
  - **Pacing sentence** (CLAUDE.md:652-655).
  - **Domain gotchas** (CLAUDE.md:907-949): the download fallback and the failure kinds.
  - **Rollout caveat** (CLAUDE.md:462-463).
  - **All five known limitations:**
    - non-FIFO cap: :473-475
    - last candidate never abandoned: :931-933
    - integrity-fail loop: :933-935
    - `.lock`-only dir after `rm`: :464-466
    - no window yields two workers, via the inode check: :454-456 and :469-470
  - **README** session block (README.md:151-158).
  - The two `-` lines in the diff are carried forward unchanged inside the extended text. Nothing unrelated was rewritten or lost.
  - The two extra windows (the `run list` probe collision and the fresh `get` mkdir→lock gap) are spec §4's "Known remaining windows" (spec :246-249), not invention.
- ⚠️ Cannot verify from diff: nothing material. I did not re-run the suite, as instructed. The implementer reports 3934 passed.

### Strengths
I checked every concrete claim against source, and all of them hold:
- **Download constants** match ia_client.py:27-38: 10/20/60 s, a 1-4 s sleep, `TRICKLE_FLOOR_BPS` 10_000, `TRICKLE_WINDOW_S` 30.
- **Slot constants** match download_slots.py:20-22. The `waiting for a download slot` line is announced once per `download_file` call (ia_client.py:367-371). The slot is held for one attempt and freed before the sleep (:394-403).
- **Candidate order** matches `_download_candidates` (:237-247): the redirect first; `d1`/`d2` only when `workable_servers` is missing or empty; duplicates skipped.
- **Retryable set** matches `_RETRYABLE_STATUS={408,429}` plus 5xx and transport errors (:41, :283-285, :308-313).
- **416** unlinks the `.part`, retryably (:279-282).
- **Content-Range:** the start is checked and so is the total when known (`_continues`, :337-343).
- **Continuation needs an md5:** otherwise the `.part` is unlinked (:316-320).
- **Stale `.part`** is unlinked at entry (:407-409).
- **Deadline:** the clock starts after the first pass and slot wait is excluded (`expired`, :373-374, :417-419).
- **`IADownloadError` text** has the `download of <filename> failed:` prefix and names every candidate (:444).
- **Kind order and legacy rule** match `classify_failure` and `failure_kind` (sessions.py:26-60). `at` is UTC ISO (:49-51).
- **Run-lock sites:**
  - `get` blocks only on a dir it created, including `--name` via an atomic mkdir (cli.py:840-857, :893).
  - approve: :1121.
  - run-level redo: :3258.
  - rm through `rmtree`: :1341-1348.
  - resume, non-blocking: :1219.
- **Lock helpers:** `RunMissing` and the inode/device check are in locks.py:43-84; `run_is_live` has no `O_CREAT` (:93-107).
- **Refusal strings** match (cli.py:1366-1372).
- **Sweep:**
  - `--all` with a positional session is an error (:1172-1174).
  - Skip reasons and eligibility match `sweep_verdict` (sessions.py:241-279).
  - Sorted by `updated_at` (cli.py:1296).
  - Results are `running`, `gone` and `error: …`; pause stops the sweep with `not reached:`; the exit rule matches (:1298-1322).
  - The crash marker is written under the lock, `exit <code>` for `typer.Exit`, and `KeyboardInterrupt` is not recorded (:1195-1228).
  - `(run)` label: :1069.
- **No-matching-artists** marks the run complete (:483-490).
- **Pacing boundary** is recorded only when `llm_calls()` advanced (:633, :646).

The prose follows CLAUDE.md's dense house style, and it cites the spec sections.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **README.md:152 says the sweep resumes runs "incomplete from … a crash".** That is true of a killed process, which leaves no marker; spec :281 uses the same wording. It is not true of an exception the sweep itself catches: that writes an `other` crash marker, and every later pass skips the run as `needs attention` (cli.py:1224-1226, sessions.py:257-261). A README-only reader could expect a crashed run to keep retrying. Suggest "or a killed process".
2. **CLAUDE.md:94-95 understates eligibility for a run with no `session.json`.** It says such a run is eligible when its `request.json` has `auto: true` or no `auto` key. A run with `criteria.json` but no `request.json` is also eligible, because `read_request` returns `{}` (sessions.py:262-268). This is trivial.
3. **CLAUDE.md:910-911: "a `d1`/`d2` absent from a non-empty list is marked not workable".** That reads as if llama does the marking. archive.org marks it; llama only treats it as not workable (ia_client.py:238-240). Wording only.
4. **CLAUDE.md:921: "(and total matches `size`)".** The total is checked only when `size` is known (ia_client.py:343). Wording only.
5. **CLAUDE.md:457: "`--json`" in the readers list is ambiguous.** It means `run list --json` and `status --by-run --json`. It mirrors the spec's own phrasing (spec :242).

### Assessment
**Task quality:** Approved
**Reasoning:** Every brief item, including the five limitations and the rollout caveat, is present. Every factual claim I checked matches the source. The remaining points are wording; the most useful is the README's ambiguous "crash".
