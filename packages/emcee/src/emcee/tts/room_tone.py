"""Room-tone fill for exact-silence runs in synthesized speech.

Some TTS output (Qwen especially) holds runs of exact digital zeros, at the joins
between chunks and inside chunks, that a listener hears as dead air or a dropout.
`fill_room_tone` covers each such run with the segment's own quietest live frames,
crossfaded together, so the pauses keep their length and gain a room. Pure numpy,
no I/O. See docs/superpowers/specs/2026-10-26-paragraph-chunking-design.md
(section 3, Room-tone fill).
"""
import hashlib

import numpy as np

FRAME_S = 0.02          # pool frame length, seconds
POOL_PERCENTILE = 8.0   # the pool is the quietest this percent of eligible frames, by RMS
CROSSFADE_S = 0.005     # crossfade between pool frames, and overlap onto neighbouring audio
MIN_RUN_S = 0.02        # only exact-zero runs at least this long are filled
POOL_ZERO_RUN_S = 0.001  # a frame holding an exact-zero run this long is left out of the pool
LIVE_RMS = 1.0          # frames at or below this RMS are digital silence, not tone
ROOM_TONE_VERSION = "v1"  # in the DJ-clip cache key; bump when any constant or the
                          # algorithm below changes the output


def _zero_runs(x: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    """Maximal runs [s, e) of exact zeros in `x` that are at least `min_len` long."""
    z = np.concatenate([[0], (x == 0).astype(np.int8), [0]])
    d = np.diff(z)
    return [(int(s), int(e)) for s, e in zip(np.where(d == 1)[0], np.where(d == -1)[0])
            if e - s >= min_len]


def fill_room_tone(pcm: bytes, framerate: int, channels: int, *, seed_text: str) -> bytes:
    """Fill exact-zero runs in int16 little-endian mono PCM with room tone.

    Returns PCM of the same length. Returns the input unchanged when it is not
    mono, when no frame is eligible for the pool, or when no run qualifies.
    """
    if channels != 1:
        return pcm
    whole = len(pcm) // 2 * 2
    x = np.frombuffer(pcm[:whole], dtype="<i2")
    n = round(FRAME_S * framerate)
    xf = round(CROSSFADE_S * framerate)
    min_run = round(MIN_RUN_S * framerate)
    pool_zero = max(1, round(POOL_ZERO_RUN_S * framerate))
    if n <= xf or xf < 1:
        return pcm
    runs = _zero_runs(x, min_run)
    if not runs:
        return pcm

    frames = x[: x.size // n * n].reshape(-1, n).astype(np.float32)
    if not len(frames):
        return pcm
    rms = np.sqrt((frames ** 2).mean(axis=1))
    eligible = rms > LIVE_RMS
    for i in np.flatnonzero(eligible):
        if _zero_runs(frames[i], pool_zero):
            eligible[i] = False
    if not eligible.any():
        return pcm
    pool = frames[eligible & (rms <= np.percentile(rms[eligible], POOL_PERCENTILE))]
    if not len(pool):
        return pcm

    rng = np.random.default_rng(
        int.from_bytes(hashlib.sha256(seed_text.encode()).digest()[:8], "big"))
    ramp = np.linspace(0, 1, xf, dtype=np.float32)
    out = x.astype(np.float32)
    for s, e in runs:
        start_edge = s < xf
        end_edge = e > x.size - xf
        lo = 0 if start_edge else s - xf
        hi = x.size if end_edge else e + xf
        need = hi - lo
        fill = pool[rng.integers(len(pool))].copy()
        while len(fill) < need:
            nxt = pool[rng.integers(len(pool))]
            fill = np.concatenate(
                [fill[:-xf], fill[-xf:] * ramp[::-1] + nxt[:xf] * ramp, nxt[xf:]])
        env = np.ones(need, dtype=np.float32)
        env[:xf] = ramp
        env[-xf:] = ramp[::-1]
        out[lo:hi] += fill[:need] * env
    return np.clip(np.rint(out), -32768, 32767).astype("<i2").tobytes() + pcm[whole:]
