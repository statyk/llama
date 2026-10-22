import sys, shutil, subprocess, pathlib, os
S = pathlib.Path(sys.argv[1]); base = S/"base"
G = "packages/llama/src/llama/stages/gather.py"
MUT = {
 "M1_agrees_true": ("        if agrees:\n", "        agrees = True\n        if agrees:\n"),
 "M2_any_set": ("        agrees = bool(songs) and fuzzy_title_eq(fuzzy_norm_title(songs[-1], aliases),\n                                                fuzzy_norm_title(st.closer, aliases))",
                "        lasts = {}\n        for i in taper.items: lasts[i.set] = i.title\n        agrees = any(fuzzy_title_eq(fuzzy_norm_title(x, aliases), fuzzy_norm_title(st.closer, aliases)) for x in lasts.values())"),
 "M3_no_consume": ("if n not in used and m is not None", "if m is not None"),
 "M4_count_always": ("        if taper_n != jb_n:\n", "        if True:\n"),
 "M5_count_encore": ("taper_n = len({i.set for i in taper.items if i.set != \"encore\"})", "taper_n = len({i.set for i in taper.items})"),
 "M6_exact_eq": ("        agrees = bool(songs) and fuzzy_title_eq(fuzzy_norm_title(songs[-1], aliases),\n                                                fuzzy_norm_title(st.closer, aliases))",
                 "        agrees = bool(songs) and songs[-1] == st.closer"),
 "M7_trip_old": ("if event is not None and (taper_owned or alignment != \"jerrybase\"):", "if event is not None and alignment != \"jerrybase\":"),
 "M8_trip_always": ("if event is not None and (taper_owned or alignment != \"jerrybase\"):", "if event is not None:"),
 "M10_notes_to_conflicts": ("            op_notes += closer_notes\n", "            notes += closer_notes\n"),
 "M11_count_not_demoted": ("            [], guard, event, decision.taper, family_aliases)\n        op_notes += count_notes\n", "            [], guard, event, decision.taper, family_aliases)\n        guard = guard or count_notes[0][:-len(' (taper\\'s markers)')]\n"),
}
only = sys.argv[2:] or list(MUT)
for name in only:
    old, new = MUT[name]
    d = S/name
    if d.exists(): shutil.rmtree(d)
    shutil.copytree(base, d)
    p = d/G; src = p.read_text()
    assert src.count(old) == 1, (name, src.count(old))
    p.write_text(src.replace(old, new))
    env = dict(os.environ, PYTHONPATH=f"{d}/packages/llama/src:{d}/packages/herder/src", PYTHONDONTWRITEBYTECODE="1")
    chk = subprocess.run(["/Users/shawn/projects/llama/.claude/worktrees/taper-markers/.venv/bin/python","-c","import llama.stages.gather as g; print(g.__file__)"], env=env, cwd=S, capture_output=True, text=True)
    assert str(d) in chk.stdout, chk
    r = subprocess.run(["/Users/shawn/projects/llama/.claude/worktrees/taper-markers/.venv/bin/python","-m","pytest","-q","-p","no:cacheprovider","-x" if False else "-q", f"{d}/packages/llama/tests/test_stage_gather.py", f"{d}/packages/llama/tests/test_taper.py"], env=env, cwd=S, capture_output=True, text=True)
    fails = [l for l in r.stdout.splitlines() if l.startswith("FAILED") or l.startswith("ERROR")]
    tail = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:]
    print(f"{name}: rc={r.returncode} {tail}"); [print("   ", f[:160]) for f in fails[:8]]
    shutil.rmtree(d)
