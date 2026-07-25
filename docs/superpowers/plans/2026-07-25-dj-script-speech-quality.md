# DJ Script & Spoken-Text Quality Pass — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four TTS-facing DJ-script defects (symbol read-aloud, garbling short sentences, missing show ID mid-broadcast, mispronounced names) without degrading the human-readable script.

**Architecture:** A deterministic `normalize_for_speech(text, lexicon)` pass is applied **only** to the string handed to `speech.synthesize()` — expanding mis-voiced symbols and applying a curated, user-extensible pronunciation lexicon. The human-facing `dj-notes.md`/`dj-notes.json` are untouched. Two of the four fixes (short sentences, show-ID-every-break) are pure prompt edits.

**Tech Stack:** Python 3.14, pytest, stdlib `csv`/`re`/`importlib.resources` (no new dependencies). Existing TTS layer (`src/llama/tts/`), package stage (`src/llama/stages/package.py`), pipeline (`src/llama/pipeline.py`).

## Global Constraints

- **No new dependencies.** Everything here uses the stdlib. (Bed music, which would add `numpy`, is a *separate* deferred spec — not in this plan.)
- **Spoken-only normalization.** `normalize_for_speech` is applied exclusively to text passed into `speech.synthesize()`. `dj-notes.md`, `dj-notes.json`, `manifest.json`, and `mentioned_songs` must never be normalized.
- **No SSML, no LLM-emitted phonetics, no per-backend lexicon columns, no bed music, no ElevenLabs pronunciation-dictionary API.** All are explicit non-goals (see spec).
- **Lexicon tuned for the default backend (Voxtral).** Document, don't solve, backend-specificity.
- **Vendored data pattern:** the baked-in seed CSV loads via `importlib.resources.files("llama.data")`, mirroring `jerrybase.py`'s `set_breaks.csv`. Absence/malformed input must warn and continue, never raise.
- **Cache key uses the normalized (spoken) text**, so editing the lexicon or a symbol rule auto-invalidates exactly the affected clips on `redo --from package`; clean segments keep their existing cache.
- **Tests:** offline, deterministic, `fake` backends only. `pytest -q` must stay green.

Spec: `docs/superpowers/specs/2026-07-25-dj-script-speech-quality-design.md`

## File Structure

- **Create** `src/llama/speech_text.py` — the `Lexicon` type, `normalize_for_speech`, and `load_lexicon`. One responsibility: turn written DJ prose into TTS-ready spoken text.
- **Create** `src/llama/data/pronunciations.csv` — the baked-in seed lexicon (vendored data, next to `set_breaks.csv`).
- **Create** `tests/test_speech_text.py` — unit tests for the normalizer and lexicon loading.
- **Modify** `src/llama/stages/package.py` — thread a `lexicon` through `run_package` → `_synthesize_dj_audio`; normalize each segment before hashing and synthesis.
- **Modify** `src/llama/pipeline.py` — build the lexicon from `run_ws.root` and pass it into `run_package`.
- **Modify** `src/llama/prompts/synthesize.md` — the three prompt-level rules.
- **Modify** `tests/test_stage_package.py` — package-level normalization + human-script-untouched tests.
- **Modify** `tests/test_prompts.py` — assert the new prompt guidance.

---

### Task 1: The spoken-text normalizer (`speech_text.py`)

Symbol expansion + a `Lexicon` type that respells whole words/phrases. No file loading yet (Task 2).

**Files:**
- Create: `src/llama/speech_text.py`
- Test: `tests/test_speech_text.py`

**Interfaces:**
- Consumes: nothing (stdlib only).
- Produces:
  - `class Lexicon` with `__init__(self, entries: dict[str, str])`, classmethod `empty() -> Lexicon`, and `apply(self, text: str) -> str`.
  - `normalize_for_speech(text: str, lexicon: Lexicon) -> str`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_speech_text.py`:

```python
from llama.speech_text import Lexicon, normalize_for_speech


def test_expands_greater_than_segue_to_into():
    # A literal setlist segue leaking into prose must not be read "greater than".
    out = normalize_for_speech("Help on the Way > Slipknot", Lexicon.empty())
    assert ">" not in out
    assert "Help on the Way into Slipknot" == out


