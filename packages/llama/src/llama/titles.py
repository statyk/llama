import re

from llama.models import ParsedSetlist, Track
from llama.util import length_seconds

# Identifier prefix embedded in tag titles ("gd73-06-10d1t04 Here Comes
# Sunshine"): 2-5 letters, 2- or 4-digit year, -/. separated date, then
# optional disc/track tokens. Adapted from deadstream, extended to 4-digit
# years.
_ID_PREFIX = re.compile(r"^[a-zA-Z]{2,5}_*\d{2}(?:\d{2})?[-.]\d{2}[-.]\d{2}\s*(?:[td]\d+)*")
_AUDIO_EXT = re.compile(r"\.(?:mp3|flac|ogg|shn)\s*$", re.I)
_EDGE_JUNK = " \t-–—_.|"


def clean_tag_title(raw: str | None) -> str:
    """Strip identifier prefix / audio extension from an embedded tag title.
    "unknown" is never a real title and maps to ""."""
    s = _ID_PREFIX.sub("", str(raw or "").strip())
    s = _AUDIO_EXT.sub("", s)
    s = s.strip(_EDGE_JUNK)
    return "" if s.lower() == "unknown" else s


_YEAR_LIKE_NUMERIC = re.compile(r"\d{4}")

# Widened from letters-only after scripts/numeric_title_census.py
# (2026-09-02, corrected 2026-09-02 fix round 1): over the 2,095-item
# iacache corpus (2,064 items with kept files, checking BOTH mp3 and flac
# delivery plus lossless-title-only recovery -- the first cut of this
# script broke on the first non-empty KEPT set and undercounted at 2/2/2),
# exactly 3 items carry a pure-4-digit cleaned tag title, 1 each, 3 distinct
# values:
#   MWatt2013-01-12                      1977  (Clash cover, direct mp3+flac tags)
#   mwatt2012-05-02.Poisson_Rouge.JFCB   1970  (Stooges cover, direct mp3+flac tags)
#   turkuaz2018-01-18                    1662  (Turkuaz original; mp3 delivery's
#     OWN tags are empty (title_fraction 0.000, n=13) -- missed by the
#     original census entirely -- but its flac copy is fully tagged
#     (0.923 pre-widening, already >= gather._RECOVER_SIBLING_ABOVE (0.9)),
#     so gather._recover_format_titles fires regardless of this widening and
#     "1662" reaches the tag rung as a RECOVERED title. The widening only
#     moves that recovered set's own title_fraction 0.923 -> 1.000.)
# Zero items carry the >=2-on-one-item STOP condition, and no value equals
# that item's own metadata.year (2013, 2012, 2018) -- all three hand-checked
# as real song titles amid an otherwise-real-titled tracklist, not a taper's
# recording-year stamp. `title_fraction` crosses `gather._RECOVER_BELOW`
# (0.5) on NONE of the three (turkuaz's mp3 side is 0.000 either way; its
# recovery gate already fired pre-widening); it crosses to/from 1.0 on all
# three. Zero STOP-qualifying items means global scope: this function itself
# accepts the numeral, not only a hygiene/adoption-side check layered on top
# of it.
#
# Standing caveat: iacache is a random.shuffle(seed=7) decade-stratified
# sample of archive.org ITEMS (see junk.py's LOSSLESS_TITLE_FORMATS comment
# for the same caveat verbatim), so this is a rate over cached items, not
# over shows llama would actually select.
#
# Cross-checked against the ~968-item working cache the pipeline actually
# touches (~/.llama/cache/md_*.json, selection-biased -- see
# docs/2026-08-07-lma-census.md): NOT zero -- 1 pure-4-digit tag title, on
# tbt2007-07-20.391.flac16 (an AKG391-mic'd SIBLING recording of
# trampledbyturtles-2007-07-20, filename ...-d2t07.mp3): "1922", the exact
# song this task's composition note already discusses. It does not trip the
# STOP condition (1, not >=2 on that item) and is not a date match (item year
# 2007 != 1922). Side note, not chased further here (no re-gather harness
# exists before Task 7): under the OLD predicate this sibling's "1922" tag
# alone failed `_sibling_titles`' `all(is_real_title(t) for t in titles)`
# gate, which is all-or-nothing per recording -- so pre-widening, this
# well-tagged sibling could not supply ANY track's title via the sibling
# rung, not just this one. The two populations AGREE ON THE RULING (zero
# STOP-qualifying items in both, by the STOP rule's own definition) even
# though their raw counts differ (3 vs 1) -- that difference is corpus size
# and selection bias, not disagreement about safety. The global-scope
# decision therefore stands on two independent bases, not one.
#
# SIZED, ACCEPTED EXPOSURE (not a re-scope, do not narrow the predicate):
# "global" also widens what structure.hygienic_title -- THE PIPELINE'S ONLY
# SILENT ADOPTER, the one surface where a wrong title ships with no flag and
# no operator ever sees it -- will accept, because hygienic_title calls this same
# is_real_title. That check runs over CANONICAL SETLIST ITEMS, not tag
# titles, a much denser population of date-shaped strings. Measured
# independently (not reused from the reviewer who first raised this) over
# the same iacache corpus via parse_setlist: 48,031 canonical items across
# 2,033 parsed descriptions, of which 181 are pure-4-digit. 162 of those 181
# already normalize into that show's own `_date_norms` (i.e. hygienic_title
# already vetoes them on the metadata-match clause, widening or not) and 0
# are caught by `is_junk_title` -- 162 confirmed under two independently
# built date-source approximations, so this is not a number sensitive to
# that choice. (162 vs. the reviewer-who-first-raised-this's 163 was never a
# disagreement, just entry-vs-item granularity: 181 total ENTRIES minus 19
# newly-passing ENTRIES is 162; 181 minus 18 DISTINCT newly-passing items is
# the mismatched 163. `minutemen1984-07-14`, which carries two of the 181
# entries, is the boundary case that separates the two countings. Recorded
# so the next reader does not re-open it.) The remaining 19 entries, on 18
# distinct items, newly clear every hygienic_title clause once this widening
# lands:
#   LosLobos2024-10-17                                                1973
#   MWatt2013-01-12                                                   1977
#   Radiators1999-10-03.dsbd.unk.tb.vortex242.mossa.flac2448          2448
#   Ween1994-00-00.SpinRadio                                          1994
#   Ween2000-05-11                                                    1999
#   cj1994-02-27.150932.FOB.AKG.Master.DAT.Ackerman.Noel.t-flac2448   2020
#   deadandco2025-08-03.schoeps.spyder9.flac16                        2026
#   dso2018-07-08.m10.spyder9.flac16                                  1978
#   dso2019-03-30.spyder9.flac16                                      1982
#   gd1984-06-21.164801.senn421.vita.miller.clugston.flac2496         1970
#   gd1989-09-29.151621.sbd.cm.miller.t.flac16                        1970
#   gd1993-05-22.170346.Nak300.D5.bzlrbi.flac2448                     1984
#   minutemen1984-07-14                                        2008, 2021
#   sbb2001-08-11.km184.flac16                                        1999
#   sbb2002-09-28.flac16                                              1999
#   ttws1995-03-20                                                    2013
#   turkuaz2018-01-18                                                 1662
#   ymsb2017-02-09.spyder9.flac16                                     1945
# This list is NOT uniformly junk: "1977" and "1662" are the same two real
# songs already established above (MWatt2013-01-12, turkuaz2018-01-18) --
# hygienic_title runs over canonical setlist items, and a real song's canonical
# item is exactly as pure-4-digit as a taper's date stamp is. The exposure
# is the REST of the list: "2448" comes out of a `flac2448` lineage fragment
# mis-split into the description; "2026" sits on a 2025 show; "2020" sits on
# a 1994 show -- lineage/tour-tag/date-adjacent junk that isn't a real song,
# surviving because `_date_norms` only vetoes a title equal to THAT show's
# own date rendering, not some other date-shaped string.
# THIS 18/19 IS AN UPPER BOUND ON EXPOSURE, NOT THE EXPOSURE: passing
# `hygienic_title` is necessary but not sufficient for a title to ship -- the
# gap must ALSO be count-forced between two independently-matched anchors
# (`adopt_gap_titles`'s whole argument). How many of these 18 would actually
# alter a shipped title in a real re-gather is NOT YET MEASURED (that needs
# a re-gather harness that does not exist before Task 7) and could be
# anywhere from 18 down to 0 -- do not read 18 as "18 junk titles will ship".
# Accepted anyway, because TBT's "1922" -- the one demonstrated-correct
# `--suggest-titles` adoption this same widening also enables via
# `setlist-gap` -- requires exactly this predicate change to reach
# `hygienic_title` at all; narrowing it back out would take 1922 with it. Task 7
# sizes the real number.
# DEFERRED, pre-existing, not introduced by this task (noted in fix round 2
# rather than fixed): `\d` matches Unicode digits, not just ASCII, so
# `is_real_title("\u0661\u0669\u0667\u0667")` (Arabic-Indic digits for
# "1977") is True. `^\d{4}$` had the identical hole before this widening --
# it just had no caller that made it visible. Out of scope here.
def is_real_title(cleaned: str) -> bool:
    """At least 3 ASCII letters (Deal, Jam) or a bare year-like 4-digit
    numeral (1922, 2001) is a real title; rejects date-less filename residue
    (d1t02), other short digit runs (01, 174), and a longer digit run that
    merely contains 4 in a row (19770101, 12345) -- `fullmatch`, not
    `match`, so the anchors can't be satisfied by a trailing newline
    either."""
    return (sum(ch.isascii() and ch.isalpha() for ch in cleaned) >= 3
            or bool(_YEAR_LIKE_NUMERIC.fullmatch(cleaned)))


