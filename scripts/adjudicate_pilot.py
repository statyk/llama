#!/usr/bin/env python3
"""The adjudicator pilot (spec "Pilot (before the full sweep)", plan Task 11).

    python scripts/adjudicate_pilot.py select  [--n 30] [--seed 20261106] [--out DIR]
    python scripts/adjudicate_pilot.py run     --arm opus|sonnet [--out DIR] [--trial-applies 3]
    python scripts/adjudicate_pilot.py compare [--out DIR]

`select` is read-only. `run` judges each selected held show once, dry-run, with the arm's
model pinned (an explicit pin never escalates), writing records to `DIR/<arm>/<slug>.json`
(never `adjudication.json`) and a cost row per show to `DIR/<arm>/costs.jsonl`; a trial
apply (applied, then restored by the runner) measures coverage and the re-run cost for
switch verdicts and the first few other auto verdicts. `compare` writes `DIR/compare.md`.

Run from the worktree with its own interpreter. Only on the operator's go: the trial
applies touch real shows (they are restored, but snapshot the `select`ed dirs first).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from dataclasses import dataclass
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable

from herder import provider_ladder
from herder.limits import RateLimited
from herder import usage as herder_usage
from llama.adjudicator import runner
from llama.adjudicator.gate import GateResult
from llama.adjudicator.verdict import PROPOSE_ONLY_OPS, SwitchRecording, Verdict
from llama.campaign_gate import ps_lines, tool_processes
from llama.catalog import iter_shows, resolve_show
from llama.config import LLMTaskConfig, load_config
from llama.ledger import Ledger

SELF_SCRIPT = "adjudicate_pilot.py"
DEFAULT_OUT = Path.home() / ".llama-harness" / "adjudicate-pilot"
DEFAULT_VERDICTS = Path.home() / ".llama-harness" / "t3" / "verdicts"
ARMS = ("opus", "sonnet")

# ------------------------------------------------------------------ Intent classes

PARTIAL = "partial tape"
PARTIAL_SIBLING = "partial tape with a better sibling"
SIBLING = "better sibling"
UNTITLED = "untitled or untitled-echo"
SCRAMBLED = "scrambled or shifted tags"
LISTEN = "needs a listen"
OTHER = "other"
CLASSES = (PARTIAL, PARTIAL_SIBLING, SIBLING, UNTITLED, SCRAMBLED, LISTEN, OTHER)

# THE MAPPING TABLE (check by eye): prototype-verdict `root_causes` -> Intent class. A show
# takes the first class in `CLASS_PRIORITY` that any of its signals reaches; a prototype
# `needed_beyond_bundle` starting "listen" is the LISTEN signal. With no prototype verdict
# the show's own flags are matched against FLAG_PATTERNS (lower-cased substring -> class).
ROOT_CAUSE_CLASS = {
    "partial-tape": PARTIAL,
    "selection-should-prefer-sibling": SIBLING,
    "shifted-or-scrambled-tags": SCRAMBLED,
    "flags-echo-untitled-tape": UNTITLED,
    "placeholder-titles-shipped": UNTITLED,
    "description-positional-titles": UNTITLED,
    "titles-from-reviews-only": UNTITLED,
    "same-item-other-format-has-titles": UNTITLED,
    "other:taper-left-titles-blank": UNTITLED,
    "other:taper-left-title-blank": UNTITLED,
}
FLAG_PATTERNS = (
    ("unresolved track titles", UNTITLED),
    ("placeholder", UNTITLED),
    ("partial", PARTIAL),
    ("alignment", SCRAMBLED),
)
# Partial + sibling signals together are the PARTIAL_SIBLING class; then this order.
CLASS_PRIORITY = (LISTEN, PARTIAL_SIBLING, PARTIAL, SIBLING, SCRAMBLED, UNTITLED, OTHER)


def classify(flags: list[str], proto: dict | None) -> str:
    signals: set[str] = set()
    if proto is not None:
        if str(proto.get("needed_beyond_bundle") or "").lower().startswith("listen"):
            signals.add(LISTEN)
        for rc in proto.get("root_causes") or []:
            if rc in ROOT_CAUSE_CLASS:
                signals.add(ROOT_CAUSE_CLASS[rc])
        if PARTIAL in signals and SIBLING in signals:
            signals.add(PARTIAL_SIBLING)
    else:
        for flag in flags:
            for needle, cls in FLAG_PATTERNS:
                if needle in flag.lower():
                    signals.add(cls)
    for cls in CLASS_PRIORITY:
        if cls in signals:
            return cls
    return OTHER


def allocate(population: dict[str, int], n: int) -> dict[str, int]:
    """Proportional allocation with a floor of 2 per class (capped at the class size),
    largest-remainder for the rest, summing to min(n, population)."""
    alloc = {c: min(size, 2) for c, size in population.items() if size > 0}
    n = min(n, sum(population.values()))
    spare = n - sum(alloc.values())
    room = {c: population[c] - alloc[c] for c in alloc}
    total_room = sum(room.values())
    if spare <= 0 or total_room == 0:
        return alloc
    quota = {c: spare * room[c] / total_room for c in alloc}
    for c in alloc:
        alloc[c] += int(quota[c])
    left = n - sum(alloc.values())
    for c in sorted(alloc, key=lambda c: (-(quota[c] - int(quota[c])), c)):
        if left <= 0:
            break
        if alloc[c] < population[c]:
            alloc[c] += 1
            left -= 1
    return alloc


def _read_proto(verdicts_dir: Path, slug: str) -> dict | None:
    p = verdicts_dir / f"{slug}.json"
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get("root_causes"), list):
        data["root_causes"] = []
    return data


def select(config, out: Path, *, n: int = 30, seed: int = 20261106,
           verdicts_dir: Path = DEFAULT_VERDICTS) -> list[dict]:
    """Read-only over the library. Writes `out/shows.json` and `out/population.json`."""
    ledger = Ledger(config.root / "ledger.jsonl")
    by_class: dict[str, list[tuple[str, Path]]] = defaultdict(list)
    for entry in iter_shows(config.root, ledger):
        if entry.state != "held":                  # the catalog's own derived state and flags
            continue
        cls = classify(entry.flags, _read_proto(verdicts_dir, entry.slug))
        by_class[cls].append((entry.slug, entry.ws.dir))
    population = {c: len(by_class[c]) for c in CLASSES if by_class.get(c)}
    alloc = allocate(population, n)
    rows, dirs = [], []
    for cls in CLASSES:
        if cls not in alloc:
            continue
        members = sorted(by_class[cls])
        for slug, d in sorted(random.Random(f"{seed}:{cls}").sample(members, alloc[cls])):
            rows.append({"slug": slug, "cls": cls})
            dirs.append(d.resolve())
    out.mkdir(parents=True, exist_ok=True)
    (out / "shows.json").write_text(json.dumps(rows, indent=1) + "\n")
    (out / "population.json").write_text(json.dumps(population, indent=1) + "\n")
    for d in dirs:
        print(d)
    return rows


# ------------------------------------------------------------------ run

class PilotRefused(Exception):
    """`run` will not start; the message is the one-line reason (exit 2)."""


class PilotStopped(Exception):
    """`run` stopped cleanly and resumably (pacing ceiling, untrusted meter, rate limit);
    the message is the one-line reason (exit 3). Re-run the same command to continue."""


EXIT_REFUSED, EXIT_STOPPED = 2, 3
STOP_AT_5H, STOP_AT_7D = 85.0, 80.0


@dataclass(frozen=True)
class Windows:
    """One meter reading: percent used in each window (None = the window was missing)."""
    five_hour: float | None
    seven_day: float | None


def running_tools(ps: Callable[[], list[str]] = ps_lines) -> list[str]:
    """ps lines of running `llama` or `emcee` processes, matched by process name through
    campaign_gate's parser (never a substring of the command line); this script, its
    ancestors and shells merely mentioning a path under the repo never match."""
    lines = ps()
    found: list[str] = []
    for tool in ("llama", "emcee"):
        found += [f"{tool}: {l.strip()}" for l in
                  tool_processes(lines, tool, self_pid=os.getpid(), self_script=SELF_SCRIPT)]
    return found


def arm_config(config, arm: str):
    """`config` with `[llm.adjudicate]` pinned to the arm's alias: an explicit model,
    so provider_ladder builds all-base rungs and never escalates. Any other key of an
    existing `[llm.adjudicate]` table is kept."""
    old = config.llm.get("adjudicate")
    pin = (old.model_copy(update={"model": arm, "backend": "claude_cli"}) if old is not None
           else LLMTaskConfig(backend="claude_cli", model=arm))
    return config.model_copy(update={"llm": {**config.llm, "adjudicate": pin}})


class TrialPolicy:
    """Trial-apply every gate.auto verdict with a switch, plus `limit` other gate.auto
    verdicts in all (`others` = how many were already spent, e.g. on an earlier resume).
    `last_kind` is "switch", "other" or None for the most recent call."""

    def __init__(self, limit: int, others: int = 0):
        self.limit, self.others, self.last_kind = limit, others, None

    def __call__(self, verdict: Verdict, gate: GateResult) -> bool:
        self.last_kind = None
        if not gate.auto:
            return False
        if any(isinstance(e, SwitchRecording) for e in verdict.edits):
            self.last_kind = "switch"
        elif self.others < self.limit:
            self.others += 1
            self.last_kind = "other"
        return self.last_kind is not None


def make_trial_policy(trial_applies: int, others: int = 0) -> TrialPolicy:
    return TrialPolicy(trial_applies, others)


def live_meter() -> Windows | None:
    """The live reading of both windows, or None when it cannot be trusted. herder's
    read_usage already returns None for a failed fetch and for the "Showing last-known
    usage" banner (cached numbers), so a stale reading is None here too."""
    reading = herder_usage.read_usage()
    if reading is None:
        return None
    f, w = reading.five_hour, reading.seven_day
    return Windows(float(f.percent) if f is not None else None,
                   float(w.percent) if w is not None else None)


