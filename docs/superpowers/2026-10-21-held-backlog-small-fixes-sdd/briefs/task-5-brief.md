### Task 5: Slice C, `redo` as a unit; runs survive a refused show

**Files:**
- Modify: `packages/llama/src/llama/cli.py` (`_redo_show` → `_redo_show_locked` + `_redo_show`; `_execute._process`'s except tuple)
- Modify: `packages/llama/tests/helpers.py` (add `packaged_gd73`)
- Modify: `CLAUDE.md` (one sentence each in the `llama redo` command line and the "Failure records" gotcha)
- Test: `packages/llama/tests/test_redo_cmd.py`, `test_pace_loop.py`, `test_reapply.py`

**Interfaces:**
- Consumes: Task 4's `show_unit` (with `expect=None`), `ShowChanged`.
- Produces:
  - `cli._redo_show_locked(config, ia, ledger, entry, from_stage: str, *, with_research: bool = False) -> Path | None`: today's `_redo_show` body without the `file_lock`. The caller must already be inside a `show_unit` for `entry.ws`. It reads `provenance.json` itself, under the caller's lock (not `entry.provenance`). When it is absent it raises `ShowChanged(f"{entry.slug}: the show was removed; nothing changed")` if `entry.provenance` was set when the entry was resolved (the show was removed while this command waited for the lock), else today's `LlamaError(f"no provenance.json in {entry.ws.dir} - reprocess it via its run first")` (plan's call: a show that never had provenance was not removed). Apart from that check it uses only `entry.ws` and `entry.slug`. The positional shape matches today's test stubs `(config, ia, ledger, e, stage, **kw)`, so Tasks 6-7 retarget those stubs by attribute name alone.
  - `cli._redo_show(config, ia, ledger, entry, from_stage: str, *, with_research: bool = False) -> Path | None`: `with show_unit(entry.ws, None): return _redo_show_locked(...)`. A redo shows no content, so its view is read after the lock is acquired and the unit's check always passes: single and batch redo wait behind another writer instead of refusing, and a show removed meanwhile is refused by `_redo_show_locked`. `redo` (single), `_redo_batch` and every existing `_redo_show` stub keep working unchanged.
  - `helpers.packaged_gd73(tmp_path, monkeypatch) -> tuple[Path, ShowWorkspace]`: writes `config.toml` (`root = tmp_path`, `[jerrybase] enabled = false`), patches `cli.make_providers = test_pipeline.fake_providers` and `cli.IAClient = test_pipeline.FakeIA`, and runs `get "GD 1973" --auto --name r`. It returns `(cfg_path, ws)` for `shows/gratefuldead-1973-06-10`, which is packaged with `package/audio/*` (64-byte files). Import `test_pipeline` inside the function.

- [ ] **Step 1: Add `helpers.packaged_gd73` (test infrastructure), then write the failing tests**

