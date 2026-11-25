# Concert Announcements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every break between two shows names what actually airs next ("Coming up next, Overnight
Variety with Cracker, followed by Ryan Adams, a few minutes before midnight Eastern. Then, at 2
Eastern, The Music Never Stopped with Dark Star Orchestra."), stitched at plan time from phrase
pieces that emcee voices on the Mac ahead of time, degrading phrase by phrase to today's breaks.

**Architecture:** transmitter derives a finite piece inventory (block phrases, artist phrases,
78 time phrases, the ID) and writes each missing text as `interstitials/pieces/piece-<id>.txt`;
a new `emcee pieces` command (launchd on the Mac) voices them dry on Qwen, verifies each take
strictly against its text, trims and normalises it and writes `piece-<id>.mp3` (or
`piece-<id>.failed`). At plan time the pure scheduler proposes each break's content from the
pieces present, `Station.extend` assembles the clip (a WAV in transmitter's workspace), measures
it and re-runs the scheduler once (pass 2); the break row records the named shows, which later
plan steps keep as a **promise** derived from the rows.

**Tech Stack:** Python 3 (emcee on the Mac), Python 3.11-compatible transmitter (hugo: Debian 12,
ffmpeg 5.1), numpy, pydantic, typer, pytest. mlx-audio server (Qwen3-TTS + whisper STT) on the Mac.

**Spec:** `docs/superpowers/specs/2026-11-25-concert-announcements-design.md` (approved; argue
from it, do not redesign). Builds on `docs/superpowers/specs/2026-10-25-scheduler-design.md`.

## Running this plan

- Work in a worktree at `/Users/shawn/projects/llama/.claude/worktrees/concert-announcements` on a
  new branch `concert-announcements` cut from `main`.
- Give the worktree its own venv and prove it imports the worktree:
  `python3 -m venv .venv && ./.venv/bin/pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"`
  `./.venv/bin/python -c "import llama, emcee, transmitter; print(llama.__file__, emcee.__file__, transmitter.__file__)"`
  must print paths inside the worktree.
- **Test command (every task):** the task's own files first
  (`./.venv/bin/python -m pytest <file> -q`), then the whole suite
  `./.venv/bin/python -m pytest -q` from the worktree root. Never a bare `pytest`, never
  `.venv/bin/pytest`.
- **transmitter tasks** also run `packages/transmitter/scripts/test-in-debian12.sh` when docker is
  available (the Python 3.11 + ffmpeg 5.1 gate); otherwise say so in the task report.
- Read before changing a package: root `CLAUDE.md`, `packages/transmitter/CLAUDE.md`,
  `packages/emcee/CLAUDE.md`. Each task that changes a package's behaviour adds or edits one
  bullet of facts in that package's `CLAUDE.md` (Task 17 consolidates).
- Each task ends with one commit on the branch; the message ends with the attribution lines the
  orchestrating session prescribes.
- Implementer model per task is given in its heading. Reviewers (spec compliance, code quality)
  are Opus for every task.

## Global Constraints

- `transmitter`, `emcee` and `llama` never import each other (`test_no_llama_or_emcee_imports.py`,
  `test_no_llama_imports.py`). The only interface is files: `interstitials/pieces/piece-<id>.txt`
  (transmitter writes), `piece-<id>.mp3` / `piece-<id>.failed` (emcee writes),
  `piece-<id>.expect` (the operator writes).
- transmitter stays Python 3.11-compatible (no PEP 695 generics, no nested same-quote f-strings,
  no `itertools.batched`) and ffmpeg 5.1-compatible.
- Tests are offline and deterministic: fake engines, fake speech, fake STT, `tmp_path`. ffmpeg-
  dependent transmitter tests skip without ffmpeg (existing pattern).
- **Strict surface** (spec "Stakes"): `plan.jsonl` rows, rollback compatibility (floor `af46d72`),
  the scheduler's purity and append-only layout, promises, render's skip path. Nothing in this
  feature may raise out of `plan_step`, `extend` or `render_step`; every failure degrades to the
  last rung (today's logic) and, where the spec says so, alerts.
- `config.toml` and the clock file gain **no** keys. New settings live only in
  `<TRANSMITTER_ROOT>/announce.toml`. emcee's `config.toml` gains no keys (the presenter is a
  command flag).
- transmitter never creates `<interstitials>/pieces`; while it is missing the feature is dormant.
- Only `plan_step` writes piece texts; `schedule`, `status`, `library` never write.
- Exact strings and values from the spec:
  - Time phrases (Eastern, `America/New_York`, whatever the clock's timezone), H = hour at or below
    the start, m = minutes past: 0-2 `at H`; 3-10 `just after H`; 11-19 `around quarter past H`;
    20-40 `around half past H`; 41-49 `around quarter to H+1`; 50-57 `a few minutes before H+1`;
    58-59 `at H+1`. Each ends ` Eastern.` Hours 12-hour, `midnight` for 0, `noon` for 12.
    78 texts (6 phrase forms x 13 hour words).
  - Piece texts: `Coming up next, <title>`, `<title> continues`,
    `Then, at <time> Eastern, <title>`, `with <artist>,`, `with <artist>.`,
    `followed by <artist>,`, the ID text. `with <artist>.` adds no second `.` when the cleaned
    artist already ends in `.` (`with moe.`).
  - Spike values: joins 0.4 s after the ID, 0.05 s within a phrase, 0.15 s after a comma-ending
    piece; bed 20 dB under the voice, 0.5 s lead-in, 1 s tail; trim at -60 dB keeping ~80 ms lead
    and ~120 ms tail; onset window 50 ms.
  - Assembled clip: lossless WAV, 44.1 kHz, 2 channels; slug `concert-<content hash>`.
  - Alert codes (all ungated events, not in `alerts.GATED_CODES` or `alerts.LEVEL_CODES`):
    `announce-assembly`, `announce-pieces`, `announce-promise`, `announce-config`.
- Never name a file `REPORT*`, `SUMMARY*`, `FINDINGS*` or `ANALYSIS*`.
- No task touches hugo, the NAS station root, `~/.transmitter`, `~/.emcee` or any release.
  **Single exception: Task 5** reads `/Volumes/media/lma-radio/delivered/*/manifest.json`
  and `~/.emcee` (config, presenter, lexicon) read-only, reads the spike takes under
  `/Users/shawn/.llama-harness/concert-announcements/spike/`
  read-only when present, and writes only under `~/.llama-harness/concert-announcements/` plus
  `~/.emcee/pieces.lock` (the `emcee pieces` flock). It requires `[tts.mlx_audio] stt_model` set
  in `~/.emcee/config.toml`; unset -> stop and report BLOCKED (the task never sets it).

## Where this plan settles what the spec left open

- **Command:** `emcee pieces <dir> --presenter <id> [--max-takes 4] [--limit N] [--dry-run]`.
- **Block pieces** are voiced unpunctuated (`Coming up next, Overnight Variety`), plus a period
  variant per titled block (`Coming up next, Overnight Variety.`, `Overnight Variety continues.`)
  used only when the clip ends after the block piece (rung 2). Then-pieces have no period variant
  (an artist piece always follows). Inventory per titled block: 4 block pieces + one Then-piece
  per distinct Eastern nominal time.
- **Then time text:** minute 0: the hour word (`2`, `midnight`, `noon`); otherwise `H:MM` with H
  12-hour (`2:30`, `12:30` for 00:30 and 12:30).
- **Bucket input:** the start's Eastern local wall time, minutes floored (seconds dropped).
- **Then-pieces inventory:** from the clock's titled occurrences over the next 8 days (as
  `announce.needed`), so a non-Eastern clock across a DST change is covered.
- **Artist:** `" ".join(show.artist.split())`; empty or non-string means no artist pieces.
  Artists are compared for "same artist" (Followed) by this cleaned string.
- **Strict verify:** tokenizer (below) on both sides; the final token exact; the sequence of
  template tokens (fixed template words and every number word) exact; the remaining (name)
  tokens within **1** token-level edit (Levenshtein over tokens). The ID piece has no name
  tokens: every one of its tokens is a template token (exact match). A `.expect` file replaces
  the comparison with exact token equality against its text.
- **Takes:** at most `MAX_TAKES = 4` per piece per run. A take fails on: the runaway guard
  (`SpeechDefect`), the onset check, no speech after trim, or the strict comparison. Any other
  `SpeechError` (server down, STT down) aborts the run with no sidecar written.
- **Onset:** reject when every 10 ms frame of the first 50 ms is within 20 dB of the take's
  speech-active level (`tts.loudness.active_level_db`).
- **Trim:** keep up to 80 ms before the first and 120 ms after the last 10 ms frame at or above
  -60 dBFS RMS, padding with digital silence to exactly 80/120 ms when less exists. Then
  `tts.loudness.normalize_speech` (the existing -20 dBFS speech-active target).
- **Gaps:** chosen by the preceding piece: after the ID piece 0.4 s; after a piece ending `,`
  0.15 s; after a piece ending `.` 0.3 s; otherwise 0.05 s. Bed (required when
  `enabled = true`; without it `announce.toml` is invalid, so off and alerted): 20 dB under the
  voice's RMS, 0.5 s lead-in, 1.0 s tail, linear fades 0.1 s in, 1.0 s out,
  looped when shorter than needed. All in `announce.toml`.
- **Typical assembled length:** `ASSEMBLED_TYPICAL_SECONDS = 18.0`, used for pass 1, for the
  predicted break before Y, and in the boundary estimate (`2 * gap + typical`) when the feature
  is on (switch on **and** the pieces folder exists).
- **Y's start** is the run's own start for Y under that boundary estimate.
- **Undecodable piece:** the assembler raises `PieceUndecodable(piece_id)`; `extend` alerts
  `announce-assembly` naming the piece id (deduped per code, as every alert), removes that
  id from the present set for the rest of the call and re-proposes (the scheduler then drops the
  phrase itself, so the assembled content is always one the scheduler proposed). The required
  block piece failing therefore leaves no usable Next: last rung.
- **Piece-text writes:** every `plan_step` (before its "already covered" early return), at most
  `WRITES_PER_STEP = 250` new files per step; the workspace list is rewritten only on change.
- **Broken promise** is decided from rows alone: the first show row after a concert row whose
  slug is not the next named slug (or that starts a run) while every earlier one matched.
- **Under a live promise**, a last-rung boundary takes its kind (`into`/`last`/`internal`) from the
  promise rather than the run, so today's `next`/`later` are judged against the shows that will
  actually play.
- **Rung visibility:** rows cannot tell rung 1 from rung 2 (the spec fixes two new fields), so
  `status` reports breaks as *assembled* (rungs 1-2) or *fallback* (rung 3).
- **`announce.toml`** is strict (`extra="forbid"`): a typo is "invalid" (off, alerted), never a
  silently ignored key; every key exists from phase A, so phase B adds none.
- **Concurrent `emcee pieces`:** a non-blocking flock on `<emcee root>/pieces.lock` (local disk,
  not the share); a held lock prints `another emcee pieces is running` and exits 0.
- **Promise merge:** when two live promises' remainders differ, a remainder that is a prefix of
  the other agrees with it and the longer is kept; the newer wins only when they differ at some
  position.
- **Premise timing:** premise checks that need phase-B code (the real assembly time on hugo) are
  deliberately at Checkpoint B, because phase A ships first; phase A keeps the decode proxy
  (Checkpoint A).

## Shared contracts (used across tasks)

```python
# transmitter/concert.py (Task 1; Task 11 adds the two dataclasses)
Named = tuple[str, tuple[str, str]]                # (slug, occurrence key) -- Task 1
EASTERN = "America/New_York"
ASSEMBLED_TYPICAL_SECONDS = 18.0
def piece_id(text: str) -> str                     # sha256(text.encode()).hexdigest()[:12]
@dataclass(frozen=True)
class NeededPiece:
    id: str; text: str; kind: str                  # kind in PIECE_KINDS
PIECE_KINDS = ("id", "next", "next_end", "continues", "continues_end", "then",
               "with_comma", "with_period", "followed", "time")

@dataclass(frozen=True)
class ConcertInput:                                # Task 11
    present: frozenset[str]                        # piece ids whose MP3 is usable
    id_text: str
    typical_frames: int
    first_break: Piece | None = None               # pass 2: the assembled clip at start_frame
    no_assembly_at: frozenset[int] = frozenset()   # start frames planned at the last rung

@dataclass(frozen=True)
class BreakContent:                                # Task 11
    pieces: tuple[tuple[str, str], ...]            # (piece id, text), play order
    entries: tuple[Named, ...]                     # X[, Y][, Z] with their occurrences
    names: tuple[tuple[str, str], ...]             # Z's occurrence when Then is present, else ()
    phrases: tuple[str, ...]                       # ordered subset of ("id","next","x","followed","then")
    y_time_id: str | None                          # Y's time-phrase piece id
    @property
    def named(self) -> tuple[str, ...]             # slugs of entries
    def same_shape(self, other: "BreakContent") -> bool   # entries, names, phrases equal

# transmitter/layout.py (Task 9)
CONCERT_ROLE = "concert"
# PlanRow gains: named_shows: tuple[str, ...] = (); piece_ids: tuple[str, ...] = ()
```

Files on the share: `<interstitials>/pieces/piece-<id>.txt` (UTF-8, exact text, no trailing
newline), `piece-<id>.mp3`, `piece-<id>.failed` (JSON `{"attempts": int, "last_reason": str,
"last_transcript": str | null, "at": "<ISO UTC>"}`), `piece-<id>.expect` (UTF-8). Dot-prefixed
files are temps of either side and are ignored by both.

## Review Focus

1. **Odd artist strings in manifests** (`moe.`, `Hot Tuna & Friends`, `Beyoncé`, `STS9`,
   `10,000 Maniacs`, an artist with a newline or double spaces, `""`, a non-string): one clean
   single-line text per piece, stable ids, no crash on either side. Tests: Task 1
   `test_artist_texts_are_single_line_and_deduped`, Task 2 `test_tokens_of_hard_names`.
2. **A clock whose timezone is not Eastern, and DST nights**: times are spoken in Eastern
   whatever the clock says; a start in the repeated 1 AM hour or a 02:00 block on the
   spring-forward day neither crashes nor speaks a nonexistent hour. Test: Task 1
   `test_eastern_whatever_the_clock_timezone_and_across_dst`.
3. **Human clutter in `pieces/`** (`notes.txt`, an `.mp3` without a `.txt`, a zero-byte `.mp3`,
   an `.mp3` younger than the quiet period, an unparseable `.failed`, a dot-temp, a
   subdirectory): presence and counts never raise and count only well-formed names. Tests:
   Task 7 `test_presence_and_counts_ignore_clutter`, Task 4 `test_pending_ignores_clutter`.
4. **A killed emcee or a racing hugo** (a stale `.piece-*.mp3.*.tmp`, a `.txt` renamed in
   mid-run or vanished after the listing, a torn or wrong text, a `.failed` deleted mid-run, two
   `emcee pieces` at once, an unmounted share): no half file is ever counted present or voiced,
   each side cleans only its own temps, the lock admits one run. Tests: Task 4
   `test_second_run_exits_on_the_lock`, `test_mp3_is_written_through_a_dot_temp`,
   `test_text_not_matching_its_id_is_skipped`, `test_text_vanished_after_listing_is_skipped`,
   `test_missing_folder_is_an_error`, `test_cleans_only_its_own_old_dot_temps`; Task 7
   `test_dot_temps_are_never_present`, `test_old_dot_temps_are_cleaned_young_ones_kept`.
5. **The same artist spelled two ways across packages** (`Grateful Dead` / `Grateful  Dead `):
   one set of pieces, and Followed treats them as the same artist. Tests: Task 1
   `test_artist_texts_are_single_line_and_deduped`, Task 11
   `test_same_artist_after_cleaning_suppresses_followed`.

---

# Phase A: voicing first (shippable alone)

Phase A changes no plan row and assembles nothing. It ships the inventory, the piece-text
writer, `status` counts and `emcee pieces`, so ~1,000 pieces can be voiced before phase B lands.

### Task 1: Piece texts, time buckets and the inventory (`transmitter/concert.py`) — implementer: sonnet

**Files:**
- Create: `packages/transmitter/src/transmitter/concert.py`
- Test: `packages/transmitter/tests_transmitter/test_concert.py`

**Interfaces:**
- Consumes: `clock.ClockConfig`, `clock.occurrences`.
- Produces: `Named`, `EASTERN`, `ASSEMBLED_TYPICAL_SECONDS`, `PIECE_KINDS`, `piece_id(text) -> str`,
  `clean(value: object) -> str | None`, `hour_word(h24: int) -> str`,
  `time_phrase(us: int) -> str`, `then_time(us: int) -> str`, `next_text(title) -> str`,
  `next_end_text(title)`, `continues_text(title)`, `continues_end_text(title)`,
  `then_text(title: str, nominal_us: int) -> str`, `with_comma(artist)`, `with_period(artist)`,
  `followed_by(artist)`, `ALL_TIME_PHRASES: tuple[str, ...]`, `NeededPiece`,
  `needed_pieces(clock: ClockConfig, artists: Iterable[object], id_text: str, from_us: int,
  days: float = 8.0) -> list[NeededPiece]` (deduped by id, sorted by id).

- [ ] **Step 1: Write the failing tests**

```python
def _us(local: str) -> int:      # "2026-11-25 23:52" in America/New_York -> us
    ...

@pytest.mark.parametrize("local,text", [
    ("2026-11-25 23:00", "at 11 Eastern."), ("2026-11-25 23:02", "at 11 Eastern."),
    ("2026-11-25 23:03", "just after 11 Eastern."), ("2026-11-25 23:10", "just after 11 Eastern."),
    ("2026-11-25 23:11", "around quarter past 11 Eastern."), ("2026-11-25 23:19", "around quarter past 11 Eastern."),
    ("2026-11-25 23:20", "around half past 11 Eastern."), ("2026-11-25 23:40", "around half past 11 Eastern."),
    ("2026-11-25 23:41", "around quarter to midnight Eastern."), ("2026-11-25 23:49", "around quarter to midnight Eastern."),
    ("2026-11-25 23:50", "a few minutes before midnight Eastern."), ("2026-11-25 23:57", "a few minutes before midnight Eastern."),
    ("2026-11-25 23:58", "at midnight Eastern."), ("2026-11-25 11:59", "at noon Eastern."),
    ("2026-11-26 00:05", "just after midnight Eastern."), ("2026-11-26 12:30", "around half past noon Eastern."),
    ("2026-11-26 00:59:59", "at 1 Eastern."),
])
def test_time_phrase_buckets(local, text):
    assert concert.time_phrase(_us(local)) == text

def test_seventy_eight_time_phrases():
    assert len(concert.ALL_TIME_PHRASES) == 78 == len(set(concert.ALL_TIME_PHRASES))
    assert all(t.endswith(" Eastern.") for t in concert.ALL_TIME_PHRASES)

def test_then_time_and_text():
    assert concert.then_time(_us("2026-11-26 02:00")) == "2"
    assert concert.then_time(_us("2026-11-26 02:30")) == "2:30"
    assert concert.then_time(_us("2026-11-26 00:00")) == "midnight"
    assert concert.then_time(_us("2026-11-26 00:30")) == "12:30"
    assert concert.then_text("The Music Never Stopped", _us("2026-11-26 02:00")) == \
        "Then, at 2 Eastern, The Music Never Stopped"

def test_fixed_texts():
    assert concert.next_text("Overnight Variety") == "Coming up next, Overnight Variety"
    assert concert.next_end_text("Overnight Variety") == "Coming up next, Overnight Variety."
    assert concert.continues_text("Overnight Variety") == "Overnight Variety continues"
    assert concert.continues_end_text("Overnight Variety") == "Overnight Variety continues."
    assert (concert.with_comma("Cracker"), concert.with_period("Cracker"), concert.followed_by("Ryan Adams")) == \
        ("with Cracker,", "with Cracker.", "followed by Ryan Adams,")
    assert concert.with_period("moe.") == "with moe."
    assert concert.piece_id("with Cracker,") == hashlib.sha256(b"with Cracker,").hexdigest()[:12]

def test_eastern_whatever_the_clock_timezone_and_across_dst():
    # a Europe/London clock; a start in the repeated 01:xx hour on 2026-11-01; a 02:00 block
    # on 2027-03-14 (spring forward) -> no exception, and the hour word is the Eastern wall hour
    ...

def test_inventory_counts_and_kinds():
    # clock: titled "a" daily 12:00, titled "b" daily 02:00, untitled "c" 18:00; artists
    # ["Cracker", "Ryan Adams"]; id_text "ID."
    got = concert.needed_pieces(clock, ["Cracker", "Ryan Adams"], "ID.", from_us=E)
    by_kind = Counter(p.kind for p in got)
    assert by_kind == {"id": 1, "next": 2, "next_end": 2, "continues": 2, "continues_end": 2,
                       "then": 2, "with_comma": 2, "with_period": 2, "followed": 2, "time": 78}
    assert all(p.id == concert.piece_id(p.text) for p in got) and got == sorted(got, key=lambda p: p.id)

def test_artist_texts_are_single_line_and_deduped():
    got = concert.needed_pieces(clock, ["Grateful Dead", "Grateful  Dead ", "moe.", "a\nb", "", None, 7], "ID.", from_us=E)
    arts = {p.text for p in got if p.kind == "with_comma"}
    assert arts == {"with Grateful Dead,", "with moe.,", "with a b,"}
    assert {p.text for p in got if p.kind == "with_period"} == {"with Grateful Dead.", "with moe.", "with a b."}
```

- [ ] **Step 2: Run** `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_concert.py -q`
  Expected: FAIL (`ModuleNotFoundError: transmitter.concert`).

- [ ] **Step 3: Implement `transmitter/concert.py`** with the signatures above. Bucket mapping
  (the one algorithm the table does not pin to code):

```python
def time_phrase(us: int) -> str:
    local = datetime.fromtimestamp(us // 1_000_000, tz=timezone.utc).astimezone(ZoneInfo(EASTERN))
    h, m = local.hour, local.minute
    nxt = (h + 1) % 24
    if m <= 2:    words = f"at {hour_word(h)}"
    elif m <= 10: words = f"just after {hour_word(h)}"
    elif m <= 19: words = f"around quarter past {hour_word(h)}"
    elif m <= 40: words = f"around half past {hour_word(h)}"
    elif m <= 49: words = f"around quarter to {hour_word(nxt)}"
    elif m <= 57: words = f"a few minutes before {hour_word(nxt)}"
    else:         words = f"at {hour_word(nxt)}"
    return f"{words} Eastern."
```

  `hour_word`: 0 -> `midnight`, 12 -> `noon`, else `str(h % 12)`. `ALL_TIME_PHRASES` enumerates
  the 6 forms (`at`, `just after`, `around quarter past`, `around half past`,
  `around quarter to`, `a few minutes before`) x 13 hour words. `needed_pieces`: the ID; for every
  titled block (`block.title`), the four block pieces; for every titled occurrence from
  `from_us` over `days`, `then_text(title, occ.nominal_us)`; per cleaned artist the three artist
  pieces; the 78 time phrases. Pure: no IO. `with_period(artist)` is `f"with {artist}"` when the
  cleaned artist already ends in `.`, else `f"with {artist}."`.

- [ ] **Step 4: Run the file, then the whole suite.** Expected: PASS.
- [ ] **Step 5: Commit** `transmitter: concert announcement piece texts and inventory`.

### Task 2: Strict transcript comparison (`emcee/tts/strict_verify.py`) — implementer: sonnet

**Files:**
- Create: `packages/emcee/src/emcee/tts/strict_verify.py`
- Test: `packages/emcee/tests/test_strict_verify.py`

**Interfaces:**
- Produces: `NAME_EDITS = 1`, `TEMPLATE_WORDS: frozenset[str]`, `number_words(n: int) -> list[str]`,
  `tokens(text: str) -> list[str]`, `strict_problem(text: str, transcript: str, *,
  expect: str | None = None) -> str | None`. Does not import or reuse `tts/verify.py`'s normaliser.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("text,want", [
    ("Then, at 2:30 Eastern, The Music Never Stopped", ["then", "at", "two", "thirty", "eastern", "the", "music", "never", "stopped"]),
    ("at 12:05", ["at", "twelve", "oh", "five"]), ("at 2:00", ["at", "two"]),
    ("You're listening to LMA Radio.", ["youre", "listening", "to", "lma", "radio"]),
    ("l m a radio", ["lma", "radio"]),
])
def test_tokens(text, want): assert tokens(text) == want

