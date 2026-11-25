# Concert announcements: local premise checks (Task 5)

Run 2026-11-25 on the operator's Mac, real local mlx-audio server, presenter `roydemure`
(Qwen), STT `mlx-community/whisper-large-v3-turbo-asr-fp16`. No code changed.
Driver: `./.venv/bin/python -m emcee pieces` (module entry; not `.venv/bin/emcee`).
Artifacts (not committed): `~/.llama-harness/concert-announcements/premises/`.

## Gate verdict: HOLD

Step 3: the spike's r1 Voxtral take `frag/06-ryan.mp3` PASSES the strict check
(`strict_problem` = None, three runs, deterministic). The Whisper model transcribes it as
`Ryan Adams.` although the spike recorded Voxtral as losing the "s". The r3 Qwen take is
caught. Step 2's runaway-guard condition was not hit (see below), so the HOLD rests on Step 3.

## Step 1: sample

The live clock was not readable without touching hugo or `~/.transmitter` (no `clock.toml`
in this checkout), so the brief's fallback was used: a two-block test clock (America/New_York,
`Overnight Variety` at 00:00 and `The Music Never Stopped` at 14:00), ID text
"You're listening to LMA Radio. Live concert tapes from the Live Music Archive.", from_us =
2026-11-26 UTC, days = 8. 291 distinct artists from the delivered manifests, 962 needed
pieces. Sample = 60: the 10 shortest, 20 artist pieces chosen for hard names (digits,
punctuation, initialisms, non-ASCII; selector in `build.py`), 30 random others (seed 0).
Note: the sample contains no block-title or ID piece other than `time`/`then`-style
fragments, since the random 30 drew only artist and time pieces; the test clock's block
pieces were not exercised.

## Step 2: voicing (`emcee pieces <dir> --presenter roydemure`)

Summary line: `voiced 50, re-takes 35, failed 10, left 0`. Wall time about 8 min 42 s for 60
pieces (about 8.7 s per piece, no `--limit`).

- Re-takes: 35 re-take lines over 60 pieces = 0.58 per piece; 13 pieces needed at least one
  re-take (22%). 3 pieces re-took then voiced (EOTO x2, U-Melt); 10 failed after 4 takes (17%).
- No take failed on the runaway guard, onset, or no-speech. Every re-take/failure reason was
  a `strict_problem` mismatch (a name the engine pronounces differently or the STT hears
  differently).

Failed pieces (all after 4 takes, `.failed` sidecars):

| id | text | last reason | last transcript |
|---|---|---|---|
| 8e61cad9b8fd | with Raq. | final word "raq" heard as "rack" | with Rack. |
| 917fce394f48 | with Raq, | final word "raq" heard as "rack" | With Rack. |
| 5f9e0e5aa404 | with Emmitt Nershi Band. | names differ by 2 edits | with Emmett Nurshey Band. |
| 6391934e3e89 | with George Porter, Jr. and Runnin' Pardners. | final "pardners" heard "partners" | with George Porter Jr. and Runnin' Partners. |
| 879aee971e4f | with George Porter, Jr. and Runnin' Pardners, | final "pardners" heard "partners" | With George Porter Jr. and running partners, |
| 6851d04fc04f | with The Travelin' McCourys. | final "mccourys" heard "macquaries" | with the Travelin' Macquarie's. |
| 7f4c93cfea25 | with Bonerama. | final "bonerama" heard "bonarama" | with Bonarama. |
| 936326f5a4e4 | followed by Club d'Elf, | final "delf" heard "delph" | Followed by Club Delph. |
| f378cb97258f | with Little Feat, | final "feat" heard "feet" | With little feet. |
| f3cde931b9d6 | with Hayes Carll, | final "carll" heard "carl" | with Hayes Carl. |

