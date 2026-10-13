VERDICT: NEEDS FIXES

### Findings

#### Critical
None.

#### Important

**I1. A corrupt or hand-edited local `~/.transmitter/alerts.json` crashes `status` with a traceback, and takes the whole output with it.**
`packages/transmitter/src/transmitter/service.py:311`: `alerts.active_codes(read_json(ws.alerts_path, {}) or {}, ...)`. `read_json` only catches `FileNotFoundError`. Measured with a scratch test: `{not json` raises `json.decoder.JSONDecodeError`, and `[1,2]` raises `AttributeError: 'list' object has no attribute 'items'` (alerts.py:54). Neither is a `TransmitterError`, so `main_cli` shows a traceback. Nothing prints at all, because `cli.status` echoes only after `status_lines` returns. The epoch, plan, lead and cloud half are all lost.
The Dispatcher already handles this file defensively (`alerts.py:121-128` `_load`: catches `(OSError, ValueError)` and treats a non-dict as `{}`), so status is the one reader that is not.
Fix: reuse that logic, for example a module-level `alerts.load_state(path)` that both `Dispatcher._load` and `status_lines` call. An unreadable file prints `alerts     hugo: unreadable (<path>)`.

**I2. A malformed `state/budget.json` crashes the cloud half with a traceback, again losing the local half.**
`service.py:280`: `float(raised.get('budget_usd', 0))`. Measured: `"abc"` gives `ValueError`, and `null`, `[1]` or `{}` give `TypeError`. A JSON NaN would print `$nan`. The Worker tolerates exactly this case: it raises `budget-file-invalid` (R13) and evaluates against the configured budget. So the operator's view crashes on a state the station handles.
The line also shows any raise as if it were in force. An expired raise, one that is not above the base, or one that expires after the period all print `raise $X until Y`, though the Worker ignores them.
Fix: use `cloudstate.raise_verdict(raised, t_us, period_end)`, which already uses `_finite` and returns the reason (`honoured` / `expired` / `ignored: ...`), and print the verdict. This also removes a second, divergent parse of the same document (DRY with `budget`).

**I3. The `offair` line contradicts the station's real state on a malformed flag (spend/on-air view, fail-closed mismatch).**
`service.py:275`: `if offair and offair.get("offair") is True: ... else: "offair     off"`. antenna (`guard.ts:230-237`) treats any present document whose `offair` is not a boolean (`{"offair": "true"}`, `{}`, `{"offair": 1}`) as off the air (fail-closed) and alerts `offair-corrupt`. For the same document, `status` prints `offair     off`.
`guard.json` has a weaker form of the same problem. A hand-edited doc that `cloudstate.guard_doc_problem` rejects is a spend trip to the Worker (R2), but `guard_summary` prints whatever `tripped` says. Measured: `{"tripped": "yes", ...}` prints `guard      TRIPPED (None) since None`, and `{"tripped": false}` without `schema` would print `guard      not tripped`.
Fix: mirror the Worker. offair absent means off, a boolean is that value, and anything else prints `offair     CORRUPT: the clock treats the station as off the air; rewrite with transmitter offair on|off`. For the guard, prefix `guard      CORRUPT (<problem>): the clock treats it as a spend trip` when `guard_doc_problem(guard)` is not None (that helper already exists in cloudstate).

**I4. One unreadable document blanks the whole cloud half, and any non-`TransmitterError` failure loses the local half too (plan-mandated structure).**
`service.py:264-271` reads all four keys inside one `try`, so a corrupt `offair.json`, `budget.json` or `state/alerts.json` (get_json raises `CloudStateError` "... is not JSON") replaces the guard, spend, period and killswitch lines with one `cloud      unavailable: state/offair.json is not JSON`. The guard state is lost exactly when the operator needs it, while R2 itself is readable.
Separately, `cli.status` builds the whole list before echoing anything. So any exception that is not a `TransmitterError` discards the local half that was already computed. That covers I1 and I2. It also covers a body-stream failure inside `cloudstate.get_json`: `resp["Body"].read()` is outside its `except Exception`, and only `ValueError` is caught around the parse. Measured with an injected `ConnectionError` from `Body.read()`: an uncaught traceback. Real cases are botocore `ReadTimeoutError` / `ResponseStreamingError` while R2 is degraded.
That contradicts the spec line the brief quotes ("without them, the local half still prints").
Fix: in `cloud_lines`, read each key separately with its own handling, so a corrupt document prints its own line and the rest still print. In `cli.status`, either echo the local lines before calling the cloud reader, or wrap the cloud half in a broad `except Exception` that prints `cloud      unavailable: <exc>` (a read-only view may catch broadly).
The brief's code has this single-try shape verbatim, so this part is plan-mandated.

**I5. `cli.status`'s client construction can raise a non-`TransmitterError`, giving a traceback and no local half.**
`cli.py:234-237` catches only `TransmitterError` around `_cloud(config)`. I checked the implementer's open question: missing R2 keys are fine, because `r2.make_client` raises `ConfigError`, a `TransmitterError` subclass (r2.py:20; the scratch test passed). But `boto3.client(..., endpoint_url=...)` with a malformed `[publish] endpoint_url` raises `ValueError: Invalid endpoint: not a url` (measured). That escapes, and `status` prints a traceback and nothing else. A typo in config should still leave the local half printing.
Fix: catch `Exception` there (keeping the message), or validate `endpoint_url` in config.