# A leading track number on an enumerated tape: 1-3 digits, an optional single
# separator, then whitespace and a non-space character.
#
# The 1-3 digit bound is LOAD-BEARING and must not be widened to \d+: it is
# what puts "1952 Vincent Black Lightning" and a bare "2001" out of this rule's
# reach entirely, without the gate below having to save them. Pinned by
# test_clean_tag_titles_leaves_an_unnumbered_year_title_alone.
#
# The (?!\d) is BELT-AND-BRACES and provably INERT: the REAL protection
# against a 4th digit is the mandatory \s+, which leaves nowhere for that digit
# to go once backtracking has trimmed the match to 3. Kept because it states
# the intent at zero cost - but do not credit it with any of the work. Three
# invariants on this branch shipped unpinned precisely because a guard that
# looks protective was assumed to be doing something.
_TRACK_NUM_PREFIX = re.compile(r"^\d{1,3}(?!\d)[.)\-:]?\s+(?=\S)")

# Whether a leading number is a track number or part of the title cannot be
# decided from one string - "01 Intro - Ramona" and "100 Years" are identical
# in isolation. It is decided by the RECORDING: an enumerated tape numbers
# essentially every track, while a real numeric title is one lone numbered
# file among unnumbered ones.
#
# Measured over 2,095 cached archive.org items (see the spec's A1 evidence):
# this gate strips 94 of the 96 genuinely enumerated tapes, and mutilates NONE
# of the 105 items carrying a real numeric title. The two it misses keep their
# prefixes, which is today's behaviour - a false negative, never a destroyed
# title. Both floors are required; dropping either one breaks a pinned test.
_ENUMERATED_MIN_FILES = 3
_ENUMERATED_MIN_COVERAGE = 0.8


