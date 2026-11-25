import pytest

from transmitter import alerts
from transmitter.announce_config import DEFAULT_ID_TEXT, AnnounceSettings, Gaps, load_settings
from transmitter.workspace import Workspace


@pytest.fixture
def calls(monkeypatch):
    got = []
    monkeypatch.setattr(alerts, "alert", lambda code, message: got.append((code, message)))
    return got


def _ws(tmp_path, text=None, raw=None):
    ws = Workspace(tmp_path)
    if text is not None:
        ws.announce_path.write_text(text)
    if raw is not None:
        ws.announce_path.write_bytes(raw)
    return ws


def test_announce_path(tmp_path):
    assert Workspace(tmp_path).announce_path == tmp_path / "announce.toml"


def test_missing_file_is_off_and_silent(tmp_path, calls):
    r = load_settings(_ws(tmp_path), alert=True)
    assert r.source == "missing" and r.problem is None
    assert r.settings == AnnounceSettings() and r.settings.enabled is False
    assert r.settings.id_text == DEFAULT_ID_TEXT
    assert calls == []


def test_valid_file_loads(tmp_path, calls):
    bed = tmp_path / "bed.wav"
    ws = _ws(tmp_path, f'enabled = true\nbed = "{bed}"\nbed_under_db = 18\n[gaps]\nafter_id = 0.6\n')
    r = load_settings(ws, alert=True)
    assert r.source == "file" and r.problem is None
    assert r.settings.enabled is True and r.settings.bed == bed
    assert r.settings.bed_under_db == 18
    assert r.settings.gaps == Gaps(after_id=0.6)
    assert r.settings.gaps.bed_tail == 1.0
    assert calls == []


@pytest.mark.parametrize("text,raw,needle", [
    ("enabld = true\n", None, "enabld"),
    ("enabled = [\n", None, "TOML"),
    ('enabled = true\nbed = "rel/bed.wav"\n', None, "bed"),
    (None, b"id_text = '\xff\xfe'\n", "UTF-8"),
    ('id_text = "a\\nb"\n', None, "id_text"),
    ('id_text = ""\n', None, "id_text"),
    ("[gaps]\nafter_id = 9\n", None, "after_id"),
    ("bed_under_db = nan\n", None, "bed_under_db"),
])
def test_invalid_file_is_off_with_one_alert(tmp_path, calls, text, raw, needle):
    r = load_settings(_ws(tmp_path, text=text, raw=raw), alert=True)
    assert r.source == "invalid"
    assert r.settings == AnnounceSettings() and r.settings.enabled is False
    assert needle in r.problem
    assert len(calls) == 1 and calls[0][0] == "announce-config"
    assert needle in calls[0][1]


def test_enabled_without_bed_is_invalid(tmp_path, calls):
    r = load_settings(_ws(tmp_path, "enabled = true\n"), alert=True)
    assert r.source == "invalid" and "bed" in r.problem
    assert r.settings.enabled is False
    assert [c for c, _ in calls] == ["announce-config"]
    calls.clear()
    r = load_settings(_ws(tmp_path, "enabled = false\n"), alert=True)
    assert r.source == "file" and r.settings.bed is None and calls == []


def test_alert_false_never_alerts(tmp_path, calls):
    r = load_settings(_ws(tmp_path, "bogus = 1\n"), alert=False)
    assert r.source == "invalid" and r.problem
    assert calls == []


def test_unreadable_file_never_raises(tmp_path, calls):
    (tmp_path / "announce.toml").mkdir()
    r = load_settings(Workspace(tmp_path), alert=True)
    assert r.source == "invalid" and r.settings.enabled is False
    assert len(calls) == 1


def test_new_codes_are_ungated_events():
    for c in ("announce-assembly", "announce-pieces", "announce-promise", "announce-config"):
        assert c not in alerts.GATED_CODES and c not in alerts.LEVEL_CODES


def test_deeply_nested_toml_never_raises(tmp_path, calls):
    r = load_settings(_ws(tmp_path, "a = " + "[" * 5000 + "]" * 5000), alert=True)
    assert r.source == "invalid" and r.problem
    assert r.settings == AnnounceSettings()
    assert [c for c, _ in calls] == ["announce-config"]
