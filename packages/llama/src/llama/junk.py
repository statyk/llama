import re
from collections import Counter
from collections.abc import Sequence
from statistics import median

from llama.titles import clean_tag_title
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


# --- Piece 4: keep short files that belong to the show -----------------------
# Spec docs/superpowers/specs/2026-10-23-junk-short-keep-design.md, 1 and 2.1-2.5.
# A file whose ONLY drop reason is the short arm ("implausibly short") is KEPT,
# unless it trips the spam-shape tripwire or its tag is wholly junk; an untagged
# one is kept only when interior in play order and its filename stem is not
# wholly junk. The floor above is untouched: the rule only re-decides files the
# short arm already dropped, after the floor is computed.
#
# The regexes and the three functions below are NORMATIVE (spec 2.3): ported
# character for character from what was measured over the library's 3,547
# short-only drops (0 music among the junk, 0 tripwire hits; pinned by
# test_short_keep_rule.py::test_deny_vocabulary_corpus). Do not edit them
# without re-measuring; that test is the gate.

SPAM_REASON = "spam-shaped name or tag"

LEAD = re.compile(r"^(?:\(?\d{1,2}:\d{2}(?::\d{2})?(?:[.:]\d+)?\)?\s*[-:)]?\s*|\d{1,3}\s*[.):_-]?\s+|d\d{1,2}t\d{1,3}\s*|\d{3,4}(?=[a-z]))+", re.I)
TIME_PAREN = re.compile(r"\s*[\(\[]\s*\d{1,2}:\d{2}[^)\]]*[\)\]]")
SPLIT = re.compile(r"\s*(?:/|,|&|\+|;|\band\b|\s-\s|-{2,}|-?>|~|\||\(|\)|\[|\])\s*", re.I)
EDGE = re.compile(r"^[\s\[\(<~*#.\-_'\":]+|[\s\]\)>~*#.\-_'\":]+$")
JUNK_PART = re.compile(
    r"^(?:"
    r"(?:set\s*(?:\d|i+|one|two|three)\s*)?(?:re-?)?tun(?:e|i|ni|in)?(?:ing|ning|eing|ig|in'?|e[\s-]*ups?|ups?)?(?:\s*up)?(?:\s+break)?"
    r"|instrument\s+change|warm[\s-]*up|(?:crowd|tuning)\s+(?:crowd|tuning)"
    r"|dead\s*air|silence|silent|blank"
    r"|(?:tape|side|disc|disk|reel)\s*(?:flip|change|cut|end|gap|break)|gap|cut[\s-]*in"
    r"|fade[\s-]*(?:in|out)"
    r"|(?:tape\s+|crowd\s+)?noise|hiss|static|test\s*tones?"
    r"|sound\s*check"
    r"|(?:opening\s+|encore\s+)?(?:crowd|audience)(?:\s+(?:noise|cheering|chanting|applause|yelling|encore\s+call))?"
    r"|(?:opening\s+|encore\s+)?applause|cheering|clapping"
    r"|(?:encore|set)\s*(?:break|call)(?:\s+i+)?|waiting(?:\s+for\s+(?:the\s+)?encore)?"
    r")$", re.I)
NONPERF = re.compile(
    r"\bcommercials?\b|\bpromos?\b|\badvert\w*|\bstation\s+(?:id|plug|identification)\b|\bnews\s+broadcast\b"
    r"|\b(?:house|p\.?\s?a\.?|intro|walk[\s-]*(?:on|in|out|off)|recorded|pre-?show|closing|exit|outro)\s+music\b"
    r"|\binterview\w*"
    r"|(?=.*\b(?:dj'?s?|radio)\b)(?=.*\b(?:talk\w*|intro\w*|outro\w*|banter|announc\w*|moderator\w*|host\w*|id|spots?)\b)"
    r"|\b(?:over|on)\s+(?:the\s+)?p\.?a\.?(?=\W|$)"
    r"|(?=.*\b(?-i:[KW][A-Z]{2,3})(?:-?FM)?\b)(?=.*\b(?:talk\w*|intro\w*|outro\w*|banter|announc\w*|moderator\w*|host\w*|id|spots?|wrap\w*)\b)"
    r"|\bhost\s*#\s*\d",
    re.I)
