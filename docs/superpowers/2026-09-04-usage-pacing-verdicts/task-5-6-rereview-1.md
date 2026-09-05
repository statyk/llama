# Task 5/6 fix-round re-review (scoped)

Diff reviewed: `review-f403239..42d90a4.diff` (commit `42d90a4`).
Method: read the diff, then for every finding applied the cited mutation to
the working tree, ran the relevant tests, confirmed RED, restored the file
(`diff` against a saved copy confirmed byte-identical), confirmed GREEN.
`__pycache__` cleared / `PYTHONDONTWRITEBYTECODE=1` around every mutation.

## Findings

- **I1** (`cli.py` half of Task 6 uncovered) — ADDRESSED.
  `packages/llama/tests/test_run_namespace.py:120-176`,
  `packages/llama/tests/test_status_cmd.py:187-203`.
  Verified directly: M45 (delete `resumes` line, `cli.py:461-462`) → RED;
  M46 (drop the `STATE_PAUSED` guard, fire for every state) → RED against
  `test_run_list_resume_suffix_requires_paused_state`; M47 (hint →
  `llama run approve {id}`) → RED against both
  `test_attention_dicts_carry_a_paused_entry` and
  `test_status_attention_shows_paused_label_and_resume_hint`; M43/M44
  (delete `STATE_PAUSED` from `_ATTENTION_LABELS`/`_ATTENTION_HINTS`,
  `cli.py:2180-2183`) → RED only against the direct-index test (see
  scrutiny item 1 below); full-revert M53 (`cli.py` → `19a4aa9`) → RED,
  2 of 3 new CLI-surface tests fail (matches the report's own account of
  which two).