def title_fraction(titles: list[str]) -> float:
    """Fraction of cleaned titles that are usable. 0.0 for no titles."""
    return sum(1 for t in titles if is_real_title(t)) / len(titles) if titles else 0.0


def clean_tag_titles(kept_files: list[dict]) -> list[str]:
    """Cleaned embedded-tag titles for one recording's kept files, in play
    order. Wraps clean_tag_title with the one decision that needs the whole
    recording: whether to strip leading track numbers."""
    titles = [clean_tag_title(f.get("title")) for f in kept_files]
    numbered = sum(1 for t in titles if _TRACK_NUM_PREFIX.match(t))
    if numbered < _ENUMERATED_MIN_FILES or numbered < _ENUMERATED_MIN_COVERAGE * len(titles):
        return titles
    # Strip exactly one number, never loop: on an enumerated tape
    # "01 200 More Miles" must lose only the "01". count=1 is BELT-AND-BRACES
    # and provably INERT: the REAL guarantee is the ^ anchor, which can only
    # match at position 0, so a second strip is unreachable with or without it.
    # The property is pinned by test_clean_tag_titles_strips_once_never_loops.
    # Kept because it states the intent at the call site - not because it does
    # anything.
    return [_TRACK_NUM_PREFIX.sub("", t, count=1) for t in titles]


