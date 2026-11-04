# Programs and the weekly lineup on the player page: design

Date: 2026-11-04. Status: approved in conversation, pending written review.

## Intent

The player page (antenna's `listen.lma-radio.com`) shows upcoming and recent shows as concert tickets, but nothing on it tells a listener that the station has regular programs at regular times: Funk on Monday and Saturday nights, Bluegrass in the morning, a Dead block every evening. Shawn wants the page to say so in three ways:

1. **Program name on every ticket.** Each show was voiced as a program, the emcee title for its profile ("Gravel & Steel", "One More from the Archive"). The ticket shows it.
2. **Upcoming tickets grouped by clock block.** "Coming up" is split under the `clock.toml` block each show was scheduled into ("Bluegrass in the Morning"), with that block's actual start and end after the scheduler's adjustments.
3. **A standing weekly lineup.** A static view of `clock.toml`: which block runs at which time on which day, independent of what the scheduler has actually planned.

Programs (emcee profile titles) and blocks (clock.toml) are different things and must stay visibly distinct. A block can hold several programs (Afternoon Variety plays any of them), and a profile block's title need not match its program's title ("Mid-morning Dead" plays "One More from the Archive"). Where a block and a program share a name ("Gravel and Steel" / "Gravel & Steel"), Shawn may rename the block in `clock.toml` later; nothing here depends on that.

## Decisions (Shawn's, from the mockups)

- **Ticket:** the program title replaces the `LMA RADIO PRESENTS` line (mockup option A). The stub is unchanged. Applies to every ticket: Coming up, Just aired, and the show page (see the calls below).
- **Coming up:** grouped under block headings (option A). Each heading: the block title on the left, the block's actual span on the right ("7:00a – 9:56a"), in the page's existing small-caps style. A block's tickets start a new row; a short block leaving empty grid cells on desktop is accepted.
- **Weekly lineup:** a day picker (option C) on desktop and phone alike, for consistency. One tab per day, today's tab selected on load; the selected day lists that day's blocks, each with its start time and title. Variety (open) blocks are styled differently from profile blocks (the mockup used italics), since any program can appear in them.
- **Placement** (proposed by Claude, accepted): the lineup is a new section at the bottom of the page, below Just aired, headed "The weekly lineup". The block on air now is highlighted in today's tab. Just aired keeps its flat list (no block headings).
- **Times** follow the listener's time zone, like the rest of the page ("Times shown in Eastern Time" is the listener's zone label). The lineup converts clock-zone start times to the listener's zone, so for a listener west of the clock's zone a block near midnight moves to the neighbouring day. That is intended.
- Review mode: **Opus**.

## Stakes

The page is public and the station is about to be shared, but everything shown here is derived, regenerated on every publish, and reversible by a revert and redeploy. The one **strict** surface is the station manifests: emcee rewriting `manifest.json` in delivered packages on the station share (`/Volumes/media/lma-radio/delivered/`), including any backfill over already-voiced shows. A bad write there can make a show unairable or lose voicing records. Those writes must go through emcee's existing atomic manifest rewrite (emcee takes no lock; see Concurrency below), preserve every field they do not own (including `awaiting_fix`), and refuse rather than guess on an unreadable or legacy manifest. The transmitter and the page only read.

## Where the data comes from

- **Program title.** Only emcee's config knows it (`[assign.profiles.<profile>] title = "..."` in `~/.emcee/config.toml`, resolved by `emcee.process.assignment_for`). hugo never sees that file, and the manifest records the voicing profile (`dj_audio.profile`) and presenter but not the title. So emcee records the title in the manifest's `dj_audio` block when it voices a package (a new optional field; null when the assignment has no title, e.g. the `[assign] default` presenter or the house narrator). The transmitter reads it from the manifest and publishes it per show.
- **Already-voiced shows** carry no title until something stamps it. A re-runnable `emcee` subcommand writes the title for the package's recorded voicing profile into `dj_audio` without re-voicing, and also resyncs titles after a title is edited in the emcee config. It writes only that field, through the strict-surface rules above. A ticket whose show has no title keeps `LMA RADIO PRESENTS`.
- **Block of each upcoming show.** Already recorded: every persisted plan row carries `block` (the clock block name) and `nominal_start`, which together identify the block occurrence. Block titles come from the clock the transmitter already loads (`clock.toml`, falling back to `clock.last-good.toml`, then the implicit open clock). A row whose block no longer exists in the clock (renamed or removed since planning) shows the block name as its title. Rows from before the scheduler (no `block`) get no heading.
- **A block occurrence's actual span** is from its first planned row's start to its last row's end, interstitials included (so it runs up to the next block's actual start).
- **Weekly lineup** is a straight read of the clock: timezone, and per block its title (or name), days, start, and whether it is an open block (no `profiles`). The transmitter publishes it as a small JSON object next to `timeline.json`, rewritten only when its content changes.

