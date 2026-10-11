# Playout Phase 1 ("Thin slice") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put a 24/7 wall-clock HLS stream of ready llama/emcee show packages on air: a Python `transmitter` on hugo that plans (trivially), renders frame-count AAC segments and publishes them to R2, plus a cron-only `antenna` Cloudflare Worker that writes `live.m3u8` (live, fallback loop, off-air) and a minimal static player.

**Architecture:** The stream is a pure function of the wall clock: segment `N` is AAC frames `[441N, 441N+441)` of one continuous frame line whose frame 0 sits at epoch `E`; `d = 10.24 s` exactly. transmitter encodes each show once (ffmpeg native `aac`, ADTS), lays shows on the frame line with pre-encoded silent frames between them, cuts segments by counting frames, prefixes each with the RFC 8216 ID3 PRIV timestamp, and uploads them in ascending `N`, advancing `state/horizon.json` only past confirmed PUTs. The antenna clock Worker reads `state/` through its R2 binding once a minute and rewrites `live.m3u8` at every grid boundary for ~75 s. Listeners only ever fetch static, cache-served R2 objects.

**Tech Stack:** Python ≥3.11 (hugo runs 3.11), typer, pydantic v2, numpy, boto3 (R2 S3 API), ffmpeg ≥5.1 (native `aac` encoder, `ebur128` filter); TypeScript, wrangler 4, vitest with `@cloudflare/vitest-plugin`, hls.js 1.x.

**Spec:** `docs/superpowers/specs/2026-10-09-playout-design.md` (phase 1 only; phases 2–4 appear here only as seams).

## Global Constraints

- **Scope:** new `packages/transmitter` (dist `llama-transmitter`, CLI `transmitter`) and new top-level `antenna/`. llama, emcee and herder code are untouched. transmitter imports neither llama nor emcee (enforced by `test_no_llama_or_emcee_imports.py`); it does not need herder.
- **Target host hugo:** Debian 12, **Python 3.11**, **ffmpeg 5.1**, Node 22, 4 cores. `requires-python = ">=3.11"`. Do not use 3.12+ APIs (`itertools.batched`, `Path.walk`, PEP 695 `type` statements / generic syntax). Use only ffmpeg features present in 5.1; the encoder is ffmpeg's native `aac` (no libfdk). `libmp3lame` is used only by tests, to fabricate MP3 fixtures.
- **Grid constants (spec, verbatim):** `d = 441 × 1024 / 44100 = 10.24 s` exactly; segment `N` = frames `[441N, 441N+441)`; frame 0 at `E`; segment timestamp `(N·d·90000) mod 2^33` = `(N·921600) mod 2^33`; output AAC-LC, 128 kbps, stereo, 44.1 kHz.
- **Container:** packed audio — ADTS `.aac` segments prefixed with an ID3v2.4 PRIV frame owned by `com.apple.streaming.transportStreamTimestamp` (8-byte big-endian 33-bit value). fMP4 only if the Task 2 spike fails (Appendix A).
- **Joins and loudness (spec):** track→track zero inserted silence (gapless decode honouring LAME delay/padding); clip↔track `0.75 s`; show→show `2 s`, rounded up to whole frames; last partial frame padded. Gain = `min(target − I, −1 dBTP − TP)`; music target `−16 LUFS` measured over tracks only; DJ clips their own speech target (default `−16 LUFS`, configurable).
- **R2 object contract (phase-1 subset):** `seg/<epoch_id>/<N>.aac` (`Cache-Control: public, max-age=31536000, immutable`), `fallback/<version>/<k>.aac`, `…/notice.aac`, `…/index.json` (immutable, never pruned), `timeline.json` (`public, max-age=30`), `notes/<slug>.json` and `show/<slug>.html` (`public, max-age=3600`), `live.m3u8` (`public, max-age=5`), `index.html` (`public, max-age=60`), static assets (`public, max-age=3600`), `state/horizon.json` `{epoch_id, epoch, d, first, last, published_at, container, fallback_version}` (not served), `state/offair.json` (hand-written in phase 1), `state/guard.json` (phase 2 writes it; absent = not tripped).
- **Ordering invariant (strict):** segments uploaded in ascending `N`; `state/horizon.json` rewritten only after every segment it covers returned 200; a show's `notes/<slug>.json` and `show/<slug>.html` before the `timeline.json` that first references it. No List calls ever. Publish and prune hold a local flock.
- **Clock (spec):** cron `* * * * *`; write immediately, then at every grid boundary until `scheduledTime + 75 s`; at most `ceil(75/d) + 2 = 10` PUTs per invocation; skip bytes identical to the last write; window `k = 6`; grace `0 < cur − last ≤ 3`; `N < first` is absent; fallback `N mod len` with `EXT-X-DISCONTINUITY` at every loop start and every live↔fallback switch; off-air (`state/offair.json` `offair: true`, or `now > E + (last+1)·d + 24 h`) → notice segment + `#EXT-X-ENDLIST`. `workers_dev = false`, `preview_urls = false`, no routes, no fetch handler.
- **Config is strict:** every pydantic config model inherits a shared `_StrictModel` with `extra="forbid"` (pydantic does not propagate `model_config` to nested models).
- **Atomic writes:** every file transmitter writes under `~/.transmitter/` goes through a unique temp name (`tempfile.mkstemp` in the target dir) + `os.replace` (the dev-only spike tool's scratch output is exempt).
- **Tests:** offline and deterministic. ffmpeg-dependent tests are marked `@requires_ffmpeg` (skip when ffmpeg is absent, like `scripts/test_stitch_m3u.py`) and use seconds of synthetic audio. Transmitter tests live in the package **`packages/transmitter/tests_transmitter/`** (with `__init__.py`): llama's tests are top-level modules (`test_config`, `test_audio`, `test_cli`, `test_pipeline`, `test_workspace`, `helpers` …) and emcee's are the `tests` package, so a `tests/` directory here would collide in the repo-wide run.
- **Worktree:** `.claude/worktrees/playout-phase1`, with its own venv: `python3 -m venv .venv && ./.venv/bin/pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee` (and `-e "packages/transmitter[dev]"` once Task 1 creates it). Always run `./.venv/bin/python -m pytest …` from the worktree root and check `./.venv/bin/python -c "import transmitter; print(transmitter.__file__)"` resolves inside the worktree.
- **hugo's versions:** ffmpeg-touching tasks finish by running `packages/transmitter/scripts/test-in-debian12.sh` (Task 2 creates it: Debian 12 container = Python 3.11 + ffmpeg 5.1). If Docker is unavailable, run the same suite on hugo itself.
- **Commit trailer:** end each commit with the attribution lines the harness supplies to you.
- **Deliberate deviations/additions** (relative to the spec; reviewers should not flag these):
  - The Playwright smoke test is deferred to phase 4; phase 1 has a manual local smoke (Task 17).
  - The renderer's safety stage is a clamp to [−1, 1], not a limiter: the gain rule already keeps true peak ≤ −1 dBTP.
  - A minimal `transmitter status` lands in phase 1.
  - Added knobs and behaviours: `[planner] start_delay_minutes`, `[publish] batch_segments`, `[publish] prune_min_segments`, the clip↔clip pause, `d` in `fallback/<v>/index.json`, the clock's wrangler `vars`, one new show per tick while filling, and a null playlist = write nothing.
  - `publish_lock` refuses rather than waits: a manual `transmitter publish` while `run` holds the lock exits 1 with a clear message (`PublishLocked`); the service's next tick simply retries.

## Review Focus

1. **NFS down on hugo:** the station root is an ordinary empty directory (no `.station-root`). `plan` must refuse with a `StationRootError` and leave `plan.jsonl` untouched — never treat the library as empty and re-plan. → Task 5 `test_empty_root_without_marker_is_refused`, Task 9 `test_plan_step_refuses_without_marker_and_keeps_plan`.
2. **A package is re-voiced or fixed between planning and rendering** (its file set changes). The renderer must skip the whole show at its boundary and re-plan from there, never encode it against stale durations. → Task 9 `test_render_step_replans_a_changed_package`.
3. **A segment upload fails mid-batch** after retries. The horizon advances only through the last confirmed segment, unconfirmed files stay on disk, the next batch resumes. → Task 11 `test_failed_segment_blocks_the_horizon`.
4. **A show whose tracks are digital silence or unmeasurable** (`ebur128` prints `I: -70.0 LUFS`, `Peak: -inf dBFS`). Gain must be 0 dB, not +54 dB, and parsing must not crash on `-inf`. → Task 7 `test_parse_summary_handles_silence`, `test_gain_db_unmeasurable_is_unity`.
5. **The horizon is empty** (`first = last + 1`) right after a recovery or a full prune. The clock must list fallback, not crash or build a negative window. → Task 15 `"an empty horizon (first = last + 1) lists fallback"`.

---

## File Structure

```
packages/transmitter/
  pyproject.toml, LICENSE
  scripts/test-in-debian12.sh          run the suite on Python 3.11 + ffmpeg 5.1 (Docker)
  src/transmitter/
    __init__.py, __main__.py
    errors.py      exception taxonomy (one base, CLI prints `error: …`)
    cli.py         typer app + error boundary (grows across tasks)
    grid.py        the time grid: constants, timestamps, index math, ISO times
    id3.py         RFC 8216 ID3 PRIV timestamp tag
    adts.py        ADTS header parse/build, frame splitting
    segment.py     segment = ID3 tag + 441 ADTS frames; segment keys
    aacenc.py      ffmpeg native-aac encode (bytes / streaming file), calibration, silent frame
    spike.py       phase-1 container spike: build + serve + test page (python -m transmitter.spike)
    config.py      strict config + `config init` template
    workspace.py   ~/.transmitter layout, atomic writes, Epoch
    state.py       local publish state (mirror of horizon + runs + notes digests), fallback version
    layout.py      PlanRow, frame line → pieces → segment bytes (FrameStore)
    station.py     station-root guard, eligibility, file-set key
    planner.py     trivial planner, recovery cut, re-plan, plan.jsonl IO
    audio.py       gapless decode (ffmpeg → f32 PCM), ebur128 meter + parser
    analysis.py    per-show analysis (samples + loudness), cache, gain rule
    render.py      show layout (joins, padding), per-show encode
    pipeline.py    Engine protocol, plan_step, render_step (revalidation, segment writing, GC)
    site.py        timeline.json, notes/<slug>.json, show/<slug>.html builders
    r2.py          boto3 client for R2
    publish.py     uploader, PUT budget, guard read, flock, publish_batch, prune
    fallback.py    fallback loop + notice render and upload
    alerts.py      alert seam (phase 1 logs)
    service.py     wiring for the CLI, run loop (Runner), status
  tests_transmitter/
    __init__.py, helpers.py, test_*.py
antenna/
  package.json, package-lock.json, tsconfig.json, wrangler.jsonc, vitest.config.ts
  worker-configuration.d.ts            generated by `wrangler types`
  src/grid.ts, src/playlist.ts, src/clock.ts, src/index.ts
  test/playlist.test.ts, test/clock.test.ts, test/nowplaying.test.ts
  public/index.html, player.js, nowplaying.js, style.css, offair.html
  templates/show.html                  read by transmitter's publisher
  scripts/deploy-assets.mjs
docs/playout-setup.md                  operator runbook + phase-1 verification checklist
pytest.ini, .gitignore, CLAUDE.md      small edits
```

Task order and model hints (the orchestrator assigns the model; reviewers stay on Opus):

| # | Task | Model hint |
|---|---|---|
| 1 | Spike A: package scaffold, grid, ID3, ADTS, segment assembly | sonnet |
| 2 | Spike B: AAC encoder, spike tool, **HUMAN CHECKPOINT** | opus |
| 3 | Config, workspace, epoch, local state, `config init` | sonnet |
| 4 | Frame layout and FrameStore (segmenter) | sonnet |
| 5 | Station root guard and eligibility | sonnet |
| 6 | Trivial planner | opus |
| 7 | Gapless decode, loudness meter, analysis cache | opus |
| 8 | Show render (joins, gain, encode, frame check) | opus |
| 9 | Plan and render steps (revalidation, recovery, segment writing) | opus |
| 10 | Timeline, notes, show-page builders + template | sonnet |
| 11 | Publisher core (ordering, retry, PUT budget, guard, flock) | opus |
| 12 | Prune | opus |
| 13 | Fallback render and upload | sonnet |
| 14 | CLI commands, run loop, status | sonnet |
| 15 | antenna scaffold and playlist builder | opus |
| 16 | antenna clock loop and Worker entry | opus |
| 17 | Static player page and asset deploy script | sonnet |
| 18 | Setup runbook and phase-1 verification checklist | sonnet |
| 19 | CLAUDE.md and install line | sonnet |

**Dependency note for the checkpoint:** Task 2 ends at a human listening checkpoint. Tasks 3, 5 and 7 do not depend on the container and may proceed while the operator listens (Task 6 consumes `layout.PlanRow` / `validate_rows` from Task 4, so it waits); **Task 4 and everything after it that assembles segments wait for PASS** (on FAIL, Appendix A changes `segment.assemble` and the FrameStore before Task 4 is built).

---

### Task 1: Spike A — package scaffold, grid, ID3, ADTS, segment assembly

**Model hint:** sonnet

**Files:**
- Create: `packages/transmitter/pyproject.toml`, `packages/transmitter/LICENSE` (copy of `packages/emcee/LICENSE`)
- Create: `packages/transmitter/src/transmitter/{__init__,__main__,errors,cli,grid,id3,adts,segment}.py`
- Create: `packages/transmitter/tests_transmitter/{__init__,helpers}.py`, `test_no_llama_or_emcee_imports.py`, `test_grid.py`, `test_id3.py`, `test_adts.py`, `test_segment.py`, `test_cli.py`
- Modify: `pytest.ini` (testpaths)

**Interfaces:**
- Consumes: nothing.
- Produces (every later Python task relies on these exact names):
  - `transmitter.errors`: `TransmitterError(message, details=None)` and subclasses `ConfigError, AdtsError, EncodeError, DecodeError, AnalysisError, StationRootError, PlanError, LayoutError, RenderError, FrameCountDrift(RenderError), PublishError, PublishLocked, PutBudgetExceeded`.
  - `transmitter.grid`: `SAMPLE_RATE=44100, CHANNELS=2, FRAME_SAMPLES=1024, SEGMENT_FRAMES=441, SEGMENT_SAMPLES=451584, D_US=10_240_000, D_MS=10_240, TS_HZ=90_000, TS_PER_SEGMENT=921_600, TS_WRAP=2**33`; `segment_timestamp(n) -> int`; `segment_start_us(epoch_us, n) -> int`; `segment_index_at(epoch_us, t_us) -> int` (floor); `first_segment_at_or_after(epoch_us, t_us) -> int` (ceil); `samples_for_seconds(s) -> int`; `frames_ceil(samples) -> int`; `gap_frames(s) -> int`; `samples_to_us(samples) -> int`; `frame_to_us(frame) -> int`; `us_to_iso(us) -> str` (`…T…:…:….mmmZ`); `iso_to_us(text) -> int`.
  - `transmitter.id3`: `PRIV_OWNER: bytes`; `timestamp_tag(ts: int) -> bytes` (73 bytes); `parse_timestamp_tag(data: bytes) -> tuple[int, int]` (`(ts, tag_length)`).
  - `transmitter.adts`: `AdtsHeader(object_type, sample_rate_index, channel_config, frame_length)`; `parse_header(buf, pos=0) -> AdtsHeader`; `frame_offsets(buf) -> list[int]` (len = frames + 1); `split_frames(buf) -> list[bytes]`; `build_frame(payload, *, object_type=2, sample_rate_index=4, channel_config=2) -> bytes`; `require_station_format(h) -> None`.
  - `transmitter.segment`: `assemble(ts_index: int, frames: Sequence[bytes]) -> bytes`; `parse(data) -> tuple[int, list[bytes]]`; `segment_key(epoch_id, n) -> str` (`seg/<epoch_id>/<n>.aac`).
  - `transmitter.cli`: `app` (typer), `main_cli()`.
  - `tests_transmitter.helpers`: `HAVE_FFMPEG`, `requires_ffmpeg`.

- [ ] **Step 1: Scaffold the package**

`packages/transmitter/pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "llama-transmitter"
version = "0.1.0"
description = "Station playout: plans, renders and publishes the llama station's HLS stream"
requires-python = ">=3.11"
license = "GPL-3.0-or-later"
license-files = ["LICENSE"]
dependencies = [
    "typer>=0.12",
    "pydantic>=2.7",
    "numpy>=1.26",
    "boto3>=1.36",
]

[project.scripts]
transmitter = "transmitter.cli:main_cli"

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.hatch.build.targets.wheel]
packages = ["src/transmitter"]
```

```bash
cp packages/emcee/LICENSE packages/transmitter/LICENSE
```

`packages/transmitter/src/transmitter/__init__.py`:

```python
"""transmitter: plans, renders and publishes the station's HLS stream."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("llama-transmitter")
except PackageNotFoundError:  # raw checkout, no metadata
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
```

`packages/transmitter/src/transmitter/__main__.py`:

```python
"""Entry point for `python -m transmitter`."""

from transmitter.cli import main_cli

if __name__ == "__main__":
    main_cli()
```

`packages/transmitter/src/transmitter/errors.py`:

```python
"""Central exception taxonomy.

`TransmitterError` is the base for expected, operator-actionable failures:
the CLI boundary prints `error: <message>` (plus indented `details`) and
exits 1. Anything else is a bug and surfaces as a traceback. This module
imports nothing from the package, to stay import-cycle-free.
"""


class TransmitterError(Exception):
    def __init__(self, message: str, details: list[str] | None = None):
        super().__init__(message)
        self.details = details or []


class ConfigError(TransmitterError):
    """config.toml could not be parsed or failed validation."""


class AdtsError(TransmitterError):
    """Bytes that should be an ADTS frame sequence are not."""


class EncodeError(TransmitterError):
    """ffmpeg's AAC encode failed."""


class DecodeError(TransmitterError):
    """ffmpeg could not decode a package's audio file."""


class AnalysisError(TransmitterError):
    """A show's durations/loudness could not be measured."""


class StationRootError(TransmitterError):
    """The station root is unset, missing, or lacks its `.station-root` marker."""


class PlanError(TransmitterError):
    """The plan cannot be extended (e.g. nothing eligible)."""


class LayoutError(TransmitterError):
    """The plan's frame layout is inconsistent with what is on disk."""


class RenderError(TransmitterError):
    """A show could not be rendered (the show is skipped and re-planned)."""


class FrameCountDrift(RenderError):
    """The encoder produced a different frame count than planned. Fatal: it
    means the frame-count model is wrong on this ffmpeg, not that one show is bad."""


class PublishError(TransmitterError):
    """An upload/delete against R2 failed after retries."""


class PublishLocked(TransmitterError):
    """Another publish or prune holds the local lock."""


class PutBudgetExceeded(TransmitterError):
    """The local daily PUT budget is spent; publishing stops until tomorrow (UTC)."""
```

`packages/transmitter/src/transmitter/cli.py`:

```python
"""CLI boundary: typer app + `main_cli` error boundary (mirrors emcee's)."""

import sys
import traceback

import typer

from transmitter.errors import TransmitterError

app = typer.Typer(help="Plan, render and publish the station's HLS stream",
                  pretty_exceptions_enable=False, no_args_is_help=True)


def _version_callback(value: bool) -> None:
    if value:
        import transmitter

        typer.echo(transmitter.__version__)
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(None, "--version", callback=_version_callback,
                                 is_eager=True, help="Print the transmitter version and exit."),
) -> None:
    """Station playout."""


def main_cli() -> None:
    try:
        app()
    except TransmitterError as e:
        print(f"error: {e}", file=sys.stderr)
        for line in e.details:
            print(f"  {line}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(130)
    except BrokenPipeError:
        raise SystemExit(0)
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
```

`packages/transmitter/tests_transmitter/__init__.py`: empty file.

`packages/transmitter/tests_transmitter/helpers.py`:

```python
"""Shared test helpers.

This directory is the package `tests_transmitter`, not `tests`: llama's test
modules are top-level (`test_config`, `helpers`, …) and emcee's are the
`tests` package, so either name would collide in the repo-wide pytest run.
Import helpers as `from tests_transmitter.helpers import …`.
"""

import shutil

import pytest

HAVE_FFMPEG = shutil.which("ffmpeg") is not None
requires_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not on PATH")
```

Modify `pytest.ini` — the `testpaths` line becomes:

```ini
testpaths = packages/herder/tests packages/llama/tests packages/emcee/tests packages/transmitter/tests_transmitter scripts
```

Install into the worktree venv:

```bash
./.venv/bin/pip install -e "packages/transmitter[dev]"
./.venv/bin/python -c "import transmitter; print(transmitter.__file__)"   # must be inside the worktree
```

- [ ] **Step 2: Write the failing tests**

`tests_transmitter/test_no_llama_or_emcee_imports.py`:

```python
"""transmitter's only input is the package directory: it never imports llama
or emcee (spec "Architecture"). Checks both src and tests."""

import re
from pathlib import Path

FORBIDDEN = re.compile(
    r"^\s*(?:from|import)\s+(?:llama|emcee)\b"
    r"|(?:__import__|import_module)\s*\(\s*['\"](?:llama|emcee)\b",
    re.M,
)


def _offenders(root: Path) -> list[str]:
    py_files = sorted(root.rglob("*.py"))
    assert py_files, f"no .py files found under {root} — path anchor broke"
    return [str(p) for p in py_files if FORBIDDEN.search(p.read_text())]


def test_pattern_catches_both_forms():
    assert FORBIDDEN.search("import emcee\n")
    assert FORBIDDEN.search("from llama.catalog import x\n")
    # split so this file's own source does not match the pattern it scans for
    assert FORBIDDEN.search("importlib.import_" + "module('emcee.station')\n")
    assert not FORBIDDEN.search("import llama_thing\n")


def test_src_never_imports_llama_or_emcee():
    root = Path(__file__).resolve().parents[1]
    assert _offenders(root / "src") == []


def test_tests_never_import_llama_or_emcee():
    root = Path(__file__).resolve().parents[1]
    assert _offenders(root / "tests_transmitter") == []
```

`tests_transmitter/test_grid.py`:

```python
import pytest

from transmitter import grid


def test_segment_duration_is_exact():
    assert grid.SEGMENT_SAMPLES == 451_584
    assert grid.D_US == 10_240_000
    assert grid.D_MS == 10_240
    assert grid.TS_PER_SEGMENT == 921_600


def test_segment_timestamp_wraps_at_2_pow_33():
    assert grid.segment_timestamp(0) == 0
    assert grid.segment_timestamp(1) == 921_600
    assert grid.segment_timestamp(9320) == 8_589_312_000
    assert grid.segment_timestamp(9321) == 299_008
    assert grid.segment_timestamp(9321) == (9321 * 921_600) % (1 << 33)


def test_segment_timestamp_rejects_negative():
    with pytest.raises(ValueError):
        grid.segment_timestamp(-1)


def test_index_at_floors_and_goes_negative_before_the_epoch():
    e = 1_000_000_000_000
    assert grid.segment_index_at(e, e) == 0
    assert grid.segment_index_at(e, e + grid.D_US - 1) == 0
    assert grid.segment_index_at(e, e + grid.D_US) == 1
    assert grid.segment_index_at(e, e - 1) == -1


def test_first_segment_at_or_after_is_a_ceiling():
    assert grid.first_segment_at_or_after(0, 0) == 0
    assert grid.first_segment_at_or_after(0, 1) == 1
    assert grid.first_segment_at_or_after(0, grid.D_US) == 1
    assert grid.first_segment_at_or_after(0, grid.D_US + 1) == 2


def test_gap_frames_round_up_to_whole_frames():
    assert grid.gap_frames(2.0) == 87      # 88200 samples / 1024 = 86.13
    assert grid.gap_frames(0.75) == 33     # 33075 / 1024 = 32.3
    assert grid.gap_frames(0.0) == 0


def test_iso_round_trip():
    us = grid.iso_to_us("2026-10-10T12:00:00Z")
    assert grid.us_to_iso(us) == "2026-10-10T12:00:00.000Z"
    assert grid.iso_to_us(grid.us_to_iso(us + grid.D_US)) == us + grid.D_US


def test_iso_requires_an_offset():
    with pytest.raises(ValueError):
        grid.iso_to_us("2026-10-10T12:00:00")
```

`tests_transmitter/test_id3.py`:

```python
import pytest

from transmitter import id3


def test_timestamp_tag_layout():
    tag = id3.timestamp_tag(0x1_2345_6789)
    assert len(tag) == 73
    assert tag[:10] == b"ID3\x04\x00\x00\x00\x00\x00\x3f"          # v2.4, size 63 (syncsafe)
    assert tag[10:20] == b"PRIV\x00\x00\x00\x35\x00\x00"           # frame body 53 bytes
    assert tag[20:64] == b"com.apple.streaming.transportStreamTimestamp"
    assert tag[64:65] == b"\x00"
    assert tag[65:] == (0x1_2345_6789).to_bytes(8, "big")


@pytest.mark.parametrize("ts", [0, 1, 921_600, (1 << 33) - 1])
def test_round_trip(ts):
    assert id3.parse_timestamp_tag(id3.timestamp_tag(ts) + b"rest") == (ts, 73)


@pytest.mark.parametrize("ts", [-1, 1 << 33])
def test_rejects_out_of_range(ts):
    with pytest.raises(ValueError):
        id3.timestamp_tag(ts)


def test_parse_rejects_non_id3():
    with pytest.raises(ValueError):
        id3.parse_timestamp_tag(b"\xff\xf1\x50\x80\x03\xdf\xfc")
```

`tests_transmitter/test_adts.py`:

```python
import pytest

from transmitter import adts
from transmitter.errors import AdtsError


def test_build_frame_matches_ffmpeg_header():
    # ffmpeg 8.1 `-c:a aac -f adts`, 44.1 kHz stereo, first frame: fff1508003dffc (30 bytes)
    frame = adts.build_frame(bytes(23))
    assert frame[:7].hex() == "fff1508003dffc"
    assert len(frame) == 30


def test_parse_header_fields():
    h = adts.parse_header(adts.build_frame(b"x" * 100))
    assert (h.object_type, h.sample_rate_index, h.channel_config, h.frame_length) == (2, 4, 2, 107)


def test_split_frames_round_trip():
    frames = [adts.build_frame(bytes([i]) * (i + 1)) for i in range(5)]
    data = b"".join(frames)
    assert adts.split_frames(data) == frames
    assert adts.frame_offsets(data) == [0, 8, 17, 27, 38, 50]


def test_split_rejects_lost_sync():
    with pytest.raises(AdtsError, match="sync"):
        adts.split_frames(adts.build_frame(b"ab") + b"\x00\x00junkjunk")


def test_split_rejects_truncated_frame():
    with pytest.raises(AdtsError):
        adts.split_frames(adts.build_frame(b"abcdef")[:-1])


def test_require_station_format():
    adts.require_station_format(adts.parse_header(adts.build_frame(b"z")))
    with pytest.raises(AdtsError):
        adts.require_station_format(adts.parse_header(adts.build_frame(b"z", channel_config=1)))
```

`tests_transmitter/test_segment.py`:

```python
import pytest

from transmitter import adts, grid, segment


def test_assemble_prefixes_the_grid_timestamp():
    frames = [adts.build_frame(i.to_bytes(4, "big")) for i in range(441)]
    data = segment.assemble(9321, frames)
    ts, parsed = segment.parse(data)
    assert ts == grid.segment_timestamp(9321) == 299_008
    assert parsed == frames


def test_assemble_requires_exactly_441_frames():
    with pytest.raises(ValueError):
        segment.assemble(0, [adts.build_frame(b"x")] * 440)


def test_segment_key():
    assert segment.segment_key("e20261010T120000Z", 42) == "seg/e20261010T120000Z/42.aac"
```

`tests_transmitter/test_cli.py`:

```python
from typer.testing import CliRunner

import transmitter
from transmitter.cli import app


def test_version():
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == transmitter.__version__
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'transmitter.grid'` (and id3/adts/segment); the import-guard and CLI tests pass.

- [ ] **Step 4: Implement grid, id3, adts, segment**

`packages/transmitter/src/transmitter/grid.py`:

```python
"""The station's time grid (spec "The core contract: the stream is a function
of the wall clock").

Segment N covers [E + N*d, E + (N+1)*d). d is exactly 441 AAC frames of 1024
samples at 44.1 kHz = 10.24 s, which is exact in microseconds, milliseconds
and 90 kHz ticks. Everything here is integer arithmetic; floats never touch
the grid.
"""

from datetime import datetime, timedelta, timezone

SAMPLE_RATE = 44_100
CHANNELS = 2
FRAME_SAMPLES = 1024
SEGMENT_FRAMES = 441
SEGMENT_SAMPLES = SEGMENT_FRAMES * FRAME_SAMPLES                # 451_584
D_US = SEGMENT_SAMPLES * 1_000_000 // SAMPLE_RATE               # 10_240_000
D_MS = D_US // 1000                                             # 10_240
TS_HZ = 90_000
TS_PER_SEGMENT = SEGMENT_SAMPLES * TS_HZ // SAMPLE_RATE         # 921_600
TS_WRAP = 1 << 33

if SEGMENT_SAMPLES * 1_000_000 % SAMPLE_RATE or SEGMENT_SAMPLES * TS_HZ % SAMPLE_RATE:
    raise AssertionError("segment duration must be exact in us and in 90 kHz ticks")

_UNIX = datetime(1970, 1, 1, tzinfo=timezone.utc)


def segment_timestamp(n: int) -> int:
    """90 kHz ID3 timestamp of segment n: (n*d*90000) mod 2^33."""
    if n < 0:
        raise ValueError(f"segment index must be >= 0, got {n}")
    return (n * TS_PER_SEGMENT) % TS_WRAP


def segment_start_us(epoch_us: int, n: int) -> int:
    return epoch_us + n * D_US


def segment_index_at(epoch_us: int, t_us: int) -> int:
    """Index of the segment airing at t (floor; negative before the epoch)."""
    return (t_us - epoch_us) // D_US


def first_segment_at_or_after(epoch_us: int, t_us: int) -> int:
    """Smallest n whose start is >= t (ceil)."""
    return -((epoch_us - t_us) // D_US)


def samples_for_seconds(seconds: float) -> int:
    return round(seconds * SAMPLE_RATE)


def frames_ceil(samples: int) -> int:
    return -(-samples // FRAME_SAMPLES)


def gap_frames(seconds: float) -> int:
    """A silence of `seconds`, rounded up to whole frames (spec: the
    inter-show gap is rounded up to whole frames)."""
    return frames_ceil(samples_for_seconds(seconds))


def samples_to_us(samples: int) -> int:
    return samples * 1_000_000 // SAMPLE_RATE


def frame_to_us(frame: int) -> int:
    return samples_to_us(frame * FRAME_SAMPLES)


def us_to_iso(us: int) -> str:
    dt = _UNIX + timedelta(microseconds=us)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def iso_to_us(text: str) -> int:
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(f"timestamp must carry a UTC offset: {text!r}")
    return (dt - _UNIX) // timedelta(microseconds=1)
```

`packages/transmitter/src/transmitter/id3.py`:

```python
"""The RFC 8216 §3.4 packed-audio timestamp: an ID3v2.4 tag holding one PRIV
frame owned by `com.apple.streaming.transportStreamTimestamp`, whose payload is
the segment's first-sample PTS as a 33-bit value in an 8-byte big-endian field."""

PRIV_OWNER = b"com.apple.streaming.transportStreamTimestamp"
_TS_LIMIT = 1 << 33


def _syncsafe(n: int) -> bytes:
    if not 0 <= n < 1 << 28:
        raise ValueError(f"syncsafe integer out of range: {n}")
    return bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F])


def _unsyncsafe(b: bytes) -> int:
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def timestamp_tag(ts: int) -> bytes:
    if not 0 <= ts < _TS_LIMIT:
        raise ValueError(f"timestamp must be a 33-bit value, got {ts}")
    body = PRIV_OWNER + b"\x00" + ts.to_bytes(8, "big")
    frame = b"PRIV" + _syncsafe(len(body)) + b"\x00\x00" + body
    return b"ID3" + bytes([4, 0, 0]) + _syncsafe(len(frame)) + frame


def parse_timestamp_tag(data: bytes) -> tuple[int, int]:
    """(timestamp, tag_length) of the ID3 tag at the start of `data`."""
    if data[:3] != b"ID3" or len(data) < 10:
        raise ValueError("data does not start with an ID3 tag")
    end = 10 + _unsyncsafe(data[6:10])
    pos = 10
    while pos + 10 <= end:
        frame_id = data[pos:pos + 4]
        size = _unsyncsafe(data[pos + 4:pos + 8])
        body = data[pos + 10:pos + 10 + size]
        if frame_id == b"PRIV" and body.startswith(PRIV_OWNER + b"\x00"):
            raw = body[len(PRIV_OWNER) + 1:]
            if len(raw) != 8:
                raise ValueError("transportStreamTimestamp payload is not 8 bytes")
            return int.from_bytes(raw, "big"), end
        pos += 10 + size
    raise ValueError("ID3 tag has no transportStreamTimestamp PRIV frame")
```

`packages/transmitter/src/transmitter/adts.py`:

```python
"""ADTS framing (ISO/IEC 13818-7): parse headers, split a stream into frames,
build headers (tests and the fMP4 contingency need them). Only 7-byte headers
(protection_absent=1) are built; parsing accepts either."""

from dataclasses import dataclass

from transmitter.errors import AdtsError

STATION_OBJECT_TYPE = 2        # AAC-LC
STATION_SAMPLE_RATE_INDEX = 4  # 44100 Hz
STATION_CHANNELS = 2


@dataclass(frozen=True)
class AdtsHeader:
    object_type: int
    sample_rate_index: int
    channel_config: int
    frame_length: int


def parse_header(buf: bytes, pos: int = 0) -> AdtsHeader:
    if len(buf) - pos < 7:
        raise AdtsError(f"truncated ADTS header at byte {pos}")
    b0, b1, b2, b3, b4, b5 = buf[pos:pos + 6]
    if b0 != 0xFF or (b1 & 0xF6) != 0xF0:
        raise AdtsError(f"lost ADTS sync at byte {pos}")
    length = ((b3 & 0x03) << 11) | (b4 << 3) | (b5 >> 5)
    if length < 7:
        raise AdtsError(f"ADTS frame length {length} at byte {pos} is shorter than its header")
    return AdtsHeader(
        object_type=((b2 >> 6) & 0x3) + 1,
        sample_rate_index=(b2 >> 2) & 0xF,
        channel_config=((b2 & 0x1) << 2) | (b3 >> 6),
        frame_length=length,
    )


def frame_offsets(buf: bytes) -> list[int]:
    """Byte offset of every frame, plus a final entry == len(buf)."""
    offsets = [0]
    pos = 0
    while pos < len(buf):
        length = parse_header(buf, pos).frame_length
        if pos + length > len(buf):
            raise AdtsError(f"truncated ADTS frame at byte {pos} ({length} bytes declared)")
        pos += length
        offsets.append(pos)
    return offsets


def split_frames(buf: bytes) -> list[bytes]:
    offsets = frame_offsets(buf)
    return [buf[a:b] for a, b in zip(offsets, offsets[1:])]


def build_frame(payload: bytes, *, object_type: int = STATION_OBJECT_TYPE,
                sample_rate_index: int = STATION_SAMPLE_RATE_INDEX,
                channel_config: int = STATION_CHANNELS) -> bytes:
    length = 7 + len(payload)
    if length >= 1 << 13:
        raise ValueError(f"ADTS frame too long: {length}")
    header = bytes([
        0xFF,
        0xF1,  # MPEG-4, layer 0, protection absent
        (((object_type - 1) & 0x3) << 6) | ((sample_rate_index & 0xF) << 2) | ((channel_config >> 2) & 0x1),
        ((channel_config & 0x3) << 6) | ((length >> 11) & 0x3),
        (length >> 3) & 0xFF,
        ((length & 0x7) << 5) | 0x1F,  # buffer fullness 0x7FF (VBR), high bits
        0xFC,                          # buffer fullness low bits; one raw data block
    ])
    return header + payload


def require_station_format(h: AdtsHeader) -> None:
    got = (h.object_type, h.sample_rate_index, h.channel_config)
    want = (STATION_OBJECT_TYPE, STATION_SAMPLE_RATE_INDEX, STATION_CHANNELS)
    if got != want:
        raise AdtsError(f"ADTS stream is (object type, rate index, channels) {got}, need {want}")
```

`packages/transmitter/src/transmitter/segment.py`:

```python
"""A packed-audio segment: the ID3 timestamp tag + exactly 441 ADTS frames.
`ts_index` is the grid index N for station segments and the loop index k for
fallback segments (spec: fallback segment timestamps are k·d)."""

from typing import Sequence

from transmitter import adts, grid, id3


def assemble(ts_index: int, frames: Sequence[bytes]) -> bytes:
    if len(frames) != grid.SEGMENT_FRAMES:
        raise ValueError(f"a segment is {grid.SEGMENT_FRAMES} frames, got {len(frames)}")
    return id3.timestamp_tag(grid.segment_timestamp(ts_index)) + b"".join(frames)


def parse(data: bytes) -> tuple[int, list[bytes]]:
    ts, tag_len = id3.parse_timestamp_tag(data)
    return ts, adts.split_frames(data[tag_len:])


def segment_key(epoch_id: str, n: int) -> str:
    return f"seg/{epoch_id}/{n}.aac"
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Expected: PASS (all).

Run: `./.venv/bin/python -m pytest -q`
Expected: the whole repo suite PASSES — in particular no "import file mismatch" collection error (that would mean the `tests_transmitter` package name collides).

- [ ] **Step 6: Commit**

```bash
git add pytest.ini packages/transmitter
git commit -m "feat(transmitter): scaffold package; grid, ID3 timestamp, ADTS and segment assembly"
```

---

### Task 2: Spike B — AAC encoder, spike tool, HUMAN CHECKPOINT

**Model hint:** opus

**Files:**
- Create: `packages/transmitter/src/transmitter/aacenc.py`, `packages/transmitter/src/transmitter/spike.py`
- Create: `packages/transmitter/scripts/test-in-debian12.sh`
- Create: `packages/transmitter/tests_transmitter/test_aacenc.py`, `test_spike.py`
- Modify: `packages/transmitter/tests_transmitter/helpers.py` (add `decode_adts`)
- Modify: `.gitignore` (add `*.aac`)

**Interfaces:**
- Consumes: Task 1's `grid`, `adts`, `segment`, `errors.EncodeError`.
- Produces:
  - `transmitter.aacenc`: `ENCODER_PRIMING_SAMPLES = 1024`; `BITRATE = "128k"`; `encode_cmd(ffmpeg) -> list[str]`; `as_station_pcm(pcm) -> np.ndarray` (float32, shape `(n, 2)`); `encode_pcm(pcm, ffmpeg="ffmpeg") -> bytes` (ADTS); `class AacFileEncoder(out_path, ffmpeg="ffmpeg")` with `.write(pcm)`, `.write_silence(samples)`, `.close() -> Path`, `.abort()`, `.samples_written`, context-manager use; `extra_frames(ffmpeg="ffmpeg") -> int` (memoized); `frames_for(padded_samples, extra) -> int`; `pad_to_frame(samples) -> int`; `silent_frame(ffmpeg="ffmpeg") -> bytes` (memoized).
  - `transmitter.spike`: `WRAP_N = 9321`; `show_a(seconds) -> tuple[np.ndarray, dict]`; `show_b(seconds) -> np.ndarray`; `build(out_dir, minutes=12.0, ffmpeg="ffmpeg") -> dict`; `vod_playlist(meta, epoch_us) -> str`; `live_playlist(meta, epoch_us, now_us, window=6) -> str | None`; `serve(out_dir, port=8000, host="0.0.0.0")`; `main(argv=None)`.
  - `tests_transmitter.helpers.decode_adts(data: bytes) -> np.ndarray` (ffmpeg decode to float32 `(n, 2)`).

- [ ] **Step 1: Write the failing encoder tests**

Append to `tests_transmitter/helpers.py`:

```python
import subprocess

import numpy as np


def decode_adts(data: bytes) -> np.ndarray:
    """Decode an ADTS byte stream to float32 (n, 2) with ffmpeg. The decoder
    does NOT trim encoder priming from raw ADTS, so sample 0 of the result is
    the first sample of the priming frame."""
    out = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-f", "aac", "-i", "pipe:0",
         "-f", "f32le", "-ac", "2", "-ar", "44100", "pipe:1"],
        input=data, capture_output=True, check=True,
    ).stdout
    return np.frombuffer(out, dtype="<f4").reshape(-1, 2)
```

`tests_transmitter/test_aacenc.py`:

```python
import numpy as np
import pytest

from tests_transmitter.helpers import decode_adts, requires_ffmpeg
from transmitter import aacenc, adts
from transmitter.errors import EncodeError
from transmitter.grid import FRAME_SAMPLES


def _zeros(n):
    return np.zeros((n, 2), np.float32)


def test_frames_for_and_pad_to_frame():
    assert aacenc.pad_to_frame(0) == 0
    assert aacenc.pad_to_frame(1) == 1024
    assert aacenc.pad_to_frame(2048) == 2048
    assert aacenc.frames_for(4096, 1) == 5
    with pytest.raises(ValueError):
        aacenc.frames_for(4097, 1)


def test_as_station_pcm_rejects_mono():
    with pytest.raises(ValueError):
        aacenc.as_station_pcm(np.zeros(10, np.float32))


@requires_ffmpeg
def test_encode_pcm_yields_station_format_frames():
    frames = adts.split_frames(aacenc.encode_pcm(_zeros(4 * FRAME_SAMPLES)))
    for f in frames:
        adts.require_station_format(adts.parse_header(f))


@requires_ffmpeg
@pytest.mark.parametrize("frames", [3, 441, 1000])
def test_extra_frames_is_the_same_for_every_padded_length(frames):
    extra = aacenc.extra_frames()
    got = len(adts.split_frames(aacenc.encode_pcm(_zeros(frames * FRAME_SAMPLES))))
    assert got == aacenc.frames_for(frames * FRAME_SAMPLES, extra)


@requires_ffmpeg
def test_priming_matches_the_declared_constant():
    pcm = _zeros(44_100)
    pcm[5000:5003] = 0.8
    decoded = decode_adts(aacenc.encode_pcm(pcm))
    peak = int(np.argmax(np.abs(decoded[:, 0])))
    assert abs((peak - 5001) - aacenc.ENCODER_PRIMING_SAMPLES) <= 3


@requires_ffmpeg
def test_file_encoder_streams_and_renames_atomically(tmp_path):
    out = tmp_path / "shows" / "k.aac"
    enc = aacenc.AacFileEncoder(out)
    enc.write(_zeros(3000))
    enc.write_silence(5000)
    assert enc.samples_written == 8000
    assert enc.close() == out
    assert len(adts.split_frames(out.read_bytes())) == aacenc.frames_for(aacenc.pad_to_frame(8000), aacenc.extra_frames())
    assert [p.name for p in out.parent.iterdir()] == ["k.aac"]


@requires_ffmpeg
def test_file_encoder_abort_leaves_nothing(tmp_path):
    out = tmp_path / "k.aac"
    with pytest.raises(RuntimeError):
        with aacenc.AacFileEncoder(out) as enc:
            enc.write(_zeros(2048))
            raise RuntimeError("boom")
    assert list(tmp_path.iterdir()) == []


@requires_ffmpeg
def test_silent_frame_is_station_format_and_decodes_to_silence():
    frame = aacenc.silent_frame()
    adts.require_station_format(adts.parse_header(frame))
    decoded = decode_adts(frame * 20)
    assert float(np.max(np.abs(decoded))) < 1e-4


def test_missing_ffmpeg_is_an_encode_error():
    with pytest.raises(EncodeError):
        aacenc.encode_pcm(_zeros(1024), ffmpeg="/nonexistent/ffmpeg")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_aacenc.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'transmitter.aacenc'`.

- [ ] **Step 3: Implement `aacenc.py`**

```python
"""AAC-LC encoding with ffmpeg's native `aac` encoder (present in ffmpeg 5.1;
no libfdk). 128 kbps target, 44.1 kHz stereo, ADTS output.

The native encoder has no strict CBR mode: `-b:a 128k` targets 128 kbps and
digital silence encodes to tiny frames. Frame counts are what matter here:
for input padded to whole frames the encoder emits `padded/1024 + extra`
frames, with `extra` measured by `extra_frames()` rather than assumed (1 on
ffmpeg 8.1; the Debian 12 run checks 5.1)."""

import functools
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from transmitter import adts
from transmitter.errors import EncodeError
from transmitter.grid import CHANNELS, FRAME_SAMPLES, SAMPLE_RATE

ENCODER_PRIMING_SAMPLES = 1024   # ffmpeg aac's declared initial_padding
BITRATE = "128k"


def encode_cmd(ffmpeg: str) -> list[str]:
    return [ffmpeg, "-nostdin", "-hide_banner", "-v", "error",
            "-f", "f32le", "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS), "-i", "pipe:0",
            "-c:a", "aac", "-b:a", BITRATE, "-f", "adts", "pipe:1"]


def as_station_pcm(pcm: np.ndarray) -> np.ndarray:
    arr = np.ascontiguousarray(pcm, dtype=np.float32)
    if arr.ndim != 2 or arr.shape[1] != CHANNELS:
        raise ValueError(f"station PCM is float32 shaped (n, {CHANNELS}); got {arr.shape}")
    return arr


def encode_pcm(pcm: np.ndarray, ffmpeg: str = "ffmpeg") -> bytes:
    """Encode a whole (small) PCM buffer in one ffmpeg call."""
    try:
        proc = subprocess.run(encode_cmd(ffmpeg), input=as_station_pcm(pcm).tobytes(),
                              capture_output=True)
    except OSError as exc:
        raise EncodeError(f"cannot run {ffmpeg}: {exc}") from exc
    if proc.returncode != 0:
        tail = proc.stderr.decode(errors="replace").strip()[-500:]
        raise EncodeError(f"ffmpeg aac encode failed (exit {proc.returncode}): {tail}")
    return proc.stdout


class AacFileEncoder:
    """Streams PCM into one ffmpeg encode whose ADTS output appears at
    `out_path` atomically on close(). stdout goes straight to a unique temp
    file and stderr to an anonymous temp file, so no pipe can fill up and
    deadlock the writer."""

    def __init__(self, out_path: Path, ffmpeg: str = "ffmpeg"):
        self.out_path = Path(out_path)
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.out_path.parent, prefix=f".{self.out_path.name}.",
                                   suffix=".tmp")
        self._tmp = Path(tmp)
        self._out = os.fdopen(fd, "wb")
        self._err = tempfile.TemporaryFile()
        try:
            self._proc = subprocess.Popen(encode_cmd(ffmpeg), stdin=subprocess.PIPE,
                                          stdout=self._out, stderr=self._err)
        except OSError as exc:
            self._out.close()
            self._cleanup()
            raise EncodeError(f"cannot run {ffmpeg}: {exc}") from exc
        self.samples_written = 0
        self._closed = False

    def __enter__(self) -> "AacFileEncoder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self.abort()

    def write(self, pcm: np.ndarray) -> None:
        arr = as_station_pcm(pcm)
        try:
            self._proc.stdin.write(arr.tobytes())
        except BrokenPipeError as exc:
            raise EncodeError(f"ffmpeg aac encoder exited early: {self._stderr_tail()}") from exc
        self.samples_written += len(arr)

    def write_silence(self, samples: int, chunk: int = 1 << 16) -> None:
        while samples > 0:
            n = min(samples, chunk)
            self.write(np.zeros((n, CHANNELS), np.float32))
            samples -= n

    def close(self) -> Path:
        try:
            self._proc.stdin.close()
        except BrokenPipeError:
            pass
        rc = self._proc.wait()
        self._out.close()
        self._closed = True
        if rc != 0:
            tail = self._stderr_tail()
            self._cleanup()
            raise EncodeError(f"ffmpeg aac encode failed (exit {rc}): {tail}")
        self._err.close()
        os.replace(self._tmp, self.out_path)
        return self.out_path

    def abort(self) -> None:
        if self._closed:
            return
        self._proc.kill()
        self._proc.wait()
        try:
            self._proc.stdin.close()
        except BrokenPipeError:
            pass
        self._out.close()
        self._closed = True
        self._cleanup()

    def _cleanup(self) -> None:
        self._err.close()
        self._tmp.unlink(missing_ok=True)

    def _stderr_tail(self) -> str:
        self._err.seek(0)
        return self._err.read().decode(errors="replace").strip()[-500:]


def pad_to_frame(samples: int) -> int:
    return -(-samples // FRAME_SAMPLES) * FRAME_SAMPLES


def frames_for(padded_samples: int, extra: int) -> int:
    if padded_samples % FRAME_SAMPLES:
        raise ValueError("pad the input to a whole number of frames first")
    return padded_samples // FRAME_SAMPLES + extra


@functools.cache
def extra_frames(ffmpeg: str = "ffmpeg") -> int:
    """Frames the encoder emits beyond padded_samples/1024 (priming + flush)."""
    probe = 8
    got = len(adts.split_frames(encode_pcm(np.zeros((probe * FRAME_SAMPLES, CHANNELS), np.float32), ffmpeg)))
    extra = got - probe
    if extra < 0:
        raise EncodeError(f"{ffmpeg} emitted {got} frames for {probe} frames of input")
    return extra


@functools.cache
def silent_frame(ffmpeg: str = "ffmpeg") -> bytes:
    """One steady-state encoded frame of digital silence, repeated to fill
    gaps between shows (spec: "pre-encoded silent frames fill the gap")."""
    frames = adts.split_frames(encode_pcm(np.zeros((16 * FRAME_SAMPLES, CHANNELS), np.float32), ffmpeg))
    frame = frames[len(frames) // 2]
    adts.require_station_format(adts.parse_header(frame))
    return frame
```

- [ ] **Step 4: Run the encoder tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_aacenc.py -q`
Expected: PASS.

- [ ] **Step 5: Write the failing spike tests**

`tests_transmitter/test_spike.py`:

```python
import json

import numpy as np

from tests_transmitter.helpers import requires_ffmpeg
from transmitter import grid, segment, spike


def test_wrap_n_is_the_first_wrapped_segment():
    assert grid.segment_timestamp(spike.WRAP_N) < grid.segment_timestamp(spike.WRAP_N - 1)


def test_show_a_segue_is_phase_continuous():
    pcm, info = spike.show_a(36.0)
    mono = pcm[:, 0].astype(np.float64)
    at = int(info["segue_at_s"] * grid.SAMPLE_RATE)
    window = mono[at - 2000:at + 2000]
    # a phase-continuous 0.25-amplitude sine below 600 Hz never moves more than
    # 2*pi*600/44100*0.25 = 0.0214 between samples; a click would.
    assert float(np.max(np.abs(np.diff(window)))) < 0.0214


def test_live_playlist_window_and_endlist():
    meta = {"n0": 100, "count": 10}
    e = 0
    at = lambda n: grid.segment_start_us(e, n) + 1   # noqa: E731
    assert spike.live_playlist(meta, e, at(99)) is None
    body = spike.live_playlist(meta, e, at(107))
    assert "#EXT-X-MEDIA-SEQUENCE:102\n" in body
    assert body.count("#EXTINF:10.240,") == 6
    assert "seg/107.aac" in body and "#EXT-X-ENDLIST" not in body
    done = spike.live_playlist(meta, e, at(115))
    assert done.rstrip().endswith("#EXT-X-ENDLIST") and "seg/109.aac" in done


@requires_ffmpeg
def test_build_produces_grid_segments_with_the_wrap_in_show_b(tmp_path):
    meta = spike.build(tmp_path, minutes=1.5)
    n0, count = meta["n0"], meta["count"]
    assert n0 < spike.WRAP_N <= n0 + count - 1
    assert meta["wrap_at_s"] > meta["show_b_at_s"]
    for n in range(n0, n0 + count):
        ts, frames = segment.parse((tmp_path / "seg" / f"{n}.aac").read_bytes())
        assert ts == grid.segment_timestamp(n)
        assert len(frames) == grid.SEGMENT_FRAMES
    vod = (tmp_path / "vod.m3u8").read_text()
    assert vod.count("#EXTINF:10.240,") == count
    assert vod.rstrip().endswith("#EXT-X-ENDLIST")
    assert json.loads((tmp_path / "meta.json").read_text()) == meta
    assert "hls.js" in (tmp_path / "index.html").read_text()
```

- [ ] **Step 6: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_spike.py -q`
Expected: FAIL — `ImportError: cannot import name 'spike'`.

- [ ] **Step 7: Implement `spike.py`**

```python
"""Phase-1 container spike (spec "Phase-1 spike").

Builds ~12 minutes of frame-count ADTS segments from synthetic audio -- a
phase-continuous segue inside show A, DJ-style pauses around a beep "clip",
a 2 s show gap, and a 2^33 timestamp wrap inside show B -- plus a test page,
a VOD playlist and a wall-clock live playlist served by a tiny local server:

    python -m transmitter.spike build OUT_DIR [--minutes 12]
    python -m transmitter.spike serve OUT_DIR [--port 8000]

It uses the production grid/id3/adts/segment/aacenc modules, so a pass here is
evidence about the code that will air. Keep OUT_DIR outside the repo.
"""

import argparse
import json
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

from transmitter import aacenc, adts, grid, segment
from transmitter.grid import D_US, SAMPLE_RATE, SEGMENT_FRAMES, TS_PER_SEGMENT, TS_WRAP

WRAP_N = -(-TS_WRAP // TS_PER_SEGMENT)   # 9321: first segment whose timestamp has wrapped
WINDOW = 6
FADE_S = 0.01


def _tone(freq: float, n: int, phase: float, amp: float) -> tuple[np.ndarray, float]:
    t = np.arange(n, dtype=np.float64)
    out = amp * np.sin(phase + 2 * np.pi * freq * t / SAMPLE_RATE)
    return out, (phase + 2 * np.pi * freq * n / SAMPLE_RATE) % (2 * np.pi)


def _fade(x: np.ndarray) -> np.ndarray:
    n = min(int(FADE_S * SAMPLE_RATE), len(x) // 2)
    if n == 0:
        return x
    ramp = 0.5 - 0.5 * np.cos(np.linspace(0.0, np.pi, n))
    x = x.copy()
    x[:n] *= ramp
    x[-n:] *= ramp[::-1]
    return x


def _stereo(mono: np.ndarray) -> np.ndarray:
    return np.repeat(mono.astype(np.float32)[:, None], 2, axis=1)


def show_a(seconds: float) -> tuple[np.ndarray, dict]:
    """440 Hz, then a phase-continuous segue to 554.37 Hz at a sample that is
    not frame-aligned, 0.75 s pause, 3 s of beeps (the "DJ clip"), 0.75 s
    pause, 440 Hz to the end. Only outer edges are faded: the segue must be
    click-free on its own."""
    n = grid.samples_for_seconds(seconds)
    pause = grid.samples_for_seconds(0.75)
    clip = grid.samples_for_seconds(3.0)
    segue_at = int(n * 0.30) + 337
    music1_end = int(n * 0.55)
    tail = n - music1_end - 2 * pause - clip
    if tail <= 0:
        raise ValueError("show A is too short")
    a1, phase = _tone(440.0, segue_at, 0.0, 0.25)
    a2, _ = _tone(554.37, music1_end - segue_at, phase, 0.25)
    beeps = np.zeros(clip)
    on = grid.samples_for_seconds(0.2)
    period = grid.samples_for_seconds(0.5)
    for start in range(0, clip - on, period):
        beep, _ = _tone(1000.0, on, 0.0, 0.2)
        beeps[start:start + on] = _fade(beep)
    a3, _ = _tone(440.0, tail, 0.0, 0.25)
    pcm = np.concatenate([_fade(np.concatenate([a1, a2])), np.zeros(pause), beeps,
                          np.zeros(pause), _fade(a3)])
    return _stereo(pcm), {"segue_at_s": segue_at / SAMPLE_RATE}


def show_b(seconds: float) -> np.ndarray:
    """660 Hz under a slow 0.25 Hz swell: continuous, so a glitch at any
    segment boundary or at the timestamp wrap is audible."""
    n = grid.samples_for_seconds(seconds)
    t = np.arange(n, dtype=np.float64) / SAMPLE_RATE
    amp = 0.15 + 0.1 * (0.5 - 0.5 * np.cos(2 * np.pi * 0.25 * t))
    return _stereo(_fade(amp * np.sin(2 * np.pi * 660.0 * t)))


def _pad(pcm: np.ndarray) -> np.ndarray:
    missing = aacenc.pad_to_frame(len(pcm)) - len(pcm)
    return np.concatenate([pcm, np.zeros((missing, 2), np.float32)])


def _header(first: int) -> list[str]:
    return ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-TARGETDURATION:11",
            f"#EXT-X-MEDIA-SEQUENCE:{first}"]


def _entry(n: int, epoch_us: int) -> list[str]:
    return [f"#EXT-X-PROGRAM-DATE-TIME:{grid.us_to_iso(grid.segment_start_us(epoch_us, n))}",
            "#EXTINF:10.240,", f"seg/{n}.aac"]


def vod_playlist(meta: dict, epoch_us: int) -> str:
    lines = _header(meta["n0"]) + ["#EXT-X-PLAYLIST-TYPE:VOD"]
    for n in range(meta["n0"], meta["n0"] + meta["count"]):
        lines += _entry(n, epoch_us)
    lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"


def live_playlist(meta: dict, epoch_us: int, now_us: int, window: int = WINDOW) -> str | None:
    first, last = meta["n0"], meta["n0"] + meta["count"] - 1
    cur = grid.segment_index_at(epoch_us, now_us)
    if cur < first:
        return None
    end = min(cur, last)
    start = max(first, end - window + 1)
    lines = _header(start)
    for n in range(start, end + 1):
        lines += _entry(n, epoch_us)
    if cur > last:
        lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"


def build(out_dir: Path, minutes: float = 12.0, ffmpeg: str = "ffmpeg") -> dict:
    out = Path(out_dir)
    (out / "seg").mkdir(parents=True, exist_ok=True)
    total_s = minutes * 60.0
    a_s = min(300.0, total_s * 0.4)
    gap_s = 2.0
    pcm_a, a_info = show_a(a_s)
    frames_a = adts.split_frames(aacenc.encode_pcm(_pad(pcm_a), ffmpeg))
    frames_b = adts.split_frames(aacenc.encode_pcm(_pad(show_b(total_s - a_s - gap_s)), ffmpeg))
    silent = aacenc.silent_frame(ffmpeg)
    gap = grid.gap_frames(gap_s)
    stream = frames_a + [silent] * gap + frames_b
    count = -(-len(stream) // SEGMENT_FRAMES)
    stream += [silent] * (count * SEGMENT_FRAMES - len(stream))
    b_start = len(frames_a) + gap
    n0 = WRAP_N - int(count * 0.6)
    if (WRAP_N - n0) * SEGMENT_FRAMES <= b_start:
        raise ValueError("too few minutes for the timestamp wrap to land inside show B")
    for i in range(count):
        n = n0 + i
        frames = stream[i * SEGMENT_FRAMES:(i + 1) * SEGMENT_FRAMES]
        (out / "seg" / f"{n}.aac").write_bytes(segment.assemble(n, frames))
    meta = {
        "n0": n0, "count": count, "wrap_between": [WRAP_N - 1, WRAP_N],
        "segue_at_s": a_info["segue_at_s"],
        "show_gap_at_s": len(frames_a) * grid.FRAME_SAMPLES / SAMPLE_RATE,
        "show_b_at_s": b_start * grid.FRAME_SAMPLES / SAMPLE_RATE,
        "wrap_at_s": (WRAP_N - n0) * D_US / 1_000_000,
    }
    nominal_epoch_us = int(time.time()) * 1_000_000 - n0 * D_US
    (out / "vod.m3u8").write_text(vod_playlist(meta, nominal_epoch_us))
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    (out / "index.html").write_text(PAGE)
    return meta


def serve(out_dir: Path, port: int = 8000, host: str = "0.0.0.0") -> None:
    out = Path(out_dir)
    meta = json.loads((out / "meta.json").read_text())
    # choose E so the live window is full the moment the server starts
    epoch_us = time.time_ns() // 1000 - (meta["n0"] + WINDOW - 1) * D_US

    class Handler(SimpleHTTPRequestHandler):
        extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                          ".m3u8": "application/vnd.apple.mpegurl", ".aac": "audio/aac"}

        def end_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self):
            if self.path.split("?")[0] == "/live.m3u8":
                body = live_playlist(meta, epoch_us, time.time_ns() // 1000)
                if body is None:
                    self.send_error(404)
                    return
                data = body.encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.apple.mpegurl")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            super().do_GET()

    httpd = ThreadingHTTPServer((host, port), partial(Handler, directory=str(out)))
    print(f"serving {out} at http://{host}:{port}/  (segue at {meta['segue_at_s']:.1f}s, "
          f"show gap at {meta['show_gap_at_s']:.1f}s, wrap at {meta['wrap_at_s']:.1f}s "
          f"of the VOD; the live playlist starts at the beginning and ends with ENDLIST)")
    httpd.serve_forever()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m transmitter.spike")
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("out_dir", type=Path)
    b.add_argument("--minutes", type=float, default=12.0)
    s = sub.add_parser("serve")
    s.add_argument("out_dir", type=Path)
    s.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if args.cmd == "build":
        print(json.dumps(build(args.out_dir, args.minutes), indent=2))
    else:
        serve(args.out_dir, args.port)


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>transmitter container spike</title>
<!-- local spike page only: the production player self-hosts hls.js (Task 17) -->
<script src="https://cdn.jsdelivr.net/npm/hls.js@1.7.3/dist/hls.min.js"></script>
<style>body{font:16px system-ui;margin:2em;max-width:42em}button{font-size:1.1em;margin:.3em}
pre{background:#eee;padding:.5em;white-space:pre-wrap;max-height:20em;overflow:auto}</style>
</head><body>
<h1>transmitter container spike</h1>
<p><button id="live">Play live.m3u8</button><button id="vod">Play vod.m3u8</button>
<button id="stop">Stop</button></p>
<audio id="audio" controls></audio>
<p id="mode"></p><p id="pos"></p>
<pre id="log"></pre>
<script>
const audio = document.getElementById("audio"), log = document.getElementById("log");
const native = (navigator.vendor || "").startsWith("Apple") &&
  audio.canPlayType("application/vnd.apple.mpegurl") !== "";
document.getElementById("mode").textContent = native
  ? "player: native HLS (Apple WebKit)" : "player: hls.js " + (window.Hls ? Hls.version : "(not loaded)");
let hls = null;
function say(m) { log.textContent += new Date().toISOString() + "  " + m + "\n"; }
function stop() { if (hls) { hls.destroy(); hls = null; } audio.removeAttribute("src"); audio.load(); }
function play(url) {
  stop(); say("loading " + url);
  if (native) { audio.src = url; }
  else {
    hls = new Hls({ liveSyncDurationCount: 3 });
    hls.on(Hls.Events.ERROR, (e, d) => say("hls.js " + (d.fatal ? "FATAL " : "") + d.type + " " + d.details));
    hls.on(Hls.Events.LEVEL_LOADED, (e, d) => { if (!d.details.live) say("playlist has ENDLIST"); });
    hls.loadSource(url); hls.attachMedia(audio);
  }
  audio.play().catch(err => say("play() rejected: " + err));
}
audio.addEventListener("ended", () => say("ended (ENDLIST reached)"));
audio.addEventListener("error", () => say("media error " + (audio.error && audio.error.code)));
audio.addEventListener("waiting", () => say("waiting (stall?) at " + audio.currentTime.toFixed(2)));
document.getElementById("live").onclick = () => play("live.m3u8");
document.getElementById("vod").onclick = () => play("vod.m3u8");
document.getElementById("stop").onclick = stop;
setInterval(() => {
  let d = null;
  if (hls && hls.playingDate) d = hls.playingDate;
  else if (native && audio.getStartDate) {
    const s = audio.getStartDate().getTime();
    if (!isNaN(s)) d = new Date(s + audio.currentTime * 1000);
  }
  document.getElementById("pos").textContent =
    "t=" + audio.currentTime.toFixed(2) + "s  program-date-time=" + (d ? d.toISOString() : "n/a");
}, 500);
</script></body></html>
"""

if __name__ == "__main__":
    main()
```

- [ ] **Step 8: Run the spike tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_spike.py -q`
Expected: PASS.

- [ ] **Step 9: Add the Debian 12 runner and check hugo's ffmpeg**

`packages/transmitter/scripts/test-in-debian12.sh` (then `chmod +x`):

```sh
#!/bin/sh
# Run transmitter's tests on hugo's versions: Debian 12 = Python 3.11 + ffmpeg 5.1.
# Usage: packages/transmitter/scripts/test-in-debian12.sh [extra pytest args]
set -eu
repo=$(cd "$(dirname "$0")/../../.." && pwd)
exec docker run --rm -v "$repo:/src:ro" debian:12 sh -euc '
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 python3-venv ffmpeg >/dev/null
  ffmpeg -version | head -1
  python3 --version
  mkdir /work
  tar -C /src --exclude=./.venv --exclude=./.git --exclude=./.claude \
      --exclude="*/node_modules" --exclude="*/__pycache__" -cf - . | tar -C /work -xf -
  python3 -m venv /venv
  /venv/bin/pip install -q -e "/work/packages/transmitter[dev]"
  cd /work
  /venv/bin/python -m pytest -q -p no:cacheprovider packages/transmitter/tests_transmitter "$@"
' sh "$@"
```

Run: `packages/transmitter/scripts/test-in-debian12.sh`
Expected: prints `ffmpeg version 5.1.x` and `Python 3.11.x`, then PASS. If `test_priming_matches_the_declared_constant` or `test_extra_frames_is_the_same_for_every_padded_length` fails on 5.1, STOP and report BLOCKED with the measured values: the frame-count model must hold on hugo.

Add to `.gitignore`:

```
*.aac
```

- [ ] **Step 10: Commit**

```bash
git add .gitignore packages/transmitter
git commit -m "feat(transmitter): native-aac encoder wrapper and the phase-1 container spike"
```

- [ ] **Step 11: HUMAN CHECKPOINT — the operator listens (orchestrator: stop and escalate)**

The orchestrator reports to the operator and waits for a recorded PASS before starting Task 4 (Tasks 3, 5 and 7 may proceed meanwhile). Procedure for the operator:

```bash
SPIKE="$HOME/spike-out"            # anywhere outside the repo
./.venv/bin/python -m transmitter.spike build "$SPIKE"
./.venv/bin/python -m transmitter.spike serve "$SPIKE"     # note the printed segue/gap/wrap offsets
```

1. **Chrome (hls.js):** open `http://localhost:8000/`, press *Play live.m3u8*, listen ≥ 3 minutes (≥ 15 segment boundaries) in show B's steady tone. Then *Play vod.m3u8* and seek to just before the printed segue, show-gap and wrap offsets in turn.
2. **Safari (macOS):** same as 1 (native HLS).
3. **iPhone/iPad on the same LAN:** `http://<mac-lan-ip>:8000/`, *Play live.m3u8*, lock the screen, let it play ≥ 10 minutes; then AirPlay to a receiver.
4. **VLC:** *Open Network Stream* `http://localhost:8000/live.m3u8`, then `…/vod.m3u8`.
5. **ENDLIST:** let a live session run to its end (the live playlist appends `#EXT-X-ENDLIST` after the last segment): every player stops cleanly, with no error loop.

**PASS requires all of:** (a) no click, dropout or stutter at segment boundaries in the continuous tones, in every player; the segue is a clean pitch step with no click; the show gap is ~2 s of clean silence with clean onsets either side; (b) playback continues through the timestamp wrap with no stall, skip or error (hls.js log: no FATAL; program-date-time keeps advancing smoothly); (c) all four players accept the packed-audio container; (d) iOS lock-screen playback runs 10 minutes uninterrupted and AirPlay works.

Record per player, per criterion, in the run's SDD ledger.

**If it FAILS:**
- (b) or (c) in any player, or (a) at *every* segment boundary → the container is the problem: switch to fMP4. Stop the run and escalate to the operator with Appendix A; it is planned and reviewed as an amendment to Task 4 (the segment writer), then this spike is re-run in fMP4 mode before Task 4 proceeds.
- (a) only at the show gap → silent-frame splicing problem, not the container: escalate (candidate fix: take the trailing frames of the preceding show's own encode as the gap filler instead of a repeated standalone silent frame).
- (d) only → a player-page issue, not the container: note it for the phase-4 player and continue.

---

### Task 3: Config, workspace, epoch, local state, `config init`

**Model hint:** sonnet

**Files:**
- Create: `packages/transmitter/src/transmitter/config.py`, `workspace.py`, `state.py`
- Modify: `packages/transmitter/src/transmitter/cli.py` (add `config init`)
- Create: `packages/transmitter/tests_transmitter/test_config.py`, `test_workspace.py`, `test_state.py`
- Modify: `packages/transmitter/tests_transmitter/test_cli.py`

**Interfaces:**
- Consumes: `grid` (Task 1), `errors.ConfigError`.
- Produces:
  - `transmitter.config`: `DEFAULT_ROOT`, `default_root() -> Path` (`$TRANSMITTER_ROOT` else `~/.transmitter`); models `StationConfig(root: Path|None, quiet_minutes=10.0)`, `PlannerConfig(seed=0, start_delay_minutes=10.0)`, `RenderConfig(ffmpeg="ffmpeg", lead_hours=24.0, low_water_hours=20.0, music_target_lufs=-16.0, speech_target_lufs=-16.0, clip_pause_seconds=0.75, show_gap_seconds=2.0)`, `PublishConfig(account_id, bucket, endpoint_url, batch_segments=360, daily_put_budget=17500, prune_margin_minutes=10.0, prune_min_segments=60, guard_check_minutes=15.0)`, `AntennaConfig(dir: Path|None, site_url: str|None, station_name="llama radio")`, `TransmitterConfig(root, station, planner, render, publish, antenna)`; `load_config(path=None) -> TransmitterConfig`; `DEFAULT_CONFIG_TOML: str`.
  - `transmitter.workspace`: `atomic_write_bytes(path, data)`, `atomic_write_text(path, text)`, `write_json(path, obj)`, `read_json(path, default=None)`; `Workspace(root)` with properties `plan_path, cache_dir, render_dir, shows_dir, epoch_path, publish_state_path, puts_path, guard_cache_path, fallback_path, lock_path` and methods `seg_dir(epoch_id)`, `fallback_dir(version)`; `Epoch(epoch_id, epoch_us)` with `.iso`, `.start_us(n)`, `.index_at(t_us)`; `load_epoch(ws) -> Epoch | None`; `load_or_create_epoch(ws, now_us) -> Epoch`.
  - `transmitter.state`: `PublishState(epoch_id=None, first=None, last=None, runs=[], notes={})`; `load_publish_state(ws)`, `save_publish_state(ws, state)`, `load_fallback_version(ws) -> str | None`, `save_fallback_version(ws, version)`.

- [ ] **Step 1: Write the failing tests**

`tests_transmitter/test_config.py`:

```python
import tomllib
from pathlib import Path

import pytest

from transmitter.config import (DEFAULT_CONFIG_TOML, DEFAULT_ROOT, TransmitterConfig,
                                default_root, load_config)
from transmitter.errors import ConfigError


def test_default_root(monkeypatch, tmp_path):
    monkeypatch.delenv("TRANSMITTER_ROOT", raising=False)
    assert default_root() == DEFAULT_ROOT == Path.home() / ".transmitter"
    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path))
    assert default_root() == tmp_path
    assert TransmitterConfig().root == tmp_path


def test_defaults():
    cfg = TransmitterConfig()
    assert cfg.render.lead_hours == 24.0 and cfg.render.low_water_hours == 20.0
    assert cfg.render.music_target_lufs == -16.0 and cfg.render.speech_target_lufs == -16.0
    assert cfg.render.clip_pause_seconds == 0.75 and cfg.render.show_gap_seconds == 2.0
    assert cfg.publish.prune_margin_minutes == 10.0 and cfg.publish.guard_check_minutes == 15.0
    assert cfg.publish.prune_min_segments == 60
    assert cfg.station.root is None


def test_missing_file_gives_defaults(tmp_path):
    assert load_config(tmp_path / "nope.toml") == TransmitterConfig()


@pytest.mark.parametrize("text", [
    "typo = 1\n",                       # top level
    "[render]\nlead_hour = 1\n",        # nested section: strictness must reach it
    "[publish]\nbuckett = 'x'\n",
])
def test_unknown_keys_are_errors(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(text)
    with pytest.raises(ConfigError, match="invalid config"):
        load_config(path)


def test_low_water_must_be_below_lead(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[render]\nlead_hours = 10\nlow_water_hours = 10\n")
    with pytest.raises(ConfigError):
        load_config(path)


def test_bad_toml_is_a_config_error(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[render\n")
    with pytest.raises(ConfigError):
        load_config(path)


def test_template_parses_to_the_defaults():
    parsed = TransmitterConfig.model_validate(tomllib.loads(DEFAULT_CONFIG_TOML))
    assert parsed.model_dump(exclude={"root"}) == TransmitterConfig().model_dump(exclude={"root"})
```

`tests_transmitter/test_workspace.py`:

```python
import pytest

from transmitter import grid
from transmitter.errors import ConfigError
from transmitter.workspace import (Epoch, Workspace, atomic_write_bytes, load_epoch,
                                   load_or_create_epoch, read_json, write_json)


def test_atomic_write_leaves_no_temp(tmp_path):
    target = tmp_path / "a" / "b.bin"
    atomic_write_bytes(target, b"one")
    atomic_write_bytes(target, b"two")
    assert target.read_bytes() == b"two"
    assert [p.name for p in target.parent.iterdir()] == ["b.bin"]


def test_json_round_trip_and_default(tmp_path):
    write_json(tmp_path / "x.json", {"a": 1})
    assert read_json(tmp_path / "x.json") == {"a": 1}
    assert read_json(tmp_path / "missing.json", {"d": 0}) == {"d": 0}


def test_workspace_paths(tmp_path):
    ws = Workspace(tmp_path)
    assert ws.plan_path == tmp_path / "plan.jsonl"
    assert ws.seg_dir("e1") == tmp_path / "render" / "seg" / "e1"
    assert ws.shows_dir == tmp_path / "render" / "shows"


def test_epoch_is_created_once_on_a_whole_second(tmp_path):
    ws = Workspace(tmp_path)
    now = grid.iso_to_us("2026-10-10T12:00:00Z") + 123_456
    e = load_or_create_epoch(ws, now)
    assert e.epoch_us == now - 123_456
    assert e.epoch_id == "e20261010T120000Z"
    assert e.iso == "2026-10-10T12:00:00.000Z"
    assert load_or_create_epoch(ws, now + 10**9) == e
    assert read_json(ws.epoch_path)["d"] == 10.24


def test_epoch_index_math():
    e = Epoch("x", 1_000_000)
    assert e.start_us(2) == 1_000_000 + 2 * grid.D_US
    assert e.index_at(e.start_us(2) + 5) == 2


def test_an_edited_d_is_refused(tmp_path):
    ws = Workspace(tmp_path)
    write_json(ws.epoch_path, {"epoch_id": "x", "epoch": "2026-10-10T12:00:00.000Z", "d": 6.0})
    with pytest.raises(ConfigError, match="epoch change"):
        load_epoch(ws)
```

`tests_transmitter/test_state.py`:

```python
from transmitter.state import (PublishState, load_fallback_version, load_publish_state,
                               save_fallback_version, save_publish_state)
from transmitter.workspace import Workspace


def test_publish_state_round_trip(tmp_path):
    ws = Workspace(tmp_path)
    assert load_publish_state(ws) == PublishState()
    state = PublishState(epoch_id="e1", first=10, last=20, runs=[[10, 20]], notes={"s": "abc"})
    save_publish_state(ws, state)
    assert load_publish_state(ws) == state


def test_fallback_version_round_trip(tmp_path):
    ws = Workspace(tmp_path)
    assert load_fallback_version(ws) is None
    save_fallback_version(ws, "3fa9c1d2e0b1")
    assert load_fallback_version(ws) == "3fa9c1d2e0b1"
```

Append to `tests_transmitter/test_cli.py`:

```python
from transmitter.config import DEFAULT_CONFIG_TOML


def test_config_init_writes_once(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path))
    runner = CliRunner()
    first = runner.invoke(app, ["config", "init"])
    assert first.exit_code == 0
    assert (tmp_path / "config.toml").read_text() == DEFAULT_CONFIG_TOML
    second = runner.invoke(app, ["config", "init"])
    assert second.exit_code == 1


def test_config_init_stdout():
    result = CliRunner().invoke(app, ["config", "init", "--stdout"])
    assert result.exit_code == 0 and result.output == DEFAULT_CONFIG_TOML
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_config.py packages/transmitter/tests_transmitter/test_workspace.py packages/transmitter/tests_transmitter/test_state.py packages/transmitter/tests_transmitter/test_cli.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'transmitter.config'`.

- [ ] **Step 3: Implement**

`packages/transmitter/src/transmitter/config.py`:

```python
"""transmitter's config (`~/.transmitter/config.toml`). Strict, like llama's
and emcee's: a typo'd key is an error, not a silently ignored knob."""

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from transmitter.errors import ConfigError

DEFAULT_ROOT = Path.home() / ".transmitter"


def default_root() -> Path:
    root = os.environ.get("TRANSMITTER_ROOT")
    return Path(root) if root else DEFAULT_ROOT


class _StrictModel(BaseModel):
    """Unknown keys are an error. Set on a shared base because pydantic does
    not propagate model_config to nested models."""
    model_config = ConfigDict(extra="forbid")


class StationConfig(_StrictModel):
    root: Path | None = None                       # NFS path on hugo; needs `.station-root`
    quiet_minutes: float = Field(default=10.0, ge=0)


class PlannerConfig(_StrictModel):
    seed: int = 0
    # A fresh run (first start, or after an outage longer than the lead) begins
    # this far ahead of now: long enough to analyse, encode and upload the
    # first show's opening batch before it airs.
    start_delay_minutes: float = Field(default=10.0, gt=0)


class RenderConfig(_StrictModel):
    ffmpeg: str = "ffmpeg"
    lead_hours: float = Field(default=24.0, gt=0)
    low_water_hours: float = Field(default=20.0, gt=0)
    music_target_lufs: float = -16.0
    speech_target_lufs: float = -16.0
    clip_pause_seconds: float = Field(default=0.75, ge=0)
    show_gap_seconds: float = Field(default=2.0, ge=0)

    @model_validator(mode="after")
    def _low_water_below_lead(self):
        if self.low_water_hours >= self.lead_hours:
            raise ValueError("render.low_water_hours must be below render.lead_hours")
        return self


class PublishConfig(_StrictModel):
    account_id: str | None = None
    bucket: str | None = None
    endpoint_url: str | None = None
    batch_segments: int = Field(default=360, ge=1)
    # ~2x the expected daily count: 86400/10.24 = 8,438 segments, plus the
    # timeline/horizon/notes/page writes of each publish batch and prune's
    # horizon rewrites (at most one per prune_min_segments, ~141/day at 60)
    # ~= 8.9k/day.
    daily_put_budget: int = Field(default=17_500, ge=1)
    prune_margin_minutes: float = Field(default=10.0, ge=0)   # as built: ge=PRUNE_MARGIN_FLOOR_MINUTES (4), Task 12
    # prune (one horizon PUT + free deletes) only once this many are prunable
    prune_min_segments: int = Field(default=60, ge=1)
    guard_check_minutes: float = Field(default=15.0, ge=0)


class AntennaConfig(_StrictModel):
    dir: Path | None = None            # the repo's antenna/ (templates/show.html)
    site_url: str | None = None        # public base URL, for Open Graph links
    station_name: str = "llama radio"


class TransmitterConfig(_StrictModel):
    root: Path = Field(default_factory=default_root)
    station: StationConfig = Field(default_factory=StationConfig)
    planner: PlannerConfig = Field(default_factory=PlannerConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
    publish: PublishConfig = Field(default_factory=PublishConfig)
    antenna: AntennaConfig = Field(default_factory=AntennaConfig)


def load_config(path: Path | None = None) -> TransmitterConfig:
    path = path or default_root() / "config.toml"
    if not path.exists():
        return TransmitterConfig()
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid config at {path}: {exc}") from exc
    try:
        return TransmitterConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid config at {path}: {exc}") from exc


# Seeded by `transmitter config init`; kept equal to the defaults above by
# tests/test_config.py::test_template_parses_to_the_defaults.
DEFAULT_CONFIG_TOML = """\
# transmitter config - seeded by `transmitter config init`.
# A value here REPLACES its built-in default; unknown keys are errors.

# workspace (plan, caches, rendered audio); default ~/.transmitter or $TRANSMITTER_ROOT
# root = "/home/station/.transmitter"

[station]
# the delivered-packages folder (NFS on hugo); must contain a `.station-root`
# marker file, or `plan` refuses (a down NFS mount is an empty directory)
# root = "/nfs/media/station"
# a package must be untouched this long before it may air
quiet_minutes = 10.0

[planner]
# seed of the fixed shuffled order
seed = 0
# a fresh run (first start, or after an outage longer than the lead) begins
# this far ahead of now
start_delay_minutes = 10.0

[render]
ffmpeg = "ffmpeg"
# keep this much audio published ahead of now; render again below low water
lead_hours = 24.0
low_water_hours = 20.0
# per-show music loudness ceiling (tracks only) and per-clip speech target;
# gain = min(target - I, -1 dBTP - TP)
music_target_lufs = -16.0
speech_target_lufs = -16.0
# pause between a DJ clip and a track; gap between shows
clip_pause_seconds = 0.75
show_gap_seconds = 2.0

[publish]
# R2 endpoint is https://<account_id>.r2.cloudflarestorage.com unless
# endpoint_url is set. Keys come from the environment:
# R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY.
# account_id = "..."
# bucket = "llama-radio"
# endpoint_url = "https://..."
# segments per publish batch (state/horizon.json advances once per batch)
batch_segments = 360
# own-write cap: publishing stops (and alerts) past this many PUTs per UTC day
daily_put_budget = 17500
# delete segments that started more than this long ago
prune_margin_minutes = 10.0
# ...but only once this many are due (each prune rewrites state/horizon.json)
prune_min_segments = 60
# read state/guard.json at most this often
guard_check_minutes = 15.0

[antenna]
# the repo's antenna/ directory (the show-page template is templates/show.html)
# dir = "/home/station/llama/antenna"
# public base URL, for Open Graph links on show pages
# site_url = "https://radio.example.org"
station_name = "llama radio"
"""
```

`packages/transmitter/src/transmitter/workspace.py`:

```python
"""~/.transmitter layout, atomic writes, and the epoch (spec "transmitter --
state and commands"; "The core contract")."""

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from transmitter import grid
from transmitter.errors import ConfigError


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Unique temp file + rename: concurrent writers never interleave."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode())


def write_json(path: Path, obj: Any) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, sort_keys=True) + "\n")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


@dataclass(frozen=True)
class Workspace:
    root: Path

    @property
    def plan_path(self) -> Path:
        return self.root / "plan.jsonl"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @property
    def render_dir(self) -> Path:
        return self.root / "render"

    @property
    def shows_dir(self) -> Path:
        return self.render_dir / "shows"

    def seg_dir(self, epoch_id: str) -> Path:
        return self.render_dir / "seg" / epoch_id

    def fallback_dir(self, version: str) -> Path:
        return self.render_dir / "fallback" / version

    @property
    def epoch_path(self) -> Path:
        return self.root / "epoch.json"

    @property
    def publish_state_path(self) -> Path:
        return self.root / "publish.json"

    @property
    def puts_path(self) -> Path:
        return self.root / "puts.json"

    @property
    def guard_cache_path(self) -> Path:
        return self.root / "guard-cache.json"

    @property
    def fallback_path(self) -> Path:
        return self.root / "fallback.json"

    @property
    def lock_path(self) -> Path:
        return self.root / "publish.lock"


@dataclass(frozen=True)
class Epoch:
    epoch_id: str
    epoch_us: int

    @property
    def iso(self) -> str:
        return grid.us_to_iso(self.epoch_us)

    def start_us(self, n: int) -> int:
        return grid.segment_start_us(self.epoch_us, n)

    def index_at(self, t_us: int) -> int:
        return grid.segment_index_at(self.epoch_us, t_us)


_D_SECONDS = grid.D_US / 1_000_000


def load_epoch(ws: Workspace) -> Epoch | None:
    data = read_json(ws.epoch_path)
    if data is None:
        return None
    if data.get("d") != _D_SECONDS:
        raise ConfigError(f"{ws.epoch_path}: d={data.get('d')!r} is not {_D_SECONDS}; an epoch "
                          "change is a deliberate re-render-everything operation, not an edit")
    return Epoch(data["epoch_id"], grid.iso_to_us(data["epoch"]))


def load_or_create_epoch(ws: Workspace, now_us: int) -> Epoch:
    existing = load_epoch(ws)
    if existing is not None:
        return existing
    e_us = now_us - now_us % 1_000_000
    stamp = datetime.fromtimestamp(e_us // 1_000_000, tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    epoch = Epoch(f"e{stamp}", e_us)
    write_json(ws.epoch_path, {"epoch_id": epoch.epoch_id, "epoch": epoch.iso, "d": _D_SECONDS})
    return epoch
```

`packages/transmitter/src/transmitter/state.py`:

```python
"""Local publish state (`publish.json`): the authoritative mirror of what is in
R2 -- horizon first/last, every run of segment keys uploaded (or attempted:
a batch records its range before its first PUT) and not yet pruned (prune
deletes by these computed ranges; no List calls), and the digest of each
show's uploaded notes/page. Plus the current fallback version."""

from dataclasses import asdict, dataclass, field

from transmitter.workspace import Workspace, read_json, write_json


@dataclass
class PublishState:
    epoch_id: str | None = None
    first: int | None = None
    last: int | None = None
    runs: list[list[int]] = field(default_factory=list)
    notes: dict[str, str] = field(default_factory=dict)


def load_publish_state(ws: Workspace) -> PublishState:
    data = read_json(ws.publish_state_path)
    if data is None:
        return PublishState()
    return PublishState(epoch_id=data.get("epoch_id"), first=data.get("first"),
                        last=data.get("last"), runs=[list(r) for r in data.get("runs", [])],
                        notes=dict(data.get("notes", {})))


def save_publish_state(ws: Workspace, state: PublishState) -> None:
    write_json(ws.publish_state_path, asdict(state))


def load_fallback_version(ws: Workspace) -> str | None:
    data = read_json(ws.fallback_path)
    return data.get("version") if data else None


def save_fallback_version(ws: Workspace, version: str) -> None:
    write_json(ws.fallback_path, {"version": version})
```

In `cli.py`, add after the `app` definition (add `from pathlib import Path` and the config import at the top):

```python
from pathlib import Path

from transmitter.config import DEFAULT_CONFIG_TOML, default_root

config_app = typer.Typer(help="Config file utilities", pretty_exceptions_enable=False)
app.add_typer(config_app, name="config")


@config_app.command("init")
def config_init(
    stdout: bool = typer.Option(False, "--stdout", help="Print the default config instead of writing it"),
    config_path: Path = typer.Option(None, "--config", help="Target file (default: $TRANSMITTER_ROOT "
                                                            "or ~/.transmitter, then /config.toml)"),
):
    """Seed a config file with the baked-in defaults, commented."""
    if stdout:
        typer.echo(DEFAULT_CONFIG_TOML, nl=False)
        return
    target = config_path or default_root() / "config.toml"
    if target.exists():
        typer.echo(f"{target} already exists - not overwriting", err=True)
        raise typer.Exit(1)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(DEFAULT_CONFIG_TOML)
    typer.echo(f"wrote {target}")
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): strict config, workspace, epoch, local publish state, config init"
```

---

### Task 4: Frame layout and FrameStore (the segmenter)

**Model hint:** sonnet

**Files:**
- Create: `packages/transmitter/src/transmitter/layout.py`
- Create: `packages/transmitter/tests_transmitter/test_layout.py`
- Modify: `packages/transmitter/tests_transmitter/helpers.py` (fake frames)

**Interfaces:**
- Consumes: `adts.build_frame/frame_offsets`, `segment.assemble`, `grid.SEGMENT_FRAMES`, `errors.LayoutError`.
- Produces:
  - `PlanRow(seq: int, slug: str, dir: str, key: str, start_frame: int, frames: int, run_start: bool = False, cut_frame: int | None = None)` with `.end_frame` (cut-aware, exclusive), `.to_json() -> dict`, `PlanRow.from_json(d)`.
  - `Piece(key: str | None, offset: int, count: int)` (`key=None` = silence).
  - `validate_rows(rows)`; `pieces(rows, start, stop) -> list[Piece]`; `segment_pieces(rows, n) -> list[Piece]`; `rows_overlapping(rows, start, stop) -> list[PlanRow]`.
  - `FrameStore(shows_dir, silent_frame, *, keep=2)` with `.path(key) -> Path`, `.has(key) -> bool`, `.frame_count(key) -> int`, `.frames(key, offset, count) -> list[bytes]`, `.build_segment(n, rows) -> bytes`.
  - helpers: `fake_frame(key, i) -> bytes`, `write_fake_show(path, key, n_frames)`, `payloads(frames) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests_transmitter/helpers.py`:

```python
from pathlib import Path

from transmitter import adts


def fake_frame(key: str, i: int) -> bytes:
    """A valid ADTS frame whose payload names its show and index."""
    return adts.build_frame(f"{key}:{i}".encode())


def write_fake_show(path: Path, key: str, n_frames: int) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(fake_frame(key, i) for i in range(n_frames)))


def payloads(frames: list[bytes]) -> list[str]:
    return [f[7:].decode() for f in frames]
```

`tests_transmitter/test_layout.py`:

```python
import pytest

from tests_transmitter.helpers import fake_frame, payloads, write_fake_show
from transmitter import grid, segment
from transmitter.errors import LayoutError
from transmitter.layout import FrameStore, Piece, PlanRow, pieces, rows_overlapping, segment_pieces, validate_rows

F = grid.SEGMENT_FRAMES


def row(seq, key, start, frames, **kw):
    return PlanRow(seq=seq, slug=f"s{seq}", dir=f"s{seq}", key=key, start_frame=start, frames=frames, **kw)


def test_pieces_show_gap_show():
    rows = [row(0, "a", 0, 100), row(1, "b", 187, 50)]
    assert pieces(rows, 90, 200) == [Piece("a", 90, 10), Piece(None, 0, 87), Piece("b", 0, 13)]


def test_pieces_before_the_first_row_and_after_the_last_are_silence():
    rows = [row(0, "a", 10, 5)]
    assert pieces(rows, 0, 20) == [Piece(None, 0, 10), Piece("a", 0, 5), Piece(None, 0, 5)]


def test_pieces_respect_a_cut_row():
    rows = [row(0, "a", 0, 1000, cut_frame=441), row(1, "b", 882, 441, run_start=True)]
    assert rows[0].end_frame == 441
    assert segment_pieces(rows, 1) == [Piece(None, 0, 441)]
    assert segment_pieces(rows, 2) == [Piece("b", 0, 441)]


def test_validate_rows_rejects_overlap_and_unaligned_run_start():
    with pytest.raises(LayoutError, match="overlap"):
        validate_rows([row(0, "a", 0, 100), row(1, "b", 50, 10)])
    with pytest.raises(LayoutError, match="segment-aligned"):
        validate_rows([row(0, "a", 5, 100, run_start=True)])


def test_rows_overlapping():
    rows = [row(0, "a", 0, 100), row(1, "b", 187, 50)]
    assert rows_overlapping(rows, 100, 187) == []
    assert rows_overlapping(rows, 99, 188) == rows


def test_plan_row_json_round_trip():
    r = row(3, "k", 882, 1234, run_start=True, cut_frame=1000)
    assert PlanRow.from_json(r.to_json()) == r


def test_build_segment_spans_show_end_gap_and_next_show(tmp_path):
    write_fake_show(tmp_path / "a.aac", "a", 600)
    write_fake_show(tmp_path / "b.aac", "b", 900)
    rows = [row(0, "a", 0, 600), row(1, "b", 687, 900)]
    store = FrameStore(tmp_path, fake_frame("silence", 0))
    ts, frames = segment.parse(store.build_segment(1, rows))
    assert ts == grid.segment_timestamp(1)
    got = payloads(frames)
    assert got[:159] == [f"a:{i}" for i in range(441, 600)]
    assert got[159:246] == ["silence:0"] * 87
    assert got[246:] == [f"b:{i}" for i in range(0, 195)]


def test_build_segment_refuses_past_the_plan(tmp_path):
    write_fake_show(tmp_path / "a.aac", "a", 500)
    store = FrameStore(tmp_path, fake_frame("silence", 0))
    with pytest.raises(LayoutError, match="past the end of the plan"):
        store.build_segment(1, [row(0, "a", 0, 500)])


def test_build_segment_checks_the_encode_matches_the_plan(tmp_path):
    write_fake_show(tmp_path / "a.aac", "a", 400)
    store = FrameStore(tmp_path, fake_frame("silence", 0))
    with pytest.raises(LayoutError, match="400 frames"):
        store.build_segment(0, [row(0, "a", 0, 900)])


def test_missing_encode_is_a_layout_error(tmp_path):
    store = FrameStore(tmp_path, fake_frame("silence", 0))
    with pytest.raises(LayoutError, match="missing"):
        store.build_segment(0, [row(0, "zz", 0, 900)])
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_layout.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'transmitter.layout'`.

- [ ] **Step 3: Implement `layout.py`**

```python
"""The station stream's frame layout (spec "Per-show encode, frame-count
segmentation"). Plan rows place each show's encoded AAC frames on one
continuous frame line whose frame 0 is at the epoch; frames between rows are
pre-encoded silence; segment N is frames [441N, 441N+441). Grid alignment is by
counting, never by ffmpeg cut points.

Container seam: `FrameStore.build_segment` is the only place frames become a
segment (via `segment.assemble`). Appendix A of the phase-1 plan swaps that
call for an fMP4 fragment writer if the container spike fails.
"""

from collections import OrderedDict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from transmitter import adts, segment
from transmitter.errors import LayoutError
from transmitter.grid import SEGMENT_FRAMES


@dataclass(frozen=True)
class PlanRow:
    seq: int
    slug: str
    dir: str            # package directory name under the station root
    key: str            # file-set key of the package when planned
    start_frame: int
    frames: int         # the encoder's full output for this show
    run_start: bool = False        # first row of a contiguous run (start-up or recovery)
    cut_frame: int | None = None   # set when an outage cut the show (recovery)

    @property
    def end_frame(self) -> int:
        return self.cut_frame if self.cut_frame is not None else self.start_frame + self.frames

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict) -> "PlanRow":
        return cls(**data)


@dataclass(frozen=True)
class Piece:
    key: str | None   # None = pre-encoded silence
    offset: int       # first frame within the show's encode (0 for silence)
    count: int


def validate_rows(rows: Sequence[PlanRow]) -> None:
    prev = None
    for r in rows:
        if r.frames <= 0:
            raise LayoutError(f"plan row {r.seq} ({r.slug}) has no frames")
        if r.cut_frame is not None and not r.start_frame < r.cut_frame <= r.start_frame + r.frames:
            raise LayoutError(f"plan row {r.seq} ({r.slug}) has a cut outside the show")
        if r.run_start and r.start_frame % SEGMENT_FRAMES:
            raise LayoutError(f"plan row {r.seq} ({r.slug}) starts a run but is not segment-aligned")
        if prev is not None and r.start_frame < prev.end_frame:
            raise LayoutError(f"plan rows {prev.seq} and {r.seq} overlap")
        prev = r


def pieces(rows: Sequence[PlanRow], start: int, stop: int) -> list[Piece]:
    """Frames [start, stop) as runs of show frames and silence."""
    if stop < start:
        raise ValueError("stop < start")
    out: list[Piece] = []
    pos = start
    for r in rows:
        if pos >= stop:
            break
        if r.end_frame <= pos:
            continue
        if r.start_frame >= stop:
            break
        if r.start_frame > pos:
            out.append(Piece(None, 0, r.start_frame - pos))
            pos = r.start_frame
        take = min(stop, r.end_frame)
        out.append(Piece(r.key, pos - r.start_frame, take - pos))
        pos = take
    if pos < stop:
        out.append(Piece(None, 0, stop - pos))
    return out


def segment_pieces(rows: Sequence[PlanRow], n: int) -> list[Piece]:
    return pieces(rows, n * SEGMENT_FRAMES, (n + 1) * SEGMENT_FRAMES)


def rows_overlapping(rows: Sequence[PlanRow], start: int, stop: int) -> list[PlanRow]:
    return [r for r in rows if r.start_frame < stop and r.end_frame > start]


class FrameStore:
    """Slices frames out of each show's encode (`render/shows/<key>.aac`).
    Keeps the `keep` most recently used encodes in memory (a 3 h show is
    ~170 MB of ADTS)."""

    def __init__(self, shows_dir: Path, silent_frame: bytes, *, keep: int = 2):
        self.shows_dir = Path(shows_dir)
        self.silent_frame = silent_frame
        self._keep = keep
        self._cache: OrderedDict[str, tuple[bytes, list[int]]] = OrderedDict()

    def path(self, key: str) -> Path:
        return self.shows_dir / f"{key}.aac"

    def has(self, key: str) -> bool:
        return self.path(key).exists()

    def _load(self, key: str) -> tuple[bytes, list[int]]:
        hit = self._cache.get(key)
        if hit is not None:
            self._cache.move_to_end(key)
            return hit
        try:
            data = self.path(key).read_bytes()
        except FileNotFoundError as exc:
            raise LayoutError(f"show encode {key} is missing") from exc
        entry = (data, adts.frame_offsets(data))
        self._cache[key] = entry
        while len(self._cache) > self._keep:
            self._cache.popitem(last=False)
        return entry

    def frame_count(self, key: str) -> int:
        return len(self._load(key)[1]) - 1

    def frames(self, key: str, offset: int, count: int) -> list[bytes]:
        data, offsets = self._load(key)
        if offset < 0 or offset + count > len(offsets) - 1:
            raise LayoutError(f"show encode {key} has {len(offsets) - 1} frames; "
                              f"asked for [{offset}, {offset + count})")
        return [data[offsets[i]:offsets[i + 1]] for i in range(offset, offset + count)]

    def build_segment(self, n: int, rows: Sequence[PlanRow]) -> bytes:
        if not rows or (n + 1) * SEGMENT_FRAMES > rows[-1].end_frame:
            raise LayoutError(f"segment {n} extends past the end of the plan")
        for r in rows_overlapping(rows, n * SEGMENT_FRAMES, (n + 1) * SEGMENT_FRAMES):
            have = self.frame_count(r.key)
            if have != r.frames:
                raise LayoutError(f"show encode {r.key} ({r.slug}) has {have} frames; "
                                  f"the plan says {r.frames}")
        parts: list[bytes] = []
        for p in segment_pieces(rows, n):
            if p.key is None:
                parts.extend([self.silent_frame] * p.count)
            else:
                parts.extend(self.frames(p.key, p.offset, p.count))
        return segment.assemble(n, parts)
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_layout.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): frame layout, plan rows and the frame-count segmenter"
```

---

### Task 5: Station root guard and eligibility

**Model hint:** sonnet

**Files:**
- Create: `packages/transmitter/src/transmitter/station.py`
- Create: `packages/transmitter/tests_transmitter/test_station.py`
- Modify: `packages/transmitter/tests_transmitter/helpers.py` (package fixture)

**Interfaces:**
- Consumes: `errors.StationRootError`.
- Produces:
  - `MARKER = ".station-root"`; `Entry(path: str, kind: "clip"|"track", title: str)`; `Show(slug, dir: Path, entries: tuple[Entry, ...], key: str, meta: dict)` where `meta` has `artist, date, venue, city, profile, url, lineage`; `Ineligible(slug, reasons: tuple[str, ...])`.
  - `require_root(root) -> Path`; `read_m3u(path) -> list[str]`; `file_set_key(pkg_dir, rels) -> str` (20 hex chars over paths + sizes + mtimes); `evaluate(pkg_dir, *, now_s, quiet_s) -> Show | Ineligible` (ignores `dj-audio/*.tmp`, emcee's temp files; an `OSError` while stat-ing or hashing — a file vanished mid-scan — is `Ineligible` with a `changing: …` reason, never a crash); `scan(root, *, now_s, quiet_s) -> tuple[list[Show], list[Ineligible]]`.
  - helpers: `make_root(tmp_path) -> Path`, `build_package(root, slug="band-2005-11-01", *, tracks=3, voiced=True, profile="indie", age_s=3600.0, audio=None) -> Path`, `set_age(pkg, age_s)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests_transmitter/helpers.py`:

```python
import json
import os
import time
from typing import Callable


def make_root(tmp_path: Path) -> Path:
    root = tmp_path / "station"
    root.mkdir(parents=True)
    (root / ".station-root").write_text("")
    return root


def set_age(pkg: Path, age_s: float) -> None:
    t = time.time() - age_s
    for p in [pkg, *pkg.rglob("*")]:
        os.utime(p, (t, t))


def build_package(root: Path, slug: str = "band-2005-11-01", *, tracks: int = 3,
                  voiced: bool = True, profile: str | None = "indie", age_s: float = 3600.0,
                  audio: Callable[[Path, int], None] | None = None) -> Path:
    """A v3 package shaped like a real delivered one (cracker-2005-11-01):
    broadcast.m3u = dj-audio/set1-intro.mp3, audio/NN - Song N.mp3 ...,
    dj-audio/99-outro.mp3. `audio(path, index)` writes each audio file
    (default: placeholder bytes -- eligibility never decodes); index 0 is the
    intro, 99 the outro. Every file's mtime is set `age_s` in the past."""
    pkg = root / slug
    (pkg / "audio").mkdir(parents=True)
    (pkg / "dj-audio").mkdir()
    write = audio or (lambda path, i: path.write_bytes(b"ID3fake" + bytes([i])))
    rows = [{"index": i, "set": "1", "title": f"Song {i}", "filename": f"{i:02d} - Song {i}.mp3",
             "duration_sec": 60.0, "segue": False} for i in range(1, tracks + 1)]
    manifest = {
        "schema_version": 3,
        "show": {"artist": "Band", "date": "2005-11-01", "venue": "Club", "city": "Lincoln, NE"},
        "source": {"performance_id": "Band/2005-11-01", "identifier": "band2005",
                   "url": "https://archive.org/details/band2005", "lineage": "AUD > CDR",
                   "profile": profile},
        "tracks": rows, "set_breaks": [],
        "briefing": {"file": "briefing.md", "json": "briefing.json", "narration": "full", "vetted": True},
        "dj_notes": None, "dj_audio": None,
    }
    m3u = ["#EXTM3U"]
    if voiced:
        manifest["dj_notes"] = {"set_intros": {"1": "Hello."}, "outro": "Bye."}
        manifest["dj_audio"] = {"set_intros": {"1": "dj-audio/set1-intro.mp3"},
                                "outro": "dj-audio/99-outro.mp3", "presenter": None}
        (pkg / "dj-notes.md").write_text("# notes\n")
        write(pkg / "dj-audio" / "set1-intro.mp3", 0)
        m3u.append("dj-audio/set1-intro.mp3")
    for i, r in enumerate(rows, 1):
        write(pkg / "audio" / r["filename"], i)
        m3u.append(f"audio/{r['filename']}")
    if voiced:
        write(pkg / "dj-audio" / "99-outro.mp3", 99)
        m3u.append("dj-audio/99-outro.mp3")
        (pkg / "broadcast.m3u").write_text("\n".join(m3u) + "\n")
    (pkg / "briefing.md").write_text("A fine show.\n\nSecond paragraph.\n")
    (pkg / "manifest.json").write_text(json.dumps(manifest, indent=2))
    set_age(pkg, age_s)
    return pkg
```

`tests_transmitter/test_station.py`:

```python
import json
import time
from pathlib import Path

import pytest

from tests_transmitter.helpers import build_package, make_root, set_age
from transmitter import station
from transmitter.errors import StationRootError
from transmitter.station import Entry, Ineligible, Show


def _eval(pkg, quiet_s=600.0):
    return station.evaluate(pkg, now_s=time.time(), quiet_s=quiet_s)


def test_ready_package_is_eligible(tmp_path):
    pkg = build_package(make_root(tmp_path))
    show = _eval(pkg)
    assert isinstance(show, Show)
    assert show.slug == "band-2005-11-01"
    assert show.entries[0] == Entry("dj-audio/set1-intro.mp3", "clip", "DJ intro (set 1)")
    assert show.entries[1] == Entry("audio/01 - Song 1.mp3", "track", "Song 1")
    assert show.entries[-1] == Entry("dj-audio/99-outro.mp3", "clip", "DJ outro")
    assert show.meta["artist"] == "Band" and show.meta["profile"] == "indie"
    assert len(show.key) == 20


def _break(pkg, how):
    m = json.loads((pkg / "manifest.json").read_text())
    if how == "unvoiced":
        m["dj_audio"] = None
    elif how == "no-notes-file":
        (pkg / "dj-notes.md").unlink()
    elif how == "clip-missing":
        (pkg / "dj-audio" / "99-outro.mp3").unlink()
    elif how == "no-m3u":
        (pkg / "broadcast.m3u").unlink()
    elif how == "track-missing":
        (pkg / "audio" / "02 - Song 2.mp3").unlink()
    elif how == "m3u-entry-missing":
        (pkg / "broadcast.m3u").write_text("audio/01 - Song 1.mp3\naudio/nope.mp3\n")
    elif how == "m3u-escapes":
        (pkg / "broadcast.m3u").write_text("../other/audio/01.mp3\n")
    elif how == "m3u-absolute":
        (pkg / "broadcast.m3u").write_text("/etc/passwd\n")
    elif how == "v2":
        m["schema_version"] = 2
    (pkg / "manifest.json").write_text(json.dumps(m))
    set_age(pkg, 3600)


@pytest.mark.parametrize("how,reason", [
    ("unvoiced", "no DJ audio"),
    ("no-notes-file", "no DJ script"),
    ("clip-missing", "DJ clip(s) missing"),
    ("no-m3u", "no broadcast.m3u"),
    ("track-missing", "track file(s) missing"),
    ("m3u-entry-missing", "entry missing: audio/nope.mp3"),
    ("m3u-escapes", "escapes the package"),
    ("m3u-absolute", "escapes the package"),
    ("v2", "unsupported manifest"),
])
def test_each_leg_makes_a_package_ineligible(tmp_path, how, reason):
    pkg = build_package(make_root(tmp_path))
    _break(pkg, how)
    result = _eval(pkg)
    assert isinstance(result, Ineligible)
    assert any(reason in r for r in result.reasons), result.reasons


def test_quiet_period(tmp_path):
    pkg = build_package(make_root(tmp_path), age_s=60)
    assert isinstance(_eval(pkg, quiet_s=600), Ineligible)
    assert isinstance(_eval(pkg, quiet_s=30), Show)


def test_key_tracks_the_file_set(tmp_path):
    pkg = build_package(make_root(tmp_path))
    k1 = _eval(pkg).key
    assert _eval(pkg).key == k1
    f = pkg / "audio" / "01 - Song 1.mp3"
    f.write_bytes(f.read_bytes() + b"x")
    set_age(pkg, 3600)
    assert _eval(pkg).key != k1


def test_emcee_temp_files_do_not_hold_the_quiet_period(tmp_path):
    pkg = build_package(make_root(tmp_path))
    (pkg / "dj-audio" / "99-outro.mp3.k2j3.tmp").write_bytes(b"partial")     # emcee's mkstemp name; mtime: now
    assert isinstance(_eval(pkg), Show)


def test_a_file_vanishing_mid_scan_is_changing_not_a_crash(tmp_path, monkeypatch):
    pkg = build_package(make_root(tmp_path))
    dj_dir = pkg / "dj-audio"
    real_iterdir = Path.iterdir

    def iterdir(self):                 # listed, then gone before evaluate stats it
        yield from real_iterdir(self)
        if self == dj_dir:
            yield dj_dir / "set2-intro.mp3"

    monkeypatch.setattr(Path, "iterdir", iterdir)
    result = _eval(pkg)
    assert isinstance(result, Ineligible)
    assert result.reasons[0].startswith("changing")


def test_scan_skips_dot_dirs_and_non_packages(tmp_path):
    root = make_root(tmp_path)
    build_package(root, "a-show")
    build_package(root, ".swap-a-show")
    (root / "not-a-package").mkdir()
    (root / "._junk").write_text("")
    shows, skipped = station.scan(root, now_s=time.time(), quiet_s=600)
    assert [s.slug for s in shows] == ["a-show"] and skipped == []


def test_empty_root_without_marker_is_refused(tmp_path):
    root = tmp_path / "nfs"
    root.mkdir()                      # what a down NFS mount looks like on hugo
    with pytest.raises(StationRootError, match="marker"):
        station.scan(root, now_s=time.time(), quiet_s=0)


def test_missing_or_unset_root_is_refused(tmp_path):
    with pytest.raises(StationRootError, match="missing"):
        station.require_root(tmp_path / "gone")
    with pytest.raises(StationRootError, match=r"\[station\] root"):
        station.require_root(None)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_station.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'transmitter.station'`.

- [ ] **Step 3: Implement `station.py`**

```python
"""The station root and package eligibility (spec "Station-root guard",
"Eligibility").

A package is eligible iff it passes emcee's four readiness legs, reimplemented
on files alone (transmitter never imports emcee) -- manifest v3+ with non-null
dj_notes and dj-notes.md present; non-null dj_audio with every named clip on
disk; broadcast.m3u present; every manifest track's audio on disk -- plus every
broadcast.m3u entry exists inside the package, and the newest mtime among
manifest.json, broadcast.m3u and dj-audio/* (bar emcee's *.tmp files) is older
than the quiet period. The playable unit is broadcast.m3u, in order. A file
that vanishes between listing and stat (emcee or llama mid-write) makes the
package "changing" -- ineligible this scan, never an exception.
"""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal

from transmitter.errors import StationRootError

MARKER = ".station-root"


@dataclass(frozen=True)
class Entry:
    path: str
    kind: Literal["clip", "track"]
    title: str


@dataclass(frozen=True)
class Show:
    slug: str
    dir: Path
    entries: tuple[Entry, ...]
    key: str
    meta: dict = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class Ineligible:
    slug: str
    reasons: tuple[str, ...]


def require_root(root: Path | None) -> Path:
    if root is None:
        raise StationRootError("set [station] root in transmitter's config.toml")
    root = Path(root)
    if not root.is_dir():
        raise StationRootError(f"station root {root} is missing (is the NFS share mounted?)")
    if not (root / MARKER).exists():
        raise StationRootError(
            f"station root {root} has no {MARKER} marker -- refusing to treat it as an empty "
            "library (on hugo a down NFS mount is an ordinary empty directory)")
    return root


def read_m3u(path: Path) -> list[str]:
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def _inside(pkg_dir: Path, rel: str) -> bool:
    p = Path(rel)
    if p.is_absolute():
        return False
    try:
        (pkg_dir / p).resolve().relative_to(pkg_dir.resolve())
    except ValueError:
        return False
    return True


def file_set_key(pkg_dir: Path, rels: Iterable[str]) -> str:
    """The cache/plan key of a show: its broadcast.m3u paths + sizes + mtimes."""
    h = hashlib.sha256()
    for rel in rels:
        st = (pkg_dir / rel).stat()
        h.update(json.dumps([rel, st.st_size, st.st_mtime_ns]).encode() + b"\n")
    return h.hexdigest()[:20]


def _clips(dj_audio: dict) -> dict[str, str]:
    """clip path -> on-air title."""
    out: dict[str, str] = {}
    intros = dj_audio.get("set_intros") or {}
    if isinstance(intros, dict):
        for set_key, path in intros.items():
            if isinstance(path, str) and path:
                out[path] = f"DJ intro (set {set_key})"
    outro = dj_audio.get("outro")
    if isinstance(outro, str) and outro:
        out[outro] = "DJ outro"
    return out


def evaluate(pkg_dir: Path, *, now_s: float, quiet_s: float) -> Show | Ineligible:
    pkg_dir = Path(pkg_dir)
    slug = pkg_dir.name
    try:
        manifest = json.loads((pkg_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return Ineligible(slug, (f"unreadable manifest.json: {exc}",))
    if not isinstance(manifest, dict):
        return Ineligible(slug, ("manifest.json is not an object",))
    version = manifest.get("schema_version")
    if not isinstance(version, int) or version < 3:
        return Ineligible(slug, (f"unsupported manifest (schema_version {version!r}; need >= 3)",))

    reasons: list[str] = []
    if manifest.get("dj_notes") is None or not (pkg_dir / "dj-notes.md").exists():
        reasons.append("no DJ script (dj_notes block + dj-notes.md required)")

    clips: dict[str, str] = {}
    dj_audio = manifest.get("dj_audio")
    if not isinstance(dj_audio, dict):
        reasons.append("no DJ audio (unvoiced)")
    else:
        clips = _clips(dj_audio)
        missing = sorted(c for c in clips if not (pkg_dir / c).exists())
        if missing:
            reasons.append(f"{len(missing)} DJ clip(s) missing: {', '.join(missing)}")

    tracks = manifest.get("tracks") or []
    titles: dict[str, str] = {}
    missing_tracks: list[str] = []
    for t in tracks:
        fn = t.get("filename") if isinstance(t, dict) else None
        if not isinstance(fn, str) or not fn:
            reasons.append("manifest track without a filename")
            continue
        titles[f"audio/{fn}"] = t.get("title") or fn
        if not (pkg_dir / "audio" / fn).exists():
            missing_tracks.append(fn)
    if missing_tracks:
        reasons.append(f"{len(missing_tracks)} of {len(tracks)} track file(s) missing: "
                       + ", ".join(sorted(missing_tracks)))

    m3u = pkg_dir / "broadcast.m3u"
    rels: list[str] = []
    if not m3u.exists():
        reasons.append("no broadcast.m3u")
    else:
        rels = read_m3u(m3u)
        if not rels:
            reasons.append("broadcast.m3u lists nothing")
        for rel in rels:
            if not _inside(pkg_dir, rel):
                reasons.append(f"broadcast.m3u entry escapes the package: {rel}")
            elif not (pkg_dir / rel).is_file():
                reasons.append(f"broadcast.m3u entry missing: {rel}")

    watched = [p for p in (pkg_dir / "manifest.json", m3u) if p.exists()]
    dj_dir = pkg_dir / "dj-audio"
    try:
        if dj_dir.is_dir():
            watched += [p for p in dj_dir.iterdir() if not p.name.endswith(".tmp")]
        newest = max((p.stat().st_mtime for p in watched), default=0.0)
    except OSError as exc:
        return Ineligible(slug, (f"changing: {exc}",))
    if now_s - newest < quiet_s:
        reasons.append(f"changed {now_s - newest:.0f}s ago (quiet period {quiet_s:.0f}s)")

    if reasons:
        return Ineligible(slug, tuple(reasons))
    try:
        key = file_set_key(pkg_dir, rels)
    except OSError as exc:
        return Ineligible(slug, (f"changing: {exc}",))
    entries = tuple(
        Entry(rel, "clip", clips[rel]) if rel in clips
        else Entry(rel, "track", titles.get(rel, Path(rel).stem))
        for rel in rels
    )
    show_meta = manifest.get("show") or {}
    source = manifest.get("source") or {}
    meta = {k: show_meta.get(k) for k in ("artist", "date", "venue", "city")}
    meta.update(profile=source.get("profile"), url=source.get("url"), lineage=source.get("lineage"))
    return Show(slug, pkg_dir, entries, key, meta)


def scan(root: Path | None, *, now_s: float, quiet_s: float) -> tuple[list[Show], list[Ineligible]]:
    """Every non-dot subdirectory holding a manifest.json is a package (dot
    entries are llama's replace-swap siblings and AppleDouble files)."""
    root = require_root(root)
    shows: list[Show] = []
    skipped: list[Ineligible] = []
    for entry in sorted(root.iterdir()):
        if entry.name.startswith(".") or not entry.is_dir():
            continue
        if not (entry / "manifest.json").exists():
            continue
        result = evaluate(entry, now_s=now_s, quiet_s=quiet_s)
        (shows if isinstance(result, Show) else skipped).append(result)
    return shows, skipped
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_station.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): station-root guard and package eligibility"
```

---

### Task 6: Trivial planner

**Model hint:** opus

**Files:**
- Create: `packages/transmitter/src/transmitter/planner.py`
- Create: `packages/transmitter/tests_transmitter/test_planner.py`

**Interfaces:**
- Consumes: `layout.PlanRow`, `layout.validate_rows`, `station.Show`, `workspace.atomic_write_text`, `errors.PlanError/TransmitterError`, `grid.SEGMENT_FRAMES`.
- Produces:
  - `shuffle_rank(seed, slug) -> str`.
  - `choose_next(eligible, last_seq: Mapping[str, int], seed, previous: str | None) -> Show` — least-recently planned first (never planned before all), ties by the seeded rank; never the same show twice in a row when an alternative exists.
  - `extend(rows, eligible, *, frames_of: Callable[[Show], int], seed, gap_frames, until_frame, start_frame, run_start, max_new=None, on_skip=lambda show, exc: None) -> list[PlanRow]` — returns `rows` plus appended rows; the first appended row starts at `start_frame` (flagged `run_start` if asked), each later one at `prev.end_frame + gap_frames`; stops once the last row ends at/after `until_frame` or after `max_new` rows; a show whose `frames_of` raises `TransmitterError` is skipped (reported through `on_skip`).
  - `next_start(rows, gap_frames) -> int`; `replan_from(rows, index) -> tuple[list[PlanRow], int, bool]` (`(kept, start_frame, run_start)`); `cut_for_recovery(rows, published_last) -> list[PlanRow]`; `current_run_start(rows) -> int | None` (segment index); `publish_next(rows, last) -> int | None`.
  - `read_plan(path) -> list[PlanRow]`; `write_plan(path, rows)`.

- [ ] **Step 1: Write the failing tests**

`tests_transmitter/test_planner.py`:

```python
from pathlib import Path

import pytest

from transmitter import planner
from transmitter.errors import PlanError, RenderError
from transmitter.grid import SEGMENT_FRAMES as F
from transmitter.layout import PlanRow
from transmitter.station import Show


def show(slug):
    return Show(slug, Path("/station") / slug, (), f"key-{slug}", {})


SHOWS = [show(s) for s in ("alpha", "bravo", "charlie", "delta")]


def ext(rows, eligible=SHOWS, **kw):
    args = dict(frames_of=lambda s: 1000, seed=7, gap_frames=87, until_frame=10_000,
                start_frame=0, run_start=True)
    args.update(kw)
    return planner.extend(rows, eligible, **args)


def test_shuffle_rank_is_stable_and_seeded():
    assert planner.shuffle_rank(7, "alpha") == planner.shuffle_rank(7, "alpha")
    assert planner.shuffle_rank(7, "alpha") != planner.shuffle_rank(8, "alpha")


def test_order_is_the_seeded_shuffle_and_independent_of_the_set():
    order = [r.slug for r in ext([], until_frame=4 * 1087 - 87)]       # exactly four 1000-frame shows
    expected = sorted(["alpha", "bravo", "charlie", "delta"], key=lambda s: planner.shuffle_rank(7, s))
    assert order == expected
    # adding a package does not reorder the others
    more = [r.slug for r in ext([], SHOWS + [show("echo")], until_frame=5 * 1087 - 87)]
    assert [s for s in more if s != "echo"] == expected


def test_rows_are_back_to_back_with_the_gap_and_cover_until():
    rows = ext([], until_frame=5_000)
    assert rows[0].start_frame == 0 and rows[0].run_start
    for a, b in zip(rows, rows[1:]):
        assert b.start_frame == a.end_frame + 87 and not b.run_start
    assert rows[-1].end_frame >= 5_000 and rows[-2].end_frame < 5_000
    assert [r.seq for r in rows] == list(range(len(rows)))


def test_least_recently_planned_first_so_a_new_show_airs_once_then_falls_in_line():
    rows = ext([], until_frame=8 * 1087 - 87)            # exactly two cycles of four
    rows = ext(rows, SHOWS + [show("echo")], until_frame=rows[-1].end_frame + 3 * 1087,
               start_frame=planner.next_start(rows, 87), run_start=False)
    tail = [r.slug for r in rows[8:]]
    assert tail[0] == "echo" and tail.count("echo") == 1


def test_no_immediate_repeat_unless_alone():
    rows = ext([], [show("solo")], until_frame=3_000)
    assert [r.slug for r in rows] == ["solo", "solo", "solo"]
    two = ext([], SHOWS[:2], until_frame=6_000)
    assert all(a.slug != b.slug for a, b in zip(two, two[1:]))


def test_max_new_limits_growth():
    assert len(ext([], until_frame=100_000, max_new=1)) == 1


def test_a_show_that_cannot_be_measured_is_skipped():
    skipped = []

    def frames_of(s):
        if s.slug == "bravo":
            raise RenderError("bad mp3")
        return 1000

    rows = ext([], frames_of=frames_of, until_frame=6_000, on_skip=lambda s, e: skipped.append(s.slug))
    assert "bravo" not in {r.slug for r in rows} and skipped == ["bravo"]


def test_nothing_eligible_is_a_plan_error_only_when_planning_is_needed():
    with pytest.raises(PlanError):
        ext([], [])
    covered = ext([], until_frame=500)
    assert ext(covered, [], until_frame=500, start_frame=planner.next_start(covered, 87),
               run_start=False) == covered


def test_replan_from_keeps_the_boundary():
    rows = ext([], until_frame=5_000)
    kept, start, run_start = planner.replan_from(rows, 2)
    assert kept == rows[:2] and start == rows[2].start_frame and run_start is False
    assert planner.replan_from(rows, 0)[2] is True


def _rows_at(start_n):
    return ext([], start_frame=start_n * F, until_frame=start_n * F + 5_000)


def test_cut_for_recovery_cuts_the_spanning_show_and_drops_the_rest():
    rows = _rows_at(10)                               # 1000-frame shows from frame 4410
    last = 12                                         # published through segment 12
    kept = planner.cut_for_recovery(rows, last)
    boundary = 13 * F                                 # 5733, inside row 1 (5497..6497)
    assert kept[0] == rows[0]
    assert kept[1].cut_frame == boundary and kept[1].end_frame == boundary
    assert len(kept) == 2


def test_cut_for_recovery_with_nothing_published_drops_everything():
    assert planner.cut_for_recovery(_rows_at(10), None) == []


def test_publish_next():
    rows = _rows_at(10)
    assert planner.current_run_start(rows) == 10
    assert planner.publish_next([], None) is None
    assert planner.publish_next(rows, None) == 10
    assert planner.publish_next(rows, 14) == 15
    assert planner.publish_next(rows, 3) == 10        # last belongs to an older run


def test_plan_file_round_trip(tmp_path):
    rows = _rows_at(10)
    planner.write_plan(tmp_path / "plan.jsonl", rows)
    assert planner.read_plan(tmp_path / "plan.jsonl") == rows
    assert planner.read_plan(tmp_path / "missing.jsonl") == []
    assert [p.name for p in tmp_path.iterdir()] == ["plan.jsonl"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_planner.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'transmitter.planner'`.

- [ ] **Step 3: Implement `planner.py`**

```python
"""Phase-1 trivial planner (spec "Scheduler": "Phase 1 replaces all of this
with a trivial planner: eligible packages in a fixed shuffled order, back to
back with the inter-show gap").

The order is a seeded hash rank, so adding or removing a package never
reshuffles the others; selection is least-recently-planned first, which walks
that order as a cycle and lets a newly eligible show air once soon and then
fall in line. Phase 3's scheduler replaces `choose_next`/`extend`; the plan
file, recovery cut and re-plan rules stay.
"""

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Callable, Mapping, Sequence

from transmitter.errors import PlanError, TransmitterError
from transmitter.grid import SEGMENT_FRAMES
from transmitter.layout import PlanRow, validate_rows
from transmitter.station import Show
from transmitter.workspace import atomic_write_text


def shuffle_rank(seed: int, slug: str) -> str:
    return hashlib.sha256(f"{seed}:{slug}".encode()).hexdigest()


def choose_next(eligible: Sequence[Show], last_seq: Mapping[str, int], seed: int,
                previous: str | None) -> Show:
    if not eligible:
        raise PlanError("no eligible packages to plan")
    ordered = sorted(eligible, key=lambda s: (last_seq.get(s.slug, -1), shuffle_rank(seed, s.slug)))
    if ordered[0].slug == previous and len(ordered) > 1:
        return ordered[1]
    return ordered[0]


def extend(rows: Sequence[PlanRow], eligible: Sequence[Show], *, frames_of: Callable[[Show], int],
           seed: int, gap_frames: int, until_frame: int, start_frame: int, run_start: bool,
           max_new: int | None = None,
           on_skip: Callable[[Show, Exception], None] = lambda show, exc: None) -> list[PlanRow]:
    out = list(rows)
    last_seq = {r.slug: r.seq for r in out}
    next_seq = max((r.seq for r in out), default=-1) + 1
    pool = list(eligible)
    previous = out[-1].slug if out else None
    start, mark, added = start_frame, run_start, 0
    while (not out or out[-1].end_frame < until_frame) and (max_new is None or added < max_new):
        chosen = choose_next(pool, last_seq, seed, previous)
        try:
            frames = frames_of(chosen)
        except TransmitterError as exc:
            on_skip(chosen, exc)
            pool = [s for s in pool if s.slug != chosen.slug]
            continue
        row = PlanRow(seq=next_seq, slug=chosen.slug, dir=chosen.dir.name, key=chosen.key,
                      start_frame=start, frames=frames, run_start=mark)
        out.append(row)
        last_seq[chosen.slug] = next_seq
        next_seq += 1
        added += 1
        previous = chosen.slug
        start, mark = row.end_frame + gap_frames, False
    validate_rows(out)
    return out


def next_start(rows: Sequence[PlanRow], gap_frames: int) -> int:
    return rows[-1].end_frame + gap_frames


def replan_from(rows: Sequence[PlanRow], index: int) -> tuple[list[PlanRow], int, bool]:
    """Skip rows[index] at its boundary: keep everything before it and re-plan
    from its start frame (spec "Frozen means rendered")."""
    return list(rows[:index]), rows[index].start_frame, rows[index].run_start


def cut_for_recovery(rows: Sequence[PlanRow], published_last: int | None) -> list[PlanRow]:
    """After an outage longer than the lead: keep the rows that began before
    the first unpublished segment, cut the one spanning it there, drop the rest."""
    if published_last is None:
        return []
    boundary = (published_last + 1) * SEGMENT_FRAMES
    kept: list[PlanRow] = []
    for r in rows:
        if r.start_frame >= boundary:
            break
        if r.end_frame > boundary:
            r = replace(r, cut_frame=boundary)
        kept.append(r)
    return kept


def current_run_start(rows: Sequence[PlanRow]) -> int | None:
    for r in reversed(rows):
        if r.run_start:
            return r.start_frame // SEGMENT_FRAMES
    return None


def publish_next(rows: Sequence[PlanRow], last: int | None) -> int | None:
    """The next segment to render/publish: continue the current run, or start
    the run if what was published belongs to an older one."""
    rs = current_run_start(rows)
    if rs is None:
        return None
    if last is not None and last + 1 >= rs:
        return last + 1
    return rs


def read_plan(path: Path) -> list[PlanRow]:
    try:
        text = Path(path).read_text()
    except FileNotFoundError:
        return []
    rows = [PlanRow.from_json(json.loads(line)) for line in text.splitlines() if line.strip()]
    validate_rows(rows)
    return rows


def write_plan(path: Path, rows: Sequence[PlanRow]) -> None:
    validate_rows(rows)
    atomic_write_text(path, "".join(json.dumps(r.to_json(), sort_keys=True) + "\n" for r in rows))
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_planner.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): trivial planner with recovery cut and re-plan"
```

---

### Task 7: Gapless decode, loudness meter, analysis cache

**Model hint:** opus

**Files:**
- Create: `packages/transmitter/src/transmitter/audio.py`, `packages/transmitter/src/transmitter/analysis.py`
- Create: `packages/transmitter/tests_transmitter/test_audio.py`, `test_analysis.py`
- Modify: `packages/transmitter/tests_transmitter/helpers.py` (MP3 fixture writer)

**Interfaces:**
- Consumes: `aacenc.as_station_pcm`, `grid`, `station.Show/Entry`, `workspace.read_json/write_json`, `errors.DecodeError/AnalysisError`.
- Produces:
  - `transmitter.audio`: `decode_cmd(ffmpeg, path) -> list[str]`; `iter_decode(path, ffmpeg="ffmpeg") -> Iterator[np.ndarray]` (float32 `(n, 2)` at 44.1 kHz, LAME delay/padding honoured); `Loudness(i_lufs: float | None, tp_dbfs: float | None)`; `METER_FILTER`; `LoudnessMeter(ffmpeg="ffmpeg")` with `.write(pcm)`, `.finish() -> Loudness`, `.abort()`; `parse_ebur128_summary(text) -> Loudness`.
  - `transmitter.analysis`: `ANALYSIS_VERSION = 1`; `TRUE_PEAK_CEILING_DB = -1.0`; `FileAnalysis(path, kind, title, samples, i_lufs=None, tp_dbfs=None)`; `ShowAnalysis(key, slug, files: tuple[FileAnalysis, ...], tracks_i_lufs, tracks_tp_dbfs, meta: dict)` with `.to_json()`/`ShowAnalysis.from_json(d)`; `analyze_show(show, ffmpeg="ffmpeg") -> ShowAnalysis`; `load_cached(cache_dir, key) -> ShowAnalysis | None`; `load_or_analyze(cache_dir, show, ffmpeg="ffmpeg") -> ShowAnalysis`; `gain_db(target, i_lufs, tp_dbfs, ceiling=TRUE_PEAK_CEILING_DB) -> float`.
  - helpers: `stereo_sine(seconds, freq, amp, phase=0.0, rate=44100) -> np.ndarray`, `write_mp3(path, pcm, rate=44100)` (libmp3lame, LAME tag included).

- [ ] **Step 1: Write the failing tests**

Append to `tests_transmitter/helpers.py`:

```python
def stereo_sine(seconds: float, freq: float, amp: float, phase: float = 0.0,
                rate: int = 44_100) -> np.ndarray:
    n = round(seconds * rate)
    t = np.arange(n, dtype=np.float64)
    mono = amp * np.sin(phase + 2 * np.pi * freq * t / rate)
    return np.repeat(mono.astype(np.float32)[:, None], 2, axis=1)


def write_mp3(path: Path, pcm: np.ndarray, rate: int = 44_100) -> None:
    """Encode float32 PCM (n, channels) to MP3 with libmp3lame, which writes
    the Xing/LAME header carrying encoder delay and padding (the gapless info
    archive.org derivatives carry)."""
    channels = 1 if pcm.ndim == 1 else pcm.shape[1]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "f32le", "-ar", str(rate),
         "-ac", str(channels), "-i", "pipe:0", "-c:a", "libmp3lame", "-b:a", "192k", str(path)],
        input=np.ascontiguousarray(pcm, dtype=np.float32).tobytes(), check=True,
    )
```

`tests_transmitter/test_audio.py`:

```python
import numpy as np
import pytest

from tests_transmitter.helpers import requires_ffmpeg, stereo_sine, write_mp3
from transmitter import audio
from transmitter.errors import AnalysisError, DecodeError

SUMMARY = """[Parsed_ebur128_0 @ 0x1] Summary:

  Integrated loudness:
    I:         -18.4 LUFS
    Threshold: -28.5 LUFS

  Loudness range:
    LRA:         6.1 LU

  True peak:
    Peak:       -0.7 dBFS
"""


def test_parse_summary():
    assert audio.parse_ebur128_summary("noise\n" + SUMMARY) == audio.Loudness(-18.4, -0.7)


def test_parse_summary_handles_silence():
    text = SUMMARY.replace("-18.4 LUFS", "-70.0 LUFS").replace("-0.7 dBFS", "-inf dBFS")
    assert audio.parse_ebur128_summary(text) == audio.Loudness(None, None)


def test_parse_summary_uses_the_last_summary():
    text = SUMMARY.replace("-18.4", "-30.0") + SUMMARY
    assert audio.parse_ebur128_summary(text).i_lufs == -18.4


def test_parse_summary_without_summary_is_an_error():
    with pytest.raises(AnalysisError):
        audio.parse_ebur128_summary("no summary here")


@requires_ffmpeg
def test_decode_honours_lame_delay_and_padding(tmp_path):
    """Two halves of one sine, split at a sample that is not an MP3 frame
    boundary, decode back to exactly their own lengths: a segue stays gapless."""
    pcm = stereo_sine(6.0, 440.0, 0.3)
    split = 123_457
    write_mp3(tmp_path / "a.mp3", pcm[:split])
    write_mp3(tmp_path / "b.mp3", pcm[split:])
    a = np.concatenate(list(audio.iter_decode(tmp_path / "a.mp3")))
    b = np.concatenate(list(audio.iter_decode(tmp_path / "b.mp3")))
    assert len(a) == split and len(b) == len(pcm) - split
    assert a.dtype == np.float32 and a.shape[1] == 2


@requires_ffmpeg
def test_decode_resamples_a_mono_24k_clip_to_stereo_44k1(tmp_path):
    mono = stereo_sine(2.0, 300.0, 0.3, rate=24_000)[:, 0]
    write_mp3(tmp_path / "clip.mp3", mono, rate=24_000)
    out = np.concatenate(list(audio.iter_decode(tmp_path / "clip.mp3")))
    assert out.shape[1] == 2
    assert abs(len(out) - 88_200) <= 64


@requires_ffmpeg
def test_decode_failure_is_a_decode_error(tmp_path):
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"not audio at all")
    with pytest.raises(DecodeError):
        list(audio.iter_decode(bad))


@requires_ffmpeg
def test_meter_measures_a_known_sine():
    meter = audio.LoudnessMeter()
    pcm = stereo_sine(8.0, 1000.0, 0.1)            # -20 dBFS peak in both channels
    for i in range(0, len(pcm), 50_000):
        meter.write(pcm[i:i + 50_000])
    loud = meter.finish()
    assert loud.i_lufs == pytest.approx(-20.0, abs=0.5)
    assert loud.tp_dbfs == pytest.approx(-20.0, abs=0.5)


@requires_ffmpeg
def test_meter_on_silence_and_on_nothing():
    meter = audio.LoudnessMeter()
    meter.write(np.zeros((44_100 * 3, 2), np.float32))
    assert meter.finish() == audio.Loudness(None, None)
    assert audio.LoudnessMeter().finish() == audio.Loudness(None, None)
```

`tests_transmitter/test_analysis.py`:

```python
import time

import numpy as np
import pytest

from tests_transmitter.helpers import build_package, make_root, requires_ffmpeg, stereo_sine, write_mp3
from transmitter import analysis, audio, station
from transmitter.analysis import FileAnalysis, ShowAnalysis, gain_db


def test_gain_db_loudness_bound():
    assert gain_db(-16.0, -20.0, -10.0) == pytest.approx(4.0)


def test_gain_db_true_peak_bound():
    assert gain_db(-16.0, -20.0, -2.0) == pytest.approx(1.0)       # -1 - (-2)


def test_gain_db_turns_down_a_hot_tape():
    assert gain_db(-16.0, -10.0, -0.1) == pytest.approx(-6.0)


def test_gain_db_unmeasurable_is_unity():
    assert gain_db(-16.0, None, None) == 0.0
    assert gain_db(-16.0, None, -3.0) == 0.0


def test_gain_db_without_a_peak_reading_uses_loudness_alone():
    assert gain_db(-16.0, -20.0, None) == pytest.approx(4.0)


def test_show_analysis_json_round_trip():
    a = ShowAnalysis(key="k", slug="s", files=(FileAnalysis("audio/a.mp3", "track", "A", 10),
                                               FileAnalysis("dj-audio/x.mp3", "clip", "DJ", 5, -18.0, -3.0)),
                     tracks_i_lufs=-17.0, tracks_tp_dbfs=-1.5, meta={"artist": "Band"})
    assert ShowAnalysis.from_json(a.to_json()) == a


def _tone_writer(path, i):
    if i in (0, 99):          # DJ clips: mono 24 kHz, like emcee's
        write_mp3(path, stereo_sine(1.5, 300.0, 0.05, rate=24_000)[:, 0], rate=24_000)
    else:
        write_mp3(path, stereo_sine(2.0, 440.0 + 110 * i, 0.2))


@requires_ffmpeg
def test_analyze_show_counts_samples_and_measures_tracks_apart_from_clips(tmp_path):
    pkg = build_package(make_root(tmp_path), tracks=2, audio=_tone_writer)
    show = station.evaluate(pkg, now_s=time.time(), quiet_s=0)
    a = analysis.analyze_show(show)
    assert [f.path for f in a.files] == [e.path for e in show.entries]
    assert [f.samples for f in a.files if f.kind == "track"] == [88_200, 88_200]
    clips = [f for f in a.files if f.kind == "clip"]
    assert all(f.i_lufs is not None and f.i_lufs < -25 for f in clips)
    assert a.tracks_i_lufs == pytest.approx(20 * np.log10(0.2), abs=1.0)
    assert a.meta["artist"] == "Band"


@requires_ffmpeg
def test_load_or_analyze_caches_by_key(tmp_path, monkeypatch):
    pkg = build_package(make_root(tmp_path), tracks=1, audio=_tone_writer)
    show = station.evaluate(pkg, now_s=time.time(), quiet_s=0)
    first = analysis.load_or_analyze(tmp_path / "cache", show)
    assert (tmp_path / "cache" / f"{show.key}.json").exists()

    def boom(*a, **k):
        raise AssertionError("decoded again despite a cache hit")

    monkeypatch.setattr(analysis, "iter_decode", boom)
    assert analysis.load_or_analyze(tmp_path / "cache", show) == first
    assert analysis.load_cached(tmp_path / "cache", show.key) == first
    assert analysis.load_cached(tmp_path / "cache", "nope") is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_audio.py packages/transmitter/tests_transmitter/test_analysis.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'transmitter.audio'`.

- [ ] **Step 3: Implement `audio.py`**

```python
"""Gapless decode and loudness measurement (spec "Renderer", "Loudness").

Decoding is ffmpeg to float32 44.1 kHz stereo PCM. ffmpeg's MP3 demuxer reads
the Xing/LAME header and trims encoder delay and padding, so consecutive tracks
of a segue concatenate with no inserted silence. Loudness is ffmpeg's
`ebur128` filter (BS.1770 integrated loudness + true peak), fed the same PCM
through a pipe. Every subprocess writes stderr to an anonymous temp file, so
no pipe can fill and deadlock the reader/writer.
"""

import math
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

from transmitter.aacenc import as_station_pcm
from transmitter.errors import AnalysisError, DecodeError
from transmitter.grid import CHANNELS, SAMPLE_RATE

CHUNK_FRAMES = 1 << 16
_BYTES_PER_FRAME = 4 * CHANNELS
METER_FILTER = "ebur128=peak=true:framelog=verbose"
SILENCE_LUFS = -70.0   # ebur128's absolute gate: nothing measurable


def decode_cmd(ffmpeg: str, path: Path) -> list[str]:
    return [ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-i", str(path),
            "-map", "0:a:0", "-f", "f32le", "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE), "pipe:1"]


def iter_decode(path: Path, ffmpeg: str = "ffmpeg") -> Iterator[np.ndarray]:
    err = tempfile.TemporaryFile()
    try:
        proc = subprocess.Popen(decode_cmd(ffmpeg, path), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=err)
    except OSError as exc:
        err.close()
        raise DecodeError(f"cannot run {ffmpeg}: {exc}") from exc
    finished = False
    try:
        pending = b""
        while True:
            chunk = proc.stdout.read(CHUNK_FRAMES * _BYTES_PER_FRAME)
            if not chunk:
                break
            data = pending + chunk
            usable = len(data) - len(data) % _BYTES_PER_FRAME
            pending = data[usable:]
            if usable:
                yield np.frombuffer(data[:usable], dtype="<f4").reshape(-1, CHANNELS)
        rc = proc.wait()
        if rc != 0 or pending:
            err.seek(0)
            tail = err.read().decode(errors="replace").strip()[-500:]
            raise DecodeError(f"{path}: ffmpeg decode failed (exit {rc}): {tail}")
        finished = True
    finally:
        if not finished and proc.poll() is None:
            proc.kill()
        proc.stdout.close()
        proc.wait()
        err.close()


@dataclass(frozen=True)
class Loudness:
    i_lufs: float | None     # None = nothing above the gate (silence)
    tp_dbfs: float | None    # None = -inf (digital silence)


_I_RE = re.compile(r"Integrated loudness:\s*\n\s*I:\s*(\S+)\s+LUFS")
_TP_RE = re.compile(r"True peak:\s*\n\s*Peak:\s*(\S+)\s+dBFS")


def _finite(text: str) -> float | None:
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def parse_ebur128_summary(text: str) -> Loudness:
    at = text.rfind("Summary:")
    if at < 0:
        raise AnalysisError("ffmpeg ebur128 printed no summary")
    tail = text[at:]
    m_i = _I_RE.search(tail)
    if m_i is None:
        raise AnalysisError("ffmpeg ebur128 summary has no integrated loudness")
    m_tp = _TP_RE.search(tail)
    i = _finite(m_i.group(1))
    if i is not None and i <= SILENCE_LUFS:
        i = None
    return Loudness(i, _finite(m_tp.group(1)) if m_tp else None)


class LoudnessMeter:
    """Feeds PCM into `ffmpeg -af ebur128` and parses its summary. The process
    starts lazily, so a meter that never receives samples reports (None, None)."""

    def __init__(self, ffmpeg: str = "ffmpeg"):
        self._ffmpeg = ffmpeg
        self._proc: subprocess.Popen | None = None
        self._err = None
        self.samples = 0

    def _start(self) -> None:
        self._err = tempfile.TemporaryFile()
        cmd = [self._ffmpeg, "-nostdin", "-hide_banner", "-nostats",
               "-f", "f32le", "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS), "-i", "pipe:0",
               "-af", METER_FILTER, "-f", "null", "-"]
        try:
            self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                          stderr=self._err)
        except OSError as exc:
            self._err.close()
            raise AnalysisError(f"cannot run {self._ffmpeg}: {exc}") from exc

    def write(self, pcm: np.ndarray) -> None:
        if len(pcm) == 0:
            return
        if self._proc is None:
            self._start()
        try:
            self._proc.stdin.write(as_station_pcm(pcm).tobytes())
        except BrokenPipeError as exc:
            raise AnalysisError(f"ffmpeg ebur128 exited early: {self._stderr()[-500:]}") from exc
        self.samples += len(pcm)

    def finish(self) -> Loudness:
        if self._proc is None:
            return Loudness(None, None)
        try:
            self._proc.stdin.close()
        except BrokenPipeError:
            pass
        rc = self._proc.wait()
        text = self._stderr()
        self._err.close()
        self._proc = None
        if rc != 0:
            raise AnalysisError(f"ffmpeg ebur128 failed (exit {rc}): {text.strip()[-500:]}")
        return parse_ebur128_summary(text)

    def abort(self) -> None:
        if self._proc is None:
            return
        self._proc.kill()
        self._proc.wait()
        try:
            self._proc.stdin.close()
        except BrokenPipeError:
            pass
        self._err.close()
        self._proc = None

    def _stderr(self) -> str:
        self._err.seek(0)
        return self._err.read().decode(errors="replace")
```

- [ ] **Step 4: Implement `analysis.py`**

```python
"""Per-show analysis (spec: "Durations and loudness come from one decode pass
per show ... cached keyed by the show's file set"): decoded sample counts per
file, integrated loudness + true peak over the tracks only, and per-clip
loudness for DJ clips (their own speech target). Rendering decodes again with
the same decoder and must reproduce these sample counts exactly."""

from dataclasses import asdict, dataclass
from pathlib import Path

from transmitter.audio import LoudnessMeter, iter_decode
from transmitter.errors import AnalysisError
from transmitter.station import Show
from transmitter.workspace import read_json, write_json

ANALYSIS_VERSION = 1
TRUE_PEAK_CEILING_DB = -1.0


@dataclass(frozen=True)
class FileAnalysis:
    path: str
    kind: str
    title: str
    samples: int
    i_lufs: float | None = None      # clips only
    tp_dbfs: float | None = None     # clips only


@dataclass(frozen=True)
class ShowAnalysis:
    key: str
    slug: str
    files: tuple[FileAnalysis, ...]
    tracks_i_lufs: float | None
    tracks_tp_dbfs: float | None
    meta: dict

    def to_json(self) -> dict:
        data = asdict(self)
        data["files"] = [asdict(f) for f in self.files]
        data["version"] = ANALYSIS_VERSION
        return data

    @classmethod
    def from_json(cls, data: dict) -> "ShowAnalysis":
        return cls(key=data["key"], slug=data["slug"],
                   files=tuple(FileAnalysis(**f) for f in data["files"]),
                   tracks_i_lufs=data["tracks_i_lufs"], tracks_tp_dbfs=data["tracks_tp_dbfs"],
                   meta=dict(data["meta"]))


def gain_db(target: float, i_lufs: float | None, tp_dbfs: float | None,
            ceiling: float = TRUE_PEAK_CEILING_DB) -> float:
    """min(target - I, ceiling - TP). The target is a ceiling, so quiet,
    dynamic tapes are not pushed into a limiter; unmeasurable audio (I below
    the gate) is left at unity gain."""
    if i_lufs is None:
        return 0.0
    gain = target - i_lufs
    if tp_dbfs is not None:
        gain = min(gain, ceiling - tp_dbfs)
    return gain


def analyze_show(show: Show, ffmpeg: str = "ffmpeg") -> ShowAnalysis:
    tracks = LoudnessMeter(ffmpeg)
    files: list[FileAnalysis] = []
    try:
        for entry in show.entries:
            clip_meter = LoudnessMeter(ffmpeg) if entry.kind == "clip" else None
            meter = clip_meter or tracks
            n = 0
            try:
                for pcm in iter_decode(show.dir / entry.path, ffmpeg):
                    meter.write(pcm)
                    n += len(pcm)
            except BaseException:
                if clip_meter is not None:
                    clip_meter.abort()
                raise
            if n == 0:
                raise AnalysisError(f"{show.slug}: {entry.path} decoded to no audio")
            loud = clip_meter.finish() if clip_meter is not None else None
            files.append(FileAnalysis(entry.path, entry.kind, entry.title, n,
                                      loud.i_lufs if loud else None, loud.tp_dbfs if loud else None))
        t = tracks.finish()
    except BaseException:
        tracks.abort()
        raise
    return ShowAnalysis(key=show.key, slug=show.slug, files=tuple(files),
                        tracks_i_lufs=t.i_lufs, tracks_tp_dbfs=t.tp_dbfs, meta=dict(show.meta))


def load_cached(cache_dir: Path, key: str) -> ShowAnalysis | None:
    data = read_json(Path(cache_dir) / f"{key}.json")
    if not data or data.get("version") != ANALYSIS_VERSION or data.get("key") != key:
        return None
    return ShowAnalysis.from_json(data)


def load_or_analyze(cache_dir: Path, show: Show, ffmpeg: str = "ffmpeg") -> ShowAnalysis:
    cached = load_cached(cache_dir, show.key)
    if cached is not None:
        return cached
    result = analyze_show(show, ffmpeg)
    write_json(Path(cache_dir) / f"{show.key}.json", result.to_json())
    return result
```

- [ ] **Step 5: Run the tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_audio.py packages/transmitter/tests_transmitter/test_analysis.py -q`
Expected: PASS.

Run: `packages/transmitter/scripts/test-in-debian12.sh`
Expected: PASS on ffmpeg 5.1 (this is where `framelog=verbose`, `-map 0:a:0` and LAME gapless decode are confirmed on hugo's ffmpeg; if `framelog` is rejected there, drop `:framelog=verbose` from `METER_FILTER` — stderr goes to a temp file, so per-frame lines are only wasted bytes — and re-run).

- [ ] **Step 6: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): gapless decode, ebur128 loudness and the per-show analysis cache"
```

---

### Task 8: Show render — joins, gain, encode, frame check

**Model hint:** opus

**Files:**
- Create: `packages/transmitter/src/transmitter/render.py`
- Create: `packages/transmitter/tests_transmitter/test_render.py`

**Interfaces:**
- Consumes: `aacenc.AacFileEncoder/frames_for/pad_to_frame/extra_frames`, `adts.frame_offsets`, `analysis.ShowAnalysis/FileAnalysis/gain_db`, `audio.iter_decode`, `config.RenderConfig`, `station.Show`, `errors.RenderError/FrameCountDrift`.
- Produces:
  - `FileSpan(path, kind, title, start_sample, samples)`; `ShowLayout(spans: tuple[FileSpan, ...], content_samples, padded_samples)`.
  - `show_layout(analysis, pause_samples) -> ShowLayout` — clip↔track and clip↔clip joins get `pause_samples`, track→track gets 0; padded to whole frames.
  - `planned_frames(analysis, pause_samples, extra) -> int`.
  - `RenderSettings(ffmpeg, music_target_lufs, speech_target_lufs, clip_pause_samples)` with `RenderSettings.from_config(cfg: RenderConfig)`.
  - `file_gain(file, analysis, settings) -> float` (linear).
  - `render_show(show, analysis, out_path, *, settings, extra) -> int` (frames written; raises `RenderError` on a changed package, `FrameCountDrift` on a frame-count mismatch).

- [ ] **Step 1: Write the failing tests**

`tests_transmitter/test_render.py`:

```python
import time

import numpy as np
import pytest

from tests_transmitter.helpers import (build_package, decode_adts, make_root, requires_ffmpeg,
                                       stereo_sine, write_mp3)
from transmitter import aacenc, analysis, render, station
from transmitter.analysis import FileAnalysis, ShowAnalysis
from transmitter.config import RenderConfig
from transmitter.errors import FrameCountDrift, RenderError


def _a(*files):
    return ShowAnalysis(key="k", slug="s", files=tuple(FileAnalysis(p, k, p, n) for p, k, n in files),
                        tracks_i_lufs=-20.0, tracks_tp_dbfs=-6.0, meta={})


def test_layout_joins():
    a = _a(("i", "clip", 100), ("t1", "track", 1000), ("t2", "track", 1000), ("o", "clip", 50))
    lay = render.show_layout(a, pause_samples=7)
    assert [s.start_sample for s in lay.spans] == [0, 107, 1107, 2114]
    assert lay.content_samples == 2164
    assert lay.padded_samples == 3072


def test_layout_clip_to_clip_also_pauses():
    lay = render.show_layout(_a(("a", "clip", 10), ("b", "clip", 10)), pause_samples=5)
    assert [s.start_sample for s in lay.spans] == [0, 15]


def test_planned_frames():
    a = _a(("t", "track", 2048))
    assert render.planned_frames(a, 0, extra=1) == 3


def test_file_gain_uses_the_track_set_for_tracks_and_the_clip_for_clips():
    s = render.RenderSettings("ffmpeg", -16.0, -18.0, 0)
    a = ShowAnalysis("k", "s", (FileAnalysis("t", "track", "t", 1), FileAnalysis("c", "clip", "c", 1, -24.0, -12.0)),
                     tracks_i_lufs=-20.0, tracks_tp_dbfs=-6.0, meta={})
    assert render.file_gain(a.files[0], a, s) == pytest.approx(10 ** (4.0 / 20))
    assert render.file_gain(a.files[1], a, s) == pytest.approx(10 ** (6.0 / 20))


def _segue_package(tmp_path):
    """Two tracks cut from one phase-continuous sine (a segue) between DJ clips."""
    music = stereo_sine(6.0, 440.0, 0.1)
    split = 130_001

    def writer(path, i):
        if i == 1:
            write_mp3(path, music[:split])
        elif i == 2:
            write_mp3(path, music[split:])
        else:
            write_mp3(path, stereo_sine(1.0, 300.0, 0.05, rate=24_000)[:, 0], rate=24_000)

    pkg = build_package(make_root(tmp_path), tracks=2, audio=writer)
    return station.evaluate(pkg, now_s=time.time(), quiet_s=0), split


@requires_ffmpeg
def test_render_show_frame_count_gain_and_gapless_segue(tmp_path):
    show, split = _segue_package(tmp_path)
    a = analysis.analyze_show(show)
    settings = render.RenderSettings.from_config(RenderConfig())     # -16/-16 LUFS, 0.75 s pause
    extra = aacenc.extra_frames()
    out = tmp_path / "shows" / f"{show.key}.aac"
    frames = render.render_show(show, a, out, settings=settings, extra=extra)
    assert frames == render.planned_frames(a, settings.clip_pause_samples, extra)

    pcm = decode_adts(out.read_bytes())[aacenc.ENCODER_PRIMING_SAMPLES:]
    lay = render.show_layout(a, settings.clip_pause_samples)
    t1, t2 = lay.spans[1], lay.spans[2]
    assert t2.start_sample == t1.start_sample + t1.samples        # no inserted silence
    join = t2.start_sample
    rms = float(np.sqrt(np.mean(pcm[join - 2048:join + 2048, 0] ** 2)))
    expected_amp = 0.1 * render.file_gain(a.files[1], a, settings)     # file_gain is linear
    assert rms == pytest.approx(expected_amp / np.sqrt(2), rel=0.15)   # no dip at the segue

    pause_mid = lay.spans[1].start_sample - settings.clip_pause_samples // 2
    assert float(np.max(np.abs(pcm[pause_mid - 500:pause_mid + 500]))) < 0.01   # clip->track pause


@requires_ffmpeg
def test_render_refuses_a_package_that_changed_after_analysis(tmp_path):
    show, _ = _segue_package(tmp_path)
    a = analysis.analyze_show(show)
    files = list(a.files)
    files[1] = FileAnalysis(files[1].path, "track", files[1].title, files[1].samples + 1)
    stale = ShowAnalysis(a.key, a.slug, tuple(files), a.tracks_i_lufs, a.tracks_tp_dbfs, a.meta)
    out = tmp_path / "x.aac"
    with pytest.raises(RenderError, match="the package changed"):
        render.render_show(show, stale, out, settings=render.RenderSettings("ffmpeg", -16, -16, 0),
                           extra=aacenc.extra_frames())
    assert not out.exists() and not any(out.parent.glob(".x.aac.*"))


@requires_ffmpeg
def test_frame_count_drift_is_fatal(tmp_path):
    show, _ = _segue_package(tmp_path)
    a = analysis.analyze_show(show)
    out = tmp_path / "x.aac"
    with pytest.raises(FrameCountDrift):
        render.render_show(show, a, out, settings=render.RenderSettings("ffmpeg", -16, -16, 0),
                           extra=aacenc.extra_frames() + 1)
    assert not out.exists()


def test_render_refuses_a_mismatched_analysis(tmp_path):
    show = station.Show("s", tmp_path, (station.Entry("audio/a.mp3", "track", "A"),), "k", {})
    with pytest.raises(RenderError, match="does not match"):
        render.render_show(show, _a(("audio/b.mp3", "track", 10)), tmp_path / "x.aac",
                           settings=render.RenderSettings("ffmpeg", -16, -16, 0), extra=1)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_render.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'transmitter.render'`.

- [ ] **Step 3: Implement `render.py`**

```python
"""Per-show encode (spec "Per-show encode, frame-count segmentation", "Joins",
"Loudness").

A show's whole broadcast.m3u is decoded gaplessly, gained (tracks by the
show's track-set gain, each DJ clip by its own speech gain), joined (no
silence track->track; `clip_pause` around clips), padded to a whole frame and
encoded once. The encoder's output -- priming and flush frames included -- is
the show's frame count; it must equal `planned_frames`, which the planner used
to place the next show."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from transmitter import aacenc, adts
from transmitter.analysis import FileAnalysis, ShowAnalysis, gain_db
from transmitter.audio import iter_decode
from transmitter.config import RenderConfig
from transmitter.errors import FrameCountDrift, RenderError
from transmitter.grid import samples_for_seconds
from transmitter.station import Show


@dataclass(frozen=True)
class FileSpan:
    path: str
    kind: str
    title: str
    start_sample: int     # within the show, before encoder priming
    samples: int


@dataclass(frozen=True)
class ShowLayout:
    spans: tuple[FileSpan, ...]
    content_samples: int
    padded_samples: int


def show_layout(analysis: ShowAnalysis, pause_samples: int) -> ShowLayout:
    spans: list[FileSpan] = []
    pos = 0
    prev: str | None = None
    for f in analysis.files:
        if prev is not None and "clip" in (prev, f.kind):
            pos += pause_samples
        spans.append(FileSpan(f.path, f.kind, f.title, pos, f.samples))
        pos += f.samples
        prev = f.kind
    return ShowLayout(tuple(spans), pos, aacenc.pad_to_frame(pos))


def planned_frames(analysis: ShowAnalysis, pause_samples: int, extra: int) -> int:
    return aacenc.frames_for(show_layout(analysis, pause_samples).padded_samples, extra)


@dataclass(frozen=True)
class RenderSettings:
    ffmpeg: str
    music_target_lufs: float
    speech_target_lufs: float
    clip_pause_samples: int

    @classmethod
    def from_config(cls, cfg: RenderConfig) -> "RenderSettings":
        return cls(cfg.ffmpeg, cfg.music_target_lufs, cfg.speech_target_lufs,
                   samples_for_seconds(cfg.clip_pause_seconds))


def file_gain(f: FileAnalysis, analysis: ShowAnalysis, settings: RenderSettings) -> float:
    if f.kind == "clip":
        db = gain_db(settings.speech_target_lufs, f.i_lufs, f.tp_dbfs)
    else:
        db = gain_db(settings.music_target_lufs, analysis.tracks_i_lufs, analysis.tracks_tp_dbfs)
    return 10.0 ** (db / 20.0)


def render_show(show: Show, analysis: ShowAnalysis, out_path: Path, *,
                settings: RenderSettings, extra: int) -> int:
    if analysis.key != show.key or [f.path for f in analysis.files] != [e.path for e in show.entries]:
        raise RenderError(f"{show.slug}: analysis does not match the package's current file set")
    layout = show_layout(analysis, settings.clip_pause_samples)
    expected = aacenc.frames_for(layout.padded_samples, extra)
    enc = aacenc.AacFileEncoder(out_path, settings.ffmpeg)
    try:
        pos = 0
        for span, f in zip(layout.spans, analysis.files):
            enc.write_silence(span.start_sample - pos)
            gain = file_gain(f, analysis, settings)
            n = 0
            for pcm in iter_decode(show.dir / span.path, settings.ffmpeg):
                # The gain rule already bounds true peak at -1 dBTP; the clamp is
                # the safety limiter the spec calls for, and normally never acts.
                enc.write(np.clip(pcm * gain, -1.0, 1.0))
                n += len(pcm)
            if n != span.samples:
                raise RenderError(f"{show.slug}: {span.path} decoded to {n} samples but was "
                                  f"analysed at {span.samples} -- the package changed")
            pos = span.start_sample + n
        enc.write_silence(layout.padded_samples - pos)
        enc.close()
    except BaseException:
        enc.abort()
        raise
    frames = len(adts.frame_offsets(Path(out_path).read_bytes())) - 1
    if frames != expected:
        Path(out_path).unlink(missing_ok=True)
        raise FrameCountDrift(f"{show.slug}: encoder produced {frames} frames, expected {expected} "
                              f"({layout.padded_samples} padded samples + {extra}); the frame-count "
                              "model does not hold on this ffmpeg")
    return frames
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_render.py -q`
Expected: PASS.

Run: `packages/transmitter/scripts/test-in-debian12.sh`
Expected: PASS on ffmpeg 5.1.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): per-show render with gapless joins, loudness gain and frame-count check"
```

---

### Task 9: Plan and render steps — revalidation, recovery, segment writing

**Model hint:** opus

**Files:**
- Create: `packages/transmitter/src/transmitter/pipeline.py`
- Create: `packages/transmitter/tests_transmitter/test_pipeline.py`
- Modify: `packages/transmitter/tests_transmitter/helpers.py` (`FakeEngine`)

**Interfaces:**
- Consumes: Tasks 3–8: `TransmitterConfig`, `Workspace`, `Epoch`, `atomic_write_bytes`, `load_publish_state`, `FrameStore/PlanRow/rows_overlapping`, `station.scan/Show/Ineligible`, `planner.*`, `analysis.load_or_analyze/ShowAnalysis`, `render.render_show/planned_frames/RenderSettings`, `aacenc.extra_frames/silent_frame`, `errors.*`.
- Produces:
  - `Engine` protocol: `analyze(show) -> ShowAnalysis`, `extra_frames() -> int`, `silent_frame() -> bytes`, `encode_show(show, analysis, out_path) -> int`. `FfmpegEngine(ws, cfg)` implements it.
  - `Station(ws, cfg, epoch, engine, scan=None, log=print)` with `scan_now(now_us) -> list[Show]`, `gap_frames`, `pause_samples`, `lead_us`, `until_frame(now_us)`, `start_margin_segments`, `frames_of(show) -> int`.
  - `plan_step(st, now_us, *, max_new=None) -> list[PlanRow]`.
  - `RenderReport(written: list[int], replanned: list[str], covered: bool)`; `render_step(st, now_us, *, limit=None) -> RenderReport` — raises `FrameCountDrift` on an encode/plan frame mismatch, and `LayoutError` when a row whose encode is missing has already started airing (`r.start_frame < n·441`): re-planning it would cut a show mid-air. Garbage-collects finished encodes and `render/shows/.*.tmp` files older than 1 h.
    > **As built (final review, O3):** a row already on air whose encode is missing is **re-encoded** when its package is unchanged (same key, still eligible, same planned frame count); `LayoutError` is raised only when it cannot be re-made — package changed, no longer eligible, planned frame count changed, or the encode fails. A re-encode that comes out at a different frame count raises `FrameCountDrift`. See `pipeline.render_step`.
  - helpers: `FakeEngine(samples_per_file=60*44100, extra=1, fail=set(), drift=0)`, `make_station(tmp_path, n_packages=3, engine=None) -> tuple[Station, list[str]]`, constants `E`, `NOW`.

- [ ] **Step 1: Write the failing tests**

Append to `tests_transmitter/helpers.py`:

```python
from transmitter import grid as _grid
from transmitter.analysis import FileAnalysis, ShowAnalysis
from transmitter.config import TransmitterConfig
from transmitter.errors import RenderError
from transmitter.render import planned_frames
from transmitter.workspace import Epoch, Workspace

E = 1_800_000_000 * 1_000_000          # an epoch on a whole second (2027-01-15)
NOW = E + 1_000 * _grid.D_US


class FakeEngine:
    """An Engine without ffmpeg: a show's "encode" is fake ADTS frames whose
    payload is '<key>:<i>', so segment contents can be read back."""

    def __init__(self, samples_per_file: int = 60 * 44_100, extra: int = 1,
                 fail: set[str] | None = None, drift: int = 0, pause_seconds: float = 0.75):
        self.samples_per_file = samples_per_file
        self.extra = extra
        self.fail = fail or set()
        self.drift = drift
        self.pause_samples = _grid.samples_for_seconds(pause_seconds)
        self.encoded: list[str] = []
        self.analyzed: list[str] = []

    def analyze(self, show):
        # Computes like production's analyze, but never writes the analysis
        # cache: tests that publish prove the timeline does not depend on it.
        self.analyzed.append(show.slug)
        files = tuple(FileAnalysis(e.path, e.kind, e.title, self.samples_per_file) for e in show.entries)
        return ShowAnalysis(key=show.key, slug=show.slug, files=files, tracks_i_lufs=-20.0,
                            tracks_tp_dbfs=-3.0, meta=dict(show.meta))

    def extra_frames(self):
        return self.extra

    def silent_frame(self):
        return fake_frame("silence", 0)

    def encode_show(self, show, analysis, out_path):
        if show.slug in self.fail:
            raise RenderError(f"{show.slug}: simulated decode failure")
        frames = planned_frames(analysis, self.pause_samples, self.extra) + self.drift
        write_fake_show(out_path, show.key, frames)
        self.encoded.append(show.slug)
        return frames


def make_station(tmp_path: Path, n_packages: int = 3, engine=None):
    from transmitter.pipeline import Station

    root = make_root(tmp_path)
    for i in range(n_packages):
        build_package(root, f"band-2005-11-{i + 1:02d}")
    cfg = TransmitterConfig(root=tmp_path / "tx",
                            station={"root": root, "quiet_minutes": 0},
                            planner={"start_delay_minutes": 0.5},
                            render={"lead_hours": 0.1, "low_water_hours": 0.05})
    logs: list[str] = []
    st = Station(ws=Workspace(cfg.root), cfg=cfg, epoch=Epoch("etest", E),
                 engine=engine or FakeEngine(), log=logs.append)
    return st, logs
```

`tests_transmitter/test_pipeline.py`:

```python
import os
import time

import pytest

from tests_transmitter.helpers import NOW, FakeEngine, make_station, payloads, set_age
from transmitter import grid, pipeline, segment
from transmitter.errors import FrameCountDrift, LayoutError, StationRootError
from transmitter.grid import SEGMENT_FRAMES as F
from transmitter.layout import segment_pieces
from transmitter.planner import read_plan
from transmitter.state import PublishState, save_publish_state

HOUR_US = 3600 * 1_000_000


def test_plan_step_starts_a_run_ahead_of_now(tmp_path):
    st, _ = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    now_n = st.epoch.index_at(NOW)
    assert st.start_margin_segments == 3
    assert rows[0].run_start and rows[0].start_frame == (now_n + 3) * F
    assert rows[-1].end_frame >= st.until_frame(NOW)
    for a, b in zip(rows, rows[1:]):
        assert b.start_frame == a.end_frame + grid.gap_frames(2.0) and not b.run_start
    assert read_plan(st.ws.plan_path) == rows


def test_plan_step_is_idempotent_when_covered(tmp_path):
    st, _ = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    assert pipeline.plan_step(st, NOW) == rows


def test_plan_step_max_new(tmp_path):
    st, _ = make_station(tmp_path)
    assert len(pipeline.plan_step(st, NOW, max_new=1)) == 1


def test_plan_step_refuses_without_marker_and_keeps_plan(tmp_path):
    st, _ = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    (st.cfg.station.root / ".station-root").unlink()
    with pytest.raises(StationRootError):
        pipeline.plan_step(st, NOW + HOUR_US)
    assert read_plan(st.ws.plan_path) == rows


def test_plan_step_recovers_after_an_outage(tmp_path):
    st, logs = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    first_n = rows[0].start_frame // F
    last = first_n + 10
    save_publish_state(st.ws, PublishState(epoch_id="etest", first=first_n, last=last, runs=[[first_n, last]]))
    seg_dir = st.ws.seg_dir("etest")
    seg_dir.mkdir(parents=True)
    stale = seg_dir / f"{last + 1}.aac"
    stale.write_bytes(b"x")
    later = NOW + 3 * HOUR_US
    new_rows = pipeline.plan_step(st, later)
    boundary = (last + 1) * F
    assert new_rows[0].cut_frame == boundary            # the show on air when it stopped
    run = [r for r in new_rows if r.run_start]
    assert run[-1].start_frame == (st.epoch.index_at(later) + 3) * F
    assert all(r.start_frame >= run[-1].start_frame for r in new_rows[1:])
    assert not stale.exists()
    assert any("recovery" in m for m in logs)


def _seg(st, n):
    return segment.parse((st.ws.seg_dir("etest") / f"{n}.aac").read_bytes())


def test_render_step_writes_grid_segments_up_to_the_lead(tmp_path):
    st, _ = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    report = pipeline.render_step(st, NOW)
    first_n = rows[0].start_frame // F
    assert report.written == list(range(first_n, st.epoch.index_at(NOW + st.lead_us) + 1))
    for n in report.written:
        ts, frames = _seg(st, n)
        assert ts == grid.segment_timestamp(n) and len(frames) == F
    assert payloads(_seg(st, first_n)[1])[0] == f"{rows[0].key}:0"


def test_render_step_fills_the_show_gap_with_silence(tmp_path):
    st, _ = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    pipeline.render_step(st, NOW)
    n = rows[0].end_frame // F
    expected: list[str] = []
    for p in segment_pieces(rows, n):
        expected += ["silence:0"] * p.count if p.key is None else [f"{p.key}:{i}" for i in range(p.offset, p.offset + p.count)]
    assert payloads(_seg(st, n)[1]) == expected
    assert "silence:0" in expected


def test_render_step_is_idempotent_and_honours_limit(tmp_path):
    st, _ = make_station(tmp_path)
    pipeline.plan_step(st, NOW)
    first = pipeline.render_step(st, NOW, limit=5)
    assert len(first.written) == 5
    rest = pipeline.render_step(st, NOW)
    assert rest.written[0] == first.written[-1] + 1
    assert pipeline.render_step(st, NOW).written == []


def test_render_step_replans_a_changed_package(tmp_path):
    engine = FakeEngine()
    st, logs = make_station(tmp_path, engine=engine)
    rows = pipeline.plan_step(st, NOW)
    victim = rows[1]
    f = next((st.cfg.station.root / victim.dir / "audio").iterdir())
    f.write_bytes(f.read_bytes() + b"re-voiced")         # file set (and key) change
    set_age(st.cfg.station.root / victim.dir, 3600)
    report = pipeline.render_step(st, NOW)
    assert victim.slug in report.replanned
    new_rows = read_plan(st.ws.plan_path)
    assert new_rows[1].start_frame == victim.start_frame and new_rows[1].slug != victim.slug
    assert victim.slug not in engine.encoded
    assert any("plan-changed" in m for m in logs)


def test_render_step_skips_a_show_that_fails_to_encode(tmp_path):
    st0, _ = make_station(tmp_path / "probe")
    victim = pipeline.plan_step(st0, NOW)[1].slug
    st, logs = make_station(tmp_path / "real", engine=FakeEngine(fail={victim}))
    pipeline.plan_step(st, NOW)
    report = pipeline.render_step(st, NOW)
    assert report.replanned == [victim]
    assert any("render failed" in m for m in logs)


def test_frame_count_drift_is_fatal(tmp_path):
    st, _ = make_station(tmp_path, engine=FakeEngine(drift=1))
    pipeline.plan_step(st, NOW)
    with pytest.raises(FrameCountDrift):
        pipeline.render_step(st, NOW)


def test_render_step_refuses_to_replan_a_show_already_on_air(tmp_path):
    st, _ = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    first_n = rows[0].start_frame // F
    mid_n = rows[1].start_frame // F + 1                    # starts after rows[1] does
    pipeline.render_step(st, NOW, limit=mid_n - first_n)     # stops just before mid_n
    (st.ws.shows_dir / f"{rows[1].key}.aac").unlink()        # its encode is lost
    with pytest.raises(LayoutError, match="already on air"):
        pipeline.render_step(st, NOW)
    assert read_plan(st.ws.plan_path) == rows
    assert not (st.ws.seg_dir("etest") / f"{mid_n}.aac").exists()


def test_render_step_gcs_finished_encodes(tmp_path):
    st, _ = make_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    shows = st.ws.shows_dir
    shows.mkdir(parents=True, exist_ok=True)
    old_tmp, new_tmp = shows / ".k-old.aac.tmp", shows / ".k-new.aac.tmp"
    old_tmp.write_bytes(b"x")
    new_tmp.write_bytes(b"x")
    two_hours_ago = time.time() - 7200
    os.utime(old_tmp, (two_hours_ago, two_hours_ago))
    pipeline.render_step(st, NOW)
    assert not (shows / f"{rows[0].key}.aac").exists()     # fully segmented
    assert (shows / f"{rows[1].key}.aac").exists()         # still needed
    assert not old_tmp.exists() and new_tmp.exists()       # a crashed encode's temp; one in flight
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_pipeline.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'transmitter.pipeline'`.

- [ ] **Step 3: Implement `pipeline.py`**

```python
"""Plan and render steps over the workspace (spec "Lead", "Frozen means
rendered", "Recovery after an outage longer than the lead").

plan_step extends plan.jsonl until it covers now + lead (or starts a fresh
run after an outage); render_step writes segment files
render/seg/<epoch_id>/<N>.aac in ascending N from the next unpublished
segment to now + lead, encoding each show the first time a segment needs it.
Before encoding, a show is re-validated against the current station scan;
a changed or failing show is skipped at its boundary and the plan re-extended
from there. Encoded shows are frozen: their segments are built from the
encode regardless of later package changes.
"""

import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from transmitter import aacenc, analysis as analysis_mod, grid, render, station
from transmitter.analysis import ShowAnalysis
from transmitter.config import TransmitterConfig
from transmitter.errors import FrameCountDrift, LayoutError, TransmitterError
from transmitter.grid import SEGMENT_FRAMES
from transmitter.layout import FrameStore, PlanRow, rows_overlapping
from transmitter.planner import (cut_for_recovery, extend, next_start, publish_next, read_plan,
                                 replan_from, write_plan)
from transmitter.state import load_publish_state
from transmitter.station import Ineligible, Show
from transmitter.workspace import Epoch, Workspace, atomic_write_bytes


class Engine(Protocol):
    def analyze(self, show: Show) -> ShowAnalysis: ...
    def extra_frames(self) -> int: ...
    def silent_frame(self) -> bytes: ...
    def encode_show(self, show: Show, analysis: ShowAnalysis, out_path: Path) -> int: ...


class FfmpegEngine:
    def __init__(self, ws: Workspace, cfg: TransmitterConfig):
        self.ws = ws
        self.settings = render.RenderSettings.from_config(cfg.render)

    def analyze(self, show: Show) -> ShowAnalysis:
        return analysis_mod.load_or_analyze(self.ws.cache_dir, show, self.settings.ffmpeg)

    def extra_frames(self) -> int:
        return aacenc.extra_frames(self.settings.ffmpeg)

    def silent_frame(self) -> bytes:
        return aacenc.silent_frame(self.settings.ffmpeg)

    def encode_show(self, show: Show, analysis: ShowAnalysis, out_path: Path) -> int:
        return render.render_show(show, analysis, out_path, settings=self.settings,
                                  extra=self.extra_frames())


Scanner = Callable[[float], tuple[list[Show], list[Ineligible]]]


@dataclass
class Station:
    ws: Workspace
    cfg: TransmitterConfig
    epoch: Epoch
    engine: Engine
    scan: Scanner | None = None
    log: Callable[[str], None] = print

    def scan_now(self, now_us: int) -> list[Show]:
        """Eligible shows; raises StationRootError when the root is unusable."""
        if self.scan is not None:
            return self.scan(now_us / 1e6)[0]
        return station.scan(self.cfg.station.root, now_s=now_us / 1e6,
                            quiet_s=self.cfg.station.quiet_minutes * 60)[0]

    @property
    def gap_frames(self) -> int:
        return grid.gap_frames(self.cfg.render.show_gap_seconds)

    @property
    def pause_samples(self) -> int:
        return grid.samples_for_seconds(self.cfg.render.clip_pause_seconds)

    @property
    def lead_us(self) -> int:
        return int(self.cfg.render.lead_hours * 3600 * 1_000_000)

    @property
    def start_margin_segments(self) -> int:
        return math.ceil(self.cfg.planner.start_delay_minutes * 60 * 1_000_000 / grid.D_US)

    def until_frame(self, now_us: int) -> int:
        return (self.epoch.index_at(now_us + self.lead_us) + 2) * SEGMENT_FRAMES

    def frames_of(self, show: Show) -> int:
        return render.planned_frames(self.engine.analyze(show), self.pause_samples,
                                     self.engine.extra_frames())

    def extend(self, rows: list[PlanRow], shows: list[Show], now_us: int, *, start_frame: int,
               run_start: bool, max_new: int | None = None) -> list[PlanRow]:
        return extend(rows, shows, frames_of=self.frames_of, seed=self.cfg.planner.seed,
                      gap_frames=self.gap_frames, until_frame=self.until_frame(now_us),
                      start_frame=start_frame, run_start=run_start, max_new=max_new,
                      on_skip=lambda s, e: self.log(f"skipping {s.slug}: {e}"))


def _drop_unpublished_segments(st: Station, last: int | None) -> None:
    seg_dir = st.ws.seg_dir(st.epoch.epoch_id)
    if not seg_dir.is_dir():
        return
    floor = -1 if last is None else last
    for p in seg_dir.glob("*.aac"):
        if p.stem.isdigit() and int(p.stem) > floor:
            p.unlink(missing_ok=True)


def plan_step(st: Station, now_us: int, *, max_new: int | None = None) -> list[PlanRow]:
    shows = st.scan_now(now_us)              # StationRootError: refuse, plan untouched
    rows = read_plan(st.ws.plan_path)
    pub = load_publish_state(st.ws)
    now_n = st.epoch.index_at(now_us)
    fresh = (now_n + st.start_margin_segments) * SEGMENT_FRAMES
    nxt = publish_next(rows, pub.last)
    if nxt is None:
        start, run_start = fresh, True
    elif nxt <= now_n:
        # The next segment to publish is already due: the outage outlasted the
        # lead and listeners are already off the live edge. Start a fresh run.
        rows = cut_for_recovery(rows, pub.last)
        _drop_unpublished_segments(st, pub.last)
        st.log(f"recovery: segment {nxt} was due at index {now_n}; new run at segment "
               f"{fresh // SEGMENT_FRAMES}")
        start, run_start = fresh, True
    else:
        if rows[-1].end_frame >= st.until_frame(now_us):
            return rows
        start, run_start = next_start(rows, st.gap_frames), False
    rows = st.extend(rows, shows, now_us, start_frame=start, run_start=run_start, max_new=max_new)
    write_plan(st.ws.plan_path, rows)
    return rows


@dataclass
class RenderReport:
    written: list[int] = field(default_factory=list)
    replanned: list[str] = field(default_factory=list)
    covered: bool = True


TMP_MAX_AGE_S = 3600


def _gc_encodes(st: Station, rows: list[PlanRow], next_n: int) -> None:
    """Drop encodes no remaining segment needs, and temp files a crashed
    encode left behind (older than an hour, so never one still being written)."""
    keep = {r.key for r in rows if r.end_frame > next_n * SEGMENT_FRAMES}
    if not st.ws.shows_dir.is_dir():
        return
    for p in st.ws.shows_dir.glob("*.aac"):
        if p.stem not in keep:
            p.unlink(missing_ok=True)
    stale = time.time() - TMP_MAX_AGE_S
    for p in st.ws.shows_dir.glob(".*.tmp"):
        try:
            if p.stat().st_mtime < stale:
                p.unlink(missing_ok=True)
        except FileNotFoundError:
            pass


def render_step(st: Station, now_us: int, *, limit: int | None = None) -> RenderReport:
    report = RenderReport()
    rows = read_plan(st.ws.plan_path)
    pub = load_publish_state(st.ws)
    n = publish_next(rows, pub.last)
    if n is None:
        return report
    target = st.epoch.index_at(now_us + st.lead_us)
    seg_dir = st.ws.seg_dir(st.epoch.epoch_id)
    store = FrameStore(st.ws.shows_dir, st.engine.silent_frame())
    shows: dict[str, Show] | None = None
    excluded: set[str] = set()
    while n <= target and (limit is None or len(report.written) < limit):
        path = seg_dir / f"{n}.aac"
        if path.exists():
            n += 1
            continue
        if not rows or (n + 1) * SEGMENT_FRAMES > rows[-1].end_frame:
            report.covered = False
            break
        replanned = False
        for r in rows_overlapping(rows, n * SEGMENT_FRAMES, (n + 1) * SEGMENT_FRAMES):
            if store.has(r.key):
                continue
            if r.start_frame < n * SEGMENT_FRAMES:
                # Its earlier segments are already rendered (frozen); a re-plan
                # here would cut the show mid-air. Alert and let the operator act.
                raise LayoutError(f"{r.slug} is already on air (from frame {r.start_frame}) but its "
                                  f"encode {r.key} is missing; refusing to re-plan into a mid-show cut")
            if shows is None:
                shows = {s.slug: s for s in st.scan_now(now_us)}
            show = shows.get(r.slug)
            reason = None
            if show is None or show.key != r.key:
                reason = "package changed or is no longer eligible"
            else:
                try:
                    frames = st.engine.encode_show(show, st.engine.analyze(show), store.path(r.key))
                    if frames != r.frames:
                        store.path(r.key).unlink(missing_ok=True)
                        raise FrameCountDrift(f"{r.slug}: encoded {frames} frames, plan says {r.frames}")
                except FrameCountDrift:
                    raise
                except TransmitterError as exc:
                    reason = f"render failed: {exc}"
            if reason is not None:
                excluded.add(r.slug)
                kept, start, run_start = replan_from(rows, rows.index(r))
                pool = [s for s in shows.values() if s.slug not in excluded]
                rows = st.extend(kept, pool, now_us, start_frame=start, run_start=run_start)
                write_plan(st.ws.plan_path, rows)
                st.log(f"plan-changed: skipped {r.slug} at frame {r.start_frame} ({reason})")
                report.replanned.append(r.slug)
                replanned = True
                break
        if replanned:
            continue
        atomic_write_bytes(path, store.build_segment(n, rows))
        report.written.append(n)
        n += 1
    _gc_encodes(st, rows, n)
    return report
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_pipeline.py -q`
Expected: PASS.

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q && packages/transmitter/scripts/test-in-debian12.sh`
Expected: PASS both.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): plan and render steps with revalidation, recovery and segment writing"
```

---

### Task 10: Timeline, notes and show-page builders + the show template

**Model hint:** sonnet

**Files:**
- Create: `packages/transmitter/src/transmitter/site.py`
- Create: `antenna/templates/show.html`
- Create: `packages/transmitter/tests_transmitter/test_site.py`

**Interfaces:**
- Consumes: `grid`, `aacenc.ENCODER_PRIMING_SAMPLES`, `render.show_layout`, `analysis.ShowAnalysis`, `layout.PlanRow`, `workspace.Epoch`.
- Produces:
  - `DAY_US`; `row_span_us(row, epoch) -> tuple[int, int]`; `file_starts(row, analysis, pause_samples, epoch) -> list[dict]` (`{kind, title, start}`, start = actual frame position plus encoder priming).
  - `build_timeline(rows, analyses: Mapping[str, ShowAnalysis], epoch, *, now_us, last_n, pause_samples) -> dict` — `{generated_at, epoch_id, shows: [{slug, start, end, artist, date, venue, city, profile, notes, page, files}], recent: [slug…], anchors: []}` covering `[now − 24 h, E + (last_n+1)·d)`.
  - `airtimes(rows, slug, epoch, lo_us, hi_us) -> list[dict]`.
  - `read_package_notes(pkg_dir) -> tuple[dict | None, str | None]` (manifest, briefing text).
  - `build_notes(slug, manifest, briefing, airtimes, meta) -> dict`.
  - `render_show_page(template, notes, *, site_url, station_name) -> str` (`string.Template.safe_substitute`: a stray `$` in the template never raises).
  - `antenna/templates/show.html` placeholders: `$title $station $description $page_url $venue $city_suffix $briefing_html $setlist_html $archive_url $lineage $slug`.

- [ ] **Step 1: Create the template**

`antenna/templates/show.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>$title · $station</title>
<meta property="og:type" content="website">
<meta property="og:site_name" content="$station">
<meta property="og:title" content="$title">
<meta property="og:description" content="$description">
<meta property="og:url" content="$page_url">
<meta name="twitter:card" content="summary">
<link rel="stylesheet" href="../style.css">
</head>
<body>
<main class="show">
<p><a href="../">← $station</a></p>
<h1>$title</h1>
<p class="where">$venue$city_suffix</p>
<section><h2>About this show</h2>
$briefing_html
</section>
<section><h2>Setlist</h2>
$setlist_html
</section>
<section><h2>Source</h2>
<p><a href="$archive_url">$archive_url</a></p>
<p class="lineage">$lineage</p>
</section>
<section><h2>Airtimes</h2>
<ul id="airtimes" data-notes="../notes/$slug.json"><li>Loading…</li></ul>
</section>
</main>
<script>
(async () => {
  const ul = document.getElementById("airtimes");
  const item = (text) => Object.assign(document.createElement("li"), { textContent: text });
  try {
    const notes = await (await fetch(ul.dataset.notes)).json();
    const fmt = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
    const times = (notes.airtimes || []).map((a) => item(fmt.format(new Date(a.start))));
    ul.replaceChildren(...(times.length ? times : [item("Not currently scheduled.")]));
  } catch (e) {
    ul.replaceChildren(item("Airtimes unavailable."));
  }
})();
</script>
</body>
</html>
```

- [ ] **Step 2: Write the failing tests**

`tests_transmitter/test_site.py`:

```python
from pathlib import Path

from tests_transmitter.helpers import build_package, make_root
from transmitter import aacenc, grid, site
from transmitter.analysis import FileAnalysis, ShowAnalysis
from transmitter.layout import PlanRow
from transmitter.workspace import Epoch

EPOCH = Epoch("e1", grid.iso_to_us("2026-10-10T00:00:00Z"))
TEMPLATE = (Path(__file__).resolve().parents[3] / "antenna" / "templates" / "show.html").read_text()
META = {"artist": "Band", "date": "2005-11-01", "venue": "Club", "city": "Lincoln, NE",
        "profile": "indie", "url": "https://archive.org/details/band2005", "lineage": "AUD"}


def _analysis(key):
    files = (FileAnalysis("dj-audio/i.mp3", "clip", "DJ intro (set 1)", 44_100),
             FileAnalysis("audio/01.mp3", "track", "Song 1", 441_000),
             FileAnalysis("dj-audio/o.mp3", "clip", "DJ outro", 44_100))
    return ShowAnalysis(key, f"show-{key}", files, -18.0, -2.0, META)


def _row(seq, key, start_frame, frames=1000, **kw):
    return PlanRow(seq=seq, slug=f"show-{key}", dir=f"show-{key}", key=key, start_frame=start_frame,
                   frames=frames, **kw)


def test_file_starts_follow_actual_frame_positions_plus_encoder_priming():
    row = _row(0, "a", 441 * 10)
    starts = site.file_starts(row, _analysis("a"), 33_075, EPOCH)
    base = 441 * 10 * 1024 + aacenc.ENCODER_PRIMING_SAMPLES
    assert starts[0] == {"kind": "clip", "title": "DJ intro (set 1)",
                         "start": grid.us_to_iso(EPOCH.epoch_us + grid.samples_to_us(base))}
    assert starts[1]["start"] == grid.us_to_iso(EPOCH.epoch_us + grid.samples_to_us(base + 44_100 + 33_075))


def test_file_starts_stop_at_a_cut():
    row = _row(0, "a", 0, frames=1000, cut_frame=40)       # cut after ~0.93 s
    assert [f["title"] for f in site.file_starts(row, _analysis("a"), 33_075, EPOCH)] == ["DJ intro (set 1)"]


def test_timeline_window_and_recent():
    rows = [_row(0, "a", 0), _row(1, "b", 1087), _row(2, "c", 2174)]
    analyses = {k: _analysis(k) for k in "abc"}
    now = EPOCH.epoch_us + grid.frame_to_us(1500)          # inside b
    last_n = 3                                             # published through frame 1764
    tl = site.build_timeline(rows, analyses, EPOCH, now_us=now, last_n=last_n, pause_samples=33_075)
    assert [s["slug"] for s in tl["shows"]] == ["show-a", "show-b"]     # c starts after the horizon
    assert tl["recent"] == ["show-a"]
    assert tl["anchors"] == [] and tl["epoch_id"] == "e1"
    a = tl["shows"][0]
    assert a["start"] == EPOCH.iso and a["notes"] == "notes/show-a.json" and a["page"] == "show/show-a.html"
    assert a["artist"] == "Band"


def test_timeline_skips_rows_without_analysis():
    tl = site.build_timeline([_row(0, "a", 0)], {}, EPOCH, now_us=EPOCH.epoch_us, last_n=5, pause_samples=0)
    assert tl["shows"] == []


def test_airtimes():
    rows = [_row(0, "a", 0), _row(1, "b", 1087), _row(2, "a", 2174)]
    got = site.airtimes(rows, "show-a", EPOCH, EPOCH.epoch_us, EPOCH.epoch_us + 10**12)
    assert [g["start"] for g in got] == [EPOCH.iso, grid.us_to_iso(EPOCH.epoch_us + grid.frame_to_us(2174))]


def test_notes_from_a_package(tmp_path):
    pkg = build_package(make_root(tmp_path))
    manifest, briefing = site.read_package_notes(pkg)
    notes = site.build_notes(pkg.name, manifest, briefing, [], META)
    assert notes["artist"] == "Band" and notes["url"] == "https://archive.org/details/band2005"
    assert notes["setlist"][0] == {"set": "1", "title": "Song 1", "segue": False}
    assert notes["briefing"].startswith("A fine show.")


def test_notes_fall_back_to_cached_meta_when_the_package_is_unreadable(tmp_path):
    assert site.read_package_notes(tmp_path / "gone") == (None, None)
    notes = site.build_notes("s", None, None, [], META)
    assert notes["artist"] == "Band" and notes["setlist"] == [] and notes["briefing"] == ""


def test_show_page_escapes_and_fills_every_placeholder():
    notes = site.build_notes("s", None, "Para <script>alert(1)</script> one.\n\nPara two.", [], META)
    html = site.render_show_page(TEMPLATE, notes, site_url="https://radio.example.org/", station_name="llama radio")
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert '<meta property="og:url" content="https://radio.example.org/show/s.html">' in html
    assert '<meta property="og:title" content="Band — 2005-11-01">' in html
    assert "<p>Para two.</p>" in html
    assert "$" not in html.split("<script>")[0]            # no unfilled placeholder
```

- [ ] **Step 3: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_site.py -q`
Expected: FAIL — `ImportError: cannot import name 'site' from 'transmitter'`.

- [ ] **Step 4: Implement `site.py`**

```python
"""Listener-facing data built by the publisher (spec "R2 object contract"):
timeline.json (shows over [now - 24 h, horizon end] with per-file offsets from
actual frame positions), notes/<slug>.json (llama's briefing, archive.org link,
lineage, setlist, airtimes) and show/<slug>.html rendered from antenna's
template. Phase 4 redesigns the page; the data contract starts here."""

import html
import json
import re
import string
from pathlib import Path
from typing import Mapping, Sequence

from transmitter import aacenc, grid
from transmitter.analysis import ShowAnalysis
from transmitter.layout import PlanRow
from transmitter.render import show_layout
from transmitter.workspace import Epoch

DAY_US = 86_400 * 1_000_000


def row_span_us(row: PlanRow, epoch: Epoch) -> tuple[int, int]:
    return (epoch.epoch_us + grid.frame_to_us(row.start_frame),
            epoch.epoch_us + grid.frame_to_us(row.end_frame))


def file_starts(row: PlanRow, analysis: ShowAnalysis, pause_samples: int, epoch: Epoch) -> list[dict]:
    base = row.start_frame * grid.FRAME_SAMPLES + aacenc.ENCODER_PRIMING_SAMPLES
    limit = row.end_frame * grid.FRAME_SAMPLES
    out = []
    for span in show_layout(analysis, pause_samples).spans:
        pos = base + span.start_sample
        if pos >= limit:
            break
        out.append({"kind": span.kind, "title": span.title,
                    "start": grid.us_to_iso(epoch.epoch_us + grid.samples_to_us(pos))})
    return out


def build_timeline(rows: Sequence[PlanRow], analyses: Mapping[str, ShowAnalysis], epoch: Epoch, *,
                   now_us: int, last_n: int, pause_samples: int) -> dict:
    lo, hi = now_us - DAY_US, epoch.start_us(last_n + 1)
    shows = []
    for row in rows:
        start_us, end_us = row_span_us(row, epoch)
        if end_us <= lo or start_us >= hi:
            continue
        a = analyses.get(row.key)
        if a is None:
            continue
        m = a.meta
        shows.append({
            "slug": row.slug, "start": grid.us_to_iso(start_us), "end": grid.us_to_iso(end_us),
            "artist": m.get("artist"), "date": m.get("date"), "venue": m.get("venue"),
            "city": m.get("city"), "profile": m.get("profile"),
            "notes": f"notes/{row.slug}.json", "page": f"show/{row.slug}.html",
            "files": file_starts(row, a, pause_samples, epoch),
        })
    recent = [s["slug"] for s in reversed(shows) if grid.iso_to_us(s["end"]) <= now_us][:10]
    return {"generated_at": grid.us_to_iso(now_us), "epoch_id": epoch.epoch_id,
            "shows": shows, "recent": recent, "anchors": []}


def airtimes(rows: Sequence[PlanRow], slug: str, epoch: Epoch, lo_us: int, hi_us: int) -> list[dict]:
    out = []
    for row in rows:
        if row.slug != slug:
            continue
        start_us, end_us = row_span_us(row, epoch)
        if end_us > lo_us and start_us < hi_us:
            out.append({"start": grid.us_to_iso(start_us), "end": grid.us_to_iso(end_us)})
    return out


def read_package_notes(pkg_dir: Path) -> tuple[dict | None, str | None]:
    try:
        manifest = json.loads((Path(pkg_dir) / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    if not isinstance(manifest, dict):
        return None, None
    name = Path((manifest.get("briefing") or {}).get("file") or "briefing.md").name
    try:
        briefing = (Path(pkg_dir) / name).read_text(encoding="utf-8")
    except OSError:
        briefing = None
    return manifest, briefing


def build_notes(slug: str, manifest: dict | None, briefing: str | None, airtimes: list[dict],
                meta: Mapping) -> dict:
    manifest = manifest or {}
    show = manifest.get("show") or {}
    source = manifest.get("source") or {}
    tracks = manifest.get("tracks") or []
    return {
        "slug": slug,
        "artist": show.get("artist", meta.get("artist")),
        "date": show.get("date", meta.get("date")),
        "venue": show.get("venue", meta.get("venue")),
        "city": show.get("city", meta.get("city")),
        "profile": source.get("profile", meta.get("profile")),
        "url": source.get("url", meta.get("url")),
        "lineage": source.get("lineage", meta.get("lineage")),
        "briefing": briefing or "",
        "setlist": [{"set": t.get("set"), "title": t.get("title"), "segue": bool(t.get("segue"))}
                    for t in tracks if isinstance(t, dict)],
        "airtimes": airtimes,
    }


def _title(notes: Mapping) -> str:
    return " — ".join(p for p in (notes.get("artist") or notes["slug"], notes.get("date")) if p)


def render_show_page(template: str, notes: Mapping, *, site_url: str | None, station_name: str) -> str:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", notes.get("briefing") or "") if p.strip()]
    briefing_html = "\n".join(f"<p>{html.escape(p)}</p>" for p in paragraphs) or "<p>No notes yet.</p>"
    items = []
    for t in notes.get("setlist", []):
        segue = " &gt;" if t.get("segue") else ""
        items.append(f"<li>{html.escape(t.get('title') or '?')}{segue}"
                     f" <span class=\"set\">{html.escape(str(t.get('set') or ''))}</span></li>")
    setlist_html = f"<ol>{''.join(items)}</ol>" if items else "<p>No setlist.</p>"
    title = _title(notes)
    description = re.sub(r"\s+", " ", paragraphs[0])[:200] if paragraphs else title
    page_url = f"{site_url.rstrip('/')}/show/{notes['slug']}.html" if site_url else ""
    city = notes.get("city")
    values = {
        "title": html.escape(title), "station": html.escape(station_name),
        "description": html.escape(description), "page_url": html.escape(page_url),
        "venue": html.escape(notes.get("venue") or ""),
        "city_suffix": html.escape(f", {city}") if city else "",
        "briefing_html": briefing_html, "setlist_html": setlist_html,
        "archive_url": html.escape(notes.get("url") or ""),
        "lineage": html.escape(notes.get("lineage") or ""),
        "slug": html.escape(notes["slug"]),
    }
    return string.Template(template).safe_substitute(values)
```

- [ ] **Step 5: Run the tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_site.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add antenna/templates packages/transmitter
git commit -m "feat(transmitter): timeline, notes and show-page builders; antenna show template"
```

---

### Task 11: Publisher core — ordering invariant, retry, PUT budget, guard read, flock

**Model hint:** opus

**Files:**
- Create: `packages/transmitter/src/transmitter/r2.py`, `packages/transmitter/src/transmitter/publish.py`
- Create: `packages/transmitter/tests_transmitter/test_r2.py`, `test_publish.py`
- Modify: `packages/transmitter/tests_transmitter/helpers.py` (`FakeBucket`)

**Interfaces:**
- Consumes: `config.PublishConfig/TransmitterConfig`, `workspace.*`, `state.*`, `planner.read_plan/publish_next`, `segment.segment_key`, `site.*`, `analysis.ShowAnalysis`, `layout.PlanRow`, `grid`, `errors.ConfigError/PublishError/PublishLocked/PutBudgetExceeded`.
- Produces:
  - `transmitter.r2.make_client(cfg: PublishConfig)` — boto3 S3 client for R2 (keys from `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY`).
  - `transmitter.publish`: constants `AAC_TYPE, JSON_TYPE, HTML_TYPE, IMMUTABLE, TIMELINE_CACHE, NOTES_CACHE, STATE_CACHE, HORIZON_KEY, GUARD_KEY, TIMELINE_KEY, CONTAINER="adts"`; `PutBudget(path, limit, today=<utc date fn>)` with `.take()`; `Uploader(client, bucket, budget, *, sleep=time.sleep, attempts=4, base_delay_s=1.0)` with `.put(key, body, content_type, cache_control)`, `.get_json(key) -> dict | None`, `.delete(key)`; `guard_blocks_publishing(uploader, ws, now_s, interval_s) -> bool`; `publish_lock(ws)` context manager (non-blocking: raises `PublishLocked` while another holder has it); `Publisher(ws, cfg, epoch, uploader, template, analysis_for, log=print)` where `analysis_for(row: PlanRow) -> ShowAnalysis | None` is injected (Task 14 wires it to the engine's read-or-compute `analyze`, so the timeline never depends on the analysis cache surviving); `horizon_doc(epoch, first, last, now_us, fallback_version) -> dict`; `put_json(uploader, key, doc, cache_control)`; `PublishReport(uploaded, horizon, stopped, error)`; `publish_batch(p, now_us) -> PublishReport` (records the attempted segment range in local `runs` before the first PUT, so prune reaches segments a stopped batch uploaded; a site-step exception of any type is recorded in `report.error` while segments and horizon still advance; an unreadable package never replaces an already-published notes/page).
  - helpers: `FakeBucket` (records `log` of `("put"|"get"|"delete", key)`, `objects`, `fail_puts: dict[key, int]`, `fail_gets: set[key]`; any other attribute access fails the test — no List calls); `make_publisher(tmp_path, bucket, *, batch=360, budget=17_500, sleep=None, rows=None, run_start_n=100, prune_min=1, station_root=None) -> Publisher` (its `analysis_for` serves in-memory analyses; nothing is cached on disk); `write_seg(ws, epoch_id, n)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests_transmitter/helpers.py`:

```python
import io

from botocore.exceptions import ClientError


class FakeBucket:
    """An in-memory R2 bucket speaking the boto3 S3 calls transmitter uses.
    Any other call (list_objects*, delete_objects, …) fails the test."""

    def __init__(self):
        self.objects: dict[str, dict] = {}
        self.log: list[tuple[str, str]] = []
        self.fail_puts: dict[str, int] = {}
        self.fail_gets: set[str] = set()

    def put_object(self, *, Bucket, Key, Body, ContentType, CacheControl):
        self.log.append(("put", Key))
        if self.fail_puts.get(Key, 0) > 0:
            self.fail_puts[Key] -= 1
            raise ClientError({"Error": {"Code": "InternalError", "Message": "boom"}}, "PutObject")
        self.objects[Key] = {"Body": bytes(Body), "ContentType": ContentType, "CacheControl": CacheControl}
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def get_object(self, *, Bucket, Key):
        self.log.append(("get", Key))
        if Key in self.fail_gets:
            raise ClientError({"Error": {"Code": "InternalError", "Message": "boom"}}, "GetObject")
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[Key]["Body"])}

    def delete_object(self, *, Bucket, Key):
        self.log.append(("delete", Key))
        self.objects.pop(Key, None)
        return {"ResponseMetadata": {"HTTPStatusCode": 204}}

    def __getattr__(self, name):
        raise AssertionError(f"unexpected S3 call: {name}")

    def json(self, key):
        return json.loads(self.objects[key]["Body"])

    def puts(self):
        return [k for op, k in self.log if op == "put"]


def write_seg(ws, epoch_id: str, n: int) -> None:
    from transmitter import segment as _segment

    path = ws.seg_dir(epoch_id) / f"{n}.aac"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_segment.assemble(n, [fake_frame("seg", n)] * 441))


TEMPLATE_PATH = Path(__file__).resolve().parents[3] / "antenna" / "templates" / "show.html"


def make_publisher(tmp_path: Path, bucket: "FakeBucket", *, batch: int = 360, budget: int = 17_500,
                   sleep=None, rows=None, run_start_n: int = 100, prune_min: int = 1,
                   station_root: Path | None = None):
    """A Publisher over a workspace holding one planned show (key "k1"),
    starting a run at segment `run_start_n`. Its analyses are served from
    memory by `analysis_for` (none is cached on disk); `p.analyses` holds them."""
    from transmitter import planner, publish
    from transmitter.layout import PlanRow

    cfg = TransmitterConfig(root=tmp_path / "tx", station={"root": station_root},
                            publish={"bucket": "b", "batch_segments": batch, "daily_put_budget": budget,
                                     "prune_min_segments": prune_min})
    ws = Workspace(cfg.root)
    epoch = Epoch("etest", E)
    rows = rows or [PlanRow(seq=0, slug="band-1", dir="band-1", key="k1",
                            start_frame=run_start_n * 441, frames=441 * 50, run_start=True)]
    planner.write_plan(ws.plan_path, rows)
    files = (FileAnalysis("audio/01.mp3", "track", "Song 1", 441 * 1024 * 40),)
    meta = {"artist": "Band", "date": "2005-11-01", "venue": "Club", "city": "Lincoln, NE",
            "profile": "indie", "url": "https://archive.org/details/band1", "lineage": "AUD"}
    analyses = {r.key: ShowAnalysis(r.key, "band-1", files, -18.0, -2.0, meta) for r in rows}
    sleeps = []
    uploader = publish.Uploader(bucket, "b", publish.PutBudget(ws.puts_path, budget, today=lambda: "2027-01-15"),
                                sleep=sleep or sleeps.append)
    p = publish.Publisher(ws=ws, cfg=cfg, epoch=epoch, uploader=uploader,
                          template=TEMPLATE_PATH.read_text(),
                          analysis_for=lambda row: analyses.get(row.key), log=lambda m: None)
    p.sleeps = sleeps
    p.analyses = analyses
    return p
```

`tests_transmitter/test_r2.py`:

```python
import pytest

from transmitter import r2
from transmitter.config import PublishConfig
from transmitter.errors import ConfigError


def test_client_needs_keys(monkeypatch):
    monkeypatch.delenv("R2_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("R2_SECRET_ACCESS_KEY", raising=False)
    with pytest.raises(ConfigError, match="R2_ACCESS_KEY_ID"):
        r2.make_client(PublishConfig(account_id="acct", bucket="b"))


def test_client_endpoint_from_account(monkeypatch):
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "id")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
    client = r2.make_client(PublishConfig(account_id="acct", bucket="b"))
    assert client.meta.endpoint_url == "https://acct.r2.cloudflarestorage.com"
    # one HTTP request per Uploader attempt, so every attempt is counted against the PUT
    # budget (botocore reads a bare `max_attempts: 1` as one *retry*: 2 requests)
    assert client.meta.config.retries["total_max_attempts"] == 1
    override = r2.make_client(PublishConfig(endpoint_url="http://localhost:9000", bucket="b"))
    assert override.meta.endpoint_url == "http://localhost:9000"


def test_client_needs_an_endpoint(monkeypatch):
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "id")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
    with pytest.raises(ConfigError, match="account_id"):
        r2.make_client(PublishConfig(bucket="b"))
```

`tests_transmitter/test_publish.py`:

```python
import json

import pytest

from tests_transmitter.helpers import FakeBucket, make_publisher, write_seg
from transmitter import publish
from transmitter.errors import PublishLocked
from transmitter.segment import segment_key
from transmitter.state import PublishState, load_publish_state, save_publish_state

NOW_US = None  # set per test from the publisher's epoch


def _now(p):
    return p.epoch.start_us(90)


def _segs(p, rng):
    for n in rng:
        write_seg(p.ws, "etest", n)


def test_uploads_segments_then_site_then_horizon(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _segs(p, range(100, 110))
    report = publish.publish_batch(p, _now(p))
    assert report.uploaded == list(range(100, 110)) and report.horizon == (100, 109)
    puts = bucket.puts()
    assert puts[:10] == [segment_key("etest", n) for n in range(100, 110)]
    assert puts[10:] == ["notes/band-1.json", "show/band-1.html", "timeline.json", "state/horizon.json"]
    h = bucket.json("state/horizon.json")
    assert h == {"epoch_id": "etest", "epoch": p.epoch.iso, "d": 10.24, "first": 100, "last": 109,
                 "published_at": h["published_at"], "container": "adts", "fallback_version": None}
    assert not any(p.ws.seg_dir("etest").iterdir())
    assert load_publish_state(p.ws) == PublishState(epoch_id="etest", first=100, last=109, runs=[[100, 109]],
                                                    notes=load_publish_state(p.ws).notes)


def test_cache_headers_and_types(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _segs(p, range(100, 102))
    publish.publish_batch(p, _now(p))
    o = bucket.objects
    assert o[segment_key("etest", 100)]["CacheControl"] == "public, max-age=31536000, immutable"
    assert o[segment_key("etest", 100)]["ContentType"] == "audio/aac"
    assert o["timeline.json"]["CacheControl"] == "public, max-age=30"
    assert o["notes/band-1.json"]["CacheControl"] == "public, max-age=3600"
    assert o["show/band-1.html"]["ContentType"] == "text/html; charset=utf-8"
    assert o["state/horizon.json"]["CacheControl"] == "no-store"


def test_failed_segment_blocks_the_horizon(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _segs(p, range(100, 106))
    bucket.fail_puts[segment_key("etest", 102)] = 99
    report = publish.publish_batch(p, _now(p))
    assert report.uploaded == [100, 101] and report.horizon == (100, 101)
    assert "seg/etest/102.aac" in report.error
    assert bucket.json("state/horizon.json")["last"] == 101
    left = sorted(int(f.stem) for f in p.ws.seg_dir("etest").iterdir())
    assert left == [102, 103, 104, 105]
    assert segment_key("etest", 103) not in bucket.objects          # never past the failure
    bucket.fail_puts.clear()
    assert publish.publish_batch(p, _now(p)).horizon == (100, 105)


def test_retry_with_backoff_and_every_attempt_counts_against_the_budget(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    key = segment_key("etest", 100)
    bucket.fail_puts[key] = 2
    p.uploader.put(key, b"x", publish.AAC_TYPE, publish.IMMUTABLE)
    assert p.sleeps == [1.0, 2.0]
    assert bucket.puts() == [key] * 3
    assert json.loads(p.ws.puts_path.read_text()) == {"day": "2027-01-15", "count": 3}


def test_horizon_failure_keeps_state_and_files_for_the_next_batch(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _segs(p, range(100, 103))
    bucket.fail_puts["state/horizon.json"] = 99
    report = publish.publish_batch(p, _now(p))
    assert report.horizon is None and "horizon" in report.error
    assert load_publish_state(p.ws).last is None
    assert len(list(p.ws.seg_dir("etest").iterdir())) == 3
    bucket.fail_puts.clear()
    assert publish.publish_batch(p, _now(p)).horizon == (100, 102)


def test_put_budget_stops_publishing(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket, budget=5)
    _segs(p, range(100, 110))
    report = publish.publish_batch(p, _now(p))
    assert report.stopped == "put-budget"
    assert len(bucket.puts()) == 5 and "state/horizon.json" not in bucket.objects
    assert publish.publish_batch(p, _now(p)).stopped == "put-budget"
    assert len(bucket.puts()) == 5


def test_the_attempted_range_is_recorded_before_the_first_put(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket, budget=5)
    _segs(p, range(100, 110))
    assert publish.publish_batch(p, _now(p)).stopped == "put-budget"     # 100..104 went up
    state = load_publish_state(p.ws)
    assert state.last is None and state.runs == [[100, 109]]           # prune still reaches them
    p.uploader.budget.limit = 17_500
    assert publish.publish_batch(p, _now(p)).horizon == (100, 109)
    assert load_publish_state(p.ws).runs == [[100, 109]]                # merged, not duplicated


def test_a_site_error_of_any_type_still_advances_the_horizon(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)

    def broken(row):
        raise KeyError("artist")

    p.analysis_for = broken
    _segs(p, range(100, 102))
    report = publish.publish_batch(p, _now(p))
    assert report.horizon == (100, 101) and report.error.startswith("site: ")
    assert bucket.json("state/horizon.json")["last"] == 101
    assert "timeline.json" not in bucket.objects


def test_an_unreadable_package_never_replaces_a_published_page(tmp_path):
    from tests_transmitter.helpers import build_package, make_root

    root = make_root(tmp_path)
    pkg = build_package(root, "band-1")
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket, station_root=root)
    _segs(p, range(100, 101))
    publish.publish_batch(p, _now(p))
    assert bucket.json("notes/band-1.json")["briefing"].startswith("A fine show.")
    (pkg / "manifest.json").unlink()                       # mid-redeliver, or the share is down
    _segs(p, range(101, 102))
    assert publish.publish_batch(p, _now(p)).horizon == (100, 101)
    assert bucket.puts().count("notes/band-1.json") == 1
    assert bucket.json("notes/band-1.json")["briefing"].startswith("A fine show.")


def test_tripped_guard_stops_publishing_and_is_read_at_most_every_15_minutes(tmp_path):
    bucket = FakeBucket()
    bucket.objects["state/guard.json"] = {"Body": json.dumps({"tripped": True, "reason": "spend"}).encode()}
    p = make_publisher(tmp_path, bucket)
    _segs(p, range(100, 102))
    assert publish.publish_batch(p, _now(p)).stopped == "guard"
    assert publish.publish_batch(p, _now(p) + 60_000_000).stopped == "guard"
    assert bucket.log == [("get", "state/guard.json")]
    later = _now(p) + 16 * 60 * 1_000_000
    bucket.objects["state/guard.json"]["Body"] = b'{"tripped": false}'
    assert publish.publish_batch(p, later).uploaded == [100, 101]


def test_absent_guard_is_not_tripped(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _segs(p, range(100, 101))
    assert publish.publish_batch(p, _now(p)).uploaded == [100]


def test_unreadable_guard_fails_closed(tmp_path):
    bucket = FakeBucket()
    bucket.fail_gets.add("state/guard.json")
    p = make_publisher(tmp_path, bucket)
    _segs(p, range(100, 101))
    assert publish.publish_batch(p, _now(p)).stopped == "guard"
    assert bucket.puts() == []


def test_lock_is_exclusive(tmp_path):
    p = make_publisher(tmp_path, FakeBucket())
    with publish.publish_lock(p.ws):
        with pytest.raises(PublishLocked):
            publish.publish_batch(p, _now(p))


def test_a_new_run_starts_the_horizon_at_the_run_start(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket, run_start_n=500)
    save_publish_state(p.ws, PublishState(epoch_id="etest", first=40, last=60, runs=[[40, 60]]))
    _segs(p, range(500, 503))
    report = publish.publish_batch(p, p.epoch.start_us(490))
    assert report.horizon == (500, 502)
    assert load_publish_state(p.ws).runs == [[40, 60], [500, 502]]


def test_notes_are_reuploaded_only_when_they_change(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _segs(p, range(100, 101))
    publish.publish_batch(p, _now(p))
    _segs(p, range(101, 102))
    publish.publish_batch(p, _now(p))
    assert bucket.puts().count("notes/band-1.json") == 1
    assert bucket.puts().count("timeline.json") == 2


def test_nothing_rendered_is_a_quiet_no_op(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    report = publish.publish_batch(p, _now(p))
    assert report.uploaded == [] and bucket.puts() == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_r2.py packages/transmitter/tests_transmitter/test_publish.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'transmitter.r2'` / `transmitter.publish`.

- [ ] **Step 3: Implement `r2.py`**

```python
"""boto3 client for R2's S3 API (spec "Publisher (phase 1)"). Keys come from
the environment (the service's env file); the account id and bucket from
config. botocore's own retries are off -- the Uploader owns retry/backoff so
every attempt is counted against the daily PUT budget -- and checksums are
only sent when an operation requires them."""

import os

from transmitter.config import PublishConfig
from transmitter.errors import ConfigError


def make_client(cfg: PublishConfig):
    import boto3
    from botocore.config import Config

    key = os.environ.get("R2_ACCESS_KEY_ID")
    secret = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not key or not secret:
        raise ConfigError("set R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY (the service's env file)")
    endpoint = cfg.endpoint_url or (
        f"https://{cfg.account_id}.r2.cloudflarestorage.com" if cfg.account_id else None)
    if endpoint is None:
        raise ConfigError("set [publish] account_id (or endpoint_url) in transmitter's config.toml")
    return boto3.client(
        "s3", endpoint_url=endpoint, region_name="auto",
        aws_access_key_id=key, aws_secret_access_key=secret,
        config=Config(retries={"total_max_attempts": 1, "mode": "standard"},
                      request_checksum_calculation="when_required",
                      response_checksum_validation="when_required",
                      connect_timeout=10, read_timeout=60),
    )
```

- [ ] **Step 4: Implement `publish.py`**

```python
"""Publisher (spec "Publisher (phase 1)", "R2 object contract").

Ordering invariant: segments go up in ascending N; state/horizon.json is
rewritten only after every segment it covers returned 200; a show's notes and
page go up before the timeline.json that references them. Presence is the
PUT's 200 -- there are no List calls. Every PUT attempt counts against a local
daily budget; publishing stops while state/guard.json says tripped (absent =
not tripped; unreadable = treated as tripped, i.e. fail closed). Publish and
prune hold a local flock so a manual run cannot race the service; the lock
does not wait, so a manual `publish` while `run` holds it fails with
PublishLocked.
"""

import fcntl
import hashlib
import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Protocol

from transmitter import grid, site
from transmitter.analysis import ShowAnalysis
from transmitter.config import TransmitterConfig
from transmitter.errors import PublishError, PublishLocked, PutBudgetExceeded
from transmitter.layout import PlanRow
from transmitter.planner import publish_next, read_plan
from transmitter.segment import segment_key
from transmitter.state import PublishState, load_fallback_version, load_publish_state, save_publish_state
from transmitter.workspace import Epoch, Workspace, read_json, write_json

AAC_TYPE = "audio/aac"
JSON_TYPE = "application/json"
HTML_TYPE = "text/html; charset=utf-8"
IMMUTABLE = "public, max-age=31536000, immutable"
TIMELINE_CACHE = "public, max-age=30"
NOTES_CACHE = "public, max-age=3600"
STATE_CACHE = "no-store"
HORIZON_KEY = "state/horizon.json"
GUARD_KEY = "state/guard.json"
TIMELINE_KEY = "timeline.json"
CONTAINER = "adts"


class BucketClient(Protocol):
    def put_object(self, **kwargs: Any) -> dict: ...
    def get_object(self, **kwargs: Any) -> dict: ...
    def delete_object(self, **kwargs: Any) -> dict: ...


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class PutBudget:
    """Own-write cap (spec): at most `limit` PUT requests per UTC day."""

    def __init__(self, path: Path, limit: int, today: Callable[[], str] = _utc_today):
        self.path, self.limit, self.today = Path(path), limit, today

    def take(self) -> None:
        data = read_json(self.path, {}) or {}
        day = self.today()
        count = data.get("count", 0) if data.get("day") == day else 0
        if count >= self.limit:
            raise PutBudgetExceeded(f"daily PUT budget of {self.limit} reached for {day} (UTC)")
        write_json(self.path, {"day": day, "count": count + 1})


def _error_code(exc: Exception) -> str | None:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        return response.get("Error", {}).get("Code")
    return None


class Uploader:
    def __init__(self, client: BucketClient, bucket: str, budget: PutBudget, *,
                 sleep: Callable[[float], None] = time.sleep, attempts: int = 4, base_delay_s: float = 1.0):
        self.client, self.bucket, self.budget = client, bucket, budget
        self.sleep, self.attempts, self.base_delay_s = sleep, attempts, base_delay_s

    def put(self, key: str, body: bytes, content_type: str, cache_control: str) -> None:
        last: Exception | None = None
        for attempt in range(self.attempts):
            self.budget.take()                      # every attempt is a billable request
            try:
                resp = self.client.put_object(Bucket=self.bucket, Key=key, Body=body,
                                              ContentType=content_type, CacheControl=cache_control)
                status = resp.get("ResponseMetadata", {}).get("HTTPStatusCode")
                if status == 200:
                    return
                last = PublishError(f"PUT {key}: HTTP {status}")
            except Exception as exc:                # botocore raises many types; all are retryable here
                last = exc
            if attempt + 1 < self.attempts:
                self.sleep(self.base_delay_s * 2 ** attempt)
        raise PublishError(f"PUT {key} failed after {self.attempts} attempts: {last}") from last

    def get_json(self, key: str) -> dict | None:
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if _error_code(exc) in ("NoSuchKey", "404"):
                return None
            raise
        return json.loads(resp["Body"].read())

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            raise PublishError(f"DELETE {key} failed: {exc}") from exc


def guard_blocks_publishing(uploader: Uploader, ws: Workspace, now_s: float, interval_s: float) -> bool:
    cached = read_json(ws.guard_cache_path)
    if cached is not None and now_s - cached["checked_at"] < interval_s:
        return cached["blocked"]
    try:
        doc = uploader.get_json(GUARD_KEY)
        blocked, error = bool(doc and doc.get("tripped")), None
    except Exception as exc:                        # cannot see the guard: do not spend
        blocked, error = True, str(exc)
    write_json(ws.guard_cache_path, {"checked_at": now_s, "blocked": blocked, "error": error})
    return blocked


@contextmanager
def publish_lock(ws: Workspace) -> Iterator[None]:
    ws.root.mkdir(parents=True, exist_ok=True)
    fd = os.open(ws.lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PublishLocked("another transmitter publish or prune holds the lock "
                                "(is `transmitter run` running?); not waiting") from exc
        yield
    finally:
        os.close(fd)


@dataclass
class Publisher:
    ws: Workspace
    cfg: TransmitterConfig
    epoch: Epoch
    uploader: Uploader
    template: str
    # A planned row's analysis, or None. Injected so the timeline does not
    # depend on the analysis cache surviving: production reads-or-computes.
    analysis_for: Callable[[PlanRow], ShowAnalysis | None]
    log: Callable[[str], None] = print


@dataclass
class PublishReport:
    uploaded: list[int] = field(default_factory=list)
    horizon: tuple[int, int] | None = None
    stopped: str | None = None       # "guard" | "put-budget"
    error: str | None = None


def horizon_doc(epoch: Epoch, first: int, last: int, now_us: int, fallback_version: str | None) -> dict:
    return {"epoch_id": epoch.epoch_id, "epoch": epoch.iso, "d": grid.D_US / 1_000_000,
            "first": first, "last": last, "published_at": grid.us_to_iso(now_us),
            "container": CONTAINER, "fallback_version": fallback_version}


def put_json(uploader: Uploader, key: str, doc: dict, cache_control: str) -> None:
    body = (json.dumps(doc, separators=(",", ":"), sort_keys=True) + "\n").encode()
    uploader.put(key, body, JSON_TYPE, cache_control)


def check_epoch(state: PublishState, epoch: Epoch) -> None:
    if state.epoch_id is not None and state.epoch_id != epoch.epoch_id:
        raise PublishError(f"published state belongs to epoch {state.epoch_id}, not {epoch.epoch_id}; "
                           "an epoch change is a deliberate re-render-everything operation")


def _extend_runs(runs: list[list[int]], start: int, last: int) -> list[list[int]]:
    """Add [start, last] to the uploaded-segment runs prune deletes, merging
    with the last run when they touch or overlap (a batch retrying a range
    an earlier, stopped batch already recorded)."""
    runs = [list(r) for r in runs]
    if runs and runs[-1][0] <= start <= runs[-1][1] + 1:
        runs[-1][1] = max(runs[-1][1], last)
    else:
        runs.append([start, last])
    return runs


def _publish_site(p: Publisher, rows: list[PlanRow], last: int, now_us: int, notes: dict[str, str]) -> dict[str, str]:
    pause = grid.samples_for_seconds(p.cfg.render.clip_pause_seconds)
    lo, hi = now_us - site.DAY_US, p.epoch.start_us(last + 1)
    analyses = {}
    for r in rows:                                   # only rows the timeline window can list
        start_us, end_us = site.row_span_us(r, p.epoch)
        if r.key not in analyses and end_us > lo and start_us < hi:
            a = p.analysis_for(r)
            if a is not None:
                analyses[r.key] = a
    timeline = site.build_timeline(rows, analyses, p.epoch, now_us=now_us, last_n=last, pause_samples=pause)
    notes = dict(notes)
    root = p.cfg.station.root
    for show in timeline["shows"]:
        slug = show["slug"]
        row = next(r for r in rows if r.slug == slug and r.key in analyses)
        manifest, briefing = site.read_package_notes(Path(root) / row.dir) if root else (None, None)
        if manifest is None and slug in notes:
            continue                                 # never replace a published page with a degraded one
        doc = site.build_notes(slug, manifest, briefing, site.airtimes(rows, slug, p.epoch, lo, hi),
                               analyses[row.key].meta)
        notes_body = (json.dumps(doc, sort_keys=True) + "\n").encode()
        page = site.render_show_page(p.template, doc, site_url=p.cfg.antenna.site_url,
                                     station_name=p.cfg.antenna.station_name).encode()
        digest = hashlib.sha256(notes_body + b"\0" + page).hexdigest()
        if notes.get(slug) == digest:
            continue
        p.uploader.put(f"notes/{slug}.json", notes_body, JSON_TYPE, NOTES_CACHE)
        p.uploader.put(f"show/{slug}.html", page, HTML_TYPE, NOTES_CACHE)
        notes[slug] = digest
    put_json(p.uploader, TIMELINE_KEY, timeline, TIMELINE_CACHE)
    return notes


def publish_batch(p: Publisher, now_us: int) -> PublishReport:
    report = PublishReport()
    with publish_lock(p.ws):
        if guard_blocks_publishing(p.uploader, p.ws, now_us / 1e6, p.cfg.publish.guard_check_minutes * 60):
            report.stopped = "guard"
            return report
        state = load_publish_state(p.ws)
        check_epoch(state, p.epoch)
        rows = read_plan(p.ws.plan_path)
        nxt = publish_next(rows, state.last)
        if nxt is None:
            return report
        seg_dir = p.ws.seg_dir(p.epoch.epoch_id)
        batch: list[int] = []
        for n in range(nxt, nxt + p.cfg.publish.batch_segments):
            if not (seg_dir / f"{n}.aac").exists():
                break
            batch.append(n)
        if not batch:
            return report
        # Record the range before the first PUT: if this batch stops part-way
        # (budget, horizon failure) and a recovery later abandons the range,
        # prune still deletes whatever of it reached R2.
        runs = _extend_runs(state.runs, nxt, batch[-1])
        if runs != state.runs:
            state.runs = runs
            save_publish_state(p.ws, state)
        uploaded: list[int] = []
        try:
            for n in batch:
                path = seg_dir / f"{n}.aac"
                p.uploader.put(segment_key(p.epoch.epoch_id, n), path.read_bytes(), AAC_TYPE, IMMUTABLE)
                uploaded.append(n)
        except PutBudgetExceeded as exc:
            report.stopped, report.error = "put-budget", str(exc)
        except PublishError as exc:
            report.error = str(exc)
        if not uploaded or report.stopped:
            return report
        continuing = state.last is not None and nxt == state.last + 1 and state.first is not None
        first = state.first if continuing else nxt
        last = uploaded[-1]
        notes = state.notes
        try:
            notes = _publish_site(p, rows, last, now_us, state.notes)
        except PutBudgetExceeded as exc:
            report.stopped, report.error = "put-budget", str(exc)
            return report
        except Exception as exc:                     # segments are fine; the horizon still advances
            p.log(f"site step failed: {exc!r}")
            report.error = f"site: {exc!r}"
        try:
            put_json(p.uploader, HORIZON_KEY,
                     horizon_doc(p.epoch, first, last, now_us, load_fallback_version(p.ws)), STATE_CACHE)
        except PutBudgetExceeded as exc:
            report.stopped, report.error = "put-budget", str(exc)
            return report
        except PublishError as exc:
            report.error = f"horizon: {exc}"
            return report
        save_publish_state(p.ws, PublishState(epoch_id=p.epoch.epoch_id, first=first, last=last,
                                              runs=state.runs, notes=notes))
        for n in uploaded:                           # only now: the horizon and local state agree
            (seg_dir / f"{n}.aac").unlink(missing_ok=True)
        report.uploaded, report.horizon = uploaded, (first, last)
        return report
```

- [ ] **Step 5: Run the tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_r2.py packages/transmitter/tests_transmitter/test_publish.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): R2 publisher with the ordering invariant, retries, PUT budget and guard read"
```

---

### Task 12: Prune

**Model hint:** opus

**Files:**
- Modify: `packages/transmitter/src/transmitter/publish.py` (add `PruneReport`, `prune`)
- Create: `packages/transmitter/tests_transmitter/test_prune.py`

**Interfaces:**
- Consumes: Task 11's `Publisher`, `Uploader.delete`, `put_json`, `horizon_doc`, `guard_blocks_publishing`, `publish_lock`, `check_epoch`, `HORIZON_KEY`, `STATE_CACHE`; `grid.first_segment_at_or_after`.
- Produces: `PruneReport(deleted: int, first: int | None, stopped: str | None, error: str | None)`; `prune(p, now_us) -> PruneReport` — once `E + N·d < now − prune_margin`, and only when at least `prune_min_segments` (default 60) segments are prunable (so the horizon is rewritten at most once per ~10 min, not every tick): rewrites `state/horizon.json` with the advanced `first` **before** deleting, never past `horizon.last` (an outage must not move `last`), then deletes by computed key range (per-key DeleteObject, the documented free operation; never List or DeleteObjects), across every recorded run.

- [ ] **Step 1: Write the failing tests**

`tests_transmitter/test_prune.py`:

```python
from tests_transmitter.helpers import FakeBucket, make_publisher
from transmitter import grid, publish
from transmitter.segment import segment_key
from transmitter.state import PublishState, load_publish_state, save_publish_state

MIN_US = 60 * 1_000_000


def _seed(p, bucket, runs, first, last):
    for lo, hi in runs:
        for n in range(lo, hi + 1):
            bucket.objects[segment_key("etest", n)] = {"Body": b"x", "ContentType": "", "CacheControl": ""}
    save_publish_state(p.ws, PublishState(epoch_id="etest", first=first, last=last, runs=[list(r) for r in runs]))


def test_prune_advances_first_before_deleting_and_keeps_the_margin(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _seed(p, bucket, [(100, 400)], 100, 400)
    now = p.epoch.start_us(300) + 10 * MIN_US           # cutoff = start of segment 300
    report = publish.prune(p, now)
    assert report.first == 300 and report.deleted == 200
    ops = [op for op in bucket.log if op[0] in ("put", "delete")]
    assert ops[0] == ("put", "state/horizon.json")
    assert all(op == "delete" for op, _ in ops[1:])
    assert bucket.json("state/horizon.json")["first"] == 300
    assert bucket.json("state/horizon.json")["last"] == 400
    assert segment_key("etest", 299) not in bucket.objects and segment_key("etest", 300) in bucket.objects
    assert load_publish_state(p.ws).runs == [[300, 400]]


def test_prune_never_moves_past_last(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _seed(p, bucket, [(100, 150)], 100, 150)
    report = publish.prune(p, p.epoch.start_us(10_000))  # long outage
    assert report.first == 151
    h = bucket.json("state/horizon.json")
    assert (h["first"], h["last"]) == (151, 150)        # empty horizon; last unchanged
    assert load_publish_state(p.ws).runs == []


def test_prune_deletes_an_old_run_left_by_a_recovery(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _seed(p, bucket, [(40, 60), (500, 600)], 500, 600)
    report = publish.prune(p, p.epoch.start_us(510) + 10 * MIN_US)
    assert report.deleted == 21 + 10
    assert load_publish_state(p.ws).runs == [[510, 600]]


def test_prune_is_idempotent(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _seed(p, bucket, [(100, 400)], 100, 400)
    now = p.epoch.start_us(300) + 10 * MIN_US
    publish.prune(p, now)
    bucket.log.clear()
    assert publish.prune(p, now).deleted == 0
    assert [op for op, _ in bucket.log if op != "get"] == []


def test_prune_resumes_after_a_failed_delete(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    _seed(p, bucket, [(100, 200)], 100, 200)
    real = bucket.delete_object
    calls = {"n": 0}

    def flaky(**kw):
        calls["n"] += 1
        if calls["n"] == 6:
            raise RuntimeError("network")
        return real(**kw)

    bucket.delete_object = flaky
    report = publish.prune(p, p.epoch.start_us(150) + 10 * MIN_US)
    assert report.error and report.deleted == 5
    assert load_publish_state(p.ws).runs == [[105, 200]]
    bucket.delete_object = real
    assert publish.prune(p, p.epoch.start_us(150) + 10 * MIN_US).deleted == 45


def test_prune_waits_until_enough_segments_are_prunable(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket, prune_min=60)
    _seed(p, bucket, [(100, 400)], 100, 400)
    report = publish.prune(p, p.epoch.start_us(159) + 10 * MIN_US)       # 59 prunable: 100..158
    assert report.deleted == 0 and report.first == 100
    assert [op for op, _ in bucket.log if op in ("put", "delete")] == []    # no horizon write
    assert publish.prune(p, p.epoch.start_us(160) + 10 * MIN_US).deleted == 60


def test_prune_stops_while_the_guard_is_tripped(tmp_path):
    bucket = FakeBucket()
    bucket.objects["state/guard.json"] = {"Body": b'{"tripped": true}', "ContentType": "", "CacheControl": ""}
    p = make_publisher(tmp_path, bucket)
    _seed(p, bucket, [(100, 400)], 100, 400)
    assert publish.prune(p, p.epoch.start_us(300) + 10 * MIN_US).stopped == "guard"
    assert not [op for op, _ in bucket.log if op in ("put", "delete")]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_prune.py -q`
Expected: FAIL — `AttributeError: module 'transmitter.publish' has no attribute 'prune'`.

- [ ] **Step 3: Implement `prune`**

Append to `publish.py`:

```python
@dataclass
class PruneReport:
    deleted: int = 0
    first: int | None = None
    stopped: str | None = None
    error: str | None = None


def prune(p: Publisher, now_us: int) -> PruneReport:
    """Delete segments that started more than `prune_margin` ago (so lagging
    players don't 404): advance horizon.first first, then delete by computed key
    range. Never past horizon.last -- an outage must not move `last`, which the
    clock's off-air rule is measured from."""
    report = PruneReport()
    with publish_lock(p.ws):
        if guard_blocks_publishing(p.uploader, p.ws, now_us / 1e6, p.cfg.publish.guard_check_minutes * 60):
            report.stopped = "guard"
            return report
        state = load_publish_state(p.ws)
        check_epoch(state, p.epoch)
        report.first = state.first
        if state.last is None:
            return report
        cutoff_us = now_us - int(p.cfg.publish.prune_margin_minutes * 60 * 1_000_000)
        n_max = min(grid.first_segment_at_or_after(p.epoch.epoch_us, cutoff_us) - 1, state.last)
        prunable = sum(max(0, min(hi, n_max) - lo + 1) for lo, hi in state.runs)
        if prunable < p.cfg.publish.prune_min_segments:
            return report                    # batch it: each prune costs a horizon PUT
        if state.first is not None and n_max >= state.first:
            try:
                put_json(p.uploader, HORIZON_KEY,
                         horizon_doc(p.epoch, n_max + 1, state.last, now_us, load_fallback_version(p.ws)),
                         STATE_CACHE)
            except (PublishError, PutBudgetExceeded) as exc:
                report.error = f"horizon: {exc}"
                return report
            state.first = n_max + 1
            save_publish_state(p.ws, state)
            report.first = state.first
        remaining: list[list[int]] = []
        failed = False
        for lo, hi in state.runs:
            if failed:
                remaining.append([lo, hi])
                continue
            n = lo
            try:
                while n <= min(hi, n_max):
                    p.uploader.delete(segment_key(p.epoch.epoch_id, n))
                    n += 1
                    report.deleted += 1
            except PublishError as exc:
                report.error, failed = str(exc), True
            if n <= hi:
                remaining.append([n, hi])
        state.runs = remaining
        save_publish_state(p.ws, state)
        return report
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_prune.py packages/transmitter/tests_transmitter/test_publish.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): prune by computed key range after advancing horizon.first"
```

---

### Task 13: Fallback render and upload

**Model hint:** sonnet

**Files:**
- Create: `packages/transmitter/src/transmitter/fallback.py`
- Create: `packages/transmitter/tests_transmitter/test_fallback.py`

**Interfaces:**
- Consumes: `aacenc.encode_pcm`, `adts.split_frames`, `segment.assemble`, `audio.iter_decode/LoudnessMeter`, `analysis.gain_db`, `grid`, Task 11's `Publisher`, `publish_lock`, `guard_blocks_publishing`, `put_json`, `horizon_doc`, `AAC_TYPE/IMMUTABLE/HORIZON_KEY/STATE_CACHE`; `state.*`; `workspace.atomic_write_bytes/write_json`.
- Produces: `FallbackBuild(version: str, segments: tuple[bytes, ...], notice: bytes)` with `.index() -> {"len", "notice", "d"}`; `build_fallback(loop_path, notice_path, *, ffmpeg, music_target_lufs, speech_target_lufs, extra) -> FallbackBuild`; `write_local(ws, build) -> Path`; `upload_fallback(p, build, now_us) -> None` (segments, then notice, then `index.json` last; records the version locally; rewrites `state/horizon.json` with the new `fallback_version` when a horizon exists; refuses while the guard is tripped).

- [ ] **Step 1: Write the failing tests**

`tests_transmitter/test_fallback.py`:

```python
import pytest

from tests_transmitter.helpers import FakeBucket, make_publisher, requires_ffmpeg, stereo_sine, write_mp3
from transmitter import aacenc, adts, fallback, grid, segment
from transmitter.errors import PublishError
from transmitter.state import PublishState, load_fallback_version, save_publish_state
from transmitter.workspace import Workspace


def _build(tmp_path, notice=True):
    write_mp3(tmp_path / "loop.mp3", stereo_sine(25.0, 330.0, 0.2))
    notice_path = None
    if notice:
        write_mp3(tmp_path / "notice.mp3", stereo_sine(14.0, 500.0, 0.1))   # longer than d: truncated
        notice_path = tmp_path / "notice.mp3"
    return fallback.build_fallback(tmp_path / "loop.mp3", notice_path, ffmpeg="ffmpeg",
                                   music_target_lufs=-16.0, speech_target_lufs=-16.0,
                                   extra=aacenc.extra_frames())


@requires_ffmpeg
def test_loop_segments_are_whole_and_timestamped_k_d(tmp_path):
    b = _build(tmp_path)
    assert len(b.segments) == 3                       # ceil((1077 + extra) / 441)
    for k, data in enumerate(b.segments):
        ts, frames = segment.parse(data)
        assert ts == grid.segment_timestamp(k) and len(frames) == grid.SEGMENT_FRAMES
    ts, frames = segment.parse(b.notice)
    assert ts == 0 and len(frames) == grid.SEGMENT_FRAMES
    assert b.index() == {"len": 3, "notice": f"fallback/{b.version}/notice.aac", "d": 10.24}


@requires_ffmpeg
def test_version_is_content_addressed(tmp_path):
    assert _build(tmp_path).version == _build(tmp_path).version
    assert _build(tmp_path, notice=False).version != _build(tmp_path).version


@requires_ffmpeg
def test_write_local(tmp_path):
    b = _build(tmp_path)
    d = fallback.write_local(Workspace(tmp_path / "ws"), b)
    assert d == tmp_path / "ws" / "render" / "fallback" / b.version
    assert sorted(p.name for p in d.iterdir()) == ["0.aac", "1.aac", "2.aac", "index.json", "notice.aac"]


def _fake_build():
    seg = segment.assemble(0, [adts.build_frame(b"x")] * 441)
    return fallback.FallbackBuild("abc123def456", (seg, seg), seg)


def test_upload_order_and_horizon_refresh(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    save_publish_state(p.ws, PublishState(epoch_id="etest", first=100, last=200, runs=[[100, 200]]))
    fallback.upload_fallback(p, _fake_build(), p.epoch.start_us(150))
    assert bucket.puts() == ["fallback/abc123def456/0.aac", "fallback/abc123def456/1.aac",
                             "fallback/abc123def456/notice.aac", "fallback/abc123def456/index.json",
                             "state/horizon.json"]
    assert bucket.objects["fallback/abc123def456/index.json"]["CacheControl"] == "public, max-age=31536000, immutable"
    assert bucket.json("state/horizon.json")["fallback_version"] == "abc123def456"
    assert (bucket.json("state/horizon.json")["first"], bucket.json("state/horizon.json")["last"]) == (100, 200)
    assert load_fallback_version(p.ws) == "abc123def456"


def test_upload_without_a_horizon_only_records_the_version(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    fallback.upload_fallback(p, _fake_build(), p.epoch.start_us(150))
    assert "state/horizon.json" not in bucket.objects
    assert load_fallback_version(p.ws) == "abc123def456"


def test_upload_refuses_while_the_guard_is_tripped(tmp_path):
    bucket = FakeBucket()
    bucket.objects["state/guard.json"] = {"Body": b'{"tripped": true}', "ContentType": "", "CacheControl": ""}
    p = make_publisher(tmp_path, bucket)
    with pytest.raises(PublishError, match="guard"):
        fallback.upload_fallback(p, _fake_build(), p.epoch.start_us(150))
    assert bucket.puts() == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_fallback.py -q`
Expected: FAIL — `ImportError: cannot import name 'fallback'`.

- [ ] **Step 3: Implement `fallback.py`**

```python
"""The fallback loop and the off-air notice (spec "R2 object contract",
"The clock"): `fallback/<version>/<k>.aac` (a short station-ID loop whose
segment k carries timestamp k·d, played as segment N mod len on the grid),
`notice.aac` (one segment) and `index.json` ({len, notice, d}). Rendered once
by `transmitter fallback render`; immutable, never pruned; the version is a
content hash, so re-rendering identical audio is a no-op key-wise."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from transmitter import aacenc, adts, grid, segment
from transmitter.analysis import gain_db
from transmitter.audio import LoudnessMeter, iter_decode
from transmitter.errors import EncodeError, PublishError
from transmitter.grid import CHANNELS, FRAME_SAMPLES, SEGMENT_FRAMES
from transmitter.publish import (AAC_TYPE, HORIZON_KEY, IMMUTABLE, STATE_CACHE, Publisher,
                                 guard_blocks_publishing, horizon_doc, publish_lock, put_json)
from transmitter.state import load_publish_state, save_fallback_version
from transmitter.workspace import Workspace, atomic_write_bytes, write_json


@dataclass(frozen=True)
class FallbackBuild:
    version: str
    segments: tuple[bytes, ...]
    notice: bytes

    def index(self) -> dict:
        return {"len": len(self.segments), "notice": f"fallback/{self.version}/notice.aac",
                "d": grid.D_US / 1_000_000}


def _decode_all(path: Path, ffmpeg: str) -> np.ndarray:
    chunks = list(iter_decode(path, ffmpeg))
    return np.concatenate(chunks) if chunks else np.zeros((0, CHANNELS), np.float32)


def _gained(pcm: np.ndarray, target: float, ffmpeg: str) -> np.ndarray:
    meter = LoudnessMeter(ffmpeg)
    meter.write(pcm)
    loud = meter.finish()
    gain = 10.0 ** (gain_db(target, loud.i_lufs, loud.tp_dbfs) / 20.0)
    return np.clip(pcm * gain, -1.0, 1.0).astype(np.float32)


def _fit(pcm: np.ndarray, samples: int) -> np.ndarray:
    """Truncate (with a 50 ms fade-out) or zero-pad to exactly `samples`."""
    if len(pcm) > samples:
        pcm = pcm[:samples].copy()
        fade = min(samples, grid.samples_for_seconds(0.05))
        if fade:
            pcm[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)[:, None]
        return pcm
    return np.concatenate([pcm, np.zeros((samples - len(pcm), CHANNELS), np.float32)])


def _encode_exact(pcm: np.ndarray, n_frames: int, extra: int, ffmpeg: str) -> list[bytes]:
    frames = adts.split_frames(aacenc.encode_pcm(_fit(pcm, (n_frames - extra) * FRAME_SAMPLES), ffmpeg))
    if len(frames) != n_frames:
        raise EncodeError(f"fallback encode produced {len(frames)} frames, expected {n_frames}")
    return frames


def build_fallback(loop_path: Path, notice_path: Path | None, *, ffmpeg: str,
                   music_target_lufs: float, speech_target_lufs: float, extra: int) -> FallbackBuild:
    loop = _decode_all(loop_path, ffmpeg)
    if len(loop) == 0:
        raise EncodeError(f"{loop_path} decoded to no audio")
    loop = _gained(loop, music_target_lufs, ffmpeg)
    n_segs = max(1, -(-(grid.frames_ceil(len(loop)) + extra) // SEGMENT_FRAMES))
    frames = _encode_exact(loop, n_segs * SEGMENT_FRAMES, extra, ffmpeg)
    segments = tuple(segment.assemble(k, frames[k * SEGMENT_FRAMES:(k + 1) * SEGMENT_FRAMES])
                     for k in range(n_segs))
    notice_pcm = (_gained(_decode_all(notice_path, ffmpeg), speech_target_lufs, ffmpeg)
                  if notice_path is not None else np.zeros((0, CHANNELS), np.float32))
    notice = segment.assemble(0, _encode_exact(notice_pcm, SEGMENT_FRAMES, extra, ffmpeg))
    h = hashlib.sha256()
    for s in segments:
        h.update(s)
    h.update(notice)
    return FallbackBuild(h.hexdigest()[:12], segments, notice)


def write_local(ws: Workspace, build: FallbackBuild) -> Path:
    d = ws.fallback_dir(build.version)
    for k, data in enumerate(build.segments):
        atomic_write_bytes(d / f"{k}.aac", data)
    atomic_write_bytes(d / "notice.aac", build.notice)
    write_json(d / "index.json", build.index())
    return d


def upload_fallback(p: Publisher, build: FallbackBuild, now_us: int) -> None:
    v = build.version
    with publish_lock(p.ws):
        if guard_blocks_publishing(p.uploader, p.ws, now_us / 1e6, p.cfg.publish.guard_check_minutes * 60):
            raise PublishError("the cost guard is tripped (state/guard.json); not uploading")
        for k, data in enumerate(build.segments):
            p.uploader.put(f"fallback/{v}/{k}.aac", data, AAC_TYPE, IMMUTABLE)
        p.uploader.put(f"fallback/{v}/notice.aac", build.notice, AAC_TYPE, IMMUTABLE)
        put_json(p.uploader, f"fallback/{v}/index.json", build.index(), IMMUTABLE)   # last: names the rest
        save_fallback_version(p.ws, v)
        state = load_publish_state(p.ws)
        if state.first is not None and state.last is not None:
            put_json(p.uploader, HORIZON_KEY, horizon_doc(p.epoch, state.first, state.last, now_us, v),
                     STATE_CACHE)
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_fallback.py -q`
Expected: PASS.

Run: `packages/transmitter/scripts/test-in-debian12.sh`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): fallback loop and off-air notice render + upload"
```

---

### Task 14: CLI commands, run loop, status

**Model hint:** sonnet

**Files:**
- Create: `packages/transmitter/src/transmitter/alerts.py`, `packages/transmitter/src/transmitter/service.py`
- Modify: `packages/transmitter/src/transmitter/cli.py`
- Create: `packages/transmitter/tests_transmitter/test_service.py`
- Modify: `packages/transmitter/tests_transmitter/test_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `transmitter.alerts.alert(code: str, message: str) -> None` — phase 1 logs `ALERT <code>: <message>` at ERROR on logger `transmitter.alerts` (phase 2 adds email/ntfy and dedupe behind this call).
  - `transmitter.service`: `now_us()`, `make_engine(ws, cfg)`, `make_client(cfg)` (both module-level so tests monkeypatch them), `open_station(cfg, t_us) -> Station`, `load_template(cfg) -> str`, `row_analysis(st, row) -> ShowAnalysis | None` (the cache if it still holds the row's key, else the engine's `analyze` — which re-caches — on the package when it still has the planned file set), `open_publisher(st) -> Publisher` (wires `analysis_for=lambda row: row_analysis(st, row)`), `publish_all(p, t_us) -> tuple[list[PublishReport], PruneReport]`, `Runner(st, p, *, clock=now_us, sleep=time.sleep, tick_s=60.0)` with `.filling`, `.halted`, `.lead_us(t_us)`, `.tick(t_us)`, `.run(max_ticks=None)` — each tick step (plan, render, publish) catches any `Exception`, logs its traceback, calls `alerts.alert(<step>, …)` and the loop goes on; a `FrameCountDrift` sets the `halted` latch instead (filling stops, one `frame-count-drift` alert, publishing of what exists continues, the loop stays alive until a restart); `status_lines(cfg, t_us) -> list[str]`.
  - CLI: `transmitter plan | render | publish | run [--once] | status | fallback render LOOP [--notice FILE] | config init`, each accepting `--config PATH`.

- [ ] **Step 1: Write the failing tests**

`tests_transmitter/test_service.py`:

```python
import logging

from tests_transmitter.helpers import NOW, TEMPLATE_PATH, FakeBucket, FakeEngine, make_station, write_seg
from transmitter import alerts, grid, pipeline, publish, service
from transmitter.planner import read_plan
from transmitter.segment import segment_key


def _publisher(st, bucket):
    uploader = publish.Uploader(bucket, "b", publish.PutBudget(st.ws.puts_path, 17_500, today=lambda: "d"),
                                sleep=lambda s: None)
    return publish.Publisher(ws=st.ws, cfg=st.cfg, epoch=st.epoch, uploader=uploader,
                             template=TEMPLATE_PATH.read_text(),
                             analysis_for=lambda row: service.row_analysis(st, row), log=lambda m: None)


def test_alert_logs(caplog):
    with caplog.at_level(logging.ERROR, logger="transmitter.alerts"):
        alerts.alert("render", "boom")
    assert "ALERT render: boom" in caplog.text


def test_runner_fills_to_the_lead_then_idles_until_low_water(tmp_path):
    engine = FakeEngine()
    st, _ = make_station(tmp_path, engine=engine)
    bucket = FakeBucket()
    runner = service.Runner(st, _publisher(st, bucket), sleep=lambda s: None)
    for _ in range(5):
        runner.tick(NOW)
        if not runner.filling:
            break
    assert not runner.filling
    assert runner.lead_us(NOW) >= st.lead_us - grid.D_US
    seg_puts = len([k for k in bucket.puts() if k.startswith("seg/")])
    encoded = list(engine.encoded)
    runner.tick(NOW)                                        # lead is full: nothing new
    assert engine.encoded == encoded
    assert len([k for k in bucket.puts() if k.startswith("seg/")]) == seg_puts
    runner.tick(NOW + 200 * 1_000_000)                      # 160 s of lead < 180 s low water
    assert len([k for k in bucket.puts() if k.startswith("seg/")]) > seg_puts


def test_runner_alerts_and_keeps_publishing_when_planning_fails(tmp_path, caplog):
    st, _ = make_station(tmp_path)
    (st.cfg.station.root / ".station-root").unlink()
    runner = service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None)
    with caplog.at_level(logging.ERROR, logger="transmitter.alerts"):
        runner.tick(NOW)
    assert "ALERT plan" in caplog.text and ".station-root" in caplog.text


def test_runner_survives_an_unexpected_error_and_the_next_tick_runs(tmp_path, caplog, monkeypatch):
    st, _ = make_station(tmp_path)
    bucket = FakeBucket()
    runner = service.Runner(st, _publisher(st, bucket), sleep=lambda s: None)
    real = pipeline.render_step
    calls = []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise KeyError("boom")
        return real(*args, **kwargs)

    monkeypatch.setattr(pipeline, "render_step", flaky)
    with caplog.at_level(logging.ERROR):
        runner.tick(NOW)
        runner.tick(NOW)
    assert "ALERT render: KeyError: 'boom'" in caplog.text and "Traceback" in caplog.text
    assert len(calls) == 2
    assert any(k.startswith("seg/") for k in bucket.puts())


def test_frame_count_drift_halts_filling_but_keeps_publishing(tmp_path, caplog):
    engine = FakeEngine(drift=1)
    st, _ = make_station(tmp_path, engine=engine)
    bucket = FakeBucket()
    runner = service.Runner(st, _publisher(st, bucket), sleep=lambda s: None)
    with caplog.at_level(logging.ERROR, logger="transmitter.alerts"):
        runner.tick(NOW)
        assert runner.halted and not runner.filling
        attempts = list(engine.encoded)
        n = read_plan(st.ws.plan_path)[0].start_frame // grid.SEGMENT_FRAMES
        write_seg(st.ws, "etest", n)                       # rendered before the halt
        runner.tick(NOW + 60_000_000)
        runner.tick(NOW + 120_000_000)
    assert caplog.text.count("ALERT frame-count-drift") == 1
    assert engine.encoded == attempts                      # no further render attempts
    assert segment_key("etest", n) in bucket.objects       # publishing went on


def test_run_with_max_ticks_sleeps_between_ticks(tmp_path):
    st, _ = make_station(tmp_path)
    sleeps = []
    clock = iter([NOW, NOW + 60_000_000, NOW + 120_000_000])
    runner = service.Runner(st, _publisher(st, FakeBucket()), clock=lambda: next(clock),
                            sleep=sleeps.append, tick_s=60.0)
    runner.run(max_ticks=3)
    assert len(sleeps) == 2


def test_status_lines(tmp_path):
    st, _ = make_station(tmp_path)
    from transmitter.workspace import write_json
    write_json(st.ws.epoch_path, {"epoch_id": "etest", "epoch": st.epoch.iso, "d": 10.24})
    lines = service.status_lines(st.cfg, NOW)
    assert lines[0].startswith("epoch      etest")
    assert any(l.startswith("published  nothing yet") for l in lines)
    assert any("fallback   none" in l for l in lines)
```

Append to `tests_transmitter/test_cli.py`:

```python
from pathlib import Path

from tests_transmitter.helpers import FakeBucket, FakeEngine, build_package, make_root
from transmitter import service

REPO = Path(__file__).resolve().parents[3]


def _config(tmp_path, root):
    path = tmp_path / "config.toml"
    path.write_text(
        f'[station]\nroot = "{root}"\nquiet_minutes = 0.0\n'
        '[planner]\nstart_delay_minutes = 0.5\n'
        '[render]\nlead_hours = 0.1\nlow_water_hours = 0.05\n'
        '[publish]\nbucket = "b"\n'
        f'[antenna]\ndir = "{REPO / "antenna"}"\n'
    )
    return path


def test_status_before_anything(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path / "tx"))
    result = CliRunner().invoke(app, ["status"])
    assert result.exit_code == 0 and "no epoch yet" in result.output


def test_plan_command(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path / "tx"))
    monkeypatch.setattr(service, "make_engine", lambda ws, cfg: FakeEngine())
    root = make_root(tmp_path)
    build_package(root, "band-2005-11-01")
    result = CliRunner().invoke(app, ["plan", "--config", str(_config(tmp_path, root))])
    assert result.exit_code == 0, result.output
    assert "band-2005-11-01" in result.output
    assert (tmp_path / "tx" / "plan.jsonl").exists()


def test_run_once_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path / "tx"))
    bucket = FakeBucket()
    monkeypatch.setattr(service, "make_engine", lambda ws, cfg: FakeEngine())
    monkeypatch.setattr(service, "make_client", lambda cfg: bucket)
    root = make_root(tmp_path)
    for i in (1, 2):
        build_package(root, f"band-2005-11-0{i}")
    result = CliRunner().invoke(app, ["run", "--once", "--config", str(_config(tmp_path, root))])
    assert result.exit_code == 0, result.output
    keys = set(bucket.objects)
    assert any(k.startswith("seg/") for k in keys)
    assert {"state/horizon.json", "timeline.json"} <= keys
    assert any(k.startswith("notes/") for k in keys) and any(k.startswith("show/") for k in keys)


def test_publish_without_a_bucket_is_a_config_error(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path / "tx"))
    monkeypatch.setattr(service, "make_engine", lambda ws, cfg: FakeEngine())
    root = make_root(tmp_path)
    path = tmp_path / "c.toml"
    path.write_text(f'[station]\nroot = "{root}"\n')
    result = CliRunner().invoke(app, ["publish", "--config", str(path)])
    assert result.exit_code != 0 and "bucket" in str(result.exception)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_service.py packages/transmitter/tests_transmitter/test_cli.py -q`
Expected: FAIL — `ImportError: cannot import name 'alerts'` / `'service'`.

- [ ] **Step 3: Implement `alerts.py` and `service.py`**

`packages/transmitter/src/transmitter/alerts.py`:

```python
"""Alert seam (spec "Alerts and operations", phase 2). Phase 1 logs at ERROR
(journald picks it up under systemd); phase 2 adds SMTP + ntfy channels and
per-condition dedupe in ~/.transmitter/alerts.json behind this same call."""

import logging

log = logging.getLogger("transmitter.alerts")


def alert(code: str, message: str) -> None:
    log.error("ALERT %s: %s", code, message)
```

`packages/transmitter/src/transmitter/service.py`:

```python
"""Wiring for the CLI and the service loop (spec "transmitter -- state and
commands", "Lead"). `run` ticks once a minute: below the low-water mark it
starts filling -- each tick plans at most one more show and renders at most
one publish batch, then publishes -- until the published lead is back at
`lead_hours`; publishing and pruning run every tick. An error in any step is
logged with its traceback and alerted, and the loop goes on; a frame-count
drift halts filling (publishing goes on) until transmitter is restarted."""

import logging
import time
from pathlib import Path
from typing import Callable

from transmitter import alerts, analysis, grid, pipeline, publish, r2, station
from transmitter.analysis import ShowAnalysis
from transmitter.config import TransmitterConfig
from transmitter.errors import ConfigError, FrameCountDrift
from transmitter.layout import PlanRow
from transmitter.planner import read_plan
from transmitter.state import load_fallback_version, load_publish_state
from transmitter.workspace import Workspace, load_epoch, load_or_create_epoch

log = logging.getLogger("transmitter")
MAX_BATCHES = 100


def now_us() -> int:
    return time.time_ns() // 1000


def make_engine(ws: Workspace, cfg: TransmitterConfig) -> pipeline.Engine:
    return pipeline.FfmpegEngine(ws, cfg)


def make_client(cfg: TransmitterConfig):
    return r2.make_client(cfg.publish)


def open_station(cfg: TransmitterConfig, t_us: int) -> pipeline.Station:
    ws = Workspace(cfg.root)
    return pipeline.Station(ws=ws, cfg=cfg, epoch=load_or_create_epoch(ws, t_us),
                            engine=make_engine(ws, cfg), log=log.info)


def load_template(cfg: TransmitterConfig) -> str:
    if cfg.antenna.dir is None:
        raise ConfigError("set [antenna] dir to the repo's antenna/ directory "
                          "(show pages are rendered from antenna/templates/show.html)")
    path = Path(cfg.antenna.dir) / "templates" / "show.html"
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read the show-page template {path}: {exc}") from exc


def row_analysis(st: pipeline.Station, row: PlanRow) -> ShowAnalysis | None:
    """A planned row's analysis for the timeline: the cache if it still holds
    the row's key, else the engine's analyze (which re-caches) on the package,
    when the package still has the file set the row was planned from."""
    cached = analysis.load_cached(st.ws.cache_dir, row.key)
    if cached is not None:
        return cached
    root = st.cfg.station.root
    if root is None:
        return None
    show = station.evaluate(Path(root) / row.dir, now_s=time.time(), quiet_s=0)
    if not isinstance(show, station.Show) or show.key != row.key:
        return None
    return st.engine.analyze(show)


def open_publisher(st: pipeline.Station) -> publish.Publisher:
    cfg = st.cfg
    if not cfg.publish.bucket:
        raise ConfigError("set [publish] bucket in transmitter's config.toml")
    budget = publish.PutBudget(st.ws.puts_path, cfg.publish.daily_put_budget)
    uploader = publish.Uploader(make_client(cfg), cfg.publish.bucket, budget)
    return publish.Publisher(ws=st.ws, cfg=cfg, epoch=st.epoch, uploader=uploader,
                             template=load_template(cfg),
                             analysis_for=lambda row: row_analysis(st, row), log=log.info)


def publish_all(p: publish.Publisher, t_us: int) -> tuple[list[publish.PublishReport], publish.PruneReport]:
    reports = []
    for _ in range(MAX_BATCHES):
        r = publish.publish_batch(p, t_us)
        reports.append(r)
        if r.stopped == "put-budget":
            alerts.alert("put-budget", r.error or "daily PUT budget exceeded; publishing stopped")
        elif r.stopped == "guard":
            log.info("publishing paused: state/guard.json says tripped (or is unreadable)")
        elif r.error:
            alerts.alert("publish", r.error)
        if not r.uploaded or r.stopped or r.error:
            break
    pr = publish.prune(p, t_us)
    if pr.error:
        alerts.alert("prune", pr.error)
    return reports, pr


class Runner:
    def __init__(self, st: pipeline.Station, p: publish.Publisher, *, clock: Callable[[], int] = now_us,
                 sleep: Callable[[float], None] = time.sleep, tick_s: float = 60.0):
        self.st, self.p, self.clock, self.sleep, self.tick_s = st, p, clock, sleep, tick_s
        self.filling = False
        self.halted = False          # latched by a frame-count drift; cleared by a restart

    def lead_us(self, t_us: int) -> int | None:
        last = load_publish_state(self.st.ws).last
        return None if last is None else self.st.epoch.start_us(last + 1) - t_us

    def _step(self, name: str, fn: Callable[[], object]) -> None:
        """Run one step; no error ends the loop (the next tick retries)."""
        try:
            fn()
        except FrameCountDrift as exc:
            # The encoder no longer matches the frame-count model: stop filling
            # rather than render more of a timeline that may be wrong.
            self.halted, self.filling = True, False
            log.error("%s step: frame-count drift; filling halted", name, exc_info=True)
            alerts.alert("frame-count-drift", f"{exc}; filling halted (publishing continues) "
                                              "until transmitter is restarted")
        except Exception as exc:
            log.exception("%s step failed", name)
            alerts.alert(name, f"{type(exc).__name__}: {exc}")

    def tick(self, t_us: int) -> None:
        low_water_us = int(self.st.cfg.render.low_water_hours * 3600 * 1_000_000)
        lead = self.lead_us(t_us)
        if not self.halted and (lead is None or lead < low_water_us):
            self.filling = True
        if self.filling:
            self._step("plan", lambda: pipeline.plan_step(self.st, t_us, max_new=1))
            self._step("render", lambda: pipeline.render_step(
                self.st, t_us, limit=self.st.cfg.publish.batch_segments))
        self._step("publish", lambda: publish_all(self.p, t_us))
        lead = self.lead_us(t_us)
        if lead is not None and lead >= self.st.lead_us - grid.D_US:
            self.filling = False

    def run(self, max_ticks: int | None = None) -> None:
        ticks = 0
        while max_ticks is None or ticks < max_ticks:
            started = time.monotonic()
            self.tick(self.clock())
            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                break
            self.sleep(max(0.0, self.tick_s - (time.monotonic() - started)))


def status_lines(cfg: TransmitterConfig, t_us: int) -> list[str]:
    ws = Workspace(cfg.root)
    epoch = load_epoch(ws)
    if epoch is None:
        return ["no epoch yet - run `transmitter plan` (or `transmitter run`) first"]
    rows = read_plan(ws.plan_path)
    pub = load_publish_state(ws)
    fb = load_fallback_version(ws)
    lines = [f"epoch      {epoch.epoch_id} ({epoch.iso})"]
    if rows:
        end_us = epoch.epoch_us + grid.frame_to_us(rows[-1].end_frame)
        lines.append(f"plan       {len(rows)} rows through {grid.us_to_iso(end_us)}")
        now_frame = (t_us - epoch.epoch_us) * grid.SAMPLE_RATE // (grid.FRAME_SAMPLES * 1_000_000)
        on = next((r for r in rows if r.start_frame <= now_frame < r.end_frame), None)
        lines.append(f"on air     {on.slug}" if on else "on air     (between shows, or not started)")
    else:
        lines.append("plan       empty")
    if pub.last is None:
        lines.append("published  nothing yet")
    else:
        lead_h = (epoch.start_us(pub.last + 1) - t_us) / 3_600_000_000
        lines.append(f"published  segments {pub.first}..{pub.last}; lead {lead_h:.1f} h")
    lines.append(f"fallback   {fb}" if fb else "fallback   none (run `transmitter fallback render`)")
    return lines
```

- [ ] **Step 4: Wire the CLI commands**

In `cli.py`, add imports at the top:

```python
import logging

from transmitter import aacenc, fallback, grid, pipeline, service
from transmitter.config import load_config
```

and these commands after `config_init`:

```python
CONFIG_OPT = typer.Option(None, "--config", help="Config file (default: $TRANSMITTER_ROOT or "
                                                 "~/.transmitter, then /config.toml)")

fallback_app = typer.Typer(help="The fallback loop and off-air notice", pretty_exceptions_enable=False)
app.add_typer(fallback_app, name="fallback")


@app.command()
def plan(config: Path = CONFIG_OPT):
    """Extend the plan to cover now + lead (phase 1: fixed shuffled order)."""
    cfg = load_config(config)
    t = service.now_us()
    st = service.open_station(cfg, t)
    rows = pipeline.plan_step(st, t)
    for r in rows[-10:]:
        typer.echo(f"{grid.us_to_iso(st.epoch.epoch_us + grid.frame_to_us(r.start_frame))}  {r.slug}")


@app.command()
def render(config: Path = CONFIG_OPT):
    """Plan, then render segments up to now + lead."""
    cfg = load_config(config)
    t = service.now_us()
    st = service.open_station(cfg, t)
    pipeline.plan_step(st, t)
    report = pipeline.render_step(st, t)
    extra = f"; re-planned around {', '.join(report.replanned)}" if report.replanned else ""
    typer.echo(f"wrote {len(report.written)} segment(s){extra}")


@app.command("publish")
def publish_cmd(config: Path = CONFIG_OPT):
    """Upload rendered segments, timeline and show pages; then prune."""
    cfg = load_config(config)
    t = service.now_us()
    st = service.open_station(cfg, t)
    reports, pruned = service.publish_all(service.open_publisher(st), t)
    typer.echo(f"uploaded {sum(len(r.uploaded) for r in reports)} segment(s); pruned {pruned.deleted}")


@app.command()
def run(config: Path = CONFIG_OPT,
        once: bool = typer.Option(False, "--once", help="Run one tick and exit")):
    """The service loop: plan/render below low water, publish and prune every minute."""
    cfg = load_config(config)
    t = service.now_us()
    st = service.open_station(cfg, t)
    service.Runner(st, service.open_publisher(st)).run(max_ticks=1 if once else None)


@app.command()
def status(config: Path = CONFIG_OPT):
    """Epoch, plan, what is on air, published lead, fallback version."""
    for line in service.status_lines(load_config(config), service.now_us()):
        typer.echo(line)


@fallback_app.command("render")
def fallback_render(
    loop: Path = typer.Argument(..., exists=True, dir_okay=False, help="Station-ID loop audio"),
    notice: Path = typer.Option(None, "--notice", exists=True, dir_okay=False,
                                help="Off-air notice audio (default: silence)"),
    config: Path = CONFIG_OPT,
):
    """Render the fallback loop + off-air notice and upload them (immutable)."""
    cfg = load_config(config)
    t = service.now_us()
    st = service.open_station(cfg, t)
    p = service.open_publisher(st)
    build = fallback.build_fallback(loop, notice, ffmpeg=cfg.render.ffmpeg,
                                    music_target_lufs=cfg.render.music_target_lufs,
                                    speech_target_lufs=cfg.render.speech_target_lufs,
                                    extra=aacenc.extra_frames(cfg.render.ffmpeg))
    fallback.write_local(st.ws, build)
    fallback.upload_fallback(p, build, t)
    typer.echo(f"fallback {build.version}: {len(build.segments)} segment(s) + notice uploaded")
```

In `main_cli`, configure logging before `app()`:

```python
def main_cli() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        app()
    ...  # unchanged
```

- [ ] **Step 5: Run the tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Expected: PASS.

Run: `./.venv/bin/python -m pytest -q && packages/transmitter/scripts/test-in-debian12.sh`
Expected: PASS both.

- [ ] **Step 6: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): plan/render/publish/run/status/fallback commands and the service loop"
```

---

### Task 15: antenna scaffold and the playlist builder

**Model hint:** opus

**Files:**
- Create: `antenna/package.json` (+ `package-lock.json` from npm), `antenna/tsconfig.json`, `antenna/wrangler.jsonc`, `antenna/vitest.config.ts`, `antenna/worker-configuration.d.ts` (generated)
- Create: `antenna/src/grid.ts`, `antenna/src/playlist.ts`, `antenna/src/index.ts` (placeholder; Task 16 fills it)
- Create: `antenna/test/playlist.test.ts`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: the `state/horizon.json` and `fallback/<v>/index.json` documents transmitter writes (Tasks 11, 13): `{epoch_id, epoch, d, first, last, published_at, container, fallback_version}` and `{len, notice, d}`.
- Produces (`src/grid.ts`): `interface Horizon`; `interface Grid { epochMs; dMs }`; `gridOf(h) -> Grid`; `indexAt(g, nowMs)`; `startMs(g, n)`; `isoAt(g, n)`.
- Produces (`src/playlist.ts`): `interface FallbackIndex { len; notice }`; `interface PlaylistConfig { window; grace; offairAfterMs }`; `interface PlaylistInputs { nowMs; horizon; fallback; offair; offairSeqMs? }`; `type Entry`; `isOffair(inputs, cfg)`; `windowEntries(cur, horizon, cfg)`; `offairPlaylist(fallback, g, seqMs)` (`EXT-X-MEDIA-SEQUENCE = indexAt(g, seqMs)`; the clock passes `scheduledTime + loopMs`, so it is constant within an invocation and never decreases); `buildPlaylist(inputs, cfg) -> string | null` (null = nothing safe to list; the caller writes nothing).

- [ ] **Step 1: Scaffold the project**

```bash
mkdir -p antenna/src antenna/test && cd antenna
cat > package.json <<'JSON'
{
  "name": "antenna",
  "private": true,
  "type": "module",
  "engines": { "node": ">=22" },
  "scripts": {
    "test": "vitest run",
    "typecheck": "tsc --noEmit",
    "types": "wrangler types",
    "deploy": "wrangler deploy",
    "deploy:assets": "node scripts/deploy-assets.mjs"
  }
}
JSON
npm install --save-dev wrangler@4 vitest@5 @cloudflare/vitest-plugin@1 typescript@5
```

(`@cloudflare/vitest-plugin` is the current name of `@cloudflare/vitest-pool-workers`, which npm now marks deprecated; it supports vitest `^4.1 || ^5`.)

`antenna/wrangler.jsonc`:

```jsonc
{
  "$schema": "node_modules/wrangler/config-schema.json",
  "name": "antenna",
  "main": "src/index.ts",
  "compatibility_date": "2026-10-01",
  // Cron-only: no routes, no fetch handler, and no public URL. A routeless
  // Worker otherwise gets a public, billed *.workers.dev URL that the zone's
  // WAF kill switch cannot reach (spec "Architecture").
  "workers_dev": false,
  "preview_urls": false,
  "triggers": { "crons": ["* * * * *"] },
  // The bucket name must match transmitter's [publish] bucket.
  "r2_buckets": [{ "binding": "BUCKET", "bucket_name": "llama-radio" }],
  "vars": {
    "PLAYLIST_WINDOW": "6",
    "GRACE_SEGMENTS": "3",
    "OFFAIR_AFTER_SECONDS": "86400",
    "LOOP_SECONDS": "75",
    "LIVE_MAX_AGE": "5"
  },
  // One log line per invocation (~1,440/day) stays inside the free allowance.
  "observability": { "enabled": true }
}
```

`antenna/vitest.config.ts`:

```ts
import { cloudflareTest } from "@cloudflare/vitest-plugin";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [cloudflareTest({ wrangler: { configPath: "./wrangler.jsonc" } })],
});
```

(If the installed plugin's export differs, `node_modules/@cloudflare/vitest-plugin/dist/pool/index.d.mts` declares it; version 1.4.0 exports `cloudflareTest(options) => Vite.Plugin` with `options.wrangler.configPath`.)

`antenna/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "es2022",
    "module": "es2022",
    "moduleResolution": "bundler",
    "lib": ["es2022"],
    "strict": true,
    "noEmit": true,
    "skipLibCheck": true,
    "isolatedModules": true,
    "allowJs": true,
    "checkJs": false,
    "types": ["@cloudflare/vitest-plugin/types"]
  },
  "include": ["src", "test", "public", "worker-configuration.d.ts"]
}
```

`antenna/src/index.ts` (placeholder so wrangler and the test pool have a `main`):

```ts
export default {
  async scheduled(): Promise<void> {},
} satisfies ExportedHandler<Env>;
```

```bash
npx wrangler types            # writes worker-configuration.d.ts (Env with BUCKET + vars)
cd ..
```

Append to `.gitignore`:

```
antenna/node_modules/
antenna/.wrangler/
```

- [ ] **Step 2: Write the failing tests**

`antenna/test/playlist.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { Horizon } from "../src/grid";
import { buildPlaylist, type FallbackIndex, type PlaylistConfig } from "../src/playlist";

const E = Date.parse("2026-10-10T12:00:00.000Z");
const D = 10_240;
const CFG: PlaylistConfig = { window: 6, grace: 3, offairAfterMs: 24 * 3600 * 1000 };
const FB: FallbackIndex = { len: 7, notice: "fallback/v1/notice.aac" };

function horizon(first: number, last: number, extra: Partial<Horizon> = {}): Horizon {
  const iso = new Date(E).toISOString();
  return { epoch_id: "e1", epoch: iso, d: 10.24, first, last, published_at: iso,
           container: "adts", fallback_version: "v1", ...extra };
}

const at = (n: number) => E + n * D + 1; // just after segment n starts

function entries(pl: string): { uri: string; disc: number; pdt: string }[] {
  const lines = pl.trim().split("\n");
  const seqLine = lines.find((l) => l.startsWith("#EXT-X-DISCONTINUITY-SEQUENCE:"));
  let disc = seqLine ? Number(seqLine.split(":")[1]) : 0;
  let pdt = "";
  const out: { uri: string; disc: number; pdt: string }[] = [];
  for (const l of lines) {
    if (l === "#EXT-X-DISCONTINUITY") disc++;
    else if (l.startsWith("#EXT-X-PROGRAM-DATE-TIME:")) pdt = l.slice("#EXT-X-PROGRAM-DATE-TIME:".length);
    else if (!l.startsWith("#")) out.push({ uri: l, disc, pdt });
  }
  return out;
}

const mediaSequence = (pl: string) => Number(/#EXT-X-MEDIA-SEQUENCE:(\d+)/.exec(pl)![1]);
const live = (ns: number[]) => ns.map((n) => `seg/e1/${n}.aac`);
const loop = (ns: number[]) => ns.map((n) => `fallback/v1/${n % 7}.aac`);

describe("buildPlaylist", () => {
  it("lists the last six live segments ending at the current index", () => {
    const pl = buildPlaylist({ nowMs: at(1000), horizon: horizon(0, 5000), fallback: FB, offair: false }, CFG)!;
    const es = entries(pl);
    expect(es.map((e) => e.uri)).toEqual(live([995, 996, 997, 998, 999, 1000]));
    expect(mediaSequence(pl)).toBe(995);
    expect(es[0].pdt).toBe(new Date(E + 995 * D).toISOString());
    expect(pl).toContain("#EXT-X-TARGETDURATION:11\n");
    expect(pl).toContain("#EXTINF:10.240,\n");
    expect(pl).not.toContain("#EXT-X-DISCONTINUITY\n");
    expect(pl).not.toContain("ENDLIST");
  });

  it("holds at horizon.last for up to three segments (a publish retry is not an outage)", () => {
    for (const behind of [1, 2, 3]) {
      const pl = buildPlaylist({ nowMs: at(100 + behind), horizon: horizon(0, 100), fallback: FB, offair: false }, CFG)!;
      expect(entries(pl).at(-1)!.uri).toBe("seg/e1/100.aac");
      expect(mediaSequence(pl)).toBe(95);
    }
  });

  it("switches to the fallback loop beyond grace, with a discontinuity at the switch", () => {
    const pl = buildPlaylist({ nowMs: at(104), horizon: horizon(0, 100), fallback: FB, offair: false }, CFG)!;
    const es = entries(pl);
    expect(es.map((e) => e.uri)).toEqual([...live([99, 100]), ...loop([101, 102, 103, 104])]);
    const lines = pl.split("\n");
    expect(lines[lines.indexOf("fallback/v1/3.aac") - 3]).toBe("#EXT-X-DISCONTINUITY");
    expect(es[2].disc).toBe(Math.floor(101 / 7));
  });

  it("treats N < horizon.first as absent", () => {
    const pl = buildPlaylist({ nowMs: at(102), horizon: horizon(100, 200), fallback: FB, offair: false }, CFG)!;
    expect(entries(pl).map((e) => e.uri)).toEqual([...loop([97, 98, 99]), ...live([100, 101, 102])]);
  });

  it("an empty horizon (first = last + 1) lists fallback", () => {
    for (const cur of [150, 152, 160]) {
      const pl = buildPlaylist({ nowMs: at(cur), horizon: horizon(151, 150), fallback: FB, offair: false }, CFG)!;
      const es = entries(pl);
      expect(es).toHaveLength(6);
      expect(es.every((e) => e.uri.startsWith("fallback/v1/"))).toBe(true);
    }
  });

  it("numbers every fallback segment floor(N/len), consistently across successive playlists", () => {
    const seen = new Map<number, number>();
    for (let cur = 1000; cur <= 1016; cur++) {
      const pl = buildPlaylist({ nowMs: at(cur), horizon: horizon(0, 10), fallback: FB, offair: false }, CFG)!;
      const ms = mediaSequence(pl);
      const es = entries(pl);
      es.forEach((e, i) => {
        const n = ms + i;
        expect(e.uri).toBe(`fallback/v1/${n % 7}.aac`);
        expect(e.disc).toBe(Math.floor(n / 7));
        if (seen.has(n)) expect(seen.get(n)).toBe(e.disc);
        seen.set(n, e.disc);
      });
      const tags = pl.split("\n").filter((l) => l === "#EXT-X-DISCONTINUITY").length;
      expect(tags).toBe(es.filter((_, i) => (ms + i) % 7 === 0).length);
    }
  });

  it("goes off-air with the notice and ENDLIST when state/offair.json says so", () => {
    const pl = buildPlaylist({ nowMs: at(1000), horizon: horizon(0, 5000), fallback: FB, offair: true }, CFG)!;
    expect(entries(pl).map((e) => e.uri)).toEqual(["fallback/v1/notice.aac"]);
    expect(pl.trimEnd().endsWith("#EXT-X-ENDLIST")).toBe(true);
    expect(mediaSequence(pl)).toBe(1000);
  });

  it("numbers the off-air playlist from offairSeqMs: constant within an invocation, never below live", () => {
    const seqMs = at(1000) + 75_000; // what the clock passes: scheduledTime + loopMs
    const off = (nowMs: number) =>
      buildPlaylist({ nowMs, horizon: horizon(0, 5000), fallback: FB, offair: true, offairSeqMs: seqMs }, CFG)!;
    expect(off(at(1001))).toBe(off(at(1000))); // identical bytes: the clock's skip makes it one PUT
    expect(mediaSequence(off(at(1000)))).toBe(1007);
    for (const cur of [10, 1000, 4999]) {
      const nowMs = at(cur);
      const livePl = buildPlaylist({ nowMs, horizon: horizon(0, 5000), fallback: FB, offair: false }, CFG)!;
      for (const offairSeqMs of [undefined, nowMs + 75_000]) {
        const offPl = buildPlaylist({ nowMs, horizon: horizon(0, 5000), fallback: FB, offair: true, offairSeqMs }, CFG)!;
        expect(mediaSequence(offPl)).toBeGreaterThanOrEqual(mediaSequence(livePl));
      }
    }
  });

  it("goes off-air offair_after past the end of the published horizon", () => {
    const end = E + 101 * D;
    const inputs = { horizon: horizon(0, 100), fallback: FB, offair: false };
    expect(buildPlaylist({ ...inputs, nowMs: end + CFG.offairAfterMs }, CFG)).not.toContain("ENDLIST");
    expect(buildPlaylist({ ...inputs, nowMs: end + CFG.offairAfterMs + 1 }, CFG)).toContain("#EXT-X-ENDLIST");
  });

  it("returns null rather than list a segment that does not exist", () => {
    expect(buildPlaylist({ nowMs: at(104), horizon: horizon(0, 100), fallback: null, offair: false }, CFG)).toBeNull();
    expect(buildPlaylist({ nowMs: at(104), horizon: horizon(0, 100, { fallback_version: null }), fallback: FB, offair: false }, CFG)).toBeNull();
    expect(buildPlaylist({ nowMs: at(1000), horizon: horizon(0, 5000), fallback: null, offair: true }, CFG)).toBeNull();
    expect(buildPlaylist({ nowMs: at(50), horizon: horizon(0, 100), fallback: null, offair: false }, CFG)).not.toBeNull();
  });

  it("returns null before the epoch", () => {
    expect(buildPlaylist({ nowMs: E - 1, horizon: horizon(0, 10), fallback: FB, offair: false }, CFG)).toBeNull();
  });

  it("namespaces live keys by epoch", () => {
    const pl = buildPlaylist({ nowMs: at(10), horizon: horizon(0, 100, { epoch_id: "e2" }), fallback: FB, offair: false }, CFG)!;
    expect(pl).toContain("seg/e2/10.aac");
    expect(mediaSequence(pl)).toBe(5);
  });
});
```

- [ ] **Step 3: Run them to verify they fail**

Run: `cd antenna && npx vitest run test/playlist.test.ts`
Expected: FAIL — cannot resolve `../src/playlist`.

- [ ] **Step 4: Implement `grid.ts` and `playlist.ts`**

`antenna/src/grid.ts`:

```ts
/** state/horizon.json as transmitter writes it (spec "R2 object contract"). */
export interface Horizon {
  epoch_id: string;
  epoch: string; // ISO-8601 UTC
  d: number; // seconds; 10.24
  first: number;
  last: number; // highest N with every segment first..last present; last < first = empty
  published_at: string;
  container: string;
  fallback_version: string | null;
}

export interface Grid {
  epochMs: number;
  dMs: number;
}

export function gridOf(h: Horizon): Grid {
  const epochMs = Date.parse(h.epoch);
  if (!Number.isFinite(epochMs)) throw new Error(`horizon.epoch is not a timestamp: ${h.epoch}`);
  const dMs = Math.round(h.d * 1000);
  if (!(dMs > 0)) throw new Error(`horizon.d is not a positive duration: ${h.d}`);
  return { epochMs, dMs };
}

/** Segment airing at nowMs (floor; negative before the epoch). */
export function indexAt(g: Grid, nowMs: number): number {
  return Math.floor((nowMs - g.epochMs) / g.dMs);
}

export function startMs(g: Grid, n: number): number {
  return g.epochMs + n * g.dMs;
}

export function isoAt(g: Grid, n: number): string {
  return new Date(startMs(g, n)).toISOString();
}
```

`antenna/src/playlist.ts`:

```ts
import { type Grid, type Horizon, gridOf, indexAt, isoAt, startMs } from "./grid";

/** fallback/<version>/index.json. */
export interface FallbackIndex {
  len: number;
  notice: string; // full key of the off-air notice segment
}

export interface PlaylistConfig {
  window: number; // k: segments listed
  grace: number; // segments the clock waits at horizon.last before falling back
  offairAfterMs: number;
}

export interface PlaylistInputs {
  nowMs: number;
  horizon: Horizon;
  fallback: FallbackIndex | null;
  offair: boolean; // state/offair.json {offair: true}
  offairSeqMs?: number; // the off-air MEDIA-SEQUENCE is indexAt(offairSeqMs); default nowMs
}

export type Entry = { n: number; kind: "live" | "fallback" };

export function isOffair(inp: PlaylistInputs, cfg: PlaylistConfig): boolean {
  if (inp.offair) return true;
  const g = gridOf(inp.horizon);
  return inp.nowMs > startMs(g, inp.horizon.last + 1) + cfg.offairAfterMs;
}

/** The listed indices. While 0 < cur - last <= grace the window holds at
 * horizon.last; segments outside [first, last] are absent and play the loop. */
export function windowEntries(cur: number, h: Horizon, cfg: PlaylistConfig): Entry[] {
  const behind = cur - h.last;
  const end = behind > 0 && behind <= cfg.grace ? h.last : cur;
  const start = Math.max(0, end - cfg.window + 1);
  const out: Entry[] = [];
  for (let n = start; n <= end; n++) out.push({ n, kind: n >= h.first && n <= h.last ? "live" : "fallback" });
  return out;
}

const extinf = (dMs: number) => `#EXTINF:${(dMs / 1000).toFixed(3)},`;
const lines = (xs: string[]) => xs.join("\n") + "\n";

/** The notice + ENDLIST. EXT-X-MEDIA-SEQUENCE must never decrease across
 * playlist reloads (RFC 8216), so it is indexAt(seqMs): at or past every live
 * sequence listed for the same clock time, and constant within one invocation
 * when the clock passes scheduledTime + loopMs. */
export function offairPlaylist(fb: FallbackIndex, g: Grid, seqMs: number): string {
  return lines([
    "#EXTM3U",
    "#EXT-X-VERSION:3",
    `#EXT-X-TARGETDURATION:${Math.ceil(g.dMs / 1000)}`,
    `#EXT-X-MEDIA-SEQUENCE:${Math.max(0, indexAt(g, seqMs))}`,
    "#EXT-X-DISCONTINUITY",
    extinf(g.dMs),
    fb.notice,
    "#EXT-X-ENDLIST",
  ]);
}

/** The live playlist, or null when nothing can be listed safely (before the
 * epoch, or a fallback/notice is needed and none is published). A null means
 * "write nothing": players stall on a stale playlist rather than fetch a
 * segment that does not exist. */
export function buildPlaylist(inp: PlaylistInputs, cfg: PlaylistConfig): string | null {
  const h = inp.horizon;
  const g = gridOf(h);
  const fb = inp.fallback !== null && h.fallback_version !== null && inp.fallback.len >= 1 ? inp.fallback : null;
  if (isOffair(inp, cfg)) return fb ? offairPlaylist(fb, g, inp.offairSeqMs ?? inp.nowMs) : null;
  const cur = indexAt(g, inp.nowMs);
  if (cur < 0) return null;
  const entries = windowEntries(cur, h, cfg);
  if (entries.length === 0) return null;
  if (fb === null && entries.some((e) => e.kind === "fallback")) return null;
  const len = fb ? fb.len : 1;
  // A discontinuity before segment 0 of every loop iteration and at every switch.
  const tagged = entries.map(
    (e, i) => (e.kind === "fallback" && e.n % len === 0) || (i > 0 && entries[i - 1].kind !== e.kind),
  );
  // Choose the sequence so fallback segment N always carries discontinuity
  // number floor(N/len) (= floor(N/len) during pure fallback). A pure-live
  // window restarts at 0: a live<->fallback transition may cost a listener one
  // reload or glitch (spec-accepted).
  let discSeq = 0;
  const fi = entries.findIndex((e) => e.kind === "fallback");
  if (fi >= 0) {
    const tagsThrough = tagged.slice(0, fi + 1).filter(Boolean).length;
    discSeq = Math.max(0, Math.floor(entries[fi].n / len) - tagsThrough);
  }
  const out = [
    "#EXTM3U",
    "#EXT-X-VERSION:3",
    `#EXT-X-TARGETDURATION:${Math.ceil(g.dMs / 1000)}`,
    `#EXT-X-MEDIA-SEQUENCE:${entries[0].n}`,
    `#EXT-X-DISCONTINUITY-SEQUENCE:${discSeq}`,
  ];
  entries.forEach((e, i) => {
    if (tagged[i]) out.push("#EXT-X-DISCONTINUITY");
    out.push(
      `#EXT-X-PROGRAM-DATE-TIME:${isoAt(g, e.n)}`,
      extinf(g.dMs),
      e.kind === "live" ? `seg/${h.epoch_id}/${e.n}.aac` : `fallback/${h.fallback_version}/${e.n % len}.aac`,
    );
  });
  return lines(out);
}
```

- [ ] **Step 5: Run the tests and the type check**

Run: `cd antenna && npx vitest run && npx tsc --noEmit`
Expected: PASS, no type errors.

- [ ] **Step 6: Commit**

```bash
git add .gitignore antenna
git commit -m "feat(antenna): Worker scaffold and the wall-clock playlist builder"
```

---

### Task 16: antenna clock loop and the Worker entry

**Model hint:** opus

> **As built (final review):** the PUT cap is not formula-only — `putCap` is `min(MAX_PUTS, ceil(loopMs/d) + 2)` with a hard `MAX_PUTS = 10`; a horizon whose `d` is not exactly 10.24 is refused (`horizon-refused`, nothing written); and `LOOP_SECONDS` is clamped to 75 s (`loop-clamped`). See `antenna/src/clock.ts`.

**Files:**
- Create: `antenna/src/clock.ts`
- Modify: `antenna/src/index.ts`
- Create: `antenna/test/clock.test.ts`

**Interfaces:**
- Consumes: Task 15's `gridOf/indexAt/startMs`, `buildPlaylist`, `FallbackIndex`, `PlaylistConfig`, `Horizon`.
- Produces: `interface StoredObject { text() }`; `interface BucketLike { get(key); put(key, value: string, { httpMetadata: { contentType, cacheControl } }) }`; `r2Bucket(b: R2Bucket) -> BucketLike`; `interface ClockConfig extends PlaylistConfig { loopMs; liveMaxAge }`; `interface ClockEnv` (string vars); `configFromEnv(env) -> ClockConfig`; `interface ClockDeps { bucket; now; sleep; scheduledTime; config; guard? }`; `guardStep(deps)` (**phase-2 seam, a no-op**); `readInputs(bucket) -> { horizon, fallback, offair }`; `putCap(cfg, dMs) -> number`; `runClock(deps) -> { puts, skipped }`; `LIVE_KEY = "live.m3u8"`.

- [ ] **Step 1: Write the failing tests**

`antenna/test/clock.test.ts`:

```ts
import { createExecutionContext, createScheduledController, env, waitOnExecutionContext } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { type BucketLike, type ClockConfig, configFromEnv, putCap, r2Bucket, runClock } from "../src/clock";
import worker from "../src/index";

const E = Date.parse("2026-10-10T12:00:00.000Z");
const D = 10_240;
const CFG: ClockConfig = { window: 6, grace: 3, offairAfterMs: 86_400_000, loopMs: 75_000, liveMaxAge: 5 };

class MemoryBucket implements BucketLike {
  objects = new Map<string, { body: string; contentType?: string; cacheControl?: string }>();
  log: string[] = [];
  async get(key: string) {
    this.log.push(`get ${key}`);
    const o = this.objects.get(key);
    return o ? { text: async () => o.body } : null;
  }
  async put(key: string, value: string, options: { httpMetadata: { contentType: string; cacheControl: string } }) {
    this.log.push(`put ${key}`);
    this.objects.set(key, { body: value, ...options.httpMetadata });
    return null;
  }
  seed(key: string, value: unknown) {
    this.objects.set(key, { body: JSON.stringify(value) });
  }
}

function horizonDoc(epochMs: number, first = 0, last = 1_000_000) {
  const iso = new Date(epochMs).toISOString();
  return { epoch_id: "e1", epoch: iso, d: 10.24, first, last, published_at: iso, container: "adts", fallback_version: "v1" };
}
const FALLBACK = { len: 7, notice: "fallback/v1/notice.aac", d: 10.24 };

function station(bucket: MemoryBucket, offair = false) {
  bucket.seed("state/horizon.json", horizonDoc(E));
  bucket.seed("fallback/v1/index.json", FALLBACK);
  if (offair) bucket.seed("state/offair.json", { offair: true, reason: "test", since: null, until: null });
}

function fakeTime(start: number) {
  let t = start;
  return { now: () => t, sleep: async (ms: number) => { t += ms; } };
}

const playlistPuts = (b: MemoryBucket) => b.log.filter((l) => l === "put live.m3u8").length;

describe("runClock", () => {
  it("writes immediately, then at every grid boundary until fire + 75 s", async () => {
    const bucket = new MemoryBucket();
    station(bucket);
    const scheduledTime = E + 50 * D + 300;
    const clock = fakeTime(scheduledTime + 40);
    const r = await runClock({ bucket, ...clock, scheduledTime, config: CFG });
    expect(r.puts).toBe(8); // immediate + boundaries 51..57; 58 starts after fire + 75 s
    expect(playlistPuts(bucket)).toBe(8);
    expect(clock.now()).toBeLessThanOrEqual(scheduledTime + CFG.loopMs);
    expect(bucket.objects.get("live.m3u8")!.body).toContain("seg/e1/57.aac");
  });

  it("never exceeds ceil(75/d) + 2 PUTs, even with a skewed fire time", async () => {
    const bucket = new MemoryBucket();
    station(bucket);
    const clock = fakeTime(E + 100 * D);
    const r = await runClock({ bucket, ...clock, scheduledTime: E + 100 * D + 600_000, config: CFG });
    expect(putCap(CFG, D)).toBe(10);
    expect(r.puts).toBe(10);
  });

  it("skips bytes identical to the last write (off-air: one PUT per invocation)", async () => {
    const bucket = new MemoryBucket();
    station(bucket, true);
    const scheduledTime = E + 50 * D + 300;
    const r = await runClock({ bucket, ...fakeTime(scheduledTime + 40), scheduledTime, config: CFG });
    expect(r.puts).toBe(1);
    expect(r.skipped).toBe(7);
    expect(bucket.objects.get("live.m3u8")!.body).toContain("#EXT-X-ENDLIST");
  });

  it("runs the guard step before reading anything", async () => {
    const bucket = new MemoryBucket();
    station(bucket);
    const seen: string[] = [];
    await runClock({
      bucket, ...fakeTime(E + 10 * D), scheduledTime: E + 10 * D, config: { ...CFG, loopMs: 0 },
      guard: async () => { seen.push("guard", ...bucket.log); },
    });
    expect(seen).toEqual(["guard"]);
    expect(bucket.log[0]).toBe("get state/horizon.json");
  });

  it("writes nothing without a horizon", async () => {
    const bucket = new MemoryBucket();
    const r = await runClock({ bucket, ...fakeTime(E), scheduledTime: E, config: CFG });
    expect(r.puts).toBe(0);
    expect(bucket.log.every((l) => l.startsWith("get "))).toBe(true);
  });

  it("writes live.m3u8 through the R2 binding with its content type and max-age", async () => {
    await env.BUCKET.put("state/horizon.json", JSON.stringify(horizonDoc(E)));
    await env.BUCKET.put("fallback/v1/index.json", JSON.stringify(FALLBACK));
    await runClock({ bucket: r2Bucket(env.BUCKET), ...fakeTime(E + 10 * D + 40), scheduledTime: E + 10 * D,
                     config: { ...CFG, loopMs: 0 } });
    const obj = await env.BUCKET.get("live.m3u8");
    expect(obj!.httpMetadata!.contentType).toBe("application/vnd.apple.mpegurl");
    expect(obj!.httpMetadata!.cacheControl).toBe("public, max-age=5");
    expect(await obj!.text()).toContain("seg/e1/10.aac");
  });
});

describe("configFromEnv", () => {
  it("parses the vars with defaults", () => {
    expect(configFromEnv({})).toEqual({ window: 6, grace: 3, offairAfterMs: 86_400_000, loopMs: 75_000, liveMaxAge: 5 });
    expect(configFromEnv({ LOOP_SECONDS: "0", PLAYLIST_WINDOW: "8" })).toMatchObject({ loopMs: 0, window: 8 });
    expect(configFromEnv({ GRACE_SEGMENTS: "nonsense" }).grace).toBe(3);
  });
});

describe("scheduled handler", () => {
  it("runs one clock invocation against the bound bucket", async () => {
    const now = Date.now();
    await env.BUCKET.put("state/horizon.json", JSON.stringify(horizonDoc(now - 100 * D)));
    await env.BUCKET.put("fallback/v1/index.json", JSON.stringify(FALLBACK));
    const ctrl = createScheduledController({ scheduledTime: now, cron: "* * * * *" });
    const ctx = createExecutionContext();
    await worker.scheduled!(ctrl, { ...env, LOOP_SECONDS: "0" } as unknown as Env, ctx);
    await waitOnExecutionContext(ctx);
    const body = await (await env.BUCKET.get("live.m3u8"))!.text();
    expect(body).toContain("#EXTM3U");
    expect(body).toContain("seg/e1/");
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd antenna && npx vitest run test/clock.test.ts`
Expected: FAIL — cannot resolve `../src/clock`.

- [ ] **Step 3: Implement `clock.ts` and the Worker entry**

`antenna/src/clock.ts`:

```ts
import { type Horizon, gridOf, indexAt, startMs } from "./grid";
import { buildPlaylist, type FallbackIndex, type PlaylistConfig } from "./playlist";

export interface StoredObject {
  text(): Promise<string>;
}

export interface BucketLike {
  get(key: string): Promise<StoredObject | null>;
  put(key: string, value: string, options: { httpMetadata: { contentType: string; cacheControl: string } }): Promise<unknown>;
}

export function r2Bucket(b: R2Bucket): BucketLike {
  return {
    get: (key) => b.get(key),
    put: (key, value, options) => b.put(key, value, options),
  };
}

export interface ClockConfig extends PlaylistConfig {
  loopMs: number;
  liveMaxAge: number;
}

export interface ClockEnv {
  PLAYLIST_WINDOW?: string;
  GRACE_SEGMENTS?: string;
  OFFAIR_AFTER_SECONDS?: string;
  LOOP_SECONDS?: string;
  LIVE_MAX_AGE?: string;
}

function num(v: string | undefined, fallback: number): number {
  const x = v === undefined ? Number.NaN : Number(v);
  return Number.isFinite(x) && x >= 0 ? x : fallback;
}

export function configFromEnv(env: ClockEnv): ClockConfig {
  return {
    window: Math.max(1, Math.floor(num(env.PLAYLIST_WINDOW, 6))),
    grace: Math.floor(num(env.GRACE_SEGMENTS, 3)),
    offairAfterMs: num(env.OFFAIR_AFTER_SECONDS, 86_400) * 1000,
    loopMs: num(env.LOOP_SECONDS, 75) * 1000,
    liveMaxAge: Math.floor(num(env.LIVE_MAX_AGE, 5)),
  };
}

export interface ClockDeps {
  bucket: BucketLike;
  now: () => number;
  sleep: (ms: number) => Promise<void>;
  scheduledTime: number;
  config: ClockConfig;
  guard?: (deps: ClockDeps) => Promise<void>;
}

export interface ClockResult {
  puts: number;
  skipped: number;
}

export const LIVE_KEY = "live.m3u8";
const BOUNDARY_SLACK_MS = 25;

/**
 * Phase-2 seam. The cost guard runs here, first in every invocation and in
 * its own try/finally: it evaluates usage when state/guard.json is >= 15 min
 * old, applies the blind rule, and reconciles the blocked state (tripped OR
 * offair: ENDLIST playlist, off-air index.html, WAF kill switch) before any
 * playlist work. Phase 1 honours only a hand-written state/offair.json, which
 * readInputs reads; this is deliberately a no-op.
 */
export async function guardStep(_deps: ClockDeps): Promise<void> {}

export interface ClockInputs {
  horizon: Horizon | null;
  fallback: FallbackIndex | null;
  offair: boolean;
}

async function readJson<T>(bucket: BucketLike, key: string): Promise<T | null> {
  const obj = await bucket.get(key);
  if (obj === null) return null;
  try {
    return JSON.parse(await obj.text()) as T;
  } catch {
    return null;
  }
}

/** state/ is read once per invocation, via the binding (never through the cache). */
export async function readInputs(bucket: BucketLike): Promise<ClockInputs> {
  const horizon = await readJson<Horizon>(bucket, "state/horizon.json");
  const offairDoc = await readJson<{ offair?: unknown }>(bucket, "state/offair.json");
  const fallback = horizon?.fallback_version
    ? await readJson<FallbackIndex>(bucket, `fallback/${horizon.fallback_version}/index.json`)
    : null;
  return { horizon, fallback, offair: offairDoc?.offair === true };
}

export function putCap(cfg: ClockConfig, dMs: number): number {
  return Math.ceil(cfg.loopMs / dMs) + 2;
}

/**
 * One cron invocation: write the current playlist immediately, then rewrite it
 * at every grid boundary E + N*d until scheduledTime + loopMs. Only CPU time is
 * billed, so the waiting is free. Overlapping invocations are harmless: the
 * playlist is a pure function of the clock and the inputs.
 */
export async function runClock(deps: ClockDeps): Promise<ClockResult> {
  await (deps.guard ?? guardStep)(deps);
  const { bucket, config } = deps;
  const inputs = await readInputs(bucket);
  const result: ClockResult = { puts: 0, skipped: 0 };
  const horizon = inputs.horizon;
  if (horizon === null) return result;
  const g = gridOf(horizon);
  const cap = putCap(config, g.dMs);
  let lastBody: string | null = null;
  const write = async (force: boolean) => {
    const body = buildPlaylist({ nowMs: deps.now(), horizon, fallback: inputs.fallback, offair: inputs.offair,
                                 offairSeqMs: deps.scheduledTime + config.loopMs }, config);
    if (body === null) return;
    if (!force && body === lastBody) {
      result.skipped++;
      return;
    }
    if (result.puts >= cap) return;
    await bucket.put(LIVE_KEY, body, {
      httpMetadata: { contentType: "application/vnd.apple.mpegurl", cacheControl: `public, max-age=${config.liveMaxAge}` },
    });
    result.puts++;
    lastBody = body;
  };
  await write(true);
  const deadline = deps.scheduledTime + config.loopMs;
  while (result.puts < cap) {
    const now = deps.now();
    const next = startMs(g, indexAt(g, now) + 1);
    if (next > deadline) break;
    await deps.sleep(next - now + BOUNDARY_SLACK_MS);
    await write(false);
  }
  return result;
}
```

`antenna/src/index.ts` (replaces the placeholder):

```ts
import { configFromEnv, r2Bucket, runClock } from "./clock";

export default {
  async scheduled(controller, env, _ctx): Promise<void> {
    const started = Date.now();
    const result = await runClock({
      bucket: r2Bucket(env.BUCKET),
      now: () => Date.now(),
      sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
      scheduledTime: controller.scheduledTime,
      config: configFromEnv(env),
    });
    // One line per invocation; the phase-1 verification compares scheduled vs
    // actual fire times (lagMs) over a day from these.
    console.log(JSON.stringify({ event: "clock", scheduled: controller.scheduledTime, started,
                                 lagMs: started - controller.scheduledTime, ...result }));
  },
} satisfies ExportedHandler<Env>;
```

- [ ] **Step 4: Run the tests and the type check**

Run: `cd antenna && npx vitest run && npx tsc --noEmit`
Expected: PASS, no type errors.

Run: `cd antenna && npx wrangler deploy --dry-run --outdir .wrangler/dry-run`
Expected: bundles successfully and lists the `BUCKET` binding; no routes. (The dry run does not print triggers: check that `antenna/wrangler.jsonc` has `"triggers": { "crons": ["* * * * *"] }`.)

- [ ] **Step 5: Commit**

```bash
git add antenna
git commit -m "feat(antenna): cron clock writes live.m3u8 at every grid boundary (PUT cap, identical skip, guard seam)"
```

---

### Task 17: Static player page and the asset deploy script

**Model hint:** sonnet

**Files:**
- Create: `antenna/public/index.html`, `antenna/public/player.js`, `antenna/public/nowplaying.js`, `antenna/public/style.css`, `antenna/public/offair.html`
- Create: `antenna/scripts/deploy-assets.mjs`
- Create: `antenna/test/nowplaying.test.ts`
- Modify: `antenna/package.json` (adds `hls.js` via npm)

**Interfaces:**
- Consumes: `live.m3u8` (Task 16), `timeline.json` shape from Task 10 (`shows[].{start,end,artist,date,venue,city,files[].{title,start}}`).
- Produces (`public/nowplaying.js`, ES module): `prefersNativeHls(nav, canPlayNative) -> boolean` (Apple WebKit = vendor starts with "Apple", and native HLS reported — covers Safari and every iOS browser; Chrome with native HLS still gets hls.js); `findNowPlaying(timeline, atMs) -> {show, file} | null`; `nowPlayingText(np, timelineLoaded) -> string`.
- Produces: R2 keys `index.html` (max-age 60), `offair.html`, `player.js`, `nowplaying.js`, `style.css`, `assets/hls.min.js` (max-age 3600), uploaded by `ANTENNA_BUCKET=<bucket> npm run deploy:assets`.

- [ ] **Step 1: Install hls.js and write the failing tests**

```bash
cd antenna && npm install hls.js@1 && cd ..
```

`antenna/test/nowplaying.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { findNowPlaying, nowPlayingText, prefersNativeHls } from "../public/nowplaying.js";

const TIMELINE = {
  shows: [
    {
      slug: "cracker-2005-11-01", start: "2026-10-10T12:00:00.000Z", end: "2026-10-10T13:40:00.000Z",
      artist: "Cracker", date: "2005-11-01", venue: "Knickerbockers", city: "Lincoln, NE USA",
      files: [
        { kind: "clip", title: "DJ intro (set 1)", start: "2026-10-10T12:00:00.023Z" },
        { kind: "track", title: "One Fine Day", start: "2026-10-10T12:03:00.000Z" },
        { kind: "track", title: "Guarded By Monkeys", start: "2026-10-10T12:10:39.000Z" },
      ],
    },
  ],
};
const t = (iso: string) => Date.parse(iso);

describe("prefersNativeHls", () => {
  it("uses native HLS on Apple WebKit only", () => {
    expect(prefersNativeHls({ vendor: "Apple Computer, Inc." }, true)).toBe(true); // Safari, any iOS browser
    expect(prefersNativeHls({ vendor: "Google Inc." }, true)).toBe(false); // Chrome's native HLS: use hls.js
    expect(prefersNativeHls({ vendor: "" }, false)).toBe(false); // Firefox
    expect(prefersNativeHls({ vendor: "Apple Computer, Inc." }, false)).toBe(false);
  });
});

describe("findNowPlaying", () => {
  it("finds the show and the latest file that has started", () => {
    const np = findNowPlaying(TIMELINE, t("2026-10-10T12:05:00Z"))!;
    expect(np.show.slug).toBe("cracker-2005-11-01");
    expect(np.file!.title).toBe("One Fine Day");
  });
  it("has a show but no file before the first file starts (encoder priming)", () => {
    expect(findNowPlaying(TIMELINE, t("2026-10-10T12:00:00.010Z"))!.file).toBeNull();
  });
  it("returns null in a gap, in the fallback loop, or without a timeline", () => {
    expect(findNowPlaying(TIMELINE, t("2026-10-10T14:00:00Z"))).toBeNull();
    expect(findNowPlaying(null, t("2026-10-10T12:05:00Z"))).toBeNull();
  });
});

describe("nowPlayingText", () => {
  it("formats show and file, or says the station will be back", () => {
    const np = findNowPlaying(TIMELINE, t("2026-10-10T12:05:00Z"));
    expect(nowPlayingText(np, true)).toBe("Cracker — 2005-11-01, Knickerbockers, Lincoln, NE USA · One Fine Day");
    expect(nowPlayingText(null, true)).toBe("We'll be back shortly.");
    expect(nowPlayingText(null, false)).toBe("Tuning in…");
  });
});
```

Run: `cd antenna && npx vitest run test/nowplaying.test.ts`
Expected: FAIL — cannot resolve `../public/nowplaying.js`.

- [ ] **Step 2: Implement the page**

`antenna/public/nowplaying.js`:

```js
// Pure helpers for the player (unit-tested). The player computes now-playing
// client-side: program-date-time of the playback position, looked up in
// timeline.json -- no request stream bills per listener.

/** Native HLS on Apple WebKit (Safari and every iOS browser -- all WebKit);
 * hls.js everywhere else, including Chrome whose native HLS is buggy. Detected
 * by vendor, not canPlayType alone (also true on Chrome). */
export function prefersNativeHls(nav, canPlayNative) {
  const vendor = typeof nav.vendor === "string" ? nav.vendor : "";
  return Boolean(canPlayNative) && vendor.startsWith("Apple");
}

export function findNowPlaying(timeline, atMs) {
  if (!timeline || !Array.isArray(timeline.shows)) return null;
  for (const show of timeline.shows) {
    if (atMs >= Date.parse(show.start) && atMs < Date.parse(show.end)) {
      let file = null;
      for (const f of show.files || []) {
        if (Date.parse(f.start) <= atMs) file = f;
        else break;
      }
      return { show, file };
    }
  }
  return null;
}

export function nowPlayingText(np, timelineLoaded) {
  if (!np) return timelineLoaded ? "We'll be back shortly." : "Tuning in…";
  const s = np.show;
  const where = [s.venue, s.city].filter(Boolean).join(", ");
  const head = [s.artist, [s.date, where].filter(Boolean).join(", ")].filter(Boolean).join(" — ");
  return np.file ? `${head} · ${np.file.title}` : head;
}
```

`antenna/public/player.js`:

```js
import { findNowPlaying, nowPlayingText, prefersNativeHls } from "./nowplaying.js";

const STREAM = "live.m3u8";
const TIMELINE = "timeline.json";
const TIMELINE_REFRESH_MS = 3 * 60 * 1000;

const audio = document.getElementById("audio");
const playButton = document.getElementById("play");
const nowPlaying = document.getElementById("now-playing");
const notice = document.getElementById("notice");
const noticeText = document.getElementById("notice-text");
const retryButton = document.getElementById("retry");
document.getElementById("stream-url").textContent = new URL(STREAM, location.href).href;

let hls = null;
let playing = false;
let timeline = null;
let timelineFetchedAt = 0;

const useNative = () => prefersNativeHls(navigator, audio.canPlayType("application/vnd.apple.mpegurl") !== "");

function showNotice(text) {
  noticeText.textContent = text;
  notice.hidden = false;
}

function stop() {
  playing = false;
  if (hls) {
    hls.destroy();
    hls = null;
  }
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  playButton.textContent = "Play";
}

// Off-air (ENDLIST) or blocked (403): stop, show the notice, never auto-reconnect.
function offAir(text) {
  stop();
  showNotice(text);
  nowPlaying.textContent = "";
}

// Radio semantics: every start joins the live edge (pause = stop).
function start() {
  stop();
  notice.hidden = true;
  playing = true;
  playButton.textContent = "Stop";
  if (useNative()) {
    audio.src = STREAM;
  } else if (window.Hls && window.Hls.isSupported()) {
    hls = new window.Hls({ liveSyncDurationCount: 3 });
    hls.on(window.Hls.Events.LEVEL_LOADED, (_event, data) => {
      if (data.details && data.details.live === false) offAir("The station is off the air.");
    });
    hls.on(window.Hls.Events.ERROR, (_event, data) => {
      const code = data.response && data.response.code;
      if (code === 403) offAir("The station is off the air.");
      else if (data.fatal) offAir("The stream is unavailable right now.");
    });
    hls.loadSource(STREAM);
    hls.attachMedia(audio);
  } else {
    offAir("This browser cannot play the stream here; open the stream URL in VLC.");
    return;
  }
  audio.play().catch(() => offAir("Playback was blocked; press Try again."));
  refreshTimeline(true);
}

audio.addEventListener("ended", () => offAir("The station is off the air."));
audio.addEventListener("error", () => {
  if (playing) offAir("The stream is unavailable right now.");
});
playButton.addEventListener("click", () => (playing ? stop() : start()));
retryButton.addEventListener("click", start);

function playbackDateMs() {
  if (hls && hls.playingDate) return hls.playingDate.getTime();
  if (typeof audio.getStartDate === "function") {
    const startMs = audio.getStartDate().getTime();
    if (Number.isFinite(startMs)) return startMs + audio.currentTime * 1000;
  }
  return null;
}

// Fetched only while playing, at most every few minutes, never while hidden.
async function refreshTimeline(force) {
  if (!playing || document.hidden) return;
  if (!force && Date.now() - timelineFetchedAt < TIMELINE_REFRESH_MS) return;
  timelineFetchedAt = Date.now();
  try {
    const res = await fetch(TIMELINE);
    if (res.ok) timeline = await res.json();
  } catch {
    // keep the last timeline
  }
}

setInterval(() => {
  if (!playing) return;
  refreshTimeline(false);
  const at = playbackDateMs();
  if (at !== null) nowPlaying.textContent = nowPlayingText(findNowPlaying(timeline, at), timeline !== null);
}, 1000);
```

`antenna/public/index.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>llama radio</title>
<meta property="og:type" content="website">
<meta property="og:title" content="llama radio">
<meta property="og:description" content="Live concert recordings from the Live Music Archive, around the clock.">
<link rel="stylesheet" href="style.css">
<script src="assets/hls.min.js" defer></script>
<script type="module" src="player.js"></script>
</head>
<body>
<main class="player">
  <h1>llama radio</h1>
  <p id="now-playing" class="now-playing">Press play to tune in.</p>
  <p><button id="play" type="button">Play</button></p>
  <audio id="audio" preload="none"></audio>
  <div id="notice" class="notice" hidden>
    <p id="notice-text">The station is off the air.</p>
    <p><button id="retry" type="button">Try again</button></p>
  </div>
  <p class="stream">Stream URL (VLC, apps): <code id="stream-url"></code></p>
  <p class="credit">Recordings from the <a href="https://archive.org/details/etree">Live Music Archive</a>.
     Non-commercial; no ads.</p>
</main>
</body>
</html>
```

`antenna/public/offair.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Off the air · llama radio</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<main class="player">
  <h1>llama radio</h1>
  <p class="notice">The station is off the air.</p>
  <p class="credit">Recordings from the <a href="https://archive.org/details/etree">Live Music Archive</a>.</p>
</main>
</body>
</html>
```

`antenna/public/style.css`:

```css
body { font: 17px/1.5 system-ui, sans-serif; margin: 0; background: #faf8f4; color: #222; }
main { max-width: 40rem; margin: 3rem auto; padding: 0 1.25rem; }
h1 { font-size: 1.8rem; margin-bottom: .5rem; }
button { font-size: 1.1rem; padding: .5rem 1.4rem; border-radius: .4rem; border: 1px solid #444; background: #fff; cursor: pointer; }
.now-playing { min-height: 1.5em; font-weight: 600; }
.notice { background: #fff3cd; border: 1px solid #e0c36b; padding: .25rem 1rem; border-radius: .4rem; }
.stream code { word-break: break-all; }
.credit, .lineage, .set { color: #666; font-size: .9rem; }
```

`antenna/scripts/deploy-assets.mjs`:

```js
#!/usr/bin/env node
// Upload antenna's static assets to the station's R2 bucket (spec "R2 object
// contract": index.html, offair.html and the app assets incl. hls.js are written
// by the antenna deploy script; index.html is static in phase 1).
// Usage: ANTENNA_BUCKET=<bucket> node scripts/deploy-assets.mjs [--dry-run]
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const bucket = process.env.ANTENNA_BUCKET;
const dryRun = process.argv.includes("--dry-run");
if (!bucket) {
  console.error("set ANTENNA_BUCKET to the station's R2 bucket name");
  process.exit(2);
}

const HTML = "text/html; charset=utf-8";
const JS = "text/javascript; charset=utf-8";
const CSS = "text/css; charset=utf-8";
const HOUR = "public, max-age=3600";
const ASSETS = [
  ["index.html", "public/index.html", HTML, "public, max-age=60"],
  ["offair.html", "public/offair.html", HTML, HOUR],
  ["player.js", "public/player.js", JS, HOUR],
  ["nowplaying.js", "public/nowplaying.js", JS, HOUR],
  ["style.css", "public/style.css", CSS, HOUR],
  ["assets/hls.min.js", "node_modules/hls.js/dist/hls.min.js", JS, HOUR],
];

for (const [key, file, type, cache] of ASSETS) {
  const path = join(root, file);
  if (!existsSync(path)) {
    console.error(`missing ${file} (run npm install?)`);
    process.exit(1);
  }
  const args = ["wrangler", "r2", "object", "put", `${bucket}/${key}`, "--file", path,
                "--content-type", type, "--cache-control", cache, "--remote"];
  if (dryRun) {
    console.log(["npx", ...args].join(" "));
    continue;
  }
  const r = spawnSync("npx", args, { cwd: root, stdio: "inherit" });
  if (r.status !== 0) process.exit(r.status ?? 1);
}
```

- [ ] **Step 3: Run the tests, the type check and a dry run**

Run: `cd antenna && npx vitest run && npx tsc --noEmit`
Expected: PASS.

Run: `cd antenna && ANTENNA_BUCKET=llama-radio node scripts/deploy-assets.mjs --dry-run`
Expected: six `npx wrangler r2 object put llama-radio/<key> … --remote` lines, one per asset.

- [ ] **Step 4: Manual smoke check (local)**

Serve the spike output from Task 2 alongside the page to check the wiring in a browser: copy `antenna/public/*` and `antenna/node_modules/hls.js/dist/hls.min.js` (as `assets/hls.min.js`) into the spike directory, add `live.m3u8` from `python -m transmitter.spike serve`, open `http://localhost:8000/index.html`, press Play: audio plays in Chrome (hls.js) and Safari (native); the stream URL shows; playback stops and the notice appears when the live playlist reaches ENDLIST. (The phase-4 Playwright smoke test against a local R2 emulation replaces this.)

- [ ] **Step 5: Commit**

```bash
git add antenna
git commit -m "feat(antenna): minimal static player (native HLS on Apple, hls.js elsewhere) and asset deploy script"
```

---

### Task 18: Setup runbook and the phase-1 verification checklist

**Model hint:** sonnet

**Files:**
- Create: `docs/playout-setup.md`

**Interfaces:**
- Consumes: the names fixed above — bucket `llama-radio` (wrangler.jsonc / `[publish] bucket`), env vars `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY`, `transmitter` commands, `npm run deploy` / `deploy:assets`, the R2 key layout.
- Produces: the operator runbook. No code; no tests. These steps need the real Cloudflare account and are not automatable in CI.

- [ ] **Step 1: Write `docs/playout-setup.md`**

Write the file with exactly these sections and content (fill in nothing at execution time beyond what is written here; `<host>` is the operator's chosen hostname and stays a literal placeholder in the doc):

````markdown
# Playout setup (phase 1)

How to stand up the station's cloud side (R2 + one cached hostname + the antenna
clock Worker) and hugo's transmitter, then verify the phase-1 assumptions. The
design is `docs/superpowers/specs/2026-10-09-playout-design.md`. **Do not share
the station publicly until phase 2 (the cost guard) ships.**

## 0. Preconditions

- A Cloudflare account **dedicated to the station** (phase 2's guard reads
  account-scoped meters; other projects would pollute them).
- **Workers Paid** ($5/month) enabled on that account.
- The station's domain is a **full** Cloudflare zone on that account (registrar NS
  records point at Cloudflare; partial/CNAME setup is Business-only).
- **No paid zone add-ons**: no Argo, Cache Reserve or Load Balancing (the guard
  cannot see them; the Budget alert would be their only backstop).
- Workers observability/logs within the free allowance (the clock logs one line
  per invocation, ~1,440/day).
- hugo: Debian 12, Python 3.11, ffmpeg 5.1, Node 22; NFS mount of the station
  share; **NTP synchronized** — check `timedatectl status` shows
  `System clock synchronized: yes` (systemd-timesyncd or chrony).

## 1. R2 bucket and custom domain

1. `cd antenna && npx wrangler login`, then `npx wrangler r2 bucket create llama-radio`
   (if you choose another name, change it in `antenna/wrangler.jsonc` and
   transmitter's `[publish] bucket`).
2. Dashboard → R2 → `llama-radio` → Settings → **Custom Domains** → connect
   `<host>` (a hostname on the station zone). Leave the `r2.dev` public URL
   **disabled** (r2.dev is uncached and would bill every request).
3. R2 → **Manage API tokens** → create a token with *Object Read & Write* scoped to
   `llama-radio` only. Put its key pair on hugo in the service's env file (mode 600,
   owned by the service user):
   ```
   R2_ACCESS_KEY_ID=...
   R2_SECRET_ACCESS_KEY=...
   ```

## 2. Zone configuration (dashboard)

1. **Caching → Cache Rules** → new rule *"station: cache everything"*:
   when `http.host eq "<host>"` → **Eligible for cache**; Edge TTL **Use cache-control
   header if present** (respect origin); Cache key → **Ignore query string**.
   (404s keep the default 3-minute edge TTL; not settable on Free.)
2. **Caching → Configuration → Browser Cache TTL = Respect Existing Headers**
   (otherwise browsers serve a stale `live.m3u8` from their own cache).
3. **Caching → Tiered Cache → Smart Tiered Cache: on.**
4. **Rules → Transform Rules → URL Rewrite**: when `http.host eq "<host>" and
   http.request.uri.path eq "/"` → rewrite path to static `/index.html`
   (R2 custom domains serve no index document).
5. **Rules → Transform Rules → Modify Response Header**: when `http.host eq "<host>"`
   → **set static** `Access-Control-Allow-Origin` = `*` (R2's CORS policy answers only
   requests carrying `Origin`, so a cached non-CORS response would lack it).
6. **Security → WAF → Custom rules**, rule *"station: allowlist"*, action **Block**:
   ```
   http.host eq "<host>" and not (
     http.request.uri.path in {"/" "/index.html" "/embed.html" "/offair.html" "/live.m3u8"
                               "/timeline.json" "/player.js" "/nowplaying.js" "/style.css"}
     or starts_with(http.request.uri.path, "/seg/")
     or starts_with(http.request.uri.path, "/fallback/")
     or starts_with(http.request.uri.path, "/notes/")
     or starts_with(http.request.uri.path, "/show/")
     or starts_with(http.request.uri.path, "/assets/")
   )
   ```
   (`state/` is not allowlisted, so it is blocked. Use only `eq`/`in`/`starts_with`/
   `ends_with`; `matches` is Business+. Try `wildcard` in a scratch rule as part of the
   verification below.)
7. Second custom rule *"station: kill switch"*, action **Block**, **created disabled**
   (phase 2's guard toggles it):
   ```
   http.host eq "<host>" and not (http.request.uri.path in {"/" "/index.html" "/offair.html" "/style.css"})
   ```
8. **Security → WAF → Rate limiting rules** (the one free rule): when
   `http.host eq "<host>"`, **100 requests per 10 seconds per IP**, action Block for 10 s.
   (A playing stream makes ~2 requests per 10 s; dozens of listeners behind one NAT fit.)
9. **Billing → Budget alerts**: two alerts at **50%** and **100%** of
   (`monthly_budget_usd` − $5) — they exclude subscription fees, and are next-day and
   informational only.

## 3. transmitter on hugo

1. Clone the repo; `python3 -m venv ~/.venvs/transmitter && ~/.venvs/transmitter/bin/pip install -e <repo>/packages/transmitter`.
2. On the share, once: `touch /nfs/media/<station>/.station-root` (create it from the
   Mac side on the SMB path if hugo's mount is read-only). Without the marker, `plan`
   refuses — a down NFS mount is an empty directory on hugo.
3. `transmitter config init`, then edit `~/.transmitter/config.toml`:
   `[station] root`, `[publish] account_id` and `bucket`, `[antenna] dir = "<repo>/antenna"`
   and `site_url = "https://<host>"`.
4. Fallback loop and off-air notice (once; re-run only to change them):
   `transmitter fallback render station-id.mp3 --notice offair-notice.mp3`.
5. Start: `transmitter run` with the env file loaded. In phase 1 it runs as the
   operator's own user (phase 2 ships a system unit, with `WatchdogSec` and journald).
   Once: `sudo loginctl enable-linger <user>`, so the user's services keep running
   after logout (a transient `systemd-run` unit does not survive a reboot: re-run
   this step after one). Then run it under `systemd-run --user
   --unit=transmitter --property=EnvironmentFile=<env file> --property=Restart=always
   --property=RestartSec=30 ~/.venvs/transmitter/bin/transmitter run` (restarted 30 s
   after any crash), and check `journalctl --user -u transmitter` for `ALERT` lines.
6. `transmitter status` shows the epoch, plan, the show on air, the published lead
   and the fallback version.

## 4. antenna

1. `cd antenna && npm ci && npm test`
2. `npx wrangler deploy` (cron `* * * * *`, R2 binding, `workers_dev = false`,
   `preview_urls = false`, no routes).
3. `ANTENNA_BUCKET=llama-radio npm run deploy:assets` (player page, off-air page,
   JS/CSS, hls.js).
4. Off-air by hand (phase 1 has no `transmitter offair`): write
   `{"offair": true, "reason": "maintenance", "since": "<iso>", "until": null}` to
   `state/offair.json`:
   `npx wrangler r2 object put llama-radio/state/offair.json --file offair.json --content-type application/json --remote`;
   back on air: same with `"offair": false` (or delete the object). Within a minute
   `live.m3u8` becomes the notice + `#EXT-X-ENDLIST`, and back.

## 5. Phase-1 verification checklist

Run these with the station up; record each result (date, observation) in the
phase-1 ledger. Each needs the real account.

- [ ] **A cron invocation may loop ~75 s with only CPU billed.** Workers → antenna →
      Metrics: wall time per invocation ≈ 75 s, CPU time a few ms; Billing → usage
      shows CPU-ms, not duration.
- [ ] **Scheduled vs actual cron fire times over a day.** `npx wrangler tail antenna`
      (or the dashboard logs): the clock logs `{"event":"clock","lagMs":…}` per
      invocation; summarize lagMs over 24 h (median, p99, any missed minutes).
- [ ] **R2 custom-domain cache hits incur no Class B.** Fetch one segment 50× via
      `https://<host>/seg/…` (`curl -sI` shows `cf-cache-status: HIT` after the first);
      R2 metrics show ~1 Class B read for it, not 50.
- [ ] **A 5 s origin max-age is honoured for `live.m3u8`** at the edge (`curl -sI
      https://<host>/live.m3u8` twice within 5 s: `HIT` with `age` ≤ 5; after 6 s,
      `EXPIRED`/`MISS` and new content) and in browsers under Respect Existing
      Headers (DevTools: no "from disk cache" for `live.m3u8` older than 5 s).
- [ ] **The ignore-query-string Cache Rule works on this plan:** `curl -sI
      'https://<host>/timeline.json?a=1'` then `?a=2` → the second is a `HIT`.
- [ ] **Whether `wildcard` rule expressions are available on Free:** save a scratch
      WAF rule using `http.request.uri.path wildcard "/seg/*"`; record accept/reject,
      then delete it.
- [ ] **The Worker's `*.workers.dev` URL serves no Worker:** `curl -sI
      https://antenna.<account-subdomain>.workers.dev/` → not served by the Worker
      (an error/404 from Cloudflare, no clock output); likewise no preview URL.
- [ ] **hls.js, Safari/iOS and VLC play the chosen container with PROGRAM-DATE-TIME,
      and stop on ENDLIST and on 403:** play `https://<host>/` in Chrome, Safari (macOS,
      iOS) and `https://<host>/live.m3u8` in VLC; set `state/offair.json` → every player
      stops with the notice; then temporarily enable the kill-switch rule → `live.m3u8`
      returns 403 and the page shows the off-air notice with a manual retry; disable it.
- [ ] **archive.org MP3 derivatives carry LAME/Xing gapless info (one segued pair):**
      for two consecutive segued tracks in a delivered package,
      `ffprobe -v debug "<track>.mp3" 2>&1 | grep -E '^\[mp3 .*\] pad '` prints
      `pad <delay> <padding>` for each; then listen across that join on air.
- [ ] **The Email Routing send-email binding is available** on the account (for
      phase 2 alerts): Email → Email Routing enabled on the zone with a verified
      destination address; a throwaway Worker with a `send_email` binding deploys.
- [ ] **GraphQL account-scoped queries work with a read-only token and lag by
      minutes** (for phase 2): create an *Account Analytics: Read* token; query
      `workersInvocationsAdaptive`, `r2OperationsAdaptiveGroups` and
      `r2StorageAdaptiveGroups` for the account over the last hour; note how far
      behind real time the newest datapoint is.
- [ ] **llama's purge flush over SMB to the Synology:** deliver one show to the NAS
      path with `llama deliver`; confirm the purge succeeds (or fails closed with its
      warning and keeps the library audio) — the one-time cut-over check from the spec.
- [ ] **A week of real op counts at ~1 listener:** after 7 days, record Workers
      requests, R2 Class A/B ops and storage from Billing/R2 metrics; compare with the
      spec's budget (Class A ≈ 620k/month, storage ≈ 1.4 GB at a 24 h lead, Workers
      ≈ 43k invocations/month).
````

- [ ] **Step 2: Check it renders and the commands match the code**

Run: `grep -n "llama-radio\|R2_ACCESS_KEY_ID\|deploy:assets\|fallback render" docs/playout-setup.md`
Expected: every name matches `antenna/wrangler.jsonc`, `transmitter/r2.py`, `antenna/package.json` and the CLI.

- [ ] **Step 3: Commit**

```bash
git add docs/playout-setup.md
git commit -m "docs: playout phase-1 setup runbook and verification checklist"
```

---

### Task 19: CLAUDE.md and the install line

**Model hint:** sonnet

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: the commands and package names above.
- Produces: repo guidance that mentions transmitter and antenna.

- [ ] **Step 1: Edit CLAUDE.md**

1. In **Commands**, the Setup line becomes:

```
- Setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"`
```

2. Append to **Commands** (after the emcee bullet):

```
- Run (transmitter, playout on hugo — phase 1): `transmitter run` (service
  loop: plan/render below the low-water lead, publish + prune every minute),
  `transmitter plan|render|publish|status`, `transmitter fallback render
  <loop> [--notice <file>]`, `transmitter config init`. State in
  `~/.transmitter/` (`TRANSMITTER_ROOT`); R2 keys from `R2_ACCESS_KEY_ID` /
  `R2_SECRET_ACCESS_KEY`. Tests: `packages/transmitter/tests_transmitter/`
  (a package, NOT `tests/`: llama's test modules are top-level and emcee's are
  the `tests` package, so the name would collide); ffmpeg-dependent tests
  skip without ffmpeg; `packages/transmitter/scripts/test-in-debian12.sh`
  runs them on hugo's Python 3.11 + ffmpeg 5.1. Container spike:
  `python -m transmitter.spike build|serve <dir>`.
- antenna (cron-only Cloudflare Worker + static player): `cd antenna && npm
  test` (vitest in the Workers runtime via `@cloudflare/vitest-plugin`),
  `npx wrangler deploy`, `ANTENNA_BUCKET=<bucket> npm run deploy:assets`.
  Cloud setup and the phase-1 verification checklist: `docs/playout-setup.md`.
```

3. Append to **What this is** (after the emcee paragraphs):

```
`transmitter` (dist `llama-transmitter`, CLI `transmitter`) is the playout
side, reading the station root (over NFS on hugo) and never importing llama or
emcee (enforced by `test_no_llama_or_emcee_imports.py`). The stream is a
function of the wall clock: segment N is AAC frames [441N, 441N+441) of one
frame line whose frame 0 sits at the epoch, d = 10.24 s exactly; each show is
encoded once (ffmpeg native `aac`, ADTS) and cut by counting frames, never by
ffmpeg cut points. Segments go to R2 in ascending N and `state/horizon.json`
only advances past confirmed PUTs. `antenna/` is a cron-only Worker (no
routes, `workers_dev = false`) that rewrites `live.m3u8` at every grid
boundary, plus the static player; listeners only ever fetch cache-served R2
objects. Design: `docs/superpowers/specs/2026-10-09-playout-design.md`
(phase 1 built; the cost guard, scheduler and full player are phases 2–4).
```

- [ ] **Step 2: Verify**

Run: `./.venv/bin/python -m pytest -q && (cd antenna && npm test)`
Expected: both PASS.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(CLAUDE.md): transmitter and antenna commands and architecture"
```

---

## Appendix A: fMP4 contingency (only if the Task 2 checkpoint fails on the container)

Not executed by default. If the operator's listening test fails criterion (b) or (c)
— or (a) at every segment boundary — the orchestrator stops and this appendix is
turned into a reviewed amendment of Task 4 (and a re-run of the spike) before any
later task proceeds. What changes, precisely:

- **Seam:** `FrameStore.build_segment` is the only caller of `segment.assemble`; the
  fallback builder (Task 13) the other. Both switch to an fMP4 fragment writer;
  nothing above them (layout, planner, render, publisher ordering) changes, because
  the frame line and its counting are container-independent.
- **Init segment:** one per epoch at `seg/<epoch_id>/init.mp4` (immutable), uploaded
  before the first media segment of the epoch and recorded in `state/horizon.json`
  (`container: "fmp4"`). Boxes: `ftyp` (major `iso6`, compatible `iso6 cmfc mp41`);
  `moov` → `mvhd` (timescale 1000, duration 0), `trak` → `tkhd` (track 1, enabled,
  volume 0x0100), `mdia` → `mdhd` (timescale **44100**), `hdlr` (`soun`), `minf` →
  `smhd`, `dinf`/`dref` (self-contained `url `), `stbl` → `stsd` with one `mp4a`
  sample entry (2 channels, 16-bit, rate 44100<<16) carrying `esds` whose
  DecoderSpecificInfo is the 2-byte AudioSpecificConfig `0x12 0x10` (AAC-LC,
  44.1 kHz, stereo) and empty `stts`/`stsc`/`stsz`/`stco`; `mvex` → `trex`
  (default sample duration 1024).
- **Media segment N:** `moof` → `mfhd` (sequence N+1), `traf` → `tfhd`
  (default-base-is-moof), `tfdt` version 1 with **baseMediaDecodeTime = N·451584**
  (= N·d in the 44100 timescale, the fMP4 counterpart of the ID3 timestamp — no
  2^33 wrap), `trun` with data-offset and 441 sample sizes (each ADTS frame's size
  minus its 7-byte header), every sample duration 1024; then `mdat` holding the 441
  raw AAC access units (ADTS headers stripped). Fallback segment k: tfdt = k·451584
  with its own init at `fallback/<v>/init.mp4`.
- **Playlist (Task 15):** `#EXT-X-VERSION:7` and `#EXT-X-MAP:URI="seg/<epoch_id>/init.mp4"`
  before the first live segment, re-emitted with the fallback init after each
  live↔fallback switch; segment URIs keep their keys with `.m4s`.
- **Tests:** a box-structure test (parse back `tfdt`, `trun` sample count/sizes, the
  `esds` ASC) and the spike re-run in fMP4 mode with the same pass criteria.

## Out of scope here (phases 2–4) and the seams left for them

- **Cost guard, blocking, WAF kill switch reconciliation, cloud alerts incl. the
  published-lead-below-floor alert** (phase 2):
  `antenna/src/clock.ts` `guardStep()` is called first in every invocation and is a
  no-op; `state/guard.json` is already honoured by transmitter (absent = not tripped,
  unreadable = blocked). The kill-switch rule is created disabled by the runbook.
- **`transmitter budget` / `offair` commands, hugo alerts (SMTP/ntfy, dedupe in
  `alerts.json`), dead-clock check, systemd unit, full `status`** (phase 2):
  `transmitter.alerts.alert()` is the single call site to extend; phase 1 writes
  `state/offair.json` by hand (only its `offair` boolean is honoured; `until` is
  informational until phase 2 defines it).
- **Scheduler: anchors, windows, pools, preferences, fill search, variety guards,
  window misses, `aired.jsonl` rotation history, `schedule` / `library` commands**
  (phase 3): replace `planner.choose_next` / `extend`; `plan.jsonl`, the recovery cut,
  re-plan-at-boundary and frozen-means-rendered rules stay. `timeline.json` already
  carries `anchors: []` and a plan-derived `recent` list.
- **Full antenna** (phase 4): designed player and show pages, `embed.html`, Media
  Session, Open Graph per show on `index.html` (the clock rewriting `index.html` at
  show boundaries and on blocked-state changes — phase 1's `index.html` is static and
  the clock does not read `timeline.json`), schedule/history UI, the Playwright smoke
  test against a local R2 emulation.
