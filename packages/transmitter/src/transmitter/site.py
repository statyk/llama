"""Listener-facing data built by the publisher (spec "R2 object contract"):
timeline.json (shows over [now - 24 h, horizon end] with per-file offsets from
actual frame positions), notes/<slug>.json (llama's briefing, archive.org link,
lineage, setlist, airtimes) and show/<slug>.html rendered from antenna's
template. Phase 4 redesigns the page; the data contract starts here."""

import html
import json
import re
import string
from pathlib import Path
from typing import Mapping, Sequence

from transmitter import aacenc, grid
from transmitter.analysis import ShowAnalysis
from transmitter.layout import PlanRow
from transmitter.render import show_layout
from transmitter.workspace import Epoch

DAY_US = 86_400 * 1_000_000


def row_span_us(row: PlanRow, epoch: Epoch) -> tuple[int, int]:
    return (epoch.epoch_us + grid.frame_to_us(row.start_frame),
            epoch.epoch_us + grid.frame_to_us(row.end_frame))


def file_starts(row: PlanRow, analysis: ShowAnalysis, pause_samples: int, epoch: Epoch) -> list[dict]:
    base = row.start_frame * grid.FRAME_SAMPLES + aacenc.ENCODER_PRIMING_SAMPLES
    limit = row.end_frame * grid.FRAME_SAMPLES
    out = []
    for span in show_layout(analysis, pause_samples).spans:
        pos = base + span.start_sample
        if pos >= limit:
            break
        out.append({"kind": span.kind, "title": span.title,
                    "start": grid.us_to_iso(epoch.epoch_us + grid.samples_to_us(pos))})
    return out


def build_timeline(rows: Sequence[PlanRow], analyses: Mapping[str, ShowAnalysis], epoch: Epoch, *,
                   now_us: int, last_n: int, pause_samples: int) -> dict:
    lo, hi = now_us - DAY_US, epoch.start_us(last_n + 1)
    shows = []
    for row in rows:
        start_us, end_us = row_span_us(row, epoch)
        if end_us <= lo or start_us >= hi:
            continue
        a = analyses.get(row.key)
        if a is None:
            continue
        m = a.meta
        shows.append({
            "slug": row.slug, "start": grid.us_to_iso(start_us), "end": grid.us_to_iso(end_us),
            "artist": m.get("artist"), "date": m.get("date"), "venue": m.get("venue"),
            "city": m.get("city"), "profile": m.get("profile"),
            "notes": f"notes/{row.slug}.json", "page": f"show/{row.slug}.html",
            "files": file_starts(row, a, pause_samples, epoch),
        })
    recent = [s["slug"] for s in reversed(shows) if grid.iso_to_us(s["end"]) <= now_us][:10]
    return {"generated_at": grid.us_to_iso(now_us), "epoch_id": epoch.epoch_id,
            "shows": shows, "recent": recent, "anchors": []}


def airtimes(rows: Sequence[PlanRow], slug: str, epoch: Epoch, lo_us: int, hi_us: int) -> list[dict]:
    out = []
    for row in rows:
        if row.slug != slug:
            continue
        start_us, end_us = row_span_us(row, epoch)
        if end_us > lo_us and start_us < hi_us:
            out.append({"start": grid.us_to_iso(start_us), "end": grid.us_to_iso(end_us)})
    return out


def read_package_notes(pkg_dir: Path) -> tuple[dict | None, str | None]:
    try:
        manifest = json.loads((Path(pkg_dir) / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    if not isinstance(manifest, dict):
        return None, None
    name = Path((manifest.get("briefing") or {}).get("file") or "briefing.md").name
    try:
        briefing = (Path(pkg_dir) / name).read_text(encoding="utf-8")
    except OSError:
        briefing = None
    return manifest, briefing


def build_notes(slug: str, manifest: dict | None, briefing: str | None, airtimes: list[dict],
                meta: Mapping) -> dict:
    manifest = manifest or {}
    show = manifest.get("show") or {}
    source = manifest.get("source") or {}
    tracks = manifest.get("tracks") or []
    return {
        "slug": slug,
        "artist": show.get("artist", meta.get("artist")),
        "date": show.get("date", meta.get("date")),
        "venue": show.get("venue", meta.get("venue")),
        "city": show.get("city", meta.get("city")),
        "profile": source.get("profile", meta.get("profile")),
        "url": source.get("url", meta.get("url")),
        "lineage": source.get("lineage", meta.get("lineage")),
        "briefing": briefing or "",
        "setlist": [{"set": t.get("set"), "title": t.get("title"), "segue": bool(t.get("segue"))}
                    for t in tracks if isinstance(t, dict)],
        "airtimes": airtimes,
    }


def _title(notes: Mapping) -> str:
    return " — ".join(p for p in (notes.get("artist") or notes["slug"], notes.get("date")) if p)


def render_show_page(template: str, notes: Mapping, *, site_url: str | None, station_name: str) -> str:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", notes.get("briefing") or "") if p.strip()]
    briefing_html = "\n".join(f"<p>{html.escape(p)}</p>" for p in paragraphs) or "<p>No notes yet.</p>"
    items = []
    for t in notes.get("setlist", []):
        segue = " &gt;" if t.get("segue") else ""
        items.append(f"<li>{html.escape(t.get('title') or '?')}{segue}"
                     f" <span class=\"set\">{html.escape(str(t.get('set') or ''))}</span></li>")
    setlist_html = f"<ol>{''.join(items)}</ol>" if items else "<p>No setlist.</p>"
    title = _title(notes)
    description = re.sub(r"\s+", " ", paragraphs[0])[:200] if paragraphs else title
    page_url = f"{site_url.rstrip('/')}/show/{notes['slug']}.html" if site_url else ""
    city = notes.get("city")
    values = {
        "title": html.escape(title), "station": html.escape(station_name),
        "description": html.escape(description), "page_url": html.escape(page_url),
        "venue": html.escape(notes.get("venue") or ""),
        "city_suffix": html.escape(f", {city}") if city else "",
        "briefing_html": briefing_html, "setlist_html": setlist_html,
        "archive_url": html.escape(notes.get("url") or ""),
        "lineage": html.escape(notes.get("lineage") or ""),
        "slug": html.escape(notes["slug"]),
    }
    return string.Template(template).safe_substitute(values)
