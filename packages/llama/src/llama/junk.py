import re
from collections import Counter
from collections.abc import Sequence
from statistics import median

from llama.util import length_seconds

# Delivery formats, in preference order. archive.org tags lossless files
# either "Flac" or "24bit Flac"; matching only the first made every 24-bit
# item look like it had no lossless copy at all, so audio_format="flac"
# yielded zero kept files and the recording became unselectable.
FORMAT_BY_AUDIO = {"mp3": ("VBR MP3",), "flac": ("Flac", "24bit Flac")}

# Lossless formats worth READING titles from. Deliberately broader than the
# delivery formats: title recovery reads metadata strings and never downloads
# these files, so Shorten is safe here - and deliberately absent above, since
# adding it would change what llama ships.
#
# Shorten is LOAD-BEARING, do not drop it. It looks inert in the tests because
# the gd73_metadata.json fixture's .shn entries all have length=None and are
# filtered as junk - that property is the FIXTURE's, not production's.
# Measured against the 2,095 cached archive.org items in
# /Users/shawn/projects/llama-setlist-analysis/iacache/, using llama's real
# filter_files:
#
#   items with Shorten files                : 209
#   ...where ALL Shorten files lack length  :   0
#   ...where filter_files keeps some        : 209
#   items whose ONLY lossless is Shorten    : 209
#
# i.e. Shorten is the sole lossless title source for ~10% of the sample.
# Standing caveat: that cache is a random.shuffle(seed=7) decade-stratified
# sample of archive.org ITEMS (built by build_corpus.py, which does not run
# select_recording or any scoring), so this is a rate over cached items, not
# over shows llama would actually select. The conclusion still holds either
# way - Shorten is the only lossless source for a substantial minority of
# items, so it stays in LOSSLESS_TITLE_FORMATS.
LOSSLESS_TITLE_FORMATS = ("Flac", "24bit Flac", "Shorten")

# The duration arm of junk filtering. It exists to drop tuning, crowd noise and
# stray clips, NOT to have an opinion about how long a song is - but an absolute
# 90s floor has exactly that opinion, and on short-song bands it is wrong by
# construction. Measured 2026-08-05 over minutemen1983-03-09: 38 audio files
# matching a 38-song description one-for-one, 27 of them under 90s, so llama
# kept 11 tracks, aligned them at coverage 1.00 and shipped a 29%-complete show
# with NO review flag. The tape was whole; the filter made it partial. Across
# the 71 lookahead flip rows, 47 had >=1 sub-90s file and 21 had >=20% of files
# under it; Minutemen + Mike Watt alone were 15 of 71.
#
# So the floor is taken RELATIVE to the tape's own median track length: a tape
# of one-minute songs gets a one-minute-scale floor, a tape of five-minute songs
# gets a five-minute-scale one. Swept over 2,030 cached items (both corpora),
# counting only files this arm UNIQUELY removes, classified by their embedded
# tag titles via `structure.is_filler`:
#
#   rule                       filler dropped   song-like dropped
#   absolute 90s (old)              1061              890
#   < 10% of median                  206               77
#   < 25% of median                  987              415
#   < 30% of median                 1194              579
#
# 0.25 keeps 93% of the old rule's junk-catching while more than halving the
# real songs it destroyed - and the song-like column is itself contaminated
# (`tunig`, `Take A Step Back`, `Drums`, `Jam #2` all sit in it), so the true
# song loss is lower still. Retuning this pair invalidates that measurement.
SHORT_FRACTION_OF_MEDIAN = 0.25
# Below this many usable durations a median is not worth trusting, so the old
# absolute floor stands. A two-file tape must not get to infer its own floor.
MIN_MEDIAN_SAMPLE = 5
MIN_PLAUSIBLE_SEC = 90.0

_LEADING_INT = re.compile(r"\s*(\d+)")


def _stem(name: str) -> str:
    """Filename up to the first digit — the item's naming-convention signature."""
    for i, ch in enumerate(name):
        if ch.isdigit():
            return name[:i]
    return name


def _track_number(f: dict, orig_tracks: dict[str, object]) -> int | None:
    """Leading integer of the file's track tag ("5", "05", "5/16"). A
    derivative takes its original's tag - derivative entries often lack it."""
    raw = f.get("track") if f.get("source") == "original" else orig_tracks.get(f.get("original"))
    m = _LEADING_INT.match(str(raw)) if raw is not None else None
    return int(m.group(1)) if m else None