def test_tokens_of_hard_names():
    assert tokens("with moe.,") == ["with", "moe"]
    assert tokens("Hot Tuna & Friends") == ["hot", "tuna", "and", "friends"]
    assert tokens("Beyoncé") == ["beyonce"]
    assert tokens("STS9") == ["sts", "nine"]
    assert tokens("10,000 Maniacs") == ["ten", "thousand", "maniacs"]
    assert tokens("Blink-182") == ["blink", "one", "hundred", "eighty", "two"]

@pytest.mark.parametrize("text,heard", [
    ("Then, at 2:30 Eastern, The Music Never Stopped", "Then at two thirty Eastern, the music never stopped."),
    ("a few minutes before midnight Eastern.", "A few minutes before midnight, Eastern."),
    ("with Dark Star Orchestra.", "With Dark Starr Orchestra."),           # one name edit
])
def test_passes(text, heard): assert strict_problem(text, heard) is None

@pytest.mark.parametrize("text,heard,why", [
    ("followed by Ryan Adams,", "Followed by Ryan Adam.", "final"),        # swallowed final consonant
    ("around quarter past 11 Eastern.", "Around quarter past 12 Eastern.", "template"),
    ("around quarter past 11 Eastern.", "Around a quarter past 11 Eastern.", "template"),
    ("with Dark Star Orchestra.", "With Dork Stars Orchestra.", "names"),   # two name edits
    ("with Cracker.", "", "nothing"),
])
def test_fails(text, heard, why): assert why in strict_problem(text, heard)

