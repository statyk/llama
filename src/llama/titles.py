from llama.models import ParsedSetlist, Track
from llama.util import length_seconds


def resolve_titles(
    kept_files: list[dict],
    setlist: ParsedSetlist,
    sibling_titles: list[str] | None = None,
) -> list[Track]:
    """Resolve track titles (tags -> setlist -> sibling -> unresolved).

    Sets and segues are placeholders here; llama.structure.align stamps the
    real values from the canonical performance setlist."""
    files = sorted(kept_files, key=lambda f: f["name"])
    n = len(files)
    aligned = setlist.items if (setlist.confidence != "low" and len(setlist.items) == n) else None

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
        tracks.append(
            Track(index=pos + 1, set="1", title=title, filename=f["name"],
                  duration_sec=length_seconds(f.get("length")), segue=False,
                  title_source=source)
        )
    return tracks


def set_breaks(tracks: list[Track]) -> list[int]:
    return [prev.index for prev, nxt in zip(tracks, tracks[1:]) if nxt.set != prev.set]
