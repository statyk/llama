VERDICT: ALL ADDRESSED

### Finding verdicts

- **H1 — ADDRESSED.** service.py:287-290: a doc rejected by `guard_doc_problem` prints `guard      CORRUPT (...): the clock treats it as a spend trip` and then `summary[1:]`. For any non-None guard, `guard_summary` (cloudstate.py:289-292) always puts the tripped/not-tripped verdict at index 0, so the doc's own verdict is the line dropped; a summary that raises gives `[]`. `budget` (cli.py:134-141) prints no summary at all for a corrupt doc, so neither view can show `guard      not tripped` or `guard      TRIPPED` after a CORRUPT line. I checked this directly with `cloud_lines` on `{"tripped": F/T}`, `{"schema":1,"tripped":F/T,"reason":None}`, `[1]` and `"x"`: each prints exactly one `guard` line, the CORRUPT one.
  - **Brief test (test_service.py:393-411).** Only the guard doc changed. It gained `schema: 1`, `since`, `period: None`, `evaluation: None`, `tripped_period_start`, `tripped_budget_usd` and `evaluated_at`. All six assertions are byte-identical. `guard_doc_problem(doc)` returns `None` (run directly).
  - **(i)** is in `test_a_corrupt_guard_never_shows_its_own_verdict_line[False|True]` (test_service.py:549-554). It asserts that no `not tripped`/`TRIPPED` line appears and that there is exactly one `guard` line.
  - **(ii)** I confirmed the mutant myself (see Checks).

- **H2 — ADDRESSED.** service.py:272-277 and :281/:294 append ` -- the clock treats it as a spend trip` to the guard's unreadable line and ` -- the clock treats the station as off the air` to offair's. Both are pinned by `test_unreadable_guard_and_offair_documents_state_the_consequence` (test_service.py:557-564). The ruling's text shows an em dash and the code uses `--`. That is cosmetic, in ASCII house style, and the test pins only the line's tail.

- **H3 — ADDRESSED.** cloudstate.py:185-186 appends ` (period end unknown)` to any honoured verdict when `end_us is None`, which also covers `honoured, capped at $100`. `raise_verdict` itself is unchanged, so `_pending_raise_usd` and raise validation are unaffected. This is the only behaviour change outside status: `budget` shares `raise_status_line`, and the one existing assertion at test_cloudstate.py:352 changed to match. The parametrized cases at test_cloudstate.py:374-375 still expect a plain `(honoured)` because they have a known period end. It is pinned in `test_a_raise_with_no_known_period_end_is_not_plainly_honoured` (test_service.py:567-571).

### New breakage in the fix diff
None.

### Out-of-scope observations
- Minor/cosmetic: the H3 wording renders as nested parentheses, `(honoured (period end unknown))`. It is readable but slightly awkward; the ruling's wording was followed.
- A guard document with a known period but an unknown `base_budget_usd` still prints plain `(honoured)` even though the configured-budget check was skipped. The ruling covered only the period end. This is not a spend hazard because it is a read-only view and the Worker decides.

### Checks run
- I read the brief, findings, handback and diff, plus cloudstate.py:120-308, service.py:263-316 and cli.py:95-152 at HEAD 4ff1126.
- `./.venv/bin/python -c "import transmitter"` resolves inside the worktree.
- I called `guard_doc_problem` on the brief's new guard doc and got `None`.
- I called `cloud_lines` directly on eight corrupt guard shapes: one guard line each, never a verdict line.
- Mutant 1, in a scratch copy from `git archive HEAD packages/transmitter`, with PYTHONPATH shadowing proven (`transmitter.__file__` resolved inside the scratch dir), run as `python -B -m pytest -p no:cacheprovider`:
  - Change: service.py:288 `if problem is not None:` -> `if True:`.
  - Predicted red: `test_status_shows_the_cloud_state_and_active_alerts`.
  - Result: exactly that test went red, on `assert "guard      TRIPPED (blind)" in text`. The unmutated baseline of the same selection had 3 passing.
- Mutant 2, in the same scratch copy:
  - Change: `lines += summary[1:]` -> `lines += summary`.
  - Predicted red: `test_a_corrupt_guard_never_shows_its_own_verdict_line[False]` and `[True]`.
  - Result: both went red, and the brief test stayed green.
- The scratch copy was removed. The live worktree is clean and HEAD is unchanged.
- I did not re-run the full suite. The implementer reports 443 passed / 1 skipped on py3.14 and on py3.11, and 444 passed on Debian-12.
