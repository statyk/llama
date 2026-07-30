"""CLI tests for `emcee presenter add/list/show/remove`.

Modeled on llama's presenter CLI tests (packages/llama/tests/test_cli_commands.py,
around lines 383, 397, 407, 510, 545) but addressed at emcee's `app`, with the
workspace root resolved via the `EMCEE_ROOT` env var (`emcee.config.default_root`,
which also backs `EmceeConfig.root`'s default) instead of a `--config` file.
"""

from pathlib import Path

from typer.testing import CliRunner

from emcee.cli import _assignments_using_presenter, app
from emcee.config import AssignConfig, Assignment, EmceeConfig
from emcee.presenters import PresenterError

runner = CliRunner()


def test_presenter_add_and_show(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EMCEE_ROOT", str(tmp_path))
    r = runner.invoke(app, ["presenter", "add", "casey", "--name", "Casey",
                            "--sex", "male", "--voice", "american-dj",
                            "--character", "Warm FM veteran."])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "presenters" / "casey.toml").exists()

    shown = runner.invoke(app, ["presenter", "show", "casey"])
    assert shown.exit_code == 0, shown.output
    assert "Casey" in shown.output and "Warm FM veteran." in shown.output
    assert "voice=american-dj" in shown.output


def test_presenter_add_character_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EMCEE_ROOT", str(tmp_path))
    cf = tmp_path / "c.txt"
    cf.write_text("Deep tape collector.\nDry humor.")
    r = runner.invoke(app, ["presenter", "add", "deej", "--name", "DJ",
                            "--sex", "female", "--voice-clone", "/ref.wav",
                            "--character-file", str(cf)])
    assert r.exit_code == 0, r.output
    shown = runner.invoke(app, ["presenter", "show", "deej"])
    assert "Deep tape collector." in shown.output
    assert "voice=clone:/ref.wav" in shown.output


