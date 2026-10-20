"""Per-show predicted-vs-actual check for one reapply wave (read-only).

usage: wavecheck.py <wave.json> <wave.log> <after-arm.json> <marker> <llmfail-before.txt>
"""
import hashlib, json, os, re, sys
from pathlib import Path

wave, log, after, marker, failbefore = map(Path, sys.argv[1:6])
HOME = Path.home()
SHOWS = HOME / ".llama/shows"
cand = json.loads((HOME / ".llama-harness/G2-cand-held.json").read_text())["shows"]
rows = json.loads(wave.read_bytes())["rows"]
slugs = [r["slug"] for r in rows]
batch = HOME / ".llama/reapply" / hashlib.sha256(wave.read_bytes()).hexdigest()[:16]
prog = {}
if (batch / "progress.jsonl").exists():
    for line in (batch / "progress.jsonl").read_text().splitlines():
        if line.strip():
            e = json.loads(line); prog[e["slug"]] = e
text = log.read_text()
fresh = set(re.findall(r"^(\S+): writing a fresh briefing", text, re.M))
redeliver = re.findall(r"re-deliver with: .*", text)
arm = json.loads(after.read_text())["shows"] if after.exists() else {}
mt = marker.stat().st_mtime

bad = 0; allowed = []
print("slug | predicted | progress | brief | needs_review flags | manifest | after: outcome repro changes flags | gather-leg vs G2")
for r in rows:
    s = r["slug"]; probs = []
    p = prog.get(s, {}).get("outcome")
    if p != "cleared": probs.append(f"progress={p}")
    b = "fresh" if s in fresh else "reuse"
    if b != r["briefing"]: probs.append(f"brief {b}!={r['briefing']}")
    sj = json.loads((SHOWS / s / "show.json").read_text())
    if sj.get("needs_review") or sj.get("review_flags"): probs.append("still held")
    man = (SHOWS / s / "package/manifest.json").exists()
    if not man: probs.append("no manifest")
    a = arm.get(s)
    if a is None:
        probs.append("not in after-arm"); asum = "-"
    else:
        ch = a["title_changes"] + a["set_changes"] + a["segue_changes"]
        fl = a["gather_flags"] + a["vet_flags"] + a["brief_flags"] + a["needs_llm"]
        asum = f"{a['outcome']} {a['reproduces']} {len(ch)} {fl}"
        if a["outcome"] != "clean" or not a["reproduces"] or ch or fl or a.get("unreplayable"):
            probs.append("after-arm not clean")
        c = cand.get(s, {})
        # venue/city/date are diffs against the stored show: G2 predicted
        # {old, new}; once applied the after-arm must report no diff and its
        # selected_* must equal G2's prediction.
        diff = [k for k in ("notes", "selected_venue", "selected_city", "set_breaks")
                if a.get(k) != c.get(k)]
        diff += [k for k in ("venue", "city", "date") if a.get(k) is not None]
        for k in ("venue", "city"):
            if isinstance(c.get(k), dict) and c[k].get("new") != a.get(f"selected_{k}"):
                diff.append(f"{k}.new")
        if diff: probs.append(f"differs from G2 cand: {diff}")
    # Amended stop rule (llama-45, 2026-10-20): a needs-brief/fresh row held
    # SOLELY by briefing_guard is an allowed known non-match.
    flags = sj.get("review_flags") or []
    guard_hold = (probs and p == "held" and r["outcome"] == "needs-brief" and r["briefing"] == "fresh"
                  and b == "fresh" and sj.get("needs_review") and flags
                  and all(f.startswith("briefing ") for f in flags)
                  and a is not None and a["outcome"] == "needs-brief" and a["reproduces"]
                  and not (a["title_changes"] + a["set_changes"] + a["segue_changes"]
                           + a["gather_flags"] + a["vet_flags"] + a["needs_llm"])
                  and not [x for x in probs if x.startswith("differs from G2")])
    if guard_hold:
        allowed.append((s, flags)); verdict = "ALLOWED held-by-fresh-guard"
    elif probs:
        bad += 1; verdict = "MISMATCH " + "; ".join(probs)
    else:
        verdict = "OK"
    print(f"{s} | {r['outcome']}/{r['briefing']} | {p} | {b} | {sj.get('needs_review')} {flags} | {man} | {asum} | {verdict}")

before = set(Path(sys.argv[6]).read_text().split()) if len(sys.argv) > 6 else set()
others, new = [], []
for d in SHOWS.iterdir():
    if d.name in slugs or not d.is_dir():
        continue
    if any(f.stat().st_mtime > mt for f in d.rglob("*") if f.is_file()):
        (new if before and d.name not in before else others).append(d.name)
fails = sorted(set(os.listdir(HOME / ".llama/llm-failures")) - set(failbefore.read_text().split()))
print(f"\nheld-by-fresh-guard (allowed): {len(allowed)}")
for s, f in allowed: print(f"  {s}: {f}")
print(f"new show dirs created since marker (not in shows-before; llama get): {len(new)} {sorted(new)}")
print(f"rows {len(rows)}, mismatches {bad}, fresh-brief lines {len(fresh)} (all in wave: {fresh <= set(slugs)}), "
      f"progress entries {len(prog)}, re-deliver lines {len(redeliver)}")
print(f"new llm-failures: {len(fails)} {fails}")
print(f"show dirs outside the wave written since marker: {len(others)} {sorted(others)}")
print(f"other slugs named in log: {sorted(set(re.findall(r'^(\S+): ', text, re.M)) - set(slugs) - {'jerrybase', 'downloading', 'summary', 'reapplied'})}")
for line in redeliver: print(line)
