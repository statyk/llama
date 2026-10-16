# emcee profile reassignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the operator move delivered shows between profiles (artist rules in config, one-off moves in `moves.json`), record in each voiced manifest which profile and TTS voiced it, make a profile change a readiness failure, and put a printed plan plus a confirmation in front of every `emcee run` spend.

**Architecture:** One pure resolver, `station.effective_profile(config, moves, manifest)`, decides the profile (move > artist rule > llama's). Config and `moves.json` are loaded once per command and passed explicitly into the scan, the plan and voicing; readiness gains a fifth leg comparing the recorded voiced profile with the effective one. Voicing resolves effective profile, presenter, title and TTS exactly once per package (`process.resolve_voicing`) and passes that `Voicing` into `process_package`, which writes the new `DJAudioBlock` fields. `emcee run` classifies pending packages into a plan (new / re-voice / repair / skip), prints it on stderr and asks before any spend.

**Tech Stack:** Python 3.11+, typer (CliRunner in tests), pydantic v2, `fcntl.flock`, pytest. All tests offline on the `fake` LLM (`herder.FakeProvider`) and `fake` TTS backends.

**Spec:** `docs/superpowers/specs/2026-10-16-emcee-profile-reassignment-design.md` (approved, authoritative). Every implementer reads the spec section their task names, plus this task.

## Execution setup (orchestrator, once, before Task 1)

- Worktree: `/Users/shawn/projects/llama/.claude/worktrees/emcee-profile-reassignment` on a new branch `emcee-profile-reassignment` from `main`.
- Its own venv, from the worktree root:
  `python3 -m venv .venv && ./.venv/bin/pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"`
- Check it imports the worktree: `./.venv/bin/python -c "import emcee; print(emcee.__file__)"` must print a path inside the worktree.
- **Always** run tests as `./.venv/bin/python -m pytest ...` from the worktree root, never a bare `pytest` and never `.venv/bin/pytest` (CLAUDE.md: the root `.venv` imports the main checkout).
- Baseline before Task 1: `./.venv/bin/python -m pytest packages/emcee -q` → `727 passed, 1 deselected`. Full suite: `./.venv/bin/python -m pytest -q` (record the count).

## Global Constraints

- emcee never imports llama (`packages/emcee/tests/test_no_llama_imports.py`); the moves lock is a copy of `packages/llama/src/llama/locks.py`'s `file_lock` pattern, not an import.
- Every new emcee config model inherits `emcee.config._StrictModel` (`extra="forbid"`).
- No function in the profile-resolution path takes `moves` as an optional or defaulted parameter (spec §1). Test helpers pass `no_moves()` explicitly.
- `moves.json` lives at `<config.root>/moves.json`; the lock at `<config.root>/moves.json.lock`. Writes: unique temp + `fsync` + `os.replace`. `--clear` never deletes the file (last clear leaves `{}`).
- llama's profile is always read through `station.manifest_profile` (maps `""` and non-strings to `None`).
- Strict surfaces (spec "Stakes"), each pinned by tests in its owning task: (1) no LLM/TTS call in `emcee run` before the plan is printed and confirmed (Task 7); (2) an unreadable/malformed `moves.json` is a hard error, and a missing one is a hard error while any package records `profile_source: "move"` (Tasks 2, 4, 5, 6); (3) with no rules and no moves every package ready today stays ready (Task 4).
- Message texts are verbatim from the spec where it gives them:
  - readiness: `voiced as {a}, now {b} (artist rule "{key}")`, `voiced as {a}, now {b} (move)`, `voiced as {a}, now {b} (move no longer recorded)`, `voiced as {a}, now {b} (delivered profile; no rule or move applies)`; a `None` profile renders `(none)`.
  - use-time: `move target "{p}" has no [assign.profiles] entry`
  - run: `skip {slug}: {n} audio file(s) missing; re-deliver from llama`, `error: refusing to voice without confirmation; pass --yes`, `nothing voiced`, `note: {n} recorded move(s) match no package (emcee move --list)`, prompt `Proceed?` (rendered `Proceed? [y/N]:`).
  - move: `moved: {slug}  {before} -> {after} ({state})` with states `pending; voiced on the next emcee run`, `ready; already voiced as {p}`, `unvoiced; voiced as {p} on the next emcee run`.
- The plan and the prompt go to **stderr**; per-package `voiced:`/`skip`/`would voice:` rows stay where they are today.
- Tests are offline and deterministic; never commit audio. CliRunner has no TTY: interactive tests patch `emcee.cli._stdin_is_tty`.
- Each task ends with the full suite green: `./.venv/bin/python -m pytest -q` from the worktree root.
- Commits: one per task as shown; end each commit message with the attribution trailer the orchestrating session specifies.

## Review Focus

Inputs the spec implies but does not test directly; each has a test in the owning task:

1. **A package whose `show.artist` is missing or not a string, under an artist rule.** Expected: it resolves to llama's profile and nothing raises. Test: Task 3 `test_artist_missing_or_not_a_string_falls_to_llama`.
2. **A hand-edited `moves.json` entry with `"profile": ""`.** `manifest_profile` maps `""` to `None`, so an empty-string target would never compare equal and would re-voice every run. Expected: a hard load error naming the file. Test: Task 2 `test_a_malformed_file_is_a_hard_error_naming_it` (the `""` case).
3. **EOF (Ctrl-D) at the `Proceed?` prompt.** Expected: nothing voiced, no spend, non-zero exit. Test: Task 7 `test_eof_at_the_prompt_spends_nothing`.
4. **A planned presenter whose `presenters/<id>.toml` is missing.** Expected: the plan still prints, and its TTS line carries `[missing presenters/<id>.toml]`. Test: Task 7 `test_the_plan_marks_a_presenter_that_cannot_be_loaded`.
5. **Two delivered packages sharing one `performance_id`** (a duplicate delivery). Expected: one move applies to both, neither counts as stale, and `move --list` does not say `missing`. Test: Task 8 `test_two_packages_sharing_a_performance_id_both_follow_one_move`.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `packages/emcee/src/emcee/artists.py` | create (T1) | `normalize_artist`, pure, imports nothing from emcee |
| `packages/emcee/src/emcee/config.py` | modify (T1) | `ArtistRule`, `AssignConfig.artists` + load-time validation, template comment |
| `packages/emcee/src/emcee/moves.py` | create (T2) | `Moves`, `load_moves`, `read_moves_data`, `moves_lock`, `write_moves`, `record_move`, `clear_move` |
| `packages/emcee/src/emcee/station.py` | modify (T3, T4) | manifest accessors, `Effective`, `effective_profile`, move validation (T3); `assess`/`readiness` fifth leg, `PackageStatus` fields, `scan(root, config, moves)` (T4) |
| `packages/emcee/src/emcee/cli.py` | modify (T4–T8) | `_load_station`, scan threading (T4); `_process_one`/`voice` (T5); `move` command (T6); `run` plan/pause (T7); `status` surfaces (T8) |
| `packages/emcee/src/emcee/models.py` | modify (T5) | `DJClips`, `TTSRecord`, `DJAudioBlock` required fields |
| `packages/emcee/src/emcee/audio.py` | modify (T5) | `_synthesize_dj_audio` returns `DJClips` |
| `packages/emcee/src/emcee/process.py` | modify (T5) | `Voicing`, `resolve_voicing`, `speech_for_voicing`, `resolve_assignment(config, profile)`, `process_package(..., *, voicing)` |
| `scripts/backfill_voiced_by.py` | modify (T5) | raw-dict update instead of a model round trip |
| `packages/emcee/tests/helpers.py` | modify (T2, T4, T5) | `no_moves`, `moves_of` (T2); `artist=` kwarg, `set_dj_audio`, `write_moves_file` (T4); `voicing_for` (T5) |
| `packages/emcee/tests/test_artists.py` | create (T1) | |
| `packages/emcee/tests/test_moves.py` | create (T2) | |
| `packages/emcee/tests/test_effective.py` | create (T3) | |
| `packages/emcee/tests/test_profile_readiness.py` | create (T4) | |
| `packages/emcee/tests/test_recording.py` | create (T5) | |
| `packages/emcee/tests/test_move_cmd.py` | create (T6) | |
| `packages/emcee/tests/test_run_plan.py` | create (T7) | |
| `packages/emcee/tests/test_status_profiles.py` | create (T8) | |
| `packages/llama/src/llama/models.py` | modify (T9) | `DJAudio` documentation copy gains optional fields |
| `packages/transmitter/src/transmitter/station.py` | modify (T9) | module docstring only |
| `CLAUDE.md`, `README.md`, `docs/station-brief.md`, `docs/playout-incident-runbook.md` | modify (T9) | docs |

## Task list and suggested implementer models

| # | Task | Implementer |
|---|---|---|
| 1 | `normalize_artist` + `[assign.artists]` config | Sonnet |
| 2 | `moves.py`: strict load, lock, write, record, clear | Sonnet |
| 3 | `effective_profile` + move-target validation (pure) | Sonnet |
| 4 | Readiness fifth leg + scan/status threading of config and moves (strict surfaces 2 and 3) | **Opus**: it touches every scan reader, and a wrong field breaks strict surface 3 |
| 5 | One resolution per package + recording `profile`/`profile_source`/`tts` | **Opus**: a refactor across process/cli/audio/models with about 40 test call sites |
| 6 | `emcee move` CLI | Sonnet (escalate to Opus on a BLOCKED-for-reasoning status) |
| 7 | `emcee run` plan and pause (strict surface 1) | **Opus**: it rewrites `run`'s control flow and exit codes |
| 8 | `emcee status` surfaces for effective profiles | Sonnet |
| 9 | Docs, llama `DJAudio` doc model, transmitter docstring, runbook note | Sonnet |

---

### Task 1: `normalize_artist` and `[assign.artists]` config

Spec: §2 "Artist rules (A)".

**Files:**
- Create: `packages/emcee/src/emcee/artists.py`
- Modify: `packages/emcee/src/emcee/config.py` (`AssignConfig` at lines 140-147; `DEFAULT_CONFIG_TOML`, end of file)
- Create: `packages/emcee/tests/test_artists.py`
- Modify: `packages/emcee/tests/test_config.py` (`test_default_config_template_mentions_every_section`, plus new tests at the end)

**Interfaces:**
- Consumes: `emcee.config._StrictModel`, `Assignment`.
- Produces:
  - `emcee.artists.normalize_artist(name: str) -> str`
  - `emcee.config.ArtistRule(_StrictModel)`: `profile: str`, `from_: list[str] | None` (TOML key `from`; `populate_by_name=True`)
  - `emcee.config.AssignConfig.artists: dict[str, ArtistRule]` (default `{}`; a string value is shorthand for `{profile = ...}`)

- [ ] **Step 1: Write the failing tests**

`packages/emcee/tests/test_artists.py`:

```python
"""normalize_artist: the loose artist-name key for [assign.artists] (spec section 2)."""

import pytest

from emcee.artists import normalize_artist


@pytest.mark.parametrize("a, b", [
    ("Karl Denson's Tiny Universe", "Karl Densons Tiny Universe"),
    ("Karl Denson’s Tiny Universe", "Karl Densons Tiny Universe"),
    ("Robert Randolph [and the Family Band]", "Robert Randolph"),
    ("Robert Walter's 20th Congress", "Robert Walters 20th Congress"),
    ("JJ Grey & MOFRO", "JJ Grey and MOFRO"),
    ("The Motet", "Motet"),
    ("TEDESCHI TRUCKS BAND", "Tedeschi Trucks Band"),
    ("  Lettuce!! ", "Lettuce"),
])
def test_spelling_variants_meet(a, b):
    assert normalize_artist(a) == normalize_artist(b)


@pytest.mark.parametrize("a, b", [
    ("Robert Randolph", "Robert Walter's 20th Congress"),
    ("Soulive", "Lettuce"),
    ("Theory of a Deadman", "Ory of a Deadman"),
])
def test_different_artists_stay_different(a, b):
    assert normalize_artist(a) != normalize_artist(b)


def test_each_rule_in_order():
    assert normalize_artist("Béla Fleck") == "béla fleck"      # unicode letters kept
    assert normalize_artist("A [x] [y]") == "a x"                       # only ONE trailing group dropped
    assert normalize_artist("Tom & Jerry") == "tom and jerry"
    assert normalize_artist("The Band") == "band"                       # leading "the " dropped
    assert normalize_artist("Theory of a Deadman") == "theory of a deadman"
    assert normalize_artist("Ween/Phish-ish") == "ween phish ish"


@pytest.mark.parametrize("name", ["[Family Band]", "!!!", "   "])
def test_names_that_normalize_to_nothing(name):
    assert normalize_artist(name) == ""
```

Append to `packages/emcee/tests/test_config.py`:

```python
# --- [assign.artists] (2026-10-16 profile reassignment, spec section 2) ---

from emcee.config import ArtistRule

_SOUTHERN = '[assign.profiles.southern]\npresenter = "gregg"\n\n'


def test_artist_shorthand_and_table_forms_parse_the_same(tmp_path: Path):
    short = _load(tmp_path, _SOUTHERN + '[assign.artists]\n"Tedeschi Trucks Band" = "southern"\n')
    table = _load(tmp_path, _SOUTHERN + '[assign.artists]\n'
                  '"Tedeschi Trucks Band" = { profile = "southern" }\n')
    assert short.assign.artists == table.assign.artists
    assert short.assign.artists["Tedeschi Trucks Band"] == ArtistRule(profile="southern")
    assert short.assign.artists["Tedeschi Trucks Band"].from_ is None


def test_artist_rule_from_list_parses(tmp_path: Path):
    cfg = _load(tmp_path, _SOUTHERN + '[assign.artists]\n'
                '"JJ Grey and MOFRO" = { profile = "southern", from = ["funk"] }\n')
    assert cfg.assign.artists["JJ Grey and MOFRO"].from_ == ["funk"]


def test_artists_default_empty():
    assert EmceeConfig().assign.artists == {}


def test_artist_rule_targeting_a_profile_without_an_entry_is_a_load_error(tmp_path: Path):
    with pytest.raises(ConfigError) as exc:
        _load(tmp_path, '[assign.artists]\n"Tedeschi Trucks Band" = "southern"\n')
    assert '"Tedeschi Trucks Band"' in str(exc.value)
    assert "[assign.profiles.southern]" in str(exc.value)


def test_two_artist_keys_normalizing_alike_is_a_load_error_naming_both(tmp_path: Path):
    with pytest.raises(ConfigError) as exc:
        _load(tmp_path, _SOUTHERN + '[assign.artists]\n'
              '"Karl Denson\'s Tiny Universe" = "southern"\n'
              '"Karl Densons Tiny Universe" = "southern"\n')
    assert "Karl Denson's Tiny Universe" in str(exc.value)
    assert "Karl Densons Tiny Universe" in str(exc.value)


def test_artist_key_normalizing_to_empty_is_a_load_error(tmp_path: Path):
    with pytest.raises(ConfigError) as exc:
        _load(tmp_path, _SOUTHERN + '[assign.artists]\n"!!!" = "southern"\n')
    assert "empty artist name" in str(exc.value)


def test_empty_from_list_is_a_load_error(tmp_path: Path):
    with pytest.raises(ConfigError) as exc:
        _load(tmp_path, _SOUTHERN + '[assign.artists]\n'
              '"Lettuce" = { profile = "southern", from = [] }\n')
    assert "can never match" in str(exc.value)


def test_unknown_key_in_an_artist_rule_is_a_load_error(tmp_path: Path):
    with pytest.raises(ConfigError):
        _load(tmp_path, _SOUTHERN + '[assign.artists]\n'
              '"Lettuce" = { profile = "southern", form = ["funk"] }\n')
```

In `test_default_config_template_mentions_every_section`, add `"[assign.artists]"` to the marker tuple.

- [ ] **Step 2: Run the tests and watch them fail**

Run: `./.venv/bin/python -m pytest packages/emcee/tests/test_artists.py packages/emcee/tests/test_config.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'emcee.artists'`; once that module exists, the config tests fail with `ImportError: cannot import name 'ArtistRule'`.

- [ ] **Step 3: Implement**

`packages/emcee/src/emcee/artists.py`:

```python
"""Loose artist-name matching for `[assign.artists]` rules (spec section 2).

Pure and dependency-free: config validation and the effective-profile
resolver both use it, so it imports nothing from emcee.
"""

import re

_TRAILING_BRACKET = re.compile(r"\[[^\[\]]*\]\s*$")
_APOSTROPHES = ("'", "’")


def normalize_artist(name: str) -> str:
    """The comparison key for an artist name. In order: casefold; drop one
    trailing `[...]` group; `&` -> ` and `; delete apostrophes (`'` and the
    right single quote); replace every other character that is not a
    Unicode letter or digit with a space; collapse whitespace and strip;
    drop a leading `the `.

    "Karl Denson's Tiny Universe" meets "Karl Densons Tiny Universe";
    "Robert Randolph [and the Family Band]" meets "Robert Randolph";
    "Béla Fleck" keeps its é."""
    s = name.casefold()
    s = _TRAILING_BRACKET.sub("", s.rstrip(), count=1)
    s = s.replace("&", " and ")
    for mark in _APOSTROPHES:
        s = s.replace(mark, "")
    s = "".join(ch if (ch.isalpha() or ch.isdigit()) else " " for ch in s)
    s = " ".join(s.split())
    if s.startswith("the "):
        s = s[4:]
    return s
```

In `packages/emcee/src/emcee/config.py`: change the pydantic import to `from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator`, add `from emcee.artists import normalize_artist` below `from emcee.errors import ConfigError`, and replace `class AssignConfig` with:

```python
class ArtistRule(_StrictModel):
    """One `[assign.artists]` rule: voice this artist's shows as `profile`,
    whatever profile llama delivered them under -- or, with `from`, only
    when llama's profile is one of those listed."""
    model_config = ConfigDict(populate_by_name=True)

    profile: str
    from_: list[str] | None = Field(default=None, alias="from")


class AssignConfig(_StrictModel):
    default: str | None = None                          # station-default presenter id
    profiles: dict[str, Assignment] = Field(default_factory=dict)
    artists: dict[str, ArtistRule] = Field(default_factory=dict)

    @field_validator("artists", mode="before")
    @classmethod
    def _artist_shorthand(cls, value):
        # `"Artist" = "profile"` is shorthand for `{ profile = "profile" }`.
        if isinstance(value, dict):
            return {key: {"profile": rule} if isinstance(rule, str) else rule
                    for key, rule in value.items()}
        return value

    @model_validator(mode="after")
    def _check_artists(self):
        """A rule naming a profile with no [assign.profiles] entry would
        silently route shows to the default presenter; two keys normalizing
        alike would make the winner depend on file order; an empty key or
        an empty `from` can never match. All are load errors."""
        seen: dict[str, str] = {}
        for key, rule in self.artists.items():
            norm = normalize_artist(key)
            if not norm:
                raise ValueError(f'[assign.artists] "{key}" normalizes to an empty artist name')
            if norm in seen:
                raise ValueError(f'[assign.artists] "{seen[norm]}" and "{key}" name the same '
                                 f'artist (both normalize to "{norm}"); keep one')
            seen[norm] = key
            if rule.from_ is not None and not rule.from_:
                raise ValueError(f'[assign.artists] "{key}": from = [] can never match; '
                                 "remove it to match every delivered profile")
            if rule.profile not in self.profiles:
                raise ValueError(f'[assign.artists] "{key}" targets profile "{rule.profile}", '
                                 f"which has no [assign.profiles.{rule.profile}] entry "
                                 "(add the entry first)")
        return self
```

At the end of `DEFAULT_CONFIG_TOML` (after the `# title = "The Primal Dead Hour"` line, inside the string), append:

```
#
# Artist rules: voice every show by an artist as another profile, whatever
# profile llama delivered it under (or only from the profiles in `from`).
# Names match loosely (case, "&"/"and", apostrophes, one trailing [...], a
# leading "The"). A rule's profile needs its own [assign.profiles.<name>]
# entry: add that first, or every emcee command refuses to start.
# [assign.artists]
# "Tedeschi Trucks Band" = "southern"
# "JJ Grey and MOFRO" = { profile = "southern", from = ["funk"] }
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `./.venv/bin/python -m pytest packages/emcee/tests/test_artists.py packages/emcee/tests/test_config.py -q` → all pass.
Run: `./.venv/bin/python -m pytest -q` → green.

- [ ] **Step 5: Commit**

```bash
git add packages/emcee/src/emcee/artists.py packages/emcee/src/emcee/config.py \
        packages/emcee/tests/test_artists.py packages/emcee/tests/test_config.py
git commit -m "feat(emcee): [assign.artists] rules with loose artist-name matching"
```

---

### Task 2: `moves.py`: strict load, lock, write, record, clear

Spec: §3 "One-off moves (B)": Stored, Writing, `--clear` addressing, Loading, A missing file. Also strict surface 2.

**Files:**
- Create: `packages/emcee/src/emcee/moves.py`
- Create: `packages/emcee/tests/test_moves.py`
- Modify: `packages/emcee/tests/helpers.py` (add `no_moves`, `moves_of`)

**Interfaces:**
- Consumes: `emcee.errors.EmceeError`.
- Produces (all in `emcee.moves`):
  - `MOVES_FILE = "moves.json"`, `LOCK_FILE = "moves.json.lock"`, `moves_path(root: Path) -> Path`
  - `@dataclass(frozen=True) class Moves: path: Path; exists: bool; entries: dict[str, dict]`
    - `Moves.get(performance_id: object) -> dict | None` (None for non-str ids)
    - `Moves.require_present(voiced_by_move: list[tuple[str, str | None, str | None]]) -> None`: each tuple is `(slug, performance_id, voiced profile)`. It raises `EmceeError` when the file is missing and the list is non-empty.
  - `load_moves(root: Path) -> Moves`: raises `EmceeError` naming the file on any read, parse or shape failure.
  - `read_moves_data(root: Path) -> dict[str, dict]`: the validated raw dict (`{}` when missing), for writers.
  - `moves_lock(root: Path)`: context manager, exclusive `flock` on `<root>/moves.json.lock`
  - `write_moves(root: Path, data: dict[str, dict]) -> None`: unique temp + fsync + rename, `indent=2, sort_keys=True`, trailing newline
  - `record_move(root: Path, performance_id: str, profile: str | None, package: str, *, moved_at: str) -> bool`: False (and no write) when the identical profile is already recorded
  - `clear_move(root: Path, show: str, live_performance_id: Callable[[], str]) -> str`: returns the removed performance_id
  - tests: `tests.helpers.no_moves() -> Moves`, `tests.helpers.moves_of(targets: dict[str, str | None]) -> Moves`

- [ ] **Step 1: Write the failing tests**

`packages/emcee/tests/test_moves.py`:

```python
"""moves.json: strict load, lock, write, record, clear (spec section 3;
strict surface 2: a recorded move is never silently lost)."""

import fcntl
import json
import os
from pathlib import Path

import pytest

import emcee.moves as moves_mod
from emcee.errors import EmceeError
from emcee.moves import (clear_move, load_moves, moves_path, read_moves_data, record_move,
                         write_moves)

STAMP = "2026-10-16T20:14:03Z"


def _write(root: Path, data) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "moves.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data))
    return path