def stop_reason(w: Windows | None, stop_5h: float, stop_7d: float) -> str | None:
    """Why the run must not start another show, or None. Fails closed."""
    if w is None:
        return "usage meter unreadable or stale (failing closed)"
    if w.five_hour is None or w.seven_day is None:
        return "usage meter is missing a window (failing closed)"
    if w.five_hour >= stop_5h:
        return f"5-hour window at {w.five_hour:g}% (limit {stop_5h:g}%)"
    if w.seven_day >= stop_7d:
        return f"7-day window at {w.seven_day:g}% (limit {stop_7d:g}%)"
    return None


def _cost_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def run(arm: str, *, config, out: Path, trial_applies: int = 3,
        stop_at_5h: float = STOP_AT_5H, stop_at_7d: float = STOP_AT_7D,
        read_meter: Callable[[], Windows | None] = live_meter,
        ps: Callable[[], list[str]] = ps_lines, ia=None, provider=None, redo=None) -> None:
    if arm not in ARMS:
        raise PilotRefused(f"unknown arm {arm!r}")
    busy = running_tools(ps)
    if busy:
        raise PilotRefused(f"refusing to run while a process runs: {busy[0]}")
    shows = json.loads((out / "shows.json").read_text())
    config = arm_config(config, arm)
    ledger = Ledger(config.root / "ledger.jsonl")
    if ia is None:
        from llama.download_slots import DownloadSlots
        from llama.ia_client import IAClient
        ia = IAClient(config.root / "cache", slots=DownloadSlots(config.root / ".download-slots"))
    if provider is None:
        provider = provider_ladder(config.llm_settings(), "adjudicate")
    if redo is None:
        import llama.cli as cli

        def redo(entry, stage):
            return cli._redo_show_locked(config, ia, ledger,
                                         cli._resolve_show(config, ledger, entry.slug), stage)
    sink = out / arm
    sink.mkdir(parents=True, exist_ok=True)
    ctx = runner.Context(config=config, ia=ia, ledger=ledger, provider=provider, redo=redo,
                         sink=sink)
    costs = sink / "costs.jsonl"
    prior = _cost_rows(costs)
    done = {r["slug"] for r in prior}
    policy = make_trial_policy(trial_applies,
                               others=sum(r.get("trial_kind") == "other" for r in prior))
    for row in shows:
        slug = row["slug"]
        if slug in done:
            continue
        before = read_meter()
        reason = stop_reason(before, stop_at_5h, stop_at_7d)
        if reason is not None:
            raise PilotStopped(f"stopped before {slug}: {reason}; re-run to resume")
        policy.last_kind = None
        t0 = time.monotonic()
        try:
            entry = resolve_show(config.root, ledger, slug)
            outcome = runner.adjudicate_show(ctx, entry, force=True, dry_run=True,
                                             trial_policy=policy).outcome
        except RateLimited as exc:
            raise PilotStopped(f"rate limited at {slug}: {exc}; re-run to resume") from exc
        except Exception as exc:    # noqa: BLE001 - one show must not wedge every resume
            outcome = f"failed: {type(exc).__name__}: {exc}"
        wall = time.monotonic() - t0
        after = read_meter()
        with costs.open("a") as f:
            f.write(json.dumps({"slug": slug, "cls": row["cls"], "outcome": outcome,
                                "five_hour_before": before.five_hour,
                                "five_hour_after": after.five_hour if after else None,
                                "wall_s": round(wall, 2), "trial": policy.last_kind is not None,
                                "trial_kind": policy.last_kind}) + "\n")
        print(f"{arm} {slug}: {outcome}")