SPAM = re.compile(r"https?://|\bwww\.|\b[a-z0-9-]+\.(?:com|net|org|info|biz)\b|@\w{3,}", re.I)
SPAM_STEM = re.compile(r"\bfollow\b|\bdownload\b|\bsubscribe\b", re.I)
SPAM_TAG = re.compile(r"\bfollow\s+(?:me|us)\b", re.I)


def basename_without_extension(name: str) -> str:
    """The filename stem the tripwire and the filename-junk test read: the
    last path component, extension removed (as measured, `rprime2.stem`)."""
    return re.sub(r"\.[A-Za-z0-9]+$", "", name.rsplit("/", 1)[-1])


def parts(t: str) -> list[str]:    # t = clean_tag_title(tag)
    t = TIME_PAREN.sub("", LEAD.sub("", t))
    return [p for p in (EDGE.sub("", x) for x in SPLIT.split(t)) if p]


def short_tag_is_junk(tag: str | None) -> bool:
    t = clean_tag_title(tag)
    if not t:
        return False
    if NONPERF.search(t):
        return True
    ps = parts(t)
    return bool(ps) and all(JUNK_PART.match(p) for p in ps)


def short_is_spam(filename: str, own_title: str | None, original_title: str | None) -> bool:
    stem = basename_without_extension(filename)
    tags = (own_title or "", original_title or "")
    return (bool(SPAM.search(stem) or SPAM_STEM.search(stem))
            or any(SPAM.search(t) or SPAM_TAG.search(t) for t in tags))


def short_filename_is_junk(filename: str) -> bool:
    """Spec 2.4 'Filename junk': an untagged file's stem, leading digits and
    separators removed, is wholly junk under the tag test. Only ever drops."""
    return short_tag_is_junk(re.sub(r"^[\d\s._-]+", "", basename_without_extension(filename)))


def short_verdict(filename: str, own_title: str | None, original_title: str | None,
                  *, interior: bool) -> str:
    """The rule for ONE short-only drop, decided in this order:
    "spam" (the tripwire, tagged or not), then tagged ("junk" or "keep"), then
    untagged ("filename" junk, else "keep" when interior, else "edge").

    The tag is the file's own `title`, else its original's (spec 2.2); it is
    tagged when that cleans to non-empty, placeholders such as `tmp` included."""
    if short_is_spam(filename, own_title, original_title):
        return "spam"
    tag = own_title or original_title
    if clean_tag_title(tag):
        return "junk" if short_tag_is_junk(tag) else "keep"
    if short_filename_is_junk(filename):
        return "filename"
    return "keep" if interior else "edge"


def _title_str(raw: object) -> str | None:
    return None if raw is None else str(raw)


def _listing_key(f: dict) -> tuple[str, int]:
    """`_dedupe_duplicate_listings`' key, (basename, rounded duration), computed
    the same way it computes it inline; that function is left unchanged."""
    return (f["name"].rsplit("/", 1)[-1], round(length_seconds(f.get("length")) or 0))


