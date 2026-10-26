### Task 1: Tolerant plan rows with scheduler fields (deploy to hugo first)

**Files:**
- Modify: `packages/transmitter/src/transmitter/layout.py:22-42`
- Modify: `packages/transmitter/src/transmitter/planner.py:118-158`
- Modify: `packages/transmitter/src/transmitter/site.py:41-62`, `publish.py:239-249`, `service.py:72-93`
- Modify: `docs/playout-setup.md` (rollback note)
- Test: `packages/transmitter/tests_transmitter/test_layout.py`, `test_planner.py`, `test_site.py`, `test_publish.py`, `test_service.py`

**Interfaces:**
- Produces: `PlanRow` fields, all with defaults so phase-1 rows load:
  `kind: str = "show"` (the scheduler writes `"show" | "interstitial"`), `block: str | None = None`, `nominal_start: str | None = None` (ISO UTC of the occurrence's nominal start; with `block` it identifies the occurrence), `role: str | None = None` (`"show" | "id" | "next" | "later"`), `miss: bool | None = None` (set on a block's first show row), `degraded: bool = False`, `fill: str | None = None` (`"pool-short" | "structural"` on fill shows), `bends: tuple[str, ...] = ()`, `names: tuple[tuple[str, str], ...] = ()` (announcement rows: `(block, nominal_start)` of each named occurrence), `package: str | None = None`, `announcement_broken: bool = False`, `extra: Mapping[str, Any]` (unknown keys, default empty, excluded from equality).
  `PlanRow.from_json(data)` puts unknown keys in `extra`; `to_json()` writes known fields then `extra` keys (known fields win on collision). Tuples serialize as JSON lists and parse back to tuples.
- `kind` is validated only as a non-empty string (no closed set). Consumers decide what a kind means: the timeline, `_publish_site` and `row_analysis` skip every kind other than `"show"`; render re-validation (Task 11) treats an unknown kind as not eligible (the skip path).
- Downstream skips, so this deploy-first commit is itself safe against scheduler rows:
  - `site.build_timeline` skips rows whose `kind != "show"` (not in `shows`, not in `recent`);
  - `publish._publish_site` never calls `analysis_for` for them;
  - `service.row_analysis` returns None for them **before** the cache lookup (a clip's analysis is cached, so the guard must come first).

- [ ] **Step 1: Write the failing tests**

```python
# test_layout.py
def test_phase1_row_loads_with_defaults():
    r = PlanRow.from_json({"seq": 0, "slug": "a", "dir": "a", "key": "k", "start_frame": 0,
                           "frames": 10, "run_start": True, "cut_frame": None})
    assert r.kind == "show" and r.block is None and r.bends == () and dict(r.extra) == {}

def test_unknown_keys_survive_a_round_trip():
    data = {"seq": 1, "slug": "a", "dir": "a", "key": "k", "start_frame": 0, "frames": 10,
            "run_start": False, "cut_frame": None, "future_field": {"x": 1}}
    r = PlanRow.from_json(data)
    assert r.extra["future_field"] == {"x": 1}
    assert PlanRow.from_json(r.to_json()).to_json() == r.to_json()
    assert r.to_json()["future_field"] == {"x": 1}

def test_scheduler_fields_round_trip_as_tuples():
    r = PlanRow(seq=2, slug="ann-abc", dir="interstitials", key="k2", start_frame=5, frames=3,
                kind="interstitial", role="next", block="dead-evening",
                nominal_start="2096-10-02T23:00:00Z", names=(("dead-evening", "2096-10-02T23:00:00Z"),),
                bends=("era",))
    back = PlanRow.from_json(json.loads(json.dumps(r.to_json())))
    assert back == r and back.names == (("dead-evening", "2096-10-02T23:00:00Z"),)
```

```python
# test_planner.py
def test_read_plan_keeps_unknown_keys_through_write(tmp_path):
    p = tmp_path / "plan.jsonl"
    p.write_text(json.dumps({"seq": 0, "slug": "a", "dir": "a", "key": "k", "start_frame": 0,
                             "frames": 441, "run_start": True, "cut_frame": None, "zz": 7}) + "\n")
    rows = read_plan(p)
    write_plan(p, rows)
    assert json.loads(p.read_text())["zz"] == 7

def test_read_plan_still_type_checks_known_fields(tmp_path):
    p = tmp_path / "plan.jsonl"
    p.write_text(json.dumps({"seq": "0", "slug": "a", "dir": "a", "key": "k", "start_frame": 0,
                             "frames": 441, "run_start": True, "cut_frame": None}) + "\n")
    with pytest.raises(PlanError):
        read_plan(p)
```

```python
# test_site.py
def test_timeline_lists_no_interstitial_rows(): ...
    # a show row and an interstitial row, both keys present in analyses: only the show is in shows and recent

# test_publish.py
def test_publish_site_never_asks_for_an_interstitial_analysis(tmp_path): ...
    # a publisher whose analysis_for records the rows it is asked for: no row with kind != "show"

# test_service.py
def test_row_analysis_ignores_interstitial_rows_even_when_cached(tmp_path): ...
    # cache/<key>.json written for an interstitial row's key: row_analysis returns None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_layout.py packages/transmitter/tests_transmitter/test_planner.py packages/transmitter/tests_transmitter/test_site.py packages/transmitter/tests_transmitter/test_publish.py packages/transmitter/tests_transmitter/test_service.py -q`
Expected: FAIL (unexpected keyword / missing attributes).

- [ ] **Step 3: Implement**

`PlanRow` stays a frozen dataclass; `extra` is `field(default_factory=dict, compare=False)` typed `Mapping[str, Any]` (wrap in `types.MappingProxyType` so the frozen row is not mutated through it). `from_json` splits known/unknown keys via `dataclasses.fields`, converts `bends` to a tuple and `names` to a tuple of 2-tuples. `to_json` is hand-written: the known fields via `dataclasses.fields` (tuples as lists), then the `extra` keys; never `dataclasses.asdict` (it deep-copies, and `copy.deepcopy` of a `MappingProxyType` raises). `planner._parse_row` keeps its integer/string/bool checks on the phase-1 fields and adds: `kind` is a non-empty string, `bends`/`names` are tuples after parsing. `validate_rows` is unchanged. Then the three downstream skips as in Interfaces.

- [ ] **Step 4: Run the transmitter suite**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Expected: all PASS.

- [ ] **Step 5: Runbook note**

In `docs/playout-setup.md`, under the operations/rollback material, add a short "Rolling transmitter back" subsection. Its text names commits ("this commit", "the commit adding `[interstitials]`"), never plan task numbers: the oldest safe rollback target is this commit; a build from before it cannot read scheduler rows (plan, render and publish wedge), and this commit is also the one that keeps interstitial rows out of `timeline.json`, `notes/` and `show/`; never truncate `plan.jsonl` by hand; before rolling back past the commit adding `[interstitials]`, remove `[interstitials]` from `config.toml`.

- [ ] **Step 6: Commit**

```bash
git add packages/transmitter/src/transmitter/{layout,planner,site,publish,service}.py \
  packages/transmitter/tests_transmitter/test_{layout,planner,site,publish,service}.py docs/playout-setup.md
git commit -m "transmitter: tolerant plan rows with scheduler fields; non-show rows skipped downstream (deploy before the scheduler)"
```

**Operator checkpoint (after Task 1):** this commit is meant to be deployed to hugo on its own, before the scheduler lands, so any later rollback lands on a reader that tolerates scheduler rows. The orchestrator reports it ready to deploy and continues; deployment is the operator's.

---

