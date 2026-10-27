"""Offline replay of gather/vet over the on-disk cache: no network, no LLM.

Slice 0 of the held-backlog Tier 1 work. This module holds the cache-only
clients and the input/config/code identities the harness stamps on each arm,
and the one place the needs-LLM verdict and the outcome class are decided
(`compute_legs` + `classify`, spec ruling 5), shared by the harness and
`llama reapply`.
"""
import dataclasses
import hashlib
import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

import llama
from llama.catalog import derive_state
from llama.config import Config
from llama import title_hygiene
from llama.errors import LlamaError
from llama.junk import basename_without_extension
from llama.models import Briefing, Overrides, Overrule, Provenance, Show, VettingResult
from llama.overrules import split_overruled
from llama.setlistfm import _pick, cache_key
from llama.stages import brief as brief_stage, package as package_stage
from llama.stages.brief import briefing_guard, normalize_briefing
from llama.stages.gather import CascadeRecord, GatherResult, compute_gather
from llama.stages.vet_research import VetOutcome, apply_vet
from llama.structure import is_filler
from llama.workspace import ShowWorkspace, read_model, read_overrides

_REFUSED = "network refused by the cache-only client"


class CacheMiss(LlamaError):
    pass


class CacheOnlyIA:
    """An archive.org client that only ever reads `md_<id>.json` from the cache."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.misses: list[str] = []

    def metadata(self, identifier: str) -> dict:
        path = self.cache_dir / f"md_{identifier}.json"
        if not path.exists():
            self.misses.append(identifier)
            raise CacheMiss(f"cache miss: md_{identifier}.json")
        return json.loads(path.read_text())

    def search(self, *args, **kwargs):
        raise CacheMiss(_REFUSED)

    def scrape(self, *args, **kwargs):
        raise CacheMiss(_REFUSED)

    def download_file(self, *args, **kwargs):
        raise CacheMiss(_REFUSED)


class CacheOnlySetlistFM:
    """A setlist.fm client that only reads the client's own cache files."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.misses: list[tuple[str, str]] = []

    def setlist(self, artist: str, date: str,
                venue: str | None = None, city: str | None = None) -> dict | None:
        path = self.cache_dir / (cache_key(artist, date) + ".json")
        if not path.exists():
            self.misses.append((artist, date))
            return None
        # Like SetlistFMClient.setlist, never raise: a corrupted cache file
        # degrades to None. Not a miss: the real client would not fetch it.
        try:
            data = json.loads(path.read_text())
            return _pick(data.get("setlist", []), venue, city)
        except Exception:
            return None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def input_digests(ws: ShowWorkspace) -> dict[str, str | None]:
    """sha256 of each file the replay reads; None when absent.

    `vetting.extraction` hashes only the extraction, never the flags (which
    are derived by the arm under test).
    """
    def of(path: Path) -> str | None:
        return _sha256(path.read_bytes()) if path.exists() else None

    extraction = None
    if ws.vetting.exists():
        result = read_model(ws.vetting, VettingResult)
        extraction = _sha256(result.vetting.model_dump_json().encode())
    return {
        "show.json": of(ws.show),
        "overrides.json": of(ws.overrides),
        "provenance.json": of(ws.provenance),
        "research.md": of(ws.research),
        "vetting.extraction": extraction,
    }


def setlistfm_configured(config: Config) -> bool:
    return bool(os.environ.get("SETLISTFM_API_KEY") or config.setlistfm.api_key)


def setlistfm_client(config: Config) -> CacheOnlySetlistFM | None:
    """The one place the replay's setlist.fm client is chosen."""
    if setlistfm_configured(config):
        return CacheOnlySetlistFM(config.root / "cache")
    return None


def config_fingerprint(config: Config) -> str:
    payload = {
        "audio_format": config.audio_format,
        "structure": config.structure.model_dump(),
        "jerrybase": config.jerrybase.model_dump(),
        "setlistfm_configured": setlistfm_configured(config),
    }
    return _sha256(json.dumps(payload, sort_keys=True).encode())


def code_identity() -> str:
    """The git HEAD of the running llama (`-dirty` if uncommitted), else its version."""
    here = str(Path(llama.__file__).resolve().parent)
    try:
        sha = subprocess.run(["git", "-C", here, "rev-parse", "HEAD"], capture_output=True,
                             text=True, check=True).stdout.strip()
        status = subprocess.run(["git", "-C", here, "status", "--porcelain"], capture_output=True,
                                text=True, check=True).stdout.strip()
        if sha:
            return sha + ("-dirty" if status else "")
    except (OSError, subprocess.CalledProcessError):
        pass
    return f"version:{llama.__version__}"


# --- flag families (plan "Contracts": Flag families) ---

# (family, predicate) in order; the first match wins. `research asserts ...`
# flags are told apart by their own texts before anything generic.
_FAMILIES: tuple[tuple[str, Callable[[str], bool]], ...] = (
    ("research-song", lambda f: f.startswith("research asserts unknown song")),
    ("research-sets", lambda f: f.startswith("research asserts ") and "sets but structure has" in f),
    ("research-date", lambda f: f.startswith("research asserts wrong date")
        or (f.startswith("research asserts ") and "looks like a year-only placeholder" in f)),
    ("structure", lambda f: f.startswith((
        "low-confidence structure alignment", "single-set structure",
        "setlist evidence shows multiple sets", "structure has ", "jerrybase set closer ",
        "low-confidence setlist", "merged track(s)"))),
    ("titles", lambda f: f.startswith("unresolved track titles")),
    ("venue", lambda f: f.startswith("venue mismatch")),
    ("city", lambda f: f.startswith("recordings of this date disagree on city")),
    ("briefing", lambda f: f.startswith(brief_stage.FLAG_PREFIX)),
    ("events", lambda f: f.startswith(("tape spans", "unassigned multi-event", "multi-event date"))),
    ("tracks", lambda f: f.startswith("no playable tracks")),
    ("package", lambda f: f.startswith(package_stage.FLAG_PREFIX)),
)