## Calls made after the builder check (Claude's, for Shawn to check)

- **Show page too.** The program title also replaces `LMA RADIO PRESENTS` on the big ticket in the in-page show panel (`panel.js`) and on the server-rendered `show/<slug>.html` (`antenna/templates/show.html`), so a show names its program the same way everywhere. That means the title also goes into `notes/<slug>.json`, and a title change changes the notes digest, so the page republishes.
- **Old voicing blocks.** For a `dj_audio` block without a `profile` key (voiced before 2026-10-16), the backfill uses emcee's existing rule, `station.manifest_voiced_profile`, which falls back to `source.profile`, and stamps those shows too. Such blocks are written as raw dicts, never round-tripped through `DJAudioBlock`. Only manifests emcee already treats as unsupported (pre-v3, unreadable) are refused.
- **What the title means.** The stamped title is the one the show was voiced under, because the presenter speaks it in the DJ script. The resync writes the current config title for the recorded voicing profile only when the current assignment for that profile names the same presenter the block records. Otherwise it skips the show and lists it in the report (it needs re-voicing, not a new title). It never clears an existing title to null. House-narrator and default-presenter shows get no title.
- **Concurrency: a general emcee station lock (Shawn, 2026-11-04: "good in general").** emcee takes no lock today. This project adds one: every emcee command that writes under a station root (`run`, `voice`, `move`, the new title backfill, and any other writer) holds a station-wide lock for its whole write phase and refuses, naming the holder, when another holds it; read-only commands (`status`, dry runs) do not take it. The backfill is an `emcee` subcommand, dry-run first and `--yes` second like `emcee run`, writing through emcee's existing atomic manifest rewrite.
  - **Across hosts.** Shawn foresees the transmitter on hugo invoking emcee locally to voice announcements, so two hosts (the Mac and hugo) may one day run emcee against the same network share. That integration is out of scope, but the lock must not rule it out: it lives on the share itself and must work between hosts, which `flock` over SMB/CIFS does not reliably do. So: a lock file created exclusively on the share, recording host, pid and start time, with a documented way to clear a stale one (same host: the pid is gone; another host: operator decision, never automatic). The builder confirms exclusive create behaves atomically on the actual share from both the Mac and hugo, or says plainly that it could not be verified.
  - **llama.** llama's `station_mark` currently refuses while an `emcee` process runs (a local `ps` check). It should also refuse while the station lock file exists. The lock file's path and format become part of the on-disk contract, since llama cannot import emcee.

## Constraints

- `emcee`, `transmitter` and `llama` never import each other; the delivered package on disk is the only contract between emcee and the transmitter (repo `CLAUDE.md`). The new `dj_audio` field is that contract.
- The transmitter's cached show analysis (`ShowAnalysis.meta`) is keyed by the audio file set and is not refreshed when only the manifest changes, so a title stamped after analysis must reach the page by reading the manifest at publish time (as `_publish_site` already does for notes), not through cached meta.
- `timeline.json` keeps its existing fields and meaning; additions only. Its existing ordering rule holds: a show's notes and page go up before any timeline that lists it.
- The page keeps its current look (cassette and concert tickets, `antenna/public/assets/radio.css`). No new client-side settings.
- One `emcee run` at a time per station root. llama's marking refuses while an `emcee` process runs; the backfill also refuses while another `emcee` process runs.
- Rollback stays a revert plus `wrangler deploy` for the page, and a revert plus hugo pull and restart for the transmitter.
- **The run goes all the way to live** (Shawn): merged and reviewed code, hugo pull and restart, `wrangler deploy`, a signed and notarized emcee release installed on the Mac, and the title backfill applied to the station share. Safe order: transmitter and page first (they tolerate a missing title), then the emcee release, then the backfill. Every station write keeps the operator gate: the agent runs the dry run, shows it, and passes `--yes` only after Shawn approves, in a separate tool call.

## Non-goals

- Renaming clock blocks (Shawn's call, any time, in `clock.toml`).
- Grouping Just aired by block.
- Showing presenters on the page.
- The transmitter invoking emcee, and running emcee on hugo at all (the lock only must not rule it out).
- A separate schedule page or calendar export.
- Changing what the cassette label or the now-playing line shows.

## Left to the builder

- Field names and exact JSON shapes for the program title in `dj_audio`, the per-show additions to `timeline.json`, block occurrence records, and the lineup object (and its R2 key and cache lifetime).
- How the page handles a missing lineup object or missing block data (hide the section or heading, never break the page).
- Exact styling within the existing look, including the variety-block style and the on-air highlight.
- How "Show all" in Coming up interacts with the block headings (it currently reveals more tickets).
