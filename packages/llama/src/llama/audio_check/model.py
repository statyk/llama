"""YAMNet class map (no numpy, no onnxruntime; the runtime is added separately)."""

from __future__ import annotations

import csv
from importlib import resources


def _load_class_names() -> tuple[str, ...]:
    path = resources.files("llama.data").joinpath("yamnet_class_map.csv")
    with path.open("r", encoding="utf-8", newline="") as fh:
        rows = sorted(csv.DictReader(fh), key=lambda r: int(r["index"]))
    return tuple(r["display_name"] for r in rows)


CLASS_NAMES: tuple[str, ...] = _load_class_names()
