"""Strict transcript comparison for short announcement pieces.

``tts/verify.py`` only fails gross mismatches; a phrase piece must be right to
the word.  The tokenizer here is deliberately its own (it spells digits out, so
``2:30`` and "two thirty" agree) and does not share ``verify.py``'s normaliser.

A piece's text splits into *template* tokens (fixed phrase words and every
number word) and *name* tokens (everything else).  Template tokens must match
exactly, in order.  Name tokens are compared phonetically, by Metaphone key
(Shawn's ruling 2026-11-25, replacing a one-edit character tolerance).  Each
maximal run of name tokens is a *span* (a title, an artist); spans are
compared pairwise in order, the last token of every span must have an equal key,
and earlier tokens may differ by ``NAME_EDITS`` token-level insert/delete
(never a substitution of an unequal key) over the whole piece.  The piece's
final token is compared by key when it is a name token, exactly when it is
template (``continues``, ``Eastern``).
"""
from __future__ import annotations

import re
import unicodedata

import jellyfish

NAME_EDITS = 1

_ONES = ("zero one two three four five six seven eight nine ten eleven twelve "
         "thirteen fourteen fifteen sixteen seventeen eighteen nineteen").split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def number_words(n: int) -> list[str]:
    if n < 20:
        return [_ONES[n]]
    if n < 100:
        return [_TENS[n // 10]] + ([_ONES[n % 10]] if n % 10 else [])
    if n < 1000:
        return [_ONES[n // 100], "hundred"] + (number_words(n % 100) if n % 100 else [])
    return number_words(n // 1000) + ["thousand"] + (number_words(n % 1000) if n % 1000 else [])


TEMPLATE_WORDS: frozenset[str] = frozenset(
    "coming up next continues with followed by then at eastern just after around "
    "quarter past half to a few minutes before midnight noon oh".split()
) | frozenset(w for n in range(1000) for w in number_words(n)) | {"thousand", "hundred"}

_TIME = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3})")
_SPLIT = re.compile(r"[^0-9a-z]+")
_BOUNDARY = re.compile(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])")


def _time_words(m: re.Match) -> str:
    hour, minute = int(m.group(1)), int(m.group(2))
    words = number_words(hour)
    if minute:
        words += ["oh"] + number_words(minute) if minute < 10 else number_words(minute)
    return " " + " ".join(words) + " "


def tokens(text: str) -> list[str]:
    s = unicodedata.normalize("NFKD", text)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    for ch in "'’‘`":
        s = s.replace(ch, "")
    s = s.replace("&", " and ")
    s = _TIME.sub(_time_words, s)
    s = _THOUSANDS.sub("", s)
    raw: list[str] = []
    for part in _SPLIT.split(s):
        raw.extend(p for p in _BOUNDARY.split(part) if p)
    out: list[str] = []
    for tok in raw:
        if tok.isdigit():
            n = int(tok)
            out.extend(number_words(n) if n <= 999_999 else [tok])
        else:
            out.append(tok)
    # Join runs of two or more single letters ("l m a" -> "lma").
    joined: list[str] = []
    run: list[str] = []
    for tok in out + [""]:
        if len(tok) == 1 and tok.isalpha():
            run.append(tok)
            continue
        if run:
            joined.append("".join(run))
            run = []
        if tok:
            joined.append(tok)
    return joined


def _name_bearing(toks: list[str]) -> bool:
    return (toks[:3] == ["coming", "up", "next"] or toks[:2] == ["then", "at"]
            or toks[:1] == ["with"] or toks[:2] == ["followed", "by"]
            or toks[-1:] == ["continues"])


def _key(tok: str) -> str:
    """Metaphone key; a token with no letters (digits) keys as itself."""
    return jellyfish.metaphone(tok) or tok


def _spans(toks: list[str], name_bearing: bool) -> tuple[list[str], list[list[str]]]:
    """Template tokens in order, and the maximal runs of name tokens."""
    if not name_bearing:
        return toks, []
    template: list[str] = []
    spans: list[list[str]] = []
    run: list[str] = []
    for t in toks:
        if t in TEMPLATE_WORDS:
            template.append(t)
            if run:
                spans.append(run)
                run = []
        else:
            run.append(t)
    if run:
        spans.append(run)
    return template, spans


def _indels(a: list[str], b: list[str]) -> int:
    """Token-level insert/delete distance between two key lists."""
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b, 1):
            cur.append(prev[j - 1] + 1 if x == y else max(prev[j], cur[j - 1]))
        prev = cur
    return len(a) + len(b) - 2 * prev[-1]


def strict_problem(text: str, transcript: str, *, expect: str | None = None) -> str | None:
    """None when the transcript matches ``text`` strictly, else a reason."""
    heard = tokens(transcript)
    if not heard:
        return "nothing transcribed"
    want = tokens(text)
    if expect is not None:
        if heard != tokens(expect):
            return f"transcript differs from .expect: wanted {' '.join(tokens(expect))!r}, heard {' '.join(heard)!r}"
        return None
    bearing = bool(want) and _name_bearing(want)
    if want:
        if bearing and want[-1] not in TEMPLATE_WORDS and want[-1] != "continues":
            if _key(heard[-1]) != _key(want[-1]):
                return (f'final word "{want[-1]}" ({_key(want[-1])}) heard as '
                        f'"{heard[-1]}" ({_key(heard[-1])})')
        elif heard[-1] != want[-1]:
            return f'final word "{want[-1]}" heard as "{heard[-1]}"'
    want_t, want_s = _spans(want, bearing)
    heard_t, heard_s = _spans(heard, bearing)
    if want_t != heard_t:
        return f"template words differ: wanted {' '.join(want_t)!r}, heard {' '.join(heard_t)!r}"
    if len(want_s) != len(heard_s):
        return (f"names: name spans differ in number: wanted {len(want_s)}, heard {len(heard_s)} "
                f"(wanted {[' '.join(x) for x in want_s]}, heard {[' '.join(x) for x in heard_s]})")
    edits = 0
    for w, h in zip(want_s, heard_s):
        if _key(w[-1]) != _key(h[-1]):
            return (f'names: last word "{w[-1]}" ({_key(w[-1])}) heard as '
                    f'"{h[-1]}" ({_key(h[-1])}) in {" ".join(w)!r} vs {" ".join(h)!r}')
        edits += _indels([_key(t) for t in w[:-1]], [_key(t) for t in h[:-1]])
    if edits > NAME_EDITS:
        return (f"names differ by {edits} token edits by key: wanted "
                f"{[' '.join(x) for x in want_s]}, heard {[' '.join(x) for x in heard_s]}")
    return None
