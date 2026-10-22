import json, os, pathlib, re, shutil, subprocess, sys, difflib
S = pathlib.Path(__file__).resolve().parent
WT = "/Users/shawn/projects/llama/.claude/worktrees/taper-markers"
PY = f"{WT}/.venv/bin/python"
FILES = ["packages/llama/tests/test_taper.py", "packages/llama/tests/test_stage_gather.py",
         "packages/llama/tests/test_replay.py", "packages/llama/tests/test_reapply.py",
         "scripts/test_replay_holds.py", "scripts/test_taper_probe.py"]
TP = "packages/llama/src/llama/taper.py"
DOC = '''    never sees less than the parser does)."""\n'''
MUTS = {
 "S0": [],
 "SENT": [(DOC, DOC + '    raise RuntimeError("SENTINEL_T8RR1")\n'),
          ("_SET_TOKEN = (\n", "SENTINEL_T8RR1 = True\n_SET_TOKEN = (\n")],
 "o":  [(r'''r"(?:set\s*(?P<tok>one|two|three|iii|ii|i|[123])(?!\w)"''', r'''r"(?:set\s*(?P<tok>one|two|three|iii|ii|i|[123])"''')],
 "o2": [(r'''r"|(?P<ord>first|second|third)\s+set(?!\w)"''', r'''r"|(?P<ord>first|second|third)\s+set"''')],
 "o3": [(r'''r"|(?P<ordn>1st|2nd|3rd)\s+set(?!\w))"''', r'''r"|(?P<ordn>1st|2nd|3rd)\s+set)"''')],
}
for mid in sys.argv[1:]:
    d = S / "m" / mid
    if d.exists(): shutil.rmtree(d)
    shutil.copytree(S / "base", d)
    p = d / TP; src = p.read_text(); out = src
    for old, new in MUTS[mid]:
        assert out.count(old) == 1, (mid, old, out.count(old))
        out = out.replace(old, new)
    p.write_text(out)
    diff = [l for l in difflib.unified_diff(src.splitlines(), out.splitlines(), lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")]
    pyc = S / "pyc" / mid
    if pyc.exists(): shutil.rmtree(pyc)
    pyc.mkdir(parents=True)
    env = dict(os.environ, PYTHONPATH=f"{d}/packages/llama/src:{d}/packages/herder/src", PYTHONPYCACHEPREFIX=str(pyc))
    chk = subprocess.run([PY, "-c", "import llama, llama.taper as t, llama.stages.gather as g, llama.replay as r, herder\nfor m in (llama,t,g,r,herder): print(m.__file__)\nprint('SENTINEL_ATTR', getattr(t,'SENTINEL_T8RR1',None))"], env=env, cwd=S/"cwd", capture_output=True, text=True)
    paths = [l for l in chk.stdout.splitlines() if not l.startswith("SENTINEL_ATTR")]
    assert len(paths) == 5 and all(x.startswith(str(d) + "/") for x in paths), chk.stdout + chk.stderr
    r = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rfE", *[f"{d}/{f}" for f in FILES]], env=env, cwd=S/"cwd", capture_output=True, text=True, timeout=600)
    fails = sorted({re.sub(r"^.*?/m/" + re.escape(mid) + "/", "", l.split(" ", 1)[1].split(" - ")[0]) for l in r.stdout.splitlines() if l.startswith(("FAILED ", "ERROR "))})
    summ = [l for l in r.stdout.splitlines() if " passed" in l or " failed" in l][-1:]
    print(f"== {mid}: diff={diff}\n   imports={paths}\n   {chk.stdout.splitlines()[-1]}\n   summary={summ} nfail={len(fails)}", flush=True)
    for f in (fails if len(fails) <= 20 else fails[:5] + [f"... ({len(fails)} total)"]):
        print("     ", f, flush=True)
    if mid == "SENT":
        want = [f for f in fails if "test_set_like_negatives" in f or "test_token_glued" in f]
        print(f"   SENT reds among target tests: {len(want)}", flush=True)
    shutil.rmtree(d); shutil.rmtree(pyc)
