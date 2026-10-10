import pytest

from tests_transmitter.helpers import FakeBucket, make_publisher, requires_ffmpeg, stereo_sine, write_mp3
from transmitter import aacenc, adts, fallback, grid, id3, segment
from transmitter.errors import PublishError
from transmitter.state import PublishState, load_fallback_version, load_publish_state, save_publish_state
from transmitter.workspace import Workspace


def _build(tmp_path, notice=True):
    write_mp3(tmp_path / "loop.mp3", stereo_sine(25.0, 330.0, 0.2))
    notice_path = None
    if notice:
        write_mp3(tmp_path / "notice.mp3", stereo_sine(14.0, 500.0, 0.1))   # longer than d: truncated
        notice_path = tmp_path / "notice.mp3"
    return fallback.build_fallback(tmp_path / "loop.mp3", notice_path, ffmpeg="ffmpeg",
                                   music_target_lufs=-16.0, speech_target_lufs=-16.0,
                                   extra=aacenc.extra_frames())


@requires_ffmpeg
def test_loop_segments_are_whole_and_timestamped_k_d(tmp_path):
    b = _build(tmp_path)
    assert len(b.segments) == 3                       # ceil((1077 + extra) / 441)
    for k, data in enumerate(b.segments):
        ts, frames = segment.parse(data)
        assert ts == grid.segment_timestamp(k) and len(frames) == grid.SEGMENT_FRAMES
    ts, frames = segment.parse(b.notice)
    assert ts == 0 and len(frames) == grid.SEGMENT_FRAMES
    assert b.index() == {"len": 3, "notice": f"fallback/{b.version}/notice.aac", "d": 10.24}


@requires_ffmpeg
@pytest.mark.parametrize("notice", [True, False])
def test_every_fallback_frame_is_a_whole_station_format_adts_frame(tmp_path, notice):
    b = _build(tmp_path, notice=notice)
    for data in (*b.segments, b.notice):
        _, tag_len = id3.parse_timestamp_tag(data)
        body = data[tag_len:]
        offsets = adts.frame_offsets(body)            # raises on any truncated / unsynced frame
        assert offsets[-1] == len(body)               # frames tile the body exactly
        frames = adts.split_frames(body)
        assert len(frames) == grid.SEGMENT_FRAMES
        for f in frames:
            h = adts.parse_header(f)
            assert h.frame_length == len(f)
            adts.require_station_format(h)


@requires_ffmpeg
def test_version_is_content_addressed(tmp_path):
    assert _build(tmp_path).version == _build(tmp_path).version
    assert _build(tmp_path, notice=False).version != _build(tmp_path).version


@requires_ffmpeg
def test_write_local(tmp_path):
    b = _build(tmp_path)
    d = fallback.write_local(Workspace(tmp_path / "ws"), b)
    assert d == tmp_path / "ws" / "render" / "fallback" / b.version
    assert sorted(p.name for p in d.iterdir()) == ["0.aac", "1.aac", "2.aac", "index.json", "notice.aac"]


def _fake_build():
    seg = segment.assemble(0, [adts.build_frame(b"x")] * 441)
    return fallback.FallbackBuild("abc123def456", (seg, seg), seg)


def test_upload_order_and_horizon_refresh(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    save_publish_state(p.ws, PublishState(epoch_id="etest", first=100, last=200, runs=[[100, 200]]))
    fallback.upload_fallback(p, _fake_build(), p.epoch.start_us(150))
    assert bucket.puts() == ["fallback/abc123def456/0.aac", "fallback/abc123def456/1.aac",
                             "fallback/abc123def456/notice.aac", "fallback/abc123def456/index.json",
                             "state/horizon.json"]
    assert bucket.objects["fallback/abc123def456/index.json"]["CacheControl"] == "public, max-age=31536000, immutable"
    assert bucket.json("state/horizon.json")["fallback_version"] == "abc123def456"
    assert (bucket.json("state/horizon.json")["first"], bucket.json("state/horizon.json")["last"]) == (100, 200)
    assert load_fallback_version(p.ws) == "abc123def456"


def test_upload_does_not_rewrite_horizon_below_high_water(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    save_publish_state(p.ws, PublishState(epoch_id="etest", first=100, last=200, runs=[[100, 260]],
                                          high_water=260))
    fallback.upload_fallback(p, _fake_build(), p.epoch.start_us(150))
    assert "state/horizon.json" not in bucket.objects
    assert bucket.puts()[-1] == "fallback/abc123def456/index.json"
    assert load_fallback_version(p.ws) == "abc123def456"       # the next publish batch carries it
    assert load_publish_state(p.ws).high_water == 260           # untouched


def test_upload_rewrites_horizon_when_high_water_is_not_above_last(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    save_publish_state(p.ws, PublishState(epoch_id="etest", first=100, last=200, runs=[[100, 200]],
                                          high_water=200))
    fallback.upload_fallback(p, _fake_build(), p.epoch.start_us(150))
    assert bucket.puts()[-1] == "state/horizon.json"
    assert bucket.json("state/horizon.json")["last"] == 200
    assert load_publish_state(p.ws).high_water == 200


def test_upload_without_a_horizon_only_records_the_version(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    fallback.upload_fallback(p, _fake_build(), p.epoch.start_us(150))
    assert "state/horizon.json" not in bucket.objects
    assert load_fallback_version(p.ws) == "abc123def456"


def test_upload_refuses_while_the_guard_is_tripped(tmp_path):
    bucket = FakeBucket()
    bucket.objects["state/guard.json"] = {"Body": b'{"tripped": true}', "ContentType": "", "CacheControl": ""}
    p = make_publisher(tmp_path, bucket)
    with pytest.raises(PublishError, match="guard"):
        fallback.upload_fallback(p, _fake_build(), p.epoch.start_us(150))
    assert bucket.puts() == []
