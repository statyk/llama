# Task 4 — SPEC-COMPLIANCE review (Opus)

## Verdict: Spec ✅

The diff implements exactly what the brief specifies — all six substantive
steps, no more. 64 insertions, 0 deletions, four files, all named in the
brief's Files list. No unrelated churn.

## What I verified

### Interfaces the later tasks consume
- `RunWorkspace.request` → `runs/<id>/request.json`, added beside
  `self.criteria` in `RunWorkspace.__init__` (`workspace.py:120`). ✅
- On-disk shape written in `_get_query` (`cli.py:675-678`) is exactly the
  seven keys in the brief and in spec §1(b), same names, same order:
  `query, limit, artist_cap, min_score, year_cap, auto, plan`. ✅

### Placement
- The write sits immediately after `ws = RunWorkspace(config.root, run_name)`
  and **before** `run_interpret` — i.e. before the first LLM call of the run,
  which is the whole point of the artifact. ✅
- `write_artifact` → `atomic_write_bytes` does `path.parent.mkdir(parents=True,
  exist_ok=True)`, so the `--name <new>` path (where `claim_run_dir` never ran
  and the dir does not exist) still works; the brief's own test exercises it
  with `--name req`. ✅

### `import json`
- Module-level `import json` added at `cli.py:1`; the five local
  `import json as _json` aliases are untouched (verified by grep: lines 875,
  1363, 1561, 2707, 2946). No shadowing — the local imports bind `_json`, not
  `json`. Exactly what the brief asked for, including leaving the alias alone. ✅
- `sessions.py` already had `import json` at module level; correctly not
  re-added. ✅

### `iter_sessions` fallback (spec §1(d))
- The `elif ws.request.exists():` branch is appended to the existing
  `if ws.criteria.exists():` chain, criteria still winning. `.get("query") or ""`
  preserves the `""` default for a malformed/empty request. ✅

### The "one reader" constraint
`grep -rn "request\.json\|ws\.request" packages/llama/src packages/emcee/src`
returns exactly three hits: the definition (`workspace.py:120`), the writer
(`cli.py:675`) and the single reader (`sessions.py:124,127`). `run rm`,
`_resolve_run` and `attention_sessions` do **not** reference it, so the spec's
risk-section claim holds in the diff and there is no extra-reader scope
expansion. ✅

### Red-first evidence — independently reproduced
The report carries red-first evidence with the command and a per-test failure
mode, which is what the brief's Step 2 requires. I did not take it on trust:
I rsync'd the worktree to a COPY at `.../scratchpad/t4-spec-copy` (excluding
`.venv`/`.git`), restored the three source files from `28fbb9e`, and ran with
`PYTHONPATH` shadowing under the worktree venv's `python -m pytest`.
Shadowing proved **inside pytest** by a planted sentinel test:
`IMPORT PATH: .../t4-spec-copy/packages/llama/src/llama/__init__.py`.

- All three sources reverted → `3 failed, 25 deselected`, with exactly the
  failure modes the report names (`FileNotFoundError` on `request.json` for
  test 1; `AttributeError: 'RunWorkspace' object has no attribute 'request'`
  for tests 2 and 3).
- I then isolated each change, because tests 2 and 3 initially fail in their
  own *setup* (on `ws.request`), which would not by itself prove they pin the
  `sessions.py` branch:
  - `workspace.py` + `cli.py` restored, **`sessions.py` fallback absent** →
    `2 failed, 1 passed` — tests 2 and 3 fail on the `query` assertion
    (`- GD 1977 Cornell`). The `elif` branch is genuinely load-bearing.
  - `workspace.py` + `sessions.py` restored, **`cli.py` write absent** →
    `1 failed, 2 passed` — test 1 fails. The write is genuinely pinned.
- So each of the three source changes has a test that reddens without it.
  Copy deleted afterwards; the worktree was never modified.

### Suite
Ran the mandated command myself:
`cd /Users/shawn/projects/llama-wt-pacing-loose-ends && ./.venv/bin/python -m pytest -q`
→ **1878 passed, 7 deselected, 26 warnings in 5.85s**. Matches the predicted
1878 (1875 + 3). `git status --porcelain` empty; HEAD is `2b42172`;
`./.venv/bin/python -c "import llama; print(llama.__file__)"` resolves inside
the worktree. The implementer's report quotes the same command with its result,
so it is auditable.

### Commit
`feat(runs): persist the raw query at run-claim time (T6b groundwork)` —
lowercase `type(scope): subject`, body explains *why* (criteria.json only on
success, query lives only in argv) and records the verified counts. ✅

### `_session_json` (brief's Step 6 warning)
Confirmed independently: `_session_json` builds its dict from `SessionInfo`
attributes only and never reads `criteria.json`/`request.json` directly, so it
needed no change and the `--json` test passes through the `iter_sessions`
fallback. The implementer checked this rather than assuming. ✅

## Findings

1. **Minor — a pre-existing comment is now partly false, and was correctly
   left alone.** The block above `run_interpret` (`cli.py:679-682`) still says
   "a checkpoint here would be unresumable -- the query lives only in argv."
   After this commit the query no longer lives only in argv; that is precisely
   what the commit changed. Leaving it is the right call for Task 4 — editing
   it is Task 6/7's job, and rewriting it here would be scope creep the brief
   did not authorise — but it must not survive Tasks 6-7 unedited, and the same
   sentence is repeated verbatim in `CLAUDE.md`. The implementer flagged this
   himself. No action owed in Task 4; tracking item for the orchestrator.

2. **Minor — `llama get --name X` against an existing run dir overwrites
   `request.json`.** `--name` bypasses `claim_run_dir`'s auto-suffixing, so a
   second `get` with the same name rewrites the artifact. This is identical to
   the pre-existing behaviour for `criteria.json` on that path, is not a
   regression, and is not something the brief or spec §1(b) asks to guard. Noted
   only so Task 5's resume branch is written knowing `request.json` is
   last-writer-wins, not append-only.

3. **Minor (informational) — `limit` is typed `int` at the `_get_query`
   signature, not `int | None`.** Spec §1(b) writes the field as `int|null`.
   The written value is whatever the `get` option supplies, so a JSON `null` is
   reachable only if that option can be `None`; a `0`/absent limit will
   serialise as an int. Consumers in Task 5 should treat the field as
   "falsy means no limit" rather than "None means no limit". Not a deviation
   from the brief, which specifies the dict literally as written.

## ⚠️ Cannot verify from diff

None. Every interface the brief names as consumed by Tasks 5-7 is present in
the diff and matches the specified shape byte-for-byte; the consumers
themselves do not exist yet, which is the intended task order.

## Scope check (the "no more" half)

- No `run rm` / `_resolve_run` / `attention_sessions` changes. ✅
- No `run resume` branch (that is Task 5). ✅
- No `except RateLimited` around `run_interpret` (that is Tasks 6-7). ✅
- No pre-flight-gate extraction (spec §1(a), a later task). ✅
- No measured constants touched; none in scope. ✅