def test_expands_ampersand_and_percent():
    assert normalize_for_speech("Jerry & Bob", Lexicon.empty()) == "Jerry and Bob"
    assert normalize_for_speech("100% live", Lexicon.empty()) == "100 percent live"


def test_clean_prose_is_unchanged():
    # Identity on ordinary text — so unaffected cache keys don't churn.
    text = "Good evening, night owls. It's June 10th, 1973."
    assert normalize_for_speech(text, Lexicon.empty()) == text


def test_lexicon_respells_whole_word_case_insensitively():
    lex = Lexicon({"Sugaree": "Shugaree"})
    assert normalize_for_speech("They opened with Sugaree tonight.", lex) == \
        "They opened with Shugaree tonight."
    assert normalize_for_speech("sugaree", lex) == "Shugaree"


def test_lexicon_does_not_match_inside_other_words():
    lex = Lexicon({"Weir": "Weer"})
    # "weird" must not become "Weerd".
    assert normalize_for_speech("that weird jam", lex) == "that weird jam"


def test_lexicon_prefers_longest_phrase():
    lex = Lexicon({"Way": "Wayy", "Help on the Way": "Help on the Wave"})
    assert normalize_for_speech("Help on the Way", lex) == "Help on the Wave"


def test_symbols_then_lexicon_and_whitespace_tidied():
    lex = Lexicon({"Mydland": "Midland"})
    assert normalize_for_speech("Brent Mydland  &   the band", lex) == \
        "Brent Midland and the band"


def test_empty_lexicon_apply_is_identity():
    assert Lexicon.empty().apply("nothing to do here") == "nothing to do here"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_speech_text.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'llama.speech_text'`.

- [ ] **Step 3: Write the implementation**

Create `src/llama/speech_text.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_speech_text.py -q`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add src/llama/speech_text.py tests/test_speech_text.py
git commit -m "feat: normalize_for_speech — symbol expansion + pronunciation lexicon"
```

---

### Task 2: Lexicon loading — baked-in seed + workspace overlay

`load_lexicon(root)` reads the vendored seed CSV and an optional workspace overlay that overrides/adds entries. Malformed input warns and is skipped.

**Files:**
- Create: `src/llama/data/pronunciations.csv`
- Modify: `src/llama/speech_text.py` (add `load_lexicon`)
- Test: `tests/test_speech_text.py` (add loading tests)

**Interfaces:**
- Consumes: `Lexicon` (Task 1).
- Produces: `load_lexicon(root: Path | None = None) -> Lexicon`. `root` is the workspace root (e.g. `~/.llama`); the overlay is `<root>/pronunciations.csv`. `root=None` → baked-in seed only.

- [ ] **Step 1: Create the seed CSV**

Create `src/llama/data/pronunciations.csv` (only pronunciations confirmed by the owner — more come via the workspace overlay; do not guess respellings):

```csv
written,spoken,note
Sugaree,Shugaree,sugar sh-sound not soon-s
Mydland,Midland,Brent Mydland keyboardist
```

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_speech_text.py`:

```python
from pathlib import Path

from llama.speech_text import load_lexicon, normalize_for_speech


def test_load_lexicon_includes_baked_in_seed():
    lex = load_lexicon()
    # Seeded, owner-confirmed entries.
    assert normalize_for_speech("Sugaree", lex) == "Shugaree"
    assert normalize_for_speech("Mydland", lex) == "Midland"


def test_workspace_overlay_adds_and_overrides(tmp_path: Path):
    (tmp_path / "pronunciations.csv").write_text(
        "written,spoken,note\n"
        "Sugaree,Sugar-ee,override the seed\n"
        "Pigpen,Pig Pen,new entry\n"
    )
    lex = load_lexicon(tmp_path)
    assert normalize_for_speech("Sugaree", lex) == "Sugar-ee"   # overlay wins
    assert normalize_for_speech("Pigpen", lex) == "Pig Pen"     # added
    assert normalize_for_speech("Mydland", lex) == "Midland"    # seed still present


def test_missing_overlay_is_fine(tmp_path: Path):
    lex = load_lexicon(tmp_path)  # no pronunciations.csv in tmp_path
    assert normalize_for_speech("Sugaree", lex) == "Shugaree"


