p='scripts/replay_holds.py'
s=open(p).read()

def rep(a,b,count=1):
    global s
    assert a in s, a[:60]
    s=s.replace(a,b,count)

rep('''    ("5c.1", "jerrybase set closer "),''','''    ("taper", "set breaks from the taper's markers"),   # also any note ending (taper's markers)
    ("5c.1", "jerrybase set closer "),''')
rep('''"narration_candidates.html", "predicted_list.json",''','''"taper_cleared.txt", "taper_changes.txt", "narration_candidates.html", "predicted_list.json",''')
rep('''            for g, prefix in NOTE_GROUPS:
                if n.startswith(prefix):''','''            for g, prefix in NOTE_GROUPS:
                if (_is_taper_note(n) if g == "taper" else n.startswith(prefix)):''')
rep('''def _notes_by_group(''','''def _is_taper_note(n: str) -> bool:
    """Two of the three fixed taper notes are identified by their suffix, not leading words."""
    return n.startswith("set breaks from the taper's markers") or n.endswith("(taper's markers)")


def _notes_by_group(''')

new = '''
# --- piece 2 (taper markers) reports ---

def _taper_cleared(base: dict, cand: dict) -> list[str]:
    """Every show held in the base arm whose candidate outcome clears it or is
    structure-changed (a structure-changed show is a clear a taper rule made)."""
    out = []
    for slug, c in sorted(cand["shows"].items()):
        b = base["shows"][slug]
        if b.get("state") != "held" or not _would_clear(c):
            continue
        removed = [f for f in _all_flags(b) if f not in _all_flags(c)]
        out.append(f"{slug}  {c.get('outcome')}"
                   + (f" (would be {c.get('would_be')})" if c.get("would_be") else "")
                   + f"  taper_owned: {_j(c.get('taper_owned'))}  source: {_j(c.get('taper_source'))}")
        out.append(f"  removed: {'; '.join(removed) or '(none)'}")
        out += [f"  note: {n}" for n in c.get("notes") or []]
    return out


def _stored_labels(root: Path, slug: str) -> list:
    return [t.get("set") for t in _tracks(_show_json(root, slug))]


def _apply_set_changes(labels: list, changes: list[dict] | None) -> list:
    """The stored labels with a row's `set_changes` applied (`index` is 1-based; a
    `new` of None means the track is past that tape's end)."""
    by = {c.get("index"): c.get("new") for c in changes or [] if isinstance(c, dict)}
    n = max([len(labels), *[i for i in by if isinstance(i, int)]], default=0)
    out = []
    for i in range(1, n + 1):
        v = by[i] if i in by else (labels[i - 1] if i <= len(labels) else None)
        if v is not None:
            out.append(v)
    return out


def _label_breaks(labels: list) -> list[int]:
    """Track numbers after which the set label changes."""
    return [i for i in range(1, len(labels)) if labels[i - 1] != labels[i]]


def _after_labels(c: dict, stored: list) -> list:
    return list(c["sets"]) if c.get("sets") else _apply_set_changes(stored, c.get("set_changes"))


def _before_labels(b: dict, stored: list) -> list:
    if b.get("outcome") == "needs-llm":
        return list(stored)            # the stored structure; the base could not replay it
    if b.get("sets"):
        return list(b["sets"])
    return _apply_set_changes(stored, b.get("set_changes"))


def _tier(before: list, after: list, filler: list, base_owned: bool, cand_owned: bool) -> str | None:
    if before == after:
        return "provenance only" if cand_owned and not base_owned else None
    if len(before) != len(after) or len(filler) != len(after):
        return "songs moved"           # cannot compare per track: do not under-report
    keep = [i for i, f in enumerate(filler) if not f]
    b, a = [before[i] for i in keep], [after[i] for i in keep]
    if _label_breaks(b) != _label_breaks(a):
        return "songs moved"
    return "labels renamed" if b != a else "filler labels only"


def _is_voiced(delivery: Path | None, slug: str) -> bool:
    if delivery is None:
        return False
    from llama.cli import _destination_is_voiced   # a raw-JSON read of manifest.json; writes nothing
    return _destination_is_voiced(delivery / slug)


def _delivery_path(config_path: Path | None) -> Path | None:
    if config_path is not None and not config_path.exists():
        raise Refusal(f"no such config: {config_path}")
    return load_config(config_path or DEFAULT_ROOT / "config.toml").delivery_path   # as `run`


TAPER_TIERS = ("songs moved", "labels renamed", "filler labels only", "provenance only")


def _taper_changes(base: dict, cand: dict, root: Path, config_path: Path | None) -> tuple[list[str], dict]:
    delivery, delivery_read = None, False
    tiers: dict[str, list[str]] = {t: [] for t in TAPER_TIERS}
    not_owned_nl = 0
    for slug, c in sorted(cand["shows"].items()):
        b = base["shows"][slug]
        if c.get("state") not in NON_HELD or "unreplayable" in (b.get("outcome"), c.get("outcome")):
            continue
        if c.get("outcome") == "needs-llm" and not c.get("taper_owned"):
            not_owned_nl += 1
            continue
        stored = _stored_labels(root, slug)
        before, after = _before_labels(b, stored), _after_labels(c, stored)
        filler = list(c.get("filler") or [False] * len(after))
        tier = _tier(before, after, filler, bool(b.get("taper_owned")), bool(c.get("taper_owned")))
        if tier is None:
            continue
        state = str(c.get("state"))
        if state == "delivered":
            if not delivery_read:
                delivery, delivery_read = _delivery_path(config_path), True
            if _is_voiced(delivery, slug):
                state = "voiced"
        tiers[tier].append(
            f"  {slug}  [{state}]  before {_j(_label_breaks(before))} after {_j(_label_breaks(after))} "
            f"stored {_j(_label_breaks(stored))}  source: {c.get('taper_source')}  "
            f"overruled: {c.get('step1_alignment')}")
    out = [f"needs-LLM in the candidate and not taper-owned (unchanged by this piece, not listed): "
           f"{not_owned_nl}", ""]
    for t in TAPER_TIERS:
        out += _lines(f"== {t} ({len(tiers[t])})", tiers[t])
    unrep = []
    for slug, c in sorted(cand["shows"].items()):
        b = base["shows"][slug]
        if not (c.get("state") in NON_HELD or b.get("state") in NON_HELD):
            continue
        arms = (("base", b), ("cand", c))
        why = [f"{a}: {r.get('unreplayable') or 'unreplayable'}" for a, r in arms
               if r.get("outcome") == "unreplayable"]
        why += [f"{a}: setlist.fm miss" for a, r in arms if r.get("slfm_miss")]
        if why:
            unrep.append(f"  {slug}  [{c.get('state')}]  {'; '.join(why)}")
    out += _lines(f"== unreplayable or setlist.fm-miss shipped shows ({len(unrep)})", unrep)
    moved = []
    for slug, c in sorted(cand["shows"].items()):
        b = base["shows"][slug]
        if "stored alignment llm" in (b.get("needs_llm") or []) and c.get("outcome") != "needs-llm":
            moved.append(f"  {slug}  [{c.get('state')}]  taper_owned: {_j(c.get('taper_owned'))}  "
                         f"segue changes: {_j(c.get('segue_changes'))}")
    out += _lines(f"== stored-llm shows now replayable ({len(moved)})", moved)
    return out, {**{t: len(v) for t, v in tiers.items()}, "needs-llm not owned": not_owned_nl,
                 "unreplayable": len(unrep), "stored-llm moved": len(moved)}

'''
rep("\ndef _jaccard(", new+"\ndef _jaccard(")

