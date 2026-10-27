"""Campaign gates (bulk-apply plan Tasks 5 and 12).

Task 5: the one process parser, ported from `scripts/rekey_overrides.py`
(`llama_processes`/`_runs_llama`) with the tool name a parameter. The station
mark writer uses it to refuse while an `emcee` process runs (spec "No
concurrent emcee"). The script keeps its own copy; it is not changed here.

Task 12: the campaign's version gate, the code pin and the rekey-restore retirement.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath
from typing import Callable, Iterable

from llama.errors import LlamaError

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


# --- Task 12: version gate, pin, rekey retirement ---

CAMPAIGN_MIN_VERSION = "2.20.0"       # the release this build ships in; confirm at release
_VERSION = re.compile(r"[0-9]+(?:\.[0-9]+)+")
_VERSION_TIMEOUT_S = 120
PIN_FILE = Path("campaign") / "pin.json"
REKEY_RECORD = "rekey-applied.json"


class GateRefused(LlamaError):
    """A campaign gate refused; nothing was written."""


def _numeric(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def _cmp(text: str, other: str) -> int | None:
    """-1/0/1 comparing a dotted version `text` with `other`; None if `text` is not one."""
    t = text.strip()
    if not _VERSION.fullmatch(t):
        return None
    got, want = _numeric(t), _numeric(other)
    n = max(len(got), len(want))
    got, want = got + (0,) * (n - len(got)), want + (0,) * (n - len(want))
    return (got > want) - (got < want)


def version_ok(text: str, minimum: str) -> bool:
    """`--version` output is a dotted version of at least `minimum`, numerically. Anything
    else is not: a dev build's `0.1.0`, a pre-release or local suffix, extra words or lines."""
    c = _cmp(text, minimum)
    return c is not None and c >= 0


def version_newer(text: str, than: str) -> bool:
    """`text` is a dotted version strictly above `than` (anything else is not)."""
    c = _cmp(text, than)
    return c is not None and c > 0


def tool_versions(tool: str) -> list[tuple[str, str]]:
    """(path, its `--version` output) for every `tool` that `which -a` lists, in PATH
    order. A binary that fails reports `exit <n>: <output>` or `error: ...` in place of
    its version (version_ok refuses both). Raises OSError when `which` itself fails."""
    done = subprocess.run(["which", "-a", tool], capture_output=True, text=True)
    if done.returncode not in (0, 1):
        raise OSError(f"which -a {tool} exited {done.returncode}: {done.stderr.strip()}")
    paths = list(dict.fromkeys(l.strip() for l in done.stdout.splitlines() if l.strip()))
    out = []
    for p in paths:
        try:
            r = subprocess.run([p, "--version"], capture_output=True, text=True,
                               timeout=_VERSION_TIMEOUT_S)
        except (OSError, subprocess.TimeoutExpired) as exc:
            out.append((p, f"error: {type(exc).__name__}: {exc}"))
            continue
        text = r.stdout.strip()
        if r.returncode != 0:
            text = f"exit {r.returncode}: {(r.stdout + r.stderr).strip()}"
        out.append((p, text))
    return out


def require_tools(echo: Callable[[str], None], *, pin: dict | None) -> None:
    """Every `llama` and `emcee` on PATH reports at least CAMPAIGN_MIN_VERSION, and, with
    a pin, no `llama` is newer than the pinned version (an installed newer build would
    write what the pinned code would not). Raises GateRefused, naming each path."""
    problems = []
    for tool in ("llama", "emcee"):
        try:
            found = tool_versions(tool)
        except Exception as exc:
            raise GateRefused(f"version check failed: {type(exc).__name__}: {exc}") from exc
        if not found:
            problems.append(f"no {tool} on PATH")
        for p, out in found:
            echo(f"{tool} on PATH: {p} {out}")
            if not version_ok(out, CAMPAIGN_MIN_VERSION):
                problems.append(f"{tool} below {CAMPAIGN_MIN_VERSION}: {p} "
                                f"{' | '.join(out.splitlines())}")
            elif tool == "llama" and pin and version_newer(out, pin["version"]):
                problems.append(f"llama newer than the pinned {pin['version']}: {p} {out}")
    if problems:
        raise GateRefused("refusing: " + "; ".join(problems), problems)


def read_pin(root: Path) -> dict | None:
    path = root / PIN_FILE
    if not path.exists():
        return None
    try:
        pin = json.loads(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise GateRefused(f"{path} unreadable ({exc}); repair it by hand") from exc
    if not isinstance(pin, dict):
        raise GateRefused(f"{path} is not a pin record; repair it by hand")
    return pin


def _write_json(path: Path, obj: dict) -> None:
    from llama.batch_snapshot import _durable_replace
    path.parent.mkdir(parents=True, exist_ok=True)
    _durable_replace(path, (json.dumps(obj, indent=2) + "\n").encode())


def write_pin(root: Path, *, tag: str, sha: str, version: str, worktree: str,
              replace: bool) -> dict:
    if read_pin(root) is not None and not replace:
        raise GateRefused(f"{root / PIN_FILE} already exists; pass --replace to overwrite it")
    pin = {"tag": tag, "sha": sha, "version": version, "worktree": worktree,
           "pinned_at": datetime.now(timezone.utc).isoformat()}
    _write_json(root / PIN_FILE, pin)
    return pin


def require_pinned_code(root: Path) -> dict:
    """The pin exists and the running code is exactly its commit, never a dirty tree."""
    from llama import replay
    pin = read_pin(root)
    if pin is None:
        raise GateRefused(f"no pin: {root / PIN_FILE} is missing; run scripts/bulk_apply.py pin "
                          f"--tag <tag> from the pinned worktree")
    ident = replay.code_identity()
    if ident != pin.get("sha"):
        raise GateRefused(f"the running code is {ident}, not the pinned {pin.get('sha')} "
                          f"({pin.get('tag')}); run from the pinned worktree {pin.get('worktree')} "
                          f"with a clean tree")
    return pin


def retire_rekey_restore(root: Path, *, by: str, at: str) -> bool:
    """Mark `rekey-applied.json` retired (rekey's `--restore` then refuses, spec "Undo").
    True only when this call wrote; False when the file is absent, unreadable or already
    retired (the first `retired` stays)."""
    path = root / REKEY_RECORD
    try:
        rec = json.loads(path.read_bytes())
    except (OSError, ValueError):
        return False
    if not isinstance(rec, dict) or "retired" in rec:
        return False
    rec["retired"] = {"at": at, "by": by}
    _write_json(path, rec)
    return True