def flag_family(flag: str) -> str:
    """The Contracts' family of a review flag; `other` when none matches."""
    for family, matches in _FAMILIES:
        if matches(flag):
            return family
    return "other"


# --- shipped fields and the briefing reuse rule ---

def _alignment(show: Show) -> str | None:
    return show.structure.alignment if show.structure is not None else None


def _pair(old, new) -> dict | None:
    return None if old == new else {"old": old, "new": new}


def shipped_diff(stored: Show, new: Show) -> dict:
    """The shipped fields (Contracts: per-track title, title_source, set, segue;
    set_breaks; venue; city; date; structure.alignment) that differ between
    the stored show and the replayed one. `[]`/`None` when equal.

    A track-count change makes per-index comparison meaningless, so every
    index up to the longer of the two is reported, in `title_changes`,
    `set_changes` and `segue_changes` alike, each side carrying its own
    track's value at that position (None past that show's end), so a
    hand-check list shows both tapes."""
    titles: list[dict] = []
    sets: list[dict] = []
    segues: list[dict] = []
    if len(stored.tracks) != len(new.tracks):
        for i in range(max(len(stored.tracks), len(new.tracks))):
            o = stored.tracks[i] if i < len(stored.tracks) else None
            n = new.tracks[i] if i < len(new.tracks) else None
            titles.append({"index": i + 1, "old": o.title if o else None,
                           "new": n.title if n else None,
                           "old_source": o.title_source if o else None,
                           "new_source": n.title_source if n else None})
            sets.append({"index": i + 1, "old": o.set if o else None,
                         "new": n.set if n else None})
            segues.append({"index": i + 1, "old": o.segue if o else None,
                           "new": n.segue if n else None})
    else:
        for o, n in zip(stored.tracks, new.tracks):
            if o.title != n.title or o.title_source != n.title_source:
                titles.append({"index": o.index, "old": o.title, "new": n.title,
                               "old_source": o.title_source, "new_source": n.title_source})
            if o.set != n.set:
                sets.append({"index": o.index, "old": o.set, "new": n.set})
            if o.segue != n.segue:
                segues.append({"index": o.index, "old": o.segue, "new": n.segue})
    return {
        "title_changes": titles,
        "venue": _pair(stored.venue, new.venue),
        "city": _pair(stored.city, new.city),
        "set_changes": sets,
        "segue_changes": segues,
        "set_breaks": _pair(list(stored.set_breaks), list(new.set_breaks)),
        "alignment": _pair(_alignment(stored), _alignment(new)),
        "date": _pair(stored.date, new.date),
    }


VISIBLE_FIELDS = ("files", "titles", "sets", "segues", "set_breaks", "venue", "city", "date")


def visible_changes(stored: Show, new: Show) -> list[str]:
    """The manifest-visible fields (VISIBLE_FIELDS order) that differ. Files are
    compared by name, so a same-count file swap counts; titles by text only
    (a `title_source` change is not visible)."""
    changed = {
        "files": [t.filename for t in stored.tracks] != [t.filename for t in new.tracks],
        "titles": [t.title for t in stored.tracks] != [t.title for t in new.tracks],
        "sets": [t.set for t in stored.tracks] != [t.set for t in new.tracks],
        "segues": [bool(t.segue) for t in stored.tracks] != [bool(t.segue) for t in new.tracks],
        "set_breaks": list(stored.set_breaks) != list(new.set_breaks),
        "venue": stored.venue != new.venue,
        "city": stored.city != new.city,
        "date": stored.date != new.date,
    }
    return [f for f in VISIBLE_FIELDS if changed[f]]


def row_visible_changes(row: dict, stored: Show) -> list[str]:
    """`visible_changes` computed from an arm row (a `ShowReplay` dict)."""
    filenames = row.get("filenames")
    changed = {
        "files": filenames is not None
                 and list(filenames) != [t.filename for t in stored.tracks],
        "titles": any(c.get("old") != c.get("new") for c in row.get("title_changes") or []),
        "sets": any(c.get("old") != c.get("new") for c in row.get("set_changes") or []),
        "segues": any(c.get("old") != c.get("new") for c in row.get("segue_changes") or []),
        "set_breaks": bool(row.get("set_breaks")),
        "venue": bool(row.get("venue")),
        "city": bool(row.get("city")),
        "date": bool(row.get("date")),
    }
    return [f for f in VISIBLE_FIELDS if changed[f]]


def row_label_only(row: dict, stored: Show) -> bool:
    """No manifest-visible change, but a `title_source` or `alignment` change."""
    if row_visible_changes(row, stored):
        return False
    return bool(row.get("title_changes")) or bool(row.get("alignment"))


def _structure_changed(diff: dict) -> bool:
    """Spec "structure-changed": set or segue labels, set_breaks or alignment."""
    return bool(diff["set_changes"] or diff["segue_changes"]
                or diff["set_breaks"] or diff["alignment"])


