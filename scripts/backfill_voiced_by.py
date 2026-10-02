#!/usr/bin/env python3
"""One-off: backfill `dj_audio.presenter` on packages emcee voiced before it
recorded the presenter.

For each voiced package whose `dj_audio` lacks the `presenter` key, look for
exactly one presenter's on-air `name` (whole word, case-sensitive) in the
script text (`dj_notes`). One match -> that presenter's id; zero or several
-> left as `?`. Dry run by default; `--apply` writes via emcee's
`rewrite_manifest`. Needs emcee installed (it may import it; emcee never
imports this).
"""
import argparse
import re
import sys
from pathlib import Path

from emcee.config import load_config
from emcee.errors import EmceeError
from emcee.models import DJAudioBlock, ScriptNotes
from emcee.package_io import Package, rewrite_manifest
from emcee.presenters import Presenter, list_presenters


def script_text(dj_notes: dict) -> str:
    """Every string the script holds: context, set_intros values, outro."""
    parts = [dj_notes.get("context"), dj_notes.get("outro")]
    intros = dj_notes.get("set_intros")
    if isinstance(intros, dict):
        parts.extend(intros.values())
    return "\n".join(p for p in parts if isinstance(p, str))


def matching_ids(text: str, presenters: list[Presenter]) -> list[str]:
    return [
        p.id for p in presenters
        if re.search(r"(?<!\w)" + re.escape(p.name) + r"(?!\w)", text)
    ]


def backfill(station_root: Path, presenters: list[Presenter], apply: bool) -> None:
    for d in sorted(station_root.iterdir()):
        if not d.is_dir() or d.name.startswith(".") or not (d / "manifest.json").exists():
            continue
        pkg = Package(d)
        try:
            manifest = pkg.manifest()
        except EmceeError as exc:
            print(f"skip {d.name}: {exc}")
            continue
        dj_audio = manifest.get("dj_audio")
        if not isinstance(dj_audio, dict) or "presenter" in dj_audio:
            continue
        dj_notes = manifest.get("dj_notes")
        text = script_text(dj_notes) if isinstance(dj_notes, dict) else ""
        ids = matching_ids(text, presenters)
        if len(ids) != 1:
            why = "no presenter name found" if not ids else f"ambiguous: {', '.join(ids)}"
            print(f"{d.name}: left as ? ({why})")
            continue
        print(f"{d.name}: {ids[0]}")
        if apply:
            try:
                rewrite_manifest(
                    pkg,
                    dj_notes=ScriptNotes.model_validate(dj_notes),
                    dj_audio=DJAudioBlock.model_validate({**dj_audio, "presenter": ids[0]}),
                )
            except Exception as exc:  # one bad package must not stop the sweep
                print(f"skip {d.name}: {exc}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--station-root", type=Path, default=None)
    ap.add_argument("--apply", action="store_true", help="write the manifests")
    args = ap.parse_args(argv)
    config = load_config()
    root = args.station_root or config.station.root
    if root is None:
        print("no station root: pass --station-root or set [station] root", file=sys.stderr)
        return 2
    presenters = [p for _, p in list_presenters(config.root) if isinstance(p, Presenter)]
    backfill(Path(root), presenters, args.apply)
    if not args.apply:
        print("dry run: pass --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
