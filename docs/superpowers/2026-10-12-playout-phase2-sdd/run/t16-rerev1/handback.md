VERDICT: OPEN FINDINGS

Scope: 078e533..76e3c16 (one commit), packages/transmitter only. Worktree untouched; all probes and mutants ran in a scratch `git archive` copy, from a scratch cwd, with PYTHONPATH shadowing (proved: `import transmitter` resolved inside the scratch tree).

### Finding verdicts

- **G1: ADDRESSED.** `alerts.load_state` (alerts.py:51) returns None for OSError/ValueError (JSONDecodeError and UnicodeDecodeError are ValueErrors) and for a non-dict. `Dispatcher._load` (alerts.py:133) uses it and still returns {} with its warning. `status_lines` prints `alerts     hugo: unreadable (<path>)` (service.py:351). Tests: `test_status_survives_a_corrupt_local_alerts_file[{not json|[1,2]]`. Implementer concern (2), the new warning for a non-dict alerts.json: harmless and arguably correct, because a non-dict file is just as unreadable as bad bytes. Behaviour is otherwise unchanged (still {}).

- **G2: ADDRESSED.** `cloudstate.raise_status_line` (cloudstate.py:171) parses the document once, through `raise_verdict`. The amount comes from `usd_text`, so it prints "unknown" when the value is not finite, and the line carries the verdict. `budget` and status share it. `budget` is unchanged: the old `_raise_status` used `usd_text(...) != "unknown"`, which is the same as `_finite(...) is not None`. It caught `TransmitterError` around `guard_period_end_us`, which only raises `CloudStateError`. It received the same `now_us`. And `budget` still passes guard=None for a corrupt guard. In status, a corrupt guard is not used to judge the raise (service.py sets guard=None). Tests: budget_usd "abc" gives `unknown … (ignored: budget_usd is not a number)`, and an expired raise gives `(expired)`.

- **G3: NOT ADDRESSED (guard half). The offair half is ADDRESSED.**
  - Offair (service.py:296-305) matches the Worker exactly (guard.ts:230-237). Absent or `false` prints off, `true` prints ON, and anything else prints the CORRUPT line. Tests: `{"offair":"true"}`, `{}`, absent, false.
  - Guard: service.py:289-290 prints the CORRUPT line and then the document's *whole* `guard_summary`, including its own verdict line. A corrupt document that claims not-tripped therefore renders as follows (probe, scratch):
    ```
    guard      CORRUPT (schema is not 1): the clock treats it as a spend trip
    guard      not tripped
    killswitch disabled
    ```
    This is implementer concern (1), and yes, it can mislead. Two lines in the same `guard` column give opposite verdicts. The second one ("not tripped") is more permissive than the Worker's reading of the same bytes (guard.ts: `corruptGuardDoc` means a spend trip), and the brief's Stakes forbid exactly that on the strict surface. It also disagrees with `budget`, which prints only the CORRUPT line for the same document (cli.py budget, `guard = None` with no summary). The ruling asked for "the remaining guard_summary lines". The implementer kept line 0 only because the brief's unchanged first test uses a guard document with no schema (now classified CORRUPT) and asserts `guard      TRIPPED (blind)`.
  - Fix, for the orchestrator to choose:
    - (a) When the document is corrupt, drop `summary[0]` (or replace it with nothing), matching `budget`. Then give the brief's first test a schema-valid guard document (`schema: 1`, `since`, `tripped_budget_usd`, `period`, `evaluation`, …) so it exercises the healthy render. This also closes the gap below.
    - (b) Keep the brief fixture and drop `summary[0]` only when the document claims not tripped. A TRIPPED claim agrees with the Worker's verdict.
  - Either way, add an assertion that a corrupt not-tripped document never prints `guard      not tripped`.
  - Related test gap: no status test renders a schema-valid guard document. Mutant M1 (service.py:288 `if problem is not None:` changed to `if True:`, so every guard prints CORRUPT) was predicted to survive and did: test_service.py + test_cli.py, 56 passed. Nothing pins the absence of the CORRUPT line on a healthy guard. Option (a) closes this.

- **G4: ADDRESSED.**
  - Each key is read separately through `fetch` (service.py:272-278). A `CloudDocumentError` (a new subclass of `CloudStateError`, raised by `get_json` only for non-JSON or non-object bytes, cloudstate.py:53/57) prints `<label> unreadable: …`, and the other documents still print. Any other failure ends the half with one `cloud      unavailable: …` line, as the ruling allows, and the brief's `…[-1] == "cloud      unavailable: cannot read state/guard.json: boom"` still holds. A failed guard read is reported on the guard line, or on the unavailable line naming guard.json.
  - `get_json` now wraps `Body.read()` (cloudstate.py:44-47). This changes nothing on success: `raw` is the same bytes, parsed as before. `offair off` still catches `TransmitterError` around its guard read. `raise_budget` turns a failed read into a `CloudStateError` refusal (previously a raw exception escaped, with no write either way). `budget` still catches `TransmitterError`, which covers both subclasses.
  - Tests: offair.json not JSON (only its own line, guard/alerts still print, no unavailable line), the inactive alert entry is filtered out, and `Body.read` raising ConnectionError becomes a `CloudStateError`.

