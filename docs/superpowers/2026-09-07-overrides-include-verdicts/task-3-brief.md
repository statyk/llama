### Task 3: show the dropped files

The `excluded (N):` section, the `+` marker, the dropped count and the
`include=` override line. `_excluded_handles` is created here and is the single
producer of the `x`-handles Task 4's resolver consumes.

**Files:**
- Modify: `packages/llama/src/llama/cli.py:1243-1265` (`_format_tracks`), `:1499` (the `recording:` line), `:1503-1524` (the `overrides:` line), `:1536-1578` (`_print_show_json`)
- Test: `packages/llama/tests/test_show_cmd.py`

**Interfaces:**
- Consumes: `Track.included`, `Show.excluded_files` entries carrying `duration_sec` (Tasks 1-2).
- Produces: `cli._excluded_handles(show) -> list[tuple[str, dict]]` — `[("x1", entry), ("x2", entry), …]` in `show.excluded_files` order.

- [ ] **Step 1: Write the failing tests**

Append to `packages/llama/tests/test_show_cmd.py`, following that file's
existing `_cfg`/`build`/`cli_invoke` pattern:

```python
def _show_with_excluded(tmp_path: Path):
    """A gathered show whose show.json carries two junk-filtered files and one
    re-admitted track."""
    from llama.models import Show, Track
    from llama.workspace import write_artifact
    from test_catalog import build

    ws = build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})
    s = read_model(ws.show, Show)
    s.tracks = [
        Track(index=1, set="1", title="Introduction", filename="intro.mp3",
              title_source="override", duration_sec=37.0, included=True),
        Track(index=2, set="1", title="Morning Dew", filename="a.mp3",
              title_source="tags", duration_sec=300.0),
    ]
    s.excluded_files = [
        {"filename": "spam.mp3", "reasons": ["filename convention mismatch"],
         "duration_sec": 72.0},
        {"filename": "tuning.mp3", "reasons": ["implausibly short"],
         "duration_sec": 12.0},
    ]
    write_artifact(ws.show, s)
    return ws


def test_excluded_handles_number_from_one_in_show_json_order():
    from llama.cli import _excluded_handles

    class _S:
        excluded_files = [{"filename": "a.mp3"}, {"filename": "b.mp3"}]

    assert [(h, e["filename"]) for h, e in _excluded_handles(_S())] == [
        ("x1", "a.mp3"), ("x2", "b.mp3")]


def test_tracks_listing_shows_the_excluded_section(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _show_with_excluded(tmp_path)
    r = cli_invoke(cfg, "show", "gratefuldead", "--tracks")
    assert r.exit_code == 0, r.output
    assert "excluded (2):" in r.output
    assert "x1" in r.output and "spam.mp3" in r.output
    assert "filename convention mismatch" in r.output
    assert "x2" in r.output and "tuning.mp3" in r.output
    assert "0:12" in r.output


def test_tracks_listing_marks_a_re_admitted_track(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _show_with_excluded(tmp_path)
    r = cli_invoke(cfg, "show", "gratefuldead", "--tracks")
    assert "+ = re-admitted by operator" in r.output
    intro = next(ln for ln in r.output.splitlines() if "intro.mp3" in ln)
    dew = next(ln for ln in r.output.splitlines() if "Morning Dew" in ln)
    assert "1.+" in intro
    assert "2.+" not in dew


def test_dropped_count_shows_without_the_tracks_flag(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _show_with_excluded(tmp_path)
    r = cli_invoke(cfg, "show", "gratefuldead")
    assert "(2 tracks, 2 dropped)" in r.output
    assert "excluded (2):" not in r.output


def test_no_dropped_clause_when_nothing_was_dropped(tmp_path: Path):
    cfg = _cfg(tmp_path)
    build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})
    r = cli_invoke(cfg, "show", "gratefuldead")
    assert "dropped" not in r.output


def test_overrides_line_and_json_carry_include(tmp_path: Path):
    import json as _json

    from llama.models import Overrides
    from llama.workspace import write_artifact

    cfg = _cfg(tmp_path)
    ws = _show_with_excluded(tmp_path)
    write_artifact(ws.overrides, Overrides(include=["intro.mp3"]))
    r = cli_invoke(cfg, "show", "gratefuldead")
    assert "include=['intro.mp3']" in r.output
    r = cli_invoke(cfg, "show", "gratefuldead", "--json", "--tracks")
    data = _json.loads(r.output)
    assert data["overrides"]["include"] == ["intro.mp3"]
    assert [e["filename"] for e in data["excluded"]] == ["spam.mp3", "tuning.mp3"]
    assert data["tracks"][0]["included"] is True
```

