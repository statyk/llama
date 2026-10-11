import json

import numpy as np

from tests_transmitter.helpers import requires_ffmpeg
from transmitter import grid, segment, spike


def test_wrap_n_is_the_first_wrapped_segment():
    assert grid.segment_timestamp(spike.WRAP_N) < grid.segment_timestamp(spike.WRAP_N - 1)


def test_show_a_segue_is_phase_continuous():
    pcm, info = spike.show_a(36.0)
    mono = pcm[:, 0].astype(np.float64)
    at = int(info["segue_at_s"] * grid.SAMPLE_RATE)
    window = mono[at - 2000:at + 2000]
    # a phase-continuous 0.25-amplitude sine below 600 Hz never moves more than
    # 2*pi*600/44100*0.25 = 0.0214 between samples; a click would.
    assert float(np.max(np.abs(np.diff(window)))) < 0.0214


def test_live_playlist_window_and_endlist():
    meta = {"n0": 100, "count": 10}
    e = 0
    at = lambda n: grid.segment_start_us(e, n) + 1   # noqa: E731
    assert spike.live_playlist(meta, e, at(99)) is None
    body = spike.live_playlist(meta, e, at(107))
    assert "#EXT-X-MEDIA-SEQUENCE:102\n" in body
    assert body.count("#EXTINF:10.240,") == 6
    assert "seg/107.aac" in body and "#EXT-X-ENDLIST" not in body
    done = spike.live_playlist(meta, e, at(115))
    assert done.rstrip().endswith("#EXT-X-ENDLIST") and "seg/109.aac" in done


@requires_ffmpeg
def test_build_produces_grid_segments_with_the_wrap_in_show_b(tmp_path):
    meta = spike.build(tmp_path, minutes=1.5)
    n0, count = meta["n0"], meta["count"]
    assert n0 < spike.WRAP_N <= n0 + count - 1
    assert meta["wrap_at_s"] > meta["show_b_at_s"]
    for n in range(n0, n0 + count):
        ts, frames = segment.parse((tmp_path / "seg" / f"{n}.aac").read_bytes())
        assert ts == grid.segment_timestamp(n)
        assert len(frames) == grid.SEGMENT_FRAMES
    vod = (tmp_path / "vod.m3u8").read_text()
    assert vod.count("#EXTINF:10.240,") == count
    assert vod.rstrip().endswith("#EXT-X-ENDLIST")
    assert json.loads((tmp_path / "meta.json").read_text()) == meta
    assert "hls.js" in (tmp_path / "index.html").read_text()