# ------------------------------------------------------------------ compare

STRICT_BARS = {"long", "title", "structure"}
PROTO_OPS = (("--include", "include"), ("--exclude", "exclude"), ("--set-title", "set_title"),
             ("--set-breaks", "structure"), ("--set-encore", "structure"),
             ("--overrule", "overrule"), ("--recording", "switch_recording"),
             ("--venue", "venue"), ("--city", "city"))


def _load(p: Path):
    return json.loads(p.read_text())


def _auto(rec: dict) -> bool:
    return bool(rec["gate"]) and not rec["vetoes"] and all(g["passed"] for g in rec["gate"])


def _applicable(rec: dict) -> list[tuple[int, dict]]:
    return [(i, e) for i, e in enumerate(rec["verdict"].get("edits", []))
            if e.get("op") not in PROPOSE_ONLY_OPS]


def category(row: dict, rec: dict | None) -> str:
    if rec is None or row["outcome"] != runner.DRY_RUN:
        return row["outcome"]
    if _auto(rec):
        return "would auto-apply"
    return "held with proposal" if _applicable(rec) else "held, no proposal"


def _target(e: dict) -> str:
    for k in ("file", "identifier", "flag", "venue", "city"):
        if k in e:
            return str(e[k])
    if "breaks_after" in e:
        return f"breaks_after={e['breaks_after']} encore_after={e.get('encore_after')}"
    return ""


