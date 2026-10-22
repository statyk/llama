p='scripts/replay_holds.py'
s=open(p).read()
def rep(a,b):
    global s
    assert a in s, a[:50]
    s=s.replace(a,b,1)
rep("def _taper_changes(base: dict, cand: dict, root: Path, config_path: Path | None)","def _taper_changes(base: dict, cand: dict, root: Path, delivery: Path | None)")
rep("    delivery, delivery_read = None, False\n","")
rep('''            if not delivery_read:
                delivery, delivery_read = _delivery_path(config_path), True
''','')
rep('''        raise Refusal(f"no such config: {config_arg}")
''','''        raise Refusal(f"no such config: {config_arg}")
    delivery = _delivery_path(config_arg)      # a malformed config also refuses before any write
''')
rep("_taper_changes(base, cand, root, config_arg)","_taper_changes(base, cand, root, delivery)")
rep('''        "taper_changes.txt: " + ", ".join(f"{k} {v}" for k, v in tcounts.items()),''','''        "taper_changes.txt: " + ", ".join(f"{k} {v}" for k, v in tcounts.items()),
        f"voiced check: delivery_path {delivery}" if delivery is not None
        else "voiced check: off (no delivery_path in config)",''')
open(p,'w').write(s)

p='scripts/test_replay_holds.py'
s=open(p).read()
s=s.replace('''def _tree_state(''','''@pytest.fixture(autouse=True)
def _hermetic_default_config(tmp_path_factory, monkeypatch):
    """compare reads the default config for delivery_path: never ~/.llama in a test."""
    monkeypatch.setattr(rh, "DEFAULT_ROOT", tmp_path_factory.mktemp("default-root"))


def _tree_state(''',1)
s+='''

def test_taper_changes_numbered_to_encore_is_not_a_plain_rename_and_rows_show_labels(tmp_path):
    base, cand, root = _clone_slugs(tmp_path, None)
    b, c = json.loads(base.read_text()), json.loads(cand.read_text())
    slug = "show-enc"
    for arm in (b, c):
        _clone(arm, CLEAN_SLUG, slug, "packaged")
        _row(arm, slug).update(outcome="clears", set_changes=[], segue_changes=[], notes=[])
    (root / "shows" / slug).mkdir(parents=True)
    (root / "shows" / slug / "show.json").write_text(json.dumps(
        {"tracks": [{"index": i + 1, "set": s} for i, s in enumerate(["1", "1", "2"])]}))
    _row(b, slug)["sets"] = ["1", "1", "2"]
    _row(b, slug)["filler"] = [False] * 3
    _owned(_row(c, slug), ["1", "1", "encore"])
    _write(base, b)
    _write(cand, c)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    text = (out / "taper_changes.txt").read_text()
    renamed = text.split("== labels renamed")[1].split("\\n== ")[0]
    moved = text.split("== songs moved")[1].split("\\n== ")[0]
    assert slug not in renamed and slug in moved
    row = [l for l in moved.splitlines() if slug in l][0]
    assert "before [2] after [2]" in row
    assert "before 1x2 2x1 | after 1x2 encorex1 | stored 1x2 2x1" in row


def test_provenance_only_row_says_step1_not_overruled(tmp_path):
    base, cand, root = _clone_slugs(tmp_path, None)
    b, c = json.loads(base.read_text()), json.loads(cand.read_text())
    slug = "show-prov2"
    for arm in (b, c):
        _clone(arm, CLEAN_SLUG, slug, "packaged")
        _row(arm, slug).update(outcome="clears", set_changes=[], segue_changes=[], notes=[])
    (root / "shows" / slug).mkdir(parents=True)
    (root / "shows" / slug / "show.json").write_text(json.dumps(
        {"tracks": [{"index": i + 1, "set": s} for i, s in enumerate(["1", "2"])]}))
    _row(b, slug)["sets"] = ["1", "2"]
    _owned(_row(c, slug), ["1", "2"], step1="jerrybase")
    _write(base, b)
    _write(cand, c)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    row = [l for l in (out / "taper_changes.txt").read_text().splitlines() if slug in l][0]
    assert "step1: jerrybase" in row and "overruled" not in row


def test_stored_llm_section_excludes_an_unreplayable_candidate(tmp_path):
    base, cand, root = _clone_slugs(tmp_path, None)
    b, c = json.loads(base.read_text()), json.loads(cand.read_text())
    for arm in (b, c):
        _clone(arm, CLEAN_SLUG, "llm-unrep", "packaged")
    _row(b, "llm-unrep").update(outcome="needs-llm", needs_llm=["stored alignment llm"])
    _row(c, "llm-unrep").update(outcome="unreplayable", unreplayable="cache miss: z")
    _write(base, b)
    _write(cand, c)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    text = (out / "taper_changes.txt").read_text()
    assert "stored-llm shows now replayable (0)" in text


def test_compare_refuses_a_missing_config_before_writing_and_summary_names_delivery(tmp_path, capsys):
    base, cand = _two_arms(tmp_path)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out),
                    "--config", str(tmp_path / "nope.toml")]) == 2
    assert "no such config" in capsys.readouterr().err
    assert not out.exists()
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    assert "voiced check: off (no delivery_path in config)" in (out / "summary.txt").read_text()
    cfg = tmp_path / "c.toml"
    cfg.write_text(f'delivery_path = "{tmp_path / "st"}"\\n')
    assert rh.main(["compare", str(base), str(cand), "--out", str(out), "--config", str(cfg)]) == 0
    assert f"voiced check: delivery_path {tmp_path / 'st'}" in (out / "summary.txt").read_text()
'''
open(p,'w').write(s)