# --- Task 15a: a stored briefing that mentions a restored file is never reused ---
# Operator ruling, Checkpoint B (premise 4): `run_brief` passed the whole show.json,
# `excluded_files` ("implausibly short") included, so a stored briefing written before a
# short file was restored routinely says that file is absent. `briefing_guard` checks
# no file-presence claim, so reuse would ship that claim on air. A false "not reusable"
# costs one brief call; a false "reusable" ships a false claim: every match refuses.

# Every text field of `Briefing` (narration is stamped, non_attendee_sentiment a bool);
# a test pins this against the model so a new field cannot go unread.
BRIEFING_TEXT_FIELDS = ("context", "significance", "per_set", "notable_moments",
                        "review_sentiment", "cautions", "mentioned_songs")

_COUNT_NUM = (r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen"
              r"|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty"
              r"|sixty)(?:[\s-]+(?:one|two|three|four|five|six|seven|eight|nine))?")

# Building blocks of the negation terms (fix rounds 4-5). They match a PUNCTUATION-NORMALISED
# copy of each text (`_normalised`): its words joined by single spaces, a word being word
# characters joined by single interior apostrophes (`isn't`, `aren’t`; the look-alikes
# `` ` ``, `´`, `ʼ`, `ʻ`, `ʹ`, `‘` and `′` fold to `'` first). Every other character is a separator:
# dashes, quotes, brackets and `;:,()`. The hyphen is read BOTH ways and a term fires on
# any copy: as a separator (`not-listed` reads `not listed`) and as an interior joiner
# (`return-to-astronaut` is one window word, so "no separate return-to-astronaut track"
# fits a 3-word window). The apostrophe is read both ways too (FW2, 15b N1): a third copy
# makes every apostrophe a separator, so a quote glued between two words ("not’listed",
# "not‘listed’", which `’` and the fold would join into one word) reads `not listed`.
# Each copy only adds readings, so the gate refuses more, never less. So a term is a
# negation, a bounded window of up to N words, then the head word. `_SEP` (a space) and
# `_WORD` (no space) are disjoint, so a window splits one way only and the match stays
# linear.
_NEG = r"(?:\bnot|\bnever|n['’]t|\bcannot|\bno longer|\bnowhere|\bneither|\bnor)"
_SEP = " "
_WORD = r"[^ ]+"
_TOKEN = re.compile(r"\w+(?:['’]\w+)*")
_TOKEN_HYPHENATED = re.compile(r"\w+(?:['’-]\w+)*")
_TOKEN_SPLIT = re.compile(r"\w+")
_APOSTROPHES = str.maketrans({"`": "'", "´": "'", "ʼ": "'", "ʻ": "'", "ʹ": "'", "‘": "'",
                               "′": "'"})


def _normalised(text: str) -> tuple[str, str, str]:
    """`text`'s words, single-space separated, punctuation a separator: once with the
    hyphen a separator too, once with it joining a word, and once with every apostrophe
    (after the fold; `ʼ`, `ʻ` and `ʹ` are word characters until they are folded) a
    separator too."""
    text = text.translate(_APOSTROPHES)
    return (" ".join(_TOKEN.findall(text)), " ".join(_TOKEN_HYPHENATED.findall(text)),
            " ".join(_TOKEN_SPLIT.findall(text)))


def _window(n: int, word: str = _WORD) -> str:
    """Up to `n` arbitrary words (lazily), each preceded by a separator, then one."""
    return rf"(?:{_SEP}{word}){{0,{n}}}?{_SEP}"