def _proto_ops(proto: dict) -> set[str]:
    act = proto.get("action") or {}
    cmds = [s.get("cmd", "") if isinstance(s, dict) else str(s)
            for s in (act.get("steps") or act.get("commands") or [])]
    tokens = {t for c in cmds for t in c.split()}          # whole flags: --clear-include != --include
    return {op for flag, op in PROTO_OPS if flag in tokens}


def _table(head: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    return out + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]


def compare(out: Path, *, verdicts_dir: Path = DEFAULT_VERDICTS) -> Path:
    shows = _load(out / "shows.json")
    pop = _load(out / "population.json") if (out / "population.json").exists() else {}
    arms = [a for a in ARMS if (out / a / "costs.jsonl").exists()]
    sampled = Counter(s["cls"] for s in shows)
    data: dict[str, dict[str, tuple[dict, dict | None]]] = {}
    for a in arms:
        rows = {}
        for l in (out / a / "costs.jsonl").read_text().splitlines():
            if l.strip():
                r = json.loads(l)
                p = out / a / f"{r['slug']}.json"
                rows[r["slug"]] = (r, _load(p) if p.exists() else None)
        data[a] = rows
    md = ["# Adjudicator pilot comparison", ""]

    md += ["## Outcomes per class and arm", ""]
    rows = []
    for cls in CLASSES:
        for a in arms:
            c = Counter(category(r, rec) for r, rec in data[a].values() if r["cls"] == cls)
            if c:
                rows.append([cls, a, sampled[cls], pop.get(cls, "?"),
                             ", ".join(f"{k}: {v}" for k, v in sorted(c.items()))])
    md += _table(["class", "arm", "sampled", "population", "outcomes"], rows)

    md += ["", "## Projected held-with-proposal", "",
           "Sampled share of each class that ends held with a proposal, scaled to the held "
           "population.", ""]
    rows = []
    for cls in CLASSES:
        for a in arms:
            mine = [r for r, rec in data[a].values() if r["cls"] == cls]
            if not mine:
                continue
            k = sum(category(r, rec) == "held with proposal"
                    for r, rec in data[a].values() if r["cls"] == cls)
            rows.append([cls, a, f"{k} of {len(mine)}", pop.get(cls, "?"),
                         round(k / len(mine) * pop[cls], 1) if cls in pop else "?"])
    total = {a: sum(round(r[4]) for r in rows if r[1] == a and isinstance(r[4], float))
             for a in arms}
    md += _table(["class", "arm", "held with proposal", "population", "projected"], rows)
    md += ["", "Projected total: " + ", ".join(f"{a} {total[a]}" for a in arms)]

    md += ["", "## Partial-tape classes", "",
           "Could the gate auto-apply them at all?", ""]
    for cls in (PARTIAL, PARTIAL_SIBLING):
        for a in arms:
            recs = [rec for r, rec in data[a].values()
                    if r["cls"] == cls and rec is not None]
            blocked = [rec for rec in recs if not _auto(rec)]
            md.append(f"- {cls}, {a}: {len(recs) - len(blocked)} of {len(recs)} auto-applicable; "
                      f"{len(blocked)} blocked")
            tally: Counter = Counter()
            for rec in blocked:
                tally.update(rec["vetoes"])
                tally.update(f"{g['op']}: {g['reason'] or g['bar']}" for g in rec["gate"]
                             if not g["passed"])
                if not rec["gate"] and not rec["vetoes"]:
                    tally["no edits"] += 1
            md += [f"    - {n} x {reason}" for reason, n in tally.most_common()]

    md += ["", "## Disagreements between arms", ""]
    if len(arms) == 2:
        a, b = arms
        for slug in dict.fromkeys([*data[a], *data[b]]):
            missing = [x for x in arms if slug not in data[x]]
            if missing:
                md.append(f"- {slug}: missing in {', '.join(missing)}")
                continue
            (ra, ea), (rb, eb) = data[a][slug], data[b][slug]
            ca, cb = category(ra, ea), category(rb, eb)
            sa = sorted((e["op"], _target(e)) for _, e in _applicable(ea)) if ea else []
            sb = sorted((e["op"], _target(e)) for _, e in _applicable(eb)) if eb else []
            if ca != cb or sa != sb:
                md.append(f"- {slug} ({ra['cls']}): {a} {ca} {sa} / {b} {cb} {sb}")
    else:
        md.append("(needs both arms)")

    md += ["", "## Agreement with the prototype verdicts", ""]
    for a in arms:
        kind_rows, op_stats = Counter(), defaultdict(Counter)
        for slug, (r, rec) in data[a].items():
            proto = _read_proto(verdicts_dir, slug)
            if proto is None or rec is None:
                continue
            pk = (proto.get("action") or {}).get("kind")
            pk = pk if pk in ("fix", "overrule") else "hold"
            kind_rows[(pk, rec["verdict"].get("kind"))] += 1
            mine = {e["op"] for _, e in _applicable(rec)}
            theirs = _proto_ops(proto)
            for op in {x for _, x in PROTO_OPS}:
                key = ("both" if op in mine and op in theirs else
                       "arm only" if op in mine else "prototype only" if op in theirs else None)
                if key:
                    op_stats[op][key] += 1
        md += [f"### {a}: by kind (prototype -> {a})", ""]
        md += _table(["prototype", a, "shows"],
                     [[p, m, n] for (p, m), n in sorted(kind_rows.items(), key=str)]) \
            if kind_rows else ["(no prototype verdicts)"]
        md += ["", f"### {a}: by edit target", ""]
        md += _table(["edit", "both", "arm only", "prototype only"],
                     [[op, s["both"], s["arm only"], s["prototype only"]]
                      for op, s in sorted(op_stats.items())])
        md.append("")

    md += ["## Trial applies", "",
           "A trial apply is applied, then restored: what it measured about the re-run.", ""]
    for a in arms:
        md += [f"### {a}", ""]
        lines = []
        for slug, (r, rec) in data[a].items():
            if not r.get("trial"):
                continue
            res = (rec or {}).get("result") or {}
            kind = r.get("trial_kind") or "other"
            if res.get("status") == "applied":
                verdict_ = "applied, still held" if res.get("held") else "applied, hold cleared"
            else:
                verdict_ = str(res.get("status") or "no result")
            detail = []
            if res.get("diff"):
                detail.append("restore reasons: " + "; ".join(res["diff"]))
            if res.get("error"):
                detail.append(f"error: {res['error']}")
            if res.get("changes"):
                detail.append("changes: " + "; ".join(res["changes"]))
            if res.get("reheld"):
                detail.append("re-hold overrules: " + "; ".join(res["reheld"]))
            lines.append(f"- {slug} ({r['cls']}) {kind}: {verdict_}"
                         + (f" [{' | '.join(detail)}]" if detail else ""))
        md += lines or ["(none)"]
        md.append("")

    md += ["## Cost and wall time", "",
           "Judge-only rows (one LLM call) and trial rows (judge plus a trial apply, which "
           "re-runs vet and brief) are separate. Rows whose 5-hour meter fell or is unread "
           "(a window reset) are counted in the last column and left out of the point means.",
           ""]
    held_total = sum(pop.values())
    rows, proj = [], {}
    for a in arms:
        for kind, flag in (("judge-only", False), ("trial", True)):
            rs = [r for r, _ in data[a].values() if bool(r.get("trial")) == flag]
            ok = [r for r in rs if r["five_hour_before"] is not None
                  and r["five_hour_after"] is not None
                  and r["five_hour_after"] >= r["five_hour_before"]]
            if not rs:
                continue
            mean_d = sum(r["five_hour_after"] - r["five_hour_before"] for r in ok) / len(ok) \
                if ok else None
            mean_w = sum(r["wall_s"] for r in rs) / len(rs)
            rows.append([a, kind, len(rs), f"{mean_d:.2f}" if mean_d is not None else "n/a",
                         f"{mean_w:.1f}", len(rs) - len(ok)])
            if not flag:
                proj[a] = (mean_d, mean_w)
    md += _table(["arm", "rows", "shows", "mean 5h-meter points/show", "mean wall s",
                  "dropped from points"], rows)
    md += ["", f"Projected full sweep ({held_total} held shows), from the judge-only rows:"]
    for a, (d, w) in proj.items():
        md.append(f"- {a}: " + (f"{d * held_total:.0f} points, " if d is not None
                                else "points n/a, ") + f"{w * held_total / 3600:.1f} h wall")

    md += ["", "## Per-show cost", ""]
    for a in arms:
        md += [f"### {a}", ""]
        prow = []
        for slug, (r, _) in data[a].items():
            b_, a_ = r["five_hour_before"], r["five_hour_after"]
            prow.append([slug, r["cls"], r["outcome"],
                         (r.get("trial_kind") or "other") if r.get("trial") else "-",
                         f"{a_ - b_:.1f}" if b_ is not None and a_ is not None else "n/a",
                         f"{r['wall_s']:.1f}"])
        md += _table(["slug", "class", "outcome", "trial", "5h delta", "wall s"], prow)
        md.append("")

    def auto_edits(a):
        for slug, (r, rec) in data[a].items():
            if rec is not None and r["outcome"] == runner.DRY_RUN and _auto(rec):
                for g in rec["gate"]:
                    e = rec["verdict"]["edits"][g["index"]]
                    yield slug, r["cls"], g, e

    def edit_lines(a, only_strict):
        lines = []
        for slug, cls, g, e in auto_edits(a):
            strict = g["bar"] in STRICT_BARS or g["op"] == "switch_recording"
            if only_strict and not strict:
                continue
            quotes = "; ".join(f"[{v['kind']}] {v['quote']}" for v in e.get("evidence", []))
            lines.append(f"- {slug} ({cls}) {g['op']} bar={g['bar']} {_target(e)} "
                         f"conf={e.get('confidence')}: {quotes}")
        return lines or ["(none)"]

    md += ["", "## Strict surface (for Shawn)", "",
           "Auto-applied edits with bar long, title or structure, or op switch_recording."]
    for a in arms:
        md += ["", f"### {a}", ""] + edit_lines(a, True)
    md += ["", "## Auto-apply list (for the Opus reviewer)", "",
           "Every edit of a verdict the gate would auto-apply."]
    for a in arms:
        md += ["", f"### {a}", ""] + edit_lines(a, False)
    path = out / "compare.md"
    path.write_text("\n".join(md) + "\n")
    return path