def _apply_short_rule(
    files: list[dict], kept: list[dict], excluded: list[dict],
    excluded_files: list[dict], orig_tracks: dict[str, object],
) -> tuple[list[dict], list[dict], set[str]]:
    """Re-decide every entry whose reasons are exactly ["implausibly short"]
    (spec 2.1: a file failing another arm too is untouched). A tripwire hit's
    reasons become [SPAM_REASON]; a junk, filename-junk or edge file keeps
    "implausibly short"; a kept file rejoins `kept`. Returns the new kept and
    excluded lists and the names the rule kept."""
    by_name = {f["name"]: f for f in files}
    tagged_keep: list[dict] = []
    untagged: list[tuple[dict, str | None, str | None]] = []
    spam: set[int] = set()
    for i, (e, f) in enumerate(zip(excluded, excluded_files)):
        # Checkpoint A ruling 1 (2026-10-24): a zero-duration file is an
        # audio-less stub; it never enters the short rule and stays dropped.
        if e["reasons"] != ["implausibly short"] or not e["duration_sec"]:
            continue
        own = _title_str(f.get("title"))
        orig = by_name.get(f.get("original")) if f.get("source") == "derivative" else None
        original = _title_str(orig.get("title")) if orig else None
        # interior=False here: an untagged non-junk file reads "edge", which
        # separates it from a tagged keep; its interior test needs the play
        # order, which needs the tagged keeps first.
        verdict = short_verdict(f["name"], own, original, interior=False)
        if verdict == "spam":
            spam.add(i)
        elif verdict == "keep":
            tagged_keep.append(f)
        elif verdict == "edge":
            untagged.append((f, own, original))

    # Play order for the interior test, over kept + tagged keeps + untagged
    # candidates (spam and filename junk are not in it), derived the way
    # filter_files derives it: over ONE copy per listing (after
    # duplicate-listing dedupe), in track-tag order when every surviving file
    # has a unique track number, else in the deduped filename order. Only kept
    # and tagged-kept files count as neighbours: two untagged files at an edge
    # do not license each other.
    #
    # The dedupe is load-bearing: on an item listed twice (top level and under
    # an <identifier>/ prefix) the duplicate track numbers force filename
    # order and the two blocks sort apart, so an edge file's top-level copy
    # would have the whole prefixed block after it and read as interior.
    # `_dedupe_duplicate_listings` is called as is (unchanged) over the
    # name-sorted pool, which is what filter_files hands it; every pool file
    # then takes the position of its listing, keyed by `_listing_key` (the
    # same key the dedupe computes inline).
    #
    # Both copies of a doubled derivative (X.mp3 / X_vbr.mp3) stay in this pool:
    # filter_files decides its final order as if a copy `_dedupe_derivatives`
    # drops were still there (fix wave I-2), so this order and that one agree.
    base = kept + tagged_keep
    pool = sorted(base + [f for f, _, _ in untagged], key=lambda f: f["name"])
    listings, _ = _dedupe_duplicate_listings(pool)
    nums = [_track_number(f, orig_tracks) for f in listings]
    if listings and all(n is not None for n in nums) and len(set(nums)) == len(nums):
        order = [f for _, f in sorted(zip(nums, listings), key=lambda p: p[0])]
    else:
        order = listings
    pos = {_listing_key(f): i for i, f in enumerate(order)}
    base_pos = [pos[_listing_key(f)] for f in base]
    lo, hi = (min(base_pos), max(base_pos)) if base_pos else (None, None)
    untagged_keep = [
        f for f, own, original in untagged
        if short_verdict(f["name"], own, original,
                         interior=lo is not None and lo < pos[_listing_key(f)] < hi) == "keep"
    ]

    # Both derivatives of one original may come back here; filter_files keeps one
    # (`_dedupe_derivatives`, fix wave I-2), so this rule itself never chooses a copy.
    back = tagged_keep + untagged_keep
    back_ids = {id(f) for f in back}
    new_excluded: list[dict] = []
    for i, (e, f) in enumerate(zip(excluded, excluded_files)):
        if id(f) in back_ids:
            continue
        new_excluded.append({**e, "reasons": [SPAM_REASON]} if i in spam else e)
    return kept + back, new_excluded, {f["name"] for f in back}