#### Minor

- **M1.** `service.py:291-294`: with no local epoch, `status_lines` returns `["no epoch yet ..."]` before the cloud half. The cloud half does not depend on the epoch. On the Mac, which R14 names as the place to run off-air when hugo is down, there is no local workspace, so `status` never shows guard, offair or killswitch there, even though `cli.status` has already built an R2 client. Consider appending the cloud lines in that branch too.
- **M2.** `cli.py:234`: `_cloud(config)` calls `load_config(config)` a second time, right after `cli.status` loaded it. It is harmless, but `_cloud` could take the loaded cfg.
- **M3.** Test gaps (test_service.py, the two appended tests):
  - none of these branches is exercised: the `raise` line, `offair     off`, `guard_summary(None)`, the `, expected until` suffix, `cli.status`'s `TransmitterError` catch;
  - the cloud-alerts `active` filter is not pinned: the fixture holds only active entries, so dropping `e.get("active")` stays green;
  - no test feeds a corrupt or partial document to `status` at all, which is how I1-I4 got through.
  Add one test per corrupt document (local alerts.json bytes and list; budget_usd string; offair `"true"`; offair.json not JSON) asserting that the local half and the other cloud lines still print.
- **M4.** `cloud_lines` prints raw values without validation, so hand-edited docs produce lines like `offair     ON since None (None), expected until 5` and `alerts     cloud: b` for a non-dict entry, which is filtered correctly but shows how loose the rendering is. Cosmetic once I3 is fixed.

### Cannot verify from diff
- Whether the pre-existing local readers `status` relies on survive corrupt bytes: `load_epoch` (a `ValueError` on bad JSON, a `KeyError` on a missing `epoch_id`), `read_plan`, `load_publish_state`, `load_fallback_version`. They predate this task (Task 12 and earlier), but they share I1's failure mode on hand-edited state. I did not crawl them.
- That `cloudstate.get_json`'s uncaught `Body.read()` path (Task 12 code) is also a problem for `budget` / `offair`. It is noted here only as it affects `status`.

### Strengths
- `status` writes nothing. The read path is `load_epoch` (not `load_or_create_epoch`), `read_plan`, `load_publish_state`, `load_fallback_version` and `read_json`, all read-only, and the cloud half issues only `get_object`. No PUT, no mkdir.
- The tests inject `cloud=` (`docs.get`, plus a raising callable) and never reach the network. `test_status_before_anything` (test_cli.py) has no bucket, so `_cloud` raises `ConfigError` before any client is built.
- The `anchors` line matches R17 verbatim.
- hugo alerts go through `alerts.active_codes`, so a stale event drops off (R16). The test pins this with a 1970 `publish` event and an inactive `render` level code.
- The happy path is clear and uses the shared `guard_summary` rather than a second renderer.
- The `cloud_error` fallback line is pinned to its exact text.

### Checks run
- **Risk: missing R2 keys are not a `TransmitterError`, so `cli.status` would crash.** Read `r2.make_client` (`ConfigError`, r2.py:20) and `errors.py` (`ConfigError(TransmitterError)`). Scratch test `test_missing_keys_is_transmitter_error`: PASSED.
- **Risk: other client-construction failures escape.** Scratch test `test_bad_endpoint` (`endpoint_url="not a url"`): `ValueError: Invalid endpoint` escaped (I5).
- **Risk: a corrupt local alerts.json crashes `status`.** Scratch test `test_local_alerts_corrupt[{not json]` gave `JSONDecodeError`, and `[[1,2]]` gave `AttributeError` (I1). Compared with `Dispatcher._load` (alerts.py:121-128), which handles both.
- **Risk: a malformed budget.json crashes `status`.** Scratch test `test_budget_usd_odd` with `abc`, `None`, `[1]` and `{"x":1}`: all four gave `ValueError`/`TypeError` at service.py:280 (I2).
- **Risk: a hand-edited guard / offair / cloud alerts doc crashes `status` or misreports.** Scratch test `test_guard_odd_shapes`: no crash. Output included `guard      TRIPPED (None) since None`, `killswitch unknown`, `offair     ON since None (None), expected until 5`, `alerts     cloud: b`. Compared offair handling with antenna `guard.ts:230-237` (a non-boolean `offair` means off air) (I3).
- **Risk: an R2 read failure that is not a `TransmitterError`.** Scratch test `test_body_read_error`, a client whose `Body.read()` raises `ConnectionError`: an uncaught traceback (I4).
- **Risk: status writes local or R2 state.** Read the status read path (`workspace.load_epoch`, `read_json`, `alerts.active_codes`, `cloudstate.get_json`): no writes. `git status --short` in the worktree after probing: clean.
- **Risk: tests reach the network.** Read both new tests (an injected `cloud=`) and `test_cli.py:51` (no bucket, so `ConfigError` comes before `make_client`).
- **Command** (from `packages/transmitter`, scratch file outside the worktree, nothing written to the worktree):
  `.venv/bin/python -m pytest -p no:cacheprovider <scratchpad>/t16q/test_probe_t16.py -q --rootdir=<scratchpad>`
  Result: `8 failed, 2 passed`. The failures are the probes listed above, which demonstrate I1, I2, I4 and I5. The passes are `test_guard_odd_shapes` and `test_missing_keys_is_transmitter_error`.
  `import transmitter` resolved inside the worktree.
