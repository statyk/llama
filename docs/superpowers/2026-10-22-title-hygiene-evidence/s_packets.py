#!/usr/bin/env python3
"""Piece 3 hand-check, class S: every show where the whole-tape `setlist`
rung (titles.py: canonical count == track count, positional copy) fills at
least one track under current code. Writes packets/S/<slug>.md + index.json
and s_rows.json. Reuses census.py's load and packet helpers (exec'd, not its
class/run sections, so census outputs are untouched). Read-only on the library.

Run: /Users/shawn/projects/llama/.venv/bin/python s_packets.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
_src = (HERE / "census.py").read_text().splitlines(keepends=True)
# lines 1-104: imports, load, helpers; 555-699: packet helpers (up to held_lbl)
exec("".join(_src[:104] + _src[554:699]), globals())

S_DIR = PK / "S"
S_DIR.mkdir(parents=True, exist_ok=True)
for f in S_DIR.glob("*.md"):
    f.unlink()

out = []
for r in rows:
    tr, src = basis(r)
    if not any(t.get("src") == "setlist" for t in tr):
        continue
    r["_basis"], r["_basis_src"] = tr, src
    canon = r.get("canonical") or []
    pos_fill = [t["n"] for t in tr if t.get("src") == "setlist"]
    tagged = [t for t in tr if t.get("src") != "setlist"]
    # deterministic shift signals (hints for the checker, not verdicts)
    adj_dup = [(a["n"], b["n"]) for a, b in zip(tr, tr[1:]) if eqt(a["title"], b["title"])]
    tag_vs_pos = []
    for t in tr:
        i = t["n"] - 1
        raw = _raw(r, t["file"])
        if raw and i < len(canon) and is_real_title(clean_tag_title(raw)):
            tag_vs_pos.append(eqt(clean_tag_title(raw), canon[i]["title"]))
    row = {"slug": r["slug"], "state": statecol(r), "held_now": r.get("state") == "held",
           "would_hold": would_hold(r), "flags": r.get("flags") if r.get("replayed") else r.get("stored_flags"),
           "canonical_source": r.get("canonical_source"), "n_tracks": len(tr), "n_positional": len(pos_fill),
           "whole_tape": len(pos_fill) == len(tr), "adjacent_dup_pairs": adj_dup,
           "raw_tag_agrees_with_position": f"{sum(tag_vs_pos)}/{len(tag_vs_pos)}",
           "family": r.get("family")}
    out.append(row)

    md = [head(r, "S", f"setlist rung filled {len(pos_fill)} of {len(tr)} tracks")]
    md.append("## Deterministic hints (census-computed; NOT verdicts)\n")
    md.append(f"- positions filled by the whole-tape `setlist` rung: {pos_fill}")
    md.append(f"- adjacent tracks with the same title: {adj_dup or 'none'}")
    md.append(f"- real raw tags that equal the canonical item at the same position: {row['raw_tag_agrees_with_position']}")
    md.append("\n## Tracks (`canonical item N` = what the rung copies onto track N; `raw tag` = the file's own tag before cleaning/demotion)\n")
    md.append(track_table(r, ["canonical item N", "raw tag"],
                          lambda k: [canon[k["n"] - 1]["title"] if k["n"] - 1 < len(canon) else "", _raw(r, k["file"])]))
    md.append("\n## Canonical setlist (as gather built it)\n")
    md.append(", ".join(f"[{c['set']}] {c['title']}" for c in canon) or "(empty)")
    md.append("\n## Selected recording's own parse_setlist items\n")
    md.append(f"({r.get('own_parse_conf')}) " + " / ".join(r.get("own_parse") or []))
    if r.get("other_formats"):
        md.append("\n## Other-format copies of the same item\n")
        for fmt, o in r["other_formats"].items():
            md.append(f"- {fmt}: {o['n']} kept files, stem bijection {o['bijection']}, title fraction {o['fraction']}")
    md.append("\n## Excluded files\n")
    md.append("\n".join(f"- {json.dumps(x)[:200]}" for x in (r.get("excluded_files") or [])) or "(none)")
    md.append("\n## Gather/vet notes\n")
    md.append("\n".join(f"- {x}" for x in (r.get("notes") or [])) or "(none)")
    md.append("\n## Selected item description (verbatim)\n")
    md.append(desc_block(r))
    md.append("\n## Overnight adjudication\n")
    md.append(verdict_block(r["slug"]))
    (S_DIR / f"{r['slug']}.md").write_text("\n".join(md) + "\n")

out.sort(key=lambda x: x["slug"])
(S_DIR / "index.json").write_text(json.dumps([{"slug": o["slug"]} for o in out], indent=1))
(HERE / "s_rows.json").write_text(json.dumps(out, indent=1, default=str))
print(len(out), "S packets;", sum(o["whole_tape"] for o in out), "whole-tape;",
      sum(bool(o["adjacent_dup_pairs"]) for o in out), "with adjacent dups;",
      sum(not o["would_hold"] for o in out), "silent")
