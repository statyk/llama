"""A DJ clip's own length from its first MPEG audio frame header.

Unchunked, unbedded clips ship the TTS provider's MP3 as is, so the bitrate
cannot be assumed. For constant-bitrate Layer III the length is the audio
bytes over the bitrate; this is an estimate (VBR files, a Xing frame and
trailing tags are not corrected for) used only to steer show choice.
"""

from pathlib import Path

SCAN_BYTES = 64 * 1024

_BITRATES_V1 = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320)
_BITRATES_V2 = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160)
_RATES = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}


def _frame_bitrate(head: bytes) -> int | None:
    """Bits per second of a valid MPEG-1/2/2.5 Layer III header, else None."""
    if len(head) < 4 or head[0] != 0xFF or head[1] & 0xE0 != 0xE0:
        return None
    version = (head[1] >> 3) & 3          # 3 = MPEG-1, 2 = MPEG-2, 0 = MPEG-2.5, 1 reserved
    layer = (head[1] >> 1) & 3            # 1 = Layer III
    bitrate_idx = head[2] >> 4
    rate_idx = (head[2] >> 2) & 3
    if version == 1 or layer != 1 or bitrate_idx in (0, 15) or rate_idx == 3:
        return None
    table = _BITRATES_V1 if version == 3 else _BITRATES_V2
    return table[bitrate_idx] * 1000


def mp3_seconds(path: Path, size: int | None = None) -> float | None:
    """Seconds of audio, or None when no valid frame header is in the first 64 KiB."""
    path = Path(path)
    with open(path, "rb") as fh:
        buf = fh.read(SCAN_BYTES)
        total = size
        if total is None:
            total = path.stat().st_size
    start = 0
    if buf[:3] == b"ID3" and len(buf) >= 10:
        syncsafe = ((buf[6] & 0x7F) << 21) | ((buf[7] & 0x7F) << 14) | ((buf[8] & 0x7F) << 7) | (buf[9] & 0x7F)
        start = 10 + syncsafe + (10 if buf[5] & 0x10 else 0)     # footer flag
    i = start
    while True:
        i = buf.find(b"\xff", i)
        if i < 0:
            return None
        bitrate = _frame_bitrate(buf[i:i + 4])
        if bitrate is not None:
            return max(total - i, 0) * 8 / bitrate
        i += 1
