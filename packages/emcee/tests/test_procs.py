"""emcee.procs: the `ps` check the title backfill runs before `--yes` writes,
a port of llama's `campaign_gate._runs_tool` (emcee cannot import llama)."""
import subprocess

from emcee import procs

MAC_PY = ("/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/"
          "Resources/Python.app/Contents/MacOS/Python")
TOOLS = ("emcee", "llama")


def test_tool_lines_matches_emcee_and_llama_but_not_self_or_ancestors():
    match = [
        "601     1 emcee run",
        "602     1 /path/.venv/bin/emcee voice x",
        "603     1 python -m emcee status",
        f"604     1 {MAC_PY} /x/.venv/bin/emcee run --yes",
        f"605     1 {MAC_PY} -m emcee voice y",
        "606     1 zsh -c cd /x && emcee run --yes",
        "607     1 /usr/local/bin/llama run resume --all",
        f"608     1 {MAC_PY} /x/.venv/bin/llama get q",
        "609     1 sh -c FOO=1 llama status",
        "610     1 zsh -c (llama status)",
        "611     1 zsh -c if true; then llama status; else true; fi",
        "612     1 zsh -c true || emcee status",
        "613     1 zsh -c echo | llama status",
        # A scripts/*.py counts for both tools: scripts/backfill_* import emcee.
        "614     1 /x/.venv/bin/python scripts/backfill_voiced_by.py --apply",
    ]
    other = [
        "1     0 /sbin/launchd",
        # The caller and its ancestors never match, even when they run a tool.
        "300     1 /x/.venv/bin/llama run resume --all",
        "400   300 zsh -c 'emcee retitle --yes'",
        f"500   400 {MAC_PY} /x/.venv/bin/emcee retitle --yes",
        "701     1 grep emcee",
        "702     1 vim emcee.toml",
        "703     1 less /x/emcee/README.md",
        "704     1 vim packages/llama/src/llama/junk.py",
        "705     1 -zsh",
        "706     1 python -m pytest",
        f"707     1 {MAC_PY} /x/.venv/bin/pytest -q",
        "708     1 python other/thing.py",
        "709   500 ps -axo pid=,ppid=,command=",
        "",
        "garbage",
        "x y z",
    ]
    lines = other[:4] + match + other[4:]
    assert procs.tool_lines(lines, TOOLS, self_pid=500) == match
    # One tool at a time narrows it; the scripts/ rule holds for either.
    emcee_only = procs.tool_lines(lines, ("emcee",), self_pid=500)
    assert emcee_only == [m for m in match if "llama" not in m.split(None, 2)[2]]
    assert match[-1] in emcee_only


def test_tool_lines_matches_campaign_gate_cases():
    match = [
        "601     1 python3 scripts/backfill_voiced_on.py",
        "602     1 python scripts/bulk_apply.py mark --wave 3",
        "603     1 python -m llama",
        "604     1 llama deliver x",
        "605     1 emcee run",
        "606     1 bash -c 'cd x && llama status'",
        '607     1 bash -c "llama deliver x"',
        "608     1 /bin/zsh -c while true; do llama run resume --all; sleep 600; done",
        "609     1 zsh -lc 'emcee status'",
    ]
    other = [
        "701     1 code ~/projects/llama",
        "702     1 git -C ~/projects/llama status",
        "703     1 bash -c 'echo llama'",
        "704     1 python -c print('emcee')",
    ]
    assert procs.tool_lines(other + match, TOOLS, self_pid=999) == match


def test_other_tool_processes_reads_ps(monkeypatch):
    import os
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        out = f"{os.getpid()} 1 emcee retitle --yes\n42 1 llama status\n43 1 vim x\n"
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

    monkeypatch.setattr(procs.subprocess, "run", fake_run)
    assert procs.other_tool_processes() == ["42 1 llama status"]
    assert seen["cmd"] == ["ps", "-axo", "pid=,ppid=,command="]
    assert procs.other_tool_processes(("emcee",)) == []