def test_id_piece_tokens_are_all_template():         # no name tolerance for the ID
    id_text = "You're listening to LMA Radio. Live concert tapes from the Live Music Archive."
    assert strict_problem(id_text, "You're listening to LMA Radio. Live concert tapes from the Live Music Archive.") is None
    assert "template" in strict_problem(id_text, "You're listening to LMA Radio. Live concert tape from the Live Music Archive.")

def test_expect_overrides():
    assert strict_problem("with moe.,", "With Mo.", expect="with mo") is None
    assert "expect" in strict_problem("with moe.,", "With Moe.", expect="with mo")
```

- [ ] **Step 2: Run** the file. Expected: FAIL (module missing).
- [ ] **Step 3: Implement.** Tokenizer, in order: NFKD and drop combining marks; lowercase;
  remove apostrophes (`'’‘\``); `&` -> ` and `; times `\b(\d{1,2}):(\d{2})\b` -> words (minute 0:
  hour only; 1-9: `oh` + ones; else `number_words`); drop thousands commas `(?<=\d),(?=\d{3})`;
  split on `[^0-9a-z]+`; split letter/digit boundaries; digit runs -> `number_words` (values over
  999,999 stay as the digit string); finally join each run of two or more consecutive
  single-letter tokens into one token. `number_words`:

```python
_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
def number_words(n):
    if n < 20: return [_ONES[n]]
    if n < 100: return [_TENS[n // 10]] + ([_ONES[n % 10]] if n % 10 else [])
    if n < 1000: return [_ONES[n // 100], "hundred"] + (number_words(n % 100) if n % 100 else [])
    return number_words(n // 1000) + ["thousand"] + (number_words(n % 1000) if n % 1000 else [])
```

  `TEMPLATE_WORDS` = {coming, up, next, continues, with, followed, by, then, at, eastern, just,
  after, around, quarter, past, half, to, a, few, minutes, before, midnight, noon, oh} plus every
  word `number_words` can produce. A text is name-bearing when its tokens start with
  `coming up next`, `then at`, `with` or `followed by`, or end with `continues`; any other text
  (the ID; the time phrases are all template words anyway) has every token treated as a
  template token. `strict_problem` checks, in order: empty transcript
  (`nothing transcribed`); `expect` given -> exact token equality (`transcript differs from
  .expect`); final token (`final word "adams" heard as "adam"`); template subsequence equality
  (`template words differ: ...`); token-level Levenshtein over the name subsequences
  `> NAME_EDITS` (`names differ by N edits`).
- [ ] **Step 4: Run the file, then the whole suite.** Expected: PASS.
- [ ] **Step 5: Commit** `emcee: strict transcript comparison for announcement pieces`.

### Task 3: Piece audio: onset, trim, normalise (`emcee/piece_audio.py`) — implementer: sonnet

**Files:**
- Create: `packages/emcee/src/emcee/piece_audio.py`
- Test: `packages/emcee/tests/test_piece_audio.py`

**Interfaces:**
- Consumes: `emcee.tts.loudness.active_level_db`, `normalize_speech`.
- Produces: `ONSET_WINDOW_S = 0.05`, `FRAME_S = 0.01`, `ONSET_MARGIN_DB = 20.0`,
  `TRIM_THRESHOLD_DB = -60.0`, `LEAD_S = 0.08`, `TAIL_S = 0.12`;
  `read_wav(wav: bytes) -> tuple[bytes, int]` (16-bit mono PCM + rate; `SpeechError` otherwise);
  `onset_problem(pcm: bytes, rate: int) -> str | None`; `trim_edges(pcm: bytes, rate: int) -> bytes`
  (raises `ValueError("no speech")` when nothing reaches the threshold);
  `finish_take(pcm: bytes, rate: int) -> bytes` (trim, then `normalize_speech`);
  `pcm_to_wav(pcm: bytes, rate: int) -> bytes`.

- [ ] **Step 1: Write the failing tests** (synthetic 24 kHz int16 signals built with numpy:
  `silence(s)`, `tone(s, dbfs)`):

```python
def test_onset_rejects_a_take_that_starts_at_speech_level():
    assert "onset" in onset_problem(tone(1.0, -20), 24000)
def test_onset_accepts_a_short_quiet_lead():
    assert onset_problem(silence(0.03) + tone(1.0, -20), 24000) is None
def test_trim_keeps_exactly_80ms_lead_and_120ms_tail():
    out = trim_edges(silence(0.5) + tone(1.0, -20) + silence(0.7), 24000)
    assert len(out) // 2 == round(24000 * (0.08 + 1.0 + 0.12))
def test_trim_pads_with_digital_silence_when_the_lead_is_short():
    out = trim_edges(silence(0.02) + tone(1.0, -20), 24000)
    assert len(out) // 2 == round(24000 * (0.08 + 1.0 + 0.12)) and out[:2 * 1440] == bytes(2 * 1440)[:2 * 1440]
def test_trim_of_silence_is_no_speech():
    with pytest.raises(ValueError, match="no speech"): trim_edges(silence(1.0), 24000)
def test_finish_take_reaches_the_speech_target():
    assert abs(active_level_db(finish_take(silence(0.2) + tone(1.0, -32), 24000), 24000) - TARGET_DB) < 0.5
def test_read_wav_refuses_stereo(): ...
```

- [ ] **Step 2: Run** the file. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** with numpy over 10 ms frames (RMS in dBFS of int16/32768).
- [ ] **Step 4: Run the file, then the whole suite.** Expected: PASS.
- [ ] **Step 5: Commit** `emcee: piece audio onset check, trim and loudness`.

### Task 4: `emcee pieces` (voicing loop, sidecars, lock, launchd example) — implementer: sonnet

**Files:**
- Create: `packages/emcee/src/emcee/pieces.py`
- Modify: `packages/emcee/src/emcee/cli.py` (new `pieces` command; add `"pieces"` to
  `_COMMAND_ORDER` after `"say"`)
- Modify: `README.md` ("Local TTS on this Mac": a "Concert announcement pieces" subsection: a
  dedicated venv used only by the launchd job, so the production `emcee` stays untouched
  (`python3 -m venv ~/.venvs/emcee-pieces && ~/.venvs/emcee-pieces/bin/pip install
  ./packages/herder ./packages/emcee` from a checkout of the branch, non-editable); a launchd
  plist `com.lma-radio.emcee-pieces`, `StartInterval` 900, `ProgramArguments`
  `~/.venvs/emcee-pieces/bin/emcee` (expanded to an absolute path), `pieces`,
  `/Volumes/media/lma-radio/delivered/interstitials/pieces`, `--presenter`, `roydemure`;
  `plutil -lint`; `launchctl bootstrap gui/$(id -u) ...`)
- Modify: `packages/emcee/CLAUDE.md` (Commands: one bullet for `emcee pieces`)
- Test: `packages/emcee/tests/test_pieces_cmd.py`; add a case to
  `packages/emcee/tests/test_procs.py` and `packages/llama/tests/test_campaign_gate.py`

**Interfaces:**
- Consumes: Task 2 `strict_problem`; Task 3 `read_wav`, `onset_problem`, `finish_take`,
  `pcm_to_wav`, `trim_edges`; `emcee.process.speech_for(config, presenter) -> (speech, bed)`;
  `emcee.tts.verify.SttClient`; `emcee.speech_text.load_lexicon`, `normalize_for_speech`;
  `emcee.audio._encode_mp3(pcm, rate, channels)`; `emcee.presenters.load_presenter`.
- Produces: `MAX_TAKES = 4`; `PieceFile(id: str, txt: Path)` with `.mp3`, `.failed`, `.expect`
  paths; `pending(folder: Path) -> list[PieceFile]` (sorted by id); `run_pieces(folder: Path, *,
  speech, stt, lexicon, max_takes: int, limit: int | None, echo: Callable[[str], None]) -> Tally`
  (`Tally(voiced: int, retakes: int, failed: int, left: int)`); seams for tests:
  `_speech(config, presenter_id)` and `_stt(config)` module functions.