rep('''    _write(out, "notes.txt", _notes_txt(cand))
''','''    _write(out, "notes.txt", _notes_txt(cand))
    stripped = bool(cand.get("structure_overrides_stripped"))
    tc, tcounts = _taper_cleared(base, cand), {}
    if not stripped:   # a stripped arm replays without the operator's overrides: not the shipped library
        _write(out, "taper_cleared.txt", _lines("shows held in base and cleared (or structure-changed) in cand:", tc))
        tch, tcounts = _taper_changes(base, cand, root, getattr(args, "config", None))
        _write(out, "taper_changes.txt", tch)
''')
rep('''    stripped = bool(cand.get("structure_overrides_stripped"))
    if not stripped:   # a stripped arm can never feed''','''    if not stripped:   # a stripped arm can never feed''')
rep('''        f"notes.txt: {n_notes} note(s)",
    ] + ([''','''        f"notes.txt: {n_notes} note(s)",
    ] + (["taper reports: not written (arms replayed with --strip-structure-overrides)"] if stripped else [
        f"taper_cleared.txt: {sum(1 for x in tc if not x.startswith(' '))} show(s)",
        "taper_changes.txt: " + ", ".join(f"{k} {v}" for k, v in tcounts.items()),
    ]) + ([''')
rep('''    c.add_argument("--no-repro-gate"''','''    c.add_argument("--config", type=Path, default=None,
                   help="config file whose delivery_path the voiced check reads "
                        "(default ~/.llama/config.toml, as `run`)")
    c.add_argument("--no-repro-gate"''')
open(p,'w').write(s)