`test_redo_cmd.py` imports (in addition to the file's own): `import shutil`, `import pytest`, `import llama.pipeline as pipeline`, `from helpers import packaged_gd73, tree_bytes`, `from herder import TaskFailed`, `from llama.config import load_config`, `from llama.errors import LlamaError`, `from llama.ia_client import IAError`, `from llama.ledger import Ledger`, `from llama.locks import Locked, file_lock`, `from llama.show_unit import ShowChanged`, `from llama.workspace import atomic_write_bytes`, `from test_catalog import build`. `test_pace_loop.py` adds `from llama.errors import LlamaError`. `test_reapply.py` adds `from llama.models import Overrides`.

`test_redo_cmd.py`:
```python
def test_failed_redo_from_brief_restores_every_file(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch); before = tree_bytes(ws.dir)
    monkeypatch.setattr(pipeline, "run_brief", lambda *a, **k: (_ for _ in ()).throw(TaskFailed("boom")))
    r = runner.invoke(cli.app, ["--config", str(cfg), "redo", "gratefuldead", "--from", "brief"])
    assert r.exit_code == 1 and isinstance(r.exception, TaskFailed)
    assert tree_bytes(ws.dir) == before            # provenance.json's processed_at included

def test_package_failure_on_purged_audio_removes_new_audio_and_restores_manifest(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch)
    for f in (ws.package_dir / "audio").iterdir():
        f.unlink()                                  # as `deliver` purges
    before = tree_bytes(ws.dir)
    from test_pipeline import FakeIA
    class SecondFails(FakeIA):
        n = 0
        def download_file(self, identifier, filename, dest, md5=None):
            SecondFails.n += 1
            if SecondFails.n == 2:
                raise IAError("download of x failed")
            return super().download_file(identifier, filename, dest, md5)
    monkeypatch.setattr(cli, "IAClient", SecondFails)
    r = runner.invoke(cli.app, ["--config", str(cfg), "redo", "gratefuldead", "--from", "package"])
    assert r.exit_code == 1 and isinstance(r.exception, IAError)
    assert tree_bytes(ws.dir) == before and list((ws.package_dir / "audio").iterdir()) == []

def test_keyboard_interrupt_after_the_drop_restores_and_re_raises(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch); before = tree_bytes(ws.dir)
    monkeypatch.setattr(pipeline, "run_brief", lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()))
    # through the function, not the runner: click turns KeyboardInterrupt into "Aborted!"
    config = load_config(cfg); ledger = Ledger(config.root / "ledger.jsonl")
    entry = cli._resolve_show(config, ledger, "gratefuldead")
    with pytest.raises(KeyboardInterrupt):
        cli._redo_show(config, cli.IAClient(), ledger, entry, "brief")
    assert tree_bytes(ws.dir) == before and not (ws.dir / ".txn").exists()

def test_a_redo_of_a_show_removed_while_it_waited_refuses_with_the_removed_message(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch)
    config = load_config(cfg); ledger = Ledger(config.root / "ledger.jsonl")
    entry = cli._resolve_show(config, ledger, "gratefuldead")
    shutil.rmtree(ws.dir)                           # `llama rm` ran while this redo waited for the lock
    with pytest.raises(ShowChanged, match="gratefuldead-1973-06-10: the show was removed; nothing changed"):
        cli._redo_show(config, cli.IAClient(), ledger, entry, "brief")
    assert [p.name for p in ws.dir.iterdir()] == [".lock"]   # spec C2's documented husk

def test_a_leftover_txn_is_deleted_not_restored_by_the_next_redo(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch)
    atomic_write_bytes(ws.dir / ".txn" / "files" / "show.json", b"STALE")
    r = runner.invoke(cli.app, ["--config", str(cfg), "redo", "gratefuldead", "--from", "package"])
    assert r.exit_code == 0, r.output
    assert ws.show.read_bytes() != b"STALE" and not (ws.dir / ".txn").exists()

def test_redo_runs_the_pipeline_inside_the_show_lock(tmp_path, monkeypatch):   # (pin)
    cfg, ws = packaged_gd73(tmp_path, monkeypatch); seen = []
    def probe(*a, **k):
        try:
            with file_lock(ws.lock, blocking=False):
                seen.append("free")
        except Locked:
            seen.append("held")
        raise TaskFailed("stop")
    monkeypatch.setattr(pipeline, "run_brief", probe)
    runner.invoke(cli.app, ["--config", str(cfg), "redo", "gratefuldead", "--from", "brief"])
    assert seen == ["held"]

def test_redo_batch_restores_a_failed_show_and_continues(tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"; cfg.write_text(f'root = "{tmp_path}"\n')
    a = build(tmp_path, "aready", stages={"select", "gather", "research", "vet", "package"})
    build(tmp_path, "bready", stages={"select", "gather", "research", "vet", "package"})
    before, done = tree_bytes(a.dir), []
    def fake(config, ia, ledger, e, stage, **kw):
        write_artifact(e.ws.show, {"half": "written"})
        if e.slug == "aready":
            raise LlamaError("boom")
        done.append(e.slug)
        return e.ws.package_dir
    monkeypatch.setattr(cli, "_redo_show_locked", fake)
    r = runner.invoke(cli.app, ["--config", str(cfg), "redo", "--packaged", "--from", "package", "--yes"])
    assert r.exit_code == 0 and "FAILED aready: boom" in r.output and done == ["bready"]
    assert tree_bytes(a.dir) == before
```
`test_pace_loop.py`:
```python
def test_a_show_refusing_its_overrides_is_a_per_show_failure_and_the_run_continues(tmp_path, monkeypatch):
    def _process(pid):
        if pid == "a":
            raise LlamaError("overrides.encore_after (20) must be greater than every set break [10, 20]")
        return f"{pid}/pkg"
    _, seen = _drive(tmp_path, monkeypatch, _process, ["a", "b"])
    assert seen == ["a", "b"]
    s = iter_sessions(tmp_path)[0]
    assert s.state == STATE_INCOMPLETE
    assert [(f["show"], f["kind"]) for f in s.failures] == [("a", "other")]
```

`test_reapply.py` **(pin)**:
```python
def test_reapply_on_refused_overrides_raises_and_writes_nothing(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    write_artifact(entry.ws.overrides, Overrides(set_breaks=[2, 4], encore_after=4))
    before = _snapshot(entry.ws)
    with pytest.raises(LlamaError, match="overrides\\.(encore_after|set_breaks)"):
        _run(config, ledger, entry)
    assert _snapshot(entry.ws) == before
```

- [ ] **Step 2: Run them and see them fail**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_redo_cmd.py packages/llama/tests/test_pace_loop.py packages/llama/tests/test_reapply.py -q -k "restores or leftover or removed_while or inside_the_show_lock or refusing_its_overrides or refused_overrides"`
Expected: the restore, leftover, removed-show and batch tests FAIL (files are left dropped, `_redo_show_locked` does not exist, and today's redo rebuilds a removed show from the provenance it read before the lock). The run test FAILs because a `LlamaError` aborts `_execute`. The two **(pin)** tests (the show-lock test and the reapply test) PASS.

- [ ] **Step 3: Implement**

- Split `_redo_show` as specified in Interfaces. `process_show` is unchanged and lock-free.
- Limitation, not mechanism: the unit protects `entry.ws`, while `process_show` writes to `show_ws(prov.performance_id)`. A show directory whose name is not `slugify(performance_id)` (renamed by hand) is outside the guarantee, as today.
- In `_execute._process`, change `except (TaskFailed, HerderError, IAError) as exc:` to `except (TaskFailed, HerderError, LlamaError) as exc:`. Keep the `RateLimited` arm above it. `classify_failure` already maps `IAError`→`archive`/`download`, and any other `LlamaError` falls through to `other`.
- In `CLAUDE.md`'s command list, after `llama redo <name> --from <stage>`, add: "(one unit: see `llama fix` below)". In the "Failure records" gotcha, add: "a per-show `LlamaError` (e.g. gather refusing the show's overrides) is a per-show failure of kind `other`, not a run abort."

- [ ] **Step 4: Run the targeted tests, then the full suite**

Run: the Step 2 command, then `./.venv/bin/python -m pytest -q`
Expected: PASS. Existing `_redo_show` stubs in `test_redo_cmd.py`/`test_profile_selector.py` are unchanged and green.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/cli.py packages/llama/tests/helpers.py packages/llama/tests/test_redo_cmd.py packages/llama/tests/test_pace_loop.py packages/llama/tests/test_reapply.py CLAUDE.md
git commit -m "feat(redo): every redo is a restoring unit; a refused show no longer aborts a run (slice C)"
```

---

