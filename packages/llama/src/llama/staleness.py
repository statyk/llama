"""Staleness check shared by the CLI and the adjudicator."""
from __future__ import annotations

from collections.abc import Collection, Sequence

from llama import junk_titles
from llama.models import Show
from llama.workspace import read_model


def expected_track_files(kept: Sequence[str], show: Show,
                         include: Collection[str]) -> list[str]:
    """The filename list `show.json` should carry: `kept` (gather's `final_kept(...).kept`
    names, in order) minus the files `show.excluded_files` records as dropped with
    reason `junk_titles.REASON` and that `include` (`overrides.include`) does not name.
    The junk-title drop runs later inside `compute_gather`, on the final titles, so
    `final_kept` alone still lists a dropped file (spec 2026-11-13-junk-tag-drop,
    "Placement in gather"); a file the operator has since included is expected back."""
    inc = set(include)
    dropped = {e.get("filename") for e in show.excluded_files
               if isinstance(e, dict) and junk_titles.REASON in (e.get("reasons") or [])
               and e.get("filename") not in inc}
    return [n for n in kept if n not in dropped]


def stale_message(ia, config, show_ws, slug: str) -> str | None:
    """The staleness refusal (spec 4.2), or None: a track number names a file through
    `show.json`, which is only safe while `show.json`'s filename list IS gather's final
    kept list, computed by gather's own helper (`gather.final_kept`) over the overrides
    as stored, i.e. before this invocation's edits, less its junk-title drops
    (`expected_track_files`). Until a show is re-gathered under
    the short-keep rule they differ on every show the rule changes. Needs `show.json`;
    reads the selected item's metadata (cached by gather)."""
    from llama import junk
    from llama.stages import gather
    from llama.workspace import read_overrides

    show = read_model(show_ws.show, Show)
    files = ia.metadata(show.identifier).get("files", [])
    overrides = read_overrides(show_ws)
    fk = gather.final_kept(files, overrides, junk.FORMAT_BY_AUDIO[config.audio_format])
    expected = expected_track_files([f["name"] for f in fk.kept], show, overrides.include)
    if expected == [t.filename for t in show.tracks]:
        return None
    return (f"{slug}: show.json's track list is not what gather keeps now; re-gather "
            f"under the new rule first (llama redo {slug} --from gather)")