- **I2** (`parse_duration`'s `$` anchor) — ADDRESSED.
  `test_pacing.py:15-21` (`"6h banana"`, `"5h30m!"`, `"6s30m"` added to
  `test_parse_duration_rejects_nonsense`). Verified: dropping `$` from
  `_DURATION_RE` (`pacing.py:13`) → RED (`DID NOT RAISE ValueError`).
- **I3** (`format_delta`'s one-minute floor) — ADDRESSED.
  `test_pacing.py:29-33` (`test_format_delta_floors_short_deltas_at_one_minute`).
  Verified: `total = max(int(seconds), 60)` → `total = int(seconds)`
  (`pacing.py:31`) → RED (`'0m' == '1m'`).
- **I4** (validator only pinned `max_wait`) — ADDRESSED.
  `test_pacing.py:88-91` (parametrized over `max_wait`/`unknown_reset_wait`/
  `reset_skew`). Verified: reducing `@field_validator(...)` to
  `("max_wait",)` (`config.py:111`) → RED, the other two parametrizations
  fail `DID NOT RAISE Exception`.
- **I5** (`sleep_until`'s `chunk_s=900` default) — ADDRESSED.
  `test_pacing.py:56-72` (`test_sleep_until_defaults_to_900s_chunks`).
  Verified: `900 → 1` (`pacing.py:36`) → RED (`assert 1 == 900`).
- **I6** (naive `when` raised bare `TypeError`) — ADDRESSED.
  `pacing.py:47-48` (guard) + `pacing.py:42-45` (docstring) +
  `test_pacing.py:74-78` (`test_sleep_until_rejects_a_naive_when`).
  Guard sits as the very first statement in `sleep_until`, before any
  arithmetic touches `when`; it checks only `when.tzinfo is None`, so an
  aware value in a non-UTC zone is unaffected. Message is legible:
  `"sleep_until requires a timezone-aware datetime, got naive {when!r}"`.
  Verified: removing the guard → RED, but importantly the failure mode is
  `pytest.raises(ValueError)` catching an unhandled `TypeError` — i.e. the
  test doesn't just go red, it goes red for exactly the reason the finding
  describes (bare `TypeError` leaking through).
- **Comment fix** (`SessionInfo.state` inline comment) — ADDRESSED.
  `sessions.py:96` now reads
  `# STATE_AWAITING | STATE_COMPLETE | STATE_INCOMPLETE | STATE_PAUSED`.

## Scrutiny item 1 — is the direct-index test load-bearing, or redundant?

Confirmed the implementer's reasoning is correct, not redundant.
`cli.py:456`: `_ATTENTION_LABELS.get(s.state, s.state)` — the fallback
default is `s.state` itself, and `STATE_PAUSED == "paused"`
(`sessions.py:17`), so deleting the `STATE_PAUSED` entry from
`_ATTENTION_LABELS` makes `.get` fall through to a default that is textually
identical to the deleted entry's value. Likewise `cli.py:2198`:
`_ATTENTION_HINTS.get(s.state, "llama run resume {id}")` — the literal
fallback string is byte-identical to the `STATE_PAUSED` entry
(`"llama run resume {id}"`).

Verified by mutation: deleted `STATE_PAUSED` from both dicts
(`_ATTENTION_LABELS = {STATE_AWAITING: ..., STATE_INCOMPLETE: ...}`, same for
`_ATTENTION_HINTS`) and ran the paused-state tests.
`test_attention_dicts_carry_a_paused_entry` failed (`KeyError: 'paused'`);
**both** output-only CLI tests
(`test_run_list_shows_paused_label_and_resume_suffix` and
`test_status_attention_shows_paused_label_and_resume_hint`) passed anyway —
1 failed, 7 passed on the targeted run. This reproduces exactly the
blindness the implementer describes. The direct-index test is necessary,
not redundant; without it M43/M44 would still survive.

## Scrutiny item 2 — is the run-id substring bug actually fixed in the shipped tests?

Confirmed. Read every new/changed assertion in
`test_run_namespace.py:120-176` and `test_status_cmd.py:187-203`:

- Workspace/session ids used are `s-onhold`, `s-incomplete`,
  `s-incomplete-carries-resume-after`, and `2026-09-04-onhold` — none
  contain the substring `"paused"`.
- Criteria query is `"q"` / `"an incomplete query"` — no incidental
  `"paused"`/`"resumes"`/`"approve"` text.
- Every label assertion indexes the exact column
  (`paused_line.split()[1] == "paused"`, `line.split()[1] == "paused"`),
  not a bare substring check, so a corrupted-but-`"paused"`-adjacent label
  could not pass by accident either.
- The `resumes ...` / hint assertions use the full literal string
  (`"resumes 2026-09-04T15:10:00+00:00"`, `"llama run resume
  2026-09-04-onhold"`), which cannot be satisfied by the id, criteria
  string, or any other text incidental to the fixture.

No assertion in the shipped tests can be satisfied by the run id or any
other incidental text. The self-caught bug the report describes is not
present in the diff as shipped.

## Scope check

- `git diff f403239..42d90a4 --name-only`:
  `packages/llama/src/llama/pacing.py`,
  `packages/llama/src/llama/sessions.py`,
  `packages/llama/tests/test_pacing.py`,
  `packages/llama/tests/test_run_namespace.py`,
  `packages/llama/tests/test_status_cmd.py`. No `config.py`, no `cli.py` —
  confirmed the implementer's claim that both needed no permanent change;
  every I1-I5 finding in those two files was a coverage gap in
  already-correct production code.
- Task 7 fences: `grep -rn "PaceOptions\|pace_options\|resume_at\b"
  packages/llama/src/llama/` → no hits. `_execute` and command signatures
  untouched (not present in this diff at all).
- Reported suite count confirmed: `./.venv/bin/python -m pytest -q` →
  **1703 passed, 7 deselected** (checked at HEAD `42d90a4`).

## New breakage introduced by this fix diff

None found. All mutated-and-restored checks left the tree byte-identical
each time; no behavior change beyond the intended I6 guard and the I1-I5
test additions.

## Deferred (out of scope, not verdicted)

- The diff's new tests are all narrowly targeted and well-commented; no
  additional coverage gaps were noticed in the touched code during this
  pass, but this was a scoped re-review of the six named findings only,
  not a fresh mutation sweep.
- The eleven Minor findings (backward wall-clock step, `chunk_s<=0`
  busy-spin, `format_delta(-3600)`, echo text, `pause_scope` write-only,
  `_session_json` omissions, `[pacing]` TOML comments/`--max-wait` flag,
  config-template presence, `pytest.raises(Exception)` breadth, typing/style
  nits) were left untouched, per instructions — not re-flagged here.

## Tree state

`git status --porcelain` empty at end of review. No edits or commits made;
every mutation applied during verification was restored and diff-confirmed
byte-identical before moving to the next check.

## Overall verdict

**All six Important findings (I1-I6) plus the one-line comment fix are
ADDRESSED.** Both scrutiny items check out: the direct-index test is
genuinely load-bearing (not redundant) for M43/M44, and the shipped CLI
tests use exact label-column/full-string assertions with non-"paused" ids,
so the self-caught run-id-substring bug is not present in what shipped. No
new breakage found in the fix diff. Scope matches the expected file list
exactly (`pacing.py`, `sessions.py` comment, three test files;
`config.py`/`cli.py` untouched). Suite count matches: 1703 passed, 7
deselected (+9 from 1694). Fix round is clean; no blockers.