# Exclusion/absence wording, matched ANYWHERE in the briefing (not only near a restored
# file's name): the conservative reading of the ruling, measured in the Task 15a report.
# Checked in this order; the first that fires names the reason. Each entry is
# (term, raw, normalised): `raw` matches the lowercased text as it is (`track count` needs
# `tracks 3–5`), `normalised` matches either copy `_normalised(text)` makes; either may be
# None, and the term fires in the first field where any matches.
_RESTORED_WORDING = tuple(
    (term, raw and re.compile(raw), norm and re.compile(norm)) for term, raw, norm in (
    ("excluded", r"\bexclu(?:de|ded|des|ding|sion|sions)\b", None),
    # these three also read the normalised text (fix round 5): "too—short", "left (entirely) out"
    # FW2 item 4: up to 2 words between, on the normalised text ("too very short",
    # "implausibly, very short"), as `left out` already allowed
    ("implausibly short", r"\bimplausibl[ey]\s+short\b", rf"\bimplausibl[ey]{_window(2)}short\b"),
    ("too short", r"\btoo\s+short\b", rf"\btoo{_window(2)}short\b"),
    ("left out", r"\b(?:left|leaves?|leaving)\s+(?:out|off)\b",
                 rf"\b(?:left|leaves?|leaving){_window(2)}(?:out|off)\b"),
    ("omitted", r"\bomi(?:t|ts|tted|tting|ssion|ssions)\b", None),
    ("absent", r"\babsen(?:t|ce)\b", None),
    ("not present", None, rf"{_NEG}{_window(3)}present\b"),
    ("missing", r"\bmissing\b", None),
    ("dropped", r"\bdropp(?:ed|ing)\b", None),
    ("not represented", None, rf"{_NEG}{_window(3)}represented\b"),
    ("not part of", None, rf"{_NEG}{_window(3)}part{_window(3)}of\b"),
    # not [up to 5 words] track(s): "not even a separate track", "never a track". The
    # window stops at a word starting `track` ("not tracked as separate tracks" is `not
    # tracked separately`'s). A `track list` head counts only when no `in`/`on` sits in
    # the window: "not a track list entry" is this term, "not in the track list" is `not in
    # the setlist`'s. Both are later terms, so this only decides which reason is named.
    ("not a track", None, rf"{_NEG}{_window(5, r'(?!track)[^ ]+')}tracks?\b(?![ -]?list(?:ing)?s?\b)"
                          rf"|{_NEG}{_window(5, r'(?!track|(?:in|on) )[^ ]+')}tracks?[ -]?list(?:ing)?s?\b"),
    # a count or a numbered range of tracks/songs/files: a restoration changes it
    ("track count", rf"\b{_COUNT_NUM}[\s-]+(?:tracks|songs|files)\b|\b{_COUNT_NUM}-(?:track|song|file)\b"
                    r"|\btracks?\s+\d+\s*(?:-|–|—|to|through|thru)\s*\d+", None),
    # Tasks 15b (operator rulings, Checkpoint B) and fix rounds: these terms, and `not
    # present`, `not represented`, `not part of` and `not a track` above, are a negation
    # (`_NEG`; `no`/`without` for `no separate track`, a bare `no` for `not found`'s
    # `place` and for `no … listed`) followed by a BOUNDED window of up to 2-5 words
    # before EVERY head word, over the normalised text ("should not, in fact, have been
    # included", "is not “officially” listed"). Heads take every inflection. `unlisted`
    # is a plain word. Over-matching only costs a brief call; under-matching ships a
    # false absence claim.
    ("not included", None, rf"{_NEG}{_window(5)}includ(?:e|es|ed|ing)\b"),
    ("not listed", None, rf"{_NEG}{_window(5)}listed\b"),
    ("does not appear", None, rf"{_NEG}{_window(5)}appear(?:s|ed|ing)?\b"),
    ("unlisted", r"\bunlisted\b", None),
    # not [up to 3 words] in|on [up to 3 words] setlist | set list | set-list | tracklist |
    # track listing, any plural: "is not even on the setlist", "not in this track listing"
    ("not in the setlist", None, rf"{_NEG}{_window(3)}(?:in|on){_window(3)}(?:set|track)[ -]?list(?:ing)?s?\b"),
    # no / without [up to 3 words] track(s): "no separate track", "without its own track"
    ("no separate track", None, rf"\b(?:no|without){_window(3)}tracks?\b"),
    # not [up to 3 words] tracked|tracking: "not tracked separately", "not separately
    # tracked", "not tracking as a separate track"
    ("not tracked separately", None, rf"{_NEG}{_window(3)}track(?:ed|ing)\b"),
    # paraphrases (fix round 4): "does not show up", "cannot be found", "isn't on the
    # tape", "is nowhere in the data", "has no place in the listing"; in|on takes the
    # nouns tape, recording, data, listing, list, file (any plural)
    ("not found", None, rf"{_NEG}{_window(3)}(?:show(?:s|ed|n|ing)?{_window(2)}up|found"
                        rf"|(?:in|on){_window(2)}(?:tape|recording|data|listing|list|file)s?)\b"
                        rf"|(?:{_NEG}|\bno){_window(3)}place\b"),
    # fix round 5, appended last so no earlier first hit moves: the verb heads list and
    # contain ("does not list the jam", "does not contain the reprise"; a bare `list` head
    # in `not listed` would take "did not appear on the list" from `does not appear`)
    ("not included or listed", None, rf"{_NEG}{_window(5)}(?:list(?:s|ed|ing)?|contain(?:s|ed|ing)?)\b"),
    # a bare `no` before a head: "No encore is listed.", "No intro appears."
    ("no … listed", None, rf"\bno{_window(3)}(?:listed|included|present|appear(?:s|ed|ing)?|found)\b"),
    # FW2 item 5, the vocabulary 15b measured outside every term (t15b-rr5, over
    # ~/.llama-harness/piece4/ckb/15a/dump.jsonl's 1,014 rows), appended last so no
    # earlier first hit moves. Corpus counts, by 15b's own probes:
    # `lacks`: 57 spans in 50 rows, 6 in 6 with a data subject ("his tape lacks the
    #   intro", belafleckandtheflecktones-1995-08-25; "the track data lacks",
    #   brotherspast-2006-11-17); a plain word, so it also refuses "lacking in top end".
    ("lacks", r"\black(?:s|ed|ing)?\b", None),
    # `not recorded`: 10 spans in 9 rows ("the first two songs of the night were not
    #   recorded", hayescarll-2006-01-21)
    ("not recorded", None, rf"{_NEG}{_window(3)}recorded\b"),
    # `cut from the recording`: 5 rows ("were cut from the recording",
    #   greenskybluegrass-2010-03-26); also `off`/`out` and the `not found` nouns
    ("cut from the recording", None,
     rf"\bcuts?{_window(2)}(?:from|off|out){_window(3)}(?:tape|recording|data|listing|list|file|show)s?\b"),
    # data subject, then `lists|contains`, then `no`: 100 spans in 96 rows with a data
    #   subject, "flags" left out of that count (506 in 363 for any verb, then `no`);
    #   "the show data lists no encore" (billystrings-2017-08-29), "Setlist.fm lists no
    #   encore". Up to 2 words between subject and verb, 1 between verb and `no`.
    ("lists no", None,
     r"\b(?:data|tapes?|recordings?|lists?|listings?|tracklists?|setlists?|tracks?|files?"
     rf"|page|description|notes|fm){_window(2)}(?:list(?:s|ed)?|contain(?:s|ed)?){_window(1)}no\b"),
))

# A filename's disc/track tail (`d3t04`, `s2t01`, `D3_T02`, `t14`, `track01`).
_TRACK_TAIL = re.compile(r"(?:(?:disc|disk|cd|set|d|s)[-_ ]?0*(\d+)[-_ ]?)?t(?:rack)?[-_ ]?0*(\d+)(?!\d)")


