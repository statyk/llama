"""inspect_m.py <id> <nodeid>... : re-apply one mutant in a fresh copy and show the tracebacks."""
import json, os, pathlib, shutil, subprocess, sys
S = pathlib.Path(__file__).resolve().parent
PY = "/Users/shawn/projects/llama/.claude/worktrees/taper-markers/.venv/bin/python"
mut = next(m for m in json.load(open(S / "mutants.json")) if m["id"] == sys.argv[1])
d = S / "m" / ("insp-" + mut["id"])
if d.exists(): shutil.rmtree(d)
shutil.copytree(S / "base", d)
p = d / mut["file"]; src = p.read_text(); assert src.count(mut["old"]) == 1
p.write_text(src.replace(mut["old"], mut["new"]))
pyc = S / "pyc" / ("insp-" + mut["id"])
if pyc.exists(): shutil.rmtree(pyc)
env = dict(os.environ, PYTHONPATH=f"{d}/packages/llama/src:{d}/packages/herder/src", PYTHONPYCACHEPREFIX=str(pyc))
r = subprocess.run([PY, "-c", "import llama.taper, llama.stages.gather as g; print(g.__file__)"], env=env, cwd=S / "cwd", capture_output=True, text=True)
assert str(d) in r.stdout, r
r = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=short", *[f"{d}/{n}" for n in sys.argv[2:]]],
                   env=env, cwd=S / "cwd", capture_output=True, text=True, timeout=600)
out = "\n".join(l for l in r.stdout.splitlines() if l.startswith(("E ", ">", "____")) or "assert" in l or " passed" in l or " failed" in l)
print(out[-6000:])
shutil.rmtree(d); shutil.rmtree(pyc, ignore_errors=True)
