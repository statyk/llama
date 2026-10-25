"""The interstitials folder (spec "Interstitial audio"): station IDs
(`id-*.mp3`) and schedule announcements (`ann-<id>.mp3`). transmitter only
reads it. Each clip becomes a one-clip `Show`, so analysis, encode and the
frame store are reused unchanged."""

import stat
from pathlib import Path

from transmitter.config import TransmitterConfig
from transmitter.station import Entry, Show, file_set_key_and_sizes

FOLDER_NAME = "interstitials"


def folder(cfg: TransmitterConfig) -> Path | None:
    if cfg.interstitials.dir is not None:
        return Path(cfg.interstitials.dir)
    if cfg.station.root is None:
        return None
    return Path(cfg.station.root) / FOLDER_NAME


def row_dir(cfg: TransmitterConfig, folder: Path) -> str:
    """The folder relative to the station root when inside it, else absolute."""
    if cfg.station.root is not None:
        try:
            return str(Path(folder).relative_to(Path(cfg.station.root)))
        except ValueError:
            pass
    return str(Path(folder))


def scan(folder: Path | None, *, now_s: float, quiet_s: float) -> list[Show]:
    if folder is None:
        return []
    try:
        paths = sorted(Path(folder).iterdir())
    except OSError:
        return []
    shows: list[Show] = []
    for p in paths:
        name = p.name
        if name.startswith(".") or not name.endswith(".mp3"):
            continue
        if name.startswith("id-"):
            role, ann_id, title = "id", None, "Station ID"
        elif name.startswith("ann-"):
            role, ann_id, title = "ann", p.stem[len("ann-"):], "Announcement"
        else:
            continue
        try:
            st = p.stat()
            if not stat.S_ISREG(st.st_mode) or st.st_size == 0 or now_s - st.st_mtime < quiet_s:
                continue
            key, sizes = file_set_key_and_sizes(Path(folder), [name])
        except OSError:
            continue
        shows.append(Show(p.stem, Path(folder), (Entry(name, "clip", title),), key,
                          {"role": role, "ann_id": ann_id, "sizes": sizes}))
    return sorted(shows, key=lambda s: s.slug)
