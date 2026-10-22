import os, shutil, subprocess, sys
S = os.path.dirname(os.path.abspath(__file__))
W = "/Users/shawn/projects/llama/.claude/worktrees/taper-markers"
G = "packages/llama/src/llama/stages/gather.py"
K = ("taper or today or umphreys or old_structure_info or merge_conflicts or notes_lineage or "
     "notes_used or segues_and_matched or structure_info_created or label_rename or reader_coverage or align_structure")
MUTANTS = {
  "M0-none": [],
  "Msentinel-never-owned": [("taper_owned = decision.placement is not None", "taper_owned = False")],
  "M1-drop-canonical-items": [("if (canonical.items and anchored is None and result.coverage < threshold", "if (anchored is None and result.coverage < threshold")],
  "M2-drop-anchored-none": [("if (canonical.items and anchored is None and result.coverage < threshold", "if (canonical.items and result.coverage < threshold")],
  "M3-drop-step1-cov": [("if (canonical.items and anchored is None and result.coverage < threshold\n                    and reader_coverage", "if (canonical.items and anchored is None\n                    and reader_coverage")],
  "M4-no-filler-exclusion": [("   if not is_filler(t.title)):", "   if True):")],
  "M5-keep-anchor-note-owned": [("            shipped_sets = list(decision.placement.sets)\n", "            shipped_sets = list(decision.placement.sets)\n            if anchor_note is not None: notes.append(anchor_note)\n")],
  "M6-step1-coverage": [("            coverage = reader_coverage\n", "            pass\n")],
}
for name, edits in MUTANTS.items():
    d = os.path.join(S, "m", name)
    if os.path.exists(d): shutil.rmtree(d)
    shutil.copytree(os.path.join(S, "base"), d)
    p = os.path.join(d, G); src = open(p).read()
    for old, new in edits:
        assert src.count(old) == 1, (name, old)
        src = src.replace(old, new)
    open(p, "w").write(src)
    env = dict(os.environ, PYTHONPATH=f"{d}/packages/llama/src:{d}/packages/herder/src", PYTHONDONTWRITEBYTECODE="1")
    chk = subprocess.run([f"{W}/.venv/bin/python", "-c", "import llama.stages.gather as g; print(g.__file__)"], env=env, cwd=S, capture_output=True, text=True).stdout.strip()
    assert chk.startswith(d), chk
    r = subprocess.run([f"{W}/.venv/bin/python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x" if False else "-q",
                        f"{d}/packages/llama/tests/test_stage_gather.py", "-k", K], env=env, cwd=S, capture_output=True, text=True)
    tail = [l for l in r.stdout.splitlines() if "passed" in l or "failed" in l or l.startswith("FAILED")]
    print(name, "rc", r.returncode, "|", " ; ".join(tail[-6:]), flush=True)
