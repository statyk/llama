"""scripts/audio_check_population.py (audio-check plan Task 9; spec "Pass bar").
Synthetic tsv + summary under tmp_path."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import audio_check_population as pop

HEADER = ["slug", "source_file", "station_file", "title", "rule", "duration_sec",
          "size_held", "operator_label", "run_055", "frac_055", "music_chosen"]


def _tsv_row(slug, src, title="Tuning", label="", run=0, frac=0.0, chosen=False):
    return {"slug": slug, "source_file": src, "station_file": f"01 - {title}.mp3",
            "title": title, "rule": "A", "duration_sec": "300", "size_held": "False",
            "operator_label": label, "run_055": str(run), "frac_055": f"{frac:.2f}",
            "music_chosen": "True" if chosen else "False"}


def _population(n_held=28):
    """n_held shows each with one caught labelled song, plus junk rows."""
    rows = [_tsv_row(f"held{i}", "a.mp3", label="song", run=300, frac=0.95, chosen=True)
            for i in range(n_held)]
    rows += [_tsv_row(f"junk{i}", "b.mp3", label="junk" if i % 2 else "") for i in range(10)]
    return rows


def _write_tsv(tmp_path, rows):
    p = tmp_path / "population2.tsv"
    lines = ["\t".join(HEADER)] + ["\t".join(r[h] for h in HEADER) for r in rows]
    p.write_text("\n".join(lines) + "\n")
    return p


def _summary_from(rows, tmp_path, override=None, drop=()):
    override = override or {}
    files = []
    for r in rows:
        key = (r["slug"], r["source_file"])
        if key in drop:
            continue
        outcome = "music" if r["music_chosen"] == "True" else "junk"
        outcome = override.get(key, outcome)
        files.append({"slug": key[0], "source_file": key[1], "outcome": outcome,
                      "run_sec": 0, "frac": 0.0,
                      "error": "fetch failed" if outcome == "failed" else None,
                      "cached": False})
    p = tmp_path / "summary.json"
    p.write_text(json.dumps({"version": "v", "started_at": "s", "finished_at": "f",
                             "files": files}))
    return p


def _run(tmp_path, rows, capsys, **kw):
    tsv = _write_tsv(tmp_path, rows)
    summ = _summary_from(rows, tmp_path, **kw)
    rc = pop.main(["--summary", str(summ), "--tsv", str(tsv)])
    return rc, capsys.readouterr().out


def test_population_script_pass_and_fail(tmp_path, capsys):
    rows = _population()
    rc, out = _run(tmp_path, rows, capsys)
    assert rc == 0 and "PASS" in out and "held shows: 28" in out
    # a junk row flipping to music is listed, not blocking (29 held is inside the bar)
    rc, out = _run(tmp_path, rows, capsys, override={("junk0", "b.mp3"): "music"})
    assert rc == 0 and "junk0 b.mp3 'Tuning': junk -> music" in out
    # a caught song flipping to junk blocks
    rc, out = _run(tmp_path, rows, capsys, override={("held0", "a.mp3"): "junk"})
    assert rc == 1 and "FAIL" in out and "held0 a.mp3" in out.split("FAIL:")[1]


def test_population_at_bar_flip_is_listed_not_blocking(tmp_path, capsys):
    rows = _population()
    rows[0] = _tsv_row("held0", "a.mp3", label="song", run=125, frac=0.95, chosen=True)
    rows[1] = _tsv_row("held1", "a.mp3", label="song", run=300, frac=0.64, chosen=True)
    rows[2] = _tsv_row("smashingpumpkins-2008-08-12", "a.mp3", label="song", run=300,
                       frac=0.95, chosen=True)
    flips = {(r["slug"], "a.mp3"): "junk" for r in rows[:3]}
    rc, out = _run(tmp_path, rows, capsys, override=flips)
    assert rc == 0, out
    assert "at-bar song flips (listed, not blocking)" in out
    # just outside the bar: run 131, frac 0.66
    rows[0] = _tsv_row("held0", "a.mp3", label="song", run=131, frac=0.66, chosen=True)
    rc, out = _run(tmp_path, rows, capsys, override={("held0", "a.mp3"): "junk"})
    assert rc == 1


def test_population_unlabelled_caught_flip_does_not_block(tmp_path, capsys):
    rows = _population(n_held=29)
    rows[0] = _tsv_row("held0", "a.mp3", label="junk", run=300, frac=0.95, chosen=True)
    rc, out = _run(tmp_path, rows, capsys, override={("held0", "a.mp3"): "junk"})
    assert rc == 0 and "music -> junk" in out


def test_population_held_count_outside_bar_blocks(tmp_path, capsys):
    rc, out = _run(tmp_path, _population(n_held=32), capsys)
    assert rc == 1 and "held count 32 is outside 28 +/- 3" in out
    rc, _ = _run(tmp_path, _population(n_held=31), capsys)
    assert rc == 0
    rc, _ = _run(tmp_path, _population(n_held=25), capsys)
    assert rc == 0
    rc, _ = _run(tmp_path, _population(n_held=24), capsys)
    assert rc == 1


def test_population_skips_silence_rows(tmp_path, capsys):
    rows = _population()
    rows += [_tsv_row(f"gomez{i}", "s.mp3", title="Silence", label="song", run=160,
                      frac=0.84, chosen=True) for i in range(4)]
    # Silence rows are absent from the summary (no longer junk titles): not blocking,
    # not reported absent, not counted held.
    rc, out = _run(tmp_path, rows, capsys, drop={(f"gomez{i}", "s.mp3") for i in range(4)})
    assert rc == 0 and "gomez" not in out and "held shows: 28" in out


def test_population_reports_absent_rows_separately(tmp_path, capsys):
    rows = _population()
    rc, out = _run(tmp_path, rows, capsys, drop={("junk3", "b.mp3")})
    assert rc == 0
    assert "absent from the summary 1" in out
    assert "absent from the summary:\n  junk3 b.mp3 'Tuning'" in out
    assert "flips 0" in out


def test_population_missing_caught_song_blocks(tmp_path, capsys):
    rows = _population(n_held=29)
    rc, out = _run(tmp_path, rows, capsys, drop={("held0", "a.mp3")})
    assert rc == 1 and "caught song missing from the summary: held0 a.mp3" in out


def test_population_failed_caught_song_blocks(tmp_path, capsys):
    rows = _population(n_held=29)
    rc, out = _run(tmp_path, rows, capsys, override={("held0", "a.mp3"): "failed"})
    assert rc == 1 and "caught song failed: held0 a.mp3" in out
    # a failed junk row is listed, not blocking
    rc, out = _run(tmp_path, rows, capsys, override={("junk0", "b.mp3"): "failed"})
    assert rc == 0 and "failed:\n  junk0 b.mp3" in out


def test_population_unreadable_summary_exits_2(tmp_path, capsys):
    tsv = _write_tsv(tmp_path, _population())
    bad = tmp_path / "s.json"
    bad.write_text("{nope")
    assert pop.main(["--summary", str(bad), "--tsv", str(tsv)]) == 2


def test_population_real_tsv_reads_28_held_when_reproduced(tmp_path, capsys):
    """The committed population2.tsv reproduced exactly passes with 28 held shows."""
    rows = pop.read_tsv(pop.DEFAULT_TSV)
    summ = _summary_from(rows, tmp_path)
    assert pop.main(["--summary", str(summ)]) == 0
    assert "held shows: 28" in capsys.readouterr().out
