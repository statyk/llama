"""Station model: scan a delivered-packages folder (`[station] root`) for
emcee packages and compute each one's voice readiness (spec section 2).
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from emcee.package_io import Package, UnsupportedPackage


@dataclass
class PackageStatus:
    path: Path
    state: str  # "ready" | "pending" | "unsupported"
    reasons: list[str] = field(default_factory=list)


def readiness(pkg: Package) -> tuple[bool, list[str]]:
    """(ok, reasons) over the four independent legs: script present, DJ audio
    present, broadcast.m3u present, every manifest track's audio file on
    disk. `reasons` names each failing leg (empty when ready). Callers must
    have already screened out unsupported (pre-v3) packages -- this assumes
    `pkg.manifest()` succeeds and will propagate `UnsupportedPackage`/
    `EmceeError` if it doesn't."""
    manifest = pkg.manifest()
    reasons: list[str] = []

    dj_notes = manifest.get("dj_notes")
    if dj_notes is None or not (pkg.dir / "dj-notes.md").exists():
        reasons.append("no DJ script (dj_notes block + dj-notes.md required)")

    dj_audio = manifest.get("dj_audio")
    if dj_audio is None:
        reasons.append("no DJ audio (unvoiced)")
    else:
        clips = [*dj_audio.get("set_intros", {}).values(), dj_audio.get("outro")]
        missing_clips = [c for c in clips if c and not (pkg.dir / c).exists()]
        if missing_clips:
            reasons.append(
                f"{len(missing_clips)} DJ audio clip(s) missing on disk: "
                + ", ".join(sorted(missing_clips))
            )

    if not (pkg.dir / "broadcast.m3u").exists():
        reasons.append("no broadcast.m3u")

    tracks = manifest.get("tracks", [])
    missing_tracks = [
        t["filename"]
        for t in tracks
        if not (pkg.dir / "audio" / t["filename"]).exists()
    ]
    if missing_tracks:
        reasons.append(
            f"{len(missing_tracks)} of {len(tracks)} audio file(s) missing: "
            + ", ".join(sorted(missing_tracks))
        )

    return (not reasons), reasons


def scan(station_root: Path) -> list[PackageStatus]:
    """Every direct subdirectory of `station_root` containing a
    `manifest.json` is a package; anything else (files, dirs without a
    manifest) is skipped. A v2-or-earlier manifest yields `state=
    "unsupported"` and is never touched further.

    A missing or non-directory `station_root` yields an empty list rather
    than raising -- `scan` alone can't distinguish "not configured yet" from
    "legitimately empty", so that judgment call is left to callers. `emcee
    run`/`emcee status` (Task 9) are expected to raise an `EmceeError` naming
    `[station] root` when they need "not configured"/"missing" to be a hard
    error; `scan`'s empty-list result is what they check for that.
    """
    root = Path(station_root)
    if not root.is_dir():
        return []

    statuses: list[PackageStatus] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        if not (entry / "manifest.json").exists():
            continue
        pkg = Package(entry)
        try:
            pkg.manifest()
        except UnsupportedPackage:
            version = json.loads(pkg.manifest_path.read_text()).get(
                "schema_version", "?"
            )
            statuses.append(
                PackageStatus(
                    path=entry,
                    state="unsupported",
                    reasons=[f"unsupported (v{version} — re-deliver from llama)"],
                )
            )
            continue
        ok, reasons = readiness(pkg)
        statuses.append(
            PackageStatus(path=entry, state="ready" if ok else "pending", reasons=reasons)
        )
    return statuses
