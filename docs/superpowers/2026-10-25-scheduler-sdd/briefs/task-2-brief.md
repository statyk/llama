### Task 2: Plan lock

**Files:**
- Create: `packages/transmitter/src/transmitter/locks.py`
- Modify: `packages/transmitter/src/transmitter/errors.py`, `workspace.py`, `service.py:300-325`, `cli.py:155-176` (`plan`, `render`)
- Test: `packages/transmitter/tests_transmitter/test_locks.py`, `test_service.py`, `test_cli.py`

**Interfaces:**
- Produces: `errors.PlanLocked(TransmitterError)`; `Workspace.plan_lock_path -> root / "plan.lock"`; `locks.plan_lock(ws: Workspace) -> ContextManager[None]` (creates `ws.root` first, as `publish_lock` does; non-waiting `fcntl.flock(LOCK_EX | LOCK_NB)`, raises `PlanLocked("another transmitter plan or render holds the lock (is `transmitter run` running?); not waiting")`, mirroring `publish.publish_lock`).
- The service wraps each of its plan and render step bodies in `plan_lock`; `Runner._step` treats `PlanLocked` exactly like `PublishLocked` (warning, step skipped, returns False). The `plan` and `render` CLI commands take the lock around their whole body (refusal → `error: …`, exit 1 via `main_cli`). `status` and (later) `schedule` take no lock.

- [ ] **Step 1: Write the failing tests**

```python
# test_locks.py
def test_plan_lock_refuses_a_second_holder(tmp_path):
    ws = Workspace(tmp_path)
    with plan_lock(ws):
        with pytest.raises(PlanLocked):
            with plan_lock(ws):
                pass
    with plan_lock(ws):      # released
        pass
```

```python
# test_cli.py
def test_plan_and_render_refuse_while_locked(tmp_path, monkeypatch):
    # build a config pointing root at tmp_path (as the existing cli tests do), hold plan_lock, invoke
    # `transmitter plan` and `transmitter render` through main_cli/CliRunner: each exits 1 with
    # "another transmitter plan or render holds the lock" on stderr and plan.jsonl is not created.
```

```python
# test_service.py
def test_tick_skips_plan_and_render_while_the_plan_lock_is_held(tmp_path):
    # Runner over make_station + a fake publisher (as existing tick tests do), filling=True;
    # hold plan_lock(st.ws) during runner.tick(NOW): plan.jsonl unchanged, no "plan"/"render"
    # alert fired, publish still ran.
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_locks.py packages/transmitter/tests_transmitter/test_cli.py packages/transmitter/tests_transmitter/test_service.py -q`
Expected: FAIL (`ModuleNotFoundError: transmitter.locks`).

- [ ] **Step 3: Implement** as in Interfaces.

- [ ] **Step 4: Run the transmitter suite** — Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter/src/transmitter/{locks,errors,workspace,service,cli}.py packages/transmitter/tests_transmitter/test_{locks,service,cli}.py
git commit -m "transmitter: plan lock around plan and render (service skips, CLI refuses)"
```

---

