"""Task 8 mutation runner. Usage: runner.py <base-copy> <mutants.json> <out.jsonl> [ids...]
Each mutant: {"id", "file", "old", "new", "predicted": [...], "collateral": [...]}.
Copies the base to m/<id>, applies exactly one replacement (old must occur once and the
diff must be one changed line), proves the import resolves to the copy, runs the
relevant test files from an empty scratch cwd under a fresh PYTHONPYCACHEPREFIX with a
timeout, and records the failing set."""
import difflib, json, os, pathlib, shutil, subprocess, sys, time

S = pathlib.Path(__file__).resolve().parent
WT = "/Users/shawn/projects/llama/.claude/worktrees/taper-markers"
PY = f"{WT}/.venv/bin/python"
FILES = ["packages/llama/tests/test_taper.py", "packages/llama/tests/test_stage_gather.py",
         "packages/llama/tests/test_replay.py", "packages/llama/tests/test_reapply.py",
         "scripts/test_replay_holds.py", "scripts/test_taper_probe.py"]
MODS = ["llama", "llama.taper", "llama.stages.gather", "llama.replay", "herder"]
TIMEOUT = 600


def run(base, mut):
    d = S / "m" / mut["id"]
    if d.exists():
        shutil.rmtree(d)
    shutil.copytree(base, d)
    diff = []
    if mut.get("file"):
        p = d / mut["file"]
        src = p.read_text()
        n = src.count(mut["old"])
        if n != 1:
            raise SystemExit(f"{mut['id']}: old occurs {n} times")
        out = src.replace(mut["old"], mut["new"])
        p.write_text(out)
        full = list(difflib.unified_diff(src.splitlines(), out.splitlines(), lineterm="", n=0))
        hunks = [l for l in full if l.startswith("@@")]
        diff = [l for l in full if not l.startswith(("---", "+++", "@@"))]
        minus = [l for l in diff if l.startswith("-")]
        plus = [l for l in diff if l.startswith("+")]
        if len(hunks) != 1 or len(minus) != 1 or len(plus) != 1:
            raise SystemExit(f"{mut['id']}: not a one-line diff: {full}")
        lineno = int(hunks[0].split()[1][1:].split(",")[0])
    else:
        lineno = None
    pyc = S / "pyc" / mut["id"]
    if pyc.exists():
        shutil.rmtree(pyc)
    pyc.mkdir(parents=True)
    env = dict(os.environ, PYTHONPATH=f"{d}/packages/llama/src:{d}/packages/herder/src",
               PYTHONPYCACHEPREFIX=str(pyc))
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    chk = subprocess.run([PY, "-c", "import importlib\nfor m in %r: print(importlib.import_module(m).__file__)" % MODS],
                         env=env, cwd=S / "cwd", capture_output=True, text=True)
    paths = chk.stdout.split()
    if len(paths) != len(MODS) or not all(x.startswith(str(d) + "/") for x in paths):
        raise SystemExit(f"{mut['id']}: import not from the copy: {chk.stdout} {chk.stderr[-500:]}")
    t0 = time.time()
    try:
        r = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rfE",
                            *[f"{d}/{f}" for f in FILES]],
                           env=env, cwd=S / "cwd", capture_output=True, text=True, timeout=TIMEOUT)
        out, rc, hang = r.stdout, r.returncode, False
    except subprocess.TimeoutExpired as e:
        out, rc, hang = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or ""), None, True
    import re as _re
    fails = sorted({_re.sub(r"^.*?/m/" + _re.escape(mut["id"]) + "/", "", l.split(" ", 1)[1].split(" - ")[0])
                    for l in out.splitlines() if l.startswith(("FAILED ", "ERROR "))})
    summary = [l for l in out.splitlines() if " passed" in l or " failed" in l or " error" in l]
    rec = {"id": mut["id"], "file": mut.get("file"), "line": lineno, "diff": diff,
           "predicted": mut.get("predicted", []), "collateral": mut.get("collateral", []),
           "fails": fails, "rc": rc, "hang": hang, "summary": summary[-1] if summary else out[-400:],
           "secs": round(time.time() - t0, 1), "imports": paths}
    shutil.rmtree(d)
    shutil.rmtree(pyc)
    return rec


if __name__ == "__main__":
    base, spec, outp = pathlib.Path(sys.argv[1]), json.loads(pathlib.Path(sys.argv[2]).read_text()), sys.argv[3]
    only = set(sys.argv[4:])
    for mut in spec:
        if only and mut["id"] not in only:
            continue
        rec = run(base, mut)
        with open(outp, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"{rec['id']}: rc={rec['rc']} hang={rec['hang']} {rec['summary']} fails={len(rec['fails'])}", flush=True)
        for x in rec["fails"]:
            print("    ", x, flush=True)