def _briefing_texts(b: Briefing) -> list[tuple[str, str]]:
    """(field, lowercased text) for every text field of `b`, per_set keys included."""
    out = [("context", b.context), ("significance", b.significance)]
    for key, points in b.per_set.items():
        out += [("per_set", key)] + [("per_set", p) for p in points]
    out += [("notable_moments", x) for x in b.notable_moments]
    out += [("review_sentiment", b.review_sentiment)]
    out += [("cautions", x) for x in b.cautions]
    out += [("mentioned_songs", x) for x in b.mentioned_songs]
    return [(f, t.lower()) for f, t in out]


def _name_patterns(filename: str) -> list[re.Pattern]:
    """How a briefing may name `filename`: the basename, its stem, and the stem's
    disc/track tail as shorthand (`d3t04`, `disc 3, track 4`, a bare `t04`)."""
    base = filename.rsplit("/", 1)[-1].lower()
    stem = basename_without_extension(filename).lower()
    pats = [re.compile(re.escape(base)), re.compile(re.escape(stem))]
    for m in _TRACK_TAIL.finditer(stem):
        disc, track = m.group(1), m.group(2)
        if disc is not None:
            pats.append(re.compile(rf"(?<![a-z0-9])(?:disc|disk|cd|set|d|s)\s*[-_ ]?0*{disc}"
                                   rf"\s*[-_ ]?t(?:rack)?\s*[-_ ]?0*{track}(?!\d)"))
            pats.append(re.compile(rf"\bdis[ck]\s*0*{disc}\W{{0,3}}track\s*0*{track}(?!\d)"))
        pats.append(re.compile(rf"(?<![a-z0-9])t0*{track}(?!\d)"))
    return pats


def _restored_mentions(briefing: Briefing, restored: list[str]) -> list[tuple[str, str, str]]:
    """Every way `briefing` mentions the restored files, in check order, as
    (kind, what, field): ("names", filename, field) per file then
    ("says", term, field) per wording term, each once at its first field."""
    texts = _briefing_texts(briefing)
    hits = []
    for fn in restored:
        pats = _name_patterns(fn)
        field = next((f for f, t in texts if any(p.search(t) for p in pats)), None)
        if field is not None:
            hits.append(("names", fn, field))
    both = [(f, t, _normalised(t)) for f, t in texts]
    for term, raw, norm in _RESTORED_WORDING:
        field = next((f for f, t, nts in both
                      if (raw and raw.search(t)) or (norm and any(norm.search(n) for n in nts))), None)
        if field is not None:
            hits.append(("says", term, field))
    return hits


def _restored_file_mention(briefing: Briefing, restored: list[str]) -> str | None:
    """The Task 15a refusal, or None: the first mention `_restored_mentions` finds."""
    hits = _restored_mentions(briefing, restored) if restored else []
    if not hits:
        return None
    kind, what, field = hits[0]
    what = what if kind == "names" else f"'{what}'"
    return f"briefing mentions a restored file: {kind} {what} in {field}"


def briefing_reusable(stored_show: Show, new_show: Show, briefing: Briefing,
                      narration: str, *, overrules: Sequence[Overrule] = ()) -> str | None:
    """Spec slice 6 step 3, the reuse rule: None when the stored briefing can
    ship with `new_show`; else the first failing reason. Broadcast fields are
    per-track titles, sets and segues, set_breaks, date, venue, city
    (title_source is not one: the briefing never sees it).

    Last (Task 15a, operator ruling at Checkpoint B): when the new show has a
    restored file (a `short_kept` track whose filename is not among the stored
    show's tracks), a briefing naming one or using exclusion/absence wording
    anywhere is refused (`_restored_file_mention`). With none, the rule is
    unchanged.

    `overrules` (bulk-apply Task 4b, parent-authorised): a guard problem matching
    one of the show's recorded overrules (`split_overruled`, against `new_show`'s
    identifier) does not refuse; the guard refuses only on a problem still held,
    and names only those. Every other refusal is unchanged, so overrules can only
    make it accept more. The default `()` is today's rule."""
    o, n = stored_show, new_show
    short = {t.filename for t in n.tracks if t.short_kept}   # spec 5.3: dropped on both sides
    ot = [t for t in o.tracks if t.filename not in short]
    nt = [t for t in n.tracks if t.filename not in short]
    if [t.filename for t in ot] != [t.filename for t in nt]:
        return "tracks differ"

    def break_keys(show: Show, kept: list) -> list:
        # a break after track i is keyed by the last remaining track at or before i
        keys = []
        for i in show.set_breaks:
            before = [t.filename for t in kept if t.index <= i]
            keys.append(before[-1] if before else None)
        return sorted(keys, key=lambda k: (k is not None, k or ""))

    changed = [name for name, differs in (
        ("titles", [t.title for t in ot] != [t.title for t in nt]),
        ("sets", [t.set for t in ot] != [t.set for t in nt]),
        ("segues", [t.segue for t in ot] != [t.segue for t in nt]),
        ("set_breaks", break_keys(o, ot) != break_keys(n, nt)),
        ("date", o.date != n.date),
        ("venue", o.venue != n.venue),
        ("city", o.city != n.city),
    ) if differs]
    if changed:
        return f"broadcast fields changed: {', '.join(changed)}"
    if briefing.narration != narration:
        return f"narration differs: briefing {briefing.narration}, overrides {narration}"
    problems = briefing_guard(normalize_briefing(briefing), new_show)   # 3a: guard the shipped form
    problems, _overruled = split_overruled(problems, overrules, new_show)
    if problems:
        return f"briefing guard: {'; '.join(problems)}"
    stored_names = {t.filename for t in o.tracks}
    # the gate scans the briefing as passed; briefing_guard scans normalize_briefing(briefing).
    # In compute_legs they are identical; the raw form can only refuse more.
    restored = [t.filename for t in n.tracks if t.short_kept and t.filename not in stored_names]
    return _restored_file_mention(briefing, restored)


