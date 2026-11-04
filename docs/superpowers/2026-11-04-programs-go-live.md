# Programs and lineup: go-live record (2026-11-04)

Plan `docs/superpowers/plans/2026-11-04-programs-and-lineup.md`, Tasks 15-20. Times Eastern.

## Merge and transmitter (Tasks 14-15)
- 09:19 merged `programs-lineup` into main (`720568c2`) and pushed; suite on main 6890 passed, 1 skipped; antenna 545.
- 09:29 Shawn restarted `transmitter@shawn` on hugo at `720568c2`; NRestarts 0, no alerts, clock `clock.toml`.
- The site publishes only when a segment batch uploads (after a fill), so the first publish with the new data came at 12:19: `timeline.json` with 16 blocks and every show carrying its block; `notes/_lineup.json` 200, `max-age=300`, 73 occurrences.

## Release (Task 17)
- `v2.22.0` was tagged at `720568c2`; its Windows build failed the `emcee --help` smoke test (`AttributeError: module 'signal' has no attribute 'SIGHUP'`: the station lock referenced it at import). No release was published for it.
- Fix `39ef8cc1`: build the signal list from what the platform has; without `pthread_sigmask` take the off-main-thread path (no handlers, nothing masked). Tests in both lock suites; Opus review clean (both mutants caught). Suite 6892 passed, 1 skipped.
- `v2.22.1` released at `39ef8cc1`, all builds green, 8 binaries plus `SHA256SUMS`.
- Shawn installed emcee 2.22.1 on the Mac. llama stays at 2.20.1 by decision (the stopped bulk-apply campaign is pinned to it; old llama keeps its `ps` guard and ignores `dj_audio.title`). The campaign handoff (`~/.llama-harness/bulk-apply/handoff-campaign.md`) records installing llama 2.22.1 and re-pinning before resuming.

## Go-live checks (Task 19)
- hugo's `[station] root`: `/nfs/media/lma-radio/delivered/` (NFSv3). The Mac mounts the share over SMB at `/Volumes/media/lma-radio/delivered`.
- Lock race on the Mac over SMB, `race --n 1000`: `acquired 238 contended 1762 vanished 99 double 0 marker-overlap 0 unreadable 0`, exit 0, no scratch files left (3 min 42 s).
- mtime over SMB read back on hugo: created `.mtime-probe-609a9da8`, hugo `stat` 1793803498; replaced (temp, fsync, close, utime 1767225600, rename); hugo kept its cached entry (1793803498/…499) for about 60 s, then read 1767225600; it never showed the rename's time. Mac read 1767225600. Probe removed.
- Cross-host lock (best effort), `cross --n 300 --start-at <same epoch>`: Mac `acquired 265 contended 35 double 0`, exit 0; hugo `acquired 2 contended 298 double 0`, exit 0. Exclusive create held between SMB and NFSv3 in this run.
- One real retitle write on a scratch station root (`/Volumes/media/lma-radio/retitle-probe/`, a copy of `acousticsyndicate-2004-06-12`'s manifest): written `(none) -> Gravel & Steel`, mtime 1793712710 kept on the Mac and on hugo, mode kept, no lock or temp left. Scratch root removed.

## The title backfill (Task 20)
- Dry run 10:3x: `574 to write, 0 unchanged, 136 awaiting fix, 0 refused, 2076 unvoiced` in 1 min 29 s; titles: One More from the Archive 111, Here Comes the Funk! 106, All Ages 93, Bluegrass Valley 88, Gravel & Steel 74, The Music Never Stopped 61, The Fillmore Annex 41. Shawn approved.
- Run after hugo's fill reached a 23.7 h lead (12:36): `emcee retitle --yes` 12:38, 2 min 14 s, `574 written`, exit 0. Backups `~/.emcee/title-backups/20261104T173830Z/` (574 after lines).
- Verified: dry run then `nothing to write`; all 574 manifests kept their recorded mtime; no station lock left; hugo lead 23.9 h, no alerts, ineligible packages 2212 = 2076 unvoiced + 136 awaiting fix (none dropped as changing).
- Program names reach the page at hugo's next site publish (the next fill).

## Open
- Page deploy (Task 16): the preview round for Shawn, then `deploy:assets` and `wrangler deploy`.
- Deferred: lineup tab ARIA (R16); making `llama deliver`'s overlay copy atomic is Shawn's call.
