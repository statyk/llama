# Audio-check spike evidence (2026-11-14)

Spec: `../specs/2026-11-14-junk-drop-audio-check-design.md`. Throwaway spike code, kept as
the record behind the spec's calibration. Paths say `<scratchpad>/spike`; audio was read
from the station copy (`/Volumes/media/lma-radio/delivered/<slug>/audio/`), never committed.

- `build_sample.py` -> `sample.json`: round-1 sample (6 groups). `analyze.py`: YAMNet, PANNs
  CNN14, MS-CLAP features per 10 s window (spike venv: Python 3.12, torch 2.x, tensorflow 2.21,
  tensorflow_hub, panns_inference, msclap, librosa).
- `make_page.py` -> blind labelling page; `human_labels.json`: operator's round-1 labels,
  keyed by index into `sample.json`.
- `summarize.py`, `runs.py`, `compare.py`, `yamonly.py`: round-1 analyses.
- `analyze_all.py`: YAMNet + PANNs over all 933 drops with a station copy (`all.json`, not
  committed: it is `drops.tsv` of the 2026-11-13 evidence resolved to station paths).
- `scale.py`, `make_page2.py` -> `sample2.json`, `human_labels2.json`: round 2 (every track
  the 0.5-bar YAMNet rule flagged that round 1 had not labelled).
- `grid.py`: threshold grid over all labels; chose Music > 0.6.
- `population.tsv`: per-drop verdicts under the three rules plus the operator label where
  one exists. `music_y06` is the chosen rule: 27 tracks True, 2 of them Gomez "Silence"
  (restored by the vocabulary change) -> 25 tracks / 22 shows.