def _read_briefing(ws: ShowWorkspace) -> Briefing:
    """The stored `briefing.json` as it would ship: 3a-normalised (spec slice
    3, "on every reuse of a stored briefing"). The one read of a stored
    briefing in replay, so the reuse decision, `brief_flags`, `Legs.briefing`
    and `stored_brief_guard` all see the same normalised briefing."""
    return normalize_briefing(read_model(ws.briefing_json, Briefing))


# --- the three legs ---

@dataclasses.dataclass
class Legs:
    """One show's deterministic replay: gather (LLM-free), vet (over the stored
    extraction) and the brief reuse decision. Nothing here is written."""
    gather: GatherResult
    stored: Show
    vet: VetOutcome | None
    # gather's verdicts, then "stored alignment llm", then "no vetting.json"
    needs_llm: list[str]
    brief: str                     # "reuse" | "fresh" | "none"
    brief_reason: str | None       # why a stored briefing.json is not reused
    brief_flags: list[str]
    briefing: Briefing | None      # the stored briefing, 3a-normalised, only when brief == "reuse"
    carried_flags: list[str]       # stored `package`-family flags, carried through
    flags: list[str]               # gather + vet + carried + brief_flags
    # on reuse, the stored briefing's overruled guard problems as `overruled: <flag>`
    # notes (notes.json `brief`); [] otherwise
    brief_notes: list[str] = dataclasses.field(default_factory=list)

    @property
    def replayed_show(self) -> Show:
        """The replayed show with vet applied: what would ship."""
        return self.vet.show if self.vet is not None else self.gather.show


def compute_legs(ws: ShowWorkspace, *, config: Config, ia, slfm: "CacheOnlySetlistFM | None",
                 scratch: Path,
                 enabled_slices: frozenset[str] = title_hygiene.ENABLED_SLICES) -> Legs:
    """Replay one library show into `scratch` (recreated empty, then given a
    copy of `overrides.json` and nothing else); `ws.dir` is only read.

    `slfm` is `setlistfm_client(config)` and nothing else (None when no key is
    configured), so the replay sees what `process_show` would. `CacheMiss`
    propagates; a missing `provenance.json`/`show.json` is a `LlamaError`.
    A `scratch` that is, contains or lies inside `ws.dir`, or lies inside the
    library's `shows/` (`ws.dir.parent`: another show's directory), is refused
    before anything is deleted: the recreate is an rmtree."""
    show_dir, scr = ws.dir.resolve(), scratch.resolve()
    if scr == show_dir or show_dir in scr.parents or scr in show_dir.parents:
        raise LlamaError(f"refusing scratch {scratch}: it overlaps the show directory {ws.dir}")
    if show_dir.parent in scr.parents:
        raise LlamaError(f"refusing scratch {scratch}: it lies inside the library's shows "
                         f"directory {ws.dir.parent}")
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    if ws.overrides.exists():
        shutil.copyfile(ws.overrides, scratch / ws.overrides.name)
    for path in (ws.provenance, ws.show):
        if not path.exists():
            raise LlamaError(f"cannot replay {ws.dir.name}: missing {path.name}")
    prov = read_model(ws.provenance, Provenance)
    stored = read_model(ws.show, Show)

    gathered = compute_gather(
        ShowWorkspace(scratch), ia, None, prov.candidate, stored.identifier,
        audio_format=config.audio_format, align_provider=None, setlistfm=slfm,
        structure_cfg=config.structure, jerrybase_enabled=config.jerrybase.enabled,
        enabled_slices=enabled_slices)
    needs_llm = list(gathered.needs_llm)
    if (stored.structure is not None and stored.structure.alignment == "llm"
            and not gathered.taper_owned and not gathered.self_filled):
        # Piece 2 relaxation (taper_owned) extended by piece 3 (self_filled, spec Q2): neither
        # makes an align_structure call, so the stored `llm` alignment is replayable.
        needs_llm.append("stored alignment llm")

    vet: VetOutcome | None = None
    if ws.vetting.exists():
        # Overrules (bulk-apply spec "Overrules persist"): gather read them from the
        # scratch copy of overrides.json; vet gets the same records.
        vet = apply_vet(read_model(ws.vetting, VettingResult).vetting, gathered.show,
                        overrules=read_overrides(ws).overrules)
    else:
        needs_llm.append("no vetting.json")
    replayed = vet.show if vet is not None else gathered.show

    carried = [f for f in stored.review_flags if flag_family(f) == "package"]
    # The gate counts carried package flags too: a show that stays held on
    # one gets no brief (spec slice 6 step 3: "only when steps 1 and 2 left
    # no flag", and reapply never clears a carried package flag).
    flags = list(gathered.show.review_flags) + (list(vet.result.flags) if vet else []) + carried

    brief, reason, brief_flags, briefing, brief_notes = "none", None, [], None, []
    if not flags:
        brief = "fresh"
        if ws.briefing_json.exists():
            stored_briefing = _read_briefing(ws)
            overrides = read_overrides(ws)
            reason = briefing_reusable(stored, replayed, stored_briefing,
                                       overrides.narration, overrules=overrides.overrules)
            if reason is None:
                brief, briefing = "reuse", stored_briefing
                # held: [] by construction; overruled: the notes (Task 4b)
                brief_flags, brief_notes = split_overruled(
                    briefing_guard(stored_briefing, replayed), overrides.overrules, replayed)

    return Legs(gather=gathered, stored=stored, vet=vet, needs_llm=needs_llm, brief=brief,
                brief_reason=reason, brief_flags=brief_flags, briefing=briefing,
                carried_flags=carried, flags=flags + brief_flags, brief_notes=brief_notes)


