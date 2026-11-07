"""Staleness check shared by the CLI and the adjudicator."""
from __future__ import annotations

from llama.models import Show
from llama.workspace import read_model


def stale_message(ia, config, show_ws, slug: str) -> str | None:
    """The staleness refusal (spec 4.2), or None: a track number names a file through
    `show.json`, which is only safe while `show.json`'s filename list IS gather's final
    kept list, computed by gather's own helper (`gather.final_kept`) over the overrides
    as stored, i.e. before this invocation's edits. Until a show is re-gathered under
    the short-keep rule they differ on every show the rule changes. Needs `show.json`;
    reads the selected item's metadata (cached by gather)."""
    from llama import junk
    from llama.stages import gather
    from llama.workspace import read_overrides

    show = read_model(show_ws.show, Show)
    files = ia.metadata(show.identifier).get("files", [])
    fk = gather.final_kept(files, read_overrides(show_ws),
                           junk.FORMAT_BY_AUDIO[config.audio_format])
    if [f["name"] for f in fk.kept] == [t.filename for t in show.tracks]:
        return None
    return (f"{slug}: show.json's track list is not what gather keeps now; re-gather "
            f"under the new rule first (llama redo {slug} --from gather)")
