import hashlib

import numpy as np

from emcee.tts import room_tone
from emcee.tts.room_tone import fill_room_tone

RATE = 24000


def _floor(rng, n):
    f = np.round(rng.normal(0, 32768 * 10 ** (-60 / 20), n)).astype(np.int16)
    f[f == 0] = 1
    return f


def _speech(rng, n):
    t = np.arange(n) / RATE
    s = 32768 * 10 ** (-20 / 20) * np.sin(2 * np.pi * 220 * t) * 1.4
    return np.round(s).astype(np.int16) + _floor(rng, n)


def _clip(gap_s=0.3, seconds=4.0, seed=0):
    """Speech bursts and floor-only pauses, one exact-zero gap. Returns (x, gap_start, gap_end)."""
    rng = np.random.default_rng(seed)
    parts, gap = [], None
    pos, k = 0, 0
    while pos < seconds * RATE:
        b = _speech(rng, int(0.5 * RATE))
        parts.append(b)
        pos += len(b)
        if k == 2:
            gap = (pos, pos + int(gap_s * RATE))
            parts.append(np.zeros(gap[1] - gap[0], dtype=np.int16))
            pos = gap[1]
        else:
            p = _floor(rng, int(0.15 * RATE))
            parts.append(p)
            pos += len(p)
        k += 1
    return np.concatenate(parts), gap[0], gap[1]


def _longest_zero_run(x):
    best = cur = 0
    for v in x:
        cur = cur + 1 if v == 0 else 0
        best = max(best, cur)
    return best


def _rms(x):
    return float(np.sqrt((x.astype(np.float64) ** 2).mean()))


def _fill(x, seed="text", channels=1):
    return np.frombuffer(
        fill_room_tone(x.astype("<i2").tobytes(), RATE, channels, seed_text=seed), "<i2")


def test_fill_replaces_zero_runs_and_keeps_length():
    x, _, _ = _clip()
    out = _fill(x)
    assert len(out) == len(x)
    assert _longest_zero_run(out) < round(0.02 * RATE)


def test_fill_is_deterministic_and_seeded_by_text():
    x, _, _ = _clip()
    a, b, c = _fill(x, "one"), _fill(x, "one"), _fill(x, "two")
    assert a.tobytes() == b.tobytes()
    assert a.tobytes() != c.tobytes()


def test_seed_is_the_sha256_of_the_text(monkeypatch):
    seen = []
    real = np.random.default_rng

    def spy(seed=None):
        seen.append(seed)
        return real(seed)

    x, _, _ = _clip()
    monkeypatch.setattr(room_tone.np.random, "default_rng", spy)
    _fill(x, "some text")
    assert seen == [int.from_bytes(hashlib.sha256(b"some text").digest()[:8], "big")]


def test_fill_level_comes_from_the_quietest_frames():
    x, s, e = _clip()
    out = _fill(x)
    gap_rms = _rms(out[s + 200:e - 200])
    floor_rms = 32768 * 10 ** (-60 / 20)
    speech_rms = _rms(x[:int(0.5 * RATE)])
    assert abs(20 * np.log10(gap_rms / floor_rms)) < 6
    assert 20 * np.log10(speech_rms / gap_rms) >= 30


def test_fill_overlaps_neighbouring_audio_by_the_crossfade():
    x, s, e = _clip()
    out = _fill(x)
    xf = round(0.005 * RATE)
    assert not np.array_equal(out[s - xf:s], x[s - xf:s])
    assert np.array_equal(out[:s - xf], x[:s - xf])


def test_pool_excludes_frames_with_a_1ms_zero_run():
    rng = np.random.default_rng(3)
    n = 480

    def frame(level, zeros=(), width=3):
        f = np.round(rng.normal(0, level, n)).astype(np.int16)
        f[f == 0] = 1
        for z in zeros:
            f[z:z + width] = 0
        return f

    crossings = [50, 200, 350]
    quiet_holey = [frame(5, [50], width=30) for _ in range(30)]
    louder = [frame(20, []) for _ in range(30)]
    x = np.concatenate(quiet_holey + louder + [np.zeros(4800, dtype=np.int16)])
    x = np.concatenate([x, frame(20, [])])
    out = _fill(x)
    gap = out[-4800 - n:-n]
    assert _longest_zero_run(gap[200:-200]) < 24
    assert 15 < _rms(gap[200:-200]) < 25  # drawn from the louder, hole-free frames
    # Control: 3-sample crossing zeros do not exclude a frame.
    y = np.concatenate([frame(5, crossings) for _ in range(30)]
                       + [frame(20, []) for _ in range(30)]
                       + [np.zeros(4800, dtype=np.int16), frame(20, [])])
    g = _fill(y)[-4800 - n:-n]
    assert _rms(g[200:-200]) < 8


def test_edge_runs_fade_from_and_to_zero():
    rng = np.random.default_rng(1)
    z = int(0.2 * RATE)
    dither = np.array([2, -2] * 5, dtype=np.int16)
    x = np.concatenate([dither, np.zeros(z, np.int16)]
                       + [_speech(rng, int(0.5 * RATE)), _floor(rng, int(0.15 * RATE))] * 3
                       + [np.zeros(z, np.int16)])
    out = _fill(x)
    assert len(out) == len(x)
    assert abs(int(out[0])) <= 3 and abs(int(out[-1])) <= 3
    assert np.abs(out[0:60]).mean() < np.abs(out[60:120]).mean()
    assert np.abs(out[-60:]).mean() < np.abs(out[-120:-60]).mean()
    assert _longest_zero_run(out) < round(0.02 * RATE)


def test_noop_without_live_frames():
    pcm = np.zeros(RATE, dtype="<i2").tobytes()
    assert fill_room_tone(pcm, RATE, 1, seed_text="t") == pcm


def test_noop_when_pool_empty():
    rng = np.random.default_rng(2)
    n = 480
    frames = []
    for _ in range(20):
        f = _speech(rng, n)
        f[100:140] = 0
        frames.append(f)
    x = np.concatenate(frames + [np.zeros(4800, np.int16)])
    pcm = x.astype("<i2").tobytes()
    assert fill_room_tone(pcm, RATE, 1, seed_text="t") == pcm


def test_noop_without_qualifying_run():
    rng = np.random.default_rng(4)
    gap = np.zeros(int(0.01 * RATE), np.int16)
    x = np.concatenate([_speech(rng, 4800), gap, _speech(rng, 4800), gap, _floor(rng, 4800)])
    pcm = x.astype("<i2").tobytes()
    assert fill_room_tone(pcm, RATE, 1, seed_text="t") == pcm


def test_skips_non_mono():
    x, _, _ = _clip()
    pcm = x.astype("<i2").tobytes()
    assert fill_room_tone(pcm, RATE, 2, seed_text="t") == pcm


def test_odd_length_pcm():
    rng = np.random.default_rng(5)
    edge = int(0.1 * RATE)
    mid = 24001 - 2 * edge
    body = np.concatenate([_speech(rng, 12000), _floor(rng, mid - 12000)])
    x = np.concatenate([np.zeros(edge, np.int16), body, np.zeros(edge, np.int16)])
    assert len(x) == 24001
    out = _fill(x)
    assert len(out) == 24001
    assert abs(int(out[0])) <= 3 and abs(int(out[-1])) <= 3
