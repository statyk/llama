"""Listener-facing data built by the publisher (spec "R2 object contract"):
timeline.json (shows over [now - 24 h, horizon end] with per-file offsets from
actual frame positions), notes/<slug>.json (llama's briefing, archive.org link,
lineage, setlist, airtimes) and show/<slug>.html rendered from antenna's
template. Phase 4 redesigns the page; the data contract starts here."""

import datetime
import html
import json
import re
import string
from pathlib import Path
from typing import Mapping, Sequence
from urllib.parse import quote

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
        if row.kind != "show":
            continue
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
    ref = manifest.get("briefing")
    if ref is not None and not isinstance(ref, dict):
        return manifest, None
    file_ref = (ref or {}).get("file") or "briefing.md"
    if not isinstance(file_ref, str):                 # a malformed reference: no briefing text
        return manifest, None
    name = Path(file_ref).name
    try:
        briefing = (Path(pkg_dir) / name).read_text(encoding="utf-8")
    except (OSError, ValueError):       # unreadable or not UTF-8: no briefing text
        briefing = None
    return manifest, briefing


CAUTIONS_PREFIX = "## cautions"        # llama's brief.py heading; transmitter cannot import it
# Pointers to the Cautions section, which public pages cut. Only shapes that leave a whole
# sentence behind: "(see cautions)"; a trailing "; see cautions" (or " — see cautions", or
# ", see cautions" just before ")") ending a sentence or a parenthesis; and a bare
# "See cautions." sentence. "see cautions on/before/for ..." and "in the cautions" stay.
CAUTIONS_POINTER = re.compile(
    r"\s*\(see cautions\)"
    r"|\s*(?:[;\u2014\u2013]|,(?=\s*see cautions\)))\s*see cautions(?=[.)])"
    r"|(?:(?<=[.!?])|(?<=[.!?][\"'\u201d\u2019])|^)\s*see cautions\.(?=\s|$)",
    re.IGNORECASE)
ARCHIVE_PREFIX = "https://archive.org/"
OG_IMAGE_PATH = "/assets/cassette-og.png"
SLUG_SAFE = "!'()*"                    # encodeURIComponent's, as timeline.js showHref
_WEEKDAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
_MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


def archive_link(url: str | None) -> str | None:
    """The url when it is an https archive.org link (literal prefix check), else None."""
    return url if isinstance(url, str) and url.startswith(ARCHIVE_PREFIX) else None


def parse_briefing(text: str) -> list[dict]:
    """Line-based briefing markdown -> [{"heading", "blocks": [{"p"} | {"ul"}]}].

    Drops the `# ` title and everything from the cautions heading on."""
    sections: list[dict] = []
    current: dict | None = None
    para: list[str] = []
    items: list[str] = []

    def flush() -> None:
        nonlocal para, items
        if current is not None:
            if para:
                current["blocks"].append({"p": " ".join(para)})
            if items:
                current["blocks"].append({"ul": items})
        para, items = [], []

    def ensure() -> dict:
        nonlocal current
        if current is None:
            current = {"heading": None, "blocks": []}
            sections.append(current)
        return current

    for raw in (text or "").splitlines():
        line = raw.strip().replace("**", "")
        if line.lower().startswith(CAUTIONS_PREFIX):
            break
        line, hit = CAUTIONS_POINTER.subn("", line)
        if hit:
            line = line.strip()
            if not line:                # the line was only a pointer: not a paragraph break
                continue
        if line.startswith("## "):
            flush()
            current = {"heading": line[3:].strip(), "blocks": []}
            sections.append(current)
        elif line.startswith("# "):
            continue
        elif not line:
            if para:
                flush()
        elif line.startswith("- "):
            ensure()
            if para:
                current["blocks"].append({"p": " ".join(para)})
                para = []
            items.append(line[2:].strip())
        else:
            ensure()
            if items:
                current["blocks"].append({"ul": items})
                items = []
            para.append(line)
    flush()
    return [s for s in sections if s["blocks"]]


def build_notes(slug: str, manifest: dict | None, briefing: str | None, airtimes: list[dict],
                meta: Mapping) -> dict:
    manifest = manifest or {}

    def part(key: str, kind: type):
        # A damaged part reads as missing, so one bad manifest can't stop timeline.json.
        value = manifest.get(key)
        return value if isinstance(value, kind) else kind()
    show = part("show", dict)
    source = part("source", dict)
    tracks = part("tracks", list)

    def pick(section: Mapping, key: str):
        # Cached metadata fills a missing OR null field (llama writes null for unknown).
        value = section.get(key)
        return meta.get(key) if value is None else value
    return {
        "slug": slug,
        "artist": pick(show, "artist"),
        "date": pick(show, "date"),
        "venue": pick(show, "venue"),
        "city": pick(show, "city"),
        "profile": pick(source, "profile"),
        "url": pick(source, "url"),
        "lineage": pick(source, "lineage"),
        "briefing": briefing or "",
        "sections": parse_briefing(briefing or ""),
        "setlist": [{"set": t.get("set"), "title": t.get("title"), "segue": bool(t.get("segue"))}
                    for t in tracks if isinstance(t, dict)],
        "airtimes": airtimes,
    }


