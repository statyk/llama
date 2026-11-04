"""Which other `emcee` or `llama` processes are running (a `ps` check).

The title backfill refuses to write while one runs: the station lock cannot
stop tools that ignore it (the one-off `scripts/backfill_*.py`, the campaign
worktree pinned at an older llama). The matching is a port of llama's
`campaign_gate._runs_tool` and its helpers; emcee cannot import llama, so it
keeps its own copy. One difference: a `.py` under a `scripts/` directory
counts for BOTH tools here (llama's copy counts it for llama only), because
`scripts/backfill_*` import emcee.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import PurePosixPath
from typing import Iterable, Sequence

_SHELLS = frozenset({"sh", "bash", "zsh"})
_SEPARATORS = re.compile(r"&&|\|\||[;|\n]")
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_LEADERS = frozenset({"do", "then", "else", "("})


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


def _runs_tool(words: list[str], tool: str) -> bool:
    """`tool` in command position: the first word's basename is `tool`; a python whose
    arguments hold `-m <tool>`, or whose first non-option argument is a `<tool>`
    console script or a `.py` under a `scripts/` directory; a shell's `-c` string,
    judged per simple command."""
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
            # A console script run through its interpreter: how macOS ps shows a
            # venv console script (Homebrew's framework Python re-execs).
            return True
        return p.suffix == ".py" and "scripts" in p.parts[:-1]
    if base in _SHELLS:
        s = _shell_string(args)
        return s is not None and any(_runs_tool(c, tool) for c in _simple_commands(s))
    return False


def tool_lines(ps_lines: Iterable[str], tools: Sequence[str], *, self_pid: int) -> list[str]:
    """The `ps -axo pid=,ppid=,command=` lines whose command runs any of `tools`:
    `self_pid` and every ancestor of it never match. Pure."""
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
            if pid not in skip and any(_runs_tool(cmd.split(), t) for t in tools)]


def other_tool_processes(tools: Sequence[str] = ("emcee", "llama")) -> list[str]:
    """The ps lines of running `tools` processes other than this one and its
    ancestors. It cannot see a script that imports emcee from outside a
    `scripts/` directory."""
    done = subprocess.run(["ps", "-axo", "pid=,ppid=,command="], capture_output=True,
                          stdin=subprocess.DEVNULL, text=True, check=True)
    return tool_lines(done.stdout.splitlines(), tools, self_pid=os.getpid())