def _keep_and_exclude(
    files: list[dict], audio: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Junk-filter ONE format's audio entries: provenance, dominant filename
    convention, plausible duration. Split out of filter_files so it can run
    once per candidate format."""
    original_names = {f["name"] for f in files if f.get("source") == "original"}
    stems = Counter(_stem(f["name"]) for f in audio)
    dominant = stems.most_common(1)[0][0] if stems else ""

    # TWO PASSES, and the order is load-bearing. The duration floor is derived
    # from the median of files that pass every OTHER arm, so junk cannot move
    # the threshold that decides what junk is: an item padded with twenty 20s
    # spam clips would otherwise drag the median down and license itself.
    non_duration: list[list[str]] = []
    for f in audio:
        reasons: list[str] = []
        if f.get("source") == "derivative":
            if f.get("original") not in original_names:
                reasons.append("derivative of unknown original")
        elif f.get("source") != "original":
            reasons.append("unknown provenance")
        if _stem(f["name"]) != dominant:
            reasons.append("filename convention mismatch")
        non_duration.append(reasons)

    clean_secs = [
        secs
        for f, other in zip(audio, non_duration)
        if not other and (secs := length_seconds(f.get("length"))) is not None
    ]
    floor = (
        SHORT_FRACTION_OF_MEDIAN * median(clean_secs)
        if len(clean_secs) >= MIN_MEDIAN_SAMPLE
        else MIN_PLAUSIBLE_SEC
    )

    kept: list[dict] = []
    excluded: list[dict] = []
    for f, other in zip(audio, non_duration):
        reasons = list(other)
        secs = length_seconds(f.get("length"))
        if secs is None:
            reasons.append("missing duration")
        elif secs < floor:
            reasons.append("implausibly short")
        if reasons:
            excluded.append({"filename": f["name"], "reasons": reasons})
        else:
            kept.append(f)
    kept.sort(key=lambda f: f["name"])
    return kept, excluded


def filter_files(
    files: list[dict], want_format: str | Sequence[str] = "VBR MP3"
) -> tuple[list[dict], list[dict], dict]:
    """Returns (kept, excluded, ordering) with kept in canonical play order.

    `want_format` may be one format or an ordered preference list. A list is
    tried in order and the first one whose KEPT set is non-empty wins - never a
    union, because an item carrying both Flac and 24bit Flac would otherwise
    keep every track twice.

    Preference is decided AFTER junk filtering, not on the raw format-matched
    list: on gd1985-07-01.144157.nak304.guy.pailes.miller.clugston.flac2496
    every `Flac` entry is junk while 15 clean tracks sit under `24bit Flac`, so
    choosing before filtering showed a flac-configured user no lossless at all.

    When NO format yields a non-empty kept set, the first format that had any
    audio entries at all is returned - today's behaviour for a genuinely
    unusable item, and `excluded` still explains why it was rejected.

    `excluded` covers only the WINNING format - a losing format's rejects are
    never merged in, so a short `excluded` list does not mean every other
    format's files were clean too."""
    wanted = (want_format,) if isinstance(want_format, str) else tuple(want_format)
    fallback: tuple[str, list[dict], list[dict]] | None = None
    chosen: tuple[str, list[dict], list[dict]] | None = None
    for fmt in wanted:
        audio = [f for f in files if f.get("format") == fmt]
        if not audio:
            continue
        fmt_kept, fmt_excluded = _keep_and_exclude(files, audio)
        if fallback is None:
            fallback = (fmt, fmt_kept, fmt_excluded)
        if fmt_kept:
            chosen = (fmt, fmt_kept, fmt_excluded)
            break
    matched, kept, excluded = chosen or fallback or ("", [], [])

    orig_tracks = {f["name"]: f.get("track") for f in files if f.get("source") == "original"}
    nums = [_track_number(f, orig_tracks) for f in kept]
    ordering = {"order_source": "filename", "reordered": False, "format": matched}
    # Track-tag order only when complete and unique: per-disc numbering
    # restarts at 1, which makes duplicates ambiguous.
    if kept and all(n is not None for n in nums) and len(set(nums)) == len(nums):
        by_track = [f for _, f in sorted(zip(nums, kept), key=lambda p: p[0])]
        ordering = {"order_source": "track-tags", "reordered": by_track != kept,
                    "format": matched}
        kept = by_track
    return kept, excluded, ordering