Re-take lines for pieces that eventually voiced: `23ae6aba9e99` (followed by EOTO,) x3
"eoto" heard "ioto", then voiced on take 4; `42a92323859f` (with EOTO,) x1 "eoto" heard "to";
`4823abc7d2ed` (with U-Melt.) x1 "melt" heard "mel".

### The 10 shortest pieces

| text | outcome |
|---|---|
| with Low. / with Low, | voiced first take (both) |
| with moe. / with moe., | voiced first take (both) |
| with Zero. / with Zero, | voiced first take (both) |
| with Zwan. | voiced first take |
| with EOTO, | voiced after 1 re-take ("to") |
| with Raq. / with Raq, | FAILED after 4 takes (heard "Rack"); these are two of the shortest 10 |

Raq failed on every take, but through the strict transcript check, not the runaway guard, so
the brief's runaway-guard HOLD condition is not met by it. It does show that very short
single-word names are the weak spot: a mispronunciation or STT disagreement on the name is
also the final word, and there is no template text to absorb it.

### Hard names (which need an `.expect` or lexicon entry)

Of the 20 hard-name picks, 17 voiced (EOTO and U-Melt after re-takes), 3 failed (the two
"Runnin' Pardners" texts and "The Travelin' McCourys"). Of the 30 random others, 5 failed
(Bonerama, Club d'Elf, Little Feat, Hayes Carll, Emmitt Nershi Band) and the rest voiced on
the first take. Failures are pronunciation/spelling cases (Pardners, McCourys, Raq, Feat
heard as "feet", Carll, d'Elf, Bonerama), each needing an `.expect` text or a
pronunciation-lexicon entry; none were digits, initialisms or non-ASCII (those voiced:
7 Walkers, DJ Logic, G. Love, Benevento/Russo, King Gizzard & The Lizard Wizard, Mojave 3,
Hank Williams III, ...And You Will Know Us..., Songs: Ohia).

## Step 3: the swallowed consonant

Both spike takes were present, so no proxy was used. Each was converted with
`ffmpeg -v error -i take.mp3 take.wav` and transcribed with `SttClient` (config `stt_model`).

| take | text | transcript | `strict_problem` |
|---|---|---|---|
| r1 Voxtral `frag/06-ryan.mp3` | `Ryan Adams,` | `Ryan Adams.` | **None (passes)** |
| r3 Qwen `r3/frag/then-2-musicnever.mp3` | `Then, at 2 Eastern, The Music Never Stopped` | `Then at 2 Eastern, the music never stops.` | `final word "stopped" heard as "stops"` (caught) |

The r1 result is deterministic (three runs). The take is 1.2 s long; the lost "s" is audible to
the spike's reviewer but whisper-large-v3-turbo restores "Adams" from context, so the strict
check cannot catch a swallowed final "s" on a name it can complete. The r3 take, a changed
final word, is caught.

## Verdict

HOLD: one Step 3 take passes the strict check (r1). The calibration or the premise (what
the strict check can catch with this STT model) is the operator's call. Also for the operator:
10 of 60 pieces (17%) failed on strict mismatches of unusual names, two of them among the 10
shortest.

## Operator ruling (2026-11-25 09:55, relayed by the orchestrating session)

**Premise ACCEPTED; HOLD lifted.** A swallowed final consonant that Whisper restores from
context goes uncaught by the strict check. Accepted because the presenter `roydemure` voices
on Qwen, whose known-bad take (r3, "stopped" heard as "stops") is caught; the uncaught r1 take
is a Voxtral take. Tightening the name comparison (last word of each title/artist exact) is
approved in principle but deferred to a combined Task 2 follow-up with a pending decision on
phonetic name matching.

## Step 2 re-run under the phonetic rule (2026-11-25, commit 49209191)

Same 60 piece texts (copied into `~/.llama-harness/concert-announcements/premises-t2b/pieces/`;
the first run's directory is untouched), same presenter `roydemure` (Qwen), same STT model,
same command (`./.venv/bin/python -m emcee pieces <dir> --presenter roydemure`, no `--limit`),
worktree venv at commit 49209191 (emcee imported from the worktree; jellyfish installed).
No code changed. Log: `premises-t2b/voice.log`.

Summary line: `voiced 57, re-takes 12, failed 3, left 0`. Wall time 6 min 25 s for 60 pieces
(11:31:19 to 11:37:44 EST, about 6.4 s per piece).

- Re-take rate: 12 re-take lines over 60 pieces = 0.20 per piece; 6 pieces needed at least one
  re-take (10%). 3 re-took once then voiced (`23ae6aba9e99` EOTO, "eoto" heard "yudo";
  `42a92323859f` EOTO, heard "ioto"; `ba8df9cc4584` AfroSkull, heard "skull"); 3 failed after 4 takes (5%).
- Every re-take/failure was a name-match reason except one onset re-take (the first 50 ms of a
  U-Melt take was at speech level). No runaway-guard or no-speech failures.

### Failed pieces (all after 4 takes)

| id | text | last reason | last transcript |
|---|---|---|---|
| 4823abc7d2ed | with U-Melt. | names differ by 2 token edits by key: wanted ['u melt'], heard ['you melt'] | With you melt. |
| 879aee971e4f | with George Porter, Jr. and Runnin' Pardners, | names differ by 3 token edits by key: wanted ['george porter jr and runnin pardners'], heard ['george porter jr and run in partners'] | with George Porter Jr. and Run-In Partners. |
| a85dc57cbcbb | with Ekoostik Hookah. | names differ by 2 token edits by key: wanted ['ekoostik hookah'], heard ['acoustic hookah'] | with acoustic hookah. |

### Comparison with the first run

| | first run (character-level rule) | re-run (phonetic rule, 49209191) |
|---|---|---|
| voiced | 50 | 57 |
| re-take lines | 35 | 12 |
| pieces needing a re-take | 13 (22%) | 6 (10%) |
| failed | 10 (17%) | 3 (5%) |
| wall time | about 8 min 42 s (about 8.7 s/piece) | 6 min 25 s (about 6.4 s/piece) |

TTS takes differ run to run (and the engine is not seeded), so these counts are indicative,
not a controlled A/B. The wall-time gain mostly follows from fewer re-takes.

### The first run's 10 failures

Now PASS (9): Raq. and Raq, (raq/rack), Emmitt Nershi Band, Runnin' Pardners with the period
(`6391934e3e89`), The Travelin' McCourys, Bonerama, Club d'Elf, Little Feat, Hayes Carll. All
voiced on the first take (none of these appears in the re-take lines).

Still FAIL (1): `879aee971e4f` "with George Porter, Jr. and Runnin' Pardners,". This take
was heard as "Run-In Partners" (an extra token, "run in" for "runnin"), which the token-count
tolerance for non-final name tokens does not absorb (3 token edits); the same text with a
period (`6391934e3e89`) happened to be transcribed "Runnin' Partners" and passed, so the
pardners/partners key equality works and the remaining failure is the STT splitting
"Runnin'" into two words.

### New failures in this run (voiced in the first run)

- `4823abc7d2ed` "with U-Melt." (first run: voiced after 1 re-take). Whisper writes "you melt";
  the key tokens ['u','melt'] vs ['you','melt'] differ, and the onset re-take shows a
  clipped take. A short-name case where the STT renders the letter U as a word.
- `a85dc57cbcbb` "with Ekoostik Hookah." (first run: voiced on the first take). Whisper writes
  "acoustic hookah" on all four takes; "Ekoostik" and "acoustic" differ by key. This piece
  needs an `.expect` entry (or a lexicon spelling) either way.

Net: the rule clears 9 of the first run's 10 failures (the ruling's PASS list: raq, pardners,
mccourys, bonerama, delf, feat, carll, plus Emmitt Nershi), but two spelling gaps (U-Melt,
Ekoostik) and one STT word-split ("Run-In") remain `.expect` or lexicon candidates.
