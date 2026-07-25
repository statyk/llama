"""Deterministic normalization of DJ-script text on the way into the TTS.

Applied ONLY to the string handed to speech.synthesize() — never to the
human-readable dj-notes.md / dj-notes.json. Two stages: expand symbols the
backends mis-voice (a literal '>' segue is otherwise read "greater than"),
then apply a curated pronunciation lexicon that respells names so the backend
says them right (e.g. Sugaree -> Shugaree). See
docs/superpowers/specs/2026-07-25-dj-script-speech-quality-design.md.
"""
import re

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