# ------------------------------------------------------------------ main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--config", type=Path, default=None, help="llama config.toml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select")
    s.add_argument("--n", type=int, default=30)
    s.add_argument("--seed", type=int, default=20261106)
    s.add_argument("--out", type=Path, default=DEFAULT_OUT)
    s.add_argument("--verdicts", type=Path, default=DEFAULT_VERDICTS)
    r = sub.add_parser("run")
    r.add_argument("--arm", choices=ARMS, required=True)
    r.add_argument("--out", type=Path, default=DEFAULT_OUT)
    r.add_argument("--trial-applies", type=int, default=3)
    r.add_argument("--stop-at-5h", type=float, default=STOP_AT_5H,
                   help="stop before a show when the 5-hour window is at/above this percent")
    r.add_argument("--stop-at-7d", type=float, default=STOP_AT_7D,
                   help="stop before a show when the 7-day window is at/above this percent")
    c = sub.add_parser("compare")
    c.add_argument("--out", type=Path, default=DEFAULT_OUT)
    c.add_argument("--verdicts", type=Path, default=DEFAULT_VERDICTS)
    args = ap.parse_args(argv)
    if args.cmd == "compare":
        print(compare(args.out, verdicts_dir=args.verdicts))
        return 0
    config = load_config(args.config)
    if args.cmd == "select":
        select(config, args.out, n=args.n, seed=args.seed, verdicts_dir=args.verdicts)
        return 0
    try:
        run(args.arm, config=config, out=args.out, trial_applies=args.trial_applies,
            stop_at_5h=args.stop_at_5h, stop_at_7d=args.stop_at_7d)
    except PilotRefused as exc:
        print(exc, file=sys.stderr)
        return EXIT_REFUSED
    except PilotStopped as exc:
        print(exc, file=sys.stderr)
        return EXIT_STOPPED
    return 0


if __name__ == "__main__":
    sys.exit(main())