# --- outcome classification (plan "Contracts": Outcome classes) ---

def classify(legs: Legs, stored_state: str) -> tuple[str, str | None]:
    """`(outcome, would_be)`. needs-LLM is decided first and admits no
    exception (spec ruling 5; "No stored vetting.json means needs-LLM"), then
    held shows (`stored_state == "held"`) and non-held shows apart."""
    if legs.needs_llm:
        return "needs-llm", None
    diff = shipped_diff(legs.stored, legs.replayed_show)
    if stored_state == "held":
        if legs.carried_flags:
            return "still-held-package", None
        if legs.flags:
            return "still-held", None
        would_be = "clears" if legs.brief == "reuse" else "needs-brief"
        if _structure_changed(diff):
            return "structure-changed", would_be
        return would_be, None
    if legs.flags:
        return "newly-held", None
    if any(diff.values()):
        return "clean-changed", None
    return "clean", None


@dataclasses.dataclass
class ShowReplay:
    """One show's row in a harness arm (plan "Contracts": ShowReplay), plus
    `date` beside `venue`/`city` (orchestrator ruling M7: date is a shipped
    field). Filled by `replay_show` (Task 5)."""
    slug: str
    state: str
    stored_flags: list[str] = dataclasses.field(default_factory=list)
    stored_core_flags: list[str] = dataclasses.field(default_factory=list)
    gather_flags: list[str] = dataclasses.field(default_factory=list)
    vet_flags: list[str] = dataclasses.field(default_factory=list)
    brief_flags: list[str] = dataclasses.field(default_factory=list)
    stored_brief_guard: list[str] | None = None
    needs_llm: list[str] = dataclasses.field(default_factory=list)
    outcome: str = ""
    would_be: str | None = None
    briefing: str = "none"
    reproduces: bool = False
    title_changes: list[dict] = dataclasses.field(default_factory=list)
    venue: dict | None = None
    city: dict | None = None
    date: dict | None = None
    selected_venue: str | None = None
    selected_city: str | None = None
    set_changes: list[dict] = dataclasses.field(default_factory=list)
    segue_changes: list[dict] = dataclasses.field(default_factory=list)
    set_breaks: dict | None = None
    alignment: dict | None = None
    notes: list[str] = dataclasses.field(default_factory=list)
    digests: dict = dataclasses.field(default_factory=dict)
    slfm_miss: bool = False
    unreplayable: str | None = None
    # Piece 2 (taper markers). Base-arm rows (base code) lack these keys; readers
    # treat a missing key as absent. `sets`/`filler` are the replayed per-track
    # labels and `is_filler` of `gathered.show`, before vet.
    taper_owned: bool = False
    sets: list[str] = dataclasses.field(default_factory=list)
    filler: list[bool] = dataclasses.field(default_factory=list)
    taper_source: str | None = None
    taper_reason: str | None = None
    step1_alignment: str | None = None
    # Piece 3 (title hygiene). Base-arm rows lack these keys. `titles`, `title_sources` and
    # `title_paths` are per track of `gathered.show`, before vet; `cascade` is the record of
    # the cascade (`_cascade_dict`), positions 1-based, `{}` on an unreplayable row. A
    # needs-LLM row carries it too (Checkpoint B ruling 4, final review I-1; a deviation from
    # the plan's Task 17 contract): every title is final before the LLM branch, which
    # touches structure only, so the record is what attributes those rows' holds.
    self_filled: bool = False
    desc_position: int = 0
    titles: list[str] = dataclasses.field(default_factory=list)
    title_sources: list[str] = dataclasses.field(default_factory=list)
    title_paths: list[str] = dataclasses.field(default_factory=list)
    cascade: dict = dataclasses.field(default_factory=dict)
    # Piece 4 (junk short-keep). Base-arm rows (e37f670) lack these keys; readers treat a
    # missing key as absent. Per track of `gathered.show`, before vet: `filenames`,
    # `short_kept` (the junk filter's short-file rule kept it) and `segues`; `breaks` is
    # `gathered.show.set_breaks`; `flags` is `legs.flags` (gather + vet + carried). The
    # encore position is derived by readers from `sets`.
    filenames: list[str] = dataclasses.field(default_factory=list)
    short_kept: list[bool] = dataclasses.field(default_factory=list)
    segues: list[bool] = dataclasses.field(default_factory=list)
    breaks: list[int] = dataclasses.field(default_factory=list)
    flags: list[str] = dataclasses.field(default_factory=list)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def _cascade_dict(rec: CascadeRecord | None) -> dict:
    """The cascade's fills and declines for the harness (positions 1-based; the dict keys of
    `d_track_declines`, `c_changed` and `short4_declined` are strings so an arm survives a JSON round trip).
    `c_demoted` lists slice 3's shifted-delivered-set demotions (final review C-1)."""
    if rec is None:
        return {}
    one = lambda xs: sorted(p + 1 for p in xs)   # noqa: E731
    d, c = rec.d, rec.lossless
    return {
        "s_mode": rec.s_plan.mode,
        "s_fills": one(rec.s_plan.fills),
        "s_declined": one(rec.s_plan.declined),
        "deferred_applied": one(rec.deferred_applied),
        "d_fills": one(d.fills) if d is not None else [],
        "d_failed": d.failed[0][0] if d is not None and d.failed else None,
        "d_track_declines": ({str(p + 1): v for p, v in sorted(d.track_declines.items())}
                             if d is not None else {}),
        "c_changed": ({str(p + 1): v for p, v in sorted(c.changed.items())}
                      if c is not None else {}),
        "c_declined": c.declined if c is not None else None,
        "c_demoted": one(c.demoted) if c is not None else [],
        "short4": one(rec.short4),
        "short4_declined": {str(p + 1): v for p, v in sorted(rec.short4_declined.items())},
        "gap_filled": one(rec.gap_filled),
    }


