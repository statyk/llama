# Programs and the weekly lineup on the player page: design

Date: 2026-11-04. Status: approved in conversation, pending written review.

## Intent

The player page (antenna's `listen.lma-radio.com`) shows upcoming and recent shows as concert tickets, but nothing on it tells a listener that the station has regular programs at regular times: Funk on Monday and Saturday nights, Bluegrass in the morning, a Dead block every evening. Shawn wants the page to say so in three ways:

1. **Program name on every ticket.** Each show was voiced as a program, the emcee title for its profile ("Gravel & Steel", "One More from the Archive"). The ticket shows it.
2. **Upcoming tickets grouped by clock block.** "Coming up" is split under the `clock.toml` block each show was scheduled into ("Bluegrass in the Morning"), with that block's actual times after the scheduler's adjustments.
3. **A standing weekly lineup.** A view of `clock.toml`: which block runs at which time on which day, independent of what the scheduler has actually planned.

Programs (emcee profile titles) and blocks (clock.toml) are different things and must stay visibly distinct. A block can hold several programs (Afternoon Variety plays any of them), and a profile block's title need not match its program's title ("Mid-morning Dead" plays "One More from the Archive"). Where a block and a program share a name ("Gravel and Steel" / "Gravel & Steel"), Shawn may rename the block in `clock.toml` later; nothing here depends on that.

## Decisions (Shawn's, from the mockups)

- **Ticket:** the program title replaces the `LMA RADIO PRESENTS` line (mockup option A). The stub is unchanged. Applies to every ticket: Coming up, Just aired, and the show page (see "Show page too" below).
- **Coming up:** grouped under block headings (option A). Each heading: the block title on the left, the block's actual span on the right ("7:00a – 9:56a"), in the page's existing small-caps style. A block's tickets start a new row; a short block leaving empty grid cells on desktop is accepted.
- **Weekly lineup:** a day picker (option C) on desktop and phone alike, for consistency. One tab per day, today's tab selected on load; the selected day lists that day's blocks, each with its start time and title. Variety blocks are styled differently from single-profile blocks (the mockup used italics), since more than one program can appear in them.
- **Placement** (proposed by Claude, accepted): the lineup is a new section at the bottom of the page, below Just aired, headed "The weekly lineup". The block on air now is highlighted in today's tab. Just aired keeps its flat list (no block headings).
- **Times** follow the listener's time zone, like the rest of the page ("Times shown in Eastern Time" is the listener's zone label), so for a listener west of the clock's zone a block near midnight moves to the neighbouring day. That is intended.
- **The run goes all the way to live** (see Rollout).
- Review mode: **Opus**.

## Stakes

The page is public and the station is about to be shared, but everything shown on it is derived, regenerated on every publish, and reversible by a revert and redeploy. The **strict** surfaces are the station share (`/Volumes/media/lma-radio/delivered/`, 2,786 packages, 710 voiced): emcee rewriting `manifest.json` there, including the title backfill over the 710 already-voiced shows, and the new station lock that emcee and llama both take. A bad manifest write can make a show unairable or lose voicing records; a bad lock can let two writers collide or wedge every writer. Station writes preserve every field they do not own (including `awaiting_fix`) and refuse rather than guess on an unreadable or legacy manifest. The transmitter and the page only read.

## Where the data comes from