If `read_model` / `build` / `_cfg` are not already imported at the top of
`test_show_cmd.py`, add the imports the file's existing tests use.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
./.venv/bin/python -m pytest packages/llama/tests/test_show_cmd.py -q -k "excluded or dropped or re_admitted or include"
```

Expected: FAIL — `ImportError` on `_excluded_handles`, and none of the strings
appear in the output.

- [ ] **Step 3: Add `_excluded_handles` and extend `_format_tracks`**

In `packages/llama/src/llama/cli.py`, immediately above `_format_tracks`:

```python
def _excluded_handles(show) -> list[tuple[str, dict]]:
    """`x`-handles for the junk-filtered files, in show.json order.

    ONE producer, consumed by both the `--tracks` listing and `fix --include`'s
    token resolver, so the handle an operator reads is always the handle the
    resolver means."""
    return [(f"x{i}", e) for i, e in enumerate(show.excluded_files, start=1)]
```

Rewrite the body of `_format_tracks` (keep the existing `_MARK` comment block
verbatim, and correct its last two lines — see Step 5):

```python
    _MARK = {True: " ", False: "?", None: "-"}
    lines = ["tracks:"]
    for t in show.tracks:
        title = t.title if t.title_source != "unresolved" else "(unknown)"
        lines.append(f"  {t.index:2d}.{'+' if t.included else ' '} set {t.set:6.6s} "
                     f"{_MARK[t.matched]} {title:28.28s} "
                     f"{t.title_source:14.14s} {_fmt_dur(t.duration_sec):>6s}  {t.filename}")
    if any(t.matched is False for t in show.tracks):
        lines.append("  ? = no setlist match")
    if any(t.matched is None for t in show.tracks):
        lines.append("  - = not measured")
    if any(t.included for t in show.tracks):
        lines.append("  + = re-admitted by operator (the junk filter had dropped it)")
    handles = _excluded_handles(show)
    if handles:
        width = max(len(e["filename"]) for _, e in handles)
        lines.append(f"excluded ({len(handles)}):")
        for handle, e in handles:
            lines.append(f"  {handle:>3s}  {e['filename']:<{width}s}  "
                         f"{_fmt_dur(e.get('duration_sec')):>6s}  "
                         f"{', '.join(e.get('reasons', []))}")
        lines.append(f"  re-admit one with: llama fix <show> --include {handles[0][0]}")
    return lines
```

- [ ] **Step 4: Add the dropped count, the `include=` override line and the JSON fields**

In `_print_show_entry`, replace the `recording:` line with:

```python
    dropped = f", {len(s.excluded_files)} dropped" if s.excluded_files else ""
    typer.echo(f"recording: {s.identifier}  ({len(s.tracks)} tracks{dropped})")
```

In the same function, immediately after the `if ov.exclude:` clause:

```python
    if ov.include:
        parts.append(f"include={ov.include}")
```

In `_print_show_json`, add `"include": ov.include,` to the `data["overrides"]`
dict (next to `"exclude"`), and inside the `if show_tracks:` block add:

```python
        data["excluded"] = s.excluded_files if s is not None else None
```

- [ ] **Step 5: Correct the stale duration comment**

The comment above `_MARK` in `_format_tracks` ends:

```
    # the duration column's own "?" (_fmt_dur) can't co-occur: junk drops
    # files with no length.
```

That is now false — `--include` can re-admit a file excluded for
`missing duration`. Replace those two lines with:

```
    # the duration column's own "?" (_fmt_dur) means no length in the item
    # metadata. Junk drops such files, so it appears only on a track the
    # operator re-admitted via overrides.include; package.py re-probes the
    # real duration from the downloaded file at package time.
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
./.venv/bin/python -m pytest packages/llama/tests/test_show_cmd.py -q
```

Expected: PASS.

- [ ] **Step 7: Run the whole suite**

```bash
./.venv/bin/python -m pytest -q
```

Expected: all green. Existing tests that assert on `--tracks` output may pin
the old column layout (the `+` column shifts every track line by one
character); update those assertions to the new layout rather than reverting the
column.

- [ ] **Step 8: Commit**

```bash
git add packages/llama/src/llama/cli.py packages/llama/tests/test_show_cmd.py
git commit -m "feat(show): list junk-filtered files with x-handles and mark re-admitted tracks"
```

---