def _keep_and_exclude(
    files: list[dict], audio: list[dict], *, short_keep: bool,
    orig_tracks: dict[str, object],
) -> tuple[list[dict], list[dict], set[str]]:
    """Junk-filter ONE format's audio entries: provenance, dominant filename
    convention, plausible duration. Split out of filter_files so it can run
    once per candidate format.

    With `short_keep`, a short-only drop is then re-decided by the piece-4 rule
    (`_apply_short_rule`). Returns (kept, excluded, names the rule kept); the
    third item is empty with `short_keep=False`, which reproduces the filter as
    it was before the rule. `orig_tracks` is filter_files' {original name:
    track tag} map, for the rule's play order."""
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
    excluded_files: list[dict] = []
    for f, other in zip(audio, non_duration):
        reasons = list(other)
        secs = length_seconds(f.get("length"))
        if secs is None:
            reasons.append("missing duration")
        elif secs < floor:
            reasons.append("implausibly short")
        if reasons:
            excluded.append({"filename": f["name"], "reasons": reasons,
                             "duration_sec": secs})
            excluded_files.append(f)
        else:
            kept.append(f)
    short_kept: set[str] = set()
    if short_keep:
        # After the floor, never before it: the rule re-decides files the
        # short arm already dropped and cannot move the threshold.
        kept, excluded, short_kept = _apply_short_rule(
            files, kept, excluded, excluded_files, orig_tracks)
    kept.sort(key=lambda f: f["name"])
    return kept, excluded, short_kept


def _dedupe_duplicate_listings(kept: list[dict]) -> tuple[list[dict], list[dict]]:
    """Some archive.org items list every track twice - once at top level,
    once under an <identifier>/ directory prefix - with identical durations
    and a title on only one copy (ymsb2005's donor: 56 files for 28 tracks,
    halving its apparent tag fraction). Collapse onto (basename, rounded
    duration): keep the first copy encountered unless a later duplicate
    carries a title the kept one lacks, in which case it swaps in. Runs
    AFTER _keep_and_exclude for the winning format, so play-order derivation
    sees only the deduped list.

    Measured 2026-09-02 with scripts/dedupe_sweep.py over 968 cached items
    (1936 item/format pairs): exactly one item changes -
    ymsb2005-12-31.flac16, 56 -> 28 kept files in both mp3 and flac."""
    winners: dict[tuple[str, int], dict] = {}
    order: list[tuple[str, int]] = []
    excluded: list[dict] = []
    for f in kept:
        base = f["name"].rsplit("/", 1)[-1]
        key = (base, round(length_seconds(f.get("length")) or 0))
        if key not in winners:
            winners[key] = f
            order.append(key)
            continue
        incumbent = winners[key]
        incumbent_title = str(incumbent.get("title") or "").strip()
        candidate_title = str(f.get("title") or "").strip()
        if not incumbent_title and candidate_title:
            excluded.append({"filename": incumbent["name"], "reasons": ["duplicate-listing"],
                             "duration_sec": length_seconds(incumbent.get("length"))})
            winners[key] = f
        else:
            excluded.append({"filename": f["name"], "reasons": ["duplicate-listing"],
                             "duration_sec": length_seconds(f.get("length"))})
    return [winners[k] for k in order], excluded


# --- Fix wave I-2: at most one derivative per original -----------------------
# Some items carry two VBR MP3 derivatives of every original, `X.mp3` and
# `X_vbr.mp3` (the plain one is the newer derivation; see below). They have
# different basenames, so `_dedupe_duplicate_listings` keeps both, and the
# show plays every song twice. Before piece 4 the short arm at least dropped both
# copies of a short piece, so a hand repair (`fix --exclude` of every long
# `_vbr`) left a correct show; the short-keep rule re-admitted both copies of
# every short piece. Operator ruling (2026-10-25): within the winning format,
# keep at most one derivative per `original`, long and short. Applies only with
# `short_keep=True` (orchestrator ruling: the legacy filter stays v2.17.0's).
DUPLICATE_DERIVATIVE_REASON = "duplicate derivative"

