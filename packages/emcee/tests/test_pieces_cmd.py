"""`emcee pieces`: voices transmitter's announcement pieces with strict verification.

Everything is offline: fake speech and STT behind the module seams
`pieces._speech` / `pieces._stt`, a tmp_path share, a tmp_path EMCEE_ROOT."""
import fcntl
import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

from emcee import pieces
from emcee.cli import app
from emcee.piece_audio import pcm_to_wav
from emcee.tts.provider import SpeechBlocked, SpeechDefect, SpeechError

runner = CliRunner()
RATE = 24000


def pid(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def good_wav() -> bytes:
    """Quiet lead-in, then a tone, then a quiet tail (passes the onset check)."""
    t = np.arange(int(RATE * 0.6)) / RATE
    tone = (6000 * np.sin(2 * np.pi * 220 * t)).astype("<i2")
    lead = (np.random.default_rng(1).normal(0, 5, int(RATE * 0.2))).astype("<i2")
    tail = np.zeros(int(RATE * 0.2), dtype="<i2")
    return pcm_to_wav(np.concatenate([lead, tone, tail]).tobytes(), RATE)


def clipped_wav() -> bytes:
    t = np.arange(int(RATE * 0.6)) / RATE
    return pcm_to_wav((6000 * np.sin(2 * np.pi * 220 * t)).astype("<i2").tobytes(), RATE)


def silent_wav() -> bytes:
    return pcm_to_wav(bytes(2 * RATE // 2), RATE)


class FakeSpeech:
    def __init__(self, takes=None):
        self.takes = list(takes or [])
        self.sent: list[str] = []
        self.preflights = 0
        self.inner = self

    def preflight(self):
        self.preflights += 1

    def synthesize(self, text, fmt="mp3"):
        assert fmt == "wav"
        self.sent.append(text)
        if self.takes:
            item = self.takes.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        return good_wav()


class FakeStt:
    def __init__(self, transcripts=None, echo=False):
        self.transcripts = list(transcripts or [])
        self.echo = echo
        self.calls = 0

    def transcribe(self, wav):
        self.calls += 1
        return self.transcripts.pop(0) if self.transcripts else "x"


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text(
        '[tts]\nbackend = "fake"\nvoice = "v"\n\n[tts.mlx_audio]\nstt_model = "whisper"\n')
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    folder = tmp_path / "pieces"
    folder.mkdir()
    return type("Env", (), {"home": home, "folder": folder, "tmp": tmp_path})()


def seam(monkeypatch, speech, stt):
    monkeypatch.setattr(pieces, "_speech", lambda config, presenter_id: speech)
    monkeypatch.setattr(pieces, "_stt", lambda config: stt)


def put(folder: Path, text: str) -> str:
    i = pid(text)
    (folder / f"piece-{i}.txt").write_text(text)
    return i


def run(env, *extra):
    return runner.invoke(app, ["pieces", str(env.folder), "--presenter", "roy", *extra])


def boom(*a, **k):
    raise AssertionError("must not be called")


def test_nothing_pending_exits_before_touching_any_server(env, monkeypatch):
    monkeypatch.setattr(pieces, "_speech", boom)
    monkeypatch.setattr(pieces, "_stt", boom)
    r = run(env)
    assert r.exit_code == 0, r.output


def test_voices_a_pending_piece_to_an_mp3(env, monkeypatch):
    i = put(env.folder, "with Cracker.")
    speech, stt = FakeSpeech(), FakeStt(["With Cracker."])
    seam(monkeypatch, speech, stt)
    r = run(env)
    assert r.exit_code == 0, r.output
    mp3 = env.folder / f"piece-{i}.mp3"
    assert mp3.stat().st_size > 0
    assert f"voiced {i}: with Cracker." in r.output
    assert "voiced 1, re-takes 0, failed 0, left 0" in r.output
    assert speech.preflights == 1
    assert [p.name for p in env.folder.iterdir() if p.name.startswith(".")] == []


def test_retakes_on_mismatch_then_succeeds(env, monkeypatch):
    i = put(env.folder, "with Cracker.")
    seam(monkeypatch, FakeSpeech(), FakeStt(["With Crack.", "With Cracker."]))
    r = run(env)
    assert r.exit_code == 0, r.output
    assert f"re-take {i} (" in r.output
    assert "voiced 1, re-takes 1, failed 0, left 0" in r.output
    assert (env.folder / f"piece-{i}.mp3").exists()


def test_failed_after_the_cap_writes_a_failed_sidecar(env, monkeypatch):
    i = put(env.folder, "with Cracker.")
    seam(monkeypatch, FakeSpeech(), FakeStt(["With Crack."] * 4))
    r = run(env)
    assert r.exit_code == 0, r.output
    assert not (env.folder / f"piece-{i}.mp3").exists()
    data = json.loads((env.folder / f"piece-{i}.failed").read_text())
    assert set(data) == {"attempts", "last_reason", "last_transcript", "at"}
    assert data["attempts"] == 4
    assert data["last_transcript"] == "With Crack."
    assert data["at"].endswith("Z") or "+00:00" in data["at"]
    assert f"failed {i} after 4 takes:" in r.output
    assert "voiced 0, re-takes 3, failed 1, left 0" in r.output
    assert [p.name for p in env.folder.iterdir() if p.name.startswith(".")] == []


def test_onset_and_guard_failures_are_failed_takes(env, monkeypatch):
    i = put(env.folder, "with Cracker.")
    defect = SpeechDefect("mlx_audio", text="x", reason="runaway")
    speech = FakeSpeech([defect, clipped_wav(), silent_wav()])
    stt = FakeStt(["With Cracker."])
    seam(monkeypatch, speech, stt)
    r = run(env)
    assert r.exit_code == 0, r.output
    assert (env.folder / f"piece-{i}.mp3").exists()
    assert "voiced 1, re-takes 3, failed 0, left 0" in r.output
    assert stt.calls == 1  # only the good take reached the STT


def test_all_unusable_takes_fail_with_no_transcript(env, monkeypatch):
    i = put(env.folder, "with Cracker.")
    seam(monkeypatch, FakeSpeech([silent_wav()] * 4), FakeStt())
    r = run(env)
    assert r.exit_code == 0, r.output
    data = json.loads((env.folder / f"piece-{i}.failed").read_text())
    assert data["last_transcript"] is None


def test_server_error_aborts_without_a_sidecar(env, monkeypatch):
    i = put(env.folder, "with Cracker.")
    seam(monkeypatch, FakeSpeech([SpeechError("server down")]), FakeStt())
    r = run(env)
    assert r.exit_code == 1
    assert "error: server down" in r.output
    assert not (env.folder / f"piece-{i}.failed").exists()
    assert not (env.folder / f"piece-{i}.mp3").exists()


def test_expect_file_overrides_the_comparison(env, monkeypatch):
    i = put(env.folder, "with Cracker.")
    (env.folder / f"piece-{i}.expect").write_text("with Cracker")
    seam(monkeypatch, FakeSpeech(), FakeStt(["with cracker"]))
    r = run(env)
    assert r.exit_code == 0, r.output
    assert (env.folder / f"piece-{i}.mp3").exists()


def test_lexicon_respelling_is_sent_but_the_original_is_compared(env, monkeypatch):
    (env.home / "pronunciations.csv").write_text("written,spoken,note\nCracker,Crack er,test\n")
    i = put(env.folder, "with Cracker.")
    speech = FakeSpeech()
    seam(monkeypatch, speech, FakeStt(["With Cracker."]))
    r = run(env)
    assert r.exit_code == 0, r.output
    assert "Crack er" in speech.sent[0]
    assert (env.folder / f"piece-{i}.mp3").exists()


def test_failed_and_voiced_pieces_are_not_pending(env):
    a = put(env.folder, "with A.")
    b = put(env.folder, "with B.")
    c = put(env.folder, "with C.")
    (env.folder / f"piece-{a}.mp3").write_bytes(b"x")
    (env.folder / f"piece-{b}.failed").write_text("{}")
    assert [p.id for p in pieces.pending(env.folder)] == [c]


def test_pending_ignores_clutter(env):
    good = put(env.folder, "with D.")
    (env.folder / "notes.txt").write_text("hi")
    (env.folder / "piece-XYZ.txt").write_text("x")
    (env.folder / f"piece-{'A' * 12}.txt").write_text("x")  # uppercase hex
    (env.folder / ".piece-aaaaaaaaaaaa.txt.t.tmp").write_text("x")
    (env.folder / f".piece-{good}.txt").write_text("x")
    (env.folder / "sub").mkdir()
    (env.folder / f"piece-{'b' * 12}.txt").mkdir()  # a directory with a txt name
    (env.folder / f"piece-{'c' * 12}.mp3").write_bytes(b"x")  # mp3 alone
    assert [p.id for p in pieces.pending(env.folder)] == [good]


def test_pending_is_sorted_by_id(env):
    ids = sorted(put(env.folder, f"with {n}.") for n in "ABCDE")
    assert [p.id for p in pieces.pending(env.folder)] == ids


def test_mp3_is_written_through_a_dot_temp(env, monkeypatch):
    i = put(env.folder, "with Cracker.")
    seam(monkeypatch, FakeSpeech(), FakeStt(["With Cracker."]))
    seen = []
    real = os.replace

    def spy(src, dst, *a, **k):
        seen.append((Path(src), Path(dst)))
        return real(src, dst, *a, **k)

    monkeypatch.setattr(pieces.os, "replace", spy)
    r = run(env)
    assert r.exit_code == 0, r.output
    assert len(seen) == 1
    src, dst = seen[0]
    assert src.name.startswith(f".piece-{i}.mp3.") and src.name.endswith(".tmp")
    assert dst.name == f"piece-{i}.mp3"


def test_second_run_exits_on_the_lock(env, monkeypatch):
    put(env.folder, "with Cracker.")
    monkeypatch.setattr(pieces, "_speech", boom)
    monkeypatch.setattr(pieces, "_stt", boom)
    fd = os.open(env.home / "pieces.lock", os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        r = run(env)
    finally:
        os.close(fd)
    assert r.exit_code == 0, r.output
    assert "another emcee pieces is running" in r.output


def test_lock_is_released_after_a_run(env, monkeypatch):
    seam(monkeypatch, FakeSpeech(), FakeStt())
    assert run(env).exit_code == 0
    fd = os.open(env.home / "pieces.lock", os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        os.close(fd)


def test_dry_run_lists_and_writes_nothing(env, monkeypatch):
    a = put(env.folder, "with Cracker.")
    monkeypatch.setattr(pieces, "_speech", boom)
    monkeypatch.setattr(pieces, "_stt", boom)
    before = sorted(p.name for p in env.folder.iterdir())
    r = run(env, "--dry-run")
    assert r.exit_code == 0, r.output
    assert f"{a}: with Cracker." in r.output
    assert sorted(p.name for p in env.folder.iterdir()) == before


def test_dry_run_prints_text_as_read_even_if_torn(env, monkeypatch):
    (env.folder / "piece-aaaaaaaaaaaa.txt").write_text("torn tex")
    r = run(env, "--dry-run")
    assert "aaaaaaaaaaaa: torn tex" in r.output


def test_refuses_without_stt_model(env, monkeypatch):
    (env.home / "config.toml").write_text('[tts]\nbackend = "fake"\nvoice = "v"\n')
    put(env.folder, "with Cracker.")
    monkeypatch.setattr(pieces, "_speech", boom)
    r = run(env)
    assert r.exit_code == 1
    assert ("error: emcee pieces needs [tts.mlx_audio] stt_model for strict verification"
            in r.output)


def test_limit_stops_after_n_pieces(env, monkeypatch):
    for n in "ABC":
        put(env.folder, f"with {n}.")
    seam(monkeypatch, FakeSpeech(), FakeStt(["With A.", "With B.", "With C."]))
    ids = [p.id for p in pieces.pending(env.folder)]
    texts = {pid(f"with {n}."): f"With {n}." for n in "ABC"}
    seam(monkeypatch, FakeSpeech(), FakeStt([texts[i] for i in ids]))
    r = run(env, "--limit", "2")
    assert r.exit_code == 0, r.output
    assert "voiced 2, re-takes 0, failed 0, left 1" in r.output
    assert len(list(env.folder.glob("piece-*.mp3"))) == 2


def test_text_not_matching_its_id_is_skipped(env, monkeypatch):
    good = put(env.folder, "with Cracker.")
    bad_id = "0" * 12
    (env.folder / f"piece-{bad_id}.txt").write_text("some other text")
    speech = FakeSpeech()
    seam(monkeypatch, speech, FakeStt(["With Cracker."]))
    r = run(env)
    assert r.exit_code == 0, r.output
    assert r.output.count(f"skip {bad_id}: text does not match its id") == 1
    assert not (env.folder / f"piece-{bad_id}.mp3").exists()
    assert not (env.folder / f"piece-{bad_id}.failed").exists()
    assert speech.sent == ["with Cracker."] or len(speech.sent) == 1
    assert (env.folder / f"piece-{good}.mp3").exists()


def test_text_vanished_after_listing_is_skipped(env, monkeypatch):
    gone = put(env.folder, "with Gone.")
    kept = put(env.folder, "with Kept.")
    real = pieces.pending
    calls = []

    def listing(folder):
        out = real(folder)
        calls.append(1)
        if len(calls) == 2:  # the voicing loop's listing; the first is the command's
            (folder / f"piece-{gone}.txt").unlink()
        return out

    monkeypatch.setattr(pieces, "pending", listing)
    speech = FakeSpeech()
    seam(monkeypatch, speech, FakeStt(["With Kept."]))
    r = run(env)
    assert r.exit_code == 0, r.output
    assert not (env.folder / f"piece-{gone}.failed").exists()
    assert not (env.folder / f"piece-{gone}.mp3").exists()
    assert (env.folder / f"piece-{kept}.mp3").exists()


def test_missing_folder_is_an_error(env, monkeypatch):
    monkeypatch.setattr(pieces, "_speech", boom)
    r = runner.invoke(app, ["pieces", str(env.tmp / "nope"), "--presenter", "roy"])
    assert r.exit_code == 1
    assert f"error: {env.tmp / 'nope'} does not exist (share not mounted?)" in r.output
    assert not (env.home / "pieces.lock").exists()


def test_cleans_only_its_own_old_dot_temps(env, monkeypatch):
    put(env.folder, "with Cracker.")
    old = time.time() - 2 * 3600
    mine = [env.folder / ".piece-x.mp3.t.tmp", env.folder / ".piece-x.failed.t.tmp"]
    theirs = env.folder / ".piece-x.txt.t.tmp"
    young = env.folder / ".piece-y.mp3.t.tmp"
    for p in (*mine, theirs, young):
        p.write_bytes(b"x")
    for p in (*mine, theirs):
        os.utime(p, (old, old))
    seam(monkeypatch, FakeSpeech(), FakeStt(["With Cracker."]))
    r = run(env)
    assert r.exit_code == 0, r.output
    assert not any(p.exists() for p in mine)
    assert theirs.exists() and young.exists()


def test_content_block_is_a_failed_take_and_the_run_goes_on(env, monkeypatch):
    ids = sorted(put(env.folder, f"with {n}.") for n in "AB")
    first = next(i for i in ids if pid("with A.") == i or pid("with B.") == i)
    texts = {pid("with A."): "with A.", pid("with B."): "with B."}
    blocked_text = texts[ids[0]]

    class Blocking(FakeSpeech):
        def synthesize(self, text, fmt="mp3"):
            if text == blocked_text:
                raise SpeechBlocked("mlx", text=text, categories=["x"])
            return super().synthesize(text, fmt)

    seam(monkeypatch, Blocking(), FakeStt([texts[ids[1]].capitalize()]))
    r = run(env)
    assert r.exit_code == 0, r.output
    assert f"re-take {ids[0]} (" in r.output
    assert (env.folder / f"piece-{ids[0]}.failed").exists()
    assert not (env.folder / f"piece-{ids[0]}.mp3").exists()
    assert json.loads((env.folder / f"piece-{ids[0]}.failed").read_text())["attempts"] == 4
    assert (env.folder / f"piece-{ids[1]}.mp3").exists()
    assert "voiced 1, re-takes 3, failed 1, left 0" in r.output


def test_write_error_stops_cleanly_leaving_no_temp(env, monkeypatch):
    i = put(env.folder, "with Cracker.")
    seam(monkeypatch, FakeSpeech(), FakeStt(["With Cracker."]))

    def broken(*a, **k):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(pieces.os, "replace", broken)
    r = run(env)
    assert r.exit_code == 1
    assert "error: [Errno 28] No space left on device" in r.output
    assert not (env.folder / f"piece-{i}.mp3").exists()
    assert not (env.folder / f"piece-{i}.failed").exists()
    assert [p.name for p in env.folder.iterdir() if p.name.startswith(".")] == []
    fd = os.open(env.home / "pieces.lock", os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # released
    finally:
        os.close(fd)