def test_presenter_add_rejects_both_or_neither_character(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EMCEE_ROOT", str(tmp_path))
    neither = runner.invoke(app, ["presenter", "add", "x", "--name", "X", "--sex", "male",
                                  "--voice", "a"])
    assert neither.exit_code != 0
    assert "give exactly one of --character / --character-file" in neither.output

    cf = tmp_path / "c.txt"
    cf.write_text("text")
    both = runner.invoke(app, ["presenter", "add", "x", "--name", "X", "--sex", "male",
                               "--voice", "a", "--character", "y",
                               "--character-file", str(cf)])
    assert both.exit_code != 0
    assert "give exactly one of --character / --character-file" in both.output


def test_presenter_add_rejects_both_or_neither_voice(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EMCEE_ROOT", str(tmp_path))
    neither = runner.invoke(app, ["presenter", "add", "x", "--name", "X", "--sex", "male",
                                  "--character", "y"])
    assert neither.exit_code != 0
    assert "invalid presenter" in neither.output

    both = runner.invoke(app, ["presenter", "add", "x", "--name", "X", "--sex", "male",
                               "--voice", "a", "--voice-clone", "/r.wav", "--character", "y"])
    assert both.exit_code != 0
    assert "invalid presenter" in both.output


def test_presenter_add_refuses_overwrite_without_force(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EMCEE_ROOT", str(tmp_path))
    args = ["presenter", "add", "casey", "--name", "Casey", "--sex", "male",
            "--voice", "american-dj", "--character", "x"]
    assert runner.invoke(app, args).exit_code == 0
    again = runner.invoke(app, args)
    assert again.exit_code != 0
    assert "exists" in again.output
    assert "use --force to overwrite" in again.output

    forced = runner.invoke(app, args + ["--force"])
    assert forced.exit_code == 0, forced.output


def test_presenter_add_missing_character_file_errors_cleanly(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EMCEE_ROOT", str(tmp_path))
    r = runner.invoke(app, ["presenter", "add", "x", "--name", "X", "--sex", "male",
                            "--voice", "a", "--character-file", str(tmp_path / "nope.txt")])
    assert r.exit_code != 0
    assert "cannot read --character-file" in r.output
    assert not isinstance(r.exception, OSError)


def test_presenter_list_empty_and_populated(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EMCEE_ROOT", str(tmp_path))
    empty = runner.invoke(app, ["presenter", "list"])
    assert empty.exit_code == 0, empty.output
    assert "no presenters" in empty.output

    runner.invoke(app, ["presenter", "add", "casey", "--name", "Casey", "--sex", "male",
                        "--voice", "american-dj", "--character", "x"])
    listed = runner.invoke(app, ["presenter", "list"])
    assert listed.exit_code == 0, listed.output
    assert "casey" in listed.output
    assert "Casey" in listed.output
    assert "american-dj" in listed.output


def test_presenter_list_renders_invalid_presenter_without_crashing(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EMCEE_ROOT", str(tmp_path))
    bad = tmp_path / "presenters" / "bad.toml"
    bad.parent.mkdir(parents=True)
    bad.write_text("name = [unclosed")
    listed = runner.invoke(app, ["presenter", "list"])
    assert listed.exit_code == 0, listed.output
    assert f"{'bad':16.16s} (invalid:" in listed.output


def test_presenter_show_bed_suffix_present_and_absent(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EMCEE_ROOT", str(tmp_path))
    runner.invoke(app, ["presenter", "add", "casey", "--name", "Casey", "--sex", "male",
                        "--voice", "american-dj", "--character", "x", "--bed", "/beds/soul.wav"])
    with_bed = runner.invoke(app, ["presenter", "show", "casey"])
    assert "bed=/beds/soul.wav" in with_bed.output

    runner.invoke(app, ["presenter", "add", "nobed", "--name", "NoBed", "--sex", "female",
                        "--voice", "v2", "--character", "y"])
    without_bed = runner.invoke(app, ["presenter", "show", "nobed"])
    assert "bed=" not in without_bed.output


def test_presenter_list_exact_column_widths(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EMCEE_ROOT", str(tmp_path))
    runner.invoke(app, ["presenter", "add", "longpresenterid12345", "--name",
                        "A Very Long On-Air Name Indeed", "--sex", "nonbinary",
                        "--voice", "american-dj", "--character", "x"])
    listed = runner.invoke(app, ["presenter", "list"])
    assert listed.exit_code == 0, listed.output
    expected = f"{'longpresenterid12345':16.16s} {'A Very Long On-Air Name Indeed':20.20s} {'nonbinary':8.8s} american-dj"
    assert expected in listed.output


def test_presenter_remove_refused_when_assignments_use_it(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EMCEE_ROOT", str(tmp_path))
    runner.invoke(app, ["presenter", "add", "casey", "--name", "Casey", "--sex", "male",
                        "--voice", "american-dj", "--character", "x"])

    import emcee.cli as cli_mod
    monkeypatch.setattr(cli_mod, "_assignments_using_presenter", lambda config, pid: ["a", "b"])

    refused = runner.invoke(app, ["presenter", "remove", "casey"], input="y\n")
    assert refused.exit_code == 1
    assert "presenter casey is used by: a, b — --force to remove anyway" in refused.output
    assert (tmp_path / "presenters" / "casey.toml").exists()

    forced = runner.invoke(app, ["presenter", "remove", "casey", "--force"], input="y\n")
    assert forced.exit_code == 0, forced.output
    assert not (tmp_path / "presenters" / "casey.toml").exists()


def test_presenter_remove_with_yes_skips_confirm(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EMCEE_ROOT", str(tmp_path))
    runner.invoke(app, ["presenter", "add", "casey", "--name", "Casey", "--sex", "male",
                        "--voice", "american-dj", "--character", "x"])
    result = runner.invoke(app, ["presenter", "remove", "casey", "--yes"])
    assert result.exit_code == 0, result.output
    assert not (tmp_path / "presenters" / "casey.toml").exists()
    assert "removed:" in result.output


def test_presenter_remove_unknown_id_errors(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EMCEE_ROOT", str(tmp_path))
    missing = runner.invoke(app, ["presenter", "remove", "ghost"])
    assert missing.exit_code == 1
    assert isinstance(missing.exception, PresenterError)


# --- _assignments_using_presenter (the real function, unmocked) --------


def test_assignments_using_presenter_profile_only_match():
    config = EmceeConfig(assign=AssignConfig(
        default=None,
        profiles={"prime-dead": Assignment(presenter="waldo")}))
    assert _assignments_using_presenter(config, "waldo") == ["prime-dead"]


def test_assignments_using_presenter_default_only_match():
    config = EmceeConfig(assign=AssignConfig(default="waldo", profiles={}))
    assert _assignments_using_presenter(config, "waldo") == ["[assign] default"]


def test_assignments_using_presenter_both_profile_and_default():
    config = EmceeConfig(assign=AssignConfig(
        default="waldo",
        profiles={"prime-dead": Assignment(presenter="waldo")}))
    assert _assignments_using_presenter(config, "waldo") == ["prime-dead", "[assign] default"]


def test_assignments_using_presenter_no_match_returns_empty():
    config = EmceeConfig(assign=AssignConfig(
        default="casey",
        profiles={"prime-dead": Assignment(presenter="casey")}))
    assert _assignments_using_presenter(config, "waldo") == []


def test_presenter_remove_refused_end_to_end_against_real_config_on_disk(tmp_path: Path, monkeypatch):
    # No monkeypatching of _assignments_using_presenter here: a real
    # config.toml on disk drives the refusal end to end.
    monkeypatch.setenv("EMCEE_ROOT", str(tmp_path))
    runner.invoke(app, ["presenter", "add", "waldo", "--name", "Waldo", "--sex", "male",
                        "--voice", "american-dj", "--character", "x"])
    (tmp_path / "config.toml").write_text(
        '[assign]\ndefault = "waldo"\n\n'
        '[assign.profiles.prime-dead]\npresenter = "waldo"\n'
    )

    refused = runner.invoke(app, ["presenter", "remove", "waldo"], input="y\n")
    assert refused.exit_code == 1
    assert "presenter waldo is used by: prime-dead, [assign] default — --force to remove anyway" in refused.output
    assert (tmp_path / "presenters" / "waldo.toml").exists()

    forced = runner.invoke(app, ["presenter", "remove", "waldo", "--force"], input="y\n")
    assert forced.exit_code == 0, forced.output
    assert not (tmp_path / "presenters" / "waldo.toml").exists()