# WHICH copy is kept: the plain `X.mp3` over `X_vbr.mp3` (operator ruling
# 2026-10-25). Measured over 104 cached items / 2,017 pairs: the plain X.mp3 is
# the newer file (the re-derivation) in 2017 of 2017 pairs, and `_vbr`'s bitrate
# is a median 2.6% higher; of the 48 cached pairs whose durations differ by more
# than 2 s, the plain copy is never the shorter (FW1 review). Set True to keep the
# `_vbr` copy instead. The operator's own choices outrank it, which is what keeps a
# flip to this one line: a copy the operator has excluded (`_dedupe_derivatives`'
# `avoid`) is never the kept copy, and a copy the operator has included (`prefer`,
# FW2 addition B) is, so `fix --exclude` of either copy keeps the other, and an
# `include` naming one copy ships that copy alone, at either value. (Before B a flip
# shipped stringcheeseincident-1999-12-31's five included short plain copies twice:
# the flip dropped them as duplicates and `include` re-admitted them beside their
# `_vbr` copies.)
PREFER_VBR_DERIVATIVE = False


def _derivative_preference(f: dict, prefer: frozenset[str] = frozenset()
                           ) -> tuple[bool, bool, bool, str]:
    """Sort key among derivatives of one original: lowest is kept.

    0. A copy in `prefer` (the operator's `overrides.include`, FW2 addition B) sorts
       first: the operator chose it.
    1. Then a copy whose stem ends `_vbr` sorts after a plain one (before it with
       `PREFER_VBR_DERIVATIVE`).
    2. Then a copy whose stem is NOT its original's stem sorts last (fix round 1,
       C-1). A group with no `_vbr` copy is a stale derivative left by a renamed
       or re-split original, and it sits at the wrong place in filename order:
       on gd1984-04-13.132772.Sennheiser-holbrook.flac24 name order kept
       `gd1984-04-13(24Bit48khz)d2t01.mp3` (Scarlet > Fire) as track 1, before
       set 1. Measured over the 23 such cached groups: exactly one copy carries
       its original's stem in every one; name order picked it in 12 only.
       Inert for a plain/_vbr pair, which step 1 already decides.
    3. Then name order."""
    stem = basename_without_extension(f["name"])
    vbr = stem.endswith("_vbr")
    stale = stem != basename_without_extension(str(f.get("original") or ""))
    return (f["name"] not in prefer, vbr != PREFER_VBR_DERIVATIVE, stale, f["name"])


def _dedupe_derivatives(
    kept: list[dict], avoid: frozenset[str] = frozenset(),
    prefer: frozenset[str] = frozenset(),
) -> tuple[list[dict], list[dict], list[dict]]:
    """Keep at most one derivative per `original` (I-2). A file that is not a
    derivative, or has no `original`, is never a duplicate. Neither is a file in
    `avoid` (the operator's `overrides.exclude`, fix round 1 I-1): it passes
    through untouched for the caller's exclusion to drop as `operator-excluded`,
    and the kept copy is chosen among the others, so excluding the preferred
    copy keeps the other one instead of silently losing the song. A file in
    `prefer` (the operator's `overrides.include`, FW2 addition B) wins its group, so
    the other copy drops and the song ships once; when both copies are included, one
    still drops, and `include` re-admits it. Returns (kept in
    input order, an `excluded` entry per dropped copy with reason
    DUPLICATE_DERIVATIVE_REASON, the dropped files themselves). Runs after
    `_dedupe_duplicate_listings`, which is unchanged.

    The step only DROPS: filter_files decides play order as if the dropped
    copies were still there. A dropped copy shares its kept copy's original and
    so its track tag, which makes the tags non-unique and the order filename
    order, as before the step. Measured (FW1 M2): letting the dedupe unmask the
    tags reorders exactly one library show, wrongly - jrad2023-05-12, whose
    renamed originals carry stale tags (`16.5 Morning Dew` tagged 18, after the
    encore `17 Casey Jones`) and whose stale `14 The Other One.mp3` derivative
    was the duplicate that kept it in its (correct) filename order."""
    groups: dict[str, list[dict]] = {}
    for f in kept:
        if f.get("source") == "derivative" and f.get("original") and f["name"] not in avoid:
            groups.setdefault(f["original"], []).append(f)
    winner = {orig: min(copies, key=lambda f: _derivative_preference(f, prefer))
              for orig, copies in groups.items() if len(copies) > 1}
    out: list[dict] = []
    excluded: list[dict] = []
    dropped: list[dict] = []
    for f in kept:
        grouped = f.get("source") == "derivative" and f["name"] not in avoid
        w = winner.get(f.get("original")) if grouped else None
        if w is None or w is f:
            out.append(f)
            continue
        excluded.append({"filename": f["name"], "reasons": [DUPLICATE_DERIVATIVE_REASON],
                         "duration_sec": length_seconds(f.get("length"))})
        dropped.append(f)
    return out, excluded, dropped