- **Program title.** Only emcee's config knows it (`[assign.profiles.<profile>] title = "..."` in `~/.emcee/config.toml`, resolved by `emcee.process.assignment_for`). hugo never sees that file, and the manifest records the voicing profile and presenter but not the title. So emcee records the title in the manifest's `dj_audio` block (a new optional field, carried by `DJAudioBlock` so the voicing path keeps writing through `rewrite_manifest`). The transmitter reads it from the manifest at publish time and publishes it per show. A ticket whose show has no title keeps `LMA RADIO PRESENTS`.
- **Block of each upcoming show.** Already recorded: every persisted plan row carries `block` (the clock block name) and `nominal_start`, which together identify the block occurrence. Block titles come from the clock, which the publish step loads itself (`Publisher` holds none; `live_clock(ws, save=False)`, as `service.py` does): `clock.toml`, falling back to `clock.last-good.toml`, then the implicit open clock. A row whose block no longer exists in the clock shows the block name as its title. Rows from before the scheduler (no `block`) get no heading.
- **A block occurrence's span** runs from its first planned row's start to the first row of the following occurrence, interstitials included. The end is shown only when a row of the following occurrence is in the plan; otherwise the heading shows the start alone.
- **Weekly lineup.** The transmitter publishes, next to `timeline.json` and rewritten only when its content changes, the next 7 days of nominal block occurrences from the clock's existing occurrence expansion, each with block name, title, start and end as UTC instants, and a variety flag. The page only formats instants in the listener's zone (the existing `airTime`); the browser does no time-zone arithmetic. A block is variety when it lists no profiles or more than one (the live clock's Early Variety lists two).
- **On air now** in the lineup is the on-air show's block from the timeline (the actual plan), not the nominal clock.

## Show page too (Claude's call, for Shawn to check)

The program title also replaces `LMA RADIO PRESENTS` on the big ticket in the in-page show panel (`panel.js`) and on the server-rendered `show/<slug>.html` (`antenna/templates/show.html`), so a show names its program the same way everywhere. The title therefore also goes into `notes/<slug>.json`; a title change changes the notes digest, so the page republishes.

## The title (Claude's call, for Shawn to check)

The title is the program's current name: `assignment_for(config, <voicing profile>).title`, where the voicing profile is `station.manifest_voiced_profile` (it falls back to `source.profile` for the 197 voiced shows whose `dj_audio` has no `profile`). Shows voiced by the default presenter or the house narrator get no title. When a program is renamed or loses its title in the config, the next resync writes the new title or clears it to null. Limitation: after a rename the ticket shows the new name while older audio may speak the old one until the show is re-voiced.

## The title backfill (Claude's calls, for Shawn to check)

An `emcee` subcommand stamps already-voiced shows and resyncs titles after a config edit, without re-voicing. It is dry-run first and `--yes` second, with the same dry-run and confirm behaviour as `emcee run`; `--yes` prints every write (slug, old title -> new title). It cannot use `rewrite_manifest`, which takes typed blocks and rewrites both, so it has its own raw single-field writer:

- Read the manifest bytes. Refuse unless `dj_audio` is a dict and the bytes reproduce exactly as `json.dumps(m, indent=2) + "\n"` (all 710 voiced manifests do today; 173 would not with `ensure_ascii=False`, so the default stays). Manifests emcee already treats as unsupported (pre-v3, unreadable) are refused too. `dj_audio` stays a raw dict, never round-tripped through `DJAudioBlock`.
- Skip, without writing: a show whose stored title already equals the target; a show with a non-null `awaiting_fix` (136 today), listed in the output, because any write changes its sha256 and breaks `bulk_apply unmark` for it (it gets the title when re-delivered and re-voiced).
- Before writing, save each show's original manifest bytes under a timestamped directory in the emcee root, so a bad run can be restored by hand.
- Set only the title key. Immediately before the rename, re-read and compare the bytes; on any change skip the show and list it. Write with fsync. After the rename, re-read and verify every other key is unchanged.
- Restore the manifest's previous mtime (`os.utime`): the transmitter treats a manifest younger than `quiet_minutes` (10 on hugo) as ineligible and drops planned shows (precedent: `scripts/backfill_voiced_on.py`).

## The station lock (Shawn: a general emcee lock, "good in general"; mechanics are Claude's calls)

- **Location.** A fixed file name in the station's delivered folder, the directory holding the package directories. For `emcee voice <dir>` that is the package directory's parent; llama derives the same path from the parent of the package directory it writes. The path and file format are part of the on-disk contract, since llama cannot import emcee.
- **emcee.** `run`, `voice` and the title backfill take it for the whole scan-plan-write sequence of the `--yes` path, taken before the scan the plan comes from. It may instead be left unheld while a dry run or confirm prompt waits, in which case the writes re-validate each package. `move` does not take it (it writes `<emcee root>/moves.json`, which already has its own flock), nor does `say` (it writes audio clips, not manifests). Read-only commands do not take it. Acquisition lives in an emcee library function. The one-off scripts that import emcee (`scripts/backfill_*.py`) are not lock-aware; that is a documented limitation.
- **llama.** llama takes the lock (create, write, release) around each station write: `clear-mark`, the `bulk_apply` mark, clear and put-back loops, and `llama deliver` to a station (it swaps whole package directories). One shared helper in llama does this for all callers. Today `station_mark` exposes `emcee_running()` (a local `ps` check) and the callers refuse on it (`clear-mark` in llama's `cli.py`, three places in `scripts/bulk_apply.py`); that check stays as well.
- **Protocol.** Exclusive create (`O_CREAT|O_EXCL`), then write: a random token, a stable host id (not raw `gethostname()`, which changes with the network on macOS), pid, the process's start time, and the command. An empty or unparseable lock counts as held. Release re-reads the file and unlinks only if it finds its own token. A held lock is refused, naming the holder, and never broken automatically, not even on the same host, and never expires by age: an explicit emcee command shows the holder (and, on the same host, whether that pid with that start time is still alive) and removes the lock on the operator's say-so.
- **Across hosts.** Shawn foresees the transmitter on hugo invoking emcee to voice announcements. That is out of scope, but the lock must not rule it out. It must be correct between processes on the Mac (required, tested). The Mac mounts the share over SMB and hugo over NFSv3 (`local_lock=none`); a best-effort check that exclusive create is atomic between the two is a go-live item, and if it cannot be shown it is written down as an unverified limitation for the future hugo integration.

## Constraints

- `emcee`, `transmitter` and `llama` never import each other; the delivered package on disk is the only contract (repo `CLAUDE.md`). The new `dj_audio` field and the station lock file are part of that contract.
- The transmitter's cached show analysis (`ShowAnalysis.meta`) is keyed by the audio file set and is not refreshed when only the manifest changes, so a title stamped after analysis must reach the page by reading the manifest at publish time (as `_publish_site` already does for notes), not through cached meta.
- `timeline.json` keeps its existing fields and meaning; additions only. Its existing ordering rule holds: a show's notes and page go up before any timeline that lists it.
- The page keeps its current look (cassette and concert tickets, `antenna/public/assets/radio.css`). No new client-side settings.
- Rollback: for the page, a revert then the deploy steps in reverse (`wrangler deploy`, `npm run deploy:assets`, `npm run pages`); for the transmitter, a revert plus hugo pull and restart.

## Rollout (Shawn: the run goes all the way to live)

1. Merged and reviewed code.
2. Transmitter and page first (they tolerate a missing title): hugo pull and restart; `npm run pages`, `npm run deploy:assets`, then `wrangler deploy`.
3. Signed and notarized emcee and llama releases, installed on the Mac. The bulk-apply campaign runs from a worktree pinned at llama v2.20.1 and is stopped; add a note to its handoff that it must be re-pinned to the new llama tag before it resumes, rather than re-pinning now.
4. The best-effort cross-host lock check (above).
5. The title backfill. The backfill changes the sha256 of voiced manifests, so a pending bulk-apply wave snapshot restore covering a stamped show would refuse with a station-changed error: Shawn says first whether any wave reversal is still wanted. Run the dry run and show it; then, after Shawn approves and in a separate tool call, `--yes`, soon after hugo has filled to `lead_hours` (check `transmitter status`) as a second guard on top of the mtime restore.

Every station write keeps the operator gate: the agent runs the dry run, shows it, and passes `--yes` only after Shawn approves.

## Also changes

- Root `CLAUDE.md` and `packages/emcee/CLAUDE.md` say emcee takes no lock; update them.
- llama's hand-kept `DJAudio` copy (`packages/llama/src/llama/models.py`) gains the title field.
- `renderTickets`' rebuild key in `page.js` includes the title.
- `antenna/templates/show.html` hardcodes `LMA RADIO PRESENTS`; it gets an escaped template variable.

## Non-goals

- Renaming clock blocks (Shawn's call, any time, in `clock.toml`).
- Grouping Just aired by block.
- Showing presenters on the page.
- The transmitter invoking emcee, and running emcee on hugo at all (the lock only must not rule it out).
- A separate schedule page or calendar export.
- Changing what the cassette label or the now-playing line shows.

## Left to the builder

- Field names and exact JSON shapes for the program title in `dj_audio`, the per-show additions to `timeline.json`, block occurrence records, and the lineup object (whether it also carries the weekly rules, its R2 key and cache lifetime).
- The lock file's name and encoding, within the contract above.
- How the page handles a missing lineup object or missing block data (hide the section or heading, never break the page).
- Exact styling within the existing look, including the variety-block style and the on-air highlight.
- How "Show all" in Coming up interacts with the block headings (it currently reveals more tickets).
