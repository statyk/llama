"""The adjudicator's evidence bundle: one show's flags, track table, overrides, research
and archive.org evidence rendered as markdown, plus the evidence rows the policy gate
substring-checks a model's quotes against. Read-only: no writes, no setlist.fm fetch."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import httpx

from llama import jerrybase, setlistfm
from llama.catalog import recording_info
from llama.config import Config
from llama.ia_client import IAError
from llama.models import Overrides, Provenance, Show, ShowNotes
from llama.show_unit import ShowView, capture_view
from llama.util import length_seconds
from llama.workspace import ShowWorkspace, read_json, read_model, read_overrides

EVIDENCE_KINDS = ("taper-description", "original-tag", "derivative-tag", "sibling-tracks",
                  "setlistfm", "jerrybase", "review")

DESC_CAP = 6000
NOTES_CAP = 3000
ROWS_PER_ITEM = 80
REVIEWS_MAX = 12
REVIEW_CAP = 1200
RESEARCH_CAP = 12000
BRIEFING_CAP = 6000
VETTING_CAP = 4000
NOTES_JSON_CAP = 3000
SIBLINGS_MAX = 8
SIBLING_DESC_CAP = 3000
SETLISTFM_CAP = 5000   # the prototype's cap; the brief names none for this section
BUNDLE_CAP = 150_000

_AUDIO = re.compile(r"\.(flac|mp3|shn|ogg)$", re.I)


def escape_braces(text: str) -> str:
    """Break every adjacent brace pair so the text can never read as a `{{…}}` template
    expression: `{{{` becomes `{ { {`."""
    text = re.sub(r"\{(?=\{)", "{ ", text)
    return re.sub(r"\}(?=\})", "} ", text)


def _clean(text) -> str:
    return escape_braces(str(text).replace("\x00", ""))


def _text_field(value) -> str:
    """An IA metadata field as text: a list (several values) joins with newlines, as
    gather's `_description` does."""
    if isinstance(value, list):
        value = "\n".join(str(v) for v in value)
    return str(value or "")


def _secs(value) -> str:
    s = length_seconds(value)
    return "?" if s is None else f"{s:g}"


@dataclass(frozen=True)
class Row:
    text: str
    filename: str | None = None
    identifier: str | None = None
    length_s: float | None = None
    title: str | None = None


@dataclass(frozen=True)
class FileMeta:
    name: str
    source: str
    format: str
    title: str
    length_s: float | None
    original: str | None


@dataclass(frozen=True)
class Bundle:
    slug: str
    show: Show
    overrides: Overrides
    view: ShowView
    provenance: Provenance | None
    selection: dict
    files: dict[str, FileMeta]
    sections: dict[str, list[Row]]
    text: str

    def own_row(self, kind: str, filename: str) -> Row | None:
        """`original-tag`: the row of the file's original (itself if it is one, else
        `FileMeta.original`). `derivative-tag`: the file's own derivative row."""
        meta = self.files.get(filename)
        if meta is None:
            return None
        if kind == "derivative-tag":
            name = filename if meta.source == "derivative" else None
        elif kind == "original-tag":
            name = filename if meta.source == "original" else meta.original
        else:
            return None
        if name is None:
            return None
        return next((r for r in self.sections[kind] if r.filename == name), None)

    def length_of(self, filename: str) -> float | None:
        """The larger of the show.json duration (track or excluded row) and the metadata
        length; None only when both are unknown."""
        known = [t.duration_sec for t in self.show.tracks if t.filename == filename]
        known += [x.get("duration_sec") for x in self.show.excluded_files
                  if x.get("filename") == filename]
        meta = self.files.get(filename)
        known.append(meta.length_s if meta else None)
        known = [k for k in known if k is not None]
        return max(known) if known else None


def _file_meta(f: dict) -> FileMeta:
    return FileMeta(name=f["name"], source=f.get("source", ""), format=f.get("format", ""),
                    title=_clean(f.get("title", "") or ""), length_s=length_seconds(f.get("length")),
                    original=f.get("original"))


def _audio(md: dict) -> list[dict]:
    return [f for f in md.get("files", []) if _AUDIO.search(f.get("name", ""))]


def _file_rows(files: list[dict], source: str, ident: str | None) -> list[Row]:
    rows = []
    for f in [f for f in files if f.get("source") == source][:ROWS_PER_ITEM]:
        m = _file_meta(f)
        fields = [m.name, m.format, m.title, _secs(f.get("length"))]
        if ident:
            fields = [ident, m.name, m.title, _secs(f.get("length"))]
        rows.append(Row(text=_clean(" | ".join(str(x) for x in fields)), filename=m.name,
                        identifier=ident, length_s=m.length_s, title=m.title))
    return rows


def _sibling_rows(ident: str, md: dict | None) -> list[Row]:
    if md is None:
        return [Row(text=_clean(f"{ident}: (metadata unavailable)"), identifier=ident)]
    desc = _text_field(md.get("metadata", {}).get("description")).strip()[:SIBLING_DESC_CAP]
    rows = [Row(text=_clean(desc), identifier=ident)] if desc else []
    files = _audio(md)
    for src in ("original", "derivative"):
        rows += _file_rows(files, src, ident)
    return rows


def _read_text(path, cap: int) -> str:
    try:
        return path.read_text()[:cap]
    except FileNotFoundError:
        return "(none)"