Behaviour (the command): `emcee pieces DIR --presenter ID [--max-takes N] [--limit N] [--dry-run]`.
No station lock (touches no package). Order: `DIR` missing or not a directory (share unmounted):
print `error: <DIR> does not exist (share not mounted?)` and exit 1; take the non-blocking flock
`<emcee root>/pieces.lock` (held: print `another emcee pieces is running`, exit 0); list pending
(`piece-<id>.txt` with neither `.mp3` nor `.failed`; names matching `^piece-[0-9a-f]{12}\.txt$`
only); none pending: exit 0 at once **before** loading the presenter or contacting any server;
`--dry-run`: print each pending `<id>: <text>` exactly as read (no integrity check, so
Checkpoint A's atomicity check sees what a voicing run would read) and exit 0; refuse with exit 1 when
`[tts.mlx_audio] stt_model` is unset (`error: emcee pieces needs [tts.mlx_audio] stt_model for
strict verification`); `speech.preflight()` once; delete its own dot-temps
(`.piece-*.mp3.*.tmp`, `.piece-*.failed.*.tmp`) older than 1 h, never transmitter's
`.piece-*.txt.*.tmp`. Per piece, first read its text: a `.txt` gone since the listing is skipped
silently (no sidecar, no crash); a text whose `piece_id`
(`sha256(text.encode()).hexdigest()[:12]`) is not the file's id prints
`skip <id>: text does not match its id` and is skipped (no `.failed`, no voicing). Then, up to
`max_takes`: `inner = getattr(speech, "inner", speech)`;
`wav = inner.synthesize(normalize_for_speech(text, lexicon), "wav")` (a `SpeechDefect` is a failed
take); `read_wav`; `onset_problem`; `finish_take`; `stt.transcribe(pcm_to_wav(...))`;
`strict_problem(text, transcript, expect=<.expect text or None>)`; success: MP3 via
`_encode_mp3`, written through `.piece-<id>.mp3.<token>.tmp` (fsynced) and `os.replace`. After the
cap: `.failed` JSON via the same dot-temp pattern. Any other `SpeechError` aborts the run (exit 1,
`error: ...`), writing no sidecar for the piece in hand. Lines printed:
`voiced <id>: <text>`, `re-take <id> (<reason>)`, `failed <id> after N takes: <reason>`, then
`voiced N, re-takes M, failed K, left P`.

- [ ] **Step 1: Write the failing tests** (fake speech returning a quiet-lead tone WAV per take,
  fake STT returning scripted transcripts, monkeypatched `_speech`/`_stt`, config with
  `stt_model` set):

```python
def test_nothing_pending_exits_before_touching_any_server(...):   # _speech/_stt raise if called; exit 0
def test_voices_a_pending_piece_to_an_mp3(...):                   # txt "with Cracker." -> piece-<id>.mp3 exists
def test_retakes_on_mismatch_then_succeeds(...):                  # transcripts ["With Crack.", "With Cracker."] -> 1 re-take
def test_failed_after_the_cap_writes_a_failed_sidecar(...):       # 4 bad takes -> .failed JSON keys attempts/last_reason/last_transcript/at; no mp3
def test_onset_and_guard_failures_are_failed_takes(...):          # SpeechDefect take, onset take, then good
def test_server_error_aborts_without_a_sidecar(...):              # SpeechError -> exit 1, no .failed, no .mp3
def test_expect_file_overrides_the_comparison(...):
def test_lexicon_respelling_is_sent_but_the_original_is_compared(...):
def test_failed_and_voiced_pieces_are_not_pending(...):
def test_pending_ignores_clutter(...):          # notes.txt, piece-XYZ.txt, .piece-…tmp, subdir, piece-<id>.mp3 alone
def test_mp3_is_written_through_a_dot_temp(...):# spy os.replace: source basename starts "."
def test_second_run_exits_on_the_lock(...):     # hold the flock -> "another emcee pieces is running", exit 0
def test_dry_run_lists_and_writes_nothing(...):
def test_refuses_without_stt_model(...):        # exit 1, message above
def test_limit_stops_after_n_pieces(...):
def test_text_not_matching_its_id_is_skipped(...):   # piece-<id>.txt holding other text -> one "skip <id>" line;
    # no .mp3, no .failed, speech never called for it; the other pieces voiced
def test_text_vanished_after_listing_is_skipped(...):  # unlink the txt between pending() and the read -> no crash, no sidecar
def test_missing_folder_is_an_error(...):        # DIR absent -> "error: ... does not exist", exit 1, lock never taken
def test_cleans_only_its_own_old_dot_temps(...): # old .piece-x.mp3.t.tmp deleted; old .piece-x.txt.t.tmp kept
# test_procs.py
def test_emcee_pieces_is_an_emcee_process():
    assert procs.tool_lines(["700 1 /x/.venv/bin/emcee pieces /v/pieces --presenter r"], ("emcee",), self_pid=1)
# packages/llama/tests/test_campaign_gate.py: the same line counts for llama's station_mark gate
```

- [ ] **Step 2: Run** the new file. Expected: FAIL (no `pieces` command).
- [ ] **Step 3: Implement** `pieces.py` and the command as described.
- [ ] **Step 4: Run** `packages/emcee/tests/test_pieces_cmd.py`, `test_procs.py`,
  `packages/llama/tests/test_campaign_gate.py`, then the whole suite. Expected: PASS.
- [ ] **Step 5: Commit** `emcee: pieces command voices announcement pieces with strict verification`.

### Task 5: Local premise checks (Qwen re-takes, strict STT, runaway guard) — implementer: sonnet

Runs on the operator's Mac against the local mlx-audio server (`curl -s http://127.0.0.1:8000/`
must answer; if not, stop and report BLOCKED: server down) with `[tts.mlx_audio] stt_model` set in
`~/.emcee/config.toml` (unset: stop and report BLOCKED: no STT model). No code changes. What it
may touch is the Task 5 exception in Global Constraints.

**Files:**
- Create: `docs/superpowers/2026-11-25-concert-announcements-evidence/premises.md`
- Create (not committed): `~/.llama-harness/concert-announcements/premises/` (sample pieces)

- [ ] **Step 1: Build the sample.** A throwaway script under `~/.llama-harness/...` (from the
  worktree venv) collects `show.artist` from `/Volumes/media/lma-radio/delivered/*/manifest.json`
  (read-only), calls `transmitter.concert.needed_pieces` with the live clock text copied by hand
  if available (else a two-block test clock) and writes `piece-<id>.txt` for: the 10 shortest
  texts; 20 artist pieces chosen for hard names (digits, punctuation, initialisms, non-ASCII);
  30 random others (seed 0). Expected: 60 `.txt` files.
- [ ] **Step 2: Voice it.** `./.venv/bin/python -m emcee pieces <dir> --presenter roydemure`.
  Record the summary line and every `re-take`/`failed` line.
- [ ] **Step 3: The swallowed consonant.** With `SP=/Users/shawn/.llama-harness/concert-announcements/spike`,
  use the spike's known-bad takes when present: r1 Voxtral `$SP/frag/06-ryan.mp3` (text in
  `$SP/frag/06-ryan.txt`, `Ryan Adams,`) and r3 Qwen `$SP/r3/frag/then-2-musicnever.mp3` (text in
  `$SP/r3/frag/then-2-musicnever.txt`, `Then, at 2 Eastern, The Music Never Stopped`; the
  swallowed "Stopped"). When neither is present, use the proxy: write `followed by Ryan Adam,`
  to `<dir>/proxy.txt` and
  `./.venv/bin/python -m emcee say <dir>/proxy.txt -o <dir>/take.mp3 --presenter roydemure --no-bed --no-chunk`,
  its text for the comparison being `followed by Ryan Adams,`. For each take:
  `ffmpeg -v error -i take.mp3 take.wav`, transcribe `take.wav` with `SttClient` (the
  `stt_model` config) and run `strict_problem(<text>, transcript)`. Expected: a `final word`
  problem for every take. Record which takes were used (spike or proxy).