class _OverridesUnreadable(Exception):
    pass


def _selected(prov: Provenance, identifier: str) -> tuple[str | None, str | None]:
    """The stripped non-empty `venue`/`coverage` of the provenance candidate's
    recording `identifier` (Contracts: selected_venue/selected_city)."""
    for rec in prov.candidate.recordings:
        if rec.identifier == identifier:
            return (rec.venue or "").strip() or None, (rec.coverage or "").strip() or None
    return None, None


def replay_show(ws: ShowWorkspace, *, config: Config, ia, slfm: "CacheOnlySetlistFM | None",
                scratch: Path, delivered: set[str],
                enabled_slices: frozenset[str] = title_hygiene.ENABLED_SLICES) -> ShowReplay:
    """One show's arm row (plan "Contracts": ShowReplay). Never raises for a
    per-show failure: a cache miss, an unreadable `overrides.json` or any
    other exception is recorded as `outcome="unreplayable"`, so one bad show
    cannot stop a run. Writes only into `scratch` (via `compute_legs`).

    The stored-side fields (stored/core flags, stored_brief_guard,
    selected_venue/city) are filled before the replay, so they are present
    for a needs-LLM show and, where readable, for an unreplayable one."""
    r = ShowReplay(slug=ws.dir.name, state="unknown")
    misses = len(slfm.misses) if slfm is not None else 0
    try:
        r.state = derive_state(ws, delivered)[0]
        if ws.overrides.exists():
            try:
                read_model(ws.overrides, Overrides)
            except (OSError, ValueError) as err:   # pydantic ValidationError is a ValueError
                raise _OverridesUnreadable() from err
        r.digests = input_digests(ws)
        if ws.show.exists():
            stored = read_model(ws.show, Show)
            r.stored_flags = list(stored.review_flags)
            r.stored_core_flags = [f for f in stored.review_flags
                                   if flag_family(f) not in ("package", "briefing")]
            if ws.briefing_json.exists():
                r.stored_brief_guard = briefing_guard(_read_briefing(ws), stored)
            if ws.provenance.exists():
                r.selected_venue, r.selected_city = _selected(
                    read_model(ws.provenance, Provenance), stored.identifier)

        legs = compute_legs(ws, config=config, ia=ia, slfm=slfm, scratch=scratch,
                            enabled_slices=enabled_slices)
        r.gather_flags = list(legs.gather.show.review_flags)
        r.vet_flags = list(legs.vet.result.flags) if legs.vet is not None else []
        r.brief_flags = list(legs.brief_flags)
        r.needs_llm = list(legs.needs_llm)
        r.briefing = legs.brief
        r.outcome, r.would_be = classify(legs, r.state)
        r.reproduces = sorted(r.stored_core_flags) == sorted(r.gather_flags + r.vet_flags)
        diff = shipped_diff(legs.stored, legs.replayed_show)
        for key in ("title_changes", "venue", "city", "date", "set_changes",
                    "segue_changes", "set_breaks", "alignment"):
            setattr(r, key, diff[key])
        r.notes = (list(legs.gather.notes) + (list(legs.vet.notes) if legs.vet is not None else [])
                   + list(legs.brief_notes))
        g = legs.gather
        r.taper_owned = bool(g.taper_owned)
        r.sets = [t.set for t in g.show.tracks]
        r.filler = [bool(is_filler(t.title)) for t in g.show.tracks]
        r.taper_source = g.taper.source if g.taper is not None else None
        r.taper_reason = g.taper.reason if g.taper is not None else None
        r.step1_alignment = g.step1_alignment
        r.self_filled = bool(g.self_filled)
        r.desc_position = sum(1 for t in g.show.tracks if t.title_source == "desc-position")
        r.titles = [t.title for t in g.show.tracks]
        r.title_sources = [t.title_source for t in g.show.tracks]
        r.title_paths = list(g.title_paths)
        r.cascade = _cascade_dict(g.title_record)
        r.filenames = [t.filename for t in g.show.tracks]
        r.short_kept = [bool(t.short_kept) for t in g.show.tracks]
        r.segues = [bool(t.segue) for t in g.show.tracks]
        r.breaks = list(g.show.set_breaks)
        r.flags = list(legs.flags)
    except CacheMiss as err:
        r.outcome, r.unreplayable = "unreplayable", str(err)
    except _OverridesUnreadable:
        r.outcome, r.unreplayable = "unreplayable", "overrides.json unreadable"
    except Exception as err:
        r.outcome, r.unreplayable = "unreplayable", f"{type(err).__name__}: {err}"[:200]
    if r.unreplayable is not None:
        r.reproduces = False
    r.slfm_miss = slfm is not None and len(slfm.misses) > misses
    return r
