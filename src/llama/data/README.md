# Vendored jerrybase structure dataset

`set_breaks.csv` is vendored **byte-identical** from the deadstream project.

- Source: https://github.com/eichblatt/deadstream
- File: `timemachine/metadata/set_breaks.csv`
- Pinned ref: `main` @ `adc6f827ae42861b5220ebd7fb9c3fa83abbeec3` (2026-06-28)
- File last modified upstream in commit `5de5ad46ca2bc13ee3cf7630a66633db8ca67076` (2023-04-26, "added ratdog")
- Raw URL (SHA-pinned, byte-identical):
  https://raw.githubusercontent.com/eichblatt/deadstream/adc6f827ae42861b5220ebd7fb9c3fa83abbeec3/timemachine/metadata/set_breaks.csv
- License: **GPL-3.0** (deadstream's license). llama vendors it deliberately;
  the owner intends to license llama GPL.

## What this is

One row per **set** per show. Generation chain:
`jerrybase.com` (authoritative per-show structure for the Garcia universe)
→ deadstream's `setbreaks.q` query → this CSV.

Columns: `date, artist, event_id, venue, city, state, show_set, time,
song (the set's closing song), song_n, isong (global running song index),
next_set, Nevents, ievent, break_length (long|short)`.

**It is ground truth for:** set count, each set's closing song, break length,
venue/city/state, and multi-event dates.
**It is NOT a setlist source:** no per-song rows; it can never build or rank
full setlists.

## Refreshing

Run `python scripts/refresh_jerrybase.py` (manual; never run by the pipeline).
After a refresh, update the pinned commit SHA above.