def _kept_running_time(kept: list[dict], avoid: frozenset[str] = frozenset()) -> float:
    """Total length of `kept`, leaving out an `avoid`ed (operator-excluded) derivative
    whose original another, non-avoided kept derivative also carries (FW2 addition A,
    FW1 re-review N-1): `_dedupe_derivatives` never drops an avoided copy, so without
    this a doubled song the operator repaired by excluding one copy would count twice.
    Every other excluded file still counts, so an exclude never moves the format away
    from the one the filename-keyed overrides were written against."""
    held = {f.get("original") for f in kept
            if f.get("source") == "derivative" and f.get("original") and f["name"] not in avoid}
    return sum(length_seconds(f.get("length")) or 0.0 for f in kept
               if not (f["name"] in avoid and f.get("source") == "derivative"
                       and f.get("original") in held))


def _choose_format(
    files: list[dict], wanted: tuple[str, ...], orig_tracks: dict[str, object],
    avoid: frozenset[str] = frozenset(), prefer: frozenset[str] = frozenset(),
) -> tuple[str, list[dict], list[dict], set[str], list[dict]]:
    """Fix wave I-1 (operator ruling 2026-10-25), the `short_keep=True` path:
    among `wanted`, the format whose KEPT files have the greatest total running
    time wins; `wanted`'s order breaks ties only. "Kept" is after the junk arms,
    the short-keep rule and both dedupes (a format listed twice must not win on
    its doubled time; nor one doubled by an operator-excluded copy,
    `_kept_running_time`). `avoid` and `prefer` are the operator's exclude and
    include, for `_dedupe_derivatives`. When no format keeps anything, the first format with any
    audio is returned, so `excluded` explains (unchanged). Returns (format,
    kept, excluded incl. both dedupes' drops, names the rule kept, the files
    the derivative dedupe dropped)."""
    fallback: tuple[str, list[dict], list[dict], set[str], list[dict]] | None = None
    best: tuple[float, tuple[str, list[dict], list[dict], set[str], list[dict]]] | None = None
    for fmt in wanted:
        audio = [f for f in files if f.get("format") == fmt]
        if not audio:
            continue
        fmt_kept, fmt_excluded, fmt_short = _keep_and_exclude(
            files, audio, short_keep=True, orig_tracks=orig_tracks)
        fmt_kept, dup_excluded = _dedupe_duplicate_listings(fmt_kept)
        fmt_kept, deriv_excluded, deriv_dropped = _dedupe_derivatives(fmt_kept, avoid, prefer)
        entry = (fmt, fmt_kept, fmt_excluded + dup_excluded + deriv_excluded, fmt_short,
                 deriv_dropped)
        if fallback is None:
            fallback = entry
        if fmt_kept:
            # The rule (I-1): the greatest kept running time wins; never "first non-empty".
            secs = _kept_running_time(fmt_kept, avoid)
            if best is None or secs > best[0]:   # strict: earlier format wins a tie
                best = (secs, entry)
    if best is not None:
        return best[1]
    return fallback or ("", [], [], set(), [])


