"""campaign_gate's process parser (bulk-apply plan Task 5): rekey_overrides'
`llama_processes`/`_runs_llama`, ported with the tool name a parameter."""
from llama import campaign_gate, station_mark

SELF = "/x/.venv/bin/python scripts/rekey_overrides.py --apply"
MAC_PY = ("/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/"
          "Resources/Python.app/Contents/MacOS/Python")


def test_tool_processes_llama_reruns_the_rekey_cases():
    """The rekey script's own `test_process_check_matches`, re-run with tool="llama"
    (and the script's self-exclusion passed as `self_script`)."""
    match = [
        "601     1 /usr/local/bin/llama run resume --all",
        "602     1 /x/.venv/bin/llama get q",
        "603     1 /usr/bin/python3 -m llama status",
        "604     1 /bin/zsh -c while true; do llama run resume --all; sleep 600; done",
        '605     1 bash -c "llama deliver x"',
        "606     1 /x/.venv/bin/python scripts/replay_holds.py run --all",
        f"607     1 {MAC_PY} /x/.venv/bin/llama get q",
        f"608     1 {MAC_PY} -m llama status",
        "609     1 sh -c FOO=1 llama status",
        "610     1 zsh -c (llama status)",
        "611     1 zsh -c if true; then llama status; else true; fi",
        "612     1 zsh -c true || llama status",
        "613     1 zsh -c echo | llama status",
    ]
    other = [
        "1     0 /sbin/launchd",
        "300     1 /usr/local/bin/llama run resume --all",
        "400   300 zsh -c 'cd /Users/shawn/projects/llama && " + SELF + "'",
        "500   400 " + SELF,
        "701     1 " + SELF,
        "702     1 zsh -c 'cd /Users/shawn/projects/llama && " + SELF + "'",
        f"703     1 {MAC_PY} scripts/rekey_overrides.py --apply",
        "704     1 vim packages/llama/src/llama/junk.py",
        "705     1 -zsh",
        "706     1 python -m pytest",
        f"707     1 {MAC_PY} /x/.venv/bin/pytest -q",
        "708     1 /x/.venv/bin/emcee run",
        "709   500 ps -axo pid=,ppid=,command=",
        "",
        "garbage",
    ]
    got = campaign_gate.tool_processes(other[:4] + match + other[4:], "llama",
                                       self_pid=500, self_script="rekey_overrides.py")
    assert got == match


def test_tool_processes_emcee():
    match = [
        "601     1 emcee run",
        "602     1 /path/.venv/bin/emcee voice x",
        "603     1 python -m emcee status",
        f"604     1 {MAC_PY} /x/.venv/bin/emcee run --yes",
        f"605     1 {MAC_PY} -m emcee voice y",
        "606     1 zsh -c cd /x && emcee run --yes",
    ]
    other = [
        "1     0 /sbin/launchd",
        # The caller and its ancestors never match, even when they run emcee.
        "300     1 /x/.venv/bin/emcee run",
        "400   300 zsh -c 'emcee run'",
        "500   400 /x/.venv/bin/python scripts/bulk_apply.py mark --apply",
        "701     1 grep emcee",
        "702     1 vim emcee.toml",
        "703     1 /x/.venv/bin/llama deliver x",
        # A llama-repo script is not emcee (the check cannot see scripts that
        # import emcee: spec "No concurrent emcee").
        "704     1 /x/.venv/bin/python scripts/backfill_voiced_by.py --apply",
        "705     1 less /x/emcee/README.md",
        "",
    ]
    got = campaign_gate.tool_processes(other[:5] + match + other[5:], "emcee", self_pid=500)
    assert got == match


def test_emcee_running_reads_ps(monkeypatch):
    import os

    me = os.getpid()
    lines = [f"{me}     1 /x/.venv/bin/python -m pytest",
             "9001     1 /x/.venv/bin/emcee run --yes",
             "9002     1 grep emcee"]
    monkeypatch.setattr(campaign_gate, "ps_lines", lambda: lines)
    assert station_mark.emcee_running() == ["9001     1 /x/.venv/bin/emcee run --yes"]
    monkeypatch.setattr(campaign_gate, "ps_lines", lambda: lines[::2])
    assert station_mark.emcee_running() == []


def test_ps_lines_runs_ps(monkeypatch):
    import subprocess

    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="1 0 /sbin/launchd\n2 1 x\n")

    monkeypatch.setattr(campaign_gate.subprocess, "run", fake_run)
    assert campaign_gate.ps_lines() == ["1 0 /sbin/launchd", "2 1 x"]
    assert seen["cmd"] == ["ps", "-axo", "pid=,ppid=,command="]
