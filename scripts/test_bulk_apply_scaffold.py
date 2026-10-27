"""scripts/bulk_apply.py scaffold: pin, arm gate, snapshot/seal/restore wrappers
(bulk-apply plan Task 12). No test touches the real library, tools or processes."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "llama" / "tests"))

import bulk_apply as ba
from llama import batch_snapshot, campaign_gate


def _config(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "lib"
    (root / "shows").mkdir(parents=True)
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'root = "{root}"\n')
    return cfg, root


def _git_repo(tmp_path: Path) -> str:
    repo = tmp_path / "repo"
    repo.mkdir()
    def g(*a):
        return subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True,
                              text=True).stdout.strip()
    g("init", "-q")
    g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x")
    g("tag", "v2.20.0")
    g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "y")
    g("tag", "v2.20.1")
    return g("rev-parse", "v2.20.0^{commit}")


def test_pin_requires_the_running_code(tmp_path, monkeypatch, capsys):
    cfg, root = _config(tmp_path)
    sha = _git_repo(tmp_path)
    monkeypatch.setattr(ba, "REPO", tmp_path / "repo")
    monkeypatch.setattr(ba, "code_identity", lambda: sha + "-dirty")
    assert ba.main(["pin", "--tag", "v2.20.0", "--config", str(cfg)]) == 2          # dirty
    monkeypatch.setattr(ba, "code_identity", lambda: sha)
    assert ba.main(["pin", "--tag", "v2.20.1", "--config", str(cfg)]) == 2          # mismatched
    assert ba.main(["pin", "--tag", "nope", "--config", str(cfg)]) == 2             # no such tag
    assert campaign_gate.read_pin(root) is None
    assert ba.main(["pin", "--tag", "v2.20.0", "--config", str(cfg)]) == 0
    pin = campaign_gate.read_pin(root)
    assert pin["sha"] == sha and pin["tag"] == "v2.20.0" and pin["worktree"] == str(tmp_path / "repo")
    assert ba.main(["pin", "--tag", "v2.20.0", "--config", str(cfg)]) == 2          # needs --replace
    assert ba.main(["pin", "--tag", "v2.20.0", "--replace", "--config", str(cfg)]) == 0


def test_arm_refuses_without_a_pin(tmp_path, monkeypatch, capsys):
    cfg, root = _config(tmp_path)
    called = []
    monkeypatch.setattr(ba.replay_holds, "run", lambda a: called.append(a) or 0)
    assert ba.main(["arm", "--out", str(tmp_path / "arm.json"), "--config", str(cfg)]) == 2
    assert "pin" in capsys.readouterr().err
    assert not called


def test_arm_runs_the_replay_over_all_shows(tmp_path, monkeypatch):
    cfg, root = _config(tmp_path)
    campaign_gate.write_pin(root, tag="v2.20.0", sha="abc", version="2.20.0", worktree="/w",
                            replace=False)
    monkeypatch.setattr("llama.replay.code_identity", lambda: "abc")
    seen = {}
    monkeypatch.setattr(ba, "require_tools", lambda echo, *, pin: seen.setdefault("pin", pin))
    monkeypatch.setattr(ba.replay_holds, "run", lambda a: seen.setdefault("args", a) and 0)
    assert ba.main(["arm", "--out", str(tmp_path / "arm.json"), "--config", str(cfg)]) == 0
    assert seen["pin"]["version"] == "2.20.0"
    assert seen["args"].all is True and seen["args"].out == tmp_path / "arm.json"


def test_restore_cli_dry_run_reports(tmp_path, monkeypatch, capsys):
    cfg, root = _config(tmp_path)
    slugs = tmp_path / "slugs.txt"
    slugs.write_text("alpha\n")
    d = root / "shows" / "alpha"
    d.mkdir()
    (d / "show.json").write_text("{}")
    assert ba.main(["snapshot", "--slugs", str(slugs), "--config", str(cfg)]) == 0
    snaps = list((root / "campaign" / "snapshots").iterdir())
    assert len(snaps) == 1
    (d / "show.json").write_text('{"changed": 1}')
    batch_snapshot.record_after(snaps[0], "alpha", root, station_root=None)   # the batch's write
    before = (d / "show.json").read_bytes()
    assert ba.main(["restore", str(snaps[0]), "--config", str(cfg)]) == 0
    out = capsys.readouterr().out
    assert "alpha:" in out
    assert (d / "show.json").read_bytes() == before                  # dry run wrote nothing
    assert ba.main(["restore", str(snaps[0]), "--apply", "--config", str(cfg)]) == 0
    assert (d / "show.json").read_bytes() == b"{}"
    assert ba.main(["seal", str(snaps[0]), "--config", str(cfg)]) == 0
    assert ba.main(["restore", str(tmp_path / "missing"), "--config", str(cfg)]) == 2


def test_pin_version_comes_from_the_tag(tmp_path, monkeypatch):
    cfg, root = _config(tmp_path)
    sha = _git_repo(tmp_path)
    monkeypatch.setattr(ba, "REPO", tmp_path / "repo")
    monkeypatch.setattr(ba, "code_identity", lambda: sha)
    monkeypatch.setattr(ba.llama, "__version__", "0.1.0")
    assert ba.main(["pin", "--tag", "v2.20.0", "--config", str(cfg)]) == 0
    assert campaign_gate.read_pin(root)["version"] == "2.20.0"


def test_pin_refuses_a_tag_that_is_not_a_version(tmp_path, monkeypatch):
    cfg, root = _config(tmp_path)
    sha = _git_repo(tmp_path)
    subprocess.run(["git", "-C", str(tmp_path / "repo"), "tag", "release-x"], check=True)
    monkeypatch.setattr(ba, "REPO", tmp_path / "repo")
    monkeypatch.setattr(ba, "code_identity", lambda: subprocess.run(
        ["git", "-C", str(tmp_path / "repo"), "rev-parse", "release-x^{commit}"],
        capture_output=True, text=True).stdout.strip())
    assert ba.main(["pin", "--tag", "release-x", "--config", str(cfg)]) == 2
    assert campaign_gate.read_pin(root) is None


def test_pin_and_tool_gate_agree_end_to_end(tmp_path, monkeypatch):
    import types
    cfg, root = _config(tmp_path)
    sha = _git_repo(tmp_path)
    monkeypatch.setattr(ba, "REPO", tmp_path / "repo")
    monkeypatch.setattr(ba, "code_identity", lambda: sha)
    monkeypatch.setattr(ba.llama, "__version__", "0.0.0+unknown")
    assert ba.main(["pin", "--tag", "v2.20.0", "--config", str(cfg)]) == 0
    def run(cmd, **kw):
        if cmd[0] == "which":
            return types.SimpleNamespace(returncode=0, stdout=f"/a/{cmd[2]}\n", stderr="")
        return types.SimpleNamespace(returncode=0, stdout="2.20.0\n", stderr="")
    monkeypatch.setattr(campaign_gate.subprocess, "run", run)
    campaign_gate.require_tools(lambda _m: None, pin=campaign_gate.read_pin(root))