- **G5: ADDRESSED.** `cli.status` catches `Exception` around `_cloud` (cli.py:228) and wraps non-Transmitter read exceptions as `CloudStateError` (cli.py:226). `cloud_lines` also has a broad catch (service.py:313). KeyboardInterrupt and SystemExit are not caught (`Exception` only). Implementer concern (3): the monkeypatch is sound. I checked offline that real `boto3.client("s3", endpoint_url="nope", …)` raises `ValueError: Invalid endpoint: nope` at construction, which is what the monkeypatch simulates. The patch is needed because the test env has no R2 keys, so the real `make_client` would raise `ConfigError` first. `_cloud` calls `service.make_client`, so the patch is on the live path.

- **G6: ADDRESSED.** The no-epoch branch appends `_cloud_tail` (service.py:329). Test: `test_status_without_an_epoch_still_shows_the_cloud_half`, covering both a cloud reader and `cloud_error`.

- **G7: ADDRESSED for the listed cases.** Every listed case has a test. Red-first verified: the new test_service.py run against 078e533's sources in a scratch copy gave **11 failed, 29 passed**, which matches the handback. The one new test that passes on old code, `test_status_offair_absent_and_false_read_as_off`, is a regression pin, not a fix test. The healthy-guard gap belongs to G3 above.

### New breakage in the fix diff
- **Important** (counted under G3, not separately): service.py:289-290, a corrupt not-tripped guard document prints `guard      not tripped` / `killswitch disabled` after the CORRUPT line. Details and fix above.
- **Minor:** service.py:277, a guard.json or offair.json that is not JSON (or not an object) prints `guard      unreadable: state/guard.json is not JSON…` / `offair     unreadable: …` without the consequence. The Worker treats both as corrupt: a spend trip, and off the air (guard.ts readJsonDoc `corrupt`, then `corruptGuardDoc` / `offair = true`). The line is not permissive, but it is less informative than the CORRUPT lines G3 prints for a parsed-but-invalid document. Suggest appending ": the clock treats it as a spend trip" for guard and ": the clock treats the station as off the air" for offair. The ruling's G7 wording ("corrupt-document CloudStateError on that key only") accepts the current shape, so this does not block.
- **Minor:** the cli.py:226 wrapper (non-Transmitter exception → `CloudStateError("cannot read <key>: …")`) is behaviourally shadowed by `cloud_lines`' own broad catch. No test drives `cli.status` with a reader that raises. Only the message prefix differs, so this is unpinned but harmless.
- **Minor (cosmetic):** service.py:20 (the errors import) and service.py:329 run past 120 columns. The repo has no lint config, so nothing enforces this.

### Out-of-scope observations
- `raise_verdict` skips the period-end check when the guard's period is unknown, which happens when guard.json is absent or corrupt (status passes guard=None then). A raise that expires after the period end can then show `(honoured)` while the Worker, which takes the period from config (`periodOrNull`), ignores it. This was pre-existing in `budget`. In status it appears only next to a CORRUPT or absent guard line, so it is not a new permissive verdict. Consider `honoured (period end unknown)` at the final review.

### Checks run
- `./.venv/bin/python -c "import transmitter; print(transmitter.__file__)"` resolved inside the worktree.
- Probe, scratch, `python -I`: `cloud_lines` on a corrupt not-tripped guard document and on the brief's document (output quoted above). Real `boto3.client` with a malformed endpoint raises `ValueError: Invalid endpoint: nope`.
- Red-first: `git archive 078e533 packages/transmitter antenna/templates antenna/public pytest.ini` plus 76e3c16's test_service.py, run with PYTHONPATH shadowing: **11 failed, 29 passed**.
- Mutant M1 (scratch copy of 76e3c16, service.py:288 changed to `if True:`). Prediction: survives. Result: test_service.py + test_cli.py, 56 passed, so it survived.
- Suite not re-run (per instructions). The handback reports py3.14 439 passed / 1 skipped, py3.11 the same, and the Debian-12 gate 440 passed.
- Read antenna/src/guard.ts:190-260 (the Worker's guard and offair parse), cloudstate.py, and cli.py `_cloud` / `offair` / `budget` / `status`.