def _text(value) -> str:
    """Display text of a notes field: blank for null, and never raises on a non-string."""
    return "" if value is None else str(value)


def _title(notes: Mapping) -> str:
    return " — ".join(p for p in (_text(notes.get("artist")) or notes["slug"], _text(notes.get("date"))) if p)


def concert_stub(date) -> tuple[str, str]:
    """The ticket stub: "2008-11-01" -> ("SAT NOV 1", "2008"); anything else comes back as stored.

    Never raises: an exception while rendering a page would stop timeline.json."""
    text = _text(date)
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text, re.ASCII)
    if m is None:
        return text, ""
    try:
        day = datetime.date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return text, ""
    return f"{_WEEKDAYS[day.weekday()]} {_MONTHS[day.month - 1]} {day.day}", m[1]


def where_line(venue, city) -> str:
    return ", ".join(p for p in (_text(venue), _text(city)) if p)


def _setlist_line(entry: Mapping) -> str:
    """One rule for segues, as notes.js setlistLine: a trailing > or -> reads " >", and
    the flag adds one only to a title without one."""
    title = _text(entry.get("title")).strip()
    if not title:
        return "?"
    title = re.sub(r"\s*-*>\s*$", " >", title)
    return f"{title} >" if entry.get("segue") and not title.endswith(">") else title


def _set_label(value) -> str:
    text = _text(value).strip()
    return f"Set {text}" if text.isdigit() else text[:1].upper() + text[1:]


def _setlist_html(setlist: Sequence[Mapping]) -> str:
    groups: list[tuple[object, list[str]]] = []
    for entry in setlist:
        if not groups or groups[-1][0] != entry.get("set"):
            groups.append((entry.get("set"), []))
        groups[-1][1].append(f"<li>{html.escape(_setlist_line(entry))}</li>")
    out = []
    for value, lines in groups:
        label = _set_label(value) if len(groups) > 1 else ""
        if label:
            out.append(f'<p class="kick">{html.escape(label)}</p>')
        out.append(f"<ol>{''.join(lines)}</ol>")
    return "\n".join(out) or "<p>No setlist.</p>"


def _sections_html(sections: Sequence[Mapping]) -> str:
    out = []
    for section in sections:
        if section.get("heading"):
            out.append(f"<h3>{html.escape(_text(section['heading']))}</h3>")
        for block in section.get("blocks") or []:
            if "p" in block:
                out.append(f"<p>{html.escape(_text(block['p']))}</p>")
            elif "ul" in block:
                items = "".join(f"<li>{html.escape(_text(item))}</li>" for item in block["ul"])
                out.append(f"<ul>{items}</ul>")
    return "\n".join(out) or "<p>No notes yet.</p>"


def _first_text(sections: Sequence[Mapping]) -> str | None:
    for section in sections:
        for block in section.get("blocks") or []:
            first = block.get("p") or (block.get("ul") or [None])[0]
            if first:
                return _text(first)
    return None


def render_show_page(template: str, notes: Mapping, *, site_url: str | None, station_name: str) -> str:
    title = _title(notes)
    sections = notes.get("sections") or []
    first = _first_text(sections)
    description = re.sub(r"\s+", " ", first)[:200] if first else title
    origin = site_url.rstrip("/") if site_url else ""
    page_url = f"{origin}/show/{quote(notes['slug'], safe=SLUG_SAFE)}.html" if origin else ""
    og_image = f'<meta property="og:image" content="{html.escape(origin + OG_IMAGE_PATH)}">' if origin else ""
    archive = archive_link(notes.get("url"))
    archive_html = (f'<a class="btn" href="{html.escape(archive)}" target="_blank" rel="noopener">'
                    "Hear the full tape on archive.org ↗</a>") if archive else ""
    lineage = _text(notes.get("lineage"))
    lineage_html = (f'<div class="meta"><b class="label">Taper\'s lineage</b><br>{html.escape(lineage)}</div>'
                    if lineage else "")
    date_stub, year_stub = concert_stub(notes.get("date"))
    values = {
        "title": html.escape(title), "station": html.escape(station_name),
        "description": html.escape(description), "page_url": html.escape(page_url),
        "og_image_html": og_image,
        "artist": html.escape(_text(notes.get("artist")) or notes["slug"]),
        "date_stub": html.escape(date_stub), "year_stub": html.escape(year_stub),
        "where": html.escape(where_line(notes.get("venue"), notes.get("city"))),
        "archive_html": archive_html,
        "sections_html": _sections_html(sections),
        "setlist_html": _setlist_html(notes.get("setlist") or []),
        "lineage": lineage_html,
        "slug": html.escape(notes["slug"]),
    }
    return string.Template(template).safe_substitute(values)
