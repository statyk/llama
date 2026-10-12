### Task 10: Timeline, notes and show-page builders + the show template

**Model hint:** sonnet

**Files:**
- Create: `packages/transmitter/src/transmitter/site.py`
- Create: `antenna/templates/show.html`
- Create: `packages/transmitter/tests_transmitter/test_site.py`

**Interfaces:**
- Consumes: `grid`, `aacenc.ENCODER_PRIMING_SAMPLES`, `render.show_layout`, `analysis.ShowAnalysis`, `layout.PlanRow`, `workspace.Epoch`.
- Produces:
  - `DAY_US`; `row_span_us(row, epoch) -> tuple[int, int]`; `file_starts(row, analysis, pause_samples, epoch) -> list[dict]` (`{kind, title, start}`, start = actual frame position plus encoder priming).
  - `build_timeline(rows, analyses: Mapping[str, ShowAnalysis], epoch, *, now_us, last_n, pause_samples) -> dict` — `{generated_at, epoch_id, shows: [{slug, start, end, artist, date, venue, city, profile, notes, page, files}], recent: [slug…], anchors: []}` covering `[now − 24 h, E + (last_n+1)·d)`.
  - `airtimes(rows, slug, epoch, lo_us, hi_us) -> list[dict]`.
  - `read_package_notes(pkg_dir) -> tuple[dict | None, str | None]` (manifest, briefing text).
  - `build_notes(slug, manifest, briefing, airtimes, meta) -> dict`.
  - `render_show_page(template, notes, *, site_url, station_name) -> str` (`string.Template.safe_substitute`: a stray `$` in the template never raises).
  - `antenna/templates/show.html` placeholders: `$title $station $description $page_url $venue $city_suffix $briefing_html $setlist_html $archive_url $lineage $slug`.

- [ ] **Step 1: Create the template**

`antenna/templates/show.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>$title · $station</title>
<meta property="og:type" content="website">
<meta property="og:site_name" content="$station">
<meta property="og:title" content="$title">
<meta property="og:description" content="$description">
<meta property="og:url" content="$page_url">
<meta name="twitter:card" content="summary">
<link rel="stylesheet" href="../style.css">
</head>
<body>
<main class="show">
<p><a href="../">← $station</a></p>
<h1>$title</h1>
<p class="where">$venue$city_suffix</p>
<section><h2>About this show</h2>
$briefing_html
</section>
<section><h2>Setlist</h2>
$setlist_html
</section>
<section><h2>Source</h2>
<p><a href="$archive_url">$archive_url</a></p>
<p class="lineage">$lineage</p>
</section>
<section><h2>Airtimes</h2>
<ul id="airtimes" data-notes="../notes/$slug.json"><li>Loading…</li></ul>
</section>
</main>
<script>
(async () => {
  const ul = document.getElementById("airtimes");
  const item = (text) => Object.assign(document.createElement("li"), { textContent: text });
  try {
    const notes = await (await fetch(ul.dataset.notes)).json();
    const fmt = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
    const times = (notes.airtimes || []).map((a) => item(fmt.format(new Date(a.start))));
    ul.replaceChildren(...(times.length ? times : [item("Not currently scheduled.")]));
  } catch (e) {
    ul.replaceChildren(item("Airtimes unavailable."));
  }
})();
</script>
</body>
</html>
```

- [ ] **Step 2: Write the failing tests**

`tests_transmitter/test_site.py`:

```python
from pathlib import Path

from tests_transmitter.helpers import build_package, make_root
from transmitter import aacenc, grid, site
from transmitter.analysis import FileAnalysis, ShowAnalysis
from transmitter.layout import PlanRow
from transmitter.workspace import Epoch

EPOCH = Epoch("e1", grid.iso_to_us("2026-10-10T00:00:00Z"))
TEMPLATE = (Path(__file__).resolve().parents[3] / "antenna" / "templates" / "show.html").read_text()
META = {"artist": "Band", "date": "2005-11-01", "venue": "Club", "city": "Lincoln, NE",
        "profile": "indie", "url": "https://archive.org/details/band2005", "lineage": "AUD"}


def _analysis(key):
    files = (FileAnalysis("dj-audio/i.mp3", "clip", "DJ intro (set 1)", 44_100),
             FileAnalysis("audio/01.mp3", "track", "Song 1", 441_000),
             FileAnalysis("dj-audio/o.mp3", "clip", "DJ outro", 44_100))
    return ShowAnalysis(key, f"show-{key}", files, -18.0, -2.0, META)


def _row(seq, key, start_frame, frames=1000, **kw):
    return PlanRow(seq=seq, slug=f"show-{key}", dir=f"show-{key}", key=key, start_frame=start_frame,
                   frames=frames, **kw)


def test_file_starts_follow_actual_frame_positions_plus_encoder_priming():
    row = _row(0, "a", 441 * 10)
    starts = site.file_starts(row, _analysis("a"), 33_075, EPOCH)
    base = 441 * 10 * 1024 + aacenc.ENCODER_PRIMING_SAMPLES
    assert starts[0] == {"kind": "clip", "title": "DJ intro (set 1)",
                         "start": grid.us_to_iso(EPOCH.epoch_us + grid.samples_to_us(base))}
    assert starts[1]["start"] == grid.us_to_iso(EPOCH.epoch_us + grid.samples_to_us(base + 44_100 + 33_075))


def test_file_starts_stop_at_a_cut():
    row = _row(0, "a", 0, frames=1000, cut_frame=40)       # cut after ~0.93 s
    assert [f["title"] for f in site.file_starts(row, _analysis("a"), 33_075, EPOCH)] == ["DJ intro (set 1)"]


def test_timeline_window_and_recent():
    rows = [_row(0, "a", 0), _row(1, "b", 1087), _row(2, "c", 2174)]
    analyses = {k: _analysis(k) for k in "abc"}
    now = EPOCH.epoch_us + grid.frame_to_us(1500)          # inside b
    last_n = 3                                             # published through frame 1764
    tl = site.build_timeline(rows, analyses, EPOCH, now_us=now, last_n=last_n, pause_samples=33_075)
    assert [s["slug"] for s in tl["shows"]] == ["show-a", "show-b"]     # c starts after the horizon
    assert tl["recent"] == ["show-a"]
    assert tl["anchors"] == [] and tl["epoch_id"] == "e1"
    a = tl["shows"][0]
    assert a["start"] == EPOCH.iso and a["notes"] == "notes/show-a.json" and a["page"] == "show/show-a.html"
    assert a["artist"] == "Band"


def test_timeline_skips_rows_without_analysis():
    tl = site.build_timeline([_row(0, "a", 0)], {}, EPOCH, now_us=EPOCH.epoch_us, last_n=5, pause_samples=0)
    assert tl["shows"] == []


def test_airtimes():
    rows = [_row(0, "a", 0), _row(1, "b", 1087), _row(2, "a", 2174)]
    got = site.airtimes(rows, "show-a", EPOCH, EPOCH.epoch_us, EPOCH.epoch_us + 10**12)
    assert [g["start"] for g in got] == [EPOCH.iso, grid.us_to_iso(EPOCH.epoch_us + grid.frame_to_us(2174))]


def test_notes_from_a_package(tmp_path):
    pkg = build_package(make_root(tmp_path))
    manifest, briefing = site.read_package_notes(pkg)
    notes = site.build_notes(pkg.name, manifest, briefing, [], META)
    assert notes["artist"] == "Band" and notes["url"] == "https://archive.org/details/band2005"
    assert notes["setlist"][0] == {"set": "1", "title": "Song 1", "segue": False}
    assert notes["briefing"].startswith("A fine show.")


def test_notes_fall_back_to_cached_meta_when_the_package_is_unreadable(tmp_path):
    assert site.read_package_notes(tmp_path / "gone") == (None, None)
    notes = site.build_notes("s", None, None, [], META)
    assert notes["artist"] == "Band" and notes["setlist"] == [] and notes["briefing"] == ""


def test_show_page_escapes_and_fills_every_placeholder():
    notes = site.build_notes("s", None, "Para <script>alert(1)</script> one.\n\nPara two.", [], META)
    html = site.render_show_page(TEMPLATE, notes, site_url="https://radio.example.org/", station_name="llama radio")
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert '<meta property="og:url" content="https://radio.example.org/show/s.html">' in html
    assert '<meta property="og:title" content="Band — 2005-11-01">' in html
    assert "<p>Para two.</p>" in html
    assert "$" not in html.split("<script>")[0]            # no unfilled placeholder
```

- [ ] **Step 3: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_site.py -q`
Expected: FAIL — `ImportError: cannot import name 'site' from 'transmitter'`.

- [ ] **Step 4: Implement `site.py`**

```python
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
```

- [ ] **Step 5: Run the tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_site.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add antenna/templates packages/transmitter
git commit -m "feat(transmitter): timeline, notes and show-page builders; antenna show template"
```

---

