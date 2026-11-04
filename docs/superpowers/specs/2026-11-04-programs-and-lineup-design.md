# Programs and the weekly lineup on the player page: design

Date: 2026-11-04. Status: approved in conversation; reviewed (two rounds, six Opus reviews, foundation sound); awaiting Shawn's read.

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

- **Program title.** Only emcee's config knows it (`[assign.profiles.<profile>] title = "..."` in `~/.emcee/config.toml`, resolved by `emcee.process.assignment_for`). hugo never sees that file, and the manifest records the voicing profile and presenter but not the title. So emcee records the title in the manifest's `dj_audio` block (a new optional field, carried by `DJAudioBlock` so the voicing path keeps writing through `rewrite_manifest`). The transmitter reads it from the manifest at publish time and publishes it per show. A ticket whose show has no title keeps `LMA RADIO PRESENTS`. Limitation: if a manifest read fails during one publish (e.g. NFS ESTALE mid-rename), that show's ticket shows `LMA RADIO PRESENTS` until the next publish.
- **Block of each upcoming show.** Already recorded: every persisted plan row carries `block` (the clock block name) and `nominal_start`. That pair is a block occurrence's identity, used in the same format on every side (plan rows, timeline, lineup). Block titles come from the clock, which the publish step loads itself (`Publisher` holds none; `live_clock(ws, save=False)`, as `service.py` does): `clock.toml`, falling back to `clock.last-good.toml`, then the implicit open clock. A block's displayed title is its clock title, else its name, everywhere (including a block no longer in the clock). Rows from before the scheduler (no `block`) get no heading.
- **A block occurrence's span** runs from its first planned row's start to the first row of the following occurrence, interstitials included. The transmitter computes each upcoming occurrence's start and end from the full persisted plan and publishes them; the end is omitted when no row of the following occurrence is in the plan, and the heading then shows the start alone. The page does not derive spans from `timeline.json`'s show rows.
- **Weekly lineup.** The transmitter publishes, next to `timeline.json` and rewritten only when its content changes, the nominal block occurrences from 24 h before now through 8 days after now, from the clock's existing occurrence expansion, each with its identity, title, start and end as UTC instants, and a variety flag. The page shows seven tabs, today and the next six days in the listener's zone, grouping occurrences by listener-local date (not weekday), so today's tab holds today's earlier blocks and no block appears twice. The page only formats instants in the listener's zone (the existing `airTime`); the browser does no time-zone arithmetic. A block is variety when it lists no profiles or more than one (the live clock's Early Variety lists two).
- **On air now** in the lineup is the on-air show's block from the timeline (the actual plan), not the nominal clock, matched to a lineup entry on block name plus nominal start.

## Show page too (Claude's call, for Shawn to check)

The program title also replaces `LMA RADIO PRESENTS` on the big ticket in the in-page show panel (`panel.js`) and on the server-rendered `show/<slug>.html` (`antenna/templates/show.html`), so a show names its program the same way everywhere. The title therefore also goes into `notes/<slug>.json`; a title change changes the notes digest, so the page republishes.

## The title (Claude's call, for Shawn to check)

The title is the program's current name: `assignment_for(config, <voicing profile>).title`, where the voicing profile is `station.manifest_voiced_profile` (it falls back to `source.profile` for the 197 voiced shows whose `dj_audio` has no `profile`). The title follows the voicing profile's current assignment only. When a program is renamed or loses its title in the config, the next resync writes the new title or clears it to null. Limitation: the recorded presenter is not consulted, so after a rename the ticket shows the new name while older audio may speak the old one until the show is re-voiced, and a show voiced by the default presenter under a profile that later gains a titled assignment gets that title.

## The title backfill (Claude's calls, for Shawn to check)

An `emcee` subcommand stamps already-voiced shows and resyncs titles after a config edit, without re-voicing. It is dry-run first and `--yes` second, with the same dry-run and confirm behaviour as `emcee run`; `--yes` prints every write (slug, old title -> new title). It cannot use `rewrite_manifest`, which takes typed blocks and rewrites both, so it has its own raw single-field writer:

- Read the manifest bytes. Refuse unless `dj_audio` is a dict and the bytes reproduce exactly as `json.dumps(m, indent=2) + "\n"` (all 710 voiced manifests do today; 173 would not with `ensure_ascii=False`, so the default stays). Manifests emcee already treats as unsupported (pre-v3, unreadable) are refused too. `dj_audio` stays a raw dict, never round-tripped through `DJAudioBlock`.
- Skip, without writing: a show whose stored title already equals the target (an absent `title` key and null are the same title, and neither is written over the other; only additions, changes, and clears of a present title are written); a show with a non-null `awaiting_fix` (136 today), listed in the output, because any write changes its sha256 and breaks `bulk_apply unmark` for it (it gets the title when re-delivered and re-voiced).
- On `--yes`, refuse while any other `emcee` or `llama` process runs (a `ps` check like `station_mark.emcee_running()`): it is the only guard against tools that ignore the station lock, the one-off `scripts/backfill_*.py` and the campaign worktree pinned at llama v2.20.1.
- The station lock is taken after the operator confirms (at the start with `--yes`) and held for the whole write phase. Under it the backfill re-reads every planned package and refuses the whole run, writing nothing, if any manifest's bytes differ from those its plan was built from.
- Before writing a show, save its original manifest bytes and their sha256 under a timestamped directory in the emcee root. If that backup write or its flush fails, abort before writing the show. A hand restore puts a file back only where its current sha256 equals the one this run wrote (the `put_back` rule).
- Set only the title key. Immediately before the rename, re-read and compare the bytes; on any change skip the show and list it. Write the temp file, fsync it, set its mtime to the original's (`os.utime`), then rename; after the rename, check the mtime and re-apply it if it differs. The transmitter treats a manifest younger than `quiet_minutes` (10 on hugo) as ineligible and drops planned shows (precedent: `scripts/backfill_voiced_on.py`), and hugo's NFS attribute cache can show a post-rename mtime for up to ~60 s if the mtime is restored only after the rename.
- After the rename, re-read and verify every other key is unchanged. On failure, put the original bytes back only if the file still holds exactly the bytes this run wrote; then stop the run, list the show, and exit non-zero (as llama's `station_mark._rewrite` does).

## The station lock (Shawn: a general emcee lock, "good in general"; mechanics are Claude's calls)

- **Location.** A fixed file name in the station's delivered folder, the directory holding the package directories. For `emcee voice <dir>` that is the package directory's parent; llama derives the same path from the parent of the package directory it writes. The path and file format are part of the on-disk contract, since llama cannot import emcee.
- **emcee.** `run` and `voice` take it per package, from the re-read of that package's manifest through its last write (clips and manifest), and release it before the next package, so llama is shut out for at most one package's voicing, never a whole run. The title backfill holds it for its whole write phase (seconds to minutes; see above). `move` does not take it (it writes `<emcee root>/moves.json`, which already has its own flock), nor does `say` (it writes audio clips, not manifests). If a package's lock is held by someone else partway through a run, the run stops there, lists the packages it did not attempt, and exits non-zero. Read-only commands do not take it. The one-off scripts that import emcee (`scripts/backfill_*.py`) are not lock-aware; that is a documented limitation.
- **llama.** llama takes it per show, from its first read of the station copy through its last station write of that show: in `llama deliver` to a station, from reading the destination manifest through the directory swap or overlay copy; likewise in `clear-mark` and each `bulk_apply` mark, clear and put-back step. One shared helper in llama does this for all callers. On a held lock a single command exits 1 naming the holder and the emcee command that shows and clears locks; a batch (a deliver batch, a `bulk_apply` loop) stops at that show and lists what it did not attempt. A delivery during an emcee run may have to be retried after the current package; that is accepted and documented. The existing `station_mark.emcee_running()` `ps` refusal (`clear-mark` in llama's `cli.py`, three places in `scripts/bulk_apply.py`) stays as well.
- **Who acquires.** Only command entry points (and `bulk_apply`'s per-show step) acquire the lock; library write functions never do. The lock is not re-entrant: a second acquire in one process is a bug, and tests must catch it. No tool holds the lock while waiting on an operator prompt; a tool that prompts takes the lock after the answer and re-reads what it decided on under it.
- **Protocol.** Exclusive create (`O_CREAT|O_EXCL`), then write a random token plus human-readable holder text (tool, command, host name, pid, start time). The holder text is for the operator only; no tool parses it to judge liveness. A held lock is refused, naming the holder; an empty or unparseable lock counts as held. Release runs in `finally`, with SIGTERM and SIGHUP handlers that raise into it; it re-reads the file and unlinks only if it finds its own token, and on a foreign token warns that its later writes ran unguarded. A held lock is never broken automatically and never expires: an explicit emcee command prints the holder text and removes the lock on the operator's say-so.
- **Across hosts.** Shawn foresees the transmitter on hugo invoking emcee to voice announcements. That is out of scope, but the lock must not rule it out. It must be correct between processes on the Mac (required; tested at go-live, see Rollout). The Mac mounts the share over SMB and hugo over NFSv3 (`local_lock=none`); a best-effort check that exclusive create is atomic between the two is a go-live item, and if it cannot be shown it is written down as an unverified limitation for the future hugo integration.

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
4. Go-live checks, each recorded in the run's notes: two processes on the Mac race exclusive create and unlink on a scratch name in the real delivered folder about 1,000 times with no double acquisition (the required property, which unit tests on local disk do not show); a scratch file written over SMB with its mtime set before rename reads back on hugo (`stat`) with the original mtime, immediately and after 60 s; and the best-effort cross-host lock check (above).
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