def _json_section(path, cap: int) -> str:
    try:
        return json.dumps(read_json(path), indent=1)[:cap]
    except FileNotFoundError:
        return "(none)"


def build_bundle(show_ws: ShowWorkspace, ia, config: Config) -> Bundle:
    view = capture_view(show_ws)
    show = read_model(show_ws.show, Show)
    overrides = read_overrides(show_ws)
    provenance = read_model(show_ws.provenance, Provenance) if view.provenance else None
    selection = read_json(show_ws.selection) if show_ws.selection.exists() else {}
    slug = show_ws.dir.name
    md = ia.metadata(show.identifier)
    meta = md.get("metadata", {})
    audio = _audio(md)
    files = {f["name"]: _file_meta(f) for f in audio}

    sections: dict[str, list[Row]] = {k: [] for k in EVIDENCE_KINDS}
    desc = _text_field(meta.get("description")).strip()[:DESC_CAP]
    notes = _text_field(meta.get("notes")).strip()[:NOTES_CAP]
    sections["taper-description"] = [Row(text=_clean(t)) for t in (desc, notes) if t]
    sections["original-tag"] = _file_rows(audio, "original", None)
    sections["derivative-tag"] = _file_rows(audio, "derivative", None)

    info = recording_info(show_ws)
    sib_blocks: list[list[Row]] = []
    for c in (info.considered if info else [])[:SIBLINGS_MAX]:
        try:
            sib_md = ia.metadata(c.identifier)
        except (IAError, httpx.HTTPError, ValueError):  # one unreachable sibling must not fail the bundle
            sib_md = None
        sib_blocks.append(_sibling_rows(c.identifier, sib_md))

    art, date = show.artist, show.item_date or show.date   # gather looks up by the item's date
    cache = config.root / "cache" / f"{setlistfm.cache_key(art, date)}.json"
    try:
        sl = json.loads(cache.read_text()).get("setlist")
    except (OSError, ValueError, AttributeError):
        sl = None
    if sl:
        sections["setlistfm"] = [Row(text=_clean(json.dumps(sl, indent=1)[:SETLISTFM_CAP]))]
    if config.jerrybase.enabled:
        sections["jerrybase"] = [Row(text=_clean(repr(e))) for e in jerrybase.lookup(art, date)]
    reviews = []
    for r in (md.get("reviews") or [])[:REVIEWS_MAX]:
        body = str(r.get("reviewbody", "")).replace("\n", " ")[:REVIEW_CAP]
        reviews.append(Row(text=_clean(f"[{str(r.get('reviewdate', ''))[:10]} {r.get('stars', '')}*] "
                                       f"{r.get('reviewtitle', '')}: {body}")))
    sections["review"] = reviews

    research = _read_text(show_ws.research, RESEARCH_CAP)
    n_sib = len(sib_blocks)
    while True:
        sections["sibling-tracks"] = [r for b in sib_blocks[:n_sib] for r in b]
        text = _render(slug, show, overrides, view, show_ws, selection, sections, research)
        if len(text) <= BUNDLE_CAP:
            break
        if n_sib:
            n_sib -= 1
        elif research:
            research = research[:max(0, len(research) - (len(text) - BUNDLE_CAP))]
        else:
            break
    return Bundle(slug=slug, show=show, overrides=overrides, view=view, provenance=provenance,
                  selection=selection, files=files, sections=sections, text=text)


def _render(slug, show, overrides, view, show_ws, selection, sections, research) -> str:
    out = [f"# {slug}", "## review flags", "\n".join(f"- {f}" for f in show.review_flags)]
    out.append("## track table")
    out.append("n | set | title | title_source | matched | dur s | file")
    out.append("\n".join(
        f"{i} | {t.set} | {t.title} | {t.title_source} | {t.matched} | "
        f"{'?' if t.duration_sec is None else round(t.duration_sec)} | {t.filename}" for i, t in enumerate(show.tracks, 1)))
    out.append("## excluded files")
    out.append("filename | reasons | dur s")
    out.append("\n".join(f"{x.get('filename')} | {x.get('reasons')} | {'?' if x.get('duration_sec') is None else x.get('duration_sec')}"
                         for x in show.excluded_files))
    out.append("## overrides.json")
    out.append(json.dumps(overrides.model_dump(mode="json"), indent=1)
               if view.overrides is not None else "(none)")
    out.append("## vetting")
    out.append(_json_section(show_ws.vetting, VETTING_CAP))
    out.append("## notes")
    out.append(json.dumps(read_model(show_ws.notes, ShowNotes).model_dump(mode="json"),
                          indent=1)[:NOTES_JSON_CAP] if show_ws.notes.exists() else "(none)")
    out.append("## research")
    out.append(research)
    out.append("## briefing")
    out.append(_read_text(show_ws.briefing_md, BRIEFING_CAP))
    out.append("## considered recordings")
    out.append("identifier | lineage | kept_tracks | title_fraction | score")
    chosen = selection.get("identifier")
    for ident, s in (selection.get("scores") or {}).items():
        out.append(f"{'* ' if ident == chosen else ''}{ident} | {s.get('lineage', '')} | "
                   f"{s.get('kept_tracks', '')} | {s.get('title_fraction', '')} | {s.get('score', '')}")
    for kind in EVIDENCE_KINDS:
        out.append(f"## evidence: {kind}")
        out.append("\n".join(r.text for r in sections[kind]))
    return _clean("\n".join(out))