def test_malformed_overlay_is_ignored_not_raised(tmp_path: Path, caplog):
    # A row missing the spoken column is skipped; a totally broken file warns.
    (tmp_path / "pronunciations.csv").write_text("this is not,valid\ncsv at all")
    lex = load_lexicon(tmp_path)  # must not raise
    assert normalize_for_speech("Sugaree", lex) == "Shugaree"  # seed intact
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/test_speech_text.py -k lexicon -q`
Expected: FAIL with `ImportError: cannot import name 'load_lexicon'`.

- [ ] **Step 4: Write the implementation**

Add to `src/llama/speech_text.py` (imports at top, function at bottom):

```python
import csv
import logging
from importlib import resources
from pathlib import Path

log = logging.getLogger(__name__)
```

```python
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
    (llama.data/pronunciations.csv) plus, if present, a workspace overlay at
    <root>/pronunciations.csv whose entries add to and override the seed.
    Malformed or unreadable sources are warned about and skipped — loading the
    lexicon must never raise (mirrors jerrybase._load)."""
    entries: dict[str, str] = {}
    try:
        with resources.files("llama.data").joinpath("pronunciations.csv").open(
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
```

Also confirm the package data ships: `pyproject.toml`'s wheel target already packages `src/llama` (so `llama/data/*.csv` is included, same as `set_breaks.csv`). No change needed — verify by inspection.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_speech_text.py -q`
Expected: PASS (all Task 1 + Task 2 tests).

- [ ] **Step 6: Commit**

```bash
git add src/llama/speech_text.py src/llama/data/pronunciations.csv tests/test_speech_text.py
git commit -m "feat: load_lexicon — baked-in seed + workspace overlay"
```

---

### Task 3: Wire the normalizer into the package stage

Normalize each DJ segment before hashing and synthesis; thread a `lexicon` through `run_package` → `_synthesize_dj_audio`, and build it from the workspace root in `process_show`.

**Files:**
- Modify: `src/llama/stages/package.py`
- Modify: `src/llama/pipeline.py:116`
- Test: `tests/test_stage_package.py`

**Interfaces:**
- Consumes: `normalize_for_speech`, `Lexicon`, `load_lexicon` (Tasks 1–2); `run_ws.root` (`RunWorkspace.root`, an existing attribute).
- Produces: `run_package(..., lexicon: Lexicon | None = None)` and `_synthesize_dj_audio(..., lexicon: Lexicon | None = None)`. `None` → `Lexicon.empty()` (symbols still expand; no respellings).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_stage_package.py` (reuse the file's existing `make_show`/`StubIA`; `make_notes()` there builds `DJNotes` — these tests build notes with symbol/lexicon-bearing text). Import at top of the test file: `from llama.models import DJNotes`, `from llama.speech_text import Lexicon`.

```python
def _notes_with(text: str) -> DJNotes:
    # One set-1 lead-in carrying the text under test, plus a plain outro.
    return DJNotes(context="", set_intros={"1": text}, outro="Goodnight.",
                   mentioned_songs=[])


def test_package_expands_segue_symbol_before_synthesis(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    show = make_show()
    speech = FakeSpeechProvider()
    run_package(sws, StubIA(), show, _notes_with("We go Help on the Way > Slipknot now."),
                speech=speech)
    spoken = " ".join(speech.calls)
    assert ">" not in spoken
    assert "Help on the Way into Slipknot" in spoken


def test_package_applies_pronunciation_lexicon(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    show = make_show()
    speech = FakeSpeechProvider()
    run_package(sws, StubIA(), show, _notes_with("They opened with Sugaree."),
                speech=speech, lexicon=Lexicon({"Sugaree": "Shugaree"}))
    assert any("Shugaree" in c for c in speech.calls)
    assert not any("Sugaree" in c and "Shugaree" not in c for c in speech.calls)


def test_package_leaves_human_notes_unnormalized(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    # A human-readable dj-notes.md already on disk (as synthesize would write).
    write_artifact(sws.dj_notes_md, "## Set 1 lead-in\nHelp on the Way > Slipknot\n")
    show = make_show()
    pkg = run_package(sws, StubIA(), show, _notes_with("Help on the Way > Slipknot"),
                      speech=FakeSpeechProvider())
    # The packaged human script keeps the readable ">" form — only audio changed.
    assert ">" in (pkg / "dj-notes.md").read_text()


def test_package_normalization_changes_only_affected_cache_key(tmp_path: Path):
    # A clean segment keeps its cache across runs (normalize is identity on it).
    sws = ShowWorkspace(tmp_path / "s")
    show = make_show()
    run_package(sws, StubIA(), show, _notes_with("A perfectly clean lead-in here."),
                speech=FakeSpeechProvider())
    second = FakeSpeechProvider()
    run_package(sws, StubIA(), show, _notes_with("A perfectly clean lead-in here."),
                speech=second)
    assert second.calls == []  # nothing re-synthesized
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_stage_package.py -k "segue or lexicon or unnormalized or affected_cache" -q`
Expected: FAIL — `run_package()` got an unexpected keyword `lexicon` (and/or `>` still present in `speech.calls`).

- [ ] **Step 3: Implement in `package.py`**

Add the import near the top of `src/llama/stages/package.py`:

```python
from llama.speech_text import Lexicon, normalize_for_speech
```

Change `_synthesize_dj_audio` (currently `package.py:143`) to accept and apply the lexicon. Replace its signature and the per-segment body:

```python
def _synthesize_dj_audio(pkg: Path, notes: DJNotes, speech, force: bool,
                         chunk: bool = False, lexicon: Lexicon | None = None) -> DJAudio:
```

Inside, immediately after `lexicon` is available (top of the function body, before the loop):

```python
    lexicon = lexicon or Lexicon.empty()
```

Within the `for stem, text in _segment_texts(notes):` loop, normalize once and use the spoken form for BOTH the cache key and synthesis (this also satisfies "normalize before the chunker splits", since `_synthesize_chunked` now receives already-normalized text):

```python
    for stem, text in _segment_texts(notes):
        spoken = normalize_for_speech(text, lexicon)
        filename = f"{stem}.mp3"
        dest = audio_dir / filename
        key = hashlib.sha256(
            f"{spoken}\n{speech.voice}\n{speech.model}\nchunk={chunk}".encode()).hexdigest()
        keys[filename] = key
        if force or not dest.exists() or cached.get(filename) != key:
            detail(f"synthesizing {filename}")
            data = _synthesize_chunked(spoken, speech) if chunk else speech.synthesize(spoken)
            tmp = dest.with_name(dest.name + ".part")
            tmp.write_bytes(data)
            tmp.replace(dest)
```

Thread `lexicon` through `run_package` (currently `package.py:189`). Update its signature:

```python
def run_package(show_ws: ShowWorkspace, ia, show: Show, notes: DJNotes | None = None,
                force: bool = False, speech=None, chunk: bool = False,
                lexicon: Lexicon | None = None) -> Path:
```

And the call inside it (currently `package.py:244`):

```python
        dj_audio = _synthesize_dj_audio(pkg, notes, speech, force, chunk=chunk, lexicon=lexicon)
```

- [ ] **Step 4: Build and pass the lexicon in `pipeline.py`**

At the top of `src/llama/pipeline.py`, add:

```python
from llama.speech_text import load_lexicon
```

In `process_show`, replace the packaging call (currently `pipeline.py:116`):

```python
    with step(f"[{pid}] packaging"):
        lexicon = load_lexicon(run_ws.root)
        pkg = run_package(show_ws, ia, show, notes, force=force, speech=speech,
                          chunk=chunk, lexicon=lexicon)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_stage_package.py tests/test_chunk.py -q`
Expected: PASS (new tests + all existing package/chunk tests — clean prose keeps its cache key, so the existing cache tests are unaffected).

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`
Expected: PASS (no regressions).

- [ ] **Step 7: Commit**

```bash
git add src/llama/stages/package.py src/llama/pipeline.py tests/test_stage_package.py
git commit -m "feat: normalize DJ segments for speech in the package stage"
```

---

### Task 4: Prompt edits — no-symbol segues, no short sentences, show ID every break

Pure prompt-quality fixes for points 1 (generation side), 2, and 3.

**Files:**
- Modify: `src/llama/prompts/synthesize.md`
- Test: `tests/test_prompts.py`

**Interfaces:**
- Consumes: nothing. Produces: no code symbols — the template's placeholder set is unchanged (`style`, `show_json`, `research`, `reviews_digest`, `lead_in_sets`, `encore_note`, `feedback`), so `test_prompt_loads_with_placeholders` still passes.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_prompts.py`:

```python
def test_synthesize_prompt_forbids_symbol_segues():
    text = load_prompt("synthesize")
    low = text.lower()
    assert '"into"' in low or "the word into" in low
    assert "greater than" in low  # explains WHY not to use ">"


def test_synthesize_prompt_bans_very_short_sentences():
    assert "short sentence" in load_prompt("synthesize").lower()


def test_synthesize_prompt_requires_show_id_every_break():
    # Every break must re-state artist + date + venue/city for mid-show tune-ins.
    low = load_prompt("synthesize").lower()
    assert "artist, date, venue" in low
    assert "tuning in" in low or "mid-" in low
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_prompts.py -q`
Expected: FAIL on the three new assertions (strings not yet in the prompt).

- [ ] **Step 3: Edit `src/llama/prompts/synthesize.md`**

Insert a rules block after the existing "Write for the ear" paragraph (after line 9, before the blank line preceding `Show data (JSON):`):

```markdown

Three hard rules for spoken delivery:
- Segues in words, never symbols: say one song goes "into" the next — never
  write ">" (the voice reads it as "greater than"), and spell out "and" for
  "&". No symbols in the prose at all.
- No very short sentences: never a one- or two-word sentence (a bare "Here's
  set two." makes the voice garble). Fold short lines into fuller ones.
- Show ID in every break: every lead-in AND the outro must re-state the show's
  identity — artist, date, venue and/or city — at least once, so a listener
  tuning in mid-broadcast learns what they are hearing.
```

Then update the `set_intros` value description (line 28) so later-set lead-ins carry the show ID too. Replace the parenthetical describing each LATER set's lead-in with:

```markdown
Each LATER set's lead-in briefly recaps the set just played, then teases this one (~30-45 seconds), and — like every break — re-states the show's identity (artist, date, venue and/or city) for anyone just tuning in
```

And update the `outro` description (line 29) to end with `; re-state the show's identity (artist, date, venue and/or city) once more` before the closing quote.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_prompts.py -q`
Expected: PASS (new + existing, including `test_synthesize_prompt_guides_spoken_stress` and the placeholder test).

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/llama/prompts/synthesize.md tests/test_prompts.py
git commit -m "feat: DJ prompt — no-symbol segues, no short sentences, show ID every break"
```

---

## Self-Review

**Spec coverage:**
- Point 1 (`>` → "greater than"): Task 1 (symbol expansion, guaranteed) + Task 4 (prompt, reduces frequency). ✓
- Point 2 (short sentences): Task 4 prompt rule. ✓ (The existing chunker fold in `package.py` remains as a secondary net; unchanged.)
- Point 3 (show ID every break): Task 4 prompt edits to the rules block, `set_intros`, and `outro`. Prompt-only per decision. ✓
- Point 4 (pronunciation): Tasks 1–3 (lexicon + spoken-only application). Seed `Sugaree→Shugaree`, `Mydland→Midland`; user-extensible overlay. ✓
- Spoken-only guarantee: Task 3 `test_package_leaves_human_notes_unnormalized`. ✓
- Cache-key uses normalized text: Task 3 implementation + `test_package_normalization_changes_only_affected_cache_key`. ✓
- Non-goals (bed music, SSML, ElevenLabs dict, LLM phonetics, per-backend columns): excluded; stated in Global Constraints. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases"; every code step shows complete code. ✓

**Type consistency:** `Lexicon` / `Lexicon.empty()` / `Lexicon({...})` / `.apply()`, `normalize_for_speech(text, lexicon)`, `load_lexicon(root)`, `run_package(..., lexicon=...)`, `_synthesize_dj_audio(..., lexicon=...)` — names and signatures consistent across Tasks 1–3. `RunWorkspace.root` confirmed to exist (`workspace.py:86`). ✓
