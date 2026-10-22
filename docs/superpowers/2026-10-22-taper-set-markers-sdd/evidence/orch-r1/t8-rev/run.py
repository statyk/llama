import difflib, json, os, re, shutil, subprocess, sys
S = os.path.dirname(os.path.abspath(__file__))
WT = "/Users/shawn/projects/llama/.claude/worktrees/taper-markers"
PY = WT + "/.venv/bin/python"
BASE = S + "/base"
L = "packages/llama/src/llama/"
G, T, R = L + "stages/gather.py", L + "taper.py", L + "replay.py"
TESTS = ["packages/llama/tests/test_taper.py", "packages/llama/tests/test_stage_gather.py",
         "packages/llama/tests/test_replay.py", "packages/llama/tests/test_reapply.py",
         "scripts/test_replay_holds.py", "scripts/test_taper_probe.py"]
M = {
    "S0": None,
    "SENT": (G, "    notes: list[str] = []\n    kept_count = count_flag\n",
             "    raise RuntimeError('SENTINEL')\n    kept_count = count_flag\n"),
    "t": (G, 'taper_n = len({i.set for i in taper.items if i.set != "encore"})',
          'taper_n = len({i.set for i in taper.items})'),
    "u": (G, "fuzzy_norm_title(st.closer, aliases))\n",
          "fuzzy_norm_title(st.closer, aliases)) and songs[-1] == st.closer\n"),
    "u2": (G, "agrees = bool(songs) and fuzzy_title_eq(fuzzy_norm_title(songs[-1], aliases),",
           "agrees = bool(songs) and songs[-1].casefold() == st.closer.casefold() and (0,"),
    "q": (T, "    if taper.set_like:\n", "    if False:\n"),
    "s": (T, "if str(number) == item.set and _CONT_AFTER.match(item.title[m.end():]):", "if False:"),
    "i": (R, "and not gathered.taper_owned):", "and bool(gathered.needs_llm)):"),
    "a": (T, "if not is_filler(t.title) or not _counts(t):", "if not _counts(t):"),
    "o": (T, r'r"(?:set\s*(?P<tok>one|two|three|iii|ii|i|[123])(?!\w)"',
          r'r"(?:set\s*(?P<tok>one|two|three|iii|ii|i|[123])"'),
    "o2": (T, r'r"|(?P<ord>first|second|third)\s+set(?!\w)"', r'r"|(?P<ord>first|second|third)\s+set"'),
    "o3": (T, r'r"|(?P<ordn>1st|2nd|3rd)\s+set(?!\w))"', r'r"|(?P<ordn>1st|2nd|3rd)\s+set)"'),
    "o4": (T, r'rf"^{_E_DECOR}(?:enc|e\d?)(?!\w)"', r'rf"^{_E_DECOR}(?:enc|e\d?)"'),
}

def run(mid):
    dst = f"{S}/m/{mid}"
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(BASE, dst)
    diff = []
    if M[mid]:
        f, old, new = M[mid]
        p = f"{dst}/{f}"
        src = open(p).read()
        assert src.count(old) == 1, (mid, src.count(old))
        out = src.replace(old, new)
        open(p, "w").write(out)
        diff = [l for l in difflib.unified_diff(src.splitlines(), out.splitlines(), lineterm="", n=0)
                if l[:1] in "+-" and not l.startswith(("+++", "---"))]
        assert len(diff) == 2 and diff[0][0] == "-" and diff[1][0] == "+", diff
    env = dict(os.environ, PYTHONPATH=f"{dst}/packages/llama/src:{dst}/packages/herder/src",
               PYTHONPYCACHEPREFIX=f"{S}/pyc/{mid}")
    shutil.rmtree(f"{S}/pyc/{mid}", ignore_errors=True)
    chk = subprocess.run([PY, "-c", "import llama, llama.taper, llama.stages.gather, llama.replay, herder;"
                          "print(llama.taper.__file__, llama.stages.gather.__file__, llama.replay.__file__, herder.__file__)"],
                         cwd=f"{S}/cwd", env=env, capture_output=True, text=True)
    paths = chk.stdout.split()
    assert len(paths) == 4 and all(x.startswith(dst + "/") for x in paths), (chk.stdout, chk.stderr)
    try:
        r = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf", *[f"{dst}/{t}" for t in TESTS]],
                           cwd=f"{S}/cwd", env=env, capture_output=True, text=True, timeout=600)
        out, rc = r.stdout, r.returncode
    except subprocess.TimeoutExpired:
        out, rc = "HANG", None
    fails = sorted(set(l.split(" ", 1)[1].split(" - ")[0].replace(dst + "/", "")
                       for l in out.splitlines() if l.startswith("FAILED ")))
    summ = [l for l in out.splitlines() if re.search(r"\d+ (passed|failed)", l)]
    print(f"{mid}: rc={rc} {summ[-1] if summ else out[-400:]} import_ok diff={diff}")
    for x in fails:
        print("    ", x)
    sys.stdout.flush()

for mid in (sys.argv[1:] or list(M)):
    run(mid)
