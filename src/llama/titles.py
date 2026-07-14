from llama.models import ParsedSetlist, Track
from llama.songs import normalize_song
from llama.util import length_seconds


def resolve_titles(
    kept_files: list[dict],
    setlist: ParsedSetlist,
    sibling_titles: list[str] | None = None,
) -> list[Track]:
    files = sorted(kept_files, key=lambda f: f["name"])
    n = len(files)
    aligned = setlist.items if (setlist.confidence != "low" and len(setlist.items) == n) else None
    by_norm = {i.normalized: i for i in setlist.items}

    tracks: list[Track] = []
    for pos, f in enumerate(files):
        tag_title = str(f.get("title") or "").strip()
        if tag_title:
            title, source = tag_title, "tags"
        elif aligned:
            title, source = aligned[pos].title, "setlist"
        elif sibling_titles and len(sibling_titles) == n:
            title, source = sibling_titles[pos], "sibling"
        else:
            title, source = f["name"], "unresolved"

        item = aligned[pos] if aligned else by_norm.get(normalize_song(title))
        tracks.append(
            Track(
                index=pos + 1,
                set=item.set if item else "1",
                title=title,
                filename=f["name"],
                duration_sec=length_seconds(f.get("length")),
                segue=item.segue if item else False,
                title_source=source,
            )
        )
    return tracks


def set_breaks(tracks: list[Track]) -> list[int]:
    return [prev.index for prev, nxt in zip(tracks, tracks[1:]) if nxt.set != prev.set]
