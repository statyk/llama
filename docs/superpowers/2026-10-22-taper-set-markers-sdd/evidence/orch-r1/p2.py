p='scripts/replay_holds.py'
s=open(p).read()
def rep(a,b):
    global s
    assert a in s, a[:50]
    s=s.replace(a,b,1)
rep('''    if _label_breaks(b) != _label_breaks(a):
        return "songs moved"
''','''    if _label_breaks(b) != _label_breaks(a):
        return "songs moved"
    if [_is_encore(x) for x in b] != [_is_encore(x) for x in a]:
        return "songs moved"           # a set became (or stopped being) the encore: a boundary kind changed
''')
rep('''def _tier(''','''def _is_encore(label) -> bool:
    return str(label).lower() in ("encore", "e")


def _runs(labels: list) -> str:
    """Compact label runs: ['1','1','2','encore'] -> '1x2 2x1 encorex1'."""
    out, i = [], 0
    while i < len(labels):
        j = i
        while j < len(labels) and labels[j] == labels[i]:
            j += 1
        out.append(f"{labels[i]}x{j - i}")
        i = j
    return " ".join(out) or "-"


def _tier(''')
rep('''        tiers[tier].append(
            f"  {slug}  [{state}]  before {_j(_label_breaks(before))} after {_j(_label_breaks(after))} "
            f"stored {_j(_label_breaks(stored))}  source: {c.get('taper_source')}  "
            f"overruled: {c.get('step1_alignment')}")''','''        step1 = ("overruled" if before != after else "step1")   # nothing was overruled when labels agree
        tiers[tier].append(
            f"  {slug}  [{state}]  before {_j(_label_breaks(before))} after {_j(_label_breaks(after))} "
            f"stored {_j(_label_breaks(stored))}  labels: before {_runs(before)} | after {_runs(after)} "
            f"| stored {_runs(stored)}  source: {c.get('taper_source')}  "
            f"{step1}: {c.get('step1_alignment')}")''')
rep('''        if "stored alignment llm" in (b.get("needs_llm") or []) and c.get("outcome") != "needs-llm":''','''        if ("stored alignment llm" in (b.get("needs_llm") or [])
                and c.get("outcome") not in ("needs-llm", "unreplayable")):''')
# up-front config validation
rep('''def _delivery_path(config_path: Path | None) -> Path | None:
    if config_path is not None and not config_path.exists():
        raise Refusal(f"no such config: {config_path}")
    return load_config''','''def _delivery_path(config_path: Path | None) -> Path | None:
    return load_config''')
rep('''def compare(args: argparse.Namespace) -> int:
    base, cand = _load_arm(args.base), _load_arm(args.cand)
''','''def compare(args: argparse.Namespace) -> int:
    base, cand = _load_arm(args.base), _load_arm(args.cand)
    config_arg = getattr(args, "config", None)
    if config_arg is not None and not config_arg.exists():    # before anything is written, as `run`
        raise Refusal(f"no such config: {config_arg}")
''')
rep('''        tch, tcounts = _taper_changes(base, cand, root, getattr(args, "config", None))''','''        tch, tcounts = _taper_changes(base, cand, root, config_arg)''')
open(p,'w').write(s)