def filter_files(
    files: list[dict], want_format: str | Sequence[str] = "VBR MP3",
    *, readmit: frozenset[str] = frozenset(), short_keep: bool = True,
    exclude: frozenset[str] = frozenset(),
) -> tuple[list[dict], list[dict], dict]:
    """Returns (kept, excluded, ordering) with kept in canonical play order.

    `want_format` may be one format or an ordered preference list. ONE format
    wins - never a union, because an item carrying both Flac and 24bit Flac
    would otherwise keep every track twice. With `short_keep` (the default) the
    winner is the format whose KEPT files have the greatest total running time,
    the list's order breaking ties only (fix wave I-1, operator ruling
    2026-10-25: "why would we pick a format with 1 file for a concert
    containing many songs?" - tsp2007-07-28.csb.flac24's lone 61 s `Flac`
    "Outro", kept by the short rule, beat the whole show in `24bit Flac`; see
    `_choose_format`). With `short_keep=False` the first format whose kept set
    is non-empty wins, as in v2.17.0.

    Preference is decided AFTER junk filtering, not on the raw format-matched
    list: on gd1985-07-01.144157.nak304.guy.pailes.miller.clugston.flac2496
    every `Flac` entry is junk while 15 clean tracks sit under `24bit Flac`, so
    choosing before filtering showed a flac-configured user no lossless at all.

    When NO format yields a non-empty kept set, the first format that had any
    audio entries at all is returned - today's behaviour for a genuinely
    unusable item, and `excluded` still explains why it was rejected.

    `excluded` covers only the WINNING format - a losing format's rejects are
    never merged in, so a short `excluded` list does not mean every other
    format's files were clean too.

    After the winning format's junk filtering, duplicate listings (an item
    that lists the same track twice - once at top level, once under an
    <identifier>/ prefix, both surviving the junk arms) are collapsed to one
    copy each; the dropped copy is appended to `excluded` with reason
    "duplicate-listing" - not a junk verdict about its content, just a
    second listing of a track already kept. See
    `_dedupe_duplicate_listings`. With `short_keep`, at most one derivative per
    `original` is then kept (`_dedupe_derivatives`: the doubled X.mp3 /
    X_vbr.mp3 class, the copy chosen by `PREFER_VBR_DERIVATIVE`); a dropped copy
    is appended to `excluded` with reason DUPLICATE_DERIVATIVE_REASON.

    `exclude` is `overrides.exclude`, read by that dedupe only: an excluded copy
    is never grouped (never chosen, never dropped as a duplicate) and stays in
    `kept` for the caller to drop (`gather.final_kept`). This filter excludes
    nothing itself. Ignored with `short_keep=False`. The dedupe also reads
    `readmit`: an included copy wins its group (FW2 addition B).

    `readmit` is `overrides.include`: source filenames the operator has ruled
    back in. They are returned to `kept` and removed from `excluded` after the
    junk arms and after both dedupes, and before play order is derived. No
    exclusion reason is refused (a dropped duplicate derivative can be
    re-admitted).

    `short_keep` (default True) applies piece 4's rule: a file whose only
    drop reason is the short arm is kept unless it is spam-shaped or its tag
    is wholly junk, and an untagged one only when interior (see
    `_apply_short_rule`). `False` reproduces the filter as it was before the
    rule exactly (and so neither the running-time format choice nor the
    derivative dedupe applies); only the overrides migration's consistency
    check passes it.
    `ordering["short_kept"]` names the files the rule kept that are in the
    returned `kept` (after dedupe and readmit), sorted; always present, `[]`
    with `short_keep=False`."""
    wanted = (want_format,) if isinstance(want_format, str) else tuple(want_format)
    orig_tracks = {f["name"]: f.get("track") for f in files if f.get("source") == "original"}
    if short_keep:
        # Fix wave I-1 and I-2: format by kept running time, then at most one
        # derivative per original (both inside `_choose_format`).
        matched, kept, excluded, short_kept, deriv_dropped = _choose_format(
            files, wanted, orig_tracks, exclude, readmit)
    else:
        # The legacy filter, v2.17.0's exactly (orchestrator ruling): the first
        # format with a non-empty kept set wins, and no derivative dedupe.
        fallback: tuple[str, list[dict], list[dict], set[str]] | None = None
        chosen: tuple[str, list[dict], list[dict], set[str]] | None = None
        for fmt in wanted:
            audio = [f for f in files if f.get("format") == fmt]
            if not audio:
                continue
            fmt_kept, fmt_excluded, fmt_short = _keep_and_exclude(
                files, audio, short_keep=short_keep, orig_tracks=orig_tracks)
            if fallback is None:
                fallback = (fmt, fmt_kept, fmt_excluded, fmt_short)
            if fmt_kept:
                chosen = (fmt, fmt_kept, fmt_excluded, fmt_short)
                break
        matched, kept, excluded, short_kept = chosen or fallback or ("", [], [], set())

        kept, dup_excluded = _dedupe_duplicate_listings(kept)
        excluded = excluded + dup_excluded
        deriv_dropped = []

    # Operator re-admission (overrides.include). All three positions are
    # load-bearing:
    #   AFTER _keep_and_exclude - the duration floor is the median of files
    #     passing every OTHER arm, so a re-admitted 37s track can never move
    #     the threshold that decides what junk is (see the two-pass note in
    #     _keep_and_exclude).
    #   AFTER _dedupe_duplicate_listings and _dedupe_derivatives - otherwise a
    #     re-admitted duplicate listing or duplicate derivative would be
    #     immediately re-dropped, and no reason is refused.
    #   BEFORE the ordering block below - play order is derived over the FINAL
    #     kept set rather than splicing a file into an order derived without
    #     it. Consequence: re-admitting a file with no track tag reverts the
    #     whole recording to filename order.
    # `readmit` names the WINNING format's files only; anything else matches
    # nothing here and is warned about by the caller.
    readmitted: set[str] = set()
    if readmit:
        # The format clause is BELT-AND-BRACES and provably inert: `back` only
        # ever looks up names taken from `excluded`, which holds the winning
        # format's files alone. Kept because it states the losing-format rule
        # at the point that would otherwise silently break it, not because it
        # does anything -- measured dead in the whole-branch review (M3).
        by_name = {f["name"]: f for f in files if f.get("format") == matched}
        back = [by_name[e["filename"]] for e in excluded
                if e["filename"] in readmit and e["filename"] in by_name]
        if back:
            readmitted = {f["name"] for f in back}
            kept = sorted(kept + back, key=lambda f: f["name"])
            excluded = [e for e in excluded if e["filename"] not in readmitted]

    nums = [_track_number(f, orig_tracks) for f in kept]
    # Fix wave I-2: the order is decided as if every derivative the dedupe
    # dropped (and readmit did not return) were still in `kept`, so the dedupe
    # never changes play order (see `_dedupe_derivatives`). Empty with
    # `short_keep=False`.
    order_nums = nums + [_track_number(f, orig_tracks) for f in deriv_dropped
                         if f["name"] not in readmitted]
    short_kept_names = sorted({f["name"] for f in kept} & short_kept)
    # `readmitted` is the set this call ACTUALLY returned to `kept`, which is
    # NOT the same as the caller's `readmit` request: a name that was never
    # excluded (already kept, wrong format, or simply absent) re-admits
    # nothing. Callers that give re-admitted files reduced standing must
    # filter on THIS, never on `overrides.include` -- filtering on the request
    # would strip an already-kept file of its vote in gather's recording-level
    # gates, which is the exact defect those gates exist to prevent.
    ordering = {"order_source": "filename", "reordered": False, "format": matched,
                "readmitted": sorted(readmitted), "short_kept": short_kept_names}
    # Track-tag order only when complete and unique: per-disc numbering
    # restarts at 1, which makes duplicates ambiguous.
    if kept and all(n is not None for n in order_nums) and len(set(order_nums)) == len(order_nums):
        by_track = [f for _, f in sorted(zip(nums, kept), key=lambda p: p[0])]
        ordering = {"order_source": "track-tags", "reordered": by_track != kept,
                    "format": matched, "readmitted": sorted(readmitted),
                    "short_kept": short_kept_names}
        kept = by_track
    return kept, excluded, ordering
