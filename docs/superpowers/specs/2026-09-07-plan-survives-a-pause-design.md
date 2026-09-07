# `--plan` survives a pause, in both run modes — design

Date: 2026-09-07
Status: proposed
Base: `origin/main` @ `67aa074`, suite 1905 passed / 7 deselected

Closes the residual filed during the 2026-09-06 loose-ends run: `llama get
--profile <name> --plan`, parked by the run-level usage-limit catch, resumes
with `plan=False` and performs a full acquisition.

## The problem

`--plan` means "build the shortlist, park the session awaiting approval,
process nothing." Query mode honours that across a pause since `67aa074`.
Profile mode does not.

Concretely: `llama get --profile prime-dead --plan` hits a usage limit during
`discover`/`search`/`winnow`, the run-level catch parks the session and prints
`llama run resume <name>`, and following that hint downloads audio and packages
shows. The operator asked to see a shortlist and got a processed show — from
the recovery path the tool itself recommended.

**Why the shipped fix cannot reach it.** `run_resume` recovers the flag from
the persisted request:

```python
plan = bool(req.get("plan")) and not ws.shortlist.exists()
```

`_get_profile` (`cli.py:815`) never writes a `request.json`. It loads the
stored profile, stamps `count` and `profile` into `criteria.json`, and calls
`_execute` directly — no `run_interpret`, no request artifact. So `req` is
`{}`, `plan` is `False`, and the run processes. The flag reaches `_execute` for
the live run (`cli.py:829`) but is never persisted, so it does not survive the
checkpoint.

**This is not a regression.** Profile runs behaved this way before the
loose-ends work too. What changed is that the run-level catch now *creates*
parked profile runs routinely, so the population is no longer empty.

## Approaches considered

### A. Extend `request.json` into a mode-agnostic invocation record — RECOMMENDED

`request.json` already exists to answer "what command started this run". Today
its shape is query-specific. Widen it to cover both modes, and `_get_profile`
writes one like every other entry point.

- The reading side is **unchanged**: `run_resume`'s existing `plan` expression
  works for both modes with no new branch.
- It resolves, rather than routes around, the shape objection that caused the
  residual to be filed in the first place.
- `iter_sessions`' fallback gets a defined answer for profile runs instead of
  an accidental one.

Cost: one new writer, one widened schema, and two existing readers must learn
that `query` is optional.

### B. Record `plan` in the pause marker (`session.json`)

Attractive at first glance — `plan` is in scope at `_render_pause`, and a
checkpoint recording the flags that must survive the checkpoint is a tidy
story. **Rejected on reflection**, and this spec records why because it was the
author's first proposal:

- It conflates two different facts. The marker answers *why the run stopped*;
  `--plan` is a property of *what the run is*, true from invocation and
  unchanged by the stop.
- It is more surface, not less: `_render_pause` has four call sites and would
  need a new keyword threaded through all of them, including one inside
  `_interpret_with_pause` where the flag is not yet in scope on the resume
  path.
- It leaves `request.json`'s shape problem unsolved, so the next flag that must
  survive a pause faces the same fork again.

### C. Stamp `plan` into `criteria.json`

Smallest possible change — both modes already write criteria, and it already
carries run-shaping fields (`count`, `profile`, `artist_cap`, `year_cap`).
**Rejected:** `Criteria` is a domain model describing *which shows to find*,
consumed by grouping, winnow and selection. `--plan` is a CLI control flag that
none of them should ever see. The convenience is real and the modelling cost is
permanent.

## Design (approach A)

### The artifact

```
runs/<id>/request.json
  {
    "mode":   "query" | "profile",     # NEW, required
    "query":  str | null,              # present for mode=query
    "profile": str | null,             # present for mode=profile
    "limit": int|null, "artist_cap": float|null,
    "min_score": float|null, "year_cap": float|null,
    "auto": bool, "plan": bool
  }
```

`mode` is explicit rather than inferred from which of `query`/`profile` is
non-null. A reader that infers will one day meet a run where both or neither is
set and pick silently; a reader that switches on `mode` fails loudly.

### Writers

- `_get_query` — adds `"mode": "query"`, `"profile": None`. Otherwise unchanged.
- `_get_profile` — writes the artifact for the first time, immediately after
  `claim_run_dir` and before `_execute`, carrying `mode="profile"`, the profile
  name, `auto`, `plan`. The selection flags (`limit`, `artist_cap`,
  `min_score`, `year_cap`) are `None`: they are query-mode CLI options and a
  profile run takes those values from its stored criteria.

### Readers

- **`run_resume`** — unchanged. The existing expression already covers both
  modes once the artifact exists.
- **`_interpret_with_pause`** (criteria-less resume) — must refuse a
  `mode="profile"` request rather than re-interpreting a `None` query. This
  branch is unreachable for profile runs today, because `_get_profile` writes
  `criteria.json` before anything can fail. It stays unreachable; the guard is
  there so that if it ever *becomes* reachable it fails loudly instead of
  calling the LLM with `None`.
- **`sessions.iter_sessions`** — the `elif ws.request.exists()` fallback learns
  `mode`: for `query`, today's behaviour; for `profile`, populate
  `SessionInfo.profile` from the request so `run list` renders
  `profile: <name>` rather than `""`.

### Migration

Old `request.json` files (written by `67aa074`, no `mode` key) must keep
working. Treat a missing `mode` as `"query"` — every artifact written before
this change was a query run, by construction, since `_get_profile` wrote none.
This is a real population: any run parked between `67aa074` and this change.

`plan` stays where it is; nothing needs rewriting on disk.

## Testing

1. A profile run parked with `criteria.json` present and `plan: true` resumes
   to `awaiting-approval`, prints the approve hint, and does NOT package
   (`"packaged:"` absent).
2. A profile run parked **without** `--plan` resumes and processes normally.
3. A profile `--plan` run whose shortlist already exists resumes and
   **processes** — the directive is satisfied once a shortlist exists, and this
   is the pin against a permanent no-op.
4. `run list` renders a parked profile run as `profile: <name>`, not `""`,
   including via `--json`.
5. An old `request.json` with no `mode` key resumes as a query run.
6. Query-mode behaviour is unchanged: the four existing resume tests stay green
   untouched.

## Constraints to mutate, not merely run

Each names its expected red test **before** the mutant is applied; a different
test failing is a failed prediction to record, not a pass.

1. Drop `_get_profile`'s `request.json` write → test 1 goes red.
2. Drop `and not ws.shortlist.exists()` → test 3 goes red (this guard is
   already pinned for query mode; test 3 extends the pin to profile mode).
3. Make `_get_profile` write `mode="query"` → test 4 goes red.
4. Treat a missing `mode` as `"profile"` instead of `"query"` → test 5 goes red.
5. Replay `auto` from the request in either mode → the existing
   `auto`-not-replayed test goes red. `run resume` keeps its own explicit
   `--auto/--interactive` flag; a persisted value must never override it.

## Risks

- **A widened persisted artifact has three readers.** All three are named
  above; a fourth appearing later is the thing to watch. The `mode` switch
  makes a new reader's omission loud rather than silent.
- **`_interpret_with_pause`'s guard covers an unreachable branch.** Deliberate:
  cheap, and the alternative is an LLM call on a `None` query if reachability
  ever changes.

## Out of scope

- Persisting `auto`. `run resume` has its own explicit flag and a persisted
  value must not override it. It stays in the artifact as informational only.
- `--plan` on `run approve`. That command is for sessions that already reached
  the shortlist, where the directive is satisfied by construction.
- Any change to `Criteria`, `session.json`, or the manifest.
