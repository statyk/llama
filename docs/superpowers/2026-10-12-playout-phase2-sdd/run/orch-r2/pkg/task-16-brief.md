### Task 16: Extended `transmitter status`

**Model hint:** sonnet

**Files:**
- Modify: `service.py` (`cloud_lines`, `status_lines`), `cli.py` (`status`)
- Modify (tests): `test_service.py` (append)

**Interfaces:**
- Consumes: `cloudstate.get_json`, `guard_summary`, the keys (Task 12); `cli._cloud` (Task 12); `Workspace.alerts_path` and `alerts.active_codes` (Task 13).
- Produces:
  - `service.cloud_lines(read) -> list[str]`, where `read(key) -> dict | None` and a `TransmitterError` is printed as `cloud      unavailable: …`.
  - `service.status_lines(cfg, t_us, cloud=None, cloud_error=None)`, with new lines after `fallback`:
    - `anchors    none (the scheduler and its window misses are phase 3)`;
    - `alerts     hugo: …` (`alerts.active_codes`: an event code drops off once `repeat_hours` pass without a new fire);
    - then the guard (`guard`, `spend`, `period`, `reading`, `killswitch`), `offair`, `raise`, and `alerts     cloud: …`.

Spec "Alerts and operations": status shows what is on air, the lead, next anchors, misses, empty-anchor warnings (those three are phase 3), `tripped` with its reason, `offair`, and active alarms. It needs R2 keys for the cloud half; without them, the local half still prints.

- [ ] **Step 1: Write the failing tests**

Append to `tests_transmitter/test_service.py`:

```python
def _with_epoch(st):
    from transmitter.workspace import write_json
    write_json(st.ws.epoch_path, {"epoch_id": "etest", "epoch": st.epoch.iso, "d": 10.24})
    return st


def test_status_shows_the_cloud_state_and_active_alerts(tmp_path):
    import json as _json

    st = _with_epoch(make_station(tmp_path)[0])
    (st.ws.root / "alerts.json").write_text(_json.dumps({"dead-clock": {"active": True}, "render": {"active": False},
                                                         "publish": {"active": True, "last_fired_at": 0.0}}))
    docs = {
        "state/guard.json": {"tripped": True, "reason": "blind", "tripped_at": "2026-10-20T06:00:00.000Z",
                             "last_error": "analytics: HTTP 503", "last_success": "2026-10-20T00:00:00.000Z",
                             "waf": {"enabled": True, "error": None}},
        "state/offair.json": {"offair": True, "reason": "objection", "since": "2026-10-20T05:00:00.000Z", "until": None},
        "state/alerts.json": {"tripped-blind": {"active": True}},
    }
    lines = service.status_lines(st.cfg, NOW, cloud=docs.get)
    text = "\n".join(lines)
    assert "alerts     hugo: dead-clock" in lines           # the 1970 publish event has gone stale
    assert "guard      TRIPPED (blind)" in text and "reading    failing since 2026-10-20T00:00:00.000Z" in text
    assert "killswitch enabled" in text
    assert "offair     ON since 2026-10-20T05:00:00.000Z (objection)" in text
    assert "alerts     cloud: tripped-blind" in text
    assert "anchors    none" in text


def test_status_without_cloud_access_still_prints_the_local_half(tmp_path):
    from transmitter.errors import CloudStateError

    st = _with_epoch(make_station(tmp_path)[0])

    def broken(key):
        raise CloudStateError("cannot read state/guard.json: boom")

    assert service.status_lines(st.cfg, NOW, cloud=broken)[-1] == "cloud      unavailable: cannot read state/guard.json: boom"
    assert service.status_lines(st.cfg, NOW, cloud_error="set R2_ACCESS_KEY_ID")[-1] == \
        "cloud      unavailable: set R2_ACCESS_KEY_ID"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_service.py -q`
Expected: FAIL. `status_lines()` does not take `cloud`.

- [ ] **Step 3: Implement**

`service.py`: add `cloudstate` to `from transmitter import …`, add this before `status_lines`, and change the signature of `status_lines`:

```python
def cloud_lines(read: Callable[[str], dict | None]) -> list[str]:
    """`status`'s cloud half: the guard, the operator's flag, a raise, cloud
    alerts. `read(key)` returns a state/ document or None (cloudstate.get_json)."""
    try:
        guard = read(cloudstate.GUARD_KEY)
        offair = read(cloudstate.OFFAIR_KEY)
        raised = read(cloudstate.BUDGET_KEY)
        cloud_alerts = read(cloudstate.ALERTS_KEY) or {}
    except TransmitterError as exc:
        return [f"cloud      unavailable: {exc}"]
    lines = cloudstate.guard_summary(guard)
    if offair and offair.get("offair") is True:
        lines.append(f"offair     ON since {offair.get('since')} ({offair.get('reason')})"
                     + (f", expected until {offair['until']}" if offair.get("until") else ""))
    else:
        lines.append("offair     off")
    if raised:
        lines.append(f"raise      ${float(raised.get('budget_usd', 0)):.2f} until {raised.get('expires')}")
    active = sorted(k for k, e in cloud_alerts.items() if isinstance(e, dict) and e.get("active"))
    lines.append(f"alerts     cloud: {', '.join(active) if active else 'none'}")
    return lines


def status_lines(cfg: TransmitterConfig, t_us: int, cloud: Callable[[str], dict | None] | None = None,
                 cloud_error: str | None = None) -> list[str]:
```

and replace the end of `status_lines`:

```python
    lines.append(f"fallback   {fb}" if fb else "fallback   none (run `transmitter fallback render`)")
    return lines
```

with:

```python
    lines.append(f"fallback   {fb}" if fb else "fallback   none (run `transmitter fallback render`)")
    lines.append("anchors    none (the scheduler and its window misses are phase 3)")
    hugo = alerts.active_codes(read_json(ws.alerts_path, {}) or {}, t_us / 1e6, cfg.alerts.repeat_hours * 3600)
    lines.append(f"alerts     hugo: {', '.join(hugo) if hugo else 'none'}")
    if cloud is not None:
        lines += cloud_lines(cloud)
    elif cloud_error:
        lines.append(f"cloud      unavailable: {cloud_error}")
    return lines
```

`cli.py` `status` becomes:

```python
@app.command()
def status(config: Path = CONFIG_OPT):
    """Epoch, plan, on air, lead, fallback; the cost guard, off-air flag, kill switch and active alerts."""
    cfg = load_config(config)
    cloud, error = None, None
    try:
        client, bucket = _cloud(config)
        cloud = lambda key: cloudstate.get_json(client, bucket, key)  # noqa: E731
    except TransmitterError as exc:                # no bucket or no R2 keys: the local half still prints
        error = str(exc)
    for line in service.status_lines(cfg, service.now_us(), cloud, error):
        typer.echo(line)
```

- [ ] **Step 4: Run the transmitter suite on both Pythons, and the Debian-12 gate**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q && ./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Expected: PASS. If Docker is available, `packages/transmitter/scripts/test-in-debian12.sh -q` passes too.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): status shows the cost guard, off-air flag, kill switch and active alerts"
```

---
