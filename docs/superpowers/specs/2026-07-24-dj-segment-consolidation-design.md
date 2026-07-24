# DJ segment consolidation — one spoken clip per music gap

**Date:** 2026-07-24
**Status:** approved (design)

## Problem

The DJ script currently emits separate segments that play back-to-back with no
music between them. For a two-sets-plus-encore show the broadcast timeline is:

```
1. Show intro (00-intro)  ┐ adjacent, no music between
2. Set 1 intro            ┘
      ── SET 1 MUSIC ──
3. Break 1                ┐ adjacent, no music between
4. Set 2 intro            ┘
      ── SET 2 MUSIC ──
5. Break 2                ┐ adjacent, no music between
6. Encore intro           ┘
      ── ENCORE MUSIC ──
7. Outro
```

Three pairs of talk run in sequence (1-2, 3-4, 5-6). That layout only makes
sense if a station break lands between each pair, which this station does not
anticipate. The result on air is the DJ saying "…and now, set one" immediately
followed by "welcome to set one, listen for…".

## Goal

No two spoken DJ clips ever play back-to-back. The DJ talks once in each gap
between music blocks: a lead-in before each set, and a closing outro after the
final music.

## Design (Option A — encore folds into the preceding set)

The DJ leads into every **non-encore** set. The first set's lead-in also opens
the whole broadcast; each later set's lead-in recaps the set just played and
teases the coming one. An **encore, when present, gets no lead-in** — it plays
unannounced right after the final set (which is how an encore feels live), and
the outro afterward acknowledges and recaps it. The outro is always the single
last spoken segment.

New broadcast timeline (two sets + encore):

```
set 1 lead-in → SET 1 → set 2 lead-in → SET 2 → ENCORE → outro
```

No-encore show (two sets):

```
set 1 lead-in → SET 1 → set 2 lead-in → SET 2 → outro
```

Single set:

```
set 1 lead-in → SET 1 → outro
```

Spoken segment count is always **(number of non-encore sets) + 1** (the outro),
and no two are adjacent. Content is preserved — the old show-intro folds into
set 1's lead-in, each old break note folds into the next set's lead-in, and the
encore recap folds into the outro. Nothing is dropped.

## Schema changes (`src/llama/models.py`)

- **`DJNotes`**: drop `intro` and `set_break_notes`. Keep `context`,
  `set_intros` (dict keyed by **non-encore** set — each value is now that set's
  full combined lead-in), `outro`, `mentioned_songs`.
- **`DJAudio`**: drop `intro` and `set_breaks`. Keep `set_intros` (keyed,
  non-encore) and `outro`.
- **`SetBreak`**: drop `note_index` and `audio`. A set break becomes a pure
  physical marker (`after_track` only). The between-set talk that used to hang
  off the break now rides on the **next set's lead-in** (`set_intros[next]` /
  `set<key>-intro.mp3`), so the break entry no longer references a DJ note or
  clip.

## Segment files (`src/llama/stages/package.py` `_segment_texts`)

In broadcast order:

- one `set<key>-intro` per non-encore set (sets in numeric order), then
- `99-outro`.

Gone: `00-intro`, `break<N>`. The encore contributes no clip. `DJAudio` paths
follow: `set_intros = {key: "dj-audio/set<key>-intro.mp3"}`,
`outro = "dj-audio/99-outro.mp3"`.

## Prompt (`src/llama/prompts/synthesize.md`)

Response JSON shape becomes:

```json
{"context": "<one line placing the show in its era/tour>",
 "set_intros": {"<lead-in set key>": "<spoken lead-in for that set>"},
 "outro": "<sign-off after the final music>",
 "mentioned_songs": [<every song title referenced, spelled as in show data>]}
```

Instruction changes:

- `set_intros` has **one key per lead-in set** (the non-encore sets), listed via
  a new `{{lead_in_sets}}` variable.
- The **first** set's lead-in opens the broadcast: artist, date, venue, why this
  show earns airtime (~60-90s), then what to listen for in that set.
- Each **later** set's lead-in briefly recaps the set just played, then teases
  the coming set (~30-45s).
- A new conditional `{{encore_note}}` line explains, when an encore exists, that
  it plays with no lead-in of its own and the **outro** must recap it.
- Remove the `intro` and `set_break_notes` fields and the `{{n_breaks}}` line.

The stage (`run_synthesize`) computes `lead_in_sets = non-encore sets` and
`has_encore`, fills `{{lead_in_sets}}` and `{{encore_note}}`, and drops
`n_breaks`. The retry feedback string drops "and break count".

**Note:** the neutral-style byte-for-byte lock test compares a rendered prompt;
its expected text must be regenerated for the new template.

## Grounding (`factual_guard` in `src/llama/stages/synthesize.py`)

- Lead-in keys are validated against **non-encore** sets:
  `lead_in_sets = {t.set for t in show.tracks if t.set != "encore"}`. A key not
  in that set (including an `"encore"` key) is a problem; every lead-in set must
  be covered.
- Remove the `set_break_notes` count check entirely.
- The free-text set-count prose scan runs over `context`, `outro`, and
  `set_intros` values (no more `intro` / `set_break_notes`).

## Human-readable notes (`render_notes_md`)

One `## Set <n> lead-in` section per non-encore set in order, then `## Outro`.
The `context` italic line stays. No standalone show-intro or set-break sections.

## Manifest (`src/llama/manifest.py`)

`dj_notes` embeds the reshaped `DJNotes` and `dj_audio` embeds the reshaped
`DJAudio`. `build_manifest` also changes: the `SetBreak` entries drop the
`note_index`/`audio` wiring (those pointed at the removed `set_break_notes` /
`dj_audio.set_breaks`) and become `after_track`-only markers. DJ-audio
placement is now fully described by `dj_audio.set_intros` (a clip before each
non-encore set) and `dj_audio.outro` (after the final music); the automation
already knows set boundaries from the tracks and the `after_track` markers.

## No migration

Consistent with the project's "purge and re-run" stance, existing
`shows/<slug>/dj-notes.json` keep the old shape and stale content until
regenerated. To adopt the new structure, run
`llama redo <show> --from synthesize`. No back-compat code, no schema shim.

## Docs to update (live docs only; dated plans/specs stay as historical record)

- `README.md` — "one break note per entry in `manifest.set_breaks`" and any
  dj-audio segment description.
- `docs/station-brief.md` — the `set_breaks` JSON example (drop `note_index` /
  `audio`) and the prose about playing `set_breaks[i].audio` during a break
  (now: play the next set's lead-in clip before that set).
- `src/llama/config.py` — the `[tts]` template line listing
  `(00-intro, set<key>-intro, break<N>, 99-outro)`.
- `CLAUDE.md` — the dj-audio segment description, if it enumerates the old set.

## Testing

- Update schema/shape-dependent tests: `test_models`, `test_manifest`,
  `test_stage_synthesize`, `test_stage_package`, `test_chunk`,
  `test_pipeline`, `test_voice_pipeline`, `test_catalog`.
- Add a segment-layout test asserting, for a two-sets-plus-encore show:
  spoken segments are exactly `set1-intro`, `set2-intro`, `99-outro` (no
  `00-intro`, no `break*`, no encore lead-in) and the count equals
  `non_encore_sets + 1`.
- `factual_guard` tests: an `"encore"` key in `set_intros` is flagged; a missing
  non-encore lead-in is flagged; the old break-count assertion is removed.
```