def _stem_no_ext(name: str) -> str:
    """Filename without its extension, directory component retained - two
    files sharing a basename in different directories are different tracks."""
    head, sep, tail = name.rpartition(".")
    return head if sep and "/" not in tail else name


def sibling_format_titles(
    kept: list[dict], other_kept: list[dict]
) -> dict[str, str] | None:
    """Map each kept file's name to the title carried by the SAME track in a
    different-format copy of the same archive.org item.

    archive.org builds the lossy derivative from the lossless original and
    sometimes does not carry the tags across, leaving a fully-tagged FLAC
    beside an untagged MP3 of the same tracks. Matching is by filename stem
    and requires a bijection: anything less declines rather than guessing by
    position."""
    if not kept or len(kept) != len(other_kept):
        return None
    ours = {_stem_no_ext(f["name"]): f["name"] for f in kept}
    theirs = {_stem_no_ext(f["name"]): f for f in other_kept}
    if len(ours) != len(kept) or len(theirs) != len(other_kept) or set(ours) != set(theirs):
        return None
    titles = clean_tag_titles([theirs[stem] for stem in ours])
    return {name: title for name, title in zip(ours.values(), titles)}


def resolve_titles(
    kept_files: list[dict],
    setlist: ParsedSetlist,
    sibling_titles: list[str] | None = None,
    format_titles: dict[str, str] | None = None,
) -> list[Track]:
    """Resolve track titles (tags -> setlist -> sibling -> unresolved).

    `format_titles` (from gather's `_recover_format_titles`) is a filename ->
    title map lifted from a different-format copy of the SAME item; when it is
    present it stands in for the tag layer entirely.

    Sets and segues are placeholders here; llama.structure.align stamps the
    real values from the canonical performance setlist. Callers pass
    kept_files in canonical play order (filter_files decides it)."""
    files = kept_files
    n = len(files)
    # The whole-tape setlist rung. MEASURED DEAD: 0 of 2,015 tracks across the
    # 89-show library (2026-08-30) — exact count equality between a parsed
    # description and a tape's file list is close to a measure-zero event on
    # real tapes; it DOES fire on small trimmed fixtures such as
    # `gd73_metadata.json` (6 files, 6 items), where it pre-empts
    # `adopt_gap_titles` entirely — a test blanking a title on that fixture
    # without also breaking the exact count match exercises this rung, not
    # the gap-fill one. Reproduce via `scripts/title_source_census.py`
    # (2026-08-30): tags 1917 | unresolved 75 | sibling 21 | override 2 |
    # setlist 0, over shows=89 tracks=2015 — same citation style as
    # `refresh_jerrybase.py`/`capture_fixture.py` for their own numbers.
    # Kept because structure.adopt_gap_titles is its localized successor
    # (count-forced GAPS between anchors), which makes this rung's deadness a
    # design property rather than a defect to re-diagnose.
    aligned = setlist.items if (setlist.confidence != "low" and len(setlist.items) == n) else None

    # When format recovery fired, the delivered format's own tags are known
    # bad and are not consulted at all - a manifest never interleaves two tag
    # sources. A recovered title that is still unusable falls through to the
    # setlist/sibling cascade rather than back to the bad tags.
    if format_titles is not None:
        tag_titles = [format_titles.get(f["name"], "") for f in files]
        tag_source = "sibling-format"
    else:
        tag_titles = clean_tag_titles(files)
        tag_source = "tags"

    tracks: list[Track] = []
    for pos, f in enumerate(files):
        if is_real_title(tag_titles[pos]):
            title, source = tag_titles[pos], tag_source
        elif aligned:
            title, source = aligned[pos].title, "setlist"
        elif sibling_titles and len(sibling_titles) == n:
            title, source = sibling_titles[pos], "sibling"
        else:
            title, source = f["name"], "unresolved"
        tracks.append(
            Track(index=pos + 1, set="1", title=title, filename=f["name"],
                  duration_sec=length_seconds(f.get("length")), segue=False,
                  title_source=source)
        )
    return tracks


def set_breaks(tracks: list[Track]) -> list[int]:
    return [prev.index for prev, nxt in zip(tracks, tracks[1:]) if nxt.set != prev.set]