def _lock_is_held(root: Path) -> bool:
    fd = os.open(root / "moves.json.lock", os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


# --- loading --------------------------------------------------------------


def test_missing_file_is_no_moves(tmp_path):
    moves = load_moves(tmp_path)
    assert (moves.exists, moves.entries, moves.path) == (False, {}, tmp_path / "moves.json")
    assert moves_path(tmp_path) == tmp_path / "moves.json"


def test_loads_a_valid_file(tmp_path):
    _write(tmp_path, {"A/1": {"profile": "southern", "package": "a-1", "moved_at": STAMP},
                      "B/2": {"profile": None}})
    moves = load_moves(tmp_path)
    assert moves.exists
    assert moves.get("A/1")["profile"] == "southern"
    assert moves.get("B/2")["profile"] is None
    assert moves.get("C/3") is None and moves.get(None) is None and moves.get(42) is None


@pytest.mark.parametrize("content, why", [
    ('{"A/1": {"profile": "sou', "invalid JSON"),
    ('["A/1"]', "not a JSON object"),
    ('{"A/1": "southern"}', "is not an object"),
    ('{"A/1": {"package": "a"}}', 'has no "profile"'),
    ('{"A/1": {"profile": 7}}', "non-empty string or null"),
    ('{"A/1": {"profile": ""}}', "non-empty string or null"),   # Review Focus 2
])
def test_a_malformed_file_is_a_hard_error_naming_it(tmp_path, content, why):
    path = _write(tmp_path, content)
    with pytest.raises(EmceeError) as exc:
        load_moves(tmp_path)
    assert str(path) in str(exc.value)
    assert why in str(exc.value)


def test_an_unreadable_file_is_a_hard_error(tmp_path):
    (tmp_path / "moves.json").mkdir()
    with pytest.raises(EmceeError, match="moves.json"):
        load_moves(tmp_path)


def test_a_non_utf8_file_is_a_hard_error(tmp_path):
    (tmp_path / "moves.json").write_bytes(b"\xff\xfe{")
    with pytest.raises(EmceeError, match="moves.json"):
        load_moves(tmp_path)


def test_read_moves_data_is_empty_for_a_missing_file_and_strict_otherwise(tmp_path):
    assert read_moves_data(tmp_path) == {}
    _write(tmp_path, "{broken")
    with pytest.raises(EmceeError):
        read_moves_data(tmp_path)


# --- the missing-file guard -----------------------------------------------


def test_require_present_passes_when_the_file_exists_or_nothing_was_move_voiced(tmp_path):
    load_moves(tmp_path).require_present([])            # missing, nothing move-voiced
    _write(tmp_path, {})
    load_moves(tmp_path).require_present([("a", "A/1", "southern")])   # present


def test_require_present_fails_naming_the_path_the_count_and_both_ways_out(tmp_path):
    moves = load_moves(tmp_path)
    with pytest.raises(EmceeError) as exc:
        moves.require_present([("a", "A/1", "southern"), ("b", None, None)])
    message = str(exc.value)
    details = "\n".join(exc.value.details)
    assert str(tmp_path / "moves.json") in message
    assert "2 package(s)" in message
    assert "a: performance_id A/1, voiced as southern" in details
    assert "b: performance_id (none), voiced as (none)" in details
    assert "rebuild" in details
    assert "write {}" in details


# --- writing --------------------------------------------------------------


def test_write_moves_fsyncs_sorts_and_leaves_no_temp(tmp_path, monkeypatch):
    synced: list[int] = []
    real_fsync = os.fsync
    monkeypatch.setattr(moves_mod.os, "fsync", lambda fd: (synced.append(fd), real_fsync(fd))[1])
    root = tmp_path / "home"

    write_moves(root, {"B/2": {"profile": None}, "A/1": {"profile": "x"}})

    path = root / "moves.json"
    assert synced
    assert json.loads(path.read_text()) == {"A/1": {"profile": "x"}, "B/2": {"profile": None}}
    assert path.read_text().index('"A/1"') < path.read_text().index('"B/2"')
    assert path.read_text().endswith("\n")
    assert sorted(p.name for p in root.iterdir()) == ["moves.json"]


# --- record ---------------------------------------------------------------


def test_record_creates_the_file_and_the_entry(tmp_path):
    assert record_move(tmp_path, "A/1", "southern", "a-1", moved_at=STAMP) is True
    assert json.loads((tmp_path / "moves.json").read_text()) == {
        "A/1": {"profile": "southern", "package": "a-1", "moved_at": STAMP}}


def test_record_of_a_null_profile(tmp_path):
    record_move(tmp_path, "A/1", None, "a-1", moved_at=STAMP)
    assert json.loads((tmp_path / "moves.json").read_text())["A/1"]["profile"] is None


def test_the_identical_move_is_unchanged_and_not_rewritten(tmp_path):
    record_move(tmp_path, "A/1", "southern", "a-1", moved_at=STAMP)
    before = (tmp_path / "moves.json").read_bytes()
    assert record_move(tmp_path, "A/1", "southern", "a-1", moved_at="2027-01-01T00:00:00Z") is False
    assert (tmp_path / "moves.json").read_bytes() == before


def test_record_keeps_unknown_keys_everywhere(tmp_path):
    _write(tmp_path, {"B/2": {"profile": "funk", "note": "keep me"},
                      "A/1": {"profile": "funk", "extra": 1}})
    record_move(tmp_path, "A/1", "southern", "a-1", moved_at=STAMP)
    data = json.loads((tmp_path / "moves.json").read_text())
    assert data["B/2"] == {"profile": "funk", "note": "keep me"}
    assert data["A/1"] == {"profile": "southern", "extra": 1, "package": "a-1", "moved_at": STAMP}


def test_record_never_overwrites_a_malformed_file(tmp_path):
    path = _write(tmp_path, "{broken")
    with pytest.raises(EmceeError):
        record_move(tmp_path, "A/1", "southern", "a-1", moved_at=STAMP)
    assert path.read_text() == "{broken"


def _spy_lock(monkeypatch) -> list[tuple[str, bool]]:
    seen: list[tuple[str, bool]] = []
    real_read, real_write = moves_mod.read_moves_data, moves_mod.write_moves

    def read(root):
        seen.append(("read", _lock_is_held(root)))
        return real_read(root)

    def write(root, data):
        seen.append(("write", _lock_is_held(root)))
        return real_write(root, data)

    monkeypatch.setattr(moves_mod, "read_moves_data", read)
    monkeypatch.setattr(moves_mod, "write_moves", write)
    return seen


def test_record_holds_the_lock_around_load_modify_write(tmp_path, monkeypatch):
    seen = _spy_lock(monkeypatch)
    record_move(tmp_path, "A/1", "southern", "a-1", moved_at=STAMP)
    assert seen == [("read", True), ("write", True)]
    assert _lock_is_held(tmp_path) is False


# --- clear ----------------------------------------------------------------


def _no_live():
    raise AssertionError("the live package must not be resolved when a recorded entry matches")


def test_clear_by_performance_id_or_recorded_package_name(tmp_path):
    _write(tmp_path, {"A/1": {"profile": "s", "package": "a-1"},
                      "B/2": {"profile": "s", "package": "b-2"}})
    assert clear_move(tmp_path, "A/1", _no_live) == "A/1"
    assert clear_move(tmp_path, "b-2", _no_live) == "B/2"
    assert (tmp_path / "moves.json").exists()
    assert json.loads((tmp_path / "moves.json").read_text()) == {}   # last clear leaves {}


def test_clear_falls_back_to_the_live_package(tmp_path):
    _write(tmp_path, {"A/1": {"profile": "s", "package": "renamed-since"}})
    assert clear_move(tmp_path, "a-1", lambda: "A/1") == "A/1"


def test_ambiguous_recorded_matches_are_refused_listing_their_ids(tmp_path):
    path = _write(tmp_path, {"Old/abc": {"profile": "s", "package": "abc"},
                             "New/abc": {"profile": "s", "package": "abc"}})
    before = path.read_bytes()
    with pytest.raises(EmceeError) as exc:
        clear_move(tmp_path, "abc", _no_live)
    assert exc.value.details == ["New/abc", "Old/abc"]
    assert path.read_bytes() == before


def test_clearing_something_never_recorded_writes_nothing(tmp_path):
    with pytest.raises(EmceeError, match="no move is recorded"):
        clear_move(tmp_path, "a-1", lambda: "A/1")
    assert not (tmp_path / "moves.json").exists()


def test_clear_holds_the_lock_around_load_modify_write(tmp_path, monkeypatch):
    _write(tmp_path, {"A/1": {"profile": "s", "package": "a-1"}})
    seen = _spy_lock(monkeypatch)
    clear_move(tmp_path, "A/1", _no_live)
    assert seen == [("read", True), ("write", True)]
```

Append to `packages/emcee/tests/helpers.py` (add `from emcee.moves import Moves` to its imports):

```python
_NO_ROOT = Path("/nonexistent-emcee-root")


def no_moves() -> Moves:
    """An absent moves.json: the explicit 'no moves' every resolver call needs."""
    return Moves(path=_NO_ROOT / "moves.json", exists=False, entries={})


def moves_of(targets: dict[str, str | None]) -> Moves:
    """A loaded moves.json mapping performance_id -> target profile."""
    return Moves(path=_NO_ROOT / "moves.json", exists=True, entries={
        pid: {"profile": profile, "package": pid.rsplit("/", 1)[-1],
              "moved_at": "2026-10-16T00:00:00Z"}
        for pid, profile in targets.items()})
```

- [ ] **Step 2: Run the tests and watch them fail**

Run: `./.venv/bin/python -m pytest packages/emcee/tests/test_moves.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'emcee.moves'`.

- [ ] **Step 3: Implement `packages/emcee/src/emcee/moves.py`**

```python
"""moves.json: the operator's one-off profile moves (spec section 3).

`<config.root>/moves.json` maps a manifest's `source.performance_id` to
`{"profile": str | null, "package": str, "moved_at": str, ...}`. It is the
ONLY record of these decisions, so it is never read leniently (strict
surface 2): any read or parse failure, or a shape other than
`{str: {"profile": non-empty str | null, ...}}`, is an `EmceeError` naming
the file. A missing file is "no moves", unless a package records that it
was voiced under a move (`Moves.require_present`).

Writers (`record_move`, `clear_move`) hold an advisory `fcntl.flock` on
`moves.json.lock` beside the file around load-modify-write, edit the raw
dict in place so unknown keys survive, and write unique temp + fsync +
rename. The lock copies llama's `locks.file_lock` pattern: emcee never
imports llama.
"""

import json
import os
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

try:
    import fcntl  # POSIX only
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None

from emcee.errors import EmceeError

MOVES_FILE = "moves.json"
LOCK_FILE = "moves.json.lock"


def moves_path(root: Path) -> Path:
    return Path(root) / MOVES_FILE


def _malformed(path: Path, why: str) -> EmceeError:
    return EmceeError(
        f"{path} is unreadable or malformed ({why}); fix or restore it: emcee never "
        "reads it as no moves, since that would re-voice every moved show under its "
        "old profile")


def _validated(data: object, path: Path) -> dict[str, dict]:
    if not isinstance(data, dict):
        raise _malformed(path, "the top level is not a JSON object")
    for pid, entry in data.items():
        if not isinstance(entry, dict):
            raise _malformed(path, f"entry {pid!r} is not an object")
        if "profile" not in entry:
            raise _malformed(path, f'entry {pid!r} has no "profile"')
        profile = entry["profile"]
        if profile is not None and (not isinstance(profile, str) or not profile):
            raise _malformed(path, f'entry {pid!r}: "profile" must be a non-empty string or null')
    return data


def _read(path: Path) -> dict[str, dict] | None:
    """The validated raw dict, or None when the file does not exist."""
    try:
        text = path.read_text()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        raise _malformed(path, f"{type(exc).__name__}: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _malformed(path, f"invalid JSON: {exc}") from exc
    return _validated(data, path)


def read_moves_data(root: Path) -> dict[str, dict]:
    """The validated raw dict (`{}` when the file is missing), for a writer
    to modify in place while holding `moves_lock`."""
    data = _read(moves_path(root))
    return {} if data is None else data


@dataclass(frozen=True)
class Moves:
    """moves.json as loaded once per command invocation."""
    path: Path
    exists: bool
    entries: dict[str, dict]

    def get(self, performance_id: object) -> dict | None:
        if not isinstance(performance_id, str):
            return None
        return self.entries.get(performance_id)

    def require_present(self, voiced_by_move: list[tuple[str, str | None, str | None]]) -> None:
        """Refuse a missing moves.json while any package records that it was
        voiced under a move (`dj_audio.profile_source == "move"`). Each tuple
        is (slug, performance_id, voiced profile)."""
        if self.exists or not voiced_by_move:
            return
        rows = [f"{slug}: performance_id {pid or '(none)'}, voiced as "
                f"{profile if profile is not None else '(none)'}"
                for slug, pid, profile in voiced_by_move]
        raise EmceeError(
            f"{self.path} is missing, but {len(voiced_by_move)} package(s) were voiced under a "
            'recorded move (dj_audio.profile_source = "move"); refusing to read that as no moves',
            details=[*rows,
                     f"either rebuild {self.path} by hand from the packages above: "
                     '{"<performance_id>": {"profile": "<profile>"}, ...}',
                     f"or write {{}} to {self.path} to accept the loss (those packages are "
                     "then re-voiced under their current profile)"])


def load_moves(root: Path) -> Moves:
    path = moves_path(root)
    data = _read(path)
    return Moves(path=path, exists=data is not None, entries={} if data is None else data)


@contextmanager
def moves_lock(root: Path) -> Iterator[None]:
    """Exclusive advisory lock on `<root>/moves.json.lock`. Released when the
    context exits or the process dies. A no-op where fcntl is missing."""
    path = Path(root) / LOCK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    if fcntl is None:  # pragma: no cover - non-POSIX fallback
        yield
        return
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def write_moves(root: Path, data: dict[str, dict]) -> None:
    """Unique temp + fsync + rename: a crash leaves the old file or the new
    one, never a torn one."""
    path = moves_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode()
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def record_move(root: Path, performance_id: str, profile: str | None, package: str, *,
                moved_at: str) -> bool:
    """Record (or retarget) one move under the lock. False, with no write,
    when the identical profile is already recorded for this id."""
    with moves_lock(root):
        data = read_moves_data(root)
        entry = data.get(performance_id)
        if entry is not None and entry["profile"] == profile:
            return False
        entry = data.setdefault(performance_id, {})
        entry.update(profile=profile, package=package, moved_at=moved_at)
        write_moves(root, data)
        return True


def clear_move(root: Path, show: str, live_performance_id: Callable[[], str]) -> str:
    """Remove one move under the lock and return its performance_id.

    Recorded entries match first, by exact performance_id or exact recorded
    package name, so a stale move whose package is gone can be cleared.
    Only when none matches is `live_performance_id()` called to resolve
    `show` as a live package. More than one recorded match is refused,
    listing the ids, so the operator can clear one exactly."""
    with moves_lock(root):
        data = read_moves_data(root)
        hits = sorted(pid for pid, entry in data.items()
                      if pid == show or entry.get("package") == show)
        if len(hits) > 1:
            raise EmceeError(f"{show!r} matches {len(hits)} recorded moves; clear one by its "
                             "performance_id", hits)
        pid = hits[0] if hits else live_performance_id()
        if pid not in data:
            raise EmceeError(f"no move is recorded for {show!r} (performance_id {pid})")
        del data[pid]
        write_moves(root, data)
        return pid
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `./.venv/bin/python -m pytest packages/emcee/tests/test_moves.py -q` → all pass.
Run: `./.venv/bin/python -m pytest -q` → green.

- [ ] **Step 5: Commit**

```bash
git add packages/emcee/src/emcee/moves.py packages/emcee/tests/test_moves.py packages/emcee/tests/helpers.py
git commit -m "feat(emcee): moves.json store with strict loading, flock and atomic writes"
```

---

### Task 3: `effective_profile` and move-target validation

Spec: §1 "The effective profile"; §3 "Validation at use time".

**Files:**
- Modify: `packages/emcee/src/emcee/station.py` (add the code below after `raw_profile`; existing code unchanged in this task)
- Create: `packages/emcee/tests/test_effective.py`

**Interfaces:**
- Consumes: `emcee.artists.normalize_artist`, `emcee.config.EmceeConfig` (`assign.artists`, `assign.profiles`), `emcee.moves.Moves.get`, `station.manifest_profile`.
- Produces (all in `emcee.station`):
  - `ProfileSource = Literal["move", "artist", "llama"]`
  - `@dataclass(frozen=True) class Effective: profile: str | None; source: ProfileSource; rule: str | None` (`rule` is the matching `[assign.artists]` key as written in config, or `None`)
  - `effective_profile(config: EmceeConfig, moves: Moves, manifest: object) -> Effective` (total, never raises)
  - `profile_label(profile: str | None) -> str` (`"(none)"` for `None`)
  - `target_problem(config: EmceeConfig, target: str | None, delivered: str | None) -> str | None`
  - `move_target_problem(config: EmceeConfig, moves: Moves, manifest: object) -> str | None`
  - total accessors: `manifest_performance_id(manifest) -> str | None`, `manifest_artist(manifest) -> str | None`, `manifest_voiced_source(manifest) -> str | None` (`dj_audio.profile_source`), `manifest_voiced_profile(manifest) -> str | None` (`dj_audio.profile` when the key is present, else llama's profile), `manifest_tts(manifest) -> dict | None`

- [ ] **Step 1: Write the failing tests**

`packages/emcee/tests/test_effective.py`:

```python
"""effective_profile: move > artist rule > llama's profile (spec section 1),
and use-time move validation (spec section 3)."""

import pytest

from emcee.config import EmceeConfig
from emcee.station import (Effective, effective_profile, manifest_artist,
                           manifest_performance_id, manifest_tts, manifest_voiced_profile,
                           manifest_voiced_source, move_target_problem, profile_label,
                           target_problem)

from tests.helpers import moves_of, no_moves

PID = "TedeschiTrucksBand/2012-11-29"
TTB = "Tedeschi Trucks Band"


def _manifest(artist=TTB, profile="funk", pid=PID) -> dict:
    return {"show": {"artist": artist}, "source": {"performance_id": pid, "profile": profile}}


def _cfg(artists=None) -> EmceeConfig:
    return EmceeConfig(assign={"profiles": {"southern": {"presenter": "gregg"},
                                            "funk": {"presenter": "fred"}},
                               "artists": artists or {}})


def test_no_rule_and_no_move_is_llamas_profile():
    assert effective_profile(_cfg(), no_moves(), _manifest()) == Effective("funk", "llama", None)


def test_an_artist_rule_without_from_applies_to_any_delivered_profile():
    got = effective_profile(_cfg({TTB: "southern"}), no_moves(), _manifest())
    assert got == Effective("southern", "artist", TTB)


def test_artist_matching_is_loose_and_reports_the_config_key():
    got = effective_profile(_cfg({"tedeschi trucks band": "southern"}), no_moves(),
                            _manifest(artist="TEDESCHI TRUCKS BAND"))
    assert got == Effective("southern", "artist", "tedeschi trucks band")


def test_from_present_applies_only_from_the_listed_profiles():
    cfg = _cfg({TTB: {"profile": "southern", "from": ["funk"]}})
    assert effective_profile(cfg, no_moves(), _manifest()).source == "artist"
    other = _cfg({TTB: {"profile": "southern", "from": ["dead"]}})
    assert effective_profile(other, no_moves(), _manifest()) == Effective("funk", "llama", None)


def test_a_show_with_no_profile_under_a_rule_with_and_without_from():
    bare = _cfg({TTB: "southern"})
    assert effective_profile(bare, no_moves(), _manifest(profile=None)).profile == "southern"
    gated = _cfg({TTB: {"profile": "southern", "from": ["funk"]}})
    assert effective_profile(gated, no_moves(), _manifest(profile=None)) == \
        Effective(None, "llama", None)


def test_a_move_beats_an_artist_rule():
    got = effective_profile(_cfg({TTB: "southern"}), moves_of({PID: "bluegrass"}), _manifest())
    assert got == Effective("bluegrass", "move", None)


def test_a_move_back_to_the_delivered_profile_beats_a_rule():
    got = effective_profile(_cfg({TTB: "southern"}), moves_of({PID: "funk"}), _manifest())
    assert got == Effective("funk", "move", None)


def test_a_move_to_none():
    assert effective_profile(_cfg(), moves_of({PID: None}), _manifest(profile=None)) == \
        Effective(None, "move", None)


def test_empty_or_non_string_llama_profile_reads_as_none():
    assert effective_profile(_cfg(), no_moves(), _manifest(profile="")).profile is None
    assert effective_profile(_cfg(), no_moves(), _manifest(profile=7)).profile is None


@pytest.mark.parametrize("show", [None, {}, {"artist": 42}, {"artist": None}, "garbage"])
def test_artist_missing_or_not_a_string_falls_to_llama(show):   # Review Focus 1
    manifest = _manifest()
    if show is None:
        del manifest["show"]
    else:
        manifest["show"] = show
    assert effective_profile(_cfg({TTB: "southern"}), no_moves(), manifest) == \
        Effective("funk", "llama", None)


@pytest.mark.parametrize("source", [None, {}, {"performance_id": 9, "profile": "funk"}])
def test_a_move_needs_a_string_performance_id(source):
    manifest = _manifest()
    if source is None:
        del manifest["source"]
    else:
        manifest["source"] = source
    assert effective_profile(_cfg(), moves_of({PID: "southern"}), manifest).source == "llama"


def test_effective_profile_never_raises_on_garbage():
    for garbage in (None, [], "x", 3, {"source": "x", "show": []}):
        assert effective_profile(_cfg({TTB: "southern"}), no_moves(), garbage).source == "llama"


# --- use-time validation ----------------------------------------------------


def test_move_target_problem_cases():
    cfg = _cfg()
    assert move_target_problem(cfg, no_moves(), _manifest()) is None                  # no move
    assert move_target_problem(cfg, moves_of({PID: "southern"}), _manifest()) is None  # assigned
    assert move_target_problem(_cfg(), moves_of({PID: "dead"}), _manifest(profile="dead")) is None
    assert move_target_problem(cfg, moves_of({PID: "gone"}), _manifest()) == \
        'move target "gone" has no [assign.profiles] entry'
    assert move_target_problem(cfg, moves_of({PID: None}), _manifest()) == \
        'move target "(none)" has no [assign.profiles] entry'


def test_target_problem_allows_the_delivered_profile_even_without_an_entry():
    cfg = EmceeConfig()
    assert target_problem(cfg, "funk", "funk") is None
    assert target_problem(cfg, None, None) is None
    assert target_problem(cfg, "funk", "dead") == 'move target "funk" has no [assign.profiles] entry'


# --- accessors ----------------------------------------------------------------


def test_accessors_are_total():
    for garbage in (None, [], "x", {"dj_audio": "x"}, {"source": None}):
        assert manifest_performance_id(garbage) is None
        assert manifest_artist(garbage) is None
        assert manifest_voiced_source(garbage) is None
        assert manifest_tts(garbage) is None
    assert profile_label(None) == "(none)" and profile_label("funk") == "funk"


def test_voiced_profile_prefers_the_recorded_key_and_falls_back_to_llamas():
    legacy = {**_manifest(), "dj_audio": {"set_intros": {}, "outro": "o"}}
    assert manifest_voiced_profile(legacy) == "funk"
    recorded = {**_manifest(), "dj_audio": {"profile": "southern", "profile_source": "artist",
                                            "tts": {"backend": "fake"}}}
    assert manifest_voiced_profile(recorded) == "southern"
    assert manifest_voiced_source(recorded) == "artist"
    assert manifest_tts(recorded) == {"backend": "fake"}
    null = {**_manifest(), "dj_audio": {"profile": None}}
    assert manifest_voiced_profile(null) is None
```

- [ ] **Step 2: Run the tests and watch them fail**

Run: `./.venv/bin/python -m pytest packages/emcee/tests/test_effective.py -q`
Expected: `ImportError: cannot import name 'Effective' from 'emcee.station'`.

- [ ] **Step 3: Implement in `packages/emcee/src/emcee/station.py`**

Add to the imports:

```python
from typing import Literal

from emcee.artists import normalize_artist
from emcee.config import EmceeConfig
from emcee.moves import Moves
```

Add after `raw_profile`:

```python
ProfileSource = Literal["move", "artist", "llama"]


@dataclass(frozen=True)
class Effective:
    """Which profile a package is voiced as, and why (spec section 1).
    `rule` is the matching [assign.artists] key as written in config, for
    messages; None unless `source == "artist"`."""
    profile: str | None
    source: ProfileSource
    rule: str | None


def profile_label(profile: str | None) -> str:
    return profile if profile is not None else "(none)"


def _get(obj: object, *keys: str) -> object:
    """obj[k1][k2]... or None for any missing key or non-dict on the way."""
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _nonempty_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def manifest_performance_id(manifest: object) -> str | None:
    """`manifest["source"]["performance_id"]`, None for any other shape. Never raises."""
    return _nonempty_str(_get(manifest, "source", "performance_id"))


def manifest_artist(manifest: object) -> str | None:
    """`manifest["show"]["artist"]`, None for any other shape. Never raises."""
    return _nonempty_str(_get(manifest, "show", "artist"))


def manifest_voiced_source(manifest: object) -> str | None:
    """`dj_audio.profile_source` as recorded, else None. Never raises."""
    return _nonempty_str(_get(manifest, "dj_audio", "profile_source"))


def manifest_voiced_profile(manifest: object) -> str | None:
    """The profile a voiced package was voiced as: `dj_audio["profile"]` when
    the key is present, else llama's profile (a legacy block was voiced under
    llama's profile, since no rules or moves existed). Never raises."""
    dj_audio = _get(manifest, "dj_audio")
    if isinstance(dj_audio, dict) and "profile" in dj_audio:
        return _nonempty_str(dj_audio["profile"])
    return manifest_profile(manifest)


def manifest_tts(manifest: object) -> dict | None:
    """`dj_audio.tts` as recorded (a dict), else None. Never raises."""
    tts = _get(manifest, "dj_audio", "tts")
    return tts if isinstance(tts, dict) else None


def effective_profile(config: EmceeConfig, moves: Moves, manifest: object) -> Effective:
    """The profile a package is voiced as. First match wins:

    1. a move recorded for the manifest's `source.performance_id`;
    2. an [assign.artists] rule whose normalized key equals the normalized
       `show.artist`, and whose `from` (if any) contains llama's profile;
    3. llama's profile (`manifest_profile`, possibly None).

    Pure and total: never raises, whatever the manifest holds."""
    entry = moves.get(manifest_performance_id(manifest))
    if entry is not None:
        return Effective(entry["profile"], "move", None)
    llama = manifest_profile(manifest)
    artist = manifest_artist(manifest)
    if artist is not None:
        wanted = normalize_artist(artist)
        for key, rule in config.assign.artists.items():
            if normalize_artist(key) == wanted and (rule.from_ is None or llama in rule.from_):
                return Effective(rule.profile, "artist", key)
    return Effective(llama, "llama", None)


def target_problem(config: EmceeConfig, target: str | None, delivered: str | None) -> str | None:
    """Why a move to `target` cannot be voiced, or None. A move to the
    delivered profile is always valid; any other target needs an
    [assign.profiles.<target>] entry."""
    if target == delivered or (target is not None and target in config.assign.profiles):
        return None
    return f'move target "{profile_label(target)}" has no [assign.profiles] entry'


def move_target_problem(config: EmceeConfig, moves: Moves, manifest: object) -> str | None:
    """Use-time validation of this package's recorded move (spec section 3):
    None when there is no move or it is valid. Never raises."""
    entry = moves.get(manifest_performance_id(manifest))
    if entry is None:
        return None
    return target_problem(config, entry["profile"], manifest_profile(manifest))
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `./.venv/bin/python -m pytest packages/emcee/tests/test_effective.py -q` → all pass.
Run: `./.venv/bin/python -m pytest -q` → green.

- [ ] **Step 5: Commit**

```bash
git add packages/emcee/src/emcee/station.py packages/emcee/tests/test_effective.py
git commit -m "feat(emcee): effective_profile resolver (move > artist rule > llama)"
```

---

### Task 4: Readiness fifth leg; scan and status threading of config and moves

Spec: §1 (scan and every reader on the effective profile; `PackageStatus.delivered_profile`), §3 (Loading, A missing file), §4 "Readiness gains a fifth leg". Strict surfaces 2 and 3.

This task changes `scan` and `readiness` signatures. `run` and `status` load moves first and fail before any work on a bad or missing file. Voicing still uses the delivered profile until Task 5. That intermediate state is intended, and the suite stays green.

**Files:**
- Modify: `packages/emcee/src/emcee/station.py` (final content below)
- Modify: `packages/emcee/src/emcee/cli.py` (`_scan_broad`, `_station_statuses`, new `_load_station`; `run` and `status_cmd` call it)
- Modify: `packages/emcee/tests/helpers.py` (`build_package(..., artist=...)`, `set_dj_audio`, `write_moves_file`)
- Create: `packages/emcee/tests/test_profile_readiness.py`
- Modify existing call sites: `packages/emcee/tests/test_station.py` (every `scan(x)` → `scan(x, EmceeConfig(), no_moves())`, every `readiness(p)` → `readiness(p, EmceeConfig(), no_moves())`), `packages/emcee/tests/test_status_cmd.py:369` (`_scan_broad(tmp_path)` → `_scan_broad(tmp_path, EmceeConfig(), no_moves())`), `packages/emcee/tests/test_handshake.py:121` (`scan(station)` → `scan(station, load_config(), no_moves())`), `packages/emcee/tests/test_voice_cmd.py` lines 240, 255, 288, 301, 320, 335 (`readiness(pkg)` → `readiness(pkg, load_config(), no_moves())`, importing `load_config` from `emcee.config` and `no_moves` from `tests.helpers`)

**Interfaces:**
- Consumes: everything Task 3 produced; `emcee.moves.Moves`, `load_moves`.
- Produces:
  - `station.PackageStatus` gains (all defaulted): `delivered_profile: str | None`, `profile_source: str | None`, `performance_id: str | None`, `voiced: bool`, `voiced_profile: str | None`, `voiced_source: str | None`, `profile_reason: str | None`, `missing_tracks: int`, `clips: int`, `move_problem: str | None`, `tts: dict | None`. `profile` now holds the **effective** profile; for unsupported or unreadable rows it holds llama's profile, best effort.
  - `station.Assessment` (frozen dataclass): `reasons: list[str]`, `voiced: bool`, `profile_reason: str | None`, `missing_tracks: int`, `clips: int`, `effective: Effective`, and the property `ok -> bool`
  - `station.assess(pkg: Package, config: EmceeConfig, moves: Moves) -> Assessment`
  - `station.readiness(pkg: Package, config: EmceeConfig, moves: Moves) -> tuple[bool, list[str]]`
  - `station.profile_change_reason(voiced: str | None, effective: Effective, voiced_source: str | None) -> str`
  - `station.identity(manifest: object, config, moves) -> dict` (the `PackageStatus` kwargs that need only the manifest; total)
  - `station.package_status(pkg, config, moves) -> PackageStatus` (may raise on a malformed manifest)
  - `station.unsupported_status(pkg) -> PackageStatus`
  - `station.scan(station_root: Path, config: EmceeConfig, moves: Moves) -> list[PackageStatus]`
  - `cli._scan_broad(root, config, moves)`, `cli._station_statuses(root, config, moves)`
  - `cli._load_station(config: EmceeConfig, root: Path) -> tuple[Moves, list[PackageStatus]]`: loads moves, scans, then enforces `require_present` before returning.
  - tests: `build_package(..., artist: str = "Grateful Dead")`, `set_dj_audio(pkg_dir: Path, **fields) -> None`, `write_moves_file(home: Path, targets: dict[str, str | None]) -> Path`

- [ ] **Step 1: Test helpers**

In `packages/emcee/tests/helpers.py`: add `artist: str = "Grateful Dead",` as the last keyword parameter of `build_package` and use it in the manifest (`"artist": artist,` instead of `"artist": "Grateful Dead",`). Append:

```python
def set_dj_audio(pkg_dir: Path, **fields) -> None:
    """Merge `fields` into a voiced fixture's dj_audio block (raw JSON), e.g.
    profile="southern", profile_source="move", presenter="gregg"."""
    path = pkg_dir / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["dj_audio"].update(fields)
    _write_json(path, manifest)


def write_moves_file(home: Path, targets: dict[str, str | None]) -> Path:
    """<home>/moves.json mapping performance_id -> target profile."""
    path = home / "moves.json"
    _write_json(path, {pid: {"profile": profile, "package": pid.rsplit("/", 1)[-1],
                             "moved_at": "2026-10-16T00:00:00Z"}
                       for pid, profile in targets.items()})
    return path
```

- [ ] **Step 2: Write the failing tests**

`packages/emcee/tests/test_profile_readiness.py`:

```python
"""Readiness's fifth leg (the profile check) and the scan threading config
and moves (spec sections 1, 3, 4; strict surfaces 2 and 3)."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import emcee.process as process_mod
from emcee.cli import app
from emcee.config import EmceeConfig
from emcee.errors import EmceeError
from emcee.package_io import Package
from emcee.station import readiness, scan

from tests.helpers import build_package, moves_of, no_moves, set_dj_audio, write_moves_file

runner = CliRunner()
TTB = "Tedeschi Trucks Band"
_SOUTHERN = '[assign.profiles.southern]\npresenter = "gregg"\n'
_RULE = _SOUTHERN + '\n[assign.artists]\n"Tedeschi Trucks Band" = "southern"\n'


def _rule_config() -> EmceeConfig:
    return EmceeConfig(assign={"profiles": {"southern": {"presenter": "gregg"}},
                               "artists": {TTB: "southern"}})


def _edit(pkg_dir: Path, mutate) -> None:
    path = pkg_dir / "manifest.json"
    manifest = json.loads(path.read_text())
    mutate(manifest)
    path.write_text(json.dumps(manifest, indent=2) + "\n")


# --- strict surface 3: nothing ready today goes pending ----------------------


@pytest.mark.parametrize("moves", [no_moves(), moves_of({})], ids=["no-file", "empty-file"])
@pytest.mark.parametrize("source", ["dead", "", None, "missing"])
def test_a_legacy_voiced_package_stays_ready_with_no_rules_or_moves(tmp_path, source, moves):
    pkg_dir = build_package(tmp_path, slug="legacy", voiced=True, profile="dead")

    def mutate(m):
        assert "profile" not in m["dj_audio"]       # the fixture is a legacy block
        if source == "missing":
            del m["source"]
        else:
            m["source"]["profile"] = source
    _edit(pkg_dir, mutate)

    assert readiness(Package(pkg_dir), EmceeConfig(), moves) == (True, [])
    [status] = scan(tmp_path, EmceeConfig(), moves)
    assert (status.state, status.reasons) == ("ready", [])


# --- the four reason texts -------------------------------------------------------


def test_the_same_legacy_package_under_a_matching_rule_goes_pending(tmp_path):
    pkg_dir = build_package(tmp_path, slug="ttb", voiced=True, profile="funk", artist=TTB)
    assert readiness(Package(pkg_dir), _rule_config(), no_moves()) == (
        False, ['voiced as funk, now southern (artist rule "Tedeschi Trucks Band")'])


def test_a_move_makes_it_pending_with_the_move_reason(tmp_path):
    pkg_dir = build_package(tmp_path, slug="ttb", voiced=True, profile="funk", artist=TTB)
    assert readiness(Package(pkg_dir), EmceeConfig(),
                     moves_of({"GratefulDead/ttb": "southern"})) == (
        False, ["voiced as funk, now southern (move)"])


def test_a_move_no_longer_recorded(tmp_path):
    pkg_dir = build_package(tmp_path, slug="ttb", voiced=True, profile="funk", artist=TTB)
    set_dj_audio(pkg_dir, profile="southern", profile_source="move")
    assert readiness(Package(pkg_dir), EmceeConfig(), no_moves()) == (
        False, ["voiced as southern, now funk (move no longer recorded)"])


def test_back_to_the_delivered_profile_when_no_rule_or_move_applies(tmp_path):
    pkg_dir = build_package(tmp_path, slug="ttb", voiced=True, profile="funk", artist=TTB)
    set_dj_audio(pkg_dir, profile="southern", profile_source="artist")
    assert readiness(Package(pkg_dir), EmceeConfig(), no_moves()) == (
        False, ["voiced as southern, now funk (delivered profile; no rule or move applies)"])


def test_a_none_profile_renders_as_none(tmp_path):
    pkg_dir = build_package(tmp_path, slug="ttb", voiced=True, profile=None, artist=TTB)
    ok, reasons = readiness(Package(pkg_dir), _rule_config(), no_moves())
    assert reasons == ['voiced as (none), now southern (artist rule "Tedeschi Trucks Band")']


# --- what does NOT make a package pending ----------------------------------------


def test_voiced_as_the_effective_profile_stays_ready(tmp_path):
    pkg_dir = build_package(tmp_path, slug="ttb", voiced=True, profile="funk", artist=TTB)
    set_dj_audio(pkg_dir, profile="southern", profile_source="artist", presenter="gregg")
    assert readiness(Package(pkg_dir), _rule_config(), no_moves()) == (True, [])


def test_a_missing_tts_or_a_different_presenter_never_makes_it_pending(tmp_path):
    pkg_dir = build_package(tmp_path, slug="gd", voiced=True, profile="dead")
    set_dj_audio(pkg_dir, profile="dead", profile_source="llama", presenter="someone-else")
    cfg = EmceeConfig(assign={"profiles": {"dead": {"presenter": "phil"}}})
    assert readiness(Package(pkg_dir), cfg, no_moves()) == (True, [])


# --- scan fields ---------------------------------------------------------------------


def test_scan_reports_effective_and_delivered_profiles(tmp_path):
    build_package(tmp_path, slug="ttb", voiced=True, profile="funk", artist=TTB)
    build_package(tmp_path, slug="gd", voiced=False, profile="dead")

    by = {s.path.name: s for s in scan(tmp_path, _rule_config(), no_moves())}

    ttb, gd = by["ttb"], by["gd"]
    assert (ttb.profile, ttb.delivered_profile, ttb.profile_source) == ("southern", "funk", "artist")
    assert ttb.state == "pending" and ttb.voiced is True
    assert ttb.profile_reason == 'voiced as funk, now southern (artist rule "Tedeschi Trucks Band")'
    assert (ttb.performance_id, ttb.clips, ttb.missing_tracks) == ("GratefulDead/ttb", 3, 0)
    assert (gd.profile, gd.delivered_profile, gd.profile_source) == ("dead", "dead", "llama")
    assert gd.voiced is False and gd.profile_reason is None and gd.tts is None


def test_scan_counts_missing_tracks_and_flags_an_invalid_move(tmp_path):
    pkg_dir = build_package(tmp_path, slug="gd", voiced=False, profile="dead")
    sorted((pkg_dir / "audio").iterdir())[0].unlink()

    [status] = scan(tmp_path, EmceeConfig(), moves_of({"GratefulDead/gd": "gone"}))

    assert status.missing_tracks == 1
    assert status.move_problem == 'move target "gone" has no [assign.profiles] entry'


def test_scan_keeps_unsupported_rows_on_llamas_profile(tmp_path):
    v2 = tmp_path / "v2"
    v2.mkdir()
    (v2 / "manifest.json").write_text(json.dumps(
        {"schema_version": 2, "source": {"profile": "old", "performance_id": "X/1"}}))
    [status] = scan(tmp_path, _rule_config(), no_moves())
    assert (status.state, status.profile, status.delivered_profile, status.performance_id) == (
        "unsupported", "old", "old", "X/1")


# --- CLI: moves are loaded first, and loudly -------------------------------------------


def _home(tmp_path, monkeypatch, assign: str = ""):
    home = tmp_path / "home"
    station = tmp_path / "station"
    station.mkdir(parents=True)
    home.mkdir()
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    (home / "config.toml").write_text(
        f'[station]\nroot = "{station}"\n\n[tts]\nbackend = "fake"\nvoice = "v"\n\n{assign}\n')
    return home, station


def _forbid_spend(monkeypatch) -> None:
    def boom(*a, **k):
        raise AssertionError("LLM or TTS spend")
    monkeypatch.setattr(process_mod, "provider_for", boom)
    monkeypatch.setattr(process_mod, "speech_provider_for", boom)


@pytest.mark.parametrize("command", [["run"], ["run", "--dry-run"], ["status"], ["status", "--json"]])
@pytest.mark.parametrize("content", ['{"GratefulDead/a": {"profile": "sou', '["not", "an", "object"]'],
                         ids=["truncated", "wrong-shape"])
def test_a_bad_moves_file_fails_loudly_before_any_work(tmp_path, monkeypatch, command, content):
    home, station = _home(tmp_path, monkeypatch)
    build_package(station, slug="a", profile="dead")
    (home / "moves.json").write_text(content)
    _forbid_spend(monkeypatch)

    result = runner.invoke(app, command)

    assert result.exit_code == 1
    assert isinstance(result.exception, EmceeError)
    assert str(home / "moves.json") in str(result.exception)
    assert "voiced:" not in result.output and "would voice" not in result.output
    assert json.loads((station / "a" / "manifest.json").read_text())["dj_audio"] is None


@pytest.mark.parametrize("command", [["run"], ["run", "--dry-run"], ["status"]])
def test_a_missing_moves_file_with_move_voiced_packages_fails(tmp_path, monkeypatch, command):
    home, station = _home(tmp_path, monkeypatch, _SOUTHERN)
    for slug in ("m1", "m2"):
        pkg_dir = build_package(station, slug=slug, voiced=True, profile="funk")
        set_dj_audio(pkg_dir, profile="southern", profile_source="move", presenter="gregg")
    build_package(station, slug="fresh", profile="dead")
    _forbid_spend(monkeypatch)

    result = runner.invoke(app, command)

    assert result.exit_code == 1
    exc = result.exception
    assert isinstance(exc, EmceeError)
    details = "\n".join(exc.details)
    assert str(home / "moves.json") in str(exc) and "2 package(s)" in str(exc)
    assert "m1: performance_id GratefulDead/m1, voiced as southern" in details
    assert "rebuild" in details and "write {}" in details
    assert "voiced:" not in result.output and "would voice" not in result.output
    assert not (home / "moves.json").exists()


def test_a_missing_moves_file_with_no_move_voiced_package_is_no_moves(tmp_path, monkeypatch):
    home, station = _home(tmp_path, monkeypatch)
    build_package(station, slug="a", voiced=True, profile="dead")

    result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)[0]["state"] == "ready"
    assert not (home / "moves.json").exists()


def test_run_filters_select_by_the_effective_profile(tmp_path, monkeypatch):
    _, station = _home(tmp_path, monkeypatch, _RULE)
    build_package(station, slug="ttb", profile="funk", artist=TTB)
    build_package(station, slug="lettuce", profile="funk", artist="Lettuce")

    south = runner.invoke(app, ["run", "--profile", "southern", "--dry-run"])
    assert "would voice: ttb  southern  gregg" in south.output
    assert "would voice: lettuce" not in south.output

    funk = runner.invoke(app, ["run", "--profile", "funk", "--dry-run"])
    assert "would voice: lettuce  funk" in funk.output
    assert "would voice: ttb" not in funk.output

    assigned = runner.invoke(app, ["run", "--assigned", "--dry-run"])
    assert "would voice: ttb" in assigned.output
    assert "would voice: lettuce" not in assigned.output


def test_a_malformed_manifest_does_not_unmove_a_moved_ready_package(tmp_path, monkeypatch):
    """One malformed manifest sends status down the per-entry `_scan_broad`
    path; that path must thread config and moves too."""
    home, station = _home(tmp_path, monkeypatch, _SOUTHERN)
    moved = build_package(station, slug="moved", voiced=True, profile="funk")
    set_dj_audio(moved, profile="southern", profile_source="move", presenter="gregg")
    write_moves_file(home, {"GratefulDead/moved": "southern"})
    bad = station / "bad"
    bad.mkdir()
    (bad / "manifest.json").write_text(json.dumps(
        {"schema_version": 3, "source": {"profile": "dead"}, "tracks": [{}]}))

    result = runner.invoke(app, ["status", "--json"])

    by = {row["slug"]: row for row in json.loads(result.stdout)}
    assert by["bad"]["state"] == "error"
    assert by["moved"]["state"] == "ready"
    assert by["moved"]["profile"] == "southern"
```

- [ ] **Step 3: Run the tests and watch them fail**

Run: `./.venv/bin/python -m pytest packages/emcee/tests/test_profile_readiness.py -q`
Expected: failures with `TypeError: readiness() takes 1 positional argument but 3 were given` (and the same for `scan`).

- [ ] **Step 4: Implement `packages/emcee/src/emcee/station.py`**

Replace the module docstring, the `PackageStatus` class, `raw_profile`, `readiness` and `scan` so the file reads as follows. Task 3's block (from `ProfileSource` to `move_target_problem`) stays as written, between `raw_profile` and `Assessment`.

```python
"""Station model: scan a delivered-packages folder (`[station] root`) for
emcee packages and compute each one's voice readiness.

Readiness has five legs: script present, DJ audio present, broadcast.m3u
present, every manifest track's audio on disk, and (2026-10-16) the
profile check: a voiced package was voiced as the profile emcee would voice
it as now (`effective_profile`: a recorded move, else an artist rule, else
llama's profile). transmitter mirrors the first four on files alone and
deliberately NOT the fifth: it cannot see rules or moves.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from emcee.artists import normalize_artist
from emcee.config import EmceeConfig
from emcee.moves import Moves
from emcee.package_io import Package, UnsupportedPackage


@dataclass
class PackageStatus:
    path: Path
    state: str  # "ready" | "pending" | "unsupported" | "error"
    reasons: list[str] = field(default_factory=list)
    # The EFFECTIVE profile (move > artist rule > llama's). For an unsupported
    # or unreadable manifest, llama's profile best-effort (no resolution).
    profile: str | None = None
    # Who voiced it: None = not voiced, "?" = voiced before emcee recorded the
    # presenter (legacy), "house" = house narrator, else the presenter id.
    voiced_by: str | None = None
    delivered_profile: str | None = None     # llama's profile (manifest_profile)
    profile_source: str | None = None        # "move" | "artist" | "llama"; None = not resolved
    performance_id: str | None = None
    voiced: bool = False                     # the dj_audio block is present
    voiced_profile: str | None = None        # manifest_voiced_profile
    voiced_source: str | None = None         # dj_audio.profile_source as recorded
    profile_reason: str | None = None        # the profile check's failing reason, if it fails
    missing_tracks: int = 0                  # manifest tracks whose audio is not on disk
    clips: int = 0                           # clips a voicing renders: one per non-encore set + outro
    move_problem: str | None = None          # use-time move validation failure
    tts: dict | None = None                  # dj_audio.tts as recorded


def manifest_profile(manifest: object) -> str | None:
    # ...unchanged...


def manifest_voiced_by(manifest: object) -> str | None:
    # ...unchanged...


def _raw_manifest(manifest_path: Path) -> object:
    """The raw parsed manifest, or None when it cannot be read. Never raises."""
    try:
        return json.loads(Path(manifest_path).read_text())
    except Exception:
        return None


def raw_profile(manifest_path: Path) -> str | None:
    """Best-effort profile from the raw manifest JSON (for rows whose
    manifest could not be loaded normally). Never raises."""
    return manifest_profile(_raw_manifest(manifest_path))


# ... Task 3's block: ProfileSource, Effective, profile_label, _get, _nonempty_str,
# manifest_performance_id, manifest_artist, manifest_voiced_source,
# manifest_voiced_profile, manifest_tts, effective_profile, target_problem,
# move_target_problem ...


@dataclass(frozen=True)
class Assessment:
    """Every readiness leg's outcome for one package, plus what the run plan
    needs to classify it."""
    reasons: list[str]
    voiced: bool                    # the dj_audio block is present
    profile_reason: str | None      # the profile check's failing reason
    missing_tracks: int
    clips: int
    effective: Effective

    @property
    def ok(self) -> bool:
        return not self.reasons


def profile_change_reason(voiced: str | None, effective: Effective,
                          voiced_source: str | None) -> str:
    """The profile check's reason, one per direction (spec section 4)."""
    head = f"voiced as {profile_label(voiced)}, now {profile_label(effective.profile)}"
    if effective.source == "artist":
        return f'{head} (artist rule "{effective.rule}")'
    if effective.source == "move":
        return f"{head} (move)"
    if voiced_source == "move":
        return f"{head} (move no longer recorded)"
    return f"{head} (delivered profile; no rule or move applies)"


def assess(pkg: Package, config: EmceeConfig, moves: Moves) -> Assessment:
    """All five legs. Callers must have already screened out unsupported
    (pre-v3) packages: this assumes `pkg.manifest()` succeeds and lets
    `UnsupportedPackage`/`EmceeError` (or a bare KeyError from a malformed
    manifest) propagate.

    The profile check runs only when `dj_audio` is present: the voiced
    profile (`manifest_voiced_profile`; a legacy block reads as llama's
    profile) must equal the effective one. A missing `tts`, or a different
    presenter, never fails it."""
    manifest = pkg.manifest()
    effective = effective_profile(config, moves, manifest)
    reasons: list[str] = []

    dj_notes = manifest.get("dj_notes")
    if dj_notes is None or not (pkg.dir / "dj-notes.md").exists():
        reasons.append("no DJ script (dj_notes block + dj-notes.md required)")

    dj_audio = manifest.get("dj_audio")
    profile_reason = None
    if dj_audio is None:
        reasons.append("no DJ audio (unvoiced)")
    else:
        clips = [*dj_audio.get("set_intros", {}).values(), dj_audio.get("outro")]
        missing_clips = [c for c in clips if c and not (pkg.dir / c).exists()]
        if missing_clips:
            reasons.append(
                f"{len(missing_clips)} DJ audio clip(s) missing on disk: "
                + ", ".join(sorted(missing_clips))
            )
        voiced_as = manifest_voiced_profile(manifest)
        if voiced_as != effective.profile:
            profile_reason = profile_change_reason(voiced_as, effective,
                                                   manifest_voiced_source(manifest))
            reasons.append(profile_reason)

    if not (pkg.dir / "broadcast.m3u").exists():
        reasons.append("no broadcast.m3u")

    tracks = manifest.get("tracks", [])
    missing_tracks = [
        t["filename"]
        for t in tracks
        if not (pkg.dir / "audio" / t["filename"]).exists()
    ]
    if missing_tracks:
        reasons.append(
            f"{len(missing_tracks)} of {len(tracks)} audio file(s) missing: "
            + ", ".join(sorted(missing_tracks))
        )

    # One intro per non-encore set plus one outro (script_guard enforces it).
    lead_in_sets = {t.get("set") for t in tracks
                    if isinstance(t, dict) and t.get("set") != "encore"}
    return Assessment(reasons, dj_audio is not None, profile_reason, len(missing_tracks),
                      len(lead_in_sets) + 1, effective)


def readiness(pkg: Package, config: EmceeConfig, moves: Moves) -> tuple[bool, list[str]]:
    """(ok, reasons) over the five legs; see `assess`."""
    a = assess(pkg, config, moves)
    return a.ok, a.reasons


def identity(manifest: object, config: EmceeConfig, moves: Moves) -> dict:
    """The PackageStatus fields that need only the manifest. Never raises,
    so an error row can carry them too."""
    effective = effective_profile(config, moves, manifest)
    return {"profile": effective.profile, "profile_source": effective.source,
            "delivered_profile": manifest_profile(manifest),
            "performance_id": manifest_performance_id(manifest),
            "voiced_by": manifest_voiced_by(manifest),
            "voiced_source": manifest_voiced_source(manifest),
            "voiced_profile": manifest_voiced_profile(manifest),
            "tts": manifest_tts(manifest),
            "move_problem": move_target_problem(config, moves, manifest)}


def package_status(pkg: Package, config: EmceeConfig, moves: Moves) -> PackageStatus:
    """A loadable v3 package's status. May raise on a malformed manifest."""
    manifest = pkg.manifest()
    a = assess(pkg, config, moves)
    return PackageStatus(path=pkg.dir, state="ready" if a.ok else "pending", reasons=a.reasons,
                         voiced=a.voiced, profile_reason=a.profile_reason,
                         missing_tracks=a.missing_tracks, clips=a.clips,
                         **identity(manifest, config, moves))


def unsupported_status(pkg: Package) -> PackageStatus:
    raw = _raw_manifest(pkg.manifest_path)
    version = raw.get("schema_version", "?") if isinstance(raw, dict) else "?"
    profile = manifest_profile(raw)
    return PackageStatus(path=pkg.dir, state="unsupported",
                         reasons=[f"unsupported (v{version} — re-deliver from llama)"],
                         profile=profile, delivered_profile=profile,
                         performance_id=manifest_performance_id(raw))


def scan(station_root: Path, config: EmceeConfig, moves: Moves) -> list[PackageStatus]:
    """Every direct subdirectory of `station_root` containing a
    `manifest.json` is a package; anything else is skipped, and so are
    dot-prefixed dirs (llama's staged replace-voiced swap). A v2-or-earlier
    manifest yields `state="unsupported"`. Read-only.

    A missing or non-directory `station_root` yields an empty list rather
    than raising: `run`/`status` decide whether that is an error.
    """
    root = Path(station_root)
    if not root.is_dir():
        return []
    statuses: list[PackageStatus] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if not (entry / "manifest.json").exists():
            continue
        pkg = Package(entry)
        try:
            pkg.manifest()
        except UnsupportedPackage:
            statuses.append(unsupported_status(pkg))
            continue
        statuses.append(package_status(pkg, config, moves))
    return statuses
```

Keep the bodies of `manifest_profile` and `manifest_voiced_by` exactly as they are today; the `# ...unchanged...` markers above only stand in for them.

- [ ] **Step 5: Implement the CLI threading in `packages/emcee/src/emcee/cli.py`**

Imports: add `from emcee.moves import Moves, load_moves`. Replace the `emcee.station` import with:

```python
from emcee.station import (PackageStatus, identity, manifest_profile, manifest_voiced_by,
                           package_status, raw_profile, scan, unsupported_status)
```

(`readiness` is no longer used in cli; keep `manifest_profile`/`manifest_voiced_by` only if still referenced. Remove an unused name rather than leave it.)

Replace `_scan_broad` and `_station_statuses`, and add `_load_station`:

```python
def _scan_broad(root: Path, config: EmceeConfig, moves: Moves) -> list[PackageStatus]:
    """Re-walk `root` package-by-package, never letting one malformed
    package's readiness check abort the walk.

    `package_io`/`station` deliberately validate no manifest model, so a
    valid-JSON-but-structurally-wrong v3 manifest (a track missing
    `filename`, `dj_audio` not a dict) raises a bare KeyError/AttributeError/
    TypeError out of `assess`. This mirrors `scan`'s walk with every entry
    wrapped, reporting a failure as `state="error"`. It threads the same
    config and moves as `scan`, so a moved package stays moved here too.
    """
    statuses: list[PackageStatus] = []
    for entry in sorted(Path(root).iterdir()):
        if (not entry.is_dir() or entry.name.startswith(".")  # llama's swap dirs
                or not (entry / "manifest.json").exists()):
            continue
        pkg = Package(entry)
        try:
            manifest = pkg.manifest()
        except UnsupportedPackage:
            statuses.append(unsupported_status(pkg))
            continue
        except Exception as exc:
            profile = raw_profile(pkg.manifest_path)
            statuses.append(PackageStatus(path=entry, state="error", reasons=_error_reasons(exc),
                                          profile=profile, delivered_profile=profile))
            continue
        try:
            statuses.append(package_status(pkg, config, moves))
        except Exception as exc:
            statuses.append(PackageStatus(path=entry, state="error", reasons=_error_reasons(exc),
                                          **identity(manifest, config, moves)))
    return statuses


def _station_statuses(root: Path, config: EmceeConfig, moves: Moves) -> list[PackageStatus]:
    """Every package's status under `root`: `station.scan` first; if a
    structurally mangled manifest makes it raise mid-walk, the per-entry
    isolated `_scan_broad`. Both are read-only, so the re-walk is safe."""
    try:
        return scan(root, config, moves)
    except Exception:
        return _scan_broad(root, config, moves)


def _load_station(config: EmceeConfig, root: Path) -> tuple[Moves, list[PackageStatus]]:
    """moves.json first (a bad file is an EmceeError naming it), then the
    scan, then the missing-file guard: all before the caller does any work
    (strict surface 2). Loaded once per command and passed everywhere."""
    moves = load_moves(config.root)
    statuses = _station_statuses(root, config, moves)
    moves.require_present([(s.path.name, s.performance_id, s.voiced_profile)
                           for s in statuses if s.voiced_source == "move"])
    return moves, statuses
```

In `run`: replace `statuses = _station_statuses(root)` with `moves, statuses = _load_station(config, root)`. `moves` is threaded into `_process_one` in Task 5. In `status_cmd`: replace `statuses = _station_statuses(root)` with `_moves, statuses = _load_station(config, root)`.

- [ ] **Step 6: Update the existing call sites listed under Files**

Mechanical: add `from emcee.config import EmceeConfig` (or `load_config` where the test sets `EMCEE_ROOT`) and `from tests.helpers import no_moves` to each file, then pass `(…, EmceeConfig(), no_moves())` / `(…, load_config(), no_moves())` as listed.

- [ ] **Step 7: Run the tests and watch them pass**

Run: `./.venv/bin/python -m pytest packages/emcee/tests/test_profile_readiness.py packages/emcee/tests/test_station.py packages/emcee/tests/test_status_cmd.py -q` → all pass.
Run: `./.venv/bin/python -m pytest -q` → green.

- [ ] **Step 8: Commit**

```bash
git add packages/emcee/src/emcee/station.py packages/emcee/src/emcee/cli.py packages/emcee/tests/
git commit -m "feat(emcee): profile check as a fifth readiness leg; scan threads config and moves"
```

---

### Task 5: One resolution per package, and recording `profile`, `profile_source`, `tts`

Spec: §4 "What emcee records, and readiness" (one resolution, `DJAudioBlock` fields, `TTSRecord`, the backfill script); §3 "Validation at use time" and "A missing file" for `voice`.

**Files:**
- Modify: `packages/emcee/src/emcee/models.py` (`DJAudioBlock` at lines 33-42)
- Modify: `packages/emcee/src/emcee/audio.py` (`_synthesize_dj_audio` return at 355-358; `interleave_broadcast`/`broadcast_m3u_text` type hints at 373, 393; the import at line 21)
- Modify: `packages/emcee/src/emcee/process.py` (module docstring, `resolve_assignment`, `speech_for`, `process_package`; new `Voicing`, `resolve_voicing`, `speech_for_voicing`)
- Modify: `packages/emcee/src/emcee/cli.py` (`_process_one`, `voice_cmd`, `run`'s `_process_one` call, imports)
- Modify: `scripts/backfill_voiced_by.py`, `scripts/test_backfill_voiced_by.py`
- Modify: `packages/emcee/tests/helpers.py` (`voicing_for`)
- Create: `packages/emcee/tests/test_recording.py`
- Modify existing tests (call sites, listed in Step 6)

**Interfaces:**
- Consumes: `station.Effective`, `effective_profile`, `move_target_problem`, `manifest_performance_id`, `manifest_voiced_source`, `manifest_voiced_profile` (Task 3); `moves.Moves`, `load_moves` (Task 2); `tts.resolve.TTSResolution`, `resolve_tts`.
- Produces:
  - `models.DJClips(BaseModel)`: `set_intros: dict[str, str]`, `outro: str`
  - `models.TTSRecord(BaseModel)`: `backend: str`, `model: str | None`, `voice: str` (all required)
  - `models.DJAudioBlock(DJClips)`: `presenter: str | None = None`, and the required, default-free `profile: str | None`, `profile_source: Literal["move", "artist", "llama"]`, `tts: TTSRecord`
  - `audio._synthesize_dj_audio(...) -> DJClips`; `audio.interleave_broadcast(tracks, dj_audio: DJClips)`, `audio.broadcast_m3u_text(tracks, dj_audio: DJClips)`
  - `process.resolve_assignment(config: EmceeConfig, profile: str | None) -> tuple[Presenter | None, str | None]` (takes the EFFECTIVE profile, never a manifest)
  - `@dataclass(frozen=True) process.Voicing`: `effective: Effective`, `presenter: Presenter | None`, `title: str | None`, `resolution: TTSResolution`
  - `process.resolve_voicing(config: EmceeConfig, moves: Moves, manifest: dict) -> Voicing`: raises `EmceeError(move_target_problem)` for an invalid move, and `TTSResolutionError`/`PresenterError` as before
  - `process.speech_for_voicing(config: EmceeConfig, voicing: Voicing) -> tuple[SpeechProvider, Bed | None]`
  - `process.speech_for(config, presenter)` unchanged in signature (used by `emcee say` and tests)
  - `process.process_package(config: EmceeConfig, pkg: Package, speech, force: bool = False, *, voicing: Voicing) -> None`
  - `cli._process_one(config: EmceeConfig, moves: Moves, pkg: Package, force: bool, fresh: Sequence[str] = ()) -> None`
  - tests: `tests.helpers.voicing_for(config: EmceeConfig, pkg: Package) -> Voicing` (house/assignment resolution with `no_moves()`)

- [ ] **Step 1: Write the failing tests**

`packages/emcee/tests/test_recording.py`:

```python
"""What emcee records in dj_audio, and one resolution per package (spec
section 4; use-time move validation and the missing-file guard for
`emcee voice`, spec section 3)."""

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from herder import FakeProvider

import emcee.process as process_mod
from emcee.cli import _process_one, app
from emcee.config import load_config
from emcee.errors import EmceeError
from emcee.models import DJAudioBlock, DJClips
from emcee.moves import load_moves
from emcee.package_io import Package
from emcee.presenters import Presenter, save_presenter
from emcee.station import readiness
from emcee.tts.voxtral import DEFAULT_MODEL as VOX_DEFAULT

from tests.helpers import build_package, no_moves, set_dj_audio, write_moves_file

runner = CliRunner()
TTB = "Tedeschi Trucks Band"
_RULE = ('[assign.profiles.southern]\npresenter = "gregg"\ntitle = "Southern Hour"\n\n'
         '[assign.artists]\n"Tedeschi Trucks Band" = "southern"\n')


def _notes_json() -> str:
    return json.dumps({
        "context": "Spring '73 tour",
        "set_intros": {"1": "Tonight: the Dead at RFK. Opens with Morning Dew.",
                       "2": "China Cat Sunflower leads set two."},
        "outro": "I Know You Rider sends us off. Thanks for listening.",
        "mentioned_songs": ["Morning Dew", "China Cat Sunflower", "I Know You Rider"],
    })


def _home(tmp_path, monkeypatch, assign: str = "",
          tts: str = '[tts]\nbackend = "fake"\nvoice = "house-voice"\n'):
    home = tmp_path / "home"
    station = tmp_path / "station"
    station.mkdir(parents=True)
    home.mkdir()
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    (home / "config.toml").write_text(f'[station]\nroot = "{station}"\n\n{tts}\n{assign}\n')
    return home, station


def _arm_llm(monkeypatch) -> None:
    monkeypatch.setattr(process_mod, "provider_for",
                        lambda settings, task: FakeProvider(completes=[_notes_json()]))


def _gregg(home: Path, **kw) -> None:
    save_presenter(home, Presenter(id="gregg", name="Mr. LeNoir", sex="male",
                                   voice="gregg-preset", character="Smoky.", **kw))


def _dj_audio(pkg_dir: Path) -> dict:
    return json.loads((pkg_dir / "manifest.json").read_text())["dj_audio"]


def _fake_synth(record: list | None = None):
    def synth(pkg_dir, notes, speech, force, chunk=False, lexicon=None, bed=None, rendered=None):
        if record is not None:
            record.append((speech.voice, bed.path.name if bed is not None else None))
        return DJClips(set_intros={k: f"dj-audio/set{k}-intro.mp3" for k in notes.set_intros},
                       outro="dj-audio/99-outro.mp3")
    return synth


def test_a_voiced_package_records_its_profile_source_and_tts(tmp_path, monkeypatch):
    _, station = _home(tmp_path, monkeypatch)
    _arm_llm(monkeypatch)
    pkg_dir = build_package(station, slug="showA", profile=None)

    result = runner.invoke(app, ["voice", str(pkg_dir)])

    assert result.exit_code == 0, result.output
    dj = _dj_audio(pkg_dir)
    assert dj["presenter"] is None
    assert "profile" in dj and dj["profile"] is None          # null serialized, not omitted
    assert dj["profile_source"] == "llama"
    assert dj["tts"] == {"backend": "fake", "model": "fake-model", "voice": "fake-voice"}


def test_voice_persona_title_bed_and_record_all_follow_the_effective_profile(tmp_path, monkeypatch):
    home, station = _home(tmp_path, monkeypatch,
                          _RULE + '\n[assign.profiles.funk]\npresenter = "fred"\n',
                          tts='[tts]\nbackend = "fake"\nvoice = "house-voice"\n'
                              'bed = "/beds/house.wav"\n')
    _gregg(home, bed="/beds/gregg.wav")
    save_presenter(home, Presenter(id="fred", name="Fred", sex="male", voice="fred-preset",
                                   character="x", bed="/beds/fred.wav"))
    _arm_llm(monkeypatch)
    scripted: dict = {}
    real_write = process_mod.write_script

    def spy_write(pkg, provider, presenter, title):
        scripted.update(presenter=presenter.id if presenter else None, title=title)
        return real_write(pkg, provider, presenter, title)

    class Tagged:
        def __init__(self, voice):
            self.voice, self.model = voice, "tagged-model"

        def synthesize(self, *a, **k):
            raise AssertionError("_synthesize_dj_audio is faked")

        def preflight(self):
            pass

        def close(self):
            pass

    synth_calls: list = []
    monkeypatch.setattr(process_mod, "write_script", spy_write)
    monkeypatch.setattr(process_mod, "_synthesize_dj_audio", _fake_synth(synth_calls))
    monkeypatch.setattr(process_mod, "speech_provider_for",
                        lambda config, resolution, *, voice, clone_ref, clone_text: Tagged(voice))
    pkg_dir = build_package(station, slug="ttb", profile="funk", artist=TTB)

    result = runner.invoke(app, ["voice", "ttb"])

    assert result.exit_code == 0, result.output
    assert scripted == {"presenter": "gregg", "title": "Southern Hour"}
    assert synth_calls == [("gregg-preset", "gregg.wav")]
    dj = _dj_audio(pkg_dir)
    assert (dj["presenter"], dj["profile"], dj["profile_source"]) == ("gregg", "southern", "artist")
    assert dj["tts"] == {"backend": "fake", "model": "tagged-model", "voice": "gregg-preset"}


def test_an_artist_rule_voicing_leaves_the_package_ready(tmp_path, monkeypatch):
    home, station = _home(tmp_path, monkeypatch, _RULE)
    _gregg(home)
    _arm_llm(monkeypatch)
    pkg_dir = build_package(station, slug="ttb", profile="funk", artist=TTB)

    assert runner.invoke(app, ["voice", "ttb"]).exit_code == 0

    assert readiness(Package(pkg_dir), load_config(), no_moves()) == (True, [])


def test_process_one_resolves_the_assignment_exactly_once(tmp_path, monkeypatch):
    home, station = _home(tmp_path, monkeypatch, _RULE)
    _gregg(home)
    _arm_llm(monkeypatch)
    pkg_dir = build_package(station, slug="ttb", profile="funk", artist=TTB)
    seen: list = []
    real = process_mod.resolve_assignment

    def counting(config, profile):
        seen.append(profile)
        return real(config, profile)

    monkeypatch.setattr(process_mod, "resolve_assignment", counting)

    _process_one(load_config(), no_moves(), Package(pkg_dir), False)

    assert seen == ["southern"]


def test_a_clone_presenters_tts_voice_is_the_clone_hash(tmp_path, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k-test")
    home, station = _home(tmp_path, monkeypatch, '[assign.profiles.dead]\npresenter = "phil"\n')
    clip = home / "phil.wav"
    clip.write_bytes(b"RIFF-phil-clip")
    save_presenter(home, Presenter(id="phil", name="Phil", sex="male", voice_clone=str(clip),
                                   tts="voxtral", character="x"))
    _arm_llm(monkeypatch)
    monkeypatch.setattr(process_mod, "_synthesize_dj_audio", _fake_synth())
    pkg_dir = build_package(station, slug="gd", profile="dead")

    result = runner.invoke(app, ["voice", "gd"])

    assert result.exit_code == 0, result.output
    assert _dj_audio(pkg_dir)["tts"] == {
        "backend": "voxtral", "model": VOX_DEFAULT,
        "voice": "clone:" + hashlib.sha256(b"RIFF-phil-clip").hexdigest()[:16]}


def test_a_legacy_block_cannot_round_trip_through_the_model():
    with pytest.raises(ValidationError):
        DJAudioBlock.model_validate({"set_intros": {"1": "a"}, "outro": "o", "presenter": "phil"})


def test_voice_under_a_recorded_move_records_the_move(tmp_path, monkeypatch):
    home, station = _home(tmp_path, monkeypatch, '[assign.profiles.southern]\npresenter = "gregg"\n')
    _gregg(home)
    _arm_llm(monkeypatch)
    pkg_dir = build_package(station, slug="ttb", profile="funk", artist=TTB)
    write_moves_file(home, {"GratefulDead/ttb": "southern"})

    assert runner.invoke(app, ["voice", "ttb"]).exit_code == 0

    dj = _dj_audio(pkg_dir)
    assert (dj["profile"], dj["profile_source"], dj["presenter"]) == ("southern", "move", "gregg")
    assert readiness(Package(pkg_dir), load_config(), load_moves(home)) == (True, [])


def _forbid_spend(monkeypatch) -> None:
    def boom(*a, **k):
        raise AssertionError("LLM or TTS spend")
    monkeypatch.setattr(process_mod, "provider_for", boom)
    monkeypatch.setattr(process_mod, "speech_provider_for", boom)


def test_voice_refuses_a_move_whose_target_lost_its_assign_entry(tmp_path, monkeypatch):
    home, station = _home(tmp_path, monkeypatch)
    pkg_dir = build_package(station, slug="ttb", voiced=True, profile="funk", artist=TTB)
    write_moves_file(home, {"GratefulDead/ttb": "southern"})
    before = (pkg_dir / "manifest.json").read_bytes()
    _forbid_spend(monkeypatch)

    result = runner.invoke(app, ["voice", "ttb"])

    assert result.exit_code == 1
    assert 'error: ttb: move target "southern" has no [assign.profiles] entry' in result.stderr
    assert (pkg_dir / "manifest.json").read_bytes() == before


def test_voice_refuses_a_missing_moves_file_for_a_move_voiced_package(tmp_path, monkeypatch):
    home, station = _home(tmp_path, monkeypatch, '[assign.profiles.southern]\npresenter = "gregg"\n')
    pkg_dir = build_package(station, slug="ttb", voiced=True, profile="funk")
    set_dj_audio(pkg_dir, profile="southern", profile_source="move", presenter="gregg")
    before = (pkg_dir / "manifest.json").read_bytes()
    _forbid_spend(monkeypatch)

    result = runner.invoke(app, ["voice", "ttb"])

    assert result.exit_code == 1
    exc = result.exception
    assert isinstance(exc, EmceeError)
    assert str(home / "moves.json") in str(exc) and "1 package(s)" in str(exc)
    assert "rebuild" in "\n".join(exc.details) and "write {}" in "\n".join(exc.details)
    assert (pkg_dir / "manifest.json").read_bytes() == before
```

Append to `scripts/test_backfill_voiced_by.py`:

```python
def test_apply_is_a_raw_update_that_keeps_unknown_keys(tmp_path, capsys):
    p = make(tmp_path, "s1", "Hi, this is K.C.",
             audio={"set_intros": {"1": "a.mp3"}, "outro": "o.mp3", "future_key": {"x": 1}})
    bf.backfill(tmp_path, PRES, apply=True)
    assert load(p)["dj_audio"] == {"set_intros": {"1": "a.mp3"}, "outro": "o.mp3",
                                   "future_key": {"x": 1}, "presenter": "kurt"}
```

- [ ] **Step 2: Run the tests and watch them fail**

Run: `./.venv/bin/python -m pytest packages/emcee/tests/test_recording.py scripts/test_backfill_voiced_by.py -q`
Expected: `ImportError: cannot import name 'DJClips'`. The backfill test fails because the model round trip drops `future_key`.

- [ ] **Step 3: Models and audio**

`packages/emcee/src/emcee/models.py`: change the pydantic import to `from typing import Literal` plus `from pydantic import BaseModel, Field`, and replace `DJAudioBlock` with:

```python
class DJClips(BaseModel):
    """The clip paths `_synthesize_dj_audio` renders (package-relative,
    dj-audio/...). Everything `broadcast.m3u` assembly needs."""

    set_intros: dict[str, str]  # one lead-in clip per non-encore set
    outro: str


class TTSRecord(BaseModel):
    """How one package's clips were synthesized. `backend` comes from the
    TTS resolution; `model`/`voice` from the provider instance -- the same
    values the render-cache key uses, so one record per package is exact.
    `voice` is a preset name, or `clone:<sha256[:16]>` of the reference clip
    (voxtral) or of the clip plus its transcript (mlx_audio)."""

    backend: str
    model: str | None
    voice: str


class DJAudioBlock(DJClips):
    """The manifest's `dj_audio` block as emcee writes it.

    `profile`/`profile_source`/`tts` are required with no defaults, so a
    legacy block (which lacks them) round-tripped through this model fails
    loudly instead of writing `"profile": null` -- which would make the
    package pending. Legacy blocks are only ever updated as raw dicts."""

    # Id of the presenter that voiced this package; None = the house narrator.
    # Always serialized, so a house-voiced manifest carries `"presenter": null`
    # -- distinguishable from a legacy manifest that lacks the key entirely.
    presenter: str | None = None
    profile: str | None                                  # the effective profile voiced as
    profile_source: Literal["move", "artist", "llama"]  # where that profile came from
    tts: TTSRecord                                       # how its clips were synthesized
```

`packages/emcee/src/emcee/audio.py`: import `DJClips` instead of `DJAudioBlock`; `_synthesize_dj_audio`'s return annotation becomes `-> DJClips` and its final statement:

```python
    return DJClips(
        set_intros={key: f"dj-audio/set{key}-intro.mp3" for key in notes.set_intros},
        outro="dj-audio/99-outro.mp3",
    )
```

`interleave_broadcast(tracks: list[dict], dj_audio: DJClips)` and `broadcast_m3u_text(tracks: list[dict], dj_audio: DJClips)` change only their annotations.

- [ ] **Step 4: `packages/emcee/src/emcee/process.py`**

Imports: add `from emcee.models import DJAudioBlock, ScriptNotes, TTSRecord` (replacing the `ScriptNotes` import), `from emcee.moves import Moves`, `from emcee.station import Effective, effective_profile, move_target_problem`, and `from emcee.tts.resolve import TTSResolution, resolve_tts` (replacing the bare `resolve_tts` import).

Module docstring: replace "`resolve_assignment`/`speech_for` are ports of ... from the package's manifest rather than from a `Profile`)." with:

```
`resolve_voicing` resolves one package exactly once -- its effective
profile (station.effective_profile: move > artist rule > llama's), the
presenter and on-air title that profile is assigned, and the TTS backend --
and `process_package` receives that `Voicing` rather than re-deriving any
of it, so voice, persona, title, bed and the recorded profile can never
come from two different resolutions.
```

Replace `resolve_assignment` and `speech_for`, and add `Voicing`, `resolve_voicing`, `_speech_from`, `speech_for_voicing`:

```python
def resolve_assignment(config: EmceeConfig, profile: str | None) -> tuple[Presenter | None, str | None]:
    """(presenter, title) for an EFFECTIVE profile (`Voicing.effective`).
    Takes a profile, never a manifest, so no caller can key it on the
    delivered profile by accident; the rules live in `assignment_for`."""
    view = assignment_for(config, profile)
    if view.presenter is None:
        return None, None
    return load_presenter(config.root, view.presenter), view.title


@dataclass(frozen=True)
class Voicing:
    """Everything one package's voicing is resolved to, once."""
    effective: Effective
    presenter: Presenter | None
    title: str | None
    resolution: TTSResolution


def resolve_voicing(config: EmceeConfig, moves: Moves, manifest: dict) -> Voicing:
    """The single resolution for one package: a recorded move whose target
    cannot be voiced is refused (use-time validation, spec section 3); then
    the effective profile, its presenter and title, and the presenter's TTS.
    Pure apart from reading the presenter's TOML: raises before any spend
    and before `_process_one` clears the manifest."""
    problem = move_target_problem(config, moves, manifest)
    if problem is not None:
        raise EmceeError(problem)
    effective = effective_profile(config, moves, manifest)
    presenter, title = resolve_assignment(config, effective.profile)
    return Voicing(effective, presenter, title, resolve_tts(config, presenter))


def _speech_from(config: EmceeConfig, presenter: Presenter | None, resolution: TTSResolution):
    """(speech_provider, bed) for an already-resolved presenter and TTS
    resolution. A presenter fully owns its voice; with no presenter the
    house [tts] voice/voice_clone/voice_clone_text are used."""
    if presenter is not None:
        voice, clone, text = presenter.voice, presenter.voice_clone, presenter.voice_clone_text
    else:
        voice, clone, text = config.tts.voice, config.tts.voice_clone, config.tts.voice_clone_text
    if not (voice or clone):
        raise EmceeError(
            "voice is active but none is configured: set [tts] voice, "
            "[tts] voice_clone, or give the profile a presenter"
        )
    speech = speech_provider_for(config, resolution, voice=voice, clone_ref=clone,
                                 clone_text=text)
    return speech, _resolve_bed(config, presenter)


def speech_for(config: EmceeConfig, presenter: Presenter | None):
    """(speech_provider, bed) for a presenter (or the house voice), resolving
    its TTS first (`resolve_tts`, pure: an unpinned presenter under an
    mlx_audio house raises here). Used by `emcee say`; package voicing uses
    `speech_for_voicing` so the TTS is resolved once."""
    return _speech_from(config, presenter, resolve_tts(config, presenter))


def speech_for_voicing(config: EmceeConfig, voicing: Voicing):
    """(speech_provider, bed) for one package's `Voicing`."""
    return _speech_from(config, voicing.presenter, voicing.resolution)
```

Replace `process_package`'s signature, the first part of its docstring and its body (keep the `_repair` loop exactly):

```python
def process_package(config: EmceeConfig, pkg: Package, speech, force: bool = False, *,
                    voicing: Voicing) -> None:
    """Script, voice, and broadcast-assemble one delivered package.

    Order: write_script -> render dj-notes.md -> synthesize DJ audio ->
    broadcast.m3u -> rewrite the manifest's dj_notes/dj_audio blocks last.
    The manifest rewrite is the package's success marker: on any failure
    this raises and the manifest is left byte-for-byte as it was.

    A TTS content-filter block (`SpeechBlocked`) is repaired in place by
    `_repair`.

    CALLER CONTRACT: `voicing` is THIS package's `resolve_voicing` result
    and `speech` is `speech_for_voicing(config, voicing)` -- never resolved
    for one package and reused for another. The persona, title and bed all
    come from `voicing.presenter`, and the recorded `dj_audio` from
    `voicing` plus `speech`; nothing here re-resolves, so a hoisted
    resolution would voice, script AND record the wrong presenter
    consistently.
    """
    manifest = pkg.manifest()
    presenter, title = voicing.presenter, voicing.title

    llm_provider = provider_for(config.llm_settings(), "scriptwrite")
    notes = write_script(pkg, llm_provider, presenter, title)
    atomic_write_text(pkg.dir / "dj-notes.md", render_notes_md(notes, manifest))

    bed = _resolve_bed(config, presenter)
    lexicon = load_lexicon(config.root)
    rendered: set[str] = set()
    used: dict[str, int] = {}
    last: dict[str, str] = {}
    repaired: set[str] = set()
    rephraser = None
    while True:
        try:
            clips = _synthesize_dj_audio(pkg.dir, notes, speech, force,
                                         chunk=config.tts.chunk, lexicon=lexicon,
                                         bed=bed, rendered=rendered)
            break
        except SpeechBlocked as blocked:
            if blocked.whole_passage or blocked.segment is None:
                raise
            if rephraser is None:  # built lazily: most packages never need it
                rephraser = provider_for(config.llm_settings(), "rephrase")
            notes = _repair(notes, blocked, manifest, rephraser, used, last, repaired, pkg.dir)
            atomic_write_text(pkg.dir / "dj-notes.md", render_notes_md(notes, manifest))

    atomic_write_text(pkg.dir / "broadcast.m3u",
                      broadcast_m3u_text(manifest["tracks"], clips))

    dj_audio = DJAudioBlock(
        set_intros=clips.set_intros, outro=clips.outro,
        presenter=presenter.id if presenter is not None else None,
        profile=voicing.effective.profile, profile_source=voicing.effective.source,
        tts=TTSRecord(backend=voicing.resolution.backend, model=speech.model,
                      voice=speech.voice))
    rewrite_manifest(pkg, dj_notes=notes, dj_audio=dj_audio)
```

- [ ] **Step 5: `packages/emcee/src/emcee/cli.py`**

Imports: in the `emcee.process` import replace `resolve_assignment, speech_for` with `resolve_voicing, speech_for_voicing`; add `manifest_performance_id, manifest_voiced_profile, manifest_voiced_source` to the `emcee.station` import.

`_process_one`:

```python
def _process_one(config: EmceeConfig, moves: Moves, pkg: Package, force: bool,
                 fresh: Sequence[str] = ()) -> None:
    """Script + voice + broadcast-assemble one package. Shared by `run`'s
    per-package loop and `voice`.

    The package is resolved exactly once (`resolve_voicing`: effective
    profile, presenter, title, TTS) and that `Voicing` is passed through to
    `process_package`; it is never hoisted above a per-package loop.

    Order (strict surface): resolution (including use-time move validation)
    and provider construction, then `speech.preflight()`, THEN the `--fresh`
    unlink, THEN the manifest clear, THEN `process_package` (the first LLM
    spend). So no configuration-only failure can discard a clip or take a
    broadcast-ready package off air.
    """
    manifest = pkg.manifest()
    voicing = resolve_voicing(config, moves, manifest)
    speech, _bed = speech_for_voicing(config, voicing)
    try:
        # ...unchanged: preflight, --fresh unlink, the JUDGMENT CALL comment,
        # rewrite_manifest(pkg, dj_notes=None, dj_audio=None)...
        process_package(config, pkg, speech, force, voicing=voicing)
    finally:
        # ...unchanged close()...
```

In `run`, the processing call becomes `_process_one(config, moves, Package(status.path), force)`.

In `voice_cmd`, replace the lines from `config = load_config()` through `pkg.manifest()  # validates ...` with:

```python
    config = load_config()
    moves = load_moves(config.root)   # a bad file fails here, before any work
    pkg = Package(_resolve_package(config, package, station_root))
    manifest = pkg.manifest()  # validates schema_version >= 3; UnsupportedPackage/EmceeError -> boundary
    if manifest_voiced_source(manifest) == "move":
        moves.require_present([(pkg.dir.name, manifest_performance_id(manifest),
                                manifest_voiced_profile(manifest))])
```

and the processing call becomes `_process_one(config, moves, pkg, force, fresh=stems)`.

- [ ] **Step 6: Update the existing tests**

Add to `packages/emcee/tests/helpers.py`:

```python
def voicing_for(config, pkg):
    """The one resolution `_process_one` would make for `pkg` with no moves:
    for tests that drive `process_package` directly."""
    from emcee.process import resolve_voicing
    return resolve_voicing(config, no_moves(), pkg.manifest())
```

Then, mechanically:

- `packages/emcee/tests/test_process.py`: import `DJClips` instead of `DJAudioBlock` and `voicing_for` from `tests.helpers`. In the four `resolve_assignment` tests pass the profile instead of the manifest: `"prime-dead"`, `"some-other-profile"`, `None`, `"prime-dead"`. Add `voicing=voicing_for(config, pkg)` to every `process_package(...)` call, including `_voice_and_read_presenter`. `make_dj_audio` builds `DJClips(...)`. In `test_process_package_writes_dj_notes_and_audio_and_manifest_last` the expected `dj_audio` gains `"profile": None, "profile_source": "llama", "tts": {"backend": "voxtral", "model": "fake-model", "voice": "fake-voice"}` (an `EmceeConfig()` house resolves to voxtral; model and voice come from the `FakeSpeechProvider` instance).
- `packages/emcee/tests/test_audio.py`: `_process` passes `voicing=voicing_for(config, pkg)`; the expected block at line ~273 gains the same three keys.
- `packages/emcee/tests/test_quality.py:159` and `packages/emcee/tests/test_verify.py:547`: add `voicing=voicing_for(config, pkg)` (`cfg` in test_verify).
- `packages/emcee/tests/test_package_io.py:85`: build `DJAudioBlock(set_intros=..., outro=..., profile="dead", profile_source="llama", tts=TTSRecord(backend="fake", model=None, voice="v"))`, importing `TTSRecord`.
- `packages/emcee/tests/test_run_cmd.py`: `flaky_process_package(config, pkg, speech, force=False, **kwargs)` passes `**kwargs` through; `fake_synth` in `_hoist_probe_setup` returns `DJClips(...)`. Rewrite `test_hoisting_resolve_assignment_and_speech_for_breaks_the_pairing` as:

```python
def test_hoisting_the_voicing_breaks_the_pairing(tmp_path, monkeypatch):
    """Sanity-checks the probe above: replays the hoisted (wrong) call shape
    a mutation would produce -- one resolve_voicing for the whole batch --
    and shows b-show is voiced with alice's voice and bed."""
    from emcee.config import load_config
    from emcee.package_io import Package
    from emcee.process import resolve_voicing, speech_for_voicing
    from tests.helpers import no_moves

    calls = _hoist_probe_setup(tmp_path, monkeypatch)
    config = load_config()
    root = config.station.root
    packages = [Package(root / "a-show"), Package(root / "b-show")]

    voicing = resolve_voicing(config, no_moves(), packages[0].manifest())
    speech, _bed = speech_for_voicing(config, voicing)
    for pkg in packages:
        process_mod.process_package(config, pkg, speech, False, voicing=voicing)

    by_pkg = {name: (voice, bed) for name, voice, bed in calls}
    assert by_pkg["b-show"] == ("alice-voice", "alice.wav")
    assert by_pkg["b-show"] != ("bob-voice", "bob.wav")
```

  In `test_dry_run_house_label_and_no_side_effects` and `test_dry_run_marks_invalid_and_unresolved_presenters_and_completes`, patch `"emcee.cli.speech_for_voicing"` instead of `"emcee.cli.speech_for"`.
- `packages/emcee/tests/test_voice_cmd.py`: `flaky_process_package(config, p, speech, force=False, **kwargs)`; lines 559 and 619 become `_process_one(load_config(), no_moves(), Package(pkg_dir), False)`.
- `packages/emcee/tests/test_mlx_wiring.py` lines 224 and 434, and `packages/emcee/tests/test_verify.py` lines 462 and 482: insert `no_moves()` as the second argument of `_process_one`.

- [ ] **Step 7: `scripts/backfill_voiced_by.py`**

Replace the imports `from emcee.models import DJAudioBlock, ScriptNotes` and `from emcee.package_io import Package, rewrite_manifest` with `import json` (stdlib, at the top) and `from emcee.package_io import Package, atomic_write`. Replace the `if apply:` block with:

```python
        if apply:
            # A raw-dict update, never a DJAudioBlock round trip: a legacy
            # block lacks the model's required profile/profile_source/tts,
            # and unknown keys must survive.
            try:
                data = json.loads(pkg.manifest_path.read_text())
                data["dj_audio"]["presenter"] = ids[0]
                atomic_write(pkg.manifest_path, json.dumps(data, indent=2) + "\n")
            except Exception as exc:  # one bad package must not stop the sweep
                print(f"skip {d.name}: {exc}")
```

Update the module docstring's "`--apply` writes via emcee's `rewrite_manifest`" to "`--apply` updates the raw manifest JSON in place (atomic write)".

- [ ] **Step 8: Run the tests and watch them pass**

Run: `./.venv/bin/python -m pytest packages/emcee/tests/test_recording.py scripts/test_backfill_voiced_by.py -q` → all pass.
Run: `./.venv/bin/python -m pytest -q` → green.
Run: `grep -n "resolve_assignment(config, manifest\|speech_for(config, presenter)" packages/emcee/src/emcee/cli.py` → no output.

- [ ] **Step 9: Commit**

```bash
git add packages/emcee/src/emcee/ packages/emcee/tests/ scripts/backfill_voiced_by.py scripts/test_backfill_voiced_by.py
git commit -m "feat(emcee): resolve each package once and record profile, source and TTS in dj_audio"
```

---

### Task 6: `emcee move`

Spec: §3, all of it.

**Files:**
- Modify: `packages/emcee/src/emcee/cli.py` (`_COMMAND_ORDER`; the new `move` command and helpers, placed after `status_cmd`)
- Modify: `packages/emcee/tests/test_cli_boundary.py:28` (expected command order)
- Create: `packages/emcee/tests/test_move_cmd.py`

**Interfaces:**
- Consumes: `cli._load_station`, `cli._resolve_station_root`, `cli._resolve_package`, `cli._usage`, `cli._typed_error` (existing/Task 4); `moves.record_move`, `clear_move`, `load_moves` (Task 2); `station.assess`, `effective_profile`, `manifest_performance_id`, `manifest_profile`, `profile_label`, `target_problem` (Tasks 3-4).
- Produces: `emcee move <show> <profile> | <show> --delivered | <show> --clear | --list [--station-root P]`; `_COMMAND_ORDER = ["run", "voice", "status", "move", "say", "presenter", "config"]`; `cli._utc_now() -> str` (`%Y-%m-%dT%H:%M:%SZ`).

Decision (the spec leaves it open): every form of `emcee move` requires `[station] root` (or `--station-root`), because each form scans the station for the missing-file guard before it writes or reads.

- [ ] **Step 1: Write the failing tests**

`packages/emcee/tests/test_move_cmd.py`:

```python
"""`emcee move`: record, clear and list one-off profile moves (spec section 3)."""

import fcntl
import json
import os
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

import emcee.moves as moves_mod
import emcee.process as process_mod
from emcee.cli import app
from emcee.errors import EmceeError

from tests.helpers import build_package, set_dj_audio, write_moves_file

runner = CliRunner()
TTB = "Tedeschi Trucks Band"
_SOUTHERN = '[assign.profiles.southern]\npresenter = "gregg"\n'
_RULE = _SOUTHERN + '\n[assign.artists]\n"Tedeschi Trucks Band" = "southern"\n'


@pytest.fixture(autouse=True)
def _no_spend(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("emcee move must make no LLM or TTS call")
    monkeypatch.setattr(process_mod, "provider_for", boom)
    monkeypatch.setattr(process_mod, "speech_provider_for", boom)


def _home(tmp_path, monkeypatch, assign: str = _SOUTHERN):
    home = tmp_path / "home"
    station = tmp_path / "station"
    station.mkdir(parents=True)
    home.mkdir()
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    (home / "config.toml").write_text(
        f'[station]\nroot = "{station}"\n\n[tts]\nbackend = "fake"\nvoice = "v"\n\n{assign}\n')
    return home, station


def _moves(home: Path) -> dict:
    return json.loads((home / "moves.json").read_text())


# --- record ------------------------------------------------------------------------


def test_record_a_move_of_a_voiced_package(tmp_path, monkeypatch):
    home, station = _home(tmp_path, monkeypatch)
    build_package(station, slug="ttb", voiced=True, profile="funk", artist=TTB)

    result = runner.invoke(app, ["move", "ttb", "southern"])

    assert result.exit_code == 0, result.output
    assert "moved: ttb  funk -> southern (pending; voiced on the next emcee run)" in result.stdout
    entry = _moves(home)["GratefulDead/ttb"]
    assert (entry["profile"], entry["package"]) == ("southern", "ttb")
    assert entry["moved_at"].endswith("Z") and len(entry["moved_at"]) == 20


def test_the_identical_move_again_is_unchanged(tmp_path, monkeypatch):
    home, station = _home(tmp_path, monkeypatch)
    build_package(station, slug="ttb", voiced=True, profile="funk")
    runner.invoke(app, ["move", "ttb", "southern"])
    before = (home / "moves.json").read_bytes()

    result = runner.invoke(app, ["move", "ttb", "southern"])

    assert result.exit_code == 0
    assert result.stdout.startswith("unchanged: ttb")
    assert (home / "moves.json").read_bytes() == before


def test_an_unvoiced_package_says_when_it_will_be_voiced(tmp_path, monkeypatch):
    _, station = _home(tmp_path, monkeypatch)
    build_package(station, slug="ttb", profile="funk")

    result = runner.invoke(app, ["move", "ttb", "southern"])

    assert ("moved: ttb  funk -> southern (unvoiced; voiced as southern on the next emcee run)"
            in result.stdout)


def test_an_exemption_from_a_rule_needs_no_assign_entry_and_reads_ready(tmp_path, monkeypatch):
    home, station = _home(tmp_path, monkeypatch, _RULE)          # no [assign.profiles.funk]
    build_package(station, slug="ttb", voiced=True, profile="funk", artist=TTB)

    result = runner.invoke(app, ["move", "ttb", "--delivered"])

    assert result.exit_code == 0, result.output
    assert "moved: ttb  southern -> funk (ready; already voiced as funk)" in result.stdout
    assert _moves(home)["GratefulDead/ttb"]["profile"] == "funk"


def test_a_move_naming_the_delivered_profile_needs_no_assign_entry(tmp_path, monkeypatch):
    home, station = _home(tmp_path, monkeypatch, _RULE)
    build_package(station, slug="ttb", voiced=True, profile="funk", artist=TTB)

    assert runner.invoke(app, ["move", "ttb", "funk"]).exit_code == 0
    assert _moves(home)["GratefulDead/ttb"]["profile"] == "funk"


def test_delivered_records_null_for_a_package_with_no_profile(tmp_path, monkeypatch):
    home, station = _home(tmp_path, monkeypatch, _RULE)
    build_package(station, slug="ttb", voiced=True, profile=None, artist=TTB)

    assert runner.invoke(app, ["move", "ttb", "--delivered"]).exit_code == 0
    assert _moves(home)["GratefulDead/ttb"]["profile"] is None


def test_other_entries_unknown_keys_survive(tmp_path, monkeypatch):
    home, station = _home(tmp_path, monkeypatch)
    (home / "moves.json").write_text(json.dumps(
        {"Other/1": {"profile": "southern", "package": "other", "note": "keep"}}))
    build_package(station, slug="ttb", profile="funk")

    assert runner.invoke(app, ["move", "ttb", "southern"]).exit_code == 0
    assert _moves(home)["Other/1"] == {"profile": "southern", "package": "other", "note": "keep"}


def test_the_lock_is_held_around_load_modify_write(tmp_path, monkeypatch):
    home, station = _home(tmp_path, monkeypatch)
    build_package(station, slug="ttb", profile="funk")
    seen: list = []

    def held() -> bool:
        fd = os.open(home / "moves.json.lock", os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        else:
            return False
        finally:
            os.close(fd)

    real_read, real_write = moves_mod.read_moves_data, moves_mod.write_moves
    monkeypatch.setattr(moves_mod, "read_moves_data",
                        lambda root: (seen.append(("read", held())), real_read(root))[1])
    monkeypatch.setattr(moves_mod, "write_moves",
                        lambda root, data: (seen.append(("write", held())), real_write(root, data))[1])

    assert runner.invoke(app, ["move", "ttb", "southern"]).exit_code == 0
    assert seen == [("read", True), ("write", True)]


# --- refusals leave moves.json byte-for-byte unchanged ------------------------------


def _refusal_station(tmp_path, monkeypatch, existing: bool):
    home, station = _home(tmp_path, monkeypatch)
    build_package(station, slug="ttb", profile="funk")
    nopid = build_package(station, slug="nopid", profile="funk")
    m = json.loads((nopid / "manifest.json").read_text())
    del m["source"]["performance_id"]
    (nopid / "manifest.json").write_text(json.dumps(m))
    old = station / "old"
    old.mkdir()
    (old / "manifest.json").write_text(json.dumps({"schema_version": 2}))
    junk = station / "junk"
    junk.mkdir()
    (junk / "manifest.json").write_text("{not json")
    if existing:
        (home / "moves.json").write_text(json.dumps(
            {"Other/1": {"profile": "southern", "package": "other"}}))
    return home


@pytest.mark.parametrize("existing", [True, False], ids=["file-present", "file-absent"])
@pytest.mark.parametrize("args, why", [
    (["move", "ttb", "bluegrass"], "[assign.profiles.bluegrass]"),
    (["move", "nopid", "southern"], "performance_id"),
    (["move", "old", "southern"], "unsupported"),
    (["move", "junk", "southern"], "not valid JSON"),
])
def test_each_refusal_exits_1_and_leaves_the_file_alone(tmp_path, monkeypatch, existing, args, why):
    home = _refusal_station(tmp_path, monkeypatch, existing)
    before = (home / "moves.json").read_bytes() if existing else None

    result = runner.invoke(app, args)

    assert result.exit_code == 1
    assert isinstance(result.exception, EmceeError)
    assert why in str(result.exception)
    if existing:
        assert (home / "moves.json").read_bytes() == before
    else:
        assert not (home / "moves.json").exists()


@pytest.mark.parametrize("args", [["move"], ["move", "ttb"], ["move", "ttb", "southern", "--clear"],
                                  ["move", "ttb", "--delivered", "--clear"], ["move", "--list", "ttb"]])
def test_usage_errors_exit_2(tmp_path, monkeypatch, args):
    _home(tmp_path, monkeypatch)
    assert runner.invoke(app, args).exit_code == 2


# --- the missing-file guard ------------------------------------------------------------


@pytest.mark.parametrize("args", [["move", "fresh", "southern"], ["move", "--list"],
                                  ["move", "moved", "--clear"]])
def test_a_missing_file_with_a_move_voiced_package_refuses_and_writes_nothing(tmp_path, monkeypatch,
                                                                              args):
    home, station = _home(tmp_path, monkeypatch)
    moved = build_package(station, slug="moved", voiced=True, profile="funk")
    set_dj_audio(moved, profile="southern", profile_source="move", presenter="gregg")
    build_package(station, slug="fresh", profile="funk")

    result = runner.invoke(app, args)

    assert result.exit_code == 1
    assert str(home / "moves.json") in str(result.exception)
    assert "1 package(s)" in str(result.exception)
    assert not (home / "moves.json").exists()


# --- --clear -----------------------------------------------------------------------------


def test_clear_prints_the_id_and_leaves_an_empty_object(tmp_path, monkeypatch):
    home, station = _home(tmp_path, monkeypatch)
    build_package(station, slug="ttb", profile="funk")
    write_moves_file(home, {"GratefulDead/ttb": "southern"})

    result = runner.invoke(app, ["move", "ttb", "--clear"])

    assert result.exit_code == 0, result.output
    assert "cleared: GratefulDead/ttb" in result.stdout
    assert _moves(home) == {}


def test_a_stale_move_is_cleared_by_id_or_by_its_recorded_package_name(tmp_path, monkeypatch):
    home, _ = _home(tmp_path, monkeypatch)
    write_moves_file(home, {"Gone/gone-1999": "southern", "Gone/gone-2000": "southern"})

    first = runner.invoke(app, ["move", "Gone/gone-1999", "--clear"])
    second = runner.invoke(app, ["move", "gone-2000", "--clear"])   # no live package has this name

    assert "cleared: Gone/gone-1999" in first.stdout
    assert "cleared: Gone/gone-2000" in second.stdout
    assert _moves(home) == {}


def test_recorded_entries_are_matched_before_live_packages(tmp_path, monkeypatch):
    home, station = _home(tmp_path, monkeypatch)
    build_package(station, slug="abc", profile="funk")              # live, pid GratefulDead/abc
    write_moves_file(home, {"Old/abc": "southern"})                # stale, recorded package "abc"

    result = runner.invoke(app, ["move", "abc", "--clear"])

    assert "cleared: Old/abc" in result.stdout


def test_ambiguous_recorded_matches_are_refused_with_their_ids(tmp_path, monkeypatch):
    home, _ = _home(tmp_path, monkeypatch)
    write_moves_file(home, {"Old/abc": "southern", "Older/abc": "southern"})
    before = (home / "moves.json").read_bytes()

    result = runner.invoke(app, ["move", "abc", "--clear"])

    assert result.exit_code == 1
    assert result.exception.details == ["Old/abc", "Older/abc"]
    assert (home / "moves.json").read_bytes() == before


# --- --list ------------------------------------------------------------------------------


def test_list_shows_target_delivered_missing_and_no_assign_entry(tmp_path, monkeypatch):
    home, station = _home(tmp_path, monkeypatch)
    build_package(station, slug="ttb", voiced=True, profile="funk")
    build_package(station, slug="gd", voiced=True, profile="dead")
    write_moves_file(home, {"GratefulDead/ttb": "southern", "GratefulDead/gd": "jazz",
                            "Gone/gone-1999": "southern"})

    out = runner.invoke(app, ["move", "--list"]).stdout.splitlines()

    assert out == [
        "gone-1999  Gone/gone-1999  southern (from ?)  missing",
        "gd  GratefulDead/gd  jazz (from dead)  [no assign entry]",
        "ttb  GratefulDead/ttb  southern (from funk)",
    ]


def test_list_with_no_moves(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    assert runner.invoke(app, ["move", "--list"]).stdout.strip() == "no moves recorded"


# --- a move survives llama's --replace-voiced -----------------------------------------------


def test_a_move_survives_a_replace_voiced_redelivery(tmp_path, monkeypatch):
    home, station = _home(tmp_path, monkeypatch)
    build_package(station, slug="ttb", voiced=True, profile="funk")
    assert runner.invoke(app, ["move", "ttb", "southern"]).exit_code == 0

    shutil.rmtree(station / "ttb")                                  # llama replaces the dir wholesale
    build_package(station, slug="ttb", voiced=False, profile="funk")  # same performance_id

    rows = {r["slug"]: r for r in json.loads(runner.invoke(app, ["status", "--json"]).stdout)}
    assert (rows["ttb"]["profile"], rows["ttb"]["state"]) == ("southern", "pending")
    dry = runner.invoke(app, ["run", "--dry-run"])
    assert "would voice: ttb  southern  gregg" in dry.stdout
```

In `packages/emcee/tests/test_cli_boundary.py`, the expected list becomes `["run", "voice", "status", "move", "say", "presenter", "config"]`.

- [ ] **Step 2: Run the tests and watch them fail**

Run: `./.venv/bin/python -m pytest packages/emcee/tests/test_move_cmd.py packages/emcee/tests/test_cli_boundary.py -q`
Expected: `move` tests fail with exit code 2 (`No such command 'move'`); the boundary test fails on the list.

- [ ] **Step 3: Implement in `packages/emcee/src/emcee/cli.py`**

`_COMMAND_ORDER = ["run", "voice", "status", "move", "say", "presenter", "config"]`.

Imports: add `from datetime import datetime, timezone`; extend the `emcee.moves` import to `Moves, clear_move, load_moves, record_move`; make sure the `emcee.station` import includes `assess, effective_profile, manifest_performance_id, manifest_profile, profile_label, target_problem` (add whichever Tasks 4-5 left out).

Add after `status_cmd`:

```python
def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _echo_moves(config: EmceeConfig, moves: Moves, statuses: list[PackageStatus]) -> None:
    """`move --list`: one row per recorded move, sorted by performance_id:
    package, id, target (from delivered), `missing` when no scanned package
    carries the id, `[no assign entry]` when the move fails use-time
    validation."""
    if not moves.entries:
        typer.echo("no moves recorded")
        return
    by_pid: dict[str, PackageStatus] = {}
    for s in statuses:
        if s.performance_id is not None:
            by_pid.setdefault(s.performance_id, s)
    for pid, entry in sorted(moves.entries.items()):
        target = entry["profile"]
        package = entry.get("package")
        name = package if isinstance(package, str) and package else pid
        status = by_pid.get(pid)
        if status is None:
            line = f"{name}  {pid}  {profile_label(target)} (from ?)  missing"
            bad = target is not None and target not in config.assign.profiles
        else:
            line = f"{name}  {pid}  {profile_label(target)} (from {profile_label(status.delivered_profile)})"
            bad = target_problem(config, target, status.delivered_profile) is not None
        if bad:
            line += "  [no assign entry]"
        typer.echo(line)


@app.command("move")
def move_cmd(
    show: str = typer.Argument(
        None, help="A package directory, or a package's name (or unique substring) under "
                   "\\[station] root; for --clear also a recorded performance_id or package name"),
    profile: str = typer.Argument(None, help="The profile to voice this show as"),
    delivered: bool = typer.Option(
        False, "--delivered",
        help="Move back to the profile llama delivered it under (exempts it from an artist rule)"),
    clear: bool = typer.Option(False, "--clear", help="Remove this show's recorded move"),
    list_moves: bool = typer.Option(False, "--list", help="List every recorded move"),
    station_root: Path = typer.Option(
        None, "--station-root", help="Override \\[station] root for this invocation"),
):
    """Record, clear or list a one-off profile move (`moves.json`).

    `emcee move <show> <profile>` voices that show as `<profile>` from the
    next `emcee run` on, whatever llama delivered it under; `--delivered`
    moves it back to llama's profile, which is how one show is exempted from
    an `\\[assign.artists]` rule. The target needs its own
    `\\[assign.profiles.<name>]` entry unless it is the delivered profile.
    Moves are keyed by the manifest's `source.performance_id`, so they
    survive llama's `--replace-voiced` re-delivery. No LLM or TTS call is
    made: the show is re-voiced by the next `emcee run`.
    """
    if list_moves:
        if show is not None or profile is not None or delivered or clear:
            _usage("--list takes no package, profile, --delivered or --clear")
    else:
        if show is None:
            _usage("give a package and one of <profile>, --delivered, --clear; or --list")
        if sum([profile is not None, delivered, clear]) != 1:
            _usage("give exactly one of <profile>, --delivered, --clear")

    config = load_config()
    root = _resolve_station_root(config, station_root)
    moves, statuses = _load_station(config, root)   # bad or missing moves.json: refuse first

    if list_moves:
        _echo_moves(config, moves, statuses)
        return

    if clear:
        def live_performance_id() -> str:
            pkg = Package(_resolve_package(config, show, station_root))
            pid = manifest_performance_id(pkg.manifest())
            if pid is None:
                raise EmceeError(f"{pkg.dir.name} has no source.performance_id; "
                                 "no move can be recorded for it")
            return pid

        typer.echo(f"cleared: {clear_move(config.root, show, live_performance_id)}")
        return

    pkg = Package(_resolve_package(config, show, station_root))
    manifest = pkg.manifest()  # unsupported or unreadable: EmceeError -> exit 1
    pid = manifest_performance_id(manifest)
    if pid is None:
        raise EmceeError(f"{pkg.dir.name} has no source.performance_id; "
                         "a move cannot be recorded for it")
    delivered_profile = manifest_profile(manifest)
    target = delivered_profile if delivered else profile
    if target_problem(config, target, delivered_profile) is not None:
        raise EmceeError(
            f"no [assign.profiles.{target}] entry: a move must target an assigned profile "
            f"or the delivered one ({profile_label(delivered_profile)})")
    before = effective_profile(config, moves, manifest).profile
    if not record_move(config.root, pid, target, pkg.dir.name, moved_at=_utc_now()):
        typer.echo(f"unchanged: {pkg.dir.name}  move to {profile_label(target)} already recorded")
        return
    try:
        a = assess(pkg, config, load_moves(config.root))
    except Exception as exc:
        typer.echo(f"moved: {pkg.dir.name}  {profile_label(before)} -> {profile_label(target)} "
                   f"(state unknown: {_typed_error(exc)})")
        return
    after = profile_label(a.effective.profile)
    if not a.voiced:
        state = f"unvoiced; voiced as {after} on the next emcee run"
    elif a.ok:
        state = f"ready; already voiced as {after}"
    else:
        state = "pending; voiced on the next emcee run"
    typer.echo(f"moved: {pkg.dir.name}  {profile_label(before)} -> {after} ({state})")
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `./.venv/bin/python -m pytest packages/emcee/tests/test_move_cmd.py packages/emcee/tests/test_cli_boundary.py -q` → all pass.
Run: `./.venv/bin/python -m pytest -q` → green.

- [ ] **Step 5: Commit**

```bash
git add packages/emcee/src/emcee/cli.py packages/emcee/tests/test_move_cmd.py packages/emcee/tests/test_cli_boundary.py
git commit -m "feat(emcee): emcee move to record, clear and list one-off profile moves"
```

---

### Task 7: The pause before `emcee run`

Spec: §5 "The pause before `emcee run`", §3 "Stale moves", "Validation at use time" (run's error row); strict surface 1.

**Files:**
- Modify: `packages/emcee/src/emcee/cli.py` (`run` rewritten; new helpers `_stdin_is_tty`, `_plural`, `_stale_moves`, `_stale_note`, `_presenter_or_marker`, `_plan_tts_cell`, `_echo_plan`; `_dry_run_marker` refactored onto `_presenter_or_marker`)
- Create: `packages/emcee/tests/test_run_plan.py`
- Modify existing tests: `packages/emcee/tests/test_run_cmd.py`, `packages/emcee/tests/test_mlx_wiring.py`, `packages/emcee/tests/test_handshake.py` (Step 4)

**Interfaces:**
- Consumes: `PackageStatus.voiced`, `.profile_reason`, `.missing_tracks`, `.clips`, `.move_problem`, `.performance_id` (Task 4); `_load_station` (Task 4); `_process_one(config, moves, pkg, force)` (Task 5); `assignment_for`, `presenter_label`, `resolve_tts`, `TTSResolutionError`, `load_presenter`, `PresenterError`, `_presenter_file` (existing).
- Produces:
  - `emcee run --yes/-y`
  - `cli._stdin_is_tty() -> bool` (tests patch it)
  - `cli._stale_moves(moves: Moves, statuses: list[PackageStatus]) -> int`, `cli._stale_note(n: int) -> str` (Task 8 reuses both)
  - `cli._plural(n: int, word: str) -> str`
  - `cli._plan_tts_cell(config, presenter_id: str | None) -> tuple[str, str]`
  - `cli._echo_plan(config: EmceeConfig, to_voice: list[PackageStatus], stale: int) -> None` (stderr)

Plan layout. The spec's example shows a single re-voice reason; this layout reduces to the same content and also fits several reasons. Every line goes to stderr:

```
to voice: 4 packages, 12 clips
  new        1
  re-voice   2
    voiced as funk, now southern (artist rule "Tedeschi Trucks Band"): 2
      ttb1
      ttb2
  repair     1
      emerson
TTS:
  gregg (Mr. LeNoir)  fake  -  2 packages
  house               fake  -  2 packages
note: 1 recorded move(s) match no package (emcee move --list)
```

Categories with a zero count are omitted. `new` packages are counted, not listed. TTS lines are sorted by presenter id, with `house` last. A model of `None` prints `-`.

- [ ] **Step 1: Write the failing tests**

`packages/emcee/tests/test_run_plan.py`:

```python
"""`emcee run`'s pause: the plan, the question and --yes (spec section 5;
strict surface 1: no LLM or TTS call before the plan is printed and
confirmed)."""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from herder import FakeProvider

import emcee.cli as cli_mod
import emcee.process as process_mod
from emcee.cli import app
from emcee.presenters import Presenter, save_presenter

from tests.helpers import build_package, set_dj_audio, write_moves_file

runner = CliRunner()
TTB = "Tedeschi Trucks Band"
_ASSIGN = ('[assign.profiles.southern]\npresenter = "gregg"\n\n'
           '[assign.artists]\n"Tedeschi Trucks Band" = "southern"\n')


def _notes_json() -> str:
    return json.dumps({
        "context": "Spring '73 tour",
        "set_intros": {"1": "Tonight: the Dead at RFK. Opens with Morning Dew.",
                       "2": "China Cat Sunflower leads set two."},
        "outro": "I Know You Rider sends us off. Thanks for listening.",
        "mentioned_songs": ["Morning Dew", "China Cat Sunflower", "I Know You Rider"],
    })


def _home(tmp_path, monkeypatch, assign: str = _ASSIGN):
    home = tmp_path / "home"
    station = tmp_path / "station"
    station.mkdir(parents=True)
    home.mkdir()
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    (home / "config.toml").write_text(
        f'[station]\nroot = "{station}"\n\n[tts]\nbackend = "fake"\nvoice = "house-voice"\n\n'
        f'{assign}\n')
    return home, station


def _gregg(home: Path) -> None:
    save_presenter(home, Presenter(id="gregg", name="Mr. LeNoir", sex="male",
                                   voice="gregg-preset", character="Smoky."))


def _spend(monkeypatch) -> list[str]:
    """Voicing works (fake LLM + fake TTS); records every LLM task asked for."""
    tasks: list[str] = []

    def fake(settings, task):
        tasks.append(task)
        return FakeProvider(completes=[_notes_json()])

    monkeypatch.setattr(process_mod, "provider_for", fake)
    return tasks


def _forbid_spend(monkeypatch) -> None:
    def boom(*a, **k):
        raise AssertionError("LLM or TTS spend before confirmation")
    monkeypatch.setattr(process_mod, "provider_for", boom)
    monkeypatch.setattr(process_mod, "speech_provider_for", boom)


def _tty(monkeypatch) -> None:
    monkeypatch.setattr(cli_mod, "_stdin_is_tty", lambda: True)


def _lines(text: str) -> list[str]:
    return [" ".join(line.split()) for line in text.splitlines()]


def _station(tmp_path, monkeypatch):
    """fresh: unvoiced (new); ttb1/ttb2: voiced as funk, now southern by rule
    (re-voice); emerson: voiced, broadcast.m3u gone (repair); holes: unvoiced
    with one track's audio missing (skip)."""
    home, station = _home(tmp_path, monkeypatch)
    _gregg(home)
    build_package(station, slug="fresh", profile="dead")
    build_package(station, slug="ttb1", voiced=True, profile="funk", artist=TTB)
    build_package(station, slug="ttb2", voiced=True, profile="funk", artist=TTB)
    emerson = build_package(station, slug="emerson", voiced=True, profile="dead")
    (emerson / "broadcast.m3u").unlink()
    holes = build_package(station, slug="holes", profile="dead")
    sorted((holes / "audio").iterdir())[0].unlink()
    return home, station


def _manifests(station: Path) -> dict[str, bytes]:
    return {d.name: (d / "manifest.json").read_bytes() for d in sorted(station.iterdir())}


# --- the plan ---------------------------------------------------------------------------


def test_the_plan_names_every_category_and_counts_clips_exactly(tmp_path, monkeypatch):
    _station(tmp_path, monkeypatch)
    _forbid_spend(monkeypatch)

    result = runner.invoke(app, ["run", "--dry-run"])

    assert result.exit_code == 0, result.output
    err = _lines(result.stderr)
    assert "to voice: 4 packages, 12 clips" in err
    assert "new 1" in err and "fresh" not in err                  # new: counted, not listed
    assert "re-voice 2" in err
    assert 'voiced as funk, now southern (artist rule "Tedeschi Trucks Band"): 2' in err
    assert "ttb1" in err and "ttb2" in err
    assert "repair 1" in err and "emerson" in err
    assert "TTS:" in err
    assert "gregg (Mr. LeNoir) fake - 2 packages" in err
    assert "house fake - 2 packages" in err
    assert "skip holes: 1 audio file(s) missing; re-deliver from llama" in result.stdout
    assert "would voice: holes" not in result.stdout
    assert "4 package(s) would be voiced" in result.stdout
    assert "Proceed?" not in result.output


def test_yes_voices_exactly_the_planned_packages(tmp_path, monkeypatch):
    _, station = _station(tmp_path, monkeypatch)
    holes_before = (station / "holes" / "manifest.json").read_bytes()
    tasks = _spend(monkeypatch)

    result = runner.invoke(app, ["run", "--yes"])

    assert result.exit_code == 0, result.output
    assert "to voice: 4 packages, 12 clips" in result.stderr
    assert "Proceed?" not in result.output
    voiced = {line.split(": ", 1)[1] for line in result.stdout.splitlines()
              if line.startswith("voiced: ")}
    assert voiced == {"fresh", "ttb1", "ttb2", "emerson"}
    assert tasks.count("scriptwrite") == 4
    assert (station / "holes" / "manifest.json").read_bytes() == holes_before
    dj = json.loads((station / "ttb1" / "manifest.json").read_text())["dj_audio"]
    assert (dj["presenter"], dj["profile"], dj["profile_source"]) == ("gregg", "southern", "artist")
    states = {r["slug"]: r["state"]
              for r in json.loads(runner.invoke(app, ["status", "--json"]).stdout)}
    assert states == {"fresh": "ready", "ttb1": "ready", "ttb2": "ready", "emerson": "ready",
                      "holes": "pending"}


def test_run_voices_from_the_one_scan_it_planned_from(tmp_path, monkeypatch):
    _station(tmp_path, monkeypatch)
    _spend(monkeypatch)
    scans: list[int] = []
    real = cli_mod._station_statuses
    monkeypatch.setattr(cli_mod, "_station_statuses",
                        lambda *a, **k: (scans.append(1), real(*a, **k))[1])

    assert runner.invoke(app, ["run", "--yes"]).exit_code == 0
    assert scans == [1]


# --- the question -------------------------------------------------------------------------


def test_a_yes_at_the_prompt_voices(tmp_path, monkeypatch):
    _station(tmp_path, monkeypatch)
    tasks = _spend(monkeypatch)
    _tty(monkeypatch)

    result = runner.invoke(app, ["run"], input="y\n")

    assert result.exit_code == 0, result.output
    assert "Proceed? [y/N]" in result.stderr
    assert tasks.count("scriptwrite") == 4


def test_a_declined_prompt_voices_nothing_and_exits_0(tmp_path, monkeypatch):
    _, station = _station(tmp_path, monkeypatch)
    before = _manifests(station)
    _forbid_spend(monkeypatch)
    _tty(monkeypatch)

    result = runner.invoke(app, ["run"], input="n\n")

    assert result.exit_code == 0, result.output
    assert "to voice: 4 packages" in result.stderr and "Proceed? [y/N]" in result.stderr
    assert "nothing voiced" in result.stdout
    assert "voiced:" not in result.stdout
    assert _manifests(station) == before


def test_eof_at_the_prompt_spends_nothing(tmp_path, monkeypatch):     # Review Focus 3
    _, station = _station(tmp_path, monkeypatch)
    before = _manifests(station)
    _forbid_spend(monkeypatch)
    _tty(monkeypatch)

    result = runner.invoke(app, ["run"], input="")

    assert result.exit_code != 0
    assert _manifests(station) == before


def test_no_tty_and_no_yes_refuses_after_the_plan_and_spends_nothing(tmp_path, monkeypatch):
    _, station = _station(tmp_path, monkeypatch)
    before = _manifests(station)
    _forbid_spend(monkeypatch)

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 1
    assert "to voice: 4 packages, 12 clips" in result.stderr
    assert "error: refusing to voice without confirmation; pass --yes" in result.stderr
    assert "Proceed?" not in result.output
    assert _manifests(station) == before


def test_dry_run_prints_the_plan_and_never_asks(tmp_path, monkeypatch):
    _, station = _station(tmp_path, monkeypatch)
    before = _manifests(station)
    _forbid_spend(monkeypatch)
    _tty(monkeypatch)

    plain = runner.invoke(app, ["run", "--dry-run"])
    both = runner.invoke(app, ["run", "--yes", "--dry-run"])

    for result in (plain, both):
        assert result.exit_code == 0, result.output
        assert "to voice: 4 packages" in result.stderr
        assert "Proceed?" not in result.output
        assert "voiced:" not in result.stdout
    assert _manifests(station) == before


def test_nothing_to_voice_means_no_plan_and_no_prompt(tmp_path, monkeypatch):
    _, station = _home(tmp_path, monkeypatch)
    build_package(station, slug="done", voiced=True, profile="dead")
    _forbid_spend(monkeypatch)
    _tty(monkeypatch)

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 0, result.output
    assert "to voice:" not in result.output and "Proceed?" not in result.output
    assert "0 package(s) voiced" in result.stdout


# --- exit codes ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["declined", "nothing", "proceeded"])
def test_any_error_row_exits_1(tmp_path, monkeypatch, mode):
    _, station = _home(tmp_path, monkeypatch)
    bad = station / "bad"
    bad.mkdir()
    (bad / "manifest.json").write_text(json.dumps(
        {"schema_version": 3, "source": {"profile": "dead"}, "tracks": [{}]}))
    if mode != "nothing":
        build_package(station, slug="fresh", profile="dead")
    if mode == "proceeded":
        _spend(monkeypatch)
        result = runner.invoke(app, ["run", "--yes"])
    else:
        _forbid_spend(monkeypatch)
        _tty(monkeypatch)
        result = runner.invoke(app, ["run"], input="n\n")

    assert result.exit_code == 1
    assert "error: bad:" in result.stderr
    if mode == "proceeded":
        assert "voiced: fresh" in result.stdout


def test_a_move_whose_target_lost_its_entry_is_an_error_row_and_others_still_voice(tmp_path,
                                                                                    monkeypatch):
    home, station = _home(tmp_path, monkeypatch, assign="")      # no [assign.profiles.southern]
    build_package(station, slug="moved", voiced=True, profile="funk")
    build_package(station, slug="fresh", profile="dead")
    write_moves_file(home, {"GratefulDead/moved": "southern"})
    _spend(monkeypatch)

    result = runner.invoke(app, ["run", "--yes"])

    assert result.exit_code == 1
    assert 'error: moved: move target "southern" has no [assign.profiles] entry' in result.stderr
    assert "to voice: 1 package, 3 clips" in result.stderr
    assert "voiced: fresh" in result.stdout and "voiced: moved" not in result.stdout


# --- notes, markers, and the malformed-manifest path ---------------------------------------


def test_a_stale_move_is_noted_with_or_without_a_plan(tmp_path, monkeypatch):
    home, station = _home(tmp_path, monkeypatch)
    write_moves_file(home, {"Gone/gone-1999": "southern"})
    build_package(station, slug="fresh", profile="dead")
    _forbid_spend(monkeypatch)
    note = "note: 1 recorded move(s) match no package (emcee move --list)"

    assert note in runner.invoke(app, ["run", "--dry-run"]).stderr

    shutil.rmtree(station / "fresh")
    build_package(station, slug="done", voiced=True, profile="dead")
    nothing = runner.invoke(app, ["run"])
    assert nothing.exit_code == 0
    assert note in nothing.stderr


def test_the_plan_marks_a_presenter_that_cannot_be_loaded(tmp_path, monkeypatch):   # Review Focus 4
    _, station = _home(tmp_path, monkeypatch)                    # no presenters/gregg.toml
    build_package(station, slug="ttb", profile="funk", artist=TTB)
    _forbid_spend(monkeypatch)

    result = runner.invoke(app, ["run", "--dry-run"])

    assert "gregg [missing presenters/gregg.toml] 1 package" in _lines(result.stderr)


def test_a_malformed_manifest_does_not_put_a_moved_ready_package_in_the_plan(tmp_path, monkeypatch):
    home, station = _home(tmp_path, monkeypatch)
    moved = build_package(station, slug="moved", voiced=True, profile="funk")
    set_dj_audio(moved, profile="southern", profile_source="move", presenter="gregg")
    write_moves_file(home, {"GratefulDead/moved": "southern"})
    bad = station / "bad"
    bad.mkdir()
    (bad / "manifest.json").write_text(json.dumps(
        {"schema_version": 3, "source": {"profile": "dead"}, "tracks": [{}]}))
    build_package(station, slug="fresh", profile="dead")
    _forbid_spend(monkeypatch)

    result = runner.invoke(app, ["run", "--dry-run"])

    assert "to voice: 1 package, 3 clips" in result.stderr
    assert "moved" not in _lines(result.stderr)
    assert "would voice: moved" not in result.stdout
```

- [ ] **Step 2: Run the tests and watch them fail**

Run: `./.venv/bin/python -m pytest packages/emcee/tests/test_run_plan.py -q`
Expected: failures (`No such option: --yes`; `to voice:` missing from stderr).

- [ ] **Step 3: Implement in `packages/emcee/src/emcee/cli.py`**

No new imports: `sys`, `Presenter`, `PresenterError`, `load_presenter`, `resolve_tts`, `TTSResolutionError` and `Moves` are already imported in `cli.py`.

Replace `_dry_run_marker` with this pair, and add the plan helpers after it:

```python
def _presenter_or_marker(config: EmceeConfig, presenter_id: str) -> Presenter | str:
    """The presenter, or the bracketed marker `--dry-run` and the plan print
    for one that cannot be loaded. Never raises. An unreadable or non-UTF-8
    file (OSError / UnicodeDecodeError, which load_presenter does not wrap)
    is invalid too."""
    path = _presenter_file(config.root, presenter_id)
    if path is None:
        return f"[missing presenters/{presenter_id}.toml]"
    try:
        return load_presenter(config.root, path.stem)
    except (PresenterError, OSError, ValueError):
        return f"[invalid presenters/{presenter_id}.toml]"


def _dry_run_marker(config: EmceeConfig, presenter_id: str) -> str:
    """The row suffix `run --dry-run` prints for a presenter-assigned package:
    a missing or invalid file, a failed TTS resolution, or -- for a PINNED
    presenter only -- the backend and model it resolves to. Never raises;
    never preflights."""
    presenter = _presenter_or_marker(config, presenter_id)
    if isinstance(presenter, str):
        return f"  {presenter}"
    try:
        resolution = resolve_tts(config, presenter)
    except TTSResolutionError as exc:
        return f"  [unresolved: {exc}]"
    if resolution.pinned:
        return f"  [{resolution.backend} {resolution.model}]"
    return ""


def _stdin_is_tty() -> bool:
    """Whether someone can answer `run`'s question. Tests patch this."""
    return sys.stdin.isatty()


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _stale_moves(moves: Moves, statuses: list[PackageStatus]) -> int:
    """Recorded moves whose performance_id no scanned package carries."""
    live = {s.performance_id for s in statuses if s.performance_id is not None}
    return sum(1 for pid in moves.entries if pid not in live)


def _stale_note(n: int) -> str:
    return f"note: {n} recorded move(s) match no package (emcee move --list)"


def _plan_tts_cell(config: EmceeConfig, presenter_id: str | None) -> tuple[str, str]:
    """(who, how) for one TTS line of the plan: `<id> (<name>)` or `house`,
    and `<backend>  <model>` -- or the `--dry-run` marker when the presenter
    cannot be loaded or resolved. Never raises."""
    presenter: Presenter | None = None
    who = "house"
    if presenter_id is not None:
        loaded = _presenter_or_marker(config, presenter_id)
        if isinstance(loaded, str):
            return presenter_id, loaded
        presenter, who = loaded, f"{presenter_id} ({loaded.name})"
    try:
        resolution = resolve_tts(config, presenter)
    except TTSResolutionError as exc:
        return who, f"[unresolved: {exc}]"
    return who, f"{resolution.backend}  {resolution.model or '-'}"


def _echo_plan(config: EmceeConfig, to_voice: list[PackageStatus], stale: int) -> None:
    """The plan `run` prints before any spend (stderr): what will be voiced,
    why, with which TTS. `new` = unvoiced; `re-voice` = the profile check
    fails (grouped by reason, every package named: it is destructive);
    `repair` = voiced, profile check passing, something else missing (named:
    it also overwrites the script and clips)."""
    def out(line: str) -> None:
        typer.echo(line, err=True)

    clips = sum(s.clips for s in to_voice)
    out(f"to voice: {_plural(len(to_voice), 'package')}, {_plural(clips, 'clip')}")
    new = [s for s in to_voice if not s.voiced]
    revoice: dict[str, list[str]] = {}
    for s in to_voice:
        if s.voiced and s.profile_reason is not None:
            revoice.setdefault(s.profile_reason, []).append(s.path.name)
    repair = [s.path.name for s in to_voice if s.voiced and s.profile_reason is None]
    if new:
        out(f"  {'new':<9}{len(new):>3}")
    if revoice:
        out(f"  {'re-voice':<9}{sum(len(v) for v in revoice.values()):>3}")
        for reason, slugs in revoice.items():
            out(f"    {reason}: {len(slugs)}")
            for slug in slugs:
                out(f"      {slug}")
    if repair:
        out(f"  {'repair':<9}{len(repair):>3}")
        for slug in repair:
            out(f"      {slug}")
    out("TTS:")
    counts: dict[str | None, int] = {}
    for s in to_voice:
        pid = assignment_for(config, s.profile).presenter
        counts[pid] = counts.get(pid, 0) + 1
    order = sorted(counts, key=lambda pid: (pid is None, pid or ""))
    cells = [(_plan_tts_cell(config, pid), counts[pid]) for pid in order]
    width = max(len(who) for (who, _), _ in cells)
    for (who, how), n in cells:
        out(f"  {who:<{width}}  {how}  {_plural(n, 'package')}")
    if stale:
        out(_stale_note(stale))
```

Replace the whole `run` command:

```python
@app.command()
def run(
    force: bool = typer.Option(False, "--force",
                               help="Re-synthesize every DJ clip even if cached"),
    station_root: Path = typer.Option(
        None, "--station-root",
        help="Override \\[station] root for this invocation"),
    profile: list[str] = typer.Option(
        [], "--profile",
        help="Only packages whose effective profile is this (exact match; a move or "
             "artist rule counts); repeatable"),
    assigned: bool = typer.Option(
        False, "--assigned",
        help="Only packages whose effective profile has its own \\[assign.profiles] "
             "entry (skip those that would fall to the default or house voice)"),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="List what would be voiced, and with which presenter, then the plan; no LLM, "
             "TTS, or writes (--force is ignored); never asks"),
    yes: bool = typer.Option(
        False, "--yes", "-y",
        help="Voice without asking (the plan is still printed)"),
):
    """Voice every pending package in the station, after a plan and a yes.

    Scans `\\[station] root` (or `--station-root`) once, with config and
    `moves.json` loaded once. Before any LLM or TTS call it prints a plan on
    stderr -- packages to voice (new / re-voice by reason / repair), the
    exact clip count, and which presenter and TTS backend voice them -- and
    asks `Proceed? [y/N]`. `--yes` skips the question. With no terminal and
    no `--yes` it prints the plan and refuses (exit 1). After a yes it
    voices exactly the planned packages, from the same scan.

    A pending package whose only problem is missing track audio is skipped
    (`skip <slug>: N audio file(s) missing; re-deliver from llama`): voicing
    cannot fix it. "unsupported" (pre-v3) packages are reported and never
    modified. A package whose recorded move targets a profile with no
    `\\[assign.profiles]` entry is an error row. Per-package failures are
    printed as `error: <slug>: <message>` and do not stop the batch.

    `--profile NAME` (repeatable) and `--assigned` select by the EFFECTIVE
    profile (a recorded move, else an `\\[assign.artists]` rule, else the
    llama profile). `--dry-run` prints `would voice: <slug>  <profile>
    <presenter>` rows, then the plan, and never asks or writes.

    Exits 1 whenever an error row was printed (proceeded, declined, or
    nothing to voice); otherwise a decline or nothing to voice exits 0.
    """
    config = load_config()
    root = _resolve_station_root(config, station_root)
    moves, statuses = _load_station(config, root)
    stale = _stale_moves(moves, statuses)

    _note_unmatched_profiles(statuses, profile)
    filtering = bool(profile) or assigned
    unreadable = 0
    failed = False
    to_voice: list[PackageStatus] = []
    for status in statuses:
        slug = status.path.name
        if filtering:
            if status.profile is None and status.state in ("error", "unsupported"):
                unreadable += 1
                continue
            if profile and status.profile not in profile:
                continue
            if assigned and assignment_for(config, status.profile).source != "profile":
                continue
        if status.state == "unsupported":
            typer.echo(f"skip {slug}: {status.reasons[0]}")
            continue
        if status.state == "ready":
            continue
        if status.state == "error":
            typer.echo(f"error: {slug}: {status.reasons[0]}", err=True)
            for line in status.reasons[1:]:
                typer.echo(f"  {line}", err=True)
            failed = True
            continue
        if status.missing_tracks:   # tracks first: voicing cannot fix them
            typer.echo(f"skip {slug}: {status.missing_tracks} audio file(s) missing; "
                       "re-deliver from llama")
            continue
        if status.move_problem is not None:
            typer.echo(f"error: {slug}: {status.move_problem}", err=True)
            failed = True
            continue
        if dry_run:
            view = assignment_for(config, status.profile)
            line = f"would voice: {slug}  {status.profile or '(none)'}  {presenter_label(view)}"
            if view.presenter is not None:
                line += _dry_run_marker(config, view.presenter)
            typer.echo(line)
        to_voice.append(status)

    if unreadable:
        typer.echo(f"note: {unreadable} package(s) skipped: manifest unreadable "
                   "(see emcee status --list)")
    if to_voice:
        _echo_plan(config, to_voice, stale)
    elif stale:
        typer.echo(_stale_note(stale), err=True)

    if dry_run:
        typer.echo(f"{len(to_voice)} package(s) would be voiced"
                   + (" (with errors)" if failed else ""))
        if failed:
            raise typer.Exit(1)
        return

    if to_voice and not yes:
        if not _stdin_is_tty():
            typer.echo("error: refusing to voice without confirmation; pass --yes", err=True)
            raise typer.Exit(1)
        if not typer.confirm("Proceed?", default=False, err=True):
            typer.echo("nothing voiced")
            raise typer.Exit(1 if failed else 0)

    processed = 0
    for status in to_voice:
        slug = status.path.name
        try:
            _process_one(config, moves, Package(status.path), force)
        except Exception as exc:
            typer.echo(f"error: {slug}: {_typed_error(exc)}", err=True)
            for line in getattr(exc, "details", []):
                typer.echo(f"  {line}", err=True)
            failed = True
            continue
        processed += 1
        typer.echo(f"voiced: {slug}")

    typer.echo(f"{processed} package(s) voiced" + (" (with errors)" if failed else ""))
    if failed:
        raise typer.Exit(1)
```

- [ ] **Step 4: Existing `run` tests gain `--yes`**

CliRunner has no TTY, so any existing test that voices through `run` now needs `--yes`:

- `packages/emcee/tests/test_run_cmd.py`: add `"--yes"` to every `runner.invoke(app, ["run", ...])` whose argument list does not contain `"--dry-run"` (the invocations at about lines 71, 83, 97, 111, 137, 168, 199, 242, 332, 413, 442, 487, 506, 649, and the loop at 660, where it becomes `["run", "--yes", "--profile", "Dead", *extra]`). In `test_run_success_survives_a_raising_speech_close`, replace `assert result.stderr == ""` with `assert "error:" not in result.stderr` (the plan now goes to stderr).
- `packages/emcee/tests/test_mlx_wiring.py`: in `_cmd`, `"run": ["run", "--yes"]`; lines 273 and 333 become `["run", "--yes"]`.
- `packages/emcee/tests/test_handshake.py:96`: `["run", "--yes"]`.
- `packages/emcee/tests/test_profile_readiness.py` and `test_move_cmd.py` need no change: their non-dry-run `run` calls fail before the plan.

- [ ] **Step 5: Run the tests and watch them pass**

Run: `./.venv/bin/python -m pytest packages/emcee/tests/test_run_plan.py packages/emcee/tests/test_run_cmd.py packages/emcee/tests/test_mlx_wiring.py packages/emcee/tests/test_handshake.py -q` → all pass.
Run: `./.venv/bin/python -m pytest -q` → green.

- [ ] **Step 6: Commit**

```bash
git add packages/emcee/src/emcee/cli.py packages/emcee/tests/
git commit -m "feat(emcee): emcee run prints a plan and asks before any spend (--yes to skip)"
```

---

### Task 8: `emcee status` on effective profiles

Spec: §1 (status grouping, `--profile`, `--list`, `--json` with `delivered_profile` and `profile_source`, the `(from …)` mark), §3 (`[no assign entry]`, the stale note), §4 (`tts` in `--json` only).

**Files:**
- Modify: `packages/emcee/src/emcee/cli.py` (`_status_json_row`, the `--list` table in `status_cmd`, `status_cmd`'s docstring and its stale note; new `_profile_cell`)
- Create: `packages/emcee/tests/test_status_profiles.py`

**Interfaces:**
- Consumes: `PackageStatus.profile`, `.delivered_profile`, `.profile_source`, `.move_problem`, `.tts` (Task 4); `_stale_moves`, `_stale_note` (Task 7); `profile_label` (Task 3).
- Produces:
  - `cli._profile_cell(s: PackageStatus) -> str`: the effective profile, then ` (from <delivered>)` when they differ (resolved rows only), then ` [no assign entry]` when the move is invalid
  - `status --json` rows gain `delivered_profile`, `profile_source`, `tts`, `move_problem`

Decision (the spec only names the `[no assign entry]` mark for `status`): it appears in the `--list` profile cell, and `--json` carries the message as `move_problem`. The summary stays grouped by effective profile with no per-row marks.

- [ ] **Step 1: Write the failing tests**

`packages/emcee/tests/test_status_profiles.py`:

```python
"""`emcee status` on effective profiles (spec sections 1, 3, 4)."""

import json
from pathlib import Path

from typer.testing import CliRunner

from emcee.cli import app

from tests.helpers import build_package, set_dj_audio, write_moves_file

runner = CliRunner()
TTB = "Tedeschi Trucks Band"
_SOUTHERN = '[assign.profiles.southern]\npresenter = "gregg"\n'
_RULE = _SOUTHERN + '\n[assign.artists]\n"Tedeschi Trucks Band" = "southern"\n'


def _home(tmp_path, monkeypatch, assign: str = _RULE):
    home = tmp_path / "home"
    station = tmp_path / "station"
    station.mkdir(parents=True)
    home.mkdir()
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    (home / "config.toml").write_text(
        f'[station]\nroot = "{station}"\n\n[tts]\nbackend = "fake"\nvoice = "v"\n\n{assign}\n')
    return home, station


def _rows(result) -> dict[str, str]:
    return {line.split()[0]: line for line in result.stdout.splitlines()}


def _json(args=("status", "--json")) -> dict[str, dict]:
    return {r["slug"]: r for r in json.loads(runner.invoke(app, list(args)).stdout)}


def test_list_marks_a_profile_that_differs_from_the_delivered_one(tmp_path, monkeypatch):
    _, station = _home(tmp_path, monkeypatch)
    build_package(station, slug="ttb", voiced=True, profile="funk", artist=TTB)
    build_package(station, slug="gd", voiced=True, profile="dead")

    rows = _rows(runner.invoke(app, ["status", "--list"]))

    assert "southern (from funk)" in rows["ttb"]
    assert "pending" in rows["ttb"]
    assert "(from" not in rows["gd"]


def test_summary_groups_by_the_effective_profile(tmp_path, monkeypatch):
    _, station = _home(tmp_path, monkeypatch)
    build_package(station, slug="ttb", voiced=True, profile="funk", artist=TTB)

    lines = [line.split() for line in runner.invoke(app, ["status"]).stdout.splitlines()]

    assert [line[0] for line in lines[1:-1]] == ["southern"]


def test_profile_filter_follows_a_move(tmp_path, monkeypatch):
    home, station = _home(tmp_path, monkeypatch, _SOUTHERN)
    build_package(station, slug="moved", voiced=True, profile="funk")
    write_moves_file(home, {"GratefulDead/moved": "southern"})

    south = runner.invoke(app, ["status", "--profile", "southern"])
    funk = runner.invoke(app, ["status", "--profile", "funk"])

    assert "moved" in _rows(south)
    assert "no packages match" in funk.stdout
    assert "note: no package has profile 'funk'" in funk.stderr


def test_json_carries_delivered_profile_source_tts_and_move_problem(tmp_path, monkeypatch):
    _, station = _home(tmp_path, monkeypatch)
    build_package(station, slug="ttb", voiced=True, profile="funk", artist=TTB)
    build_package(station, slug="legacy", voiced=True, profile="dead")
    rec = build_package(station, slug="rec", voiced=True, profile="dead")
    tts = {"backend": "voxtral", "model": "voxtral-mini-tts-2603", "voice": "clone:0123abcd"}
    set_dj_audio(rec, presenter=None, profile="dead", profile_source="llama", tts=tts)

    by = _json()

    assert (by["ttb"]["profile"], by["ttb"]["delivered_profile"], by["ttb"]["profile_source"]) == (
        "southern", "funk", "artist")
    assert by["legacy"]["tts"] is None
    assert by["rec"]["tts"] == tts
    assert by["ttb"]["move_problem"] is None


def test_a_move_without_an_assign_entry_is_marked(tmp_path, monkeypatch):
    home, station = _home(tmp_path, monkeypatch, assign="")
    build_package(station, slug="moved", voiced=True, profile="funk")
    write_moves_file(home, {"GratefulDead/moved": "southern"})

    rows = _rows(runner.invoke(app, ["status", "--list"]))
    by = _json()

    assert "southern (from funk) [no assign entry]" in rows["moved"]
    assert by["moved"]["move_problem"] == 'move target "southern" has no [assign.profiles] entry'


def test_status_notes_stale_moves_on_stderr(tmp_path, monkeypatch):
    home, station = _home(tmp_path, monkeypatch)
    build_package(station, slug="gd", voiced=True, profile="dead")
    write_moves_file(home, {"Gone/gone-1999": "southern"})
    note = "note: 1 recorded move(s) match no package (emcee move --list)"

    plain = runner.invoke(app, ["status"])
    as_json = runner.invoke(app, ["status", "--json"])

    assert note in plain.stderr
    assert note in as_json.stderr
    assert json.loads(as_json.stdout)[0]["slug"] == "gd"       # stdout stays pure JSON


def test_two_packages_sharing_a_performance_id_both_follow_one_move(tmp_path, monkeypatch):
    home, station = _home(tmp_path, monkeypatch, _SOUTHERN)   # Review Focus 5
    build_package(station, slug="a", voiced=True, profile="funk")
    b = build_package(station, slug="b", voiced=True, profile="funk")
    m = json.loads((b / "manifest.json").read_text())
    m["source"]["performance_id"] = "GratefulDead/a"
    (b / "manifest.json").write_text(json.dumps(m))
    write_moves_file(home, {"GratefulDead/a": "southern"})

    result = runner.invoke(app, ["status", "--json"])
    by = {r["slug"]: r for r in json.loads(result.stdout)}
    listed = runner.invoke(app, ["move", "--list"]).stdout

    assert by["a"]["profile"] == by["b"]["profile"] == "southern"
    assert by["a"]["profile_source"] == by["b"]["profile_source"] == "move"
    assert "match no package" not in result.stderr
    assert "missing" not in listed
```

- [ ] **Step 2: Run the tests and watch them fail**

Run: `./.venv/bin/python -m pytest packages/emcee/tests/test_status_profiles.py -q`
Expected: failures (`(from funk)` missing, `KeyError: 'delivered_profile'`, no stale note).

- [ ] **Step 3: Implement in `packages/emcee/src/emcee/cli.py`**

Add before `_status_json_row`:

```python
def _profile_cell(s: PackageStatus) -> str:
    """The `--list` profile cell: the effective profile; ` (from <llama's>)`
    when a move or rule changed it; ` [no assign entry]` when its recorded
    move cannot be voiced."""
    cell = profile_label(s.profile)
    if s.profile_source is not None and s.profile != s.delivered_profile:
        cell += f" (from {profile_label(s.delivered_profile)})"
    if s.move_problem is not None:
        cell += " [no assign entry]"
    return cell
```

`_status_json_row` returns:

```python
    return {"slug": s.path.name, "state": s.state, "reasons": s.reasons,
            "profile": s.profile, "delivered_profile": s.delivered_profile,
            "profile_source": s.profile_source, "voiced_by": s.voiced_by,
            "assigned_presenter": presenter, "assignment_source": source,
            "tts": s.tts, "move_problem": s.move_problem}
```

In `status_cmd`: change `_moves, statuses = _load_station(config, root)` to `moves, statuses = _load_station(config, root)` followed by `stale = _stale_moves(moves, statuses)`. Every exit path then ends with the note on stderr. Restructure the tail as:

```python
    if json_output:
        typer.echo(json.dumps([_status_json_row(config, s) for s in statuses], indent=2))
    elif not statuses:
        typer.echo("no packages found" if station_empty or not filtered
                   else "no packages match")
    elif not (list_view or filtered):
        _echo_status_summary(config, statuses)
    else:
        width = max(len(s.path.name) for s in statuses)
        profiles = [_profile_cell(s) for s in statuses]
        pwidth = max(len(p) for p in profiles)
        cells = [_voiced_by_cell(config, s) for s in statuses]
        vwidth = max(len(c) for c in cells)
        for s, pcell, cell in zip(statuses, profiles, cells):
            reasons = "; ".join(s.reasons)
            typer.echo(f"{s.path.name:<{width}}  {pcell:<{pwidth}}  "
                       f"{s.state:<12}  {cell:<{vwidth}}  {reasons}".rstrip())
    if stale:
        typer.echo(_stale_note(stale), err=True)
```

Docstring: in `status_cmd` replace the paragraph that starts "With no flags: one row per profile" with:

```
    Profiles are EFFECTIVE profiles: a recorded move (`emcee move`), else an
    `\\[assign.artists]` rule, else the llama profile. With no flags: one row
    per profile -- its assigned presenter and how many packages are ready /
    pending / other (unsupported + error), plus a total. `--list`/`-l`,
    `--profile NAME` or `--state STATE` switch to the per-show table (slug,
    profile, state, voiced-by, reasons); a profile a move or rule changed
    reads `southern (from funk)`, and a move whose target has no
    `\\[assign.profiles]` entry adds `[no assign entry]`. "pending" no longer
    means "off air": a package pending only for a profile change keeps
    airing its old voicing until it is re-voiced. `--json` is always
    per-show and adds `profile`, `delivered_profile`, `profile_source`,
    `voiced_by`, `assigned_presenter`, `assignment_source`, `tts` (the
    recorded TTS, null when absent) and `move_problem`. Recorded moves that
    match no package are counted in a `note:` on stderr.
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `./.venv/bin/python -m pytest packages/emcee/tests/test_status_profiles.py packages/emcee/tests/test_status_cmd.py -q` → all pass.
Run: `./.venv/bin/python -m pytest -q` → green.

- [ ] **Step 5: Commit**

```bash
git add packages/emcee/src/emcee/cli.py packages/emcee/tests/test_status_profiles.py
git commit -m "feat(emcee): status shows effective profiles, recorded TTS and stale moves"
```

---

### Task 9: Docs, llama's `DJAudio` doc model, transmitter docstring, runbook note

Spec: "Docs" and "Rollout"; §4 "llama's behavior is unaffected".

**Files:**
- Modify: `packages/llama/src/llama/models.py` (`DJAudio` at ~262)
- Modify: `packages/llama/tests/test_the_cut.py` (one new test)
- Modify: `packages/transmitter/src/transmitter/station.py` (module docstring only)
- Modify: `docs/station-brief.md`, `README.md`, `CLAUDE.md`, `docs/playout-incident-runbook.md`

**Interfaces:**
- Consumes: the shapes Tasks 5-8 produced.
- Produces: `llama.models.DJAudioTTS(BaseModel)` (`backend: str`, `model: str | None = None`, `voice: str`); `llama.models.DJAudio` gains `profile: str | None = None`, `profile_source: str | None = None`, `tts: DJAudioTTS | None = None`.

- [ ] **Step 1: Write the failing test** (append to `packages/llama/tests/test_the_cut.py`)

```python
def test_dj_audio_doc_model_accepts_emcees_recorded_profile_and_tts():
    # emcee 2026-10-16 records the profile it voiced as and how; llama's copy
    # of the block is documentation only and must stay shape-compatible.
    from llama.models import DJAudio

    block = {"set_intros": {"1": "dj-audio/set1-intro.mp3"}, "outro": "dj-audio/99-outro.mp3",
             "presenter": "gregg", "profile": "southern", "profile_source": "artist",
             "tts": {"backend": "voxtral", "model": "voxtral-mini-tts-2603",
                     "voice": "clone:0123abcd"}}
    assert DJAudio.model_validate(block).model_dump() == block
    legacy = DJAudio(set_intros={}, outro="o")
    assert (legacy.profile, legacy.profile_source, legacy.tts) == (None, None, None)
```

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_the_cut.py -q`. Expected: FAIL, because the round trip drops `profile`, `profile_source` and `tts`.

- [ ] **Step 2: llama's doc model**

Replace `class DJAudio` in `packages/llama/src/llama/models.py` with:

```python
class DJAudioTTS(BaseModel):
    """emcee-written: how a package's DJ clips were synthesized."""
    backend: str
    model: str | None = None
    voice: str


class DJAudio(BaseModel):
    """Per-segment spoken DJ clips, as package-relative paths (dj-audio/...).

    A documentation copy of emcee's `DJAudioBlock`, kept shape-compatible by
    hand: emcee writes it, llama only checks whether it is null. Everything
    after `outro` is optional here because blocks voiced before emcee
    recorded it lack those keys. llama's `status`/`deliver --profile` keep
    using the delivered profile (`source.profile`), not `profile` below."""
    set_intros: dict[str, str]  # one lead-in per non-encore set: "1", "2"
    outro: str
    presenter: str | None = None       # emcee-written: id of the voicing presenter; None = house
    profile: str | None = None         # emcee-written: the profile it was voiced as
    profile_source: str | None = None  # "move" | "artist" | "llama"
    tts: DJAudioTTS | None = None      # emcee-written: backend, model, voice
```

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_the_cut.py -q` → pass.

- [ ] **Step 3: transmitter docstring** (`packages/transmitter/src/transmitter/station.py`, docstring only)

Replace the first paragraph's opening, "A package is eligible iff it passes emcee's four readiness legs, reimplemented on files alone (transmitter never imports emcee) --", with "A package is eligible iff it passes emcee's four file-level readiness legs, reimplemented on files alone (transmitter never imports emcee) --". Then append a new paragraph at the end of the docstring:

```
emcee has a fifth readiness leg, the profile check (a package voiced as a
profile other than the one emcee would voice it as now, after an `emcee
move` or an `[assign.artists]` rule, is "pending" there). It is deliberately
NOT mirrored here: transmitter cannot see emcee's rules or moves, and such a
package keeps airing its existing voicing until its re-voice clears the DJ
blocks (ineligible while it runs, eligible again when it lands).
```

- [ ] **Step 4: `docs/station-brief.md`**

In the `dj-audio/` bullet, replace the `jsonc` block that shows `"dj_audio"` (the one with only `set_intros`/`outro`) with:

```jsonc
  "dj_audio": {
    "set_intros": { "1": "dj-audio/set1-intro.mp3",
                    "2": "dj-audio/set2-intro.mp3" },
    "outro": "dj-audio/99-outro.mp3",
    "presenter": "phil",             // presenter id; null = the house narrator
    "profile": "dead",               // the profile emcee voiced it as -- usually
                                     // source.profile, but an operator move or an
                                     // artist rule can change it
    "profile_source": "llama",       // "llama" | "artist" | "move"
    "tts": { "backend": "voxtral",   // how the clips were synthesized
             "model": "voxtral-mini-tts-2603",
             "voice": "clone:3f2a9c1d0b7e4a65" }  // preset name, or a clone hash
  }
```

After the block, add: "Packages voiced before 2026-10-16 lack `profile`, `profile_source` and `tts` (and the oldest lack `presenter`); treat a missing key as unknown. `profile` is informational for consumers: what airs is `broadcast.m3u`."

- [ ] **Step 5: `README.md`**

In the **Voicing.** command block, replace the `emcee run` and `emcee status` lines with:

```
    emcee run                          # scan [station] root, print the plan, ask, then voice
    emcee run --yes                    # same, without the question (the plan still prints)
    emcee run --dry-run                # the would-voice rows and the plan; never asks or writes
```

and

```
    emcee status                       # summary by (effective) profile: ready / pending / other
    emcee status --list                # per show; a moved show reads "southern (from funk)"
    emcee status --json
    emcee move tedeschitrucksband-2012-11-29 southern
                                       # voice this show as southern from the next run on
    emcee move tedeschitrucksband-2012-11-29 --delivered
                                       # back to llama's profile (exempts it from an artist rule)
    emcee move tedeschitrucksband-2012-11-29 --clear
    emcee move --list                  # every recorded move; `missing` = no package has it
```

After the paragraph that starts "`emcee run` is the everyday command", add a new subsection:

```markdown
**Moving shows between profiles.** Two ways, both emcee-side (llama's own
records and `llama status`/`deliver --profile` keep the profile that found
the show):

- **Artist rules** in `~/.emcee/config.toml`, for every show by an artist:

      [assign.artists]
      "Tedeschi Trucks Band" = "southern"                         # from any profile
      "JJ Grey and MOFRO"    = { profile = "southern", from = ["funk"] }

  Names match loosely (case, `&`/`and`, apostrophes, one trailing `[...]`,
  a leading "The"). A rule's profile needs its own `[assign.profiles.<name>]`
  entry, or every emcee command refuses to start. So the order is: create
  the presenter (`emcee presenter add`), add its `[assign.profiles.<name>]`
  entry, then add rules.
- **One-off moves** with `emcee move` (above), kept in
  `~/.emcee/moves.json`, keyed by the show's performance id, so they survive
  a `llama deliver --replace-voiced`. A move beats a rule; `--delivered` is
  how one show is exempted from a rule. Back up `moves.json`: an unreadable
  one stops every emcee command, and a missing one does too while any
  package was voiced under a move. A move not yet voiced lives only there.

A show whose effective profile changes goes `pending` (it keeps airing its
old voicing until the re-voice lands), and the next `emcee run` lists it
under `re-voice` in the plan, with the reason, before asking. Each voiced
manifest records the profile it was voiced as, where that came from, and
the TTS backend, model and voice (`dj_audio.profile`, `profile_source`,
`tts`). Changing a presenter, a presenter's TTS pin or the house voice does
not trigger a re-voice.

**Running `emcee run` from an agent** (no terminal): run `emcee run
--dry-run`, show the operator the plan, and pass `--yes` only after they
approve. The `--yes` run scans again, so anything delivered, moved or
edited in between is voiced without having been shown: keep that gap
short, and run nothing else against the station meanwhile.
```

In the "**The reassuring corollary**" paragraph near the end, after "are seen as `ready` by `station.readiness` and `emcee run` leaves them untouched", add: "(with no artist rules and no moves; a rule or move that changes a show's profile makes it pending, and `emcee run` asks before re-voicing it)".

- [ ] **Step 6: `CLAUDE.md`**

- In the **Run (emcee, …)** bullet (starts at about line 106), right after "`emcee run` (scan `[station] root` and voice every not-yet-broadcast-ready package;", insert: "it prints a plan on stderr (new / re-voice by reason / repair, the exact clip count, presenter and TTS per group) and asks `Proceed? [y/N]` before ANY LLM or TTS spend; `--yes`/`-y` skips the question; with no TTY and no `--yes` it prints the plan and exits 1. A package whose only problem is missing track audio is skipped (`re-deliver from llama`), not voiced. **An agent (no TTY) runs `emcee run --dry-run`, shows the plan, and passes `--yes` only after the operator approves**; the `--yes` run re-scans, so keep the gap short;". In the same bullet, add after the `emcee status` description: "`emcee move <show> <profile>|--delivered|--clear`, `emcee move --list` (one-off profile moves in `<emcee root>/moves.json`, keyed by `source.performance_id`; flock + atomic write; a move to an unassigned profile other than the delivered one is refused);".
- In the **emcee (station-side voicing), architecture** bullet, replace "(script present, DJ audio present, `broadcast.m3u` present, every manifest track's audio on disk)" with "(script present, DJ audio present, `broadcast.m3u` present, every manifest track's audio on disk, and, since 2026-10-16, the profile check: the voiced profile (`dj_audio.profile`, else, for a legacy block, `source.profile`) equals the EFFECTIVE profile, `station.effective_profile` = a `moves.json` move > an `[assign.artists]` rule > `source.profile`; transmitter deliberately does not mirror this leg)". Replace "resolve presenter assignment (`resolve_assignment`, keyed off `manifest["source"]["profile"]` against `[assign]`)" with "resolve the package ONCE (`resolve_voicing`: effective profile, then `resolve_assignment(config, profile)` against `[assign]`, then `resolve_tts`) and pass that `Voicing` through". After "rewrites the manifest's `dj_notes`/`dj_audio` blocks last", add: "`dj_audio` records `presenter`, `profile`, `profile_source` and `tts` (`backend`/`model`/`voice`); the last three are required in `DJAudioBlock`, so a legacy block must never be round-tripped through the model (update it as a raw dict)". Add one sentence: "**`moves.json` is never read leniently**: unreadable or malformed is a hard error for `run`/`voice`/`status`/`move`, and so is a missing file while any package records `profile_source: \"move\"`."

- [ ] **Step 7: `docs/playout-incident-runbook.md`**

In "## 6. Procedures", add a bullet:

```markdown
- **A show is being re-voiced by emcee** (an `emcee move` or `[assign.artists]`
  rule changed its profile): nothing to do on hugo. transmitter does not
  see emcee's profile check, so the package keeps airing its old voicing; an
  already-encoded row keeps its stored encode, a planned unencoded row whose
  package changes is re-planned in place, and a package caught mid-re-voice
  (DJ blocks cleared) is ineligible and planned around until the re-voice
  lands. A re-voice cannot cause `LayoutError` (that comes only from an
  on-air row whose encode is missing). A re-voice that FAILS leaves the
  package off the pool until `emcee voice <show>` succeeds.
```

- [ ] **Step 8: Verify and commit**

Run: `./.venv/bin/python -m pytest -q` → green.
Run: `bash packages/transmitter/scripts/test-in-debian12.sh` only if docker is available; it is a docstring-only change, so skipping it is acceptable. Note the skip in the task report.

```bash
git add packages/llama/src/llama/models.py packages/llama/tests/test_the_cut.py \
        packages/transmitter/src/transmitter/station.py docs/station-brief.md README.md \
        CLAUDE.md docs/playout-incident-runbook.md
git commit -m "docs: profile moves, artist rules, the run plan, and the recorded dj_audio shape"
```

---

## Self-review (done while writing; recorded for the reviewers)

**Spec coverage:**
- §1 effective profile and every reader: T3 (resolver), T4 (scan, filters, `_note_unmatched_profiles`, `PackageStatus.delivered_profile`), T7 (dry-run rows, plan), T8 (status summary, `--list`, `--json`, `(from …)` mark). Config and moves are loaded once per command, and no resolver defaults its moves (Global Constraints, T4 `_load_station`, T5 `resolve_voicing`).
- §2 artist rules, matching, validation: T1. `from` names are not validated (T1 code: no check).
- §3 moves: storage, lock, raw in-place edits, temp + fsync + rename, `--clear` never deleting: T2. Command forms, refusals, `--delivered`, output states, `unchanged`, `--clear` addressing and ambiguity, `--list`, the missing-file guard on `move`: T6. Stale note: T7 (run) and T8 (status). Use-time validation: T4 (`move_problem`), T5 (`voice`), T7 (`run`), T8 (`status`), T6 (`--list`). Loading strictness: T2, T4 (`run`, `status`), T5 (`voice`), T6 (`move`). Recovery data in manifests: T5.
- §4 single resolution, `DJAudioBlock`/`TTSRecord`, the backfill script, the fifth readiness leg with its four reasons, a legacy manifest staying ready, a missing `tts` never making a package pending, `tts` in `--json` only, llama's doc model: T4, T5, T8, T9.
- §5 the pause, all bullets: T7.
- Docs list and the Rollout agent line: T9.
- Testing list: each item maps to a named test in T1-T8 (normalize: T1; effective: T3; config: T1; readiness incl. `""`/null/missing `source`: T4; `_scan_broad` in status (T4) and in the run plan (T7); recording incl. null profile, clone hash, legacy rejection: T5; `emcee move` list: T6; `moves.json` failures for run/status (T4), voice (T5), move (T6); use-time validation: T7 (+T5); stale note: T7, T8; the pause: T7; filters: T4).

**Placeholder scan:** none. Two places say "unchanged" and point at exact existing lines rather than repeating them: the bodies of `manifest_profile`/`manifest_voiced_by` (T4) and the preflight/unlink/clear block of `_process_one` (T5).

**Type consistency:** `Moves`/`load_moves`/`read_moves_data`/`write_moves`/`record_move(..., *, moved_at)`/`clear_move(root, show, live_performance_id)` (T2) are used with those exact names in T4-T7. `Effective(profile, source, rule)` is defined in T3 and used in T4/T5. `scan(root, config, moves)`, `readiness(pkg, config, moves)`, `assess` → `Assessment.effective` (T4) are used in T5/T6. `_process_one(config, moves, pkg, force, fresh=())` is defined in T5 and called in T7. `process_package(config, pkg, speech, force=False, *, voicing)` and `voicing_for(config, pkg)` come from T5. `_stale_moves`/`_stale_note` are defined in T7 and reused in T8. `PackageStatus` field names match across T4, T6, T7 and T8.

**Review Focus:** five lines, each with a named test in its owning task (T2, T3, T7, T7, T8).
