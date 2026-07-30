"""Deterministic normalization of DJ-script text on the way into the TTS.

Applied ONLY to the string handed to speech.synthesize() — never to the
human-readable dj-notes.md / dj-notes.json. Two stages: expand symbols the
backends mis-voice (a literal '>' segue is otherwise read "greater than"),
then apply a curated pronunciation lexicon that respells names so the backend
says them right (e.g. Sugaree -> Shugaree). See
docs/superpowers/specs/2026-07-25-dj-script-speech-quality-design.md.
"""
import csv
import logging
import re
from importlib import resources
from pathlib import Path

log = logging.getLogger(__name__)

# Symbols that plausibly appear in DJ prose and that the TTS mis-voices.
# Ordered literal substitutions; deliberately small (numerals/years are left
# alone — the backends handle those acceptably).
_SYMBOL_REPLACEMENTS = [
    (">", " into "),
    ("&", " and "),
    ("%", " percent "),
]
_MULTISPACE = re.compile(r"[ \t]{2,}")


class Lexicon:
    """Written-form -> spoken-form respellings, matched case-insensitively on
    whole words/phrases. Respelling is spoken-only, so case of the replacement
    is irrelevant; the value is substituted verbatim.
    """

    def __init__(self, entries: dict[str, str]):
        self._entries = {w: s for w, s in entries.items() if w.strip()}
        self._lower = {w.lower(): s for w, s in self._entries.items()}
        self._pattern = self._compile(self._entries)

    @staticmethod
    def _compile(entries: dict[str, str]) -> "re.Pattern | None":
        if not entries:
            return None
        # Longest first so "Help on the Way" wins over a bare "Way".
        keys = sorted(entries, key=len, reverse=True)
        alt = "|".join(re.escape(k) for k in keys)
        # (?<!\w)...(?!\w) is a word boundary that also works for multi-word
        # phrases (\b would fail at internal spaces).
        return re.compile(rf"(?<!\w)(?:{alt})(?!\w)", re.IGNORECASE)

    @classmethod
    def empty(cls) -> "Lexicon":
        return cls({})

    def apply(self, text: str) -> str:
        if self._pattern is None:
            return text
        return self._pattern.sub(lambda m: self._lower[m.group(0).lower()], text)


def normalize_for_speech(text: str, lexicon: Lexicon) -> str:
    """Expand mis-voiced symbols, apply the pronunciation lexicon, tidy spaces.
    Identity on clean prose with an empty lexicon."""
    for symbol, replacement in _SYMBOL_REPLACEMENTS:
        text = text.replace(symbol, replacement)
    text = lexicon.apply(text)
    return _MULTISPACE.sub(" ", text).strip()


def _merge_rows(entries: dict[str, str], f) -> None:
    """Merge written,spoken rows from an open CSV file into entries in place.
    Later files override earlier ones; blank/short rows are skipped."""
    for row in csv.DictReader(f):
        written = (row.get("written") or "").strip()
        spoken = (row.get("spoken") or "").strip()
        if written and spoken:
            entries[written] = spoken


def load_lexicon(root: Path | None = None) -> Lexicon:
    """The pronunciation lexicon: the baked-in seed
    (emcee.data/pronunciations.csv) plus, if present, a workspace overlay at
    <root>/pronunciations.csv whose entries add to and override the seed.
    Malformed or unreadable sources are warned about and skipped — loading the
    lexicon must never raise (mirrors jerrybase._load)."""
    entries: dict[str, str] = {}
    try:
        with resources.files("emcee.data").joinpath("pronunciations.csv").open(
                "r", encoding="utf-8", newline="") as f:
            _merge_rows(entries, f)
    except Exception as err:  # noqa: BLE001 - a bad seed must not break packaging
        log.warning("pronunciations: could not load baked-in seed: %s", err)
    if root is not None:
        overlay = root / "pronunciations.csv"
        if overlay.exists():
            try:
                with overlay.open("r", encoding="utf-8", newline="") as f:
                    _merge_rows(entries, f)
            except Exception as err:  # noqa: BLE001 - a bad overlay is ignorable
                log.warning("pronunciations: ignoring malformed overlay %s: %s",
                            overlay, err)
    return Lexicon(entries)
