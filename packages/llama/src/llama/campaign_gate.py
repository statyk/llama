"""Campaign gates (bulk-apply plan Tasks 5 and 12).

Task 5: the one process parser, ported from `scripts/rekey_overrides.py`
(`llama_processes`/`_runs_llama`) with the tool name a parameter. The station
mark writer uses it to refuse while an `emcee` process runs (spec "No
concurrent emcee"). The script keeps its own copy; it is not changed here.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import PurePosixPath
from typing import Iterable

_SHELLS = frozenset({"sh", "bash", "zsh"})
_SEPARATORS = re.compile(r"&&|\|\||[;|\n]")
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_LEADERS = frozenset({"do", "then", "else", "("})
# A `.py` under a `scripts/` directory counts as llama: this repo's scripts import
# llama. It does not count as emcee: the check cannot see scripts that import emcee
# (`scripts/backfill_*`), and the runbook says not to run them during marking.
_SCRIPTS_RUN = frozenset({"llama"})


def _unquote(word: str) -> str:
    return word.strip("'\"")


def _shell_string(args: list[str]) -> str | None:
    """The `-c` string of a shell's arguments (ps joins argv with spaces, so it is the
    rest of the line), else None. `-c` may sit in an option cluster (`-lc`)."""
    for i, a in enumerate(args):
        if a.startswith("-") and not a.startswith("--") and "c" in a[1:]:
            s = " ".join(args[i + 1:]).strip()
            if len(s) >= 2 and s[0] in "'\"" and s[-1] == s[0]:
                s = s[1:-1]
            return s
    return None


def _simple_commands(s: str) -> list[list[str]]:
    out = []
    for piece in _SEPARATORS.split(s):
        words = [_unquote(w) for w in piece.split()]
        words = [w for w in words if w]
        while words:
            if words[0] in _LEADERS or _ASSIGNMENT.match(words[0]):
                words.pop(0)
            elif words[0].startswith("(") and len(words[0]) > 1:
                words[0] = words[0][1:]
            else:
                break
        if words:
            out.append(words)
    return out


def _runs_tool(words: list[str], tool: str, self_script: str | None) -> bool:
    """`tool` in command position: the first word's basename is `tool`; a python whose
    arguments hold `-m <tool>`, or whose first non-option argument is a `<tool>`
    console script (or, for llama only, a `.py` under a `scripts/` directory other
    than `self_script`); a shell's `-c` string, judged per simple command."""
    if not words:
        return False
    first = _unquote(words[0])
    base = first.rsplit("/", 1)[-1]
    args = [_unquote(w) for w in words[1:]]
    if base == tool:
        return True
    if base.lower().startswith("python"):
        if any(a == "-m" and b == tool for a, b in zip(args, args[1:])):
            return True
        script = next((a for a in args if not a.startswith("-")), None)
        if script is None:
            return False
        p = PurePosixPath(script)
        if p.name == tool:
            # A console script run through its interpreter: how macOS ps shows a venv
            # console script (Homebrew's framework Python re-execs; measured 2026-10-24).
            return True
        return (tool in _SCRIPTS_RUN and p.suffix == ".py" and "scripts" in p.parts[:-1]
                and p.name != self_script)
    if base in _SHELLS:
        s = _shell_string(args)
        return s is not None and any(_runs_tool(c, tool, self_script)
                                     for c in _simple_commands(s))
    return False


def tool_processes(ps_lines: Iterable[str], tool: str, *, self_pid: int,
                   self_script: str | None = None) -> list[str]:
    """The `ps -axo pid=,ppid=,command=` lines whose command runs `tool`: `self_pid`
    and every ancestor of it never match. `self_script` (a basename) is the calling
    script, which never counts as llama under another pid either (rekey's rule)."""
    rows: list[tuple[int, int, str, str]] = []
    for line in ps_lines:
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        rows.append((pid, ppid, parts[2], line.strip()))
    parent = {pid: ppid for pid, ppid, _, _ in rows}
    skip, cur = set(), self_pid
    while cur not in skip:
        skip.add(cur)
        if cur not in parent:
            break
        cur = parent[cur]
    return [line for pid, _, cmd, line in rows
            if pid not in skip and _runs_tool(cmd.split(), tool, self_script)]


def ps_lines() -> list[str]:
    done = subprocess.run(["ps", "-axo", "pid=,ppid=,command="], capture_output=True,
                          text=True, check=True)
    return done.stdout.splitlines()
