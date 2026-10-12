# Binding constraints for every reviewer (verbatim from plan Global Constraints + spec Stakes)

## Stakes

What is at risk is **money and on-air continuity**, not data. transmitter only
*reads* the station root; transmitter and antenna write only their own state
(`~/.transmitter/`) and their own R2 bucket. Nothing here deletes or overwrites
anything llama or emcee own, and everything produced is regenerable from the
packages. A bug elsewhere costs dead air, a glitch, a bad schedule, or a re-render.

**One strict surface: spend.** The operator's ceiling is "a few tens of dollars a
month", after which the station is shut down. Cloudflare has no account spending
cap, so the design enforces it: every listener path is a cache-served static
object (no per-listener billing), the clock's `#EXT-X-ENDLIST` playlist stops
players, the WAF kill switch blocks the hostname, and the cost guard fails closed
when it cannot read usage. A defect there can run up an uncapped bill silently;
treat those paths with the rigor of a migration. Secondary but real: the station
must never list a segment that does not exist (players stall), and must never cut
a performance mid-song (an explicit operator rule).


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