- [ ] **Step 4: Write `premises.md`**: re-take rate (re-takes / pieces), failure count, the 10
  shortest pieces' outcomes with any runaway-guard reasons, hard-name outcomes (which need an
  `.expect`), the Step 3 result, wall time per piece. **HOLD** (report to the operator and stop
  the run) if any of the 10 shortest fails on the runaway guard on every take (a calibration
  change is the operator's call) or any Step 3 take passes. Otherwise **REPORT** and continue.
- [ ] **Step 5: Commit** `docs: concert announcement premise checks`.

### Task 6: `announce.toml` (`transmitter/announce_config.py`) — implementer: sonnet

**Files:**
- Create: `packages/transmitter/src/transmitter/announce_config.py`
- Modify: `packages/transmitter/src/transmitter/workspace.py` (`Workspace.announce_path` ->
  `root / "announce.toml"`)
- Test: `packages/transmitter/tests_transmitter/test_announce_config.py`

**Interfaces:**
- Produces:

```python
DEFAULT_ID_TEXT = "You're listening to LMA Radio. Live concert tapes from the Live Music Archive."
class Gaps(_Strict):          # seconds; each ge=0, le=2.0
    after_id: float = 0.4; after_comma: float = 0.15; after_period: float = 0.3; within: float = 0.05
    bed_lead_in: float = 0.5; bed_tail: float = 1.0
class AnnounceSettings(_Strict):   # extra="forbid", allow_inf_nan=False
    enabled: bool = False
    id_text: str = DEFAULT_ID_TEXT          # min_length=1, single line
    bed: Path | None = None                 # absolute; required when enabled (model validator)
    bed_under_db: float = 20.0              # ge=0, le=60
    gaps: Gaps = Gaps()
@dataclass(frozen=True)
class LoadedSettings:
    settings: AnnounceSettings
    source: Literal["file", "missing", "invalid"]
    problem: str | None
def load_settings(ws: Workspace, *, alert: bool) -> LoadedSettings   # never raises
```

- [ ] **Step 1: Write the failing tests**

```python
def test_missing_file_is_off_and_silent(tmp_path, monkeypatch):   # source "missing", enabled False, no alert
def test_valid_file_loads(tmp_path):                              # enabled = true with an absolute bed, gaps override
def test_invalid_file_is_off_with_one_alert(tmp_path, monkeypatch):  # unknown key; bad TOML; relative bed; non-UTF-8
    # source "invalid", settings == AnnounceSettings() (defaults, off), alerts.alert("announce-config", ...) called once
def test_enabled_without_bed_is_invalid(tmp_path, monkeypatch):  # enabled = true, no bed -> source "invalid",
    # problem names `bed`, settings off, one "announce-config" alert; enabled = false without bed is valid
def test_alert_false_never_alerts(tmp_path, monkeypatch):
def test_unreadable_file_never_raises(tmp_path):                  # a directory at announce.toml
def test_new_codes_are_ungated_events():
    for c in ("announce-assembly", "announce-pieces", "announce-promise", "announce-config"):
        assert c not in alerts.GATED_CODES and c not in alerts.LEVEL_CODES
```

- [ ] **Step 2: Run** the file. Expected: FAIL.
- [ ] **Step 3: Implement** (pydantic, `tomllib`; catch `OSError`, `UnicodeDecodeError`,
  `TOMLDecodeError`, `ValidationError`).
- [ ] **Step 4: Run the file, the whole suite, the Debian-12 gate.** Expected: PASS.
- [ ] **Step 5: Commit** `transmitter: announce.toml settings (off by default)`.

### Task 7: The needed-piece list writer (`transmitter/piecelist.py`, `plan_step`) — implementer: sonnet

**Files:**
- Create: `packages/transmitter/src/transmitter/piecelist.py`
- Modify: `packages/transmitter/src/transmitter/station.py` (`Ineligible.artist: str | None =
  None`, filled in `_evaluate` for every `Ineligible` returned after the manifest parsed as a
  dict, from `show.artist`)
- Modify: `packages/transmitter/src/transmitter/workspace.py` (`Workspace.pieces_needed_path` ->
  `root / "pieces-needed.json"`)
- Modify: `packages/transmitter/src/transmitter/pipeline.py` (`Station.scan_all`, `scan_pieces(...,
  shows=None)`, `write_piece_list`, `plan_step` wiring)
- Test: `packages/transmitter/tests_transmitter/test_piecelist.py`; additions in
  `test_station.py`, `test_pipeline.py`

**Interfaces:**
- Consumes: Task 1 `needed_pieces`, `NeededPiece`; Task 6 `load_settings`; `interstitials.folder`.
- Produces:

```python
PIECES_DIR = "pieces"; WRITES_PER_STEP = 250; TMP_MAX_AGE_S = 3600
_NAME = re.compile(r"^piece-([0-9a-f]{12})\.(txt|mp3|failed|expect)$")
def pieces_folder(cfg: TransmitterConfig) -> Path | None          # interstitials.folder(cfg) / "pieces"
def write_texts(folder: Path, needed: Sequence[NeededPiece], *, now_s: float) -> tuple[int, int]
    # (written, still_to_write); raises OSError; never creates `folder`
def present_ids(folder: Path | None, *, now_s: float, quiet_s: float) -> frozenset[str]
def failed_ids(folder: Path | None) -> frozenset[str]
def save_needed(ws: Workspace, needed: Sequence[NeededPiece], *, now_us: int) -> None   # only on change
def load_needed(ws: Workspace) -> list[NeededPiece] | None                              # never raises
@dataclass(frozen=True)
class PieceCounts: needed: int; present: int; failed: int; missing: int
def counts(ws: Workspace, folder: Path | None, *, now_s: float, quiet_s: float) -> PieceCounts | None
# pipeline.py
Station.scan_all(now_us) -> tuple[list[Show], list[Ineligible]]
Station.scan_pieces(now_us, *, read_only=False, shows: list[Show] | None = None) -> list[Piece]
def write_piece_list(st: Station, now_us: int, shows: list[Show], ineligible: list[Ineligible]) -> None  # never raises
```

`write_texts`: one `os.listdir`; for each needed id without `piece-<id>.txt`, write
`.piece-<id>.txt.<pid>-<token>.tmp` (UTF-8 text, flush, fsync) then `os.replace`; at most
`WRITES_PER_STEP`; delete its own `.piece-*.txt.*.tmp` older than `TMP_MAX_AGE_S` (emcee's
`.piece-*.mp3.*.tmp` / `.piece-*.failed.*.tmp` are emcee's to clean); never deletes a piece.
Present = `piece-<id>.mp3` regular, non-empty, mtime older than `quiet_s`. `write_piece_list`:
settings via `load_settings(st.ws, alert=True)`; clock via `clock.live_clock(st.ws, save=False)`;
artists = `meta["artist"]` of `shows` plus `ineligible[i].artist`; `save_needed` always;
folder missing -> no writes, no alert; any exception -> `st.log("piece list: ...")` and
`alerts.alert("announce-pieces", ...)`. `plan_step` calls `scan_all` once, then `write_piece_list`,
then `scan_pieces(now_us, shows=shows)`, all before its "already covered" early return.

- [ ] **Step 1: Write the failing tests**

```python
def test_ineligible_records_carry_the_artist(tmp_path):      # unvoiced package -> Ineligible.artist == "Band"
def test_writes_missing_texts_only(tmp_path):                 # existing txt untouched (mtime), new ones exact text, no trailing newline
def test_never_creates_the_folder(tmp_path):
def test_caps_writes_per_step(tmp_path):                      # 300 needed -> (250, 50), then (50, 0)
def test_dot_temps_are_never_present(tmp_path):
def test_old_dot_temps_are_cleaned_young_ones_kept(tmp_path):   # old .piece-x.txt.t.tmp deleted, young kept;
    # an old .piece-x.mp3.t.tmp (emcee's) kept
def test_presence_and_counts_ignore_clutter(tmp_path):        # notes.txt, zero-byte mp3, young mp3, garbage .failed, subdir
def test_failed_without_mp3_counts_failed(tmp_path):
def test_save_needed_rewrites_only_on_change(tmp_path):
def test_plan_step_writes_the_list_including_ineligible_artists(tmp_path):
    # make_station + an unvoiced package by "New Artist" + interstitials/pieces created ->
    # after plan_step, "with New Artist." is a piece-<id>.txt and in pieces-needed.json
def test_plan_step_writes_the_list_even_when_already_covered(tmp_path):
def test_plan_step_with_no_pieces_folder_writes_no_texts_and_no_alert(tmp_path, monkeypatch):
def test_a_write_failure_alerts_and_planning_goes_on(tmp_path, monkeypatch):
    # write_texts raises OSError -> plan_step returns rows as without the feature; alert "announce-pieces"
def test_the_list_is_written_with_announcements_switched_off(tmp_path):
def test_read_only_views_write_no_texts(tmp_path):            # schedule_report/status_lines/library_report leave pieces/ empty
```

- [ ] **Step 2: Run** the new file. Expected: FAIL.
- [ ] **Step 3: Implement** as above.
- [ ] **Step 4: Run** the transmitter tests, the whole suite, the Debian-12 gate. Expected: PASS
  (existing `plan_step` tests unchanged: with no `pieces/` folder nothing is written to the share).
- [ ] **Step 5: Commit** `transmitter: write the needed announcement pieces at plan time`.

### Task 8: `transmitter status`: piece counts and the switch — implementer: sonnet

**Files:**
- Modify: `packages/transmitter/src/transmitter/service.py` (`_scheduler_lines`)
- Modify: `packages/transmitter/CLAUDE.md` (Commands: `status` reads `pieces-needed.json` and the
  pieces folder)
- Modify: `docs/playout-setup.md` (new 7.6 "Concert announcements", phase-A part: the pieces
  folder `delivered/interstitials/pieces/` and its permissions (writable by hugo's transmitter
  user and the Mac's user; the feature is dormant while it is missing); the launchd job (the
  dedicated venv and plist, pointing at the README subsection from Task 4); voicing and
  re-arming (read `.failed`, add `.expect`, delete the `.failed`); and the note: a long
  `emcee pieces` run counts as an emcee process, so llama's `station_mark` and `emcee retitle`
  refuse meanwhile; `--limit` keeps runs short)
- Test: `packages/transmitter/tests_transmitter/test_service.py`

**Interfaces:**
- Consumes: Task 6 `load_settings(..., alert=False)`; Task 7 `pieces_folder`, `counts`.

Lines (exact):
- `concert    off (no announce.toml)` | `concert    off` | `concert    on` |
  `concert    off: announce.toml invalid (<condensed problem>)`; `concert    off` and
  `concert    on` gain `; bed <path>` when `bed` is set (always, when on)
- `pieces     dormant: <folder> does not exist (create it to start voicing)` when the folder is
  missing; else `pieces     no needed-piece list yet (written at the next plan step)` when
  `load_needed` is None; else `pieces     needed N; present P; failed F; missing M`. `present`
  is Task 7's (an MP3 counts whether or not it decodes; undecodable ids are Task 16's optional
  line).

- [ ] **Step 1: Write the failing tests**: one per line form above (including the bed path), plus
  `test_status_pieces_lines_never_raise_on_a_corrupt_list` (garbage `pieces-needed.json` reads
  as no list) and `test_status_writes_nothing` (no file created in `pieces/` or the workspace).
- [ ] **Step 2: Run** the new tests. Expected: FAIL.
- [ ] **Step 3: Implement**, then write the 7.6 phase-A runbook part.
- [ ] **Step 4: Run** the file, the whole suite, the Debian-12 gate. Expected: PASS.
- [ ] **Step 5: Commit** `transmitter: status shows announcement piece counts; runbook for voicing`.

## Checkpoint A (operator): deploy phase A and start voicing

Stop here. The orchestrator reports Tasks 1-8 and Task 5's premises and waits for the operator.
Phase A writes no new plan-row field, so rolling hugo back stays as today (floor `af46d72`).

1. **NAS:** create `delivered/interstitials/pieces/` (runbook 7.6), writable by hugo's
   transmitter user and the Mac's user. On hugo: `touch <folder>/.w && rm <folder>/.w` as the
   transmitter user succeeds.
2. **hugo:** `git pull`, `pip install -e packages/transmitter`, restart
   `transmitter@<user>`. Do **not** create `announce.toml` yet (or create it with
   `enabled = false`). `plan_step` (and so the piece-text writer) runs only while the service is
   filling: check the lead in `transmitter status`; the texts appear at the first fill after the
   lead drops below its low-water mark. After that fill, `transmitter status` shows
   `pieces     needed ~1000; present 0; ...`; `ls <folder> | wc -l` grows by up to 250 per plan step.
3. **Mac: the dedicated venv** from the README subsection (`~/.venvs/emcee-pieces`, used only by
   the launchd job; the production `emcee` is untouched). Not bootstrapped yet.
4. **Rename atomicity (spec premise):** during hugo's write burst (a fill that writes texts), on
   the Mac run
   `for i in $(seq 120); do ~/.venvs/emcee-pieces/bin/emcee pieces <folder> --presenter roydemure --dry-run | python3 -c 'import hashlib,re,sys; [print("MISMATCH", l.rstrip()) for l in sys.stdin if (m := re.match(r"([0-9a-f]{12}): (.*)$", l.rstrip("\n"))) and (not m[2] or hashlib.sha256(m[2].encode()).hexdigest()[:12] != m[1])]'; sleep 5; done`.
   It checks `sha256(text)[:12] == id` and a non-empty text for every `<id>: <text>` line
   `--dry-run` prints. Pass: no `MISMATCH` line.
5. **Assembly-time proxy on hugo** (until phase B's script exists): once 7 MP3s exist,
   `time (for f in $(ls <folder>/piece-*.mp3 | head -7); do ffmpeg -v error -i "$f" -f f32le -ac 2 -ar 44100 - >/dev/null; done)`.
   Record it; phase B's Checkpoint B repeats this with the real assembler.
6. **Mac:** install the launchd job from the README subsection (`ProgramArguments` pointing at
   `~/.venvs/emcee-pieces/bin/emcee`),
   `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.lma-radio.emcee-pieces.plist`.
   Next morning: `transmitter status` shows present close to needed; read every `.failed`
   (`cat <folder>/*.failed`), add `.expect` files for names STT cannot spell, delete those
   `.failed` files to re-arm.

---

# Phase B: assembly, promises, render

### Task 9: Plan-row fields, the concert role, rollback floor — implementer: sonnet

**Files:**
- Modify: `packages/transmitter/src/transmitter/layout.py` (`CONCERT_ROLE = "concert"`;
  `PlanRow.named_shows: tuple[str, ...] = ()`, `PlanRow.piece_ids: tuple[str, ...] = ()`, after
  `announcement_broken`; `to_json` writes them as lists only when non-empty; `from_json` requires a
  list or tuple and converts to a tuple, like `bends`)
- Modify: `packages/transmitter/src/transmitter/pipeline.py`
  (`ANNOUNCEMENT_ROLES = ("next", "later", CONCERT_ROLE)`)
- Test: `packages/transmitter/tests_transmitter/test_layout.py`, `test_pipeline.py`

- [ ] **Step 1: Write the failing tests**

```python
def _concert_row(**kw):
    return PlanRow(seq=5, slug="concert-0123456789abcdef", dir="/tx/render/concert", key="k", start_frame=100,
                   frames=800, kind="interstitial", role="concert", block="b", nominal_start="2026-11-26T05:00:00Z",
                   names=(("c", "2026-11-26T07:00:00Z"),), named_shows=("x", "y", "z"), piece_ids=("a1", "b2"), **kw)

def test_concert_row_round_trips():
    r = _concert_row()
    d = json.loads(json.dumps(r.to_json()))
    assert d["named_shows"] == ["x", "y", "z"] and d["piece_ids"] == ["a1", "b2"]
    assert PlanRow.from_json(d) == r

def test_concert_row_with_unknown_keys_round_trips():
    d = {**_concert_row().to_json(), "future": {"q": 1}}
    back = PlanRow.from_json(json.loads(json.dumps(d)))
    assert back.extra["future"] == {"q": 1} and back.to_json() == json.loads(json.dumps(d))

def test_empty_new_fields_are_not_written():          # a show row's to_json has neither key
def test_named_shows_must_be_a_list():                 # {"named_shows": "x"} -> TypeError (read_plan -> PlanError)

def test_concert_names_flag_a_missed_z(tmp_path):      # _announcement_broken: a concert row naming Z's occurrence,
    # then Z's first show row with miss=True -> broken; a concert row with names=() never flags
```

- [ ] **Step 2: Run** the new tests. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Rollback floor.** Run (expected output: `floor OK`):

```bash
S=/private/tmp/claude-501/concert-floor; mkdir -p $S
git show af46d72:packages/transmitter/src/transmitter/layout.py > $S/floor_layout.py
./.venv/bin/python - $S/floor_layout.py <<'EOF'
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("floor_layout", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
from transmitter.layout import PlanRow
new = PlanRow(seq=5, slug="concert-0123456789abcdef", dir="/tx/render/concert", key="k", start_frame=100,
              frames=800, kind="interstitial", role="concert", block="b", nominal_start="2026-11-26T05:00:00Z",
              names=(("c", "2026-11-26T07:00:00Z"),), named_shows=("x", "y", "z"), piece_ids=("a1", "b2"))
d = json.loads(json.dumps(new.to_json()))
old = m.PlanRow.from_json(d)
assert old.to_json() == d, (old.to_json(), d)
assert dict(old.extra) == {"named_shows": ["x", "y", "z"], "piece_ids": ["a1", "b2"]}
assert old.role == "concert" and old.kind == "interstitial"
print("floor OK")
EOF
git show af46d72:packages/transmitter/src/transmitter/planner.py | grep -n 'role'; echo "rc=$?"
# a plan written by the new build, read back by the floor's and by main's read_plan
./.venv/bin/python - $S/plan.jsonl <<'EOF'
import sys
from transmitter.layout import PlanRow
from transmitter.planner import write_plan
show = PlanRow(seq=4, slug="s", dir="/d/s", key="ks", start_frame=0, frames=50, kind="show", run_start=True)
concert = PlanRow(seq=5, slug="concert-0123456789abcdef", dir="/tx/render/concert", key="k", start_frame=100,
                  frames=800, kind="interstitial", role="concert", block="b", nominal_start="2026-11-26T05:00:00Z",
                  names=(("c", "2026-11-26T07:00:00Z"),), named_shows=("x", "y", "z"), piece_ids=("a1", "b2"))
write_plan(sys.argv[1], [show, concert])
EOF
for rev in af46d72 main; do
  mkdir -p $S/$rev && git archive $rev packages/transmitter/src | tar -x -C $S/$rev
  PYTHONPATH=$S/$rev/packages/transmitter/src ./.venv/bin/python - $S/plan.jsonl $S/$rev $rev <<'EOF'
import sys, transmitter
assert transmitter.__file__.startswith(sys.argv[2]), transmitter.__file__   # the copy, not the worktree
from transmitter.planner import read_plan
rows = read_plan(sys.argv[1])
assert len(rows) == 2 and rows[1].role == "concert" and rows[1].kind == "interstitial"
assert dict(rows[1].extra) == {"named_shows": ["x", "y", "z"], "piece_ids": ["a1", "b2"]}
print(f"read_plan OK at {sys.argv[3]}")
EOF
done
```

  Expected: `floor OK`, then `rc=1` (the floor's `_parse_row` never looks at `role`), then
  `read_plan OK at af46d72` and `read_plan OK at main` (no `PlanError`; the new fields ride in
  `extra`). Paste all four outputs into the task report.
- [ ] **Step 5: Run** the file, the whole suite, the Debian-12 gate. Expected: PASS.
- [ ] **Step 6: Commit** `transmitter: concert break rows (named_shows, piece_ids)`.

### Task 10: Promises from rows (`transmitter/promises.py`) — implementer: opus

**Files:**
- Create: `packages/transmitter/src/transmitter/promises.py`
- Test: `packages/transmitter/tests_transmitter/test_promises.py`

**Interfaces:**
- Consumes: Task 1 `concert.Named`; Task 9 `CONCERT_ROLE`, `PlanRow.named_shows`;
  `clock.occurrences`, `grid.iso_to_us`.
- Produces:

```python
def entries_of(row: PlanRow) -> tuple[Named, ...] | None
    # a concert row's named shows with their occurrences: every slug but Z in (row.block,
    # row.nominal_start); the last slug in names[0] when names is non-empty. None when the
    # row is not a concert row or is malformed (non-str slug, empty, more than 3, names
    # longer than 1, missing block/nominal). Never raises.
def remaining(rows: Sequence[PlanRow], *, pool_slugs: frozenset[str], clock: ClockConfig,
              run_start: bool) -> tuple[Named, ...]
    # the unplaced entries of the live promises, in order; () when none. run_start=True
    # (the next piece starts a run) voids everything. Live per spec (a)-(d): the show rows
    # after the break, in order, are a prefix of its entries (interstitials ignored), no row
    # after it has run_start, each unplaced slug is in pool_slugs, each named occurrence is
    # still yielded by the clock. Two live promises: a remainder that is a prefix of the
    # other's agrees and the longer is kept; only remainders that differ at some position
    # disagree, and then the newer wins. Never raises; never loops.
def first_mismatch(rows: Sequence[PlanRow], row: PlanRow) -> bool
    # `row` (about to be appended) is a show row that breaks a promise for the first time:
    # some concert row R in `rows` has entries, every show row after R so far matched them
    # in order with no run_start, fewer than all are placed, and `row` is not the next
    # named slug or has run_start. Rows only; never raises.
```

- [ ] **Step 1: Write the failing tests** (rows built by hand; the clock `clk` helper style of
  `test_scheduler.py`):

```python
def test_entries_put_z_in_its_named_occurrence():
def test_malformed_rows_have_no_promise():          # named_shows (1, 2); 4 slugs; names with 2 pairs; no block
def test_partial_promise_is_live_and_remaining_is_the_rest():   # [P, concert(x,y,z)] + row x -> (y,…),(z,…)
def test_kept_promise_leaves_nothing():             # x, y, z all placed
def test_void_when_a_named_slug_left_the_pool():    # y not in pool_slugs -> ()
def test_void_when_a_row_after_it_starts_a_run():
def test_void_when_run_start_is_requested():
def test_void_when_the_clock_no_longer_yields_the_occurrence():   # block renamed in the clock
def test_void_when_a_different_show_was_placed():
def test_a_prefix_remainder_agrees_and_the_longer_is_kept():   # [R1(x,y,z), x, R2(y)] -> (y,…),(z,…)
def test_newer_live_promise_wins_on_disagreement():   # [R1(x,y,z), x, R2(w)] -> (w,…)
def test_first_mismatch_only_once():                # rows [R(x,y), x] + row w -> True; [R, x, w] + row v -> False
def test_first_mismatch_on_a_run_start_row():
def test_never_raises_on_garbage():                 # nominal_start "not-a-date", names [["a"]] via from_json-built extra, etc.
    for rows in GARBAGE: assert remaining(rows, pool_slugs=frozenset(), clock=clock, run_start=False) == ()
```

- [ ] **Step 2: Run** the file. Expected: FAIL.
- [ ] **Step 3: Implement.** Occurrence check: `occurrences(clock, nominal, nominal + 1)` contains
  the key; `iso_to_us` errors make the promise void.
- [ ] **Step 4: Run** the file, the whole suite, the Debian-12 gate. Expected: PASS.
- [ ] **Step 5: Commit** `transmitter: promises derived from concert break rows`.

### Task 11: The scheduler proposes concert breaks — implementer: opus

**Files:**
- Modify: `packages/transmitter/src/transmitter/concert.py` (add `ConcertInput`, `BreakContent`;
  see Shared contracts)
- Modify: `packages/transmitter/src/transmitter/scheduler.py`
- Test: `packages/transmitter/tests_transmitter/test_scheduler_concert.py` (reuse
  `test_scheduler.py`'s helpers `sp`, `clip`, `clk`, `occ`, `mk`, `fr`, `E`, `GAP`, `IDS`)
- Create: `packages/transmitter/tests_transmitter/fixtures/concert_off_golden.jsonl` (Step 2)

**Interfaces:**
- Consumes: Task 1 texts and `piece_id`; Task 9 `CONCERT_ROLE`.
- Produces: `SchedulerInput.concert: ConcertInput | None = None` (last field, default keeps
  every existing caller and test byte-identical); `PlannedPiece.concert: BreakContent | None =
  None`; `to_row` writes `role=CONCERT_ROLE`, `named_shows=content.named`,
  `piece_ids=tuple(i for i, _ in content.pieces)`, `names=content.names` for a concert piece;
  `PLACEHOLDER_SLUG = "concert-pending"` (the pass-1 placeholder piece: kind `interstitial`,
  role meta `"concert"`, frames `concert.typical_frames`, `exact=False`).

Decision at `boundary()` (after the existing `_STOP` check, before today's choice), when
`inp.concert` is set and `s not in no_assembly_at`:

1. Clip length C = `first_break.frames` when `s == inp.start_frame` and `first_break` is given,
   else `typical_frames`. X's start `x_start = s + C + gap`.
2. X and X's occurrence: not placed -> the current occurrence's run from `x_start`; else
   `_run_at(x_start)`: an empty step means X opens the next occurrence (fresh run from
   `x_start`), else X continues the current one. *Entering* = X opens its occurrence. This
   decision is the concert path's own (made with C, not with the ID length today's logic would
   use): when it returns a concert piece and X is entering, it calls `_enter(X's occurrence)`
   itself, and the piece's `block`/`nominal_start` are X's occurrence. When it falls to today's
   logic (step 3) it has called no `_enter`.
3. X's block untitled, or degraded, or the Next block piece absent -> return to today's logic
   (rung 3), leaving state as today's code expects.
4. Phrases, each kept only when all its pieces are in `present`:
   - `id`: `piece_id(id_text)`.
   - Y = the next show of X's run in X's occurrence. **Followed** needs Y, Y's artist cleaned
     and different from X's, and `with_comma(X)`, `followed_by(Y)`,
     `time_phrase(Y's predicted start)` present. Same artist: Followed not spoken, Y still named.
     Followed dropped for any other reason: Y not named.
   - X's artist piece: `with_comma(X)` when Followed is spoken, else `with_period(X)`. Absent ->
     the clip ends after the block piece (`next_end_text`/`continues_end_text` if present, else
     the plain block piece); Followed and Then dropped; only X named.
   - **Then:** Z = the first show of the occurrence after X's, when Z directly follows the last
     named show (X's run has no show after the last named show), Z's block name differs from
     X's, Z's block is titled and not degraded, Z's predicted start is inside its window, and
     `then_text(Z title, Z nominal)` and `with_period(Z)` are present. `names = (Z occ key,)`.
     Z's predicted start `landing` = `complete()[-1].landing` of X's run through the last named
     show (as `_try_next` judges Y). Z is the first show of
     `_new_run(next_occ, landing, (), rec.with_piece(X[, Y]), <last named show's artist>,
     extra_used=(<X[, Y] slugs>))`, the recency taken with each named show at its predicted start
     (as `_try_later` does), so Z is never a show already named.
5. Piece order: [id], block piece, X artist, [followed_by(Y), time(Y)], [then, with_period(Z)].
6. The piece: `first_break` when given for `s == start_frame`, else the placeholder. After it, the
   active run is X's (as `_try_next`/`_try_later` leave it).

Boundary estimate: with `inp.concert` set, `self.B = 2 * gap + typical_frames` (not the median ID).

- [ ] **Step 1: Write the failing tests**

```python
def test_concert_off_is_today():                       # concert=None -> project() identical to the golden
    # projection of DAYCLOCK in tests_transmitter/fixtures/concert_off_golden.jsonl; also every existing test passes unchanged
def test_full_break_names_x_y_z_with_the_spec_wording():
    # Overnight Variety (titled, profile p) holding Cracker then Ryan Adams, then The Music Never Stopped
    # (titled) whose first show is Dark Star Orchestra; all pieces present ->
    # texts == [ID, "Coming up next, Overnight Variety", "with Cracker,", "followed by Ryan Adams,",
    #           <time phrase of Y's start>, "Then, at 2 Eastern, The Music Never Stopped", "with Dark Star Orchestra."]
    # named == ("cracker-…", "ryanadams-…", "dso-…"); names == (tmns occ key,); role "concert"
def test_continuing_x_uses_the_continues_piece():
def test_same_artist_after_cleaning_suppresses_followed():   # "Grateful Dead" / "Grateful  Dead" -> no followed piece,
    # X piece "with Grateful Dead." and Y still in named; Then may follow Y
def test_followed_dropped_for_a_missing_piece_unnames_y_and_blocks_then():
def test_then_needs_a_different_titled_undegraded_block_in_its_window():   # four parametrized failures
def test_missing_x_artist_ends_after_the_block_piece():   # pieces: [ID, "Coming up next, Overnight Variety."]; named (X,)
def test_missing_id_piece_is_left_out():
def test_untitled_or_degraded_x_is_todays_logic():
def test_missing_block_piece_is_todays_logic():
def test_no_assembly_at_the_start_is_todays_logic():
def test_y_time_phrase_comes_from_ys_predicted_start():
def test_concert_length_decides_entering_and_the_row_carries_xs_occurrence():
    # a boundary where an ID-length clip would leave X in the current occurrence but the
    # 18 s concert clip makes X open the next one (and the reverse case) -> the concert row's
    # block/nominal_start == X's occurrence, and X's show row follows in that occurrence
def test_then_never_names_a_show_already_named():
    # X is the only show both X's pool and Z's pool could pick -> Z (if Then is spoken) != X
def test_first_break_sets_the_length_of_piece_zero_only():
def test_boundary_estimate_uses_the_typical_assembled_length():
def test_same_shape_ignores_a_y_bucket_only_difference():
    a = BreakContent(pieces=(..., (t1, "around quarter past 11 Eastern."), ...), y_time_id=t1, ...)
    b = dataclasses.replace(a, pieces=(..., (t2, "around half past 11 Eastern."), ...), y_time_id=t2)
    assert a.same_shape(b) and not a.same_shape(dataclasses.replace(a, entries=a.entries[:2]))
def test_to_row_writes_the_concert_fields():
def test_piece_zero_does_not_depend_on_ahead():      # project(ahead=1)[0] == project(ahead=3)[0] with concert input
```

- [ ] **Step 2: Capture the golden, then run.** Before any scheduler change, write the
  projection of DAYCLOCK from the unmodified scheduler (rows as `to_json`, one per line) to
  `tests_transmitter/fixtures/concert_off_golden.jsonl` with a throwaway snippet; commit it with the
  tests. Then run the file. Expected: `test_concert_off_is_today` PASS, the rest FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `test_scheduler.py`, `test_scheduler_block.py`, the new file, the whole
  suite, the Debian-12 gate. Expected: PASS, existing scheduler tests unchanged.
- [ ] **Step 5: Commit** `transmitter: the scheduler proposes concert breaks`.

### Task 12: The scheduler keeps live promises — implementer: opus

**Files:**
- Modify: `packages/transmitter/src/transmitter/scheduler.py`
- Test: `packages/transmitter/tests_transmitter/test_scheduler_concert.py`

**Interfaces:**
- Consumes: Task 10 `remaining`; Task 11 content.
- Produces: `_Projection.promise: list[Named]`, initialised from
  `promises.remaining(inp.rows, pool_slugs=<show slugs of the pool>, clock=inp.clock,
  run_start=inp.run_start)`, set to a concert piece's `entries` when one is projected, popped when
  the next placed show is its head, cleared (void) otherwise. Applied identically with
  `inp.concert` None (promises hold whether announcements are on or off).
  `SchedulerInput.promises: bool = True` (after `concert`): `False` starts the projection with no
  promise (Task 14's guard).

Rules:
- `show()`: with a non-empty promise, the head's occurrence is the current one or, after
  `_enter`, the next one (any other: void, plan normally). The head slug is placed at this slot
  (`pools.by_slug`); when the run's own pick is that slug its fields are used as today, else
  `fill` from membership in `pools.own(occ)` (in it: `None`; not in it: the run's `cause`, or
  `"structural"` when the run has none), `bends=()`, `degraded=pools.degraded(occ)`, `miss` as
  today, and the active run is dropped (`self.run = None`) so the next `_run_at` re-plans with it
  placed. Deriving `fill` this way makes `extra_own` (rebuilt from the rows' `fill`) the same in
  a projection and in a live continuation.
- `boundary()`: with a non-empty promise, kind is `into` when the head's occurrence differs from
  the current one, `last` when the entry after the head is in a different occurrence, else the
  run's judgment. A concert break's X/Y/Z start from the promise's entries; shows beyond the
  promise come from a run continued with the promised shows placed. A new break never names a
  show the promise does not (it may name fewer).
- A void promise never raises, loops or stalls: planning continues as if it never existed.

- [ ] **Step 1: Write the failing tests**

```python
def test_live_promise_places_the_named_shows_after_lengths_change():
    # rows [P, concert(X, Y, Z)]; the pool now has X 20 min longer, so a fresh run would pick
    # differently -> project places X, then (after a break) Y, then Z, in order
def test_promise_places_z_even_outside_its_window():  # and to_row of Z's first show has miss True
def test_new_break_between_x_and_y_names_y_and_z_or_fewer():
def test_void_promise_plans_normally_and_never_raises():   # Y left the pool; occurrence gone; run_start
    for case in VOID_CASES: project(case)   # no exception; output == project with the concert row's promise stripped
def test_malformed_concert_row_never_raises():
def test_promises_false_plans_as_if_no_promise():    # live concert row, promises=False -> same as the row stripped
def test_a_prefix_promise_places_y_then_z():          # rows [R1(X,Y,Z), X, R2(Y)] -> Y then Z placed,
    # no row with announcement_broken
def test_promises_hold_with_announcements_off():      # concert=None, persisted concert row -> X, Y, Z placed
@pytest.mark.parametrize("ahead", [1, 2])
def test_appending_first_pieces_reproduces_one_projection_with_concert_breaks(ahead):
    # test_scheduler.py's closure test over REPRO_CLOCK with ConcertInput (every piece present,
    # typical 18 s) and titled blocks: project(until) == live(until) row for row, and the rows
    # contain role "concert" with three named shows at least once
def test_projection_equals_live_for_promises():
    # persisted [.., concert(X, Y, Z), X] with a pool change: project(...) == live(...), both
    # placing Y then Z
def test_projection_equals_live_when_the_promised_show_is_a_fill_show():
    # Y is not in its block's own pool (a fill show when promised): project(...) == live(...)
    # row for row, Y's row carries the derived fill, and extra_own rebuilds identically
```

- [ ] **Step 2: Run** the file. Expected: FAIL on the new tests.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** all scheduler tests, the whole suite, the Debian-12 gate. Expected: PASS.
- [ ] **Step 5: Commit** `transmitter: the scheduler keeps live promises`.

### Task 13: The assembler (`transmitter/assemble.py`) — implementer: sonnet

**Files:**
- Create: `packages/transmitter/src/transmitter/assemble.py`
- Create: `packages/transmitter/scripts/time_assembly.py` (operator timing script: assembles N
  breaks from the present pieces of a folder into a temp dir and prints per-break seconds)
- Modify: `packages/transmitter/src/transmitter/errors.py` (`AssemblyError(TransmitterError)`,
  `PieceUndecodable(AssemblyError)` with `.piece_id`)
- Modify: `packages/transmitter/src/transmitter/workspace.py` (`Workspace.concert_dir` ->
  `render_dir / "concert"`)
- Test: `packages/transmitter/tests_transmitter/test_assemble.py`

**Interfaces:**
- Consumes: Task 6 `AnnounceSettings`; Task 9 `layout.CONCERT_ROLE`; Task 11 `BreakContent`;
  `audio.iter_decode`, `station.Entry`, `station.file_set_key_and_sizes`, `workspace.atomic_write_bytes`.
- Produces:

```python
ASSEMBLY_VERSION = 1; CLIP_PREFIX = "concert-"     # the role is layout.CONCERT_ROLE (imported, not redefined)
class Assembler:
    def __init__(self, *, pieces: Path, out_dir: Path, settings: AnnounceSettings, ffmpeg: str = "ffmpeg"): ...
    def build(self, content: BreakContent) -> Show     # one-clip Show: entries (Entry("<name>.wav", "clip", "Announcement"),)
                                                       # as interstitials.scan builds them (render.file_gain decides loudness
                                                       # by that kind); meta {"role": CONCERT_ROLE, "ann_id": None, "sizes": ...}
def scan_clips(out_dir: Path) -> list[Show]            # concert-*.wav, no quiet period (own atomic writes)
def gc_clips(out_dir: Path, cache_dir: Path, keep: set[str], *, now_s: float, min_age_s: float = 3600) -> int
    # deletes unreferenced clips older than min_age_s with their cache/<key>.json, and dot-temps older than min_age_s
```

`build`: for each piece id, `piece-<id>.mp3` decoded with `iter_decode` (44.1 kHz stereo float);
a missing or undecodable piece raises `PieceUndecodable(id)`; a decoded piece is cached in the
instance by its file-set key. Gaps per "Where this plan settles". Bed (when `settings.bed`):
decoded (unreadable: `AssemblyError`), looped to cover `bed_lead_in + voice + bed_tail`, scaled
so its RMS is `bed_under_db` below the voice's RMS, faded in over 0.1 s and out over the tail,
the voice starting at `bed_lead_in`. No bed: no lead-in or tail. Mix clipped to [-1, 1], written
as 16-bit PCM WAV, 44,100 Hz, 2 channels, atomically, to
`out_dir/concert-<h>.wav`, `h = sha256(json.dumps([[file_set_key(piece) ...], settings.gaps.model_dump(),
bed key or None, bed_under_db, ASSEMBLY_VERSION]))[:16]`; an existing file of that name is reused
unwritten, its mtime refreshed with `os.utime` (so `gc_clips`' age counts from the last adoption).

- [ ] **Step 1: Write the failing tests** (ffmpeg-dependent ones skip without ffmpeg; pieces made
  with `helpers.write_mp3`):

```python
def test_build_joins_pieces_with_the_spec_gaps(tmp_path):   # decoded WAV length == sum(pieces) + 0.4 + 0.15 + ... (±1 frame per piece)
def test_build_mixes_the_bed_under_with_lead_in_and_tail(tmp_path):   # +0.5 s before, +1.0 s after; bed RMS 20 dB under in a voice-free gap
def test_wav_is_44k1_stereo_16bit(tmp_path):
def test_slug_is_a_content_hash_and_rebuilding_reuses_the_file(tmp_path):   # same content -> same slug, bytes not
    # rewritten (inode and content unchanged), mtime refreshed (set it back, rebuild, mtime is now)
def test_the_clip_show_is_a_clip_entry(tmp_path):     # build(...).entries == (Entry("concert-<h>.wav", "clip", "Announcement"),)
def test_slug_changes_with_gaps_bed_gain_and_piece_files(tmp_path):
def test_missing_or_undecodable_piece_raises_piece_undecodable(tmp_path):   # .piece_id == the bad id
def test_unreadable_bed_is_an_assembly_error(tmp_path):
def test_scan_clips_finds_concert_wavs_only(tmp_path):
def test_gc_keeps_referenced_and_young_clips(tmp_path):    # deletes old unreferenced wav + its cache json + old dot-temp
```

- [ ] **Step 2: Run** the file. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the file, the whole suite, the Debian-12 gate. Expected: PASS.
- [ ] **Step 5: Commit** `transmitter: assemble concert breaks from voiced pieces`.

### Task 14: `extend`: two passes, the failure ladder, broken promises — implementer: opus

**Files:**
- Modify: `packages/transmitter/src/transmitter/pipeline.py`
- Test: `packages/transmitter/tests_transmitter/test_pipeline_concert.py` (a `FakeAssembler`
  writing a small WAV per content and recording calls; `FakeEngine(clip_samples=...)`)

**Interfaces:**
- Consumes: Tasks 6, 7, 10, 11, 12 (`SchedulerInput.promises`), 13.
- Produces: `Station.assemble: Callable[[BreakContent, AnnounceSettings], Show] | None = None`
  (None: a real `Assembler(pieces=pieces_folder(cfg), out_dir=ws.concert_dir, ...)`);
  `concert_input(st, now_us, *, read_only: bool, no_assembly_at: frozenset[int] = frozenset())
  -> tuple[ConcertInput | None, AnnounceSettings]` (None unless `enabled` and the pieces folder
  exists; `read_only` loads settings with `alert=False`; `typical_frames` =
  `aacenc.frames_for(aacenc.pad_to_frame(grid.samples_for_seconds(ASSEMBLED_TYPICAL_SECONDS)), extra)`);
  `extend(..., no_assembly_at: frozenset[int] = frozenset())`;
  `Station.concert_pieces() -> list[Piece]` (`assemble.scan_clips(ws.concert_dir)` as interstitial
  pieces with `dir=str(ws.concert_dir)`; never raises: an `OSError` is `[]`), which `scan_pieces`
  adds to its pool.

Per row in `extend`, when `run1.role == CONCERT_ROLE` (and never otherwise; the existing path is
unchanged):
1. Build the clip (`st.assemble or` the real one) and measure it with `frames_of` ->
   `Piece("interstitial", show, str(ws.concert_dir), frames, True)`.
   `PieceUndecodable(id)`: alert `announce-assembly` naming the id (`piece <id> undecodable`;
   deduped per code by the alert dispatcher), drop `id` from `present` for the rest of the call,
   re-project. Any other exception (`Exception`, not only `TransmitterError`): log, alert
   `announce-assembly`, add `start` to `no_assembly_at`, re-project.
2. Measure every named show not yet exact (`frames_of`; the watchdog ping comes with it). A
   failure: today's skip (drop from `pool`, log) plus `start` into `no_assembly_at`, re-project.
3. Pass 2: `project` with the measured pool and `first_break=clip`. Its piece [0] a concert
   break whose content `same_shape` as pass 1 -> append it with pass 1's content (wording) and the
   clip. Otherwise `start` into `no_assembly_at`, re-project (today's logic at this boundary).
4. Never more than one assembly per (start, content) per call; the loop always terminates
   (each retry shrinks `present` or grows `no_assembly_at`).
5. Every show row appended: `promises.first_mismatch(out, row)` -> `announcement_broken=True`,
   log `promise-broken: <slug> at <block> <nominal>` and alert `announce-promise`.
6. Guard: any exception other than `PlanError` out of a `project` call that had concert input or
   live promises (`promises.remaining(...)` non-empty) is logged and alerted (`announce-assembly`
   when concert input was given, else `announce-promise`), and that row is re-run with
   `concert=None` and `promises=False`; both stay so for the rest of the call. An exception from
   that re-run is today's and propagates as today.

`plan_step` and `render_step` pass nothing new except `no_assembly_at` (Task 15).

- [ ] **Step 1: Write the failing tests**

```python
def test_feature_off_extends_exactly_as_today(tmp_path):          # no announce.toml; then enabled=false; then no pieces/
def test_appends_a_concert_row_with_the_assembled_clip(tmp_path): # role concert, dir == str(concert_dir), slug concert-*,
    # frames == frames_of(clip), named_shows and piece_ids set, every row exact
def test_pass2_bucket_only_difference_keeps_pass1_wording(tmp_path, monkeypatch):
    # pass-2 content differs from pass 1 only in y_time_id -> appended piece_ids == pass 1's
def test_pass2_different_names_falls_to_the_last_rung(tmp_path, monkeypatch):   # row role "id" (or next/later), no alert
def test_assembly_failure_alerts_and_falls_to_the_last_rung(tmp_path, monkeypatch):
    # assembler raises RuntimeError -> no exception out of plan_step; alert "announce-assembly"; row not concert
def test_undecodable_piece_is_treated_absent_for_the_call(tmp_path):  # PieceUndecodable(followed id) -> concert row
    # without the Followed phrase; assembler called twice; one "announce-assembly" alert naming the id
def test_unmeasurable_named_show_is_skipped_and_the_break_falls(tmp_path):
def test_named_shows_are_measured_before_pass_2(tmp_path):        # frames_of called for X, Y, Z; watchdog pings counted
def test_named_shows_are_placed_by_later_steps(tmp_path):         # plan_step(max_new=1) repeatedly -> X, break, Y, break, Z
def test_broken_promise_marks_only_the_first_mismatched_row_and_alerts(tmp_path):
    # after the concert row, remove Y's package; next steps: the row at Y's slot has announcement_broken,
    # later rows do not; alert "announce-promise" once per firing
def test_void_promise_never_stalls_planning(tmp_path):            # Y awaiting_fix and the clock edited -> plan_step covers until_frame
def test_invalid_announce_toml_alerts_and_plans_as_today(tmp_path):
@pytest.mark.parametrize("path", ["concert", "promise"])
def test_a_raising_concert_or_promise_path_falls_to_todays_logic(tmp_path, monkeypatch, path):
    # monkeypatch the scheduler's concert decision (or promises.remaining's use in the projection)
    # to raise RuntimeError -> extend raises nothing; the row is appended as with concert=None and
    # no promises; alert "announce-assembly" (concert) or "announce-promise" (promise); later rows
    # of the call also planned without either
```

- [ ] **Step 2: Run** the file. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `test_pipeline.py`, the new file, the whole suite, the Debian-12 gate.
  Expected: PASS, `test_pipeline.py` unchanged.
- [ ] **Step 5: Commit** `transmitter: plan concert breaks in two passes`.

### Task 15: Render: concert rows, the no-loop skip path, garbage collection — implementer: opus

**Files:**
- Modify: `packages/transmitter/src/transmitter/pipeline.py` (`render_step`, `_gc_assembled`)
- Test: `packages/transmitter/tests_transmitter/test_pipeline_concert.py`

**Interfaces:**
- Consumes: Task 13 `gc_clips`, `scan_clips`; Task 14 `extend(no_assembly_at=...)`,
  `Station.concert_pieces`.

Behaviour: a concert row renders like any interstitial row, its piece found in the scan (which now
includes `ws.concert_dir`). Any skip-path reason on a row with `role == CONCERT_ROLE` (missing
file, key changed, frames changed, render failure) adds `r.start_frame` to a per-call
`no_assembly: set[int]`, passed to every `st.extend` re-plan of the call; the clip ident is
excluded as for any interstitial. After each `st.extend` of the call, the clips it assembled are
merged into the call's `pieces` map: every `st.concert_pieces()` piece whose `(kind, slug)` is not
already a key is added (an excluded ident stays excluded), so a new concert row renders without a
further re-plan. The on-air refusal (`LayoutError`) is unchanged. At the end,
`_gc_assembled(st, rows, pub)`: `keep` = slugs of concert rows ending after
`(listed_bound + 1) * SEGMENT_FRAMES` (all concert rows when nothing is published);
`gc_clips(ws.concert_dir, ws.cache_dir, keep, now_s=time.time())`; an `OSError` there is logged,
never raised.

- [ ] **Step 1: Write the failing tests**

```python
def test_concert_row_renders_from_the_workspace_clip_folder(tmp_path):
def test_a_changed_concert_clip_is_replanned_at_the_last_rung_once(tmp_path, monkeypatch):
    # after planning, rewrite the WAV (key changes) and make the FakeAssembler produce a clip
    # whose analysis never matches -> render_step: exactly one re-plan at that frame, the new row
    # at that start has role id/next/later, report.replanned == [<concert slug>], no PlanError
def test_render_replan_with_assembly_disabled_cannot_loop(tmp_path, monkeypatch):
    # an assembler whose every clip mismatches at render -> replans <= number of distinct concert
    # rows in the lead; the call terminates without hitting the cap
def test_missing_concert_clip_is_replanned_at_the_last_rung(tmp_path):
    # after planning, delete the concert WAV -> the `piece is None` branch: exactly one re-plan at
    # that frame, the new row there has role id/next/later (not concert), report.replanned == [<concert slug>]
def test_render_replan_keeps_an_earlier_promise(tmp_path):
    # R1 names X, Y, Z; X's row is skipped at render (X re-voiced: key changed, re-planned in place,
    # not excluded) -> the re-plan places X, then Y, then Z; no row has announcement_broken; the row
    # re-planned at X's frame is X's show row (no concert row is planned there)
def test_new_concert_breaks_from_a_render_replan_render_without_another_replan(tmp_path):
    # a show re-voiced in the lead re-plans into new concert breaks (new clips in concert_dir) ->
    # they render with no further re-plan: report.replanned == [<that show>]
def test_lost_encode_of_a_concert_row_on_air_is_refused(tmp_path):   # LayoutError, as for any piece
def test_gc_keeps_clips_of_rows_after_the_high_water_mark(tmp_path):
def test_gc_failure_never_fails_render(tmp_path, monkeypatch):
```

- [ ] **Step 2: Run** the new tests. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `test_pipeline.py`, `test_pipeline_concert.py`, the whole suite, the
  Debian-12 gate. Expected: PASS.
- [ ] **Step 5: Commit** `transmitter: render concert breaks; re-plan them at the last rung`.

### Task 16: `schedule` and `status` show breaks and promises — implementer: sonnet

**Files:**
- Modify: `packages/transmitter/src/transmitter/report.py` (`_Item.text: str | None`;
  `BlockView.breaks` entry for a concert row: `concert: "<texts joined by a space>"`; unknown
  piece ids print as `<id>`)
- Modify: `packages/transmitter/src/transmitter/service.py` (`schedule_report` builds the
  scheduler input with `concert_input(st, t_us, read_only=True)` and passes a `texts_of(piece_ids)`
  lookup from `load_needed`; `_scheduler_lines` adds two lines)
- Test: `packages/transmitter/tests_transmitter/test_cli.py`, `test_service.py`

Status lines (exact): `breaks     next 24 h: A assembled, F fallback` (interstitial rows starting
in the next 24 h: role `concert` vs any other) and
`promises   B broken announcement(s) (last 24 h and planned)` (rows with `announcement_broken`).
Schedule: projected concert breaks print their content's texts; persisted ones their texts by id.
Optional (the builder may skip it): if `extend` records the ids that raised `PieceUndecodable`,
`status` adds `pieces     undecodable: <ids>`; Task 8's `present` count is unchanged either way.

- [ ] **Step 1: Write the failing tests**: `test_schedule_prints_the_concert_text`,
  `test_schedule_prints_fallback_breaks_as_today`, `test_schedule_writes_nothing_and_never_alerts`
  (no piece texts, no WAV, no alert with an invalid `announce.toml`),
  `test_status_counts_assembled_and_fallback_breaks`, `test_status_counts_broken_promises`.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the files, the whole suite, the Debian-12 gate. Expected: PASS.
- [ ] **Step 5: Commit** `transmitter: schedule and status show concert breaks`.

# Phase C: documentation

### Task 17: Runbook, CLAUDE.md, final acceptance — implementer: sonnet

**Files:**
- Modify: `docs/playout-setup.md` (7.6 "Concert announcements", whose phase-A part (the folder,
  the launchd job, voicing and re-arming, the emcee-process note) Task 8 wrote, gains the phase-B
  part: `announce.toml` with every key and its default (`bed` required when `enabled = true`),
  clearing `pieces/*.mp3` by hand after changing
  the announcer presenter or a lexicon entry, switching on, what each rung sounds like, the alert
  codes; 7.1 gains the four codes; 7.5 gains: rolling back past this feature leaves concert rows
  that an older build skips and re-plans once; a lost encode of one already on air is refused;
  rolling back while a promise is pending can air "followed by Y" with Y never placed)
- Modify: `packages/transmitter/CLAUDE.md`, `packages/emcee/CLAUDE.md` (consolidate the task
  bullets: the pieces contract, `announce.toml`, concert rows and promises, `emcee pieces`)
- Modify: root `CLAUDE.md` only if a rule that holds everywhere changed (expected: none)

- [ ] **Step 1: Write the docs.**
- [ ] **Step 2: Verify:** `./.venv/bin/python -m pytest -q` (whole suite) and the Debian-12 gate.
  Expected: PASS.
- [ ] **Step 3: Commit** `docs: concert announcements runbook`.

## Checkpoint B (operator): deploy phase B, measure, switch on

1. hugo: pull, install, restart with `announce.toml` absent or `enabled = false`. Nothing on air
   changes; `status` shows `concert    off`.
2. **Assembly time on hugo (spec premise):**
   `python packages/transmitter/scripts/time_assembly.py <pieces folder> --breaks 20`. Pass: the
   median well under the plan step's budget (a few seconds); record it.
3. Set `enabled = true` with `bed` (required when on). `transmitter schedule --days 1` shows
   `concert: "..."` breaks with the right names and times; at the next fill, `status` shows `assembled` breaks.
4. Listen to the first assembled breaks once they air. To switch off: `enabled = false` (rows
   already planned still air; promises they made are kept).
