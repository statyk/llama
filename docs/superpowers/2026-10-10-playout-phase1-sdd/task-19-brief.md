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
